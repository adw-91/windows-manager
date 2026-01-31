"""Windows System Information Service - Fetches detailed system information"""

import platform
import socket
import psutil
import subprocess
from typing import Dict, Optional


class WindowsInfo:
    """Retrieve Windows system information"""

    def __init__(self):
        self._cache = {}

    def get_system_name(self) -> str:
        """Get computer hostname"""
        return socket.gethostname()

    def get_processor(self) -> str:
        """Get processor information"""
        try:
            # Try to get detailed CPU info from wmic
            result = subprocess.run(
                ['wmic', 'cpu', 'get', 'name'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                # Skip the header "Name" and get the actual processor name
                if len(lines) > 1:
                    return lines[1]
                elif len(lines) == 1 and lines[0].lower() != 'name':
                    return lines[0]
        except Exception as e:
            pass

        # Fallback to platform info
        cpu = platform.processor()
        if cpu:
            return cpu

        # Last resort: use psutil to get CPU count info
        return f"{psutil.cpu_count(logical=False)} Core Processor"

    def get_memory_info(self) -> Dict[str, any]:
        """Get detailed memory information with per-stick capacity"""
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)

        # Try to get detailed memory stick info
        stick_capacities = self._get_memory_stick_capacities()

        if stick_capacities:
            stick_count = len(stick_capacities)
            # Calculate per-stick GB (use the most common capacity)
            per_stick_gb = stick_capacities[0] / (1024**3)
            formatted = f"{total_gb:.1f} GB ({per_stick_gb:.1f} GB x{stick_count})"
        else:
            stick_count = 1
            formatted = f"{total_gb:.1f} GB"

        return {
            "total_gb": total_gb,
            "stick_count": stick_count,
            "formatted": formatted
        }

    def _get_memory_stick_capacities(self) -> list:
        """Get capacity of each physical memory stick in bytes"""
        try:
            result = subprocess.run(
                ['wmic', 'memorychip', 'get', 'capacity'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                # First line is header "Capacity", rest are actual capacities
                capacities = []
                for line in lines[1:]:
                    try:
                        capacities.append(int(line))
                    except ValueError:
                        continue
                return capacities
        except:
            pass
        return []

    def get_total_disk_space(self) -> str:
        """Get total disk space across all drives"""
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
        """Get primary network adapter information"""
        try:
            # Get network interfaces
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            # Find active interface with IP
            for interface, addr_list in addrs.items():
                if interface in stats and stats[interface].isup:
                    for addr in addr_list:
                        if addr.family == socket.AF_INET:  # IPv4
                            if not addr.address.startswith('127.'):
                                return f"{interface} ({addr.address})"
        except:
            pass
        return "Not connected"

    def get_os_version(self) -> str:
        """Get Windows version"""
        return f"{platform.system()} {platform.release()}"

    def get_os_build(self) -> str:
        """Get Windows build number"""
        return platform.version()

    def get_system_architecture(self) -> str:
        """Get system architecture"""
        return platform.machine()

    def get_domain_workgroup(self) -> str:
        """Get domain or workgroup name"""
        try:
            result = subprocess.run(
                ['wmic', 'computersystem', 'get', 'domain'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                if len(lines) > 1:
                    domain = lines[1]
                    return domain if domain else "WORKGROUP"
        except:
            pass
        return "Unknown"

    def get_manufacturer(self) -> str:
        """Get computer manufacturer"""
        try:
            result = subprocess.run(
                ['wmic', 'computersystem', 'get', 'manufacturer'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                if len(lines) > 1:
                    return lines[1]
        except:
            pass
        return "Unknown"

    def get_model(self) -> str:
        """Get computer model"""
        try:
            result = subprocess.run(
                ['wmic', 'computersystem', 'get', 'model'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                if len(lines) > 1:
                    return lines[1]
        except:
            pass
        return "Unknown"

    def get_bios_version(self) -> str:
        """Get BIOS version"""
        try:
            result = subprocess.run(
                ['wmic', 'bios', 'get', 'smbiosbiosversion'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                if len(lines) > 1:
                    return lines[1]
        except:
            pass
        return "Unknown"

    def get_system_locale(self) -> str:
        """Get system locale"""
        try:
            result = subprocess.run(
                ['powershell', '-Command', 'Get-WinSystemLocale | Select-Object -ExpandProperty Name'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                locale = result.stdout.strip()
                if locale:
                    return locale
        except:
            pass

        # Fallback to environment variable
        import locale as locale_module
        try:
            return locale_module.getdefaultlocale()[0] or "en-US"
        except:
            return "en-US"

    def get_timezone(self) -> str:
        """Get system timezone"""
        try:
            result = subprocess.run(
                ['tzutil', '/g'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass

        # Fallback
        import time
        return time.tzname[0]

    def get_all_system_info(self) -> Dict[str, str]:
        """Get all system information as a dictionary"""
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
