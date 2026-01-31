"""Tests for SystemMonitor service"""

import unittest
from src.services.system_monitor import SystemMonitor


class TestSystemMonitor(unittest.TestCase):
    """Test cases for SystemMonitor"""

    def setUp(self):
        """Set up test fixtures"""
        self.monitor = SystemMonitor()

    def test_get_cpu_usage(self):
        """Test CPU usage retrieval"""
        cpu_usage = self.monitor.get_cpu_usage()
        self.assertIsInstance(cpu_usage, float)
        self.assertGreaterEqual(cpu_usage, 0.0)
        self.assertLessEqual(cpu_usage, 100.0)

    def test_get_memory_info(self):
        """Test memory information retrieval"""
        mem_info = self.monitor.get_memory_info()
        self.assertIn("total", mem_info)
        self.assertIn("available", mem_info)
        self.assertIn("used", mem_info)
        self.assertIn("percent", mem_info)
        self.assertGreater(mem_info["total"], 0)

    def test_get_disk_info(self):
        """Test disk information retrieval"""
        disk_info = self.monitor.get_disk_info()
        self.assertIsInstance(disk_info, list)

    def test_get_system_uptime(self):
        """Test system uptime retrieval"""
        uptime = self.monitor.get_system_uptime()
        self.assertIsInstance(uptime, float)
        self.assertGreater(uptime, 0)


if __name__ == "__main__":
    unittest.main()
