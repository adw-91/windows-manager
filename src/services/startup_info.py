"""
Startup Applications Information Service.

Queries Windows Registry, Task Scheduler, and startup folders to get list of
applications that run at system startup or user logon.
"""

import winreg
import os
from typing import List, Dict, Optional
from pathlib import Path

from src.services.data_cache import DataCache


class StartupInfo:
    """Retrieve startup applications information from multiple sources."""

    # Registry paths to check for Run and RunOnce keys
    REGISTRY_PATHS = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKLM Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce", "HKLM RunOnce"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKCU Run"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce", "HKCU RunOnce"),
    ]

    def __init__(self):
        """Initialize the service."""
        pass

    def get_startup_apps(self) -> List[Dict[str, str]]:
        """
        Get list of all startup applications from all sources.

        Returns:
            List of dicts with keys: Name, Command, Location, Type, Enabled
        """
        startup_list = []

        # Get from registry
        startup_list.extend(self._get_registry_startups())

        # Get from startup folders
        startup_list.extend(self._get_startup_folder_items())

        # Get from Task Scheduler
        startup_list.extend(self._get_task_scheduler_startups())

        return startup_list

    def _get_registry_startups(self) -> List[Dict[str, str]]:
        """
        Get startup items from registry Run/RunOnce keys.

        Returns:
            List of startup item dicts
        """
        startup_list = []

        for hkey, path, location in self.REGISTRY_PATHS:
            try:
                with winreg.OpenKey(hkey, path) as key:
                    index = 0
                    while True:
                        try:
                            name, command, _ = winreg.EnumValue(key, index)

                            # Check if this is a disabled entry (prefixed with __)
                            is_disabled = name.startswith("__")
                            display_name = name[2:] if is_disabled else name

                            startup_list.append({
                                "Name": display_name,
                                "Command": command,
                                "Location": location,
                                "Type": "Registry",
                                "Enabled": "No" if is_disabled else "Yes",
                                "_original_name": name,  # Keep original for management
                            })
                            index += 1
                        except OSError:
                            # No more values
                            break
            except OSError:
                # Registry key doesn't exist or no access
                continue

        return startup_list

    def _get_startup_folder_items(self) -> List[Dict[str, str]]:
        """
        Get startup items from shell:startup folders.

        Checks both user startup folder and all users startup folder.

        Returns:
            List of startup item dicts
        """
        startup_list = []

        # User startup folder
        user_startup = Path(os.path.expandvars(
            r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
        ))

        # All users startup folder
        all_users_startup = Path(os.path.expandvars(
            r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
        ))

        for folder_path, location in [
            (user_startup, "User Startup Folder"),
            (all_users_startup, "All Users Startup Folder")
        ]:
            if folder_path.exists():
                try:
                    for item in folder_path.iterdir():
                        if item.is_file():
                            startup_list.append({
                                "Name": item.stem,  # Filename without extension
                                "Command": str(item),
                                "Location": location,
                                "Type": "Startup Folder",
                                "Enabled": "Yes",
                            })
                except OSError:
                    # Permission denied or other error
                    continue

        return startup_list

    def _get_task_scheduler_startups(self) -> List[Dict[str, str]]:
        """
        Get startup items from Task Scheduler (tasks that run at logon).

        Uses COM to query Windows Task Scheduler for tasks configured to run
        at user logon.

        Returns:
            List of startup item dicts
        """
        startup_list = []

        try:
            import win32com.client

            scheduler = win32com.client.Dispatch("Schedule.Service")
            scheduler.Connect()

            # Get root folder and all subfolders
            folders_to_check = [scheduler.GetFolder("\\")]

            while folders_to_check:
                folder = folders_to_check.pop(0)

                # Add subfolders to check
                try:
                    for subfolder in folder.GetFolders(0):
                        folders_to_check.append(subfolder)
                except Exception:
                    pass

                # Check tasks in this folder
                try:
                    tasks = folder.GetTasks(0)
                    for task in tasks:
                        # Check if task runs at logon
                        if self._is_logon_task(task):
                            # Get task action (command)
                            command = self._get_task_command(task)

                            startup_list.append({
                                "Name": task.Name,
                                "Command": command,
                                "Location": "Task Scheduler",
                                "Type": "Scheduled Task",
                                "Enabled": "Yes" if task.Enabled else "No",
                            })
                except Exception:
                    continue

        except ImportError:
            # win32com not available
            pass
        except Exception:
            # Other error accessing Task Scheduler
            pass

        return startup_list

    def _is_logon_task(self, task) -> bool:
        """
        Check if a task is configured to run at logon.

        Args:
            task: Task Scheduler task object

        Returns:
            True if task runs at logon
        """
        try:
            definition = task.Definition
            triggers = definition.Triggers

            for trigger in triggers:
                # TASK_TRIGGER_LOGON = 9
                if trigger.Type == 9:
                    return True
        except Exception:
            pass

        return False

    def _get_task_command(self, task) -> str:
        """
        Get the command/action from a task.

        Args:
            task: Task Scheduler task object

        Returns:
            Command string
        """
        try:
            definition = task.Definition
            actions = definition.Actions

            if actions.Count > 0:
                action = actions.Item(1)  # COM uses 1-based indexing
                # TASK_ACTION_EXEC = 0
                if action.Type == 0:
                    command = action.Path
                    if action.Arguments:
                        command += f" {action.Arguments}"
                    return command
        except Exception:
            pass

        return "N/A"

    def set_startup_enabled(
        self,
        name: str,
        location: str,
        enabled: bool,
        original_name: Optional[str] = None
    ) -> bool:
        """
        Enable or disable a startup entry.

        Currently only supports registry entries. Scheduled tasks require
        different handling via Task Scheduler API.

        Args:
            name: Display name of the startup entry
            location: Location string (e.g., "HKLM Run", "HKCU Run")
            enabled: True to enable, False to disable
            original_name: Original registry name (with __ prefix if disabled)

        Returns:
            True if successful, False otherwise
        """
        # Only handle registry entries for now
        if "Run" not in location:
            return False

        # Map location to registry path
        location_map = {
            "HKLM Run": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            "HKLM RunOnce": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
            "HKCU Run": (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            "HKCU RunOnce": (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
        }

        if location not in location_map:
            return False

        hkey, path = location_map[location]
        current_name = original_name if original_name else name

        try:
            with winreg.OpenKey(hkey, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
                if enabled:
                    # If currently disabled (has __ prefix), enable it
                    if current_name.startswith("__"):
                        try:
                            value = winreg.QueryValueEx(key, current_name)[0]
                            # Rename back to original (remove __)
                            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
                            winreg.DeleteValue(key, current_name)
                            return True
                        except OSError:
                            return False
                    else:
                        # Already enabled
                        return True
                else:
                    # Disable by prefixing with __
                    if not current_name.startswith("__"):
                        try:
                            value = winreg.QueryValueEx(key, current_name)[0]
                            disabled_name = f"__{name}"
                            winreg.SetValueEx(key, disabled_name, 0, winreg.REG_SZ, value)
                            winreg.DeleteValue(key, current_name)
                            return True
                        except OSError:
                            return False
                    else:
                        # Already disabled
                        return True
        except OSError:
            # Permission denied or key doesn't exist
            return False

    def add_startup_app(self, name: str, command: str, location: str = "HKCU Run") -> bool:
        """
        Add a new startup entry.

        Args:
            name: Name for the startup entry
            command: Command/path to execute
            location: Where to add it (default: "HKCU Run")

        Returns:
            True if successful, False otherwise
        """
        # Map location to registry path
        location_map = {
            "HKLM Run": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            "HKLM RunOnce": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
            "HKCU Run": (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            "HKCU RunOnce": (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
        }

        if location not in location_map:
            return False

        hkey, path = location_map[location]

        try:
            with winreg.OpenKey(hkey, path, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
                return True
        except OSError:
            # Permission denied or key doesn't exist
            return False

    def remove_startup_app(self, name: str, location: str) -> bool:
        """
        Remove a startup entry.

        Args:
            name: Name of the startup entry
            location: Location string (e.g., "HKLM Run", "HKCU Run")

        Returns:
            True if successful, False otherwise
        """
        # Only handle registry entries for now
        if "Run" not in location:
            return False

        # Map location to registry path
        location_map = {
            "HKLM Run": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            "HKLM RunOnce": (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
            "HKCU Run": (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            "HKCU RunOnce": (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
        }

        if location not in location_map:
            return False

        hkey, path = location_map[location]

        try:
            with winreg.OpenKey(hkey, path, 0, winreg.KEY_WRITE) as key:
                winreg.DeleteValue(key, name)
                return True
        except OSError:
            # Permission denied, key doesn't exist, or value not found
            return False


# Global instances
_startup_info_instance: Optional[StartupInfo] = None
_startup_cache_instance: Optional[DataCache] = None


def get_startup_info() -> StartupInfo:
    """Get the global StartupInfo instance (singleton)."""
    global _startup_info_instance
    if _startup_info_instance is None:
        _startup_info_instance = StartupInfo()
    return _startup_info_instance


def get_startup_cache() -> DataCache[List[Dict[str, str]]]:
    """
    Get the global startup cache instance (singleton).

    This provides cached access to startup applications with:
    - Background loading (non-blocking UI)
    - Manual refresh support
    - Thread-safe access

    Usage:
        cache = get_startup_cache()
        cache.load()  # Start background load
        cache.data_loaded.connect(on_startup_loaded)

        # Later...
        startup_list = cache.get_data()
        cache.refresh()  # Reload
    """
    global _startup_cache_instance
    if _startup_cache_instance is None:
        startup_service = get_startup_info()
        _startup_cache_instance = DataCache(
            loader_func=startup_service.get_startup_apps,
            fallback_value=[]
        )
    return _startup_cache_instance
