import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog, scrolledtext
import serial
import serial.tools.list_ports
import os
import threading
import time
import ctypes
import sys

class ESPFileBrowser(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ESP32 eMMC File Manager")
        self.geometry("1200x800")
        self.ser = None
        self.current_path = "/"
        
        # Set icon if available (PyInstaller friendly)
        try:
            icon_path = self.resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        # === Dark Theme Colors ===

        # === Dark Theme Colors ===
        self.bg_color = "#1e1e1e"
        self.fg_color = "#e0e0e0"
        self.accent_color = "#3c3c3c"
        self.highlight_color = "#0078d4"
        
        # Configure root window
        self.configure(bg=self.bg_color)
        
        # Enable dark title bar on Windows
        self.update()
        try:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass  # Silently fail on non-Windows or older Windows versions
        
        # Configure ttk styles for dark theme
        style = ttk.Style()
        style.theme_use('clam')
        
        # Treeview styling
        style.configure("Treeview",
                        background=self.accent_color,
                        foreground=self.fg_color,
                        fieldbackground=self.accent_color,
                        borderwidth=0)
        style.configure("Treeview.Heading",
                        background="#2d2d2d",
                        foreground=self.fg_color,
                        borderwidth=0,
                        relief="flat")
        style.map("Treeview",
                  background=[("selected", self.highlight_color)],
                  foreground=[("selected", "white")])
        style.map("Treeview.Heading",
                  background=[("active", "#4a4a4a")])
        
        # Combobox styling (including dropdown)
        style.configure("TCombobox",
                        fieldbackground=self.accent_color,
                        background=self.accent_color,
                        foreground=self.fg_color,
                        arrowcolor=self.fg_color,
                        bordercolor=self.accent_color,
                        lightcolor=self.accent_color,
                        darkcolor=self.accent_color)
        style.map("TCombobox",
                  fieldbackground=[("readonly", self.accent_color), ("disabled", "#2d2d2d")],
                  background=[("active", "#4a4a4a"), ("pressed", "#4a4a4a")],
                  foreground=[("disabled", "#808080")],
                  arrowcolor=[("disabled", "#808080")])
        
        # Style the combobox dropdown listbox
        self.option_add("*TCombobox*Listbox*Background", self.accent_color)
        self.option_add("*TCombobox*Listbox*Foreground", self.fg_color)
        self.option_add("*TCombobox*Listbox*selectBackground", self.highlight_color)
        self.option_add("*TCombobox*Listbox*selectForeground", "white")
        
        # Scrollbar styling
        style.configure("Vertical.TScrollbar",
                        background=self.accent_color,
                        troughcolor=self.bg_color,
                        bordercolor=self.bg_color,
                        arrowcolor=self.fg_color,
                        borderwidth=0)
        style.map("Vertical.TScrollbar",
                  background=[("active", "#4a4a4a"), ("pressed", "#555555")])
        
        # Horizontal scrollbar
        style.configure("Horizontal.TScrollbar",
                        background=self.accent_color,
                        troughcolor=self.bg_color,
                        bordercolor=self.bg_color,
                        arrowcolor=self.fg_color,
                        borderwidth=0)
        style.map("Horizontal.TScrollbar",
                  background=[("active", "#4a4a4a"), ("pressed", "#555555")])
        
        # Progressbar styling
        style.configure("TProgressbar",
                        background=self.highlight_color,
                        troughcolor=self.accent_color,
                        bordercolor=self.accent_color)
        
        # LabelFrame styling
        style.configure("TLabelframe",
                        background=self.bg_color,
                        foreground=self.fg_color,
                        bordercolor=self.accent_color)
        style.configure("TLabelframe.Label",
                        background=self.bg_color,
                        foreground=self.fg_color)

        # === Connection Bar ===
        top = tk.Frame(self, bg=self.bg_color)
        top.pack(pady=8, fill=tk.X, padx=10)
        tk.Label(top, text="Port:", bg=self.bg_color, fg=self.fg_color).pack(side=tk.LEFT)
        self.port_combo = ttk.Combobox(top, values=self.get_ports(), width=15)
        self.port_combo.pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="Refresh", command=self.refresh_ports,
                  bg=self.accent_color, fg=self.fg_color, activebackground="#4a4a4a",
                  activeforeground="white", relief=tk.FLAT, padx=8, pady=2).pack(side=tk.LEFT)

        tk.Label(top, text="Baud:", bg=self.bg_color, fg=self.fg_color).pack(side=tk.LEFT, padx=(30,5))
        self.baud_combo = ttk.Combobox(top, values=[9600, 19200, 31250, 38400, 57600, 74880, 115200, 230400, 250000, 460800, 500000, 921600, 1000000, 2000000], width=12, state="readonly")
        self.baud_combo.set(115200)
        self.baud_combo.pack(side=tk.LEFT, padx=5)

        tk.Button(top, text="Connect", bg="#1b5e20", fg="white", font=("Segoe UI", 10, "bold"),
                  command=self.connect, activebackground="#2e7d32", relief=tk.FLAT,
                  padx=10, pady=3).pack(side=tk.LEFT, padx=10)
        tk.Button(top, text="Disconnect", bg="#b71c1c", fg="white", font=("Segoe UI", 10, "bold"),
                  command=self.disconnect, activebackground="#c62828", relief=tk.FLAT,
                  padx=10, pady=3).pack(side=tk.LEFT, padx=5)

        # === Storage + Path ===
        info_frame = tk.Frame(self, bg=self.bg_color)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        self.storage_label = tk.Label(info_frame, text="Storage: Not connected", font=("Segoe UI", 10),
                                       bg=self.bg_color, fg=self.fg_color)
        self.storage_label.pack(side=tk.LEFT)
        self.path_label = tk.Label(info_frame, text="/", font=("Segoe UI", 10, "bold"),
                                    bg=self.bg_color, fg="#4fc3f7")
        self.path_label.pack(side=tk.RIGHT)

        # === Toolbar ===
        toolbar = tk.Frame(self, bg=self.bg_color)
        toolbar.pack(fill=tk.X, pady=5)
        btn_style = {"bg": self.accent_color, "fg": self.fg_color, "activebackground": "#4a4a4a",
                     "activeforeground": "white", "relief": tk.FLAT, "padx": 10, "pady": 3}
        tk.Button(toolbar, text="New Folder", command=self.new_folder, **btn_style).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Upload", command=self.upload, **btn_style).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Download", command=self.download_selected, **btn_style).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Delete", command=self.delete_selected, **btn_style).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Rename", command=self.rename_selected, **btn_style).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Refresh", command=self.refresh, **btn_style).pack(side=tk.LEFT, padx=20)
        tk.Button(toolbar, text="Up", command=self.go_up, **btn_style).pack(side=tk.RIGHT, padx=5)

        # === Treeview ===
        tree_frame = tk.Frame(self, bg=self.bg_color)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tree = ttk.Treeview(tree_frame, columns=("size",), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size")
        self.tree.column("size", width=140, anchor="e")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.bind("<Double-1>", self.on_double_click)

        # === Console ===
        console_frame = tk.LabelFrame(self, text="Serial Console", bg=self.bg_color, fg=self.fg_color,
                                       font=("Segoe UI", 9))
        console_frame.pack(fill=tk.X, padx=10, pady=5)
        self.console = scrolledtext.ScrolledText(console_frame, height=8, state='disabled',
                                                  bg='#0d0d0d', fg='#00ff00', font=("Consolas", 9),
                                                  insertbackground='white')
        self.console.pack(fill=tk.X, padx=5, pady=5)

    def log(self, text):
        self.console.config(state='normal')
        self.console.insert(tk.END, text + "\n")
        self.console.see(tk.END)
        self.console.config(state='disabled')

    def get_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]

    def refresh_ports(self):
        self.port_combo['values'] = self.get_ports()

    def connect(self):
        port = self.port_combo.get()
        if not port:
            messagebox.showerror("Error", "Select a COM port")
            return
        try:
            baud = int(self.baud_combo.get())
            self.ser = serial.Serial(port, baud, timeout=1, write_timeout=5)
            time.sleep(1.2)
            self.ser.reset_input_buffer()
            self.log(f"Connected to {port} @ {baud:,} baud")
            self.after(50, self.refresh)  # Ultra-fast refresh
        except Exception as e:
            messagebox.showerror("Connection Failed", str(e))

    def disconnect(self):
        """Close the serial connection and reset the UI state"""
        if self.ser:
            try:
                self.ser.close()
                self.log("Disconnected from serial port")
            except Exception as e:
                self.log(f"Error disconnecting: {e}")
            finally:
                self.ser = None
        self.tree.delete(*self.tree.get_children())
        self.storage_label.config(text="Storage: Not connected")
        self.current_path = "/"
        self.path_label.config(text="/")

    def send(self, cmd):
        if not self.ser: return
        self.ser.reset_input_buffer()
        self.ser.write((cmd + "\n").encode())
        self.log(f"→ {cmd}")

    def read_response(self, timeout=1.0):
        """Lightning-fast response reader"""
        lines = []
        start = time.time()
        while time.time() - start < timeout:
            if self.ser.in_waiting > 0:
                line = self.ser.readline().decode(errors='ignore').strip()
                if line:
                    lines.append(line)
                    self.log(line)
                if line == "DONE":
                    return lines
            else:
                time.sleep(0.001)
        return lines

    def human_size(self, bytes_val):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:,.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:,.2f} TB"

    def refresh(self):
        if not self.ser: return
        self.tree.delete(*self.tree.get_children())
        self.path_label.config(text=self.current_path or "/")

        # Storage (fast)
        self.send("STORAGE")
        lines = self.read_response(0.5)
        total = free = 0
        for line in lines:
            if "TOTAL:" in line:
                parts = line.split(" FREE:")
                total = int(parts[0].split(":")[1])
                free = int(parts[1])
                self.storage_label.config(text=f"Total: {self.human_size(total)} | Free: {self.human_size(free)}")

        # List directory (fast)
        self.send(f"LIST {self.current_path}")
        lines = self.read_response(1.0)
        for line in lines:
            if line.startswith("DIR :"):
                name = line[6:].strip()
                self.tree.insert("", "end", text=" " + name, values=("",))
            elif line.startswith("FILE :"):
                parts = line.split(" SIZE : ")
                name = parts[0][7:].strip()
                size = int(parts[1])
                self.tree.insert("", "end", text=" " + name, values=(self.human_size(size),))

    def on_double_click(self, event):
        item = self.tree.selection()
        if not item: return
        name = self.tree.item(item[0], "text").strip()
        if self.tree.item(item[0], "values") == ("",):
            self.current_path = (self.current_path.rstrip("/") + "/" + name + "/").replace("//", "/")
            self.refresh()

    def go_up(self):
        if self.current_path != "/":
            self.current_path = os.path.dirname(self.current_path.rstrip("/")) + "/"
            if self.current_path == "/": self.current_path = "/"
            self.refresh()

    def new_folder(self):
        name = simpledialog.askstring("New Folder", "Name:")
        if name:
            path = self.current_path.rstrip("/") + "/" + name
            self.send(f"CREATE_DIR {path}")
            self.read_response(0.5)
            self.refresh()

    def upload(self):
        local = filedialog.askopenfilename()
        if not local: return
        name = os.path.basename(local)
        size = os.path.getsize(local)
        remote_path = f'"{self.current_path.rstrip("/")}/{name}"'

        win = tk.Toplevel(self)
        win.title("Uploading...")
        win.geometry("420x130")
        tk.Label(win, text="Uploading:").pack(pady=5)
        tk.Label(win, text=name, fg="blue").pack()
        pb = ttk.Progressbar(win, length=380, mode="determinate")
        pb.pack(pady=10)
        pb['maximum'] = size
        lbl = tk.Label(win, text="0 B / 0 B")
        lbl.pack()

        def run():
            try:
                self.send(f"PUTFILE {remote_path} {size}")
                time.sleep(0.05)
                with open(local, "rb") as f:
                    sent = 0
                    while sent < size:
                        chunk = f.read(16384)
                        if not chunk: break
                        self.ser.write(chunk)
                        sent += len(chunk)
                        pb['value'] = sent
                        lbl.config(text=f"{self.human_size(sent)} / {self.human_size(size)}")
                        win.update_idletasks()
                self.read_response(1.0)
                self.refresh()
                messagebox.showinfo("Success", f"Uploaded:\n{name}")
            except Exception as e:
                messagebox.showerror("Error", f"Upload failed:\n{e}")
            finally:
                win.destroy()

        threading.Thread(target=run, daemon=True).start()

    def download_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.tree.item(sel[0], "text").strip()
        if self.tree.item(sel[0], "values") == ("",):   # it's a folder
            return

        local_path = filedialog.asksaveasfilename(initialfile=name)
        if not local_path:
            return

        remote_path = f'"{self.current_path.rstrip("/")}/{name}"'   # <-- QUOTED PATH

        win = tk.Toplevel(self)
        win.title("Downloading...")
        win.geometry("420x110")
        tk.Label(win, text=f"Downloading {name}").pack(pady=10)
        pb = ttk.Progressbar(win, length=380, mode="determinate")
        pb.pack(pady=10)
        lbl = tk.Label(win, text="Getting size...")
        lbl.pack()

        def run():
            try:
                # ---- GET SIZE ----
                self.send(f"GETSIZE {remote_path}")
                resp = self.read_response(0.8)
                size_line = [l for l in resp if l.startswith("SIZE:")]
                if not size_line:
                    messagebox.showerror("Error", "Failed to get file size")
                    win.destroy()
                    return
                size = int(size_line[0].split(":", 1)[1])
                pb['maximum'] = size
                lbl.config(text="0 B / 0 B")

                # ---- GET DATA (binary) ----
                self.send(f"GETDATA {remote_path}")
                self.ser.reset_input_buffer()
                data = b""
                while len(data) < size:
                    chunk = self.ser.read(min(32768, size - len(data)))
                    if not chunk:
                        break
                    data += chunk
                    pb['value'] = len(data)
                    lbl.config(text=f"{self.human_size(len(data))} / {self.human_size(size)}")
                    win.update_idletasks()

                with open(local_path, "wb") as f:
                    f.write(data)

                messagebox.showinfo("Success", f"Downloaded {name}\n{self.human_size(size)}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
            finally:
                win.destroy()

        threading.Thread(target=run, daemon=True).start()

    def delete_recursive(self, path):
        """Delete folder and all contents recursively"""
        self.send(f"LIST {path}")
        lines = self.read_response(0.8)
        for line in lines:
            if line.startswith("DIR :"):
                subdir = line[6:].strip()
                self.delete_recursive(path.rstrip("/") + "/" + subdir)
            elif line.startswith("FILE :"):
                filename = line.split(" SIZE : ")[0][7:].strip()
                current_dir = path.rstrip('"')
                fullpath = f'{current_dir.rstrip("/")}/{filename}"'
                self.send(f"DELETE {fullpath}")
                self.read_response(0.3)

        self.send(f"REMOVE_DIR {path}")
        self.read_response(0.5)

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel: return
        name = self.tree.item(sel[0], "text").strip()
        full_path = f'"{self.current_path.rstrip("/")}/{name}"'
        is_dir = self.tree.item(sel[0], "values") == ("",)

        if is_dir:
            if messagebox.askyesno("Delete Folder", f"Delete folder and ALL contents?\n\n{name}"):
                win = tk.Toplevel(self); win.title("Deleting..."); tk.Label(win, text="Working...").pack(pady=20)
                def run(): self.delete_recursive(full_path); self.after(100, self.refresh); win.destroy()
                threading.Thread(target=run, daemon=True).start()
        else:
            if messagebox.askyesno("Delete File", f"Delete {name}?"):
                self.send(f"DELETE {full_path}")
                self.read_response(0.5)
                self.refresh()

    def rename_selected(self):
        sel = self.tree.selection()
        if not sel: return
        old_name = self.tree.item(sel[0], "text").strip()
        new_name = simpledialog.askstring("Rename", "New name:", initialvalue=old_name)
        if new_name and new_name != old_name:
            old_path = f'"{self.current_path.rstrip("/")}/{old_name}"'
            new_path = f'"{self.current_path.rstrip("/")}/{new_name}"'
            self.send(f"RENAME {old_path} {new_path}")
            self.read_response(0.5)
            self.refresh()

    def resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)

if __name__ == "__main__":
    app = ESPFileBrowser()
    app.mainloop()
