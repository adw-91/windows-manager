"""Tests for SystemTab data collection (no UI, just the worker function)."""
import unittest
from src.services.windows_info import WindowsInfo


class TestSystemTabData(unittest.TestCase):
    """Test the data collection methods used by SystemTab.

    We import and test WindowsInfo directly since the SystemTab data methods
    use WindowsInfo + registry/ctypes calls that don't require Qt.
    """

    def test_windows_info_system_summary_fields(self):
        """WindowsInfo provides all fields needed for system summary."""
        info = WindowsInfo()
        self.assertIsInstance(info.get_system_name(), str)
        self.assertIsInstance(info.get_manufacturer(), str)
        self.assertIsInstance(info.get_model(), str)
        self.assertIsInstance(info.get_processor(), str)

    def test_windows_info_hardware_fields(self):
        """WindowsInfo provides BIOS version."""
        info = WindowsInfo()
        bios = info.get_bios_version()
        self.assertIsInstance(bios, str)
        self.assertNotEqual(bios, "")

    def test_registry_display_adapter(self):
        """Display adapter name should be readable from registry."""
        import winreg
        from src.utils.win32.registry import read_string
        display = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000",
            "DriverDesc",
        )
        # May be None on VMs without GPU, but should not raise
        self.assertTrue(display is None or isinstance(display, str))

    def test_secure_boot_check(self):
        """Secure boot check should return bool or None."""
        from src.utils.win32.system_info import is_secure_boot_enabled
        result = is_secure_boot_enabled()
        self.assertIn(result, (True, False, None))


if __name__ == "__main__":
    unittest.main()
