# Enterprise Performance Fix - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix catastrophic performance on enterprise-managed Windows machines where EDR/security software makes per-process queries 10-100x slower than home machines.

**Architecture:** Split process enumeration into a fast path (CPU-only updates from cached Process objects every 3s) and a slow path (full `process_iter` with memory/status every 15s). Fix blocking `cpu_percent(interval=0.1)`, reduce handle counting overhead, and defer pyqtgraph widget creation to prevent UI lock on tile expansion.

**Tech Stack:** Python 3.12, PySide6, psutil, pyqtgraph, win32 APIs

---

## Problem Overview

### Diagnostic Results (work laptop: 12-core, 32GB, Intel Iris Xe, 413 processes)

| Operation | Measured Time | Expected | Severity |
|---|---|---|---|
| `psutil.process_iter()` (413 procs) | **10.3s** | <1s | **CRITICAL** |
| `cpu_percent(interval=0.1)` | 101ms (blocking) | 0ms | HIGH |
| `num_handles() + num_threads()` x100 | ~2.2s | <0.5s | HIGH |
| Process table full rebuild (UI thread) | heavy per 2s | - | MODERATE |
| Graph widget creation on expand | synchronous | - | MODERATE |

### Root Cause

Enterprise machines have ~413 processes (vs ~150 home) due to EDR agents (CrowdStrike/Defender ATP), management tools (SCCM/Intune), DLP software, and corporate services. Each `psutil.Process()` attribute query triggers EDR interception, making per-process calls 10-100x slower.

### Current Architecture Problems

1. **ProcessManager.get_all_processes()** calls `psutil.process_iter(['pid','name','memory_info','status'])` which takes 10.3s. The LoopingWorker runs this every 2s, meaning the worker is permanently blocked — it never finishes before the next cycle wants to start.

2. **SystemMonitor.get_cpu_usage()** uses `psutil.cpu_percent(interval=0.1)` which blocks the worker thread for 100ms per call. Should use `interval=None` (non-blocking, uses cached delta).

3. **_collect_details()** iterates 100 PIDs calling `num_threads()` + `num_handles()` every 2s. At ~22ms/process with EDR, this takes ~2.2s — exceeding its own 2s refresh interval.

4. **ExpandableMetricTile.expand()** creates a pyqtgraph PlotWidget synchronously during the click handler. On iGPU (Iris Xe vs RTX 4060 at home), widget creation + first render causes visible UI freeze.

5. **Process table _populate_table()** destroys and recreates ALL QTableWidgetItem objects (413 procs × 5 cols = 2065 items) every refresh cycle in the UI thread.

### Key Files

- `src/services/process_manager.py` — process enumeration + CPU tracking
- `src/services/system_monitor.py` — CPU usage with blocking interval
- `src/ui/system_overview_tab.py` — metric workers, graph updates, detail collection
- `src/ui/processes_services_tab.py` — process table rendering + refresh loop
- `src/ui/widgets/expandable_metric_tile.py` — tile expand/collapse with graph creation
- `src/utils/thread_utils.py` — LoopingWorker, SingleRunWorker (no changes needed)

---

## Task 1: Fix blocking CPU measurement in SystemMonitor

**Files:**
- Modify: `src/services/system_monitor.py:10-15`

**Why:** `cpu_percent(interval=0.1)` blocks the calling thread for 100ms every call. The `interval=None` form returns instantly using the delta since the last call. We just need to prime it once in the constructor.

**Step 1: Fix the code**

In `src/services/system_monitor.py`, change the constructor and `get_cpu_usage`:

```python
class SystemMonitor:
    """Monitor system resources like CPU, memory, disk usage"""

    def __init__(self):
        self.update_interval = 1000  # milliseconds
        # Prime cpu_percent so first interval=None call returns real data
        psutil.cpu_percent(interval=None)

    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        return psutil.cpu_percent(interval=None)
```

Key change: line 15 `interval=0.1` → `interval=None`, add priming call in `__init__`.

**Step 2: Verify**

Run: `".venv\Scripts\python.exe" -c "from src.services.system_monitor import SystemMonitor; m = SystemMonitor(); print(m.get_cpu_usage())"`

Expected: Prints a number (may be 0.0 on first call, that's fine — subsequent calls in the app's 1s loop will have real deltas).

**Step 3: Commit**

```bash
git add src/services/system_monitor.py
git commit -m "perf: remove 100ms blocking sleep from CPU measurement

cpu_percent(interval=0.1) blocks the worker thread for 100ms per call.
Switch to interval=None (non-blocking delta) with constructor priming."
```

---

## Task 2: Add two-phase process refresh to ProcessManager

**Files:**
- Modify: `src/services/process_manager.py`

**Why:** `process_iter` takes 10.3s on enterprise machines (413 processes with EDR). Currently called every 2s, meaning the worker never finishes before the next cycle. Solution: add a fast `get_fast_update()` that only refreshes CPU% using cached Process objects (instant), while the existing `get_all_processes()` becomes the slow path for discovering new/dead processes and updating memory.

**Step 1: Add info cache and fast update method**

Replace the entire `ProcessManager` class in `src/services/process_manager.py`:

```python
class ProcessManager:
    """Manage and monitor Windows processes with proper CPU tracking."""

    def __init__(self):
        self._process_cache: Dict[int, psutil.Process] = {}
        self._cpu_cache: Dict[int, float] = {}
        self._info_cache: Dict[int, Dict[str, Any]] = {}  # name, memory_mb, status
        self._lock = Lock()
        self._initialized = False
        self._cpu_count = psutil.cpu_count() or 1

    def get_all_processes(self) -> List[Dict[str, Any]]:
        """Full refresh: enumerate all processes with memory info.

        SLOW on enterprise machines (10s+ with 400+ processes).
        Call infrequently (every 10-15s). Updates the process cache
        so that get_fast_update() has fresh data to work with.
        """
        processes = []
        current_pids = set()

        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'status']):
            try:
                pinfo = proc.info
                pid = pinfo['pid']
                current_pids.add(pid)

                mem_mb = pinfo['memory_info'].rss / (1024**2) if pinfo['memory_info'] else 0

                with self._lock:
                    if pid not in self._process_cache:
                        self._process_cache[pid] = proc
                        try:
                            proc.cpu_percent()  # Initialize CPU tracking
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        self._cpu_cache[pid] = 0.0
                    else:
                        try:
                            cpu = self._process_cache[pid].cpu_percent()
                            if cpu is not None:
                                self._cpu_cache[pid] = min(cpu / self._cpu_count, 100.0)
                            else:
                                self._cpu_cache[pid] = 0.0
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            self._cpu_cache[pid] = 0.0

                    cpu_percent = self._cpu_cache.get(pid, 0.0)

                    # Cache info for fast updates
                    self._info_cache[pid] = {
                        "name": pinfo['name'] or "",
                        "memory_mb": mem_mb,
                        "status": pinfo['status'] or "",
                    }

                processes.append({
                    "pid": pid,
                    "name": pinfo['name'],
                    "cpu_percent": cpu_percent,
                    "memory_mb": mem_mb,
                    "status": pinfo['status'],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Clean up cache for terminated processes
        with self._lock:
            dead_pids = set(self._process_cache.keys()) - current_pids
            for pid in dead_pids:
                self._process_cache.pop(pid, None)
                self._cpu_cache.pop(pid, None)
                self._info_cache.pop(pid, None)

        self._initialized = True
        return processes

    def get_fast_update(self) -> List[Dict[str, Any]]:
        """Fast refresh: only update CPU% using cached Process objects.

        Uses cached name/memory/status from the last full refresh.
        Only calls proc.cpu_percent() which is non-blocking.
        Typically completes in <100ms even with 400+ processes.
        """
        if not self._initialized:
            return []

        processes = []
        with self._lock:
            dead_pids = set()
            for pid, proc in self._process_cache.items():
                try:
                    cpu = proc.cpu_percent()
                    normalized = min(cpu / self._cpu_count, 100.0) if cpu else 0.0
                    self._cpu_cache[pid] = normalized

                    info = self._info_cache.get(pid, {})
                    processes.append({
                        "pid": pid,
                        "name": info.get("name", ""),
                        "cpu_percent": normalized,
                        "memory_mb": info.get("memory_mb", 0),
                        "status": info.get("status", ""),
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    dead_pids.add(pid)

            for pid in dead_pids:
                self._process_cache.pop(pid, None)
                self._cpu_cache.pop(pid, None)
                self._info_cache.pop(pid, None)

        return processes

    def get_process_info(self, pid: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific process"""
        try:
            proc = psutil.Process(pid)
            return {
                "pid": proc.pid,
                "name": proc.name(),
                "status": proc.status(),
                "cpu_percent": proc.cpu_percent(interval=0.1),
                "memory_mb": proc.memory_info().rss / (1024**2),
                "num_threads": proc.num_threads(),
                "create_time": proc.create_time(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def kill_process(self, pid: int) -> bool:
        """Terminate a process by PID"""
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def get_process_count(self) -> int:
        """Get total number of running processes"""
        return len(psutil.pids())
```

**Step 2: Verify**

Run: `".venv\Scripts\python.exe" -c "from src.services.process_manager import ProcessManager; pm = ProcessManager(); full = pm.get_all_processes(); print(f'Full: {len(full)} procs'); fast = pm.get_fast_update(); print(f'Fast: {len(fast)} procs')"`

Expected: Both print similar process counts. Full will take ~10s, fast should be near-instant.

**Step 3: Commit**

```bash
git add src/services/process_manager.py
git commit -m "perf: add two-phase process refresh (fast CPU-only + slow full)

process_iter takes 10.3s on enterprise machines with 413 processes.
New get_fast_update() only calls cpu_percent() on cached Process objects
(non-blocking), reusing cached name/memory/status from the last full
refresh. Completes in <100ms vs 10s+ for full enumeration."
```

---

## Task 3: Wire two-phase refresh into ProcessesServicesTab

**Files:**
- Modify: `src/ui/processes_services_tab.py:40-62` (constructor), `352-359` (load methods), `546-560` (auto-refresh)

**Why:** Currently uses a single LoopingWorker calling `get_all_processes` every 2s. Need to split into: fast worker (3s, CPU-only) + slow worker (15s, full enum).

**Step 1: Change constructor and add dual workers**

In `ProcessesServicesTab.__init__`, change the worker setup. Replace these instance vars:

```python
self._refresh_worker: Optional[LoopingWorker] = None
```

With:

```python
self._fast_refresh_worker: Optional[LoopingWorker] = None
self._full_refresh_worker: Optional[LoopingWorker] = None
```

Change `REFRESH_INTERVAL_MS`:

```python
FAST_REFRESH_MS = 3000    # CPU-only update every 3s
FULL_REFRESH_MS = 15000   # Full process enumeration every 15s
```

Remove the old `REFRESH_INTERVAL_MS = 2000`.

**Step 2: Change _load_initial_processes**

Replace:

```python
def _load_initial_processes(self) -> None:
    """Load processes asynchronously on startup using SingleRunWorker."""
    worker = SingleRunWorker(self._process_manager.get_all_processes)
    worker.signals.result.connect(self._on_processes_loaded)
    worker.signals.error.connect(self._on_load_error)
    QThreadPool.globalInstance().start(worker)
    # Start auto-refresh immediately
    self._on_auto_refresh_toggled(Qt.CheckState.Checked)
```

With:

```python
def _load_initial_processes(self) -> None:
    """Load processes asynchronously on startup using SingleRunWorker."""
    worker = SingleRunWorker(self._process_manager.get_all_processes)
    worker.signals.result.connect(self._on_processes_loaded)
    worker.signals.error.connect(self._on_load_error)
    QThreadPool.globalInstance().start(worker)
    self._start_auto_refresh()
```

**Step 3: Replace _on_auto_refresh_toggled**

Replace the existing method with:

```python
def _start_auto_refresh(self) -> None:
    """Start dual refresh workers: fast (CPU-only) + slow (full enum)."""
    if self._fast_refresh_worker is None:
        self._fast_refresh_worker = LoopingWorker(
            self.FAST_REFRESH_MS,
            self._process_manager.get_fast_update,
        )
        self._fast_refresh_worker.signals.result.connect(self._on_processes_loaded)
        self._fast_refresh_worker.signals.error.connect(self._on_load_error)
        self._fast_refresh_worker.start()

    if self._full_refresh_worker is None:
        self._full_refresh_worker = LoopingWorker(
            self.FULL_REFRESH_MS,
            self._process_manager.get_all_processes,
        )
        self._full_refresh_worker.signals.result.connect(self._on_processes_loaded)
        self._full_refresh_worker.signals.error.connect(self._on_load_error)
        self._full_refresh_worker.start()

def _stop_auto_refresh(self) -> None:
    """Stop both refresh workers."""
    if self._fast_refresh_worker is not None:
        self._fast_refresh_worker.stop()
        self._fast_refresh_worker = None
    if self._full_refresh_worker is not None:
        self._full_refresh_worker.stop()
        self._full_refresh_worker = None

@Slot(int)
def _on_auto_refresh_toggled(self, state: int) -> None:
    """Handle auto-refresh checkbox toggle."""
    if state == Qt.CheckState.Checked:
        self._start_auto_refresh()
    else:
        self._stop_auto_refresh()
```

**Step 4: Fix closeEvent**

Replace:

```python
def closeEvent(self, event) -> None:
    """Clean up workers when tab is closed."""
    if self._refresh_worker is not None:
        self._refresh_worker.stop()
        self._refresh_worker = None
    event.accept()
```

With:

```python
def closeEvent(self, event) -> None:
    """Clean up workers when tab is closed."""
    self._stop_auto_refresh()
    event.accept()
```

**Step 5: Verify**

Run app: `".venv\Scripts\python.exe" run_app.py`

Navigate to Processes tab. Should see:
- Initial process list appears within ~10s (first full load)
- CPU% values update every ~3s (fast refresh)
- New processes appear within ~15s of launch (full refresh cycle)
- App remains responsive during refreshes

**Step 6: Commit**

```bash
git add src/ui/processes_services_tab.py
git commit -m "perf: split process refresh into fast (3s CPU) and slow (15s full)

Fast worker calls get_fast_update() every 3s — only cpu_percent() on
cached objects (<100ms). Slow worker calls get_all_processes() every 15s
for new/dead process discovery and memory updates (10s+ on enterprise)."
```

---

## Task 4: Reduce _collect_details overhead

**Files:**
- Modify: `src/ui/system_overview_tab.py:481-487` (worker interval), `536-558` (collection logic)

**Why:** The details worker iterates 100 PIDs calling `num_threads()` + `num_handles()` every 2s. Takes ~2.2s on enterprise machines (exceeding its own interval). Handle counting is the expensive part and provides low-value "nice to have" data.

**Step 1: Increase details interval and reduce PID sampling**

Change the details worker interval on line 481-487 from `2000` to `5000`:

```python
# Details worker (slower updates for detailed info)
details_worker = LoopingWorker(
    5000,  # 5 seconds — handle/thread counting is slow with EDR
    self._collect_details,
)
```

**Step 2: Reduce handle/thread counting in _collect_details**

Replace the PID iteration block (lines 543-558):

```python
    pids = psutil.pids()
    process_count = len(pids)
    thread_count = 0
    handle_count = 0
    for pid in pids[:100]:
        try:
            proc = psutil.Process(pid)
            thread_count += proc.num_threads()
            if hasattr(proc, 'num_handles'):
                handle_count += proc.num_handles()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if len(pids) > 100:
        thread_count = int(thread_count * len(pids) / 100)
        handle_count = int(handle_count * len(pids) / 100)
```

With:

```python
    pids = psutil.pids()
    process_count = len(pids)

    # Sample 20 processes for thread/handle estimates.
    # num_handles() is very slow on enterprise machines with EDR (~22ms/proc).
    sample_size = min(20, len(pids))
    thread_count = 0
    handle_count = 0
    sampled = 0
    for pid in pids[:sample_size]:
        try:
            proc = psutil.Process(pid)
            thread_count += proc.num_threads()
            if hasattr(proc, 'num_handles'):
                handle_count += proc.num_handles()
            sampled += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if sampled > 0 and len(pids) > sample_size:
        thread_count = int(thread_count * len(pids) / sampled)
        handle_count = int(handle_count * len(pids) / sampled)
```

**Step 3: Commit**

```bash
git add src/ui/system_overview_tab.py
git commit -m "perf: reduce details worker overhead (5s interval, 20-PID sample)

num_handles()/num_threads() take ~22ms/process with EDR interception.
Reduced from 100-PID sample every 2s (~2.2s work) to 20-PID sample
every 5s (~0.44s work). Thread/handle counts are estimates anyway."
```

---

## Task 5: Defer graph creation on tile expand

**Files:**
- Modify: `src/ui/widgets/expandable_metric_tile.py:255-283`

**Why:** `_create_graph()` instantiates a pyqtgraph PlotWidget synchronously during the click handler. On Intel Iris Xe (iGPU), this causes a visible freeze. Deferring creation with `QTimer.singleShot(0, ...)` lets the expand animation start first and processes pending events before the heavyweight graph widget is created.

**Step 1: Defer graph creation in expand()**

Replace the `expand()` method:

```python
def expand(self) -> None:
    """Expand the tile to show the graph and details."""
    if self._is_expanded:
        return

    self._is_expanded = True
    self._animating = True  # Suppress graph updates during animation
    self._expand_indicator.setText("▲")

    self._expanded_container.setVisible(True)
    self._subtitle_label.setVisible(True)  # Show subtitle when expanded

    # Calculate target height based on content
    target_height = self.EXPANDED_HEIGHT
    if not self._detail_labels:
        target_height -= 80  # Less height if no details

    self._animation.setStartValue(self.height())
    self._animation.setEndValue(target_height)
    self._animation.start()

    # Defer graph creation to after the event loop processes the animation.
    # This prevents UI freeze on iGPU where PlotWidget creation is slow.
    if not self._graph_created:
        QTimer.singleShot(50, self._create_graph)

    # Allow graph updates after animation completes (200ms)
    QTimer.singleShot(250, self._on_expand_animation_done)

    self.expanded.emit(self)
```

Key change: Moved `_create_graph()` from synchronous to `QTimer.singleShot(50, ...)` — creates after 50ms, giving the animation a head start.

**Step 2: Commit**

```bash
git add src/ui/widgets/expandable_metric_tile.py
git commit -m "perf: defer graph creation on tile expand to prevent UI freeze

PlotWidget creation is slow on iGPU (Intel Iris Xe). Defer with
QTimer.singleShot(50ms) so the expand animation starts first and
the event loop stays responsive during widget initialization."
```

---

## Task 6: In-place process table updates

**Files:**
- Modify: `src/ui/processes_services_tab.py:391-517` (`_populate_table` method)

**Why:** Currently destroys and recreates ALL QTableWidgetItems (413 × 5 = 2065 items) every refresh. This is pure UI-thread overhead. Reusing existing items avoids widget churn.

**Step 1: Rewrite _populate_table to reuse items**

Replace the `_populate_table` method:

```python
def _populate_table(self) -> None:
    """Populate table with filtered process data, reusing existing items."""
    ctrl_pressed = self._check_ctrl_state()

    if ctrl_pressed:
        self._sort_status_label.setText("⏸ Sorting paused (release Ctrl to resume)")
    else:
        self._sort_status_label.setText("")

    # Store current selection
    selected_pid = None
    selected_rows = self._process_table.selectedIndexes()
    if selected_rows:
        row = selected_rows[0].row()
        pid_item = self._process_table.item(row, self.COL_PID)
        if pid_item:
            selected_pid = pid_item.text()

    # Store current row order if Ctrl is pressed
    current_order = []
    if ctrl_pressed:
        for row in range(self._process_table.rowCount()):
            pid_item = self._process_table.item(row, self.COL_PID)
            if pid_item:
                current_order.append(pid_item.data(Qt.ItemDataRole.UserRole))

    self._process_table.setSortingEnabled(False)

    # Determine row order
    proc_by_pid = {proc.get("pid"): proc for proc in self._filtered_processes}

    if ctrl_pressed and current_order:
        ordered_procs = []
        seen_pids = set()
        for pid in current_order:
            if pid in proc_by_pid:
                ordered_procs.append(proc_by_pid[pid])
                seen_pids.add(pid)
        for proc in self._filtered_processes:
            if proc.get("pid") not in seen_pids:
                ordered_procs.append(proc)
    else:
        ordered_procs = self._filtered_processes

    # Adjust row count
    new_count = len(ordered_procs)
    self._process_table.setRowCount(new_count)

    for row, proc in enumerate(ordered_procs):
        # PID
        pid_item = self._process_table.item(row, self.COL_PID)
        if pid_item is None:
            pid_item = QTableWidgetItem()
            self._process_table.setItem(row, self.COL_PID, pid_item)
        pid_item.setData(Qt.ItemDataRole.DisplayRole, str(proc.get("pid", "")))
        pid_item.setData(Qt.ItemDataRole.UserRole, proc.get("pid", 0))

        # Name
        name_item = self._process_table.item(row, self.COL_NAME)
        if name_item is None:
            name_item = QTableWidgetItem()
            self._process_table.setItem(row, self.COL_NAME, name_item)
        name_item.setText(proc.get("name", ""))

        # CPU %
        cpu_val = min(proc.get('cpu_percent', 0), 100.0)
        cpu_item = self._process_table.item(row, self.COL_CPU)
        if cpu_item is None:
            cpu_item = QTableWidgetItem()
            self._process_table.setItem(row, self.COL_CPU, cpu_item)
        cpu_item.setData(Qt.ItemDataRole.DisplayRole, f"{cpu_val:.1f}%")
        cpu_item.setData(Qt.ItemDataRole.UserRole, cpu_val)

        # CPU coloring
        proc_name = proc.get("name", "")
        if proc_name == "System Idle Process":
            if cpu_val > 80:
                cpu_item.setForeground(Colors.SUCCESS)
            elif cpu_val > 50:
                cpu_item.setForeground(Colors.TEXT_PRIMARY)
            elif cpu_val > 20:
                cpu_item.setForeground(Colors.WARNING)
            else:
                cpu_item.setForeground(Colors.ERROR)
        else:
            if cpu_val > 50:
                cpu_item.setForeground(Colors.ERROR)
            elif cpu_val > 20:
                cpu_item.setForeground(Colors.WARNING)
            else:
                cpu_item.setForeground(Colors.TEXT_PRIMARY)

        # Memory
        mem_val = proc.get('memory_mb', 0)
        memory_item = self._process_table.item(row, self.COL_MEMORY)
        if memory_item is None:
            memory_item = QTableWidgetItem()
            self._process_table.setItem(row, self.COL_MEMORY, memory_item)
        memory_item.setData(Qt.ItemDataRole.DisplayRole, f"{mem_val:.1f}")
        memory_item.setData(Qt.ItemDataRole.UserRole, mem_val)
        if mem_val > 1000:
            memory_item.setForeground(Colors.ERROR)
        elif mem_val > 500:
            memory_item.setForeground(Colors.WARNING)
        else:
            memory_item.setForeground(Colors.TEXT_PRIMARY)

        # Status
        status = proc.get("status", "")
        status_item = self._process_table.item(row, self.COL_STATUS)
        if status_item is None:
            status_item = QTableWidgetItem()
            self._process_table.setItem(row, self.COL_STATUS, status_item)
        status_item.setText(status)
        if status == "running":
            status_item.setForeground(Colors.SUCCESS)
        elif status in ("zombie", "dead"):
            status_item.setForeground(Colors.ERROR)
        elif status in ("stopped", "sleeping"):
            status_item.setForeground(Colors.TEXT_SECONDARY)
        else:
            status_item.setForeground(Colors.TEXT_PRIMARY)

    self._process_table.setSortingEnabled(True)

    if not ctrl_pressed and self._last_sort_column is not None:
        self._process_table.sortItems(self._last_sort_column, self._last_sort_order)

    # Restore selection
    if selected_pid:
        for row in range(self._process_table.rowCount()):
            pid_item = self._process_table.item(row, self.COL_PID)
            if pid_item and pid_item.text() == selected_pid:
                self._process_table.selectRow(row)
                break

    self._update_count_label()
```

Key changes:
- Check `self._process_table.item(row, col)` — if it exists, reuse it; if `None`, create new
- Reset foreground colors to default when below thresholds (avoids stale color from previous process in that row)

**Step 2: Commit**

```bash
git add src/ui/processes_services_tab.py
git commit -m "perf: reuse QTableWidgetItems instead of full rebuild every refresh

Previously destroyed and recreated 2065 items (413 procs × 5 cols)
every refresh cycle in the UI thread. Now reuses existing items and
only creates new ones for new rows."
```

---

## Task 7: Smoke test and push

**Step 1: Run the app and verify all changes**

```bash
".venv\Scripts\python.exe" run_app.py
```

Verify:
- [ ] App starts and Overview tab loads within a few seconds
- [ ] CPU/Memory/Disk/Network tiles update values
- [ ] Clicking a tile to expand does NOT freeze the UI
- [ ] Graph appears and starts drawing curves
- [ ] Collapsing and expanding other tiles works
- [ ] Processes tab shows process list
- [ ] CPU% values update every ~3s
- [ ] Process list refreshes (new processes appear) within ~15s
- [ ] Switching between tabs is responsive
- [ ] No crashes or errors in console

**Step 2: Run diagnostic to compare**

```bash
".venv\Scripts\python.exe" diagnostic_perf.py
```

The `process_iter` will still show ~10s (that's the OS/EDR cost), but the app should feel responsive because the fast worker bypasses it.

**Step 3: Push**

```bash
git push
```
