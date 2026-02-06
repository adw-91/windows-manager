"""Diagnostic script to identify performance bottlenecks.

Run on the slow machine:
    python diagnose.py

Tests both static creation and continuous graph updates to
reproduce the real app's behavior.
"""

import time
import os
import sys
import random

times = {}

def mark(label: str) -> None:
    times[label] = time.perf_counter()
    elapsed = times[label] - times.get("__start", times[label])
    print(f"  [{elapsed:7.2f}s] {label}")

times["__start"] = time.perf_counter()
mark("Script start")

# Phase 1: Imports
import numpy as np
mark("numpy import")

import psutil
mark("psutil import")

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget,
    QScrollArea, QFrame, QLabel, QProgressBar, QStackedWidget,
)
from PySide6.QtCore import Qt, QTimer
mark("PySide6 import")

import pyqtgraph as pg
pg.setConfigOptions(antialias=False, useOpenGL=False)
mark("pyqtgraph import + config")

# Phase 2: Create app
app = QApplication(sys.argv)
mark("QApplication created")

# ===================================================================
# TEST 1: Static PlotWidget (baseline)
# ===================================================================
print("\n--- TEST 1: Single static PlotWidget ---")
w1 = pg.PlotWidget()
w1.plot([1, 2, 3, 4, 5], [1, 4, 9, 16, 25])
w1.show()
app.processEvents()
mark("Static PlotWidget created + rendered")
w1.close()

# ===================================================================
# TEST 2: Simulates real app - 4 PlotWidgets with continuous updates
#          inside a nested layout (like ExpandableMetricTile in ScrollArea)
# ===================================================================
print("\n--- TEST 2: 4 graphs with 500ms continuous updates (10s test) ---")

class FakeMetricTile(QFrame):
    """Simulates ExpandableMetricTile with an embedded graph."""
    def __init__(self, title: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        layout.addWidget(QProgressBar())

        self.graph = pg.PlotWidget()
        self.graph.setMinimumHeight(150)
        self.graph.setMaximumHeight(150)
        self.graph.setXRange(0, 59, padding=0)
        self.graph.setYRange(0, 100, padding=0.05)
        self.graph.setMouseEnabled(x=False, y=False)
        self.graph.showGrid(x=True, y=True, alpha=0.2)

        # Multiple series like the real CPU tile
        self.curves = []
        self.buffers = []
        colors = ["#4fc3f7", "#81c784", "#ffb74d", "#e57373"]
        for i, color in enumerate(colors):
            curve = self.graph.plot(pen=pg.mkPen(color=color, width=2), clipToView=True)
            self.curves.append(curve)
            self.buffers.append(np.zeros(60))

        self.head = 0
        layout.addWidget(self.graph)

    def update_data(self):
        """Simulate a graph data update (like the real 500ms worker)."""
        for i, (curve, buf) in enumerate(zip(self.curves, self.buffers)):
            buf[self.head] = random.uniform(10 + i * 20, 30 + i * 20)
            # Reorder buffer for display (like RingBuffer.get_data)
            ordered = np.concatenate([buf[self.head + 1:], buf[:self.head + 1]])
            x = np.arange(60)
            curve.setData(x, ordered)
        self.head = (self.head + 1) % 60


# Build a window structure similar to the real app
window = QMainWindow()
window.resize(1000, 700)

central = QWidget()
window.setCentralWidget(central)
main_layout = QVBoxLayout(central)

# Stacked widget (like the real app)
stack = QStackedWidget()

# Scroll area containing tiles (like SystemOverviewTab)
scroll = QScrollArea()
scroll.setWidgetResizable(True)
scroll_content = QWidget()
scroll_layout = QVBoxLayout(scroll_content)

tiles = []
for name in ["CPU Usage", "Memory", "Disk Activity", "Network"]:
    tile = FakeMetricTile(name)
    tiles.append(tile)
    scroll_layout.addWidget(tile)

scroll_layout.addStretch()
scroll.setWidget(scroll_content)
stack.addWidget(scroll)
# Add empty pages like real app's other tabs
for _ in range(5):
    stack.addWidget(QWidget())

main_layout.addWidget(stack)

mark("Test window built (4 tiles, 4 series each)")

window.show()
app.processEvents()
mark("Test window shown + first render")

# Run continuous updates for 10 seconds, measuring each frame
update_count = 0
frame_times = []
slow_frames = 0
test_start = time.perf_counter()

print("  Running 10 seconds of continuous 500ms updates...")
print("  (Each update: 4 tiles x 4 series = 16 curve.setData calls)")

while time.perf_counter() - test_start < 10.0:
    frame_start = time.perf_counter()

    # Update all tiles (simulates the graph worker signal delivery)
    for tile in tiles:
        tile.update_data()

    # Process events (simulates the main thread doing its work)
    app.processEvents()

    frame_end = time.perf_counter()
    frame_ms = (frame_end - frame_start) * 1000
    frame_times.append(frame_ms)
    if frame_ms > 100:
        slow_frames += 1
    update_count += 1

    # Wait remainder of 500ms interval
    elapsed_ms = (frame_end - frame_start) * 1000
    sleep_ms = max(0, 500 - elapsed_ms)
    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000)

mark(f"Continuous update test complete ({update_count} frames)")

# ===================================================================
# TEST 3: Same but with only 1 tile visible (like real app behavior)
# ===================================================================
print("\n--- TEST 3: Only 1 tile updating (simulates expanded-only) ---")

frame_times_single = []
test_start = time.perf_counter()
while time.perf_counter() - test_start < 5.0:
    frame_start = time.perf_counter()
    tiles[0].update_data()  # Only update one tile
    app.processEvents()
    frame_ms = (time.perf_counter() - frame_start) * 1000
    frame_times_single.append(frame_ms)
    time.sleep(max(0, (500 - frame_ms) / 1000))

mark("Single-tile update test complete")

# ===================================================================
# RESULTS
# ===================================================================
print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)

total = time.perf_counter() - times["__start"]
print(f"Total time: {total:.1f}s\n")

if frame_times:
    avg = sum(frame_times) / len(frame_times)
    worst = max(frame_times)
    p95 = sorted(frame_times)[int(len(frame_times) * 0.95)]
    print("TEST 2 - All 4 tiles updating (16 setData calls per frame):")
    print(f"  Frames:     {len(frame_times)}")
    print(f"  Avg frame:  {avg:.1f}ms")
    print(f"  P95 frame:  {p95:.1f}ms")
    print(f"  Worst frame: {worst:.1f}ms")
    print(f"  Slow frames (>100ms): {slow_frames}")
    if worst > 500:
        print(f"  ** WARNING: Worst frame {worst:.0f}ms > 500ms - would cause visible hang **")
    if worst > 5000:
        print(f"  ** CRITICAL: Worst frame {worst:.0f}ms > 5s - would trigger 'Not Responding' **")

if frame_times_single:
    avg = sum(frame_times_single) / len(frame_times_single)
    worst = max(frame_times_single)
    p95 = sorted(frame_times_single)[int(len(frame_times_single) * 0.95)]
    print(f"\nTEST 3 - Single tile updating (4 setData calls per frame):")
    print(f"  Frames:     {len(frame_times_single)}")
    print(f"  Avg frame:  {avg:.1f}ms")
    print(f"  P95 frame:  {p95:.1f}ms")
    print(f"  Worst frame: {worst:.1f}ms")

print("\nGPU/OpenGL info:")
try:
    from PySide6.QtGui import QSurfaceFormat
    fmt = QSurfaceFormat.defaultFormat()
    print(f"  OpenGL profile: {fmt.profile()}")
    print(f"  Render type: {fmt.renderableType()}")
except Exception as e:
    print(f"  Error: {e}")

print(f"\nDisplay: {app.primaryScreen().size().width()}x{app.primaryScreen().size().height()}")
print(f"Device pixel ratio: {app.primaryScreen().devicePixelRatio()}")
print(f"Logical DPI: {app.primaryScreen().logicalDotsPerInch()}")

window.close()
app.quit()
