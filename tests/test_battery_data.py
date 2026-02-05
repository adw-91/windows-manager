"""Tests for battery data collection (no UI)."""
import unittest
import winreg
from src.utils.win32.registry import read_string


class TestBatteryData(unittest.TestCase):
    def test_power_plan_registry(self):
        """Active power scheme GUID should be readable from registry."""
        guid = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes",
            "ActivePowerScheme",
        )
        self.assertIsNotNone(guid)
        self.assertGreater(len(guid), 0)
        # GUID format has dashes
        self.assertIn("-", guid)

    def test_wmi_battery_query(self):
        """Win32_Battery WMI query should not crash (may return empty on desktops)."""
        from src.utils.win32.wmi import WmiConnection
        conn = WmiConnection()
        result = conn.query("SELECT Name FROM Win32_Battery")
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
