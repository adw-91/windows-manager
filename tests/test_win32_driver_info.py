"""Tests for DeviceInfo using native SetupAPI."""
import unittest
from src.services.device_info import DeviceInfo


class TestDeviceInfo(unittest.TestCase):
    def test_get_all_devices(self):
        info = DeviceInfo()
        devices = info.get_all_devices()
        self.assertIsInstance(devices, list)
        self.assertGreater(len(devices), 5)

    def test_device_dict_keys(self):
        info = DeviceInfo()
        devices = info.get_all_devices()
        if devices:
            d = devices[0]
            for key in ("device_id", "name", "class_name", "problem_code", "has_problem"):
                self.assertIn(key, d)

    def test_problem_description(self):
        self.assertEqual(DeviceInfo.get_problem_description(0), "Working properly")
        self.assertEqual(DeviceInfo.get_problem_description(22), "Disabled")
        self.assertIn("Unknown", DeviceInfo.get_problem_description(999))


if __name__ == "__main__":
    unittest.main()
