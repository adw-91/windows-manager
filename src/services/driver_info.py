"""
Windows Drivers Information Service.

Queries Windows drivers using WMI COM Win32_SystemDriver class.
"""

import logging
from typing import List, Dict, Optional

from src.utils.win32.wmi import WmiConnection

logger = logging.getLogger(__name__)


class DriverInfo:
    """Retrieve Windows system driver information using WMI COM."""

    def __init__(self):
        """Initialize the service."""
        pass

    def get_all_drivers(self) -> List[Dict[str, str]]:
        """Get list of all Windows system drivers from WMI COM.

        Returns:
            List of dicts with keys: Name, DisplayName, PathName, State, StartMode, Description
        """
        try:
            conn = WmiConnection()
            results = conn.query(
                "SELECT Name, DisplayName, PathName, State, StartMode, Description "
                "FROM Win32_SystemDriver"
            )
            drivers = []
            for row in results:
                name = row.get("Name") or ""
                if not name:
                    continue
                drivers.append({
                    "Name": name,
                    "DisplayName": row.get("DisplayName") or name,
                    "PathName": row.get("PathName") or "",
                    "State": row.get("State") or "",
                    "StartMode": row.get("StartMode") or "",
                    "Description": row.get("Description") or "",
                })
            return drivers
        except Exception as e:
            logger.warning("Failed to query drivers: %s", e)
            return []


# Global instances
_driver_info_instance: Optional[DriverInfo] = None


def get_driver_info() -> DriverInfo:
    """Get the global DriverInfo instance (singleton)."""
    global _driver_info_instance
    if _driver_info_instance is None:
        _driver_info_instance = DriverInfo()
    return _driver_info_instance
