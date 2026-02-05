"""Tests for win32 system info ctypes wrappers."""
import unittest
from src.utils.win32.system_info import (
    get_system_locale,
    get_total_physical_memory,
    get_firmware_type,
    is_secure_boot_enabled,
    get_computer_name_ex,
)


class TestSystemInfo(unittest.TestCase):
    def test_get_system_locale(self):
        locale = get_system_locale()
        self.assertIsInstance(locale, str)
        self.assertGreater(len(locale), 0)
        # Locale format is like "en-US"
        self.assertIn("-", locale)

    def test_get_total_physical_memory(self):
        mem = get_total_physical_memory()
        self.assertIsInstance(mem, int)
        # At least 512 MB
        self.assertGreater(mem, 512 * 1024 * 1024)

    def test_get_firmware_type(self):
        fw = get_firmware_type()
        self.assertIn(fw, ("UEFI", "BIOS", "Unknown"))

    def test_is_secure_boot_enabled(self):
        result = is_secure_boot_enabled()
        # Can be True, False, or None (if not UEFI)
        self.assertIn(result, (True, False, None))

    def test_get_computer_name_ex(self):
        # ComputerNameNetBIOS = 0
        name = get_computer_name_ex(0)
        self.assertIsNotNone(name)
        self.assertGreater(len(name), 0)


if __name__ == "__main__":
    unittest.main()
