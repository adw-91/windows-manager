# Phase 8 Resize Performance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate resize lag on static tabs (System, Enterprise) by profiling and fixing FlowLayout recalculation overhead.

**Architecture:** FlowLayout._do_layout() runs on every resize pixel with no caching, triggering full geometry recalculation across 6-10 cards with 8-15 KV pairs each. Fix by adding width-based layout caching and resize batching on card-heavy tabs.

**Tech Stack:** PySide6 (QLayout, QWidget), Python time.perf_counter for profiling

---

### Task 1: Add resize profiling instrumentation

**Files:**
- Modify: `src/ui/widgets/flow_layout.py:87-90`
- Modify: `src/ui/system_tab.py:182` (SystemTab class)
- Modify: `src/ui/enterprise_tab.py:171` (EnterpriseTab class)

**Step 1: Add timing to FlowLayout.setGeometry**

Add a module-level counter and timing to `flow_layout.py` to measure how often and how long `_do_layout` runs during resize.

```python
# At top of file, after imports
import time

_layout_call_count = 0
_layout_total_ms = 0.0

def get_layout_stats() -> tuple[int, float]:
    """Return (call_count, total_ms) and reset counters."""
    global _layout_call_count, _layout_total_ms
    count, total = _layout_call_count, _layout_total_ms
    _layout_call_count = 0
    _layout_total_ms = 0.0
    return count, total
```

In `setGeometry`:
```python
def setGeometry(self, rect: QRect) -> None:
    """Set the geometry of the layout and arrange items."""
    global _layout_call_count, _layout_total_ms
    super().setGeometry(rect)
    t0 = time.perf_counter()
    self._do_layout(rect, test_only=False)
    _layout_total_ms += (time.perf_counter() - t0) * 1000
    _layout_call_count += 1
```

**Step 2: Add resize logging to SystemTab**

Add a `resizeEvent` override to `SystemTab` that logs FlowLayout stats every 500ms during resize:

```python
# In SystemTab.__init__, after init_ui():
from PySide6.QtCore import QTimer
self._resize_log_timer = QTimer(self)
self._resize_log_timer.setInterval(500)
self._resize_log_timer.setSingleShot(True)
self._resize_log_timer.timeout.connect(self._log_resize_stats)

# New methods:
def resizeEvent(self, event) -> None:
    super().resizeEvent(event)
    self._resize_log_timer.start()

def _log_resize_stats(self) -> None:
    from src.ui.widgets.flow_layout import get_layout_stats
    count, total = get_layout_stats()
    if count > 0:
        print(f"[SystemTab resize] FlowLayout: {count} calls, {total:.1f}ms total, {total/count:.2f}ms avg")
```

Add identical instrumentation to `EnterpriseTab`.

**Step 3: Run the app and resize on each tab**

Run: `python run_app.py`

Test procedure:
1. Navigate to System tab, grab window edge, drag left-right for 3 seconds
2. Navigate to Enterprise tab, repeat
3. Navigate to Overview tab, repeat
4. Check console output for FlowLayout call counts and timings

Expected output format:
```
[SystemTab resize] FlowLayout: 47 calls, 12.3ms total, 0.26ms avg
```

**Step 4: Commit profiling instrumentation**

```bash
git add src/ui/widgets/flow_layout.py src/ui/system_tab.py src/ui/enterprise_tab.py
git commit -m "perf: add FlowLayout resize profiling instrumentation"
```

---

### Task 2: Add FlowLayout width caching

The core optimisation. FlowLayout only reflows when width changes — height changes never affect the horizontal wrapping calculation. Cache the last layout result and skip recalculation when width is unchanged.

**Files:**
- Modify: `src/ui/widgets/flow_layout.py:16-33` (constructor)
- Modify: `src/ui/widgets/flow_layout.py:87-90` (setGeometry)
- Modify: `src/ui/widgets/flow_layout.py:39-41` (addItem — invalidate cache)
- Modify: `src/ui/widgets/flow_layout.py:69-73` (takeAt — invalidate cache)

**Step 1: Add cache fields to constructor**

```python
def __init__(self, parent=None, margin: int = 0, h_spacing: int = 12, v_spacing: int = 8):
    super().__init__(parent)
    self._item_list: list[QWidgetItem] = []
    self._h_spacing = h_spacing
    self._v_spacing = v_spacing
    self._cached_width: int = -1  # Last width we laid out for
    self._cached_height: int = -1  # Height result from that layout

    if margin >= 0:
        self.setContentsMargins(margin, margin, margin, margin)
```

**Step 2: Cache-aware setGeometry**

```python
def setGeometry(self, rect: QRect) -> None:
    """Set the geometry of the layout and arrange items."""
    super().setGeometry(rect)
    # Skip full recalculation if width hasn't changed
    if rect.width() == self._cached_width:
        return
    self._do_layout(rect, test_only=False)
    self._cached_width = rect.width()
```

**Step 3: Invalidate cache on item changes**

In `addItem`:
```python
def addItem(self, item: QWidgetItem) -> None:
    """Add an item to the layout."""
    self._item_list.append(item)
    self._cached_width = -1  # Invalidate cache
```

In `takeAt`:
```python
def takeAt(self, index: int) -> QWidgetItem | None:
    """Remove and return the item at the given index."""
    if 0 <= index < len(self._item_list):
        self._cached_width = -1  # Invalidate cache
        return self._item_list.pop(index)
    return None
```

**Step 4: Run the app and compare profiling output**

Run: `python run_app.py`

Repeat the same resize test as Task 1 Step 3. Expected: FlowLayout call count should drop dramatically (only fires when width actually changes, not on every pixel of vertical resize).

**Step 5: Commit**

```bash
git add src/ui/widgets/flow_layout.py
git commit -m "perf: add width-based layout caching to FlowLayout"
```

---

### Task 3: Batch layout updates during resize on card-heavy tabs

For tabs with many cards (SystemTab: 6 cards, EnterpriseTab: 4 cards), suppress intermediate repaints during resize drag using `setUpdatesEnabled(False)` with a debounce timer.

**Files:**
- Modify: `src/ui/system_tab.py:182` (SystemTab class)
- Modify: `src/ui/enterprise_tab.py:171` (EnterpriseTab class)

**Step 1: Add resize debouncing to SystemTab**

In `SystemTab.__init__` (after `init_ui()`), replace the profiling timer with a resize debounce timer:

```python
self._resize_timer = QTimer(self)
self._resize_timer.setInterval(100)
self._resize_timer.setSingleShot(True)
self._resize_timer.timeout.connect(self._on_resize_done)
```

Override `resizeEvent`:
```python
def resizeEvent(self, event) -> None:
    """Suppress repaints during resize drag, batch at end."""
    if not self._resize_timer.isActive():
        self._card_container.setUpdatesEnabled(False)
    self._resize_timer.start()
    super().resizeEvent(event)

def _on_resize_done(self) -> None:
    """Re-enable updates after resize drag ends."""
    self._card_container.setUpdatesEnabled(True)
    self._card_container.update()
```

**Step 2: Add identical resize debouncing to EnterpriseTab**

Same pattern — add `_resize_timer`, override `resizeEvent`, add `_on_resize_done`. Target `self._card_container`.

In `EnterpriseTab.__init__` (after `init_ui()`):
```python
self._resize_timer = QTimer(self)
self._resize_timer.setInterval(100)
self._resize_timer.setSingleShot(True)
self._resize_timer.timeout.connect(self._on_resize_done)
```

```python
def resizeEvent(self, event) -> None:
    """Suppress repaints during resize drag, batch at end."""
    if not self._resize_timer.isActive():
        self._card_container.setUpdatesEnabled(False)
    self._resize_timer.start()
    super().resizeEvent(event)

def _on_resize_done(self) -> None:
    """Re-enable updates after resize drag ends."""
    self._card_container.setUpdatesEnabled(True)
    self._card_container.update()
```

**Step 3: Test resize smoothness**

Run: `python run_app.py`

Test: Navigate to System tab, drag window edge aggressively. Compare feel to before — should feel noticeably smoother with less stutter. Enterprise tab should also feel improved.

**Step 4: Commit**

```bash
git add src/ui/system_tab.py src/ui/enterprise_tab.py
git commit -m "perf: batch layout updates during resize on card-heavy tabs"
```

---

### Task 4: Remove profiling instrumentation

**Files:**
- Modify: `src/ui/widgets/flow_layout.py` (remove timing globals and imports)
- Modify: `src/ui/system_tab.py` (remove profiling log method if still present)
- Modify: `src/ui/enterprise_tab.py` (remove profiling log method if still present)

**Step 1: Clean up flow_layout.py**

Remove the `import time`, `_layout_call_count`, `_layout_total_ms`, and `get_layout_stats()` function. Remove the timing code from `setGeometry` (keep only the cache logic from Task 2).

Final `setGeometry` should be:
```python
def setGeometry(self, rect: QRect) -> None:
    """Set the geometry of the layout and arrange items."""
    super().setGeometry(rect)
    if rect.width() == self._cached_width:
        return
    self._do_layout(rect, test_only=False)
    self._cached_width = rect.width()
```

**Step 2: Clean up tab files**

Remove any remaining `_log_resize_stats` methods and `get_layout_stats` imports from SystemTab and EnterpriseTab. Keep only the resize debounce timer and `_on_resize_done`.

**Step 3: Verify app launches cleanly**

Run: `python -c "from src.ui.main_window import MainWindow; print('OK')"`
Run: `python run_app.py` — verify no console output from profiling

**Step 4: Commit**

```bash
git add src/ui/widgets/flow_layout.py src/ui/system_tab.py src/ui/enterprise_tab.py
git commit -m "chore: remove resize profiling instrumentation"
```

---

### Task 5: Update Phase 8 status to completed

**Files:**
- Modify: `docs/PROJECT_OVERVIEW.md:18` (Phase 8 status)

**Step 1: Update status**

Change Phase 8 row from `**In Progress**` to `**Completed**`.

**Step 2: Commit**

```bash
git add docs/PROJECT_OVERVIEW.md
git commit -m "docs: mark Phase 8 performance bottlenecks as completed"
```

---

## Notes for Implementer

- **FlowLayout is used in:** InfoCard (SystemTab, 6 cards), EnterpriseCard (EnterpriseTab, 4 cards), and KeyValuePair widgets within those cards.
- **The width cache is the highest-impact change.** During a purely vertical resize (or when the scroll area absorbs width changes), FlowLayout will skip all recalculation entirely.
- **setUpdatesEnabled batching** prevents Qt from repainting intermediate states during drag. The 100ms timer fires once after the user stops dragging.
- **heightForWidth()** is called frequently by Qt's layout system. The width cache does NOT affect it (it uses test_only=True). If profiling shows heightForWidth is also hot, consider caching its result keyed by width argument.
- **QTimer imports:** Both SystemTab and EnterpriseTab already import from `PySide6.QtCore` — just add `QTimer` to the existing import line.
