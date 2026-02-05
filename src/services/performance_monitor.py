"""
Performance monitoring service.

Provides real-time system performance metrics for CPU, memory, disk, and network.
Uses psutil for cross-platform compatibility with Windows optimizations.
"""

import threading
import time
from dataclasses import dataclass
from typing import Optional
import psutil


@dataclass
class CpuTimes:
    """CPU time percentages."""
    user: float
    system: float
    idle: float
    interrupt: float = 0.0
    dpc: float = 0.0  # Windows-specific


@dataclass
class DiskIO:
    """Disk I/O rates in bytes per second."""
    read_bytes_per_sec: float
    write_bytes_per_sec: float
    read_count_per_sec: float
    write_count_per_sec: float


@dataclass
class NetworkIO:
    """Network I/O rates in bytes per second."""
    bytes_sent_per_sec: float
    bytes_recv_per_sec: float
    packets_sent_per_sec: float
    packets_recv_per_sec: float


class PerformanceMonitor:
    """
    Collects real-time system performance metrics.

    Uses differential measurement for rate calculations to avoid
    blocking sleeps in the caller's thread.

    Usage:
        monitor = PerformanceMonitor()
        cpu = monitor.get_cpu_times()
        ctx_rate = monitor.get_context_switch_rate()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Store previous values for rate calculations
        self._last_cpu_stats: Optional[psutil._common.scpustats] = None
        self._last_cpu_stats_time: Optional[float] = None

        self._last_disk_io: Optional[psutil._common.sdiskio] = None
        self._last_disk_io_time: Optional[float] = None

        self._last_net_io: Optional[psutil._common.snetio] = None
        self._last_net_io_time: Optional[float] = None

        # Initialize baselines
        self._init_baselines()

    def _init_baselines(self) -> None:
        """Initialize baseline measurements for rate calculations."""
        try:
            self._last_cpu_stats = psutil.cpu_stats()
            self._last_cpu_stats_time = time.perf_counter()

            self._last_disk_io = psutil.disk_io_counters()
            self._last_disk_io_time = time.perf_counter()

            self._last_net_io = psutil.net_io_counters()
            self._last_net_io_time = time.perf_counter()
        except Exception:
            pass  # Will initialize on first call

    def get_cpu_times(self) -> CpuTimes:
        """
        Get CPU time percentages.

        Returns:
            CpuTimes with user, system, idle, and Windows-specific metrics.
        """
        times = psutil.cpu_times_percent(interval=None)

        return CpuTimes(
            user=times.user,
            system=times.system,
            idle=times.idle,
            interrupt=getattr(times, 'interrupt', 0.0),
            dpc=getattr(times, 'dpc', 0.0),
        )

    def get_cpu_percent(self) -> float:
        """Get overall CPU usage percentage."""
        return psutil.cpu_percent(interval=None)

    def get_cpu_percent_per_core(self) -> list[float]:
        """Get CPU usage percentage for each core."""
        return psutil.cpu_percent(interval=None, percpu=True)

    def get_cpu_rates(self) -> tuple[float, float]:
        """
        Get context switches/s and interrupts/s from a single snapshot.

        Returns:
            Tuple of (context_switches_per_sec, interrupts_per_sec).
        """
        try:
            current = psutil.cpu_stats()
            current_time = time.perf_counter()

            with self._lock:
                if self._last_cpu_stats is None or self._last_cpu_stats_time is None:
                    self._last_cpu_stats = current
                    self._last_cpu_stats_time = current_time
                    return 0.0, 0.0

                elapsed = current_time - self._last_cpu_stats_time
                if elapsed <= 0:
                    return 0.0, 0.0

                ctx_rate = (current.ctx_switches - self._last_cpu_stats.ctx_switches) / elapsed
                int_rate = (current.interrupts - self._last_cpu_stats.interrupts) / elapsed

                self._last_cpu_stats = current
                self._last_cpu_stats_time = current_time

            return max(0.0, ctx_rate), max(0.0, int_rate)
        except Exception:
            return 0.0, 0.0

    def get_context_switch_rate(self) -> float:
        """Get context switches per second. Prefer get_cpu_rates() for both values."""
        return self.get_cpu_rates()[0]

    def get_interrupt_rate(self) -> float:
        """Get interrupts per second. Prefer get_cpu_rates() for both values."""
        return self.get_cpu_rates()[1]

    def get_memory_percent(self) -> float:
        """Get memory usage percentage."""
        return psutil.virtual_memory().percent

    def get_memory_used_gb(self) -> float:
        """Get memory used in GB."""
        mem = psutil.virtual_memory()
        return mem.used / (1024 ** 3)

    def get_memory_available_gb(self) -> float:
        """Get memory available in GB."""
        mem = psutil.virtual_memory()
        return mem.available / (1024 ** 3)

    def get_disk_io(self) -> DiskIO:
        """
        Get disk I/O rates.

        Uses differential measurement - call periodically for accurate rates.

        Returns:
            DiskIO with read/write bytes and operations per second.
        """
        try:
            current = psutil.disk_io_counters()
            current_time = time.perf_counter()

            if current is None:
                return DiskIO(0.0, 0.0, 0.0, 0.0)

            with self._lock:
                if self._last_disk_io is None or self._last_disk_io_time is None:
                    self._last_disk_io = current
                    self._last_disk_io_time = current_time
                    return DiskIO(0.0, 0.0, 0.0, 0.0)

                elapsed = current_time - self._last_disk_io_time
                if elapsed <= 0:
                    return DiskIO(0.0, 0.0, 0.0, 0.0)

                result = DiskIO(
                    read_bytes_per_sec=(current.read_bytes - self._last_disk_io.read_bytes) / elapsed,
                    write_bytes_per_sec=(current.write_bytes - self._last_disk_io.write_bytes) / elapsed,
                    read_count_per_sec=(current.read_count - self._last_disk_io.read_count) / elapsed,
                    write_count_per_sec=(current.write_count - self._last_disk_io.write_count) / elapsed,
                )

                self._last_disk_io = current
                self._last_disk_io_time = current_time

            return result
        except Exception:
            return DiskIO(0.0, 0.0, 0.0, 0.0)

    def get_network_io(self) -> NetworkIO:
        """
        Get network I/O rates.

        Uses differential measurement - call periodically for accurate rates.

        Returns:
            NetworkIO with bytes and packets per second.
        """
        try:
            current = psutil.net_io_counters()
            current_time = time.perf_counter()

            with self._lock:
                if self._last_net_io is None or self._last_net_io_time is None:
                    self._last_net_io = current
                    self._last_net_io_time = current_time
                    return NetworkIO(0.0, 0.0, 0.0, 0.0)

                elapsed = current_time - self._last_net_io_time
                if elapsed <= 0:
                    return NetworkIO(0.0, 0.0, 0.0, 0.0)

                result = NetworkIO(
                    bytes_sent_per_sec=(current.bytes_sent - self._last_net_io.bytes_sent) / elapsed,
                    bytes_recv_per_sec=(current.bytes_recv - self._last_net_io.bytes_recv) / elapsed,
                    packets_sent_per_sec=(current.packets_sent - self._last_net_io.packets_sent) / elapsed,
                    packets_recv_per_sec=(current.packets_recv - self._last_net_io.packets_recv) / elapsed,
                )

                self._last_net_io = current
                self._last_net_io_time = current_time

            return result
        except Exception:
            return NetworkIO(0.0, 0.0, 0.0, 0.0)

    def get_disk_usage_percent(self, path: str = "C:\\") -> float:
        """Get disk usage percentage for a given path."""
        try:
            usage = psutil.disk_usage(path)
            return usage.percent
        except Exception:
            return 0.0


# Singleton instance for shared state (rate calculations need continuity)
_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get the shared PerformanceMonitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = PerformanceMonitor()
    return _monitor
