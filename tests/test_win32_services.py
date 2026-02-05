"""Tests for service_info using win32service API."""
import unittest
from src.services.service_info import ServiceInfo


class TestServiceInfo(unittest.TestCase):
    def test_get_all_services(self):
        svc = ServiceInfo()
        services = svc.get_all_services()
        self.assertIsInstance(services, list)
        self.assertGreater(len(services), 50)  # Windows has 100+ services

    def test_service_dict_keys(self):
        svc = ServiceInfo()
        services = svc.get_all_services()
        if services:
            s = services[0]
            for key in ("Name", "DisplayName", "Status", "StartMode", "PathName", "Description"):
                self.assertIn(key, s, f"Missing key: {key}")

    def test_get_service_info_existing(self):
        """'Spooler' service exists on all Windows machines."""
        svc = ServiceInfo()
        info = svc.get_service_info("Spooler")
        self.assertIsNotNone(info)
        self.assertEqual(info["Name"], "Spooler")
        self.assertIn(info["Status"], ("Running", "Stopped", "Start Pending", "Stop Pending",
                                        "Continue Pending", "Pause Pending", "Paused", "Unknown"))

    def test_get_service_info_nonexistent(self):
        svc = ServiceInfo()
        info = svc.get_service_info("NonExistentService12345")
        self.assertIsNone(info)


if __name__ == "__main__":
    unittest.main()
