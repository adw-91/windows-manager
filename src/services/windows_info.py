"""Windows System Information Service - Fetches detailed system information via native APIs."""

import datetime
import platform
import socket
import winreg
from typing import Any, Dict, Optional

import psutil
import win32net

from src.utils.win32.registry import read_string
from src.utils.win32.system_info import get_system_locale as _get_locale, get_total_physical_memory
from src.utils.win32.wmi import WmiConnection


class WindowsInfo:
    """Retrieve Windows system information via registry, ctypes, and WMI COM."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def get_system_name(self) -> str:
        """Get computer hostname."""
        return socket.gethostname()

    def get_processor(self) -> str:
        """Get processor information from registry."""
        name = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            "ProcessorNameString",
        )
        if name:
            return name.strip()

        # Fallback to platform info
        cpu = platform.processor()
        if cpu:
            return cpu
        return f"{psutil.cpu_count(logical=False)} Core Processor"

    def get_memory_info(self) -> Dict[str, Any]:
        """Get detailed memory information with per-stick capacity."""
        total_bytes = get_total_physical_memory()
        total_gb = total_bytes / (1024**3)

        # Try to get per-stick info via WMI COM
        stick_capacities = self._get_memory_stick_capacities()

        if stick_capacities:
            stick_count = len(stick_capacities)
            per_stick_gb = stick_capacities[0] / (1024**3)
            formatted = f"{total_gb:.1f} GB ({per_stick_gb:.1f} GB x{stick_count})"
        else:
            stick_count = 1
            formatted = f"{total_gb:.1f} GB"

        return {
            "total_gb": total_gb,
            "stick_count": stick_count,
            "formatted": formatted,
        }

    def _get_memory_stick_capacities(self) -> list:
        """Get capacity of each physical memory stick in bytes via WMI COM."""
        try:
            conn = WmiConnection()
            results = conn.query("SELECT Capacity FROM Win32_PhysicalMemory")
            capacities = []
            for row in results:
                cap = row.get("Capacity")
                if cap is not None:
                    capacities.append(int(cap))
            return capacities
        except Exception:
            return []

    def get_total_disk_space(self) -> str:
        """Get total disk space across all drives."""
        total_bytes = 0
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                total_bytes += usage.total
            except PermissionError:
                continue

        total_gb = total_bytes / (1024**3)
        if total_gb >= 1024:
            return f"{total_gb / 1024:.2f} TB"
        return f"{total_gb:.1f} GB"

    def get_network_info(self) -> str:
        """Get primary network adapter information."""
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            for interface, addr_list in addrs.items():
                if interface in stats and stats[interface].isup:
                    for addr in addr_list:
                        if addr.family == socket.AF_INET:
                            if not addr.address.startswith('127.'):
                                return f"{interface} ({addr.address})"
        except Exception:
            pass
        return "Not connected"

    def get_os_version(self) -> str:
        """Get Windows version."""
        return f"{platform.system()} {platform.release()}"

    def get_os_build(self) -> str:
        """Get Windows build number."""
        return platform.version()

    def get_system_architecture(self) -> str:
        """Get system architecture."""
        return platform.machine()

    def get_domain_workgroup(self) -> str:
        """Get domain or workgroup name via NetGetJoinInformation."""
        try:
            name, status = win32net.NetGetJoinInformation(None)
            # status: 0=Unknown, 1=Unjoined, 2=Workgroup, 3=Domain
            return name if name else "WORKGROUP"
        except Exception:
            return "Unknown"

    def get_manufacturer(self) -> str:
        """Get computer manufacturer from registry."""
        mfr = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\SystemInformation",
            "SystemManufacturer",
        )
        return mfr if mfr else "Unknown"

    def get_model(self) -> str:
        """Get computer model from registry."""
        model = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\SystemInformation",
            "SystemProductName",
        )
        return model if model else "Unknown"

    def get_bios_version(self) -> str:
        """Get BIOS version from registry."""
        bios = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\BIOS",
            "BIOSVersion",
        )
        return bios if bios else "Unknown"

    def get_system_locale(self) -> str:
        """Get system locale via kernel32 GetSystemDefaultLocaleName."""
        return _get_locale()

    def get_timezone(self) -> str:
        """Get system timezone using Python datetime."""
        try:
            return datetime.datetime.now().astimezone().tzname() or "Unknown"
        except Exception:
            import time
            return time.tzname[0]

    def get_all_system_info(self) -> Dict[str, str]:
        """Get all system information as a dictionary."""
        return {
            "System Name": self.get_system_name(),
            "Manufacturer": self.get_manufacturer(),
            "Model": self.get_model(),
            "Processor": self.get_processor(),
            "Total Memory": self.get_memory_info()["formatted"],
            "Total Disk Space": self.get_total_disk_space(),
            "OS Version": self.get_os_version(),
            "OS Build": self.get_os_build(),
            "System Locale": self.get_system_locale(),
            "Time Zone": self.get_timezone(),
            "Architecture": self.get_system_architecture(),
            "Connected Network": self.get_network_info(),
            "Domain/Workgroup": self.get_domain_workgroup(),
            "BIOS Version": self.get_bios_version(),
        }
