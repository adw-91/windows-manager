"""Tests for win32 registry helpers."""
import unittest
import winreg
from src.utils.win32.registry import read_string, read_dword, enumerate_subkeys


class TestRegistry(unittest.TestCase):
    def test_read_string_known_key(self):
        """ProductName always exists in Windows registry."""
        result = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            "ProductName",
        )
        self.assertIsNotNone(result)
        self.assertIn("Windows", result)

    def test_read_string_missing_returns_none(self):
        result = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            "NonExistentValue12345",
        )
        self.assertIsNone(result)

    def test_read_string_bad_path_returns_none(self):
        result = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\NonExistent\Path12345",
            "Anything",
        )
        self.assertIsNone(result)

    def test_read_dword_known_key(self):
        result = read_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            "InstallDate",
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result, int)

    def test_enumerate_subkeys(self):
        """CentralProcessor always has at least one subkey (0)."""
        result = enumerate_subkeys(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor",
        )
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertIn("0", result)


if __name__ == "__main__":
    unittest.main()
