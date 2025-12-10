import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog, scrolledtext
import serial
import serial.tools.list_ports
import os
import threading
import time

class ESPFileBrowser(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ESP32 eMMC File Manager")
        self.geometry("1200x800")
        self.ser = None
        self.current_path = "/"

        # === Connection Bar ===
        top = tk.Frame(self)
        top.pack(pady=8, fill=tk.X, padx=10)
        tk.Label(top, text="Port:").pack(side=tk.LEFT)
        self.port_combo = ttk.Combobox(top, values=self.get_ports(), width=15)
        self.port_combo.pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="Refresh", command=self.refresh_ports).pack(side=tk.LEFT)

        tk.Label(top, text="Baud:").pack(side=tk.LEFT, padx=(30,5))
        self.baud_combo = ttk.Combobox(top, values=[9600, 19200, 31250, 38400, 57600, 74880, 115200, 230400, 250000, 460800, 500000, 921600, 1000000, 2000000], width=12, state="readonly")
        self.baud_combo.set(115200)
        self.baud_combo.pack(side=tk.LEFT, padx=5)

        tk.Button(top, text="Connect", bg="#1b5e20", fg="white", font=("Segoe UI", 10, "bold"),
                  command=self.connect).pack(side=tk.LEFT, padx=15)

        # === Storage + Path ===
        info_frame = tk.Frame(self)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        self.storage_label = tk.Label(info_frame, text="Storage: Not connected", font=("Segoe UI", 10))
        self.storage_label.pack(side=tk.LEFT)
        self.path_label = tk.Label(info_frame, text="/", font=("Segoe UI", 10, "bold"), fg="#0066cc")
        self.path_label.pack(side=tk.RIGHT)

        # === Toolbar ===
        toolbar = tk.Frame(self)
        toolbar.pack(fill=tk.X, pady=5)
        tk.Button(toolbar, text="New Folder", command=self.new_folder).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Upload", command=self.upload).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Download", command=self.download_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Delete", command=self.delete_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Rename", command=self.rename_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=20)
        tk.Button(toolbar, text="Up", command=self.go_up).pack(side=tk.RIGHT, padx=5)

        # === Treeview ===
        tree_frame = tk.Frame(self)
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
        console_frame = tk.LabelFrame(self, text="Serial Console")
        console_frame.pack(fill=tk.X, padx=10, pady=5)
        self.console = scrolledtext.ScrolledText(console_frame, height=8, state='disabled', bg='black', fg='#00ff00', font=("Consolas", 9))
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

if __name__ == "__main__":
    app = ESPFileBrowser()
    app.mainloop()
