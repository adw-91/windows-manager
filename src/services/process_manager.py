"""Process Manager Service - Manages Windows processes"""

import psutil
from typing import Any, List, Dict, Optional
from threading import Lock


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
        """Get list of all running processes with accurate CPU readings."""
        processes = []
        current_pids = set()

        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'status']):
            try:
                pinfo = proc.info
                pid = pinfo['pid']
                current_pids.add(pid)

                # Get or cache the process object
                with self._lock:
                    if pid not in self._process_cache:
                        self._process_cache[pid] = proc
                        # First call to cpu_percent returns 0, so store 0 initially
                        try:
                            proc.cpu_percent()  # Initialize CPU tracking
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        self._cpu_cache[pid] = 0.0
                    else:
                        # Get updated CPU percent (non-blocking after first call)
                        try:
                            cpu = self._process_cache[pid].cpu_percent()
                            # cpu_percent() returns value as percentage of all CPUs
                            # e.g., on 8 cores, 100% means using 1 full core
                            # Normalize to 0-100 range (% of single core, capped at 100)
                            if cpu is not None:
                                # Normalize: divide by CPU count to get average per-core usage
                                # But cap display at 100% for sanity
                                normalized_cpu = min(cpu / self._cpu_count, 100.0)
                                self._cpu_cache[pid] = normalized_cpu
                            else:
                                self._cpu_cache[pid] = 0.0
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            self._cpu_cache[pid] = 0.0

                    cpu_percent = self._cpu_cache.get(pid, 0.0)

                    mem_mb = pinfo['memory_info'].rss / (1024**2) if pinfo['memory_info'] else 0

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


_process_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """Get the global ProcessManager instance (singleton pattern)."""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager
