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
 *   • Non-blocking PUTFILE with chunked flow control
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

  // Returns true while a file transfer is in progress.
  // Use this to suppress debug Serial output that would corrupt the protocol.
  bool isTransferActive() const {
    return _putActive;
  }

  // Register a callback that fires periodically during long transfers.
  // Use this to send heartbeats or perform other time-critical tasks.
  void setKeepAliveCallback(void (*callback)()) {
    _keepAliveCallback = callback;
  }

  // Call this from loop() — returns quickly, never blocks long
  void handleFileManager() {
    // If a PUTFILE transfer is in progress, handle it non-blocking
    if (_putActive) {
      _handlePutData();
      return;
    }

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

    // ---------- PUTFILE (non-blocking start) ----------
    } else if (cmd.startsWith("PUTFILE ")) {
      int lastSpace = cmd.lastIndexOf(' ');
      if (lastSpace <= 8) {
        Serial.println("ERROR");
        Serial.println("DONE");
        return;
      }
      String path = getPath(cmd, 8);
      _putSize = cmd.substring(lastSpace + 1).toInt();

      _putFile = SD_MMC.open(path.c_str(), FILE_WRITE);
      if (!_putFile) {
        Serial.println("ERROR");
        Serial.println("DONE");
        return;
      }

      _putReceived = 0;
      _putChunkPos = 0;
      _putLastData = millis();
      _putActive = true;
      Serial.printf("READY %d\n", PUT_CHUNK);
      Serial.flush();  // Ensure READY is sent over USB before reading
      _lastKeepAlive = millis();
      _handlePutData();  // Stay here until transfer completes

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
      unsigned long lastKA = millis();
      while (f.available()) {
        size_t len = f.read(buf, sizeof(buf));
        Serial.write(buf, len);
        if (millis() - lastKA >= 200) {
          if (_keepAliveCallback) _keepAliveCallback();
          lastKA = millis();
          delay(1);  // Feed TWDT
        }
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
  // PUTFILE non-blocking state
  // -----------------------------------------------------------------
  static const int PUT_CHUNK = 4096;
  bool _putActive = false;
  File _putFile;
  long _putSize = 0;
  long _putReceived = 0;
  int  _putChunkPos = 0;
  unsigned long _putLastData = 0;
  uint8_t _putBuf[4096];
  void (*_keepAliveCallback)() = nullptr;
  unsigned long _lastKeepAlive = 0;

  // Loops internally for the entire PUTFILE transfer.
  // Uses available()+read() instead of timed readBytes for reliable HWCDC support.
  // Keep-alive callback fires every ~200ms for heartbeat support.
  void _handlePutData() {
    while (_putActive) {
      long remaining = _putSize - _putReceived;
      int chunkWant = (remaining > PUT_CHUNK) ? PUT_CHUNK : (int)remaining;

      // Read whatever is available right now (no timeout dependency)
      int avail = Serial.available();
      if (avail > 0) {
        int toRead = avail;
        if (toRead > chunkWant - _putChunkPos) toRead = chunkWant - _putChunkPos;
        int got = Serial.readBytes(_putBuf + _putChunkPos, toRead);
        if (got > 0) {
          _putChunkPos += got;
          _putLastData = millis();
        }
      }

      delay(1);  // Required: allows USB packet processing between reads

      // Fire keep-alive callback every ~200ms to let app send heartbeats
      if (_keepAliveCallback && millis() - _lastKeepAlive >= 200) {
        _keepAliveCallback();
        _lastKeepAlive = millis();
      }

      // Full chunk accumulated — write to SD and request next
      if (_putChunkPos >= chunkWant) {
        _putFile.write(_putBuf, _putChunkPos);
        _putReceived += _putChunkPos;
        _putChunkPos = 0;

        if (_putReceived >= _putSize) {
          _putFile.close();
          Serial.println("OK");
          Serial.println("DONE");
          _putActive = false;
        } else {
          Serial.println("NEXT");
        }
      } else if (millis() - _putLastData > 10000) {
        _putFile.close();
        Serial.println("ERROR");
        Serial.println("DONE");
        _putActive = false;
      }
    }
  }

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