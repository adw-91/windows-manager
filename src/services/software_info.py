"""
Installed Software Information Service.

Queries Windows Registry to get list of installed software from multiple locations:
- HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall
- HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall
- HKLM\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall (64-bit systems)
"""

import winreg
from typing import List, Dict, Optional
from datetime import datetime

from src.services.data_cache import DataCache


class SoftwareInfo:
    """Retrieve installed software information from Windows Registry."""

    # Registry paths to check
    REGISTRY_PATHS = [
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    def __init__(self):
        """Initialize the service."""
        pass

    def get_installed_software(self) -> List[Dict[str, str]]:
        """
        Get list of all installed software from registry.

        Returns:
            List of dicts with keys: Name, Publisher, Version, InstallDate, Size
        """
        software_dict = {}  # Use dict to deduplicate by name

        for hkey, path in self.REGISTRY_PATHS:
            try:
                self._read_registry_path(hkey, path, software_dict)
            except OSError:
                # Registry path doesn't exist or no access, skip it
                continue

        # Convert to list and return
        return list(software_dict.values())

    def _read_registry_path(
        self,
        hkey: int,
        path: str,
        software_dict: Dict[str, Dict[str, str]]
    ) -> None:
        """
        Read software entries from a specific registry path.

        Args:
            hkey: Registry hive (HKEY_LOCAL_MACHINE or HKEY_CURRENT_USER)
            path: Registry path to read
            software_dict: Dictionary to populate (keyed by display name)
        """
        try:
            with winreg.OpenKey(hkey, path) as key:
                index = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, index)
                        self._read_software_entry(hkey, path, subkey_name, software_dict)
                        index += 1
                    except OSError:
                        # No more subkeys
                        break
        except OSError:
            # Can't open key
            pass

    def _read_software_entry(
        self,
        hkey: int,
        path: str,
        subkey_name: str,
        software_dict: Dict[str, Dict[str, str]]
    ) -> None:
        """
        Read a single software entry from registry.

        Args:
            hkey: Registry hive
            path: Registry path
            subkey_name: Name of the subkey to read
            software_dict: Dictionary to populate
        """
        subkey_path = f"{path}\\{subkey_name}"

        try:
            with winreg.OpenKey(hkey, subkey_path) as subkey:
                # Get DisplayName - required field
                try:
                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                except OSError:
                    # No DisplayName, skip this entry
                    return

                # Skip system components and updates
                if not display_name or self._should_skip_entry(subkey, display_name):
                    return

                # Get other fields (optional)
                publisher = self._read_reg_value(subkey, "Publisher", "")
                version = self._read_reg_value(subkey, "DisplayVersion", "")
                install_date = self._read_reg_value(subkey, "InstallDate", "")
                size = self._read_reg_value(subkey, "EstimatedSize", "")
                install_location = self._read_reg_value(subkey, "InstallLocation", "")
                install_source = self._read_reg_value(subkey, "InstallSource", "")
                uninstall_string = self._read_reg_value(subkey, "UninstallString", "")
                modify_path = self._read_reg_value(subkey, "ModifyPath", "")

                # Parse and format fields
                formatted_date = self._parse_install_date(install_date)
                formatted_size = self._format_size(size)

                # Add to dict (dedupe by name, prefer entries with more info)
                if display_name not in software_dict or self._is_better_entry(
                    software_dict[display_name],
                    publisher,
                    version,
                    formatted_date,
                    formatted_size,
                    install_location,
                    install_source,
                    uninstall_string,
                    modify_path
                ):
                    software_dict[display_name] = {
                        "Name": display_name,
                        "Publisher": publisher,
                        "Version": version,
                        "InstallDate": formatted_date,
                        "Size": formatted_size,
                        "InstallLocation": install_location,
                        "InstallSource": install_source,
                        "UninstallString": uninstall_string,
                        "ModifyPath": modify_path,
                        "_date_sort": install_date,  # Keep raw for sorting
                        "_size_sort": self._parse_size_for_sort(size),
                    }

        except OSError:
            # Can't read this entry, skip
            pass

    def _should_skip_entry(self, subkey, display_name: str) -> bool:
        """
        Check if entry should be skipped (system component, update, etc.).

        Args:
            subkey: Registry key handle
            display_name: Display name of the software

        Returns:
            True if should skip
        """
        # Skip if SystemComponent flag is set
        try:
            system_component = winreg.QueryValueEx(subkey, "SystemComponent")[0]
            if system_component == 1:
                return True
        except OSError:
            pass

        # Skip if ParentKeyName exists (it's an update/patch)
        try:
            winreg.QueryValueEx(subkey, "ParentKeyName")
            return True
        except OSError:
            pass

        # Skip Windows updates
        if "KB" in display_name and ("Update" in display_name or "Hotfix" in display_name):
            return True

        return False

    def _read_reg_value(self, key, value_name: str, default: str = "") -> str:
        """
        Read a registry value, return default if not found.

        Args:
            key: Registry key handle
            value_name: Name of value to read
            default: Default value if not found

        Returns:
            Value as string, or default
        """
        try:
            value, _ = winreg.QueryValueEx(key, value_name)
            return str(value) if value else default
        except OSError:
            return default

    def _parse_install_date(self, date_str: str) -> str:
        """
        Parse install date from YYYYMMDD format to readable format.

        Args:
            date_str: Date in YYYYMMDD format (e.g., "20240115")

        Returns:
            Formatted date string (e.g., "2024-01-15") or empty string
        """
        if not date_str or len(date_str) != 8:
            return ""

        try:
            year = date_str[0:4]
            month = date_str[4:6]
            day = date_str[6:8]

            # Validate
            date_obj = datetime(int(year), int(month), int(day))
            return date_obj.strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            return ""

    def _format_size(self, size_str: str) -> str:
        """
        Format size from KB to human-readable format.

        Args:
            size_str: Size in KB as string

        Returns:
            Formatted size string (e.g., "1.5 GB") or empty string
        """
        if not size_str:
            return ""

        try:
            size_kb = int(size_str)
            if size_kb == 0:
                return ""

            # Convert KB to appropriate unit
            if size_kb < 1024:
                return f"{size_kb} KB"
            elif size_kb < 1024 * 1024:
                size_mb = size_kb / 1024
                return f"{size_mb:.1f} MB"
            else:
                size_gb = size_kb / (1024 * 1024)
                return f"{size_gb:.2f} GB"
        except (ValueError, TypeError):
            return ""

    def _parse_size_for_sort(self, size_str: str) -> int:
        """
        Parse size string to integer for sorting.

        Args:
            size_str: Size in KB as string

        Returns:
            Size as integer (KB), or 0 if invalid
        """
        try:
            return int(size_str) if size_str else 0
        except (ValueError, TypeError):
            return 0

    def _is_better_entry(
        self,
        existing: Dict[str, str],
        publisher: str,
        version: str,
        date: str,
        size: str,
        install_location: str,
        install_source: str,
        uninstall_string: str,
        modify_path: str
    ) -> bool:
        """
        Check if new entry has more information than existing.

        Args:
            existing: Existing entry dict
            publisher: New publisher value
            version: New version value
            date: New install date value
            size: New size value
            install_location: New install location value
            install_source: New install source value
            uninstall_string: New uninstall string value
            modify_path: New modify path value

        Returns:
            True if new entry is better
        """
        # Count non-empty fields in each (excluding internal _* fields)
        existing_count = sum(
            1 for k, v in existing.items()
            if not k.startswith("_") and v
        )
        new_count = sum(
            1 for v in [publisher, version, date, size, install_location,
                       install_source, uninstall_string, modify_path]
            if v
        )

        return new_count > existing_count


# Global instances
_software_info_instance: Optional[SoftwareInfo] = None
_software_cache_instance: Optional[DataCache] = None


def get_software_info() -> SoftwareInfo:
    """Get the global SoftwareInfo instance (singleton)."""
    global _software_info_instance
    if _software_info_instance is None:
        _software_info_instance = SoftwareInfo()
    return _software_info_instance


def get_software_cache() -> DataCache[List[Dict[str, str]]]:
    """
    Get the global software cache instance (singleton).

    This provides cached access to installed software with:
    - Background loading (non-blocking UI)
    - Manual refresh support
    - Thread-safe access

    Usage:
        cache = get_software_cache()
        cache.load()  # Start background load
        cache.data_loaded.connect(on_software_loaded)

        # Later...
        software_list = cache.get_data()
        cache.refresh()  # Reload
    """
    global _software_cache_instance
    if _software_cache_instance is None:
        software_service = get_software_info()
        _software_cache_instance = DataCache(
            loader_func=software_service.get_installed_software,
            fallback_value=[]
        )
    return _software_cache_instance
