"""Tests for ProcessManager service"""

import os
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
        current_pid = os.getpid()
        info = self.manager.get_process_info(current_pid)

        self.assertIsNotNone(info)
        self.assertEqual(info["pid"], current_pid)
        self.assertIn("name", info)
        self.assertIn("status", info)


class TestProcessManagerNative(unittest.TestCase):
    """Test native enumeration features of ProcessManager."""

    def test_get_all_processes_returns_list(self):
        pm = ProcessManager()
        procs = pm.get_all_processes()
        self.assertIsInstance(procs, list)
        self.assertGreater(len(procs), 10)

    def test_process_dict_has_required_keys(self):
        pm = ProcessManager()
        procs = pm.get_all_processes()
        for proc in procs[:5]:
            for key in ("pid", "name", "cpu_percent", "memory_mb", "status"):
                self.assertIn(key, proc)

    def test_cpu_percent_is_zero_on_first_call(self):
        """First call has no delta, so CPU should be 0.0 for all."""
        pm = ProcessManager()
        procs = pm.get_all_processes()
        for proc in procs:
            self.assertEqual(proc["cpu_percent"], 0.0)

    def test_fast_update_returns_data_after_init(self):
        pm = ProcessManager()
        pm.get_all_processes()  # Initialize
        fast = pm.get_fast_update()
        self.assertGreater(len(fast), 10)

    def test_fast_update_returns_empty_before_init(self):
        pm = ProcessManager()
        fast = pm.get_fast_update()
        self.assertEqual(fast, [])

    def test_get_process_count(self):
        pm = ProcessManager()
        count = pm.get_process_count()
        self.assertGreater(count, 10)

    def test_get_thread_handle_totals(self):
        pm = ProcessManager()
        pm.get_all_processes()  # Populate cache
        threads, handles = pm.get_thread_handle_totals()
        self.assertGreater(threads, 100)
        self.assertGreater(handles, 1000)


if __name__ == "__main__":
    unittest.main()
