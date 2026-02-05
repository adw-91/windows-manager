"""Tests for win32 WMI COM helper."""
import unittest
from src.utils.win32.wmi import WmiConnection


class TestWmiConnection(unittest.TestCase):
    def test_query_operating_system(self):
        """Win32_OperatingSystem always returns exactly one result."""
        conn = WmiConnection()
        results = conn.query("SELECT Caption FROM Win32_OperatingSystem")
        self.assertEqual(len(results), 1)
        self.assertIn("Caption", results[0])
        self.assertIn("Windows", results[0]["Caption"])

    def test_query_single(self):
        result = WmiConnection().query_single("SELECT Caption FROM Win32_OperatingSystem")
        self.assertIsNotNone(result)
        self.assertIn("Windows", result["Caption"])

    def test_query_single_no_results(self):
        result = WmiConnection().query_single(
            "SELECT Name FROM Win32_SystemDriver WHERE Name = 'NonExistentDriver12345'"
        )
        self.assertIsNone(result)

    def test_query_multiple_results(self):
        """Win32_SystemDriver always returns multiple drivers."""
        conn = WmiConnection()
        results = conn.query("SELECT Name FROM Win32_SystemDriver")
        self.assertGreater(len(results), 10)

    def test_root_wmi_namespace(self):
        """root\\WMI namespace should be accessible."""
        conn = WmiConnection(r"root\WMI")
        # MSAcpi_ThermalZoneTemperature may or may not exist, but connection should succeed
        self.assertIsNotNone(conn)


if __name__ == "__main__":
    unittest.main()
