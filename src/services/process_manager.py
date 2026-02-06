"""Process Manager Service - Manages Windows processes."""

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
