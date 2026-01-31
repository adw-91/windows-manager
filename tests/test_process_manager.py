"""Tests for ProcessManager service"""

import unittest
from src.services.process_manager import ProcessManager


class TestProcessManager(unittest.TestCase):
    """Test cases for ProcessManager"""

    def setUp(self):
        """Set up test fixtures"""
        self.manager = ProcessManager()

    def test_get_all_processes(self):
        """Test retrieving all processes"""
        processes = self.manager.get_all_processes()
        self.assertIsInstance(processes, list)
        self.assertGreater(len(processes), 0)

        if processes:
            proc = processes[0]
            self.assertIn("pid", proc)
            self.assertIn("name", proc)
            self.assertIn("cpu_percent", proc)
            self.assertIn("memory_mb", proc)

    def test_get_process_count(self):
        """Test getting process count"""
        count = self.manager.get_process_count()
        self.assertIsInstance(count, int)
        self.assertGreater(count, 0)

    def test_get_process_info(self):
        """Test getting info for a specific process"""
        import os
        current_pid = os.getpid()
        info = self.manager.get_process_info(current_pid)

        self.assertIsNotNone(info)
        self.assertEqual(info["pid"], current_pid)
        self.assertIn("name", info)
        self.assertIn("status", info)


if __name__ == "__main__":
    unittest.main()
