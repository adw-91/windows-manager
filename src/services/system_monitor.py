"""System Monitor Service - Tracks system resources and performance metrics"""

import psutil
from typing import Dict, List


class SystemMonitor:
    """Monitor system resources like CPU, memory, disk usage"""

    def __init__(self):
        self.update_interval = 1000  # milliseconds

    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        return psutil.cpu_percent(interval=0.1)

    def get_memory_info(self) -> Dict[str, float]:
        """Get memory usage information"""
        mem = psutil.virtual_memory()
        return {
            "total": mem.total / (1024**3),  # GB
            "available": mem.available / (1024**3),  # GB
            "used": mem.used / (1024**3),  # GB
            "percent": mem.percent,
        }

    def get_disk_info(self) -> List[Dict[str, any]]:
        """Get disk usage information for all drives"""
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total": usage.total / (1024**3),  # GB
                    "used": usage.used / (1024**3),  # GB
                    "free": usage.free / (1024**3),  # GB
                    "percent": usage.percent,
                })
            except PermissionError:
                continue
        return disks

    def get_system_uptime(self) -> float:
        """Get system uptime in seconds"""
        import time
        boot_time = psutil.boot_time()
        return time.time() - boot_time

    def has_battery(self) -> bool:
        """Check if system has a battery"""
        battery = psutil.sensors_battery()
        return battery is not None

    def get_battery_info(self) -> Dict[str, any]:
        """Get battery status information"""
        battery = psutil.sensors_battery()
        if battery is None:
            return None

        return {
            "percent": battery.percent,
            "power_plugged": battery.power_plugged,
            "time_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else None
        }
