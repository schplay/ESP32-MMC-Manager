# ESP32 MMC File Manager (Desktop + Firmware)

A **full-featured, high-speed file manager** for the ESP32-S3 with MMC (SD or EMMC) storage.
It lets you:

* Browse directories (double-click to enter)
* Upload / download any file
* Create folders
* Rename / delete files **and** folders (recursive delete)
* See total / free storage in GB (2-decimal precision)
* Work with **any filename** – spaces, Unicode, special characters are fully supported

All communication is over a **single USB-Serial link** (up to **2 000 000 baud**).

---

## Purpose

I found myself with ESP32 based projects that have EMMC storage that needs to be managed (such as pre-loading files) and
wanted a tool that could do this without adding heavy features such as USB MSC or Web Servers to projects that don't 
need them. This tool solved that problem for me and it may be useful to you too.

---

## Desktop Application (Python)

### Requirements
```bash
pip install pyserial
```
### Run
```bash
python ESPFileManager.py
```

## ESP32 Firmware

### Hardware

* ESP32-S3 with SD or eMMC (SD_MMC)
* USB-CDC or native USB-Serial

### Library
Only the standard Arduino ESP32 core and SD_MMC are required.

### How to use
```cpp
#include "ESP32FileManager.h"

ESP32FileManager fileManager;   // global instance

void setup() {
  Serial.begin(115200);
  delay(100);
  while (!Serial) delay(10);

  if (!SD_MMC.begin("/sdcard", true)) {
    Serial.println("ERROR: Mount Failed");
    while (1) delay(100);
  }
}

void loop() {
  fileManager.handleFileManager();   // <-- ONLY THIS LINE NEEDED
}
```

## Protocol
All commands are line-based and end with \n.
Paths are quoted when they contain spaces.

STORAGE                     → TOTAL:1234567890 FREE:987654321\nDONE
LIST "/path"                → FILE : name.ext SIZE : 12345\nDIR : subdir\nDONE
CREATE_DIR "/new folder"    → DIR created\nDONE
PUTFILE "/file with spaces.txt" 54321   → (binary data follows)
GETSIZE "/file.txt"         → SIZE:54321\nDONE
GETDATA "/file.txt"         → (raw binary, exactly SIZE bytes)
DELETE "/file.txt"          → DELETED\nDONE
REMOVE_DIR "/folder"        → REMOVED\nDONE
RENAME "/old" "/new"        → RENAMED\nDONE

## Known Limitations
* **Maximum file size** – limited by RAM only when uploading (streamed in 16 KB chunks).
Downloads can be any size (streamed to PC).
* **Recursive delete** - may take a few seconds for very large folders (progress is shown in console).
* **Serial exclusivity** - during upload or download operations, other messages on the serial bus will corrupt the transfer so other serial communications (such as your ESP32 printing status messages) should be disabled for these operations.
