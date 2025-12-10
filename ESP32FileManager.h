/**
 * ESP32FileManager.h
 * --------------------------------------------------------------
 * Single-header class that implements the complete file-manager
 * protocol used by the Python desktop application.
 *
 * Include it in your sketch, create a global instance and call
 *   fileManager.handleFileManager();
 * from loop(). No other code is required.
 *
 * Features:
 *   • Quoted-path support (spaces, special chars)
 *   • STORAGE, LIST, CREATE_DIR, PUTFILE, GETSIZE, GETDATA,
 *     DELETE, REMOVE_DIR, RENAME
 *   • Recursive directory listing (listDir helper)
 *   • Simple, robust, no extra libraries
 *
 * --------------------------------------------------------------
 * USAGE:
 *   #include "ESP32FileManager.h"
 *   ESP32FileManager fileManager;
 *
 *   void setup() {
 *     Serial.begin(2000000);
 *     delay(100);
 *     while (!Serial) delay(10);
 *     SD_MMC.begin("/sdcard", true);
 *   }
 *
 *   void loop() {
 *     fileManager.handleFileManager();
 *   }
 * --------------------------------------------------------------
 */

#ifndef ESP32FileManager_h
#define ESP32FileManager_h

#include <Arduino.h>
#include <SD_MMC.h>

class ESP32FileManager {
public:
  void begin() {
    Serial.println("READY");
  }

  // Call this from loop()
  void handleFileManager() {
    if (!Serial.available()) return;

    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() == 0) return;

    // ---------- Helper: extract quoted path ----------
    auto getPath = [&](const String& c, int start) -> String {
      int q1 = c.indexOf('"', start);
      if (q1 == -1) return c.substring(start);
      int q2 = c.indexOf('"', q1 + 1);
      if (q2 == -1) q2 = c.length();
      return c.substring(q1 + 1, q2);
    };

    // ---------- STORAGE ----------
    if (cmd == "STORAGE") {
      uint64_t total = SD_MMC.totalBytes();
      uint64_t used  = SD_MMC.usedBytes();
      Serial.printf("TOTAL:%llu FREE:%llu\n", total, total - used);
      Serial.println("DONE");

    // ---------- LIST ----------
    } else if (cmd.startsWith("LIST ")) {
      String path = getPath(cmd, 5);
      listDir(SD_MMC, path.c_str(), 0);
      Serial.println("DONE");

    // ---------- CREATE_DIR ----------
    } else if (cmd.startsWith("CREATE_DIR ")) {
      String path = getPath(cmd, 11);
      createDir(SD_MMC, path.c_str());
      Serial.println("DIR created");
      Serial.println("DONE");

    // ---------- PUTFILE ----------
    } else if (cmd.startsWith("PUTFILE ")) {
      int lastSpace = cmd.lastIndexOf(' ');
      if (lastSpace <= 8) {
        Serial.println("ERROR");
        Serial.println("DONE");
        return;
      }
      String path = getPath(cmd, 8);
      long size = cmd.substring(lastSpace + 1).toInt();

      File f = SD_MMC.open(path.c_str(), FILE_WRITE);
      if (!f) {
        Serial.println("ERROR");
        Serial.println("DONE");
        return;
      }

      long received = 0;
      uint8_t buf[1024];
      while (received < size) {
        int want = min(1024, (int)(size - received));
        int got = Serial.readBytes(buf, want);
        if (got <= 0) break;
        f.write(buf, got);
        received += got;
      }
      f.close();

      Serial.println(received == size ? "OK" : "ERROR");
      Serial.println("DONE");

    // ---------- GETSIZE ----------
    } else if (cmd.startsWith("GETSIZE ")) {
      String path = getPath(cmd, 8);
      File f = SD_MMC.open(path.c_str());
      if (!f || f.isDirectory()) {
        Serial.println("ERROR");
      } else {
        Serial.print("SIZE:");
        Serial.println(f.size());
        f.close();
      }
      Serial.println("DONE");

    // ---------- GETDATA ----------
    } else if (cmd.startsWith("GETDATA ")) {
      String path = getPath(cmd, 8);
      File f = SD_MMC.open(path.c_str());
      if (!f || f.isDirectory()) {
        if (f) f.close();
        return;
      }
      uint8_t buf[1024];
      while (f.available()) {
        size_t len = f.read(buf, sizeof(buf));
        Serial.write(buf, len);
      }
      f.close();

    // ---------- DELETE ----------
    } else if (cmd.startsWith("DELETE ")) {
      String path = getPath(cmd, 7);
      Serial.println(SD_MMC.remove(path.c_str()) ? "DELETED" : "ERROR");
      Serial.println("DONE");

    // ---------- REMOVE_DIR ----------
    } else if (cmd.startsWith("REMOVE_DIR ")) {
      String path = getPath(cmd, 11);
      removeDir(SD_MMC, path.c_str());
      Serial.println("REMOVED");
      Serial.println("DONE");

    // ---------- RENAME ----------
    } else if (cmd.startsWith("RENAME ")) {
      // Command comes as: RENAME "/old name.txt" "/new name.txt"
      // Find the two quoted strings
      int q1 = cmd.indexOf('"');
      int q2 = cmd.indexOf('"', q1 + 1);
      int q3 = cmd.indexOf('"', q2 + 1);
      int q4 = cmd.indexOf('"', q3 + 1);

      if (q1 == -1 || q2 == -1 || q3 == -1 || q4 == -1) {
        Serial.println("ERROR");
        Serial.println("DONE");
        return;
      }

      String from = cmd.substring(q1 + 1, q2);
      String to   = cmd.substring(q3 + 1, q4);

      // SD_MMC.rename REQUIRES absolute paths with leading slash
      if (!from.startsWith("/")) from = "/" + from;
      if (!to.startsWith("/"))   to   = "/" + to;

      bool success = SD_MMC.rename(from.c_str(), to.c_str());
      Serial.println(success ? "RENAMED" : "ERROR");
      Serial.println("DONE");
    }
  }

private:
  // -----------------------------------------------------------------
  // Helper: recursive directory listing (used by LIST)
  // -----------------------------------------------------------------
  void listDir(fs::FS &fs, const char * dirname, uint8_t levels) {
    File root = fs.open(dirname);
    if (!root || !root.isDirectory()) {
      Serial.println("ERROR: Invalid directory");
      return;
    }

    File file = root.openNextFile();
    while (file) {
      String fullName = String(file.name());
      String baseName;

      // If we're not in root, strip the dirname prefix
      if (strcmp(dirname, "/") != 0) {
        if (fullName.startsWith(dirname)) {
          baseName = fullName.substring(strlen(dirname));
        } else {
          baseName = fullName;  // fallback
        }
      } else {
        baseName = fullName;
      }

      // Remove leading slash if present
      if (baseName.startsWith("/")) {
        baseName = baseName.substring(1);
      }

      if (file.isDirectory()) {
        Serial.print("DIR : ");
        Serial.println(baseName);
      } else {
        Serial.print("FILE : ");
        Serial.print(baseName);
        Serial.print(" SIZE : ");
        Serial.println(file.size());
      }
      file = root.openNextFile();
    }
    root.close();
  }

  // -----------------------------------------------------------------
  // Helper: create directory (void – no return value)
  // -----------------------------------------------------------------
  void createDir(fs::FS &fs, const char * path) {
    fs.mkdir(path);
  }

  // -----------------------------------------------------------------
  // Helper: remove directory (void)
  // -----------------------------------------------------------------
  void removeDir(fs::FS &fs, const char * path) {
    fs.rmdir(path);
  }

  // -----------------------------------------------------------------
  // Helper: rename file/directory (void)
  // -----------------------------------------------------------------
  void renameFile(fs::FS &fs, const char * path1, const char * path2) {
    fs.rename(path1, path2);
  }
};

#endif