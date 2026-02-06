# Native Process Enumeration via NtQuerySystemInformation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace psutil's per-process-handle enumeration with a single `NtQuerySystemInformation(SystemProcessInformation)` kernel call that returns all process data (PID, name, threads, handles, memory, CPU times) in one buffer — completely bypassing EDR interception of `OpenProcess()` handles.

**Architecture:** New `src/utils/win32/process_info.py` module wraps `NtQuerySystemInformation` via ctypes, returning the same dict format that `ProcessManager` currently produces. `ProcessManager` switches from `psutil.process_iter()` to the native call for bulk enumeration, keeping psutil only for `kill_process()` (which genuinely needs a process handle). The overview tab's `_collect_details` also switches to the native data for thread/handle totals — eliminating the sampling approach entirely since the kernel returns exact counts for every process.

**Tech Stack:** Python 3.12+, ctypes (ntdll.dll), existing `src/utils/win32/` package pattern

---

## Problem Summary

| Approach | Mechanism | Enterprise Cost (413 procs) |
|----------|-----------|----------------------------|
| `psutil.process_iter()` | Opens handle per-process → EDR intercepts each | **10.3s** |
| `NtQuerySystemInformation` | Single kernel call, no per-process handles | **<50ms** |

psutil's `process_iter` internally enumerates PIDs, then opens individual process handles to read memory/name/status. EDR agents (CrowdStrike, Defender ATP) hook `OpenProcess()`, adding ~25ms per call. With 413 processes, this adds up to 10+ seconds.

`NtQuerySystemInformation(SystemProcessInformation)` returns a single buffer containing a linked list of `SYSTEM_PROCESS_INFORMATION` structs with **all** process data already populated by the kernel. No per-process handles are opened, so EDR has nothing to intercept.

### Data Available from NtQuerySystemInformation (per process)

| Field | Type | Maps To |
|-------|------|---------|
| `UniqueProcessId` | `c_void_p` (handle-sized int) | `pid` |
| `ImageName` | `UNICODE_STRING` | `name` |
| `NumberOfThreads` | `ULONG` | thread count (exact, no sampling) |
| `HandleCount` | `ULONG` | handle count (exact, no sampling) |
| `WorkingSetSize` | `c_size_t` | `memory_mb` (RSS equivalent) |
| `UserTime` + `KernelTime` | `c_longlong` (100ns units) | CPU usage (compute delta between snapshots) |
| `CreateTime` | `c_longlong` (100ns since 1601) | process start time |
| `SessionId` | `ULONG` | session ID |
| `InheritedFromUniqueProcessId` | `c_void_p` | parent PID |
| `PagefileUsage` | `c_size_t` | commit charge |

### What psutil is still needed for

- `psutil.cpu_percent()` / `psutil.cpu_times_percent()` — system-wide CPU (single syscall, fast)
- `psutil.virtual_memory()` / `psutil.disk_usage()` / `psutil.net_io_counters()` — system metrics
- `psutil.Process(pid).terminate()` — kill process (requires handle, but single call)
- `psutil.cpu_count()` / `psutil.cpu_freq()` — hardware info
- `psutil.sensors_battery()` — battery status
- `psutil.win_service_iter()` — service enumeration (in `system_tab.py`, not hot path)

### Key Files

- Create: `src/utils/win32/process_info.py` — NtQuerySystemInformation wrapper
- Create: `tests/test_win32_process_info.py` — tests for native process enumeration
- Modify: `src/services/process_manager.py` — switch from psutil to native enumeration
- Modify: `src/ui/system_overview_tab.py` — use exact thread/handle counts from native data
- Modify: `src/ui/system_tab.py` — replace `psutil.pids()` with native process count

---

## Task 1: Create `src/utils/win32/process_info.py` — ctypes structs and raw query

**Files:**
- Create: `src/utils/win32/process_info.py`
- Create: `tests/test_win32_process_info.py`

**Why:** This is the core module. Defines the `SYSTEM_PROCESS_INFORMATION` struct in ctypes and wraps the `NtQuerySystemInformation` call. Returns a list of dicts with the same shape the rest of the app expects.

**Step 1: Write the failing test**

```python
# tests/test_win32_process_info.py
"""Tests for native process enumeration via NtQuerySystemInformation."""
import os
import unittest
from src.utils.win32.process_info import enumerate_processes


class TestEnumerateProcesses(unittest.TestCase):
    def test_returns_list(self):
        """Should return a non-empty list of process dicts."""
        procs = enumerate_processes()
        self.assertIsInstance(procs, list)
        self.assertGreater(len(procs), 10)

    def test_process_dict_keys(self):
        """Each process dict must have the expected keys."""
        procs = enumerate_processes()
        required_keys = {
            "pid", "name", "thread_count", "handle_count",
            "working_set_bytes", "user_time_ns", "kernel_time_ns",
            "create_time_ns", "parent_pid", "session_id",
            "status",
        }
        for proc in procs[:5]:
            for key in required_keys:
                self.assertIn(key, proc, f"Missing key '{key}' in process {proc.get('pid')}")

    def test_contains_current_process(self):
        """The current Python process should appear in results."""
        my_pid = os.getpid()
        procs = enumerate_processes()
        pids = [p["pid"] for p in procs]
        self.assertIn(my_pid, pids)

    def test_current_process_has_name(self):
        """The current process should have 'python' in its name."""
        my_pid = os.getpid()
        procs = enumerate_processes()
        my_proc = next(p for p in procs if p["pid"] == my_pid)
        self.assertIn("python", my_proc["name"].lower())

    def test_system_idle_process(self):
        """PID 0 should be 'System Idle Process'."""
        procs = enumerate_processes()
        idle = next((p for p in procs if p["pid"] == 0), None)
        self.assertIsNotNone(idle, "PID 0 not found")
        self.assertEqual(idle["name"], "System Idle Process")

    def test_thread_and_handle_counts_are_positive(self):
        """Non-idle processes should have positive thread and handle counts."""
        procs = enumerate_processes()
        # PID 4 (System) always has threads and handles
        system_proc = next((p for p in procs if p["pid"] == 4), None)
        if system_proc:
            self.assertGreater(system_proc["thread_count"], 0)
            self.assertGreater(system_proc["handle_count"], 0)

    def test_working_set_bytes_reasonable(self):
        """Current process should have non-trivial working set."""
        my_pid = os.getpid()
        procs = enumerate_processes()
        my_proc = next(p for p in procs if p["pid"] == my_pid)
        # Python process should use at least 1 MB
        self.assertGreater(my_proc["working_set_bytes"], 1_000_000)

    def test_total_thread_count(self):
        """Total thread count across all processes should be substantial."""
        procs = enumerate_processes()
        total_threads = sum(p["thread_count"] for p in procs)
        # Any Windows system has at least 500 threads
        self.assertGreater(total_threads, 100)

    def test_total_handle_count(self):
        """Total handle count across all processes should be substantial."""
        procs = enumerate_processes()
        total_handles = sum(p["handle_count"] for p in procs)
        # Any Windows system has thousands of handles
        self.assertGreater(total_handles, 1000)

    def test_status_values(self):
        """Status should be 'running' for all processes (kernel perspective)."""
        procs = enumerate_processes()
        for proc in procs:
            self.assertEqual(proc["status"], "running")


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_win32_process_info.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.utils.win32.process_info'`

**Step 3: Write the implementation**

```python
# src/utils/win32/process_info.py
"""Native process enumeration via NtQuerySystemInformation.

Uses a single kernel call to get all process data (PID, name, threads,
handles, memory, CPU times) without opening per-process handles.
This bypasses EDR interception that makes psutil.process_iter() slow
on enterprise machines.
"""
import ctypes
from ctypes import wintypes
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

ntdll = ctypes.windll.ntdll

# Constants
SystemProcessInformation = 5
STATUS_SUCCESS = 0
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", ctypes.c_ushort),
        ("MaximumLength", ctypes.c_ushort),
        ("Buffer", ctypes.c_wchar_p),
    ]


class SYSTEM_PROCESS_INFORMATION(ctypes.Structure):
    """Kernel process information struct returned by NtQuerySystemInformation.

    64-bit layout. Fields documented at:
    https://ntdoc.m417z.com/system_process_information
    """
    _fields_ = [
        ("NextEntryOffset", wintypes.ULONG),
        ("NumberOfThreads", wintypes.ULONG),
        ("WorkingSetPrivateSize", ctypes.c_longlong),
        ("HardFaultCount", wintypes.ULONG),
        ("NumberOfThreadsHighWatermark", wintypes.ULONG),
        ("CycleTime", ctypes.c_ulonglong),
        ("CreateTime", ctypes.c_longlong),
        ("UserTime", ctypes.c_longlong),
        ("KernelTime", ctypes.c_longlong),
        ("ImageName", UNICODE_STRING),
        ("BasePriority", ctypes.c_long),
        ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p),
        ("HandleCount", wintypes.ULONG),
        ("SessionId", wintypes.ULONG),
        ("UniqueProcessKey", ctypes.c_size_t),
        ("PeakVirtualSize", ctypes.c_size_t),
        ("VirtualSize", ctypes.c_size_t),
        ("PageFaultCount", wintypes.ULONG),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivatePageCount", ctypes.c_size_t),
        ("ReadOperationCount", ctypes.c_longlong),
        ("WriteOperationCount", ctypes.c_longlong),
        ("OtherOperationCount", ctypes.c_longlong),
        ("ReadTransferCount", ctypes.c_longlong),
        ("WriteTransferCount", ctypes.c_longlong),
        ("OtherTransferCount", ctypes.c_longlong),
    ]


# Set up function signature once at module level
ntdll.NtQuerySystemInformation.argtypes = [
    wintypes.ULONG,
    ctypes.c_void_p,
    wintypes.ULONG,
    ctypes.POINTER(wintypes.ULONG),
]
ntdll.NtQuerySystemInformation.restype = ctypes.c_ulong


def _query_system_process_information() -> ctypes.Array:
    """Call NtQuerySystemInformation and return the raw byte buffer.

    Handles the two-pass pattern: first call to get required size,
    second call with allocated buffer. Retries if buffer is too small
    (processes can spawn between calls).
    """
    return_length = wintypes.ULONG(0)

    # Pass 1: get required buffer size
    ntdll.NtQuerySystemInformation(
        SystemProcessInformation, None, 0, ctypes.byref(return_length),
    )

    # Allocate with 64KB margin for processes spawning between calls
    buf_size = return_length.value + 0x10000
    buf = (ctypes.c_byte * buf_size)()

    # Pass 2: query the data
    status = ntdll.NtQuerySystemInformation(
        SystemProcessInformation,
        ctypes.byref(buf),
        buf_size,
        ctypes.byref(return_length),
    )

    if status & 0xFFFFFFFF == STATUS_INFO_LENGTH_MISMATCH:
        # Retry with double the returned size
        buf_size = return_length.value * 2
        buf = (ctypes.c_byte * buf_size)()
        status = ntdll.NtQuerySystemInformation(
            SystemProcessInformation,
            ctypes.byref(buf),
            buf_size,
            ctypes.byref(return_length),
        )

    if status != STATUS_SUCCESS:
        raise OSError(
            f"NtQuerySystemInformation failed with NTSTATUS 0x{status:08X}"
        )

    return buf


def enumerate_processes() -> List[Dict[str, Any]]:
    """Enumerate all processes using a single NtQuerySystemInformation call.

    Returns a list of dicts with:
        pid: int - process ID
        name: str - process image name
        parent_pid: int - parent process ID
        session_id: int - session ID
        thread_count: int - exact number of threads
        handle_count: int - exact number of open handles
        working_set_bytes: int - physical memory (RSS equivalent)
        user_time_ns: int - user-mode CPU time in nanoseconds
        kernel_time_ns: int - kernel-mode CPU time in nanoseconds
        create_time_ns: int - creation time as Windows FILETIME (100ns since 1601)
        status: str - always "running" (kernel only tracks live processes)
    """
    buf = _query_system_process_information()
    processes = []
    offset = 0

    while True:
        spi = ctypes.cast(
            ctypes.byref(buf, offset),
            ctypes.POINTER(SYSTEM_PROCESS_INFORMATION),
        ).contents

        pid = spi.UniqueProcessId or 0
        parent_pid = spi.InheritedFromUniqueProcessId or 0
        name = spi.ImageName.Buffer if spi.ImageName.Buffer else "System Idle Process"

        processes.append({
            "pid": pid,
            "name": name,
            "parent_pid": parent_pid,
            "session_id": spi.SessionId,
            "thread_count": spi.NumberOfThreads,
            "handle_count": spi.HandleCount,
            "working_set_bytes": spi.WorkingSetSize,
            "user_time_ns": spi.UserTime * 100,       # 100ns units → nanoseconds
            "kernel_time_ns": spi.KernelTime * 100,    # 100ns units → nanoseconds
            "create_time_ns": spi.CreateTime,           # Windows FILETIME (100ns since 1601)
            "status": "running",
        })

        if spi.NextEntryOffset == 0:
            break
        offset += spi.NextEntryOffset

    return processes
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_win32_process_info.py -v`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add src/utils/win32/process_info.py tests/test_win32_process_info.py
git commit -m "feat(win32): add native process enumeration via NtQuerySystemInformation

Single kernel call returns all process data (PID, name, threads, handles,
memory, CPU times) without opening per-process handles. Bypasses EDR
interception that makes psutil.process_iter() take 10s+ on enterprise."
```

---

## Task 2: Add re-export in `src/utils/win32/__init__.py`

**Files:**
- Modify: `src/utils/win32/__init__.py`

**Step 1: Add import**

Add to the imports in `src/utils/win32/__init__.py`:

```python
from src.utils.win32.process_info import enumerate_processes
```

Also update the module docstring `Submodules:` list to include:
```
    process_info - Native process enumeration via NtQuerySystemInformation
```

**Step 2: Verify**

Run: `python -c "from src.utils.win32 import enumerate_processes; print(f'{len(enumerate_processes())} processes')"`
Expected: Prints a process count.

**Step 3: Commit**

```bash
git add src/utils/win32/__init__.py
git commit -m "feat(win32): add enumerate_processes re-export"
```

---

## Task 3: Rewrite `ProcessManager` to use native enumeration + CPU delta tracking

**Files:**
- Modify: `src/services/process_manager.py`
- Modify: `tests/test_process_manager.py` (add new tests)

**Why:** The biggest change. `get_all_processes()` switches from `psutil.process_iter()` to `enumerate_processes()`. CPU percentage is computed from deltas of `user_time_ns + kernel_time_ns` between snapshots, matching how Task Manager does it. The `get_fast_update()` method now also uses native enumeration (it's fast enough — no per-process handles), eliminating the need for cached psutil `Process` objects entirely.

**Step 1: Write the failing tests**

Add to `tests/test_process_manager.py`:

```python
class TestProcessManagerNative(unittest.TestCase):
    def test_get_all_processes_returns_list(self):
        pm = ProcessManager()
        procs = pm.get_all_processes()
        self.assertIsInstance(procs, list)
        self.assertGreater(len(procs), 10)

    def test_process_dict_has_required_keys(self):
        pm = ProcessManager()
        procs = pm.get_all_processes()
        for proc in procs[:5]:
            for key in ("pid", "name", "cpu_percent", "memory_mb", "status"):
                self.assertIn(key, proc)

    def test_cpu_percent_is_zero_on_first_call(self):
        """First call has no delta, so CPU should be 0.0 for all."""
        pm = ProcessManager()
        procs = pm.get_all_processes()
        for proc in procs:
            self.assertEqual(proc["cpu_percent"], 0.0)

    def test_fast_update_returns_data_after_init(self):
        pm = ProcessManager()
        pm.get_all_processes()  # Initialize
        fast = pm.get_fast_update()
        self.assertGreater(len(fast), 10)

    def test_fast_update_returns_empty_before_init(self):
        pm = ProcessManager()
        fast = pm.get_fast_update()
        self.assertEqual(fast, [])

    def test_get_process_count(self):
        pm = ProcessManager()
        count = pm.get_process_count()
        self.assertGreater(count, 10)

    def test_get_thread_handle_totals(self):
        pm = ProcessManager()
        pm.get_all_processes()  # Populate cache
        threads, handles = pm.get_thread_handle_totals()
        self.assertGreater(threads, 100)
        self.assertGreater(handles, 1000)
```

**Step 2: Run to verify new tests fail**

Run: `python -m pytest tests/test_process_manager.py -v`
Expected: New tests fail (old tests may still pass since we haven't changed anything yet).

**Step 3: Rewrite `process_manager.py`**

Replace the entire `ProcessManager` class. Key changes:
- Remove `psutil.process_iter()` usage entirely
- Remove `self._process_cache` (no more psutil `Process` objects)
- Add `self._prev_times: Dict[int, int]` for CPU time deltas
- Add `self._prev_snapshot_time: float` for wall-clock delta
- `get_all_processes()` calls `enumerate_processes()` and computes CPU %
- `get_fast_update()` also calls `enumerate_processes()` (it's fast now)
- Add `get_thread_handle_totals()` returning exact sums from native data
- `get_process_count()` uses `len(enumerate_processes())`
- Keep `kill_process()` using `psutil.Process(pid).terminate()` (needs handle)
- Keep `get_process_info()` using `psutil.Process(pid)` (single-process detail view, rare)

```python
"""Process Manager Service - Manages Windows processes"""

import time
import psutil
from typing import Any, List, Dict, Optional
from threading import Lock

from src.utils.win32.process_info import enumerate_processes


class ProcessManager:
    """Manage and monitor Windows processes with native kernel enumeration.

    Uses NtQuerySystemInformation for bulk process data (single kernel call,
    no per-process handles). CPU percentage is computed from user+kernel time
    deltas between snapshots, matching Task Manager's approach.
    """

    def __init__(self):
        self._prev_times: Dict[int, int] = {}  # pid -> (user_time_ns + kernel_time_ns)
        self._prev_wall_time: float = 0.0
        self._lock = Lock()
        self._initialized = False
        self._cpu_count = psutil.cpu_count() or 1
        # Cache latest snapshot for get_thread_handle_totals()
        self._latest_snapshot: List[Dict[str, Any]] = []

    def get_all_processes(self) -> List[Dict[str, Any]]:
        """Full refresh: enumerate all processes via NtQuerySystemInformation.

        Single kernel call — no per-process handles, no EDR interception.
        Computes CPU% from time deltas between consecutive calls.
        """
        raw = enumerate_processes()
        now = time.monotonic()

        with self._lock:
            wall_delta = now - self._prev_wall_time if self._prev_wall_time else 0.0
            # Convert wall delta to nanoseconds
            wall_delta_ns = wall_delta * 1_000_000_000

            processes = []
            current_times: Dict[int, int] = {}

            for proc in raw:
                pid = proc["pid"]
                total_time = proc["user_time_ns"] + proc["kernel_time_ns"]
                current_times[pid] = total_time

                # Compute CPU %
                cpu_percent = 0.0
                if self._initialized and wall_delta_ns > 0 and pid in self._prev_times:
                    time_delta = total_time - self._prev_times[pid]
                    if time_delta > 0:
                        # time_delta / wall_delta gives fraction of one CPU core
                        # Divide by cpu_count to get percentage of total system
                        cpu_percent = (time_delta / wall_delta_ns) * 100.0 / self._cpu_count
                        cpu_percent = min(cpu_percent, 100.0)

                processes.append({
                    "pid": pid,
                    "name": proc["name"],
                    "cpu_percent": cpu_percent,
                    "memory_mb": proc["working_set_bytes"] / (1024 ** 2),
                    "status": proc["status"],
                })

            self._prev_times = current_times
            self._prev_wall_time = now
            self._latest_snapshot = raw
            self._initialized = True

        return processes

    def get_fast_update(self) -> List[Dict[str, Any]]:
        """Fast refresh — identical to get_all_processes since native enum is fast.

        NtQuerySystemInformation completes in <50ms regardless of process count
        or EDR presence. No need for a separate "fast" path anymore.
        """
        if not self._initialized:
            return []
        return self.get_all_processes()

    def get_thread_handle_totals(self) -> tuple[int, int]:
        """Return exact total thread and handle counts from latest snapshot.

        No sampling needed — NtQuerySystemInformation returns exact counts
        for every process in a single call.
        """
        with self._lock:
            total_threads = sum(p["thread_count"] for p in self._latest_snapshot)
            total_handles = sum(p["handle_count"] for p in self._latest_snapshot)
        return total_threads, total_handles

    def get_process_count(self) -> int:
        """Get total number of running processes."""
        with self._lock:
            if self._latest_snapshot:
                return len(self._latest_snapshot)
        return len(enumerate_processes())

    def get_process_info(self, pid: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific process.

        Uses psutil for single-process detail (rare, on-demand operation).
        """
        try:
            proc = psutil.Process(pid)
            return {
                "pid": proc.pid,
                "name": proc.name(),
                "status": proc.status(),
                "cpu_percent": proc.cpu_percent(interval=0.1),
                "memory_mb": proc.memory_info().rss / (1024 ** 2),
                "num_threads": proc.num_threads(),
                "create_time": proc.create_time(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def kill_process(self, pid: int) -> bool:
        """Terminate a process by PID."""
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False


_process_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """Get the global ProcessManager instance (singleton pattern)."""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_process_manager.py -v`
Expected: All tests PASS (both old and new).

**Step 5: Commit**

```bash
git add src/services/process_manager.py tests/test_process_manager.py
git commit -m "feat: rewrite ProcessManager to use NtQuerySystemInformation

Replaces psutil.process_iter() with native kernel call for bulk process
enumeration. CPU% computed from user+kernel time deltas between snapshots.
get_fast_update() now also uses native enum (<50ms, no EDR impact).
Adds get_thread_handle_totals() with exact counts (no sampling)."
```

---

## Task 4: Update `_collect_details` to use exact thread/handle counts

**Files:**
- Modify: `src/ui/system_overview_tab.py:536-564`

**Why:** The `_collect_details` worker currently samples 20 processes with `psutil.Process(pid).num_threads()` + `.num_handles()` and extrapolates. This is slow on enterprise machines and inaccurate. The native data now gives us exact totals via `get_thread_handle_totals()`.

**Step 1: Replace the sampling block**

In `src/ui/system_overview_tab.py`, the `_collect_details` method currently has (lines 543-564):

```python
        pids = psutil.pids()
        process_count = len(pids)

        # Sample 20 processes for thread/handle estimates.
        sample_size = min(20, len(pids))
        thread_count = 0
        handle_count = 0
        sampled = 0
        for pid in pids[:sample_size]:
            ...
```

Replace the PID sampling block with:

```python
        process_count = self._process_manager.get_process_count()
        thread_count, handle_count = self._process_manager.get_thread_handle_totals()
```

This eliminates:
- `psutil.pids()` call
- `psutil.Process(pid)` construction x20
- `.num_threads()` x20
- `.num_handles()` x20
- The sampling/extrapolation logic

The `~` prefix on thread/handle display can be removed since counts are now exact. Change in the return dict:

```python
                "Threads": f"{thread_count:,}",      # was f"~{thread_count:,}"
                "Handles": f"{handle_count:,}",       # was f"~{handle_count:,}" with "if handle_count else N/A"
```

Also remove the `import psutil` if it's no longer used in this method. Check: `psutil.cpu_count()`, `psutil.cpu_freq()`, `psutil.virtual_memory()`, `psutil.swap_memory()`, `psutil.net_if_addrs()`, `psutil.net_if_stats()` are still used in `_collect_details`, so keep the import.

**Step 2: Verify**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

**Step 3: Commit**

```bash
git add src/ui/system_overview_tab.py
git commit -m "perf: use exact thread/handle totals from native enumeration

Replaces 20-process sampling + extrapolation with exact counts from
NtQuerySystemInformation via ProcessManager.get_thread_handle_totals().
Eliminates 20x psutil.Process() handle opens from details worker."
```

---

## Task 5: Replace `psutil.pids()` in `system_tab.py`

**Files:**
- Modify: `src/ui/system_tab.py:470`

**Why:** `system_tab.py` calls `psutil.pids()` for the process count display in the Software Environment section. Use `ProcessManager.get_process_count()` instead for consistency.

**Step 1: Change the code**

At line 470, replace:

```python
            info["Processes"] = str(len(psutil.pids()))
```

With:

```python
            from src.services.process_manager import get_process_manager
            info["Processes"] = str(get_process_manager().get_process_count())
```

Note: `psutil.pids()` is still fast and not a bottleneck, but this ensures consistency and avoids an unnecessary psutil call when we already have the data.

Check if `psutil` import can be removed from `system_tab.py` — look for other psutil uses. There are `psutil.win_service_iter()` and `psutil.win_service_get()` calls, so keep the import.

**Step 2: Verify**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

**Step 3: Commit**

```bash
git add src/ui/system_tab.py
git commit -m "refactor: use ProcessManager for process count in system_tab

Replaces psutil.pids() with ProcessManager.get_process_count() for
consistency with native enumeration."
```

---

## Task 6: Performance benchmark and final verification

**Files:**
- No code changes (verification only)

**Step 1: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS (including the new `test_win32_process_info.py` and updated `test_process_manager.py`).

**Step 2: Run a quick timing comparison**

Run:
```python
python -c "
import time, psutil
from src.utils.win32.process_info import enumerate_processes

# Native
start = time.perf_counter()
native = enumerate_processes()
native_time = time.perf_counter() - start

# psutil
start = time.perf_counter()
ps = list(psutil.process_iter(['pid', 'name', 'memory_info', 'status']))
psutil_time = time.perf_counter() - start

print(f'Native: {len(native)} procs in {native_time*1000:.1f}ms')
print(f'psutil: {len(ps)} procs in {psutil_time*1000:.1f}ms')
print(f'Speedup: {psutil_time/native_time:.1f}x')
"
```

Expected: Native should be significantly faster (expect 10-200x on enterprise machines, 2-10x on home machines).

**Step 3: Commit and push**

```bash
git push
```

---

## Summary of Changes

| File | Before | After |
|------|--------|-------|
| `src/utils/win32/process_info.py` | N/A | New: ctypes wrapper for NtQuerySystemInformation |
| `src/utils/win32/__init__.py` | No process_info export | Adds `enumerate_processes` re-export |
| `src/services/process_manager.py` | `psutil.process_iter()` + per-process `cpu_percent()` | `enumerate_processes()` + CPU time deltas |
| `src/ui/system_overview_tab.py` | Sample 20 PIDs for thread/handle estimates | Exact totals from `get_thread_handle_totals()` |
| `src/ui/system_tab.py` | `psutil.pids()` for count | `ProcessManager.get_process_count()` |

**psutil retained for:**
- `cpu_percent()` / `cpu_times_percent()` (system-wide, single syscall)
- `virtual_memory()` / `disk_usage()` / `net_io_counters()` (system metrics)
- `Process(pid).terminate()` (kill process, requires handle)
- `Process(pid).*` in `get_process_info()` (single-process detail, rare)
- `win_service_iter()` / `win_service_get()` (service info, not hot path)
- `cpu_count()` / `cpu_freq()` / `sensors_battery()` (hardware info)
