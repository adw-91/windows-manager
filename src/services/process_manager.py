"""Process Manager Service - Manages Windows processes"""

import psutil
from typing import List, Dict, Optional


class ProcessManager:
    """Manage and monitor Windows processes"""

    def __init__(self):
        pass

    def get_all_processes(self) -> List[Dict[str, any]]:
        """Get list of all running processes"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']):
            try:
                pinfo = proc.info
                processes.append({
                    "pid": pinfo['pid'],
                    "name": pinfo['name'],
                    "cpu_percent": pinfo['cpu_percent'] or 0.0,
                    "memory_mb": pinfo['memory_info'].rss / (1024**2) if pinfo['memory_info'] else 0,
                    "status": pinfo['status'],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return processes

    def get_process_info(self, pid: int) -> Optional[Dict[str, any]]:
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
