"""
Device Information Service.

Wraps native SetupAPI device enumeration with driver detail lookups.
"""

import logging
import winreg
from typing import List, Dict, Optional

from src.utils.win32.device_api import enumerate_devices
from src.utils.win32.registry import read_string

logger = logging.getLogger(__name__)

# CM_PROB_* codes → human-readable descriptions (from MS Learn)
PROBLEM_CODES: Dict[int, str] = {
    0: "Working properly",
    1: "Not configured correctly",
    3: "Driver may be corrupted",
    10: "Cannot start",
    12: "Insufficient resources",
    14: "Restart required",
    16: "Not fully detected",
    18: "Reinstall drivers",
    21: "Windows is removing device",
    22: "Disabled",
    24: "Not present",
    28: "Drivers not installed",
    29: "Disabled by firmware",
    31: "Not working properly",
    32: "Driver disabled (previous instance)",
    33: "Resource translator unavailable",
    34: "Cannot determine resources",
    35: "BIOS resource conflict",
    36: "IRQ translation failed",
    37: "Cannot determine all resources",
    38: "Duplicate device",
    39: "Registry problem",
    40: "Driver cannot load",
    41: "Hardware failure",
    42: "Failure creating device",
    43: "Stopped (reported problems)",
    44: "Stopped by driver",
    45: "Not connected",
    46: "Access denied",
    47: "Pending removal",
    48: "Blocked by policy",
    49: "Registry too large",
    50: "Cannot set properties",
    51: "Device waiting on dependency",
    52: "Unsigned driver",
}


class DeviceInfo:
    """Retrieve Windows device information using native SetupAPI."""

    def get_all_devices(self) -> List[Dict]:
        """Get list of all present PnP devices."""
        try:
            return enumerate_devices()
        except Exception as e:
            logger.warning("Failed to enumerate devices: %s", e)
            return []

    def get_driver_details(self, device: Dict) -> Dict[str, str]:
        """Read driver version/date/provider from the driver registry key.

        Called lazily when a device is selected in the tree.
        """
        details: Dict[str, str] = {}
        driver_key = device.get("driver_key", "")
        class_guid = device.get("class_guid", "")

        if not driver_key or not class_guid:
            return details

        reg_path = f"SYSTEM\\CurrentControlSet\\Control\\Class\\{class_guid}\\{driver_key}"

        version = read_string(winreg.HKEY_LOCAL_MACHINE, reg_path, "DriverVersion")
        if version:
            details["Driver Version"] = version

        date = read_string(winreg.HKEY_LOCAL_MACHINE, reg_path, "DriverDate")
        if date:
            details["Driver Date"] = date

        provider = read_string(winreg.HKEY_LOCAL_MACHINE, reg_path, "ProviderName")
        if provider:
            details["Provider"] = provider

        inf_path = read_string(winreg.HKEY_LOCAL_MACHINE, reg_path, "InfPath")
        if inf_path:
            details["INF File"] = inf_path

        return details

    @staticmethod
    def get_problem_description(code: int) -> str:
        """Get human-readable description for a CM_PROB_* code."""
        return PROBLEM_CODES.get(code, f"Unknown problem (code {code})")


# Global instance
_device_info_instance: Optional[DeviceInfo] = None


def get_device_info() -> DeviceInfo:
    """Get the global DeviceInfo instance (singleton)."""
    global _device_info_instance
    if _device_info_instance is None:
        _device_info_instance = DeviceInfo()
    return _device_info_instance
