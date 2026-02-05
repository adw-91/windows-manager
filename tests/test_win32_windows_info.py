"""Tests for WindowsInfo using native APIs."""
import unittest
from src.services.windows_info import WindowsInfo


class TestWindowsInfo(unittest.TestCase):
    def setUp(self):
        self.info = WindowsInfo()

    def test_get_processor(self):
        proc = self.info.get_processor()
        self.assertIsInstance(proc, str)
        self.assertNotEqual(proc, "Unknown")

    def test_get_memory_info(self):
        mem = self.info.get_memory_info()
        self.assertIn("total_gb", mem)
        self.assertIn("formatted", mem)
        self.assertGreater(mem["total_gb"], 0)

    def test_get_manufacturer(self):
        mfr = self.info.get_manufacturer()
        self.assertIsInstance(mfr, str)
        # Should not be empty or "Unknown" on real hardware
        self.assertGreater(len(mfr), 0)

    def test_get_model(self):
        model = self.info.get_model()
        self.assertIsInstance(model, str)

    def test_get_bios_version(self):
        bios = self.info.get_bios_version()
        self.assertIsInstance(bios, str)

    def test_get_system_locale(self):
        locale = self.info.get_system_locale()
        self.assertIsInstance(locale, str)
        self.assertIn("-", locale)

    def test_get_domain_workgroup(self):
        domain = self.info.get_domain_workgroup()
        self.assertIsInstance(domain, str)
        self.assertGreater(len(domain), 0)

    def test_get_all_system_info(self):
        """Smoke test — all fields should return strings."""
        info = self.info.get_all_system_info()
        self.assertIsInstance(info, dict)
        self.assertGreater(len(info), 5)


if __name__ == "__main__":
    unittest.main()
