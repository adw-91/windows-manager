"""Diagnostic script to identify performance bottlenecks.

Run on the slow machine:
    python diagnose.py
"""

import time
import os

# Force software OpenGL BEFORE any Qt/pyqtgraph imports
# Uncomment one at a time to test which helps:
# os.environ["QT_OPENGL"] = "software"          # Test A: Mesa software OpenGL
# os.environ["QSG_RHI_BACKEND"] = "sw"           # Test B: Software RHI backend
# os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"       # Test C: Force Mesa on Linux (no-op on Windows usually)

times = {}

def mark(label: str) -> None:
    times[label] = time.perf_counter()
    elapsed = times[label] - times.get("__start", times[label])
    print(f"  [{elapsed:7.2f}s] {label}")

times["__start"] = time.perf_counter()
mark("Script start")

# Phase 1: Python imports (no Qt yet)
import sys
mark("stdlib imports")

import numpy as np
mark("numpy import")

import psutil
mark("psutil import")

# Phase 2: Qt imports
from PySide6.QtWidgets import QApplication
mark("PySide6.QtWidgets import")

from PySide6.QtCore import Qt
mark("PySide6.QtCore import")

# Phase 3: pyqtgraph (known to probe GPU)
import pyqtgraph as pg
mark("pyqtgraph import")

pg.setConfigOptions(antialias=False, useOpenGL=False)
mark("pyqtgraph setConfigOptions")

# Phase 4: Create QApplication
app = QApplication(sys.argv)
mark("QApplication created")

# Phase 5: Create a minimal PlotWidget (graph)
print("\n--- Creating first PlotWidget (this is where freeze happens) ---")
widget = pg.PlotWidget()
mark("PlotWidget created")

widget.plot([1, 2, 3, 4, 5], [1, 4, 9, 16, 25])
mark("PlotWidget.plot() called")

widget.show()
mark("PlotWidget.show() called")

# Process events to force render
app.processEvents()
mark("First processEvents (render)")

app.processEvents()
mark("Second processEvents")

# Phase 6: Test COM/WMI (new Phase 9 code)
print("\n--- Testing COM/WMI ---")
try:
    import pythoncom
    mark("pythoncom import")

    pythoncom.CoInitialize()
    mark("CoInitialize()")

    import win32com.client
    mark("win32com.client import")

    locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
    mark("WMI SWbemLocator created")

    svc = locator.ConnectServer(".", "root\\cimv2")
    mark("WMI ConnectServer (root\\cimv2)")

    results = svc.ExecQuery("SELECT Name FROM Win32_OperatingSystem")
    for r in results:
        print(f"    OS: {r.Name}")
    mark("WMI query completed")
except Exception as e:
    mark(f"COM/WMI error: {e}")

# Phase 7: Test win32service
print("\n--- Testing win32service ---")
try:
    import win32service
    mark("win32service import")

    scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ENUMERATE_SERVICE)
    mark("OpenSCManager")

    services = win32service.EnumServicesStatusEx(scm, win32service.SERVICE_WIN32)
    mark(f"EnumServicesStatusEx ({len(services)} services)")

    win32service.CloseServiceHandle(scm)
except Exception as e:
    mark(f"win32service error: {e}")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
total = time.perf_counter() - times["__start"]
print(f"Total time: {total:.2f}s")
print()

# Identify slow steps (>1s)
prev_time = times["__start"]
sorted_times = sorted(times.items(), key=lambda x: x[1])
print("Slow steps (>1s):")
found_slow = False
for i in range(1, len(sorted_times)):
    label = sorted_times[i][0]
    delta = sorted_times[i][1] - sorted_times[i - 1][1]
    if delta > 1.0:
        print(f"  {delta:7.2f}s  {label}")
        found_slow = True
if not found_slow:
    print("  (none)")

print()
print("GPU/OpenGL info:")
try:
    from PySide6.QtGui import QSurfaceFormat
    fmt = QSurfaceFormat.defaultFormat()
    print(f"  OpenGL profile: {fmt.profile()}")
    print(f"  Render type: {fmt.renderableType()}")
except Exception as e:
    print(f"  Could not get surface format: {e}")

widget.close()
app.quit()
