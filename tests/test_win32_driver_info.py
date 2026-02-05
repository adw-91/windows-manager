"""Tests for DriverInfo using WMI COM."""
import unittest
from src.services.driver_info import DriverInfo


class TestDriverInfo(unittest.TestCase):
    def test_get_all_drivers(self):
        info = DriverInfo()
        drivers = info.get_all_drivers()
        self.assertIsInstance(drivers, list)
        self.assertGreater(len(drivers), 10)

    def test_driver_dict_keys(self):
        info = DriverInfo()
        drivers = info.get_all_drivers()
        if drivers:
            d = drivers[0]
            for key in ("Name", "DisplayName", "State", "StartMode"):
                self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()
