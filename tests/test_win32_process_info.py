"""Tests for native process enumeration via NtQuerySystemInformation."""
import os
import unittest
from src.utils.win32.process_info import enumerate_processes


class TestEnumerateProcesses(unittest.TestCase):
    def test_returns_list(self):
        """Should return a non-empty list of process dicts."""
        procs = enumerate_processes()
        self.assertIsInstance(procs, list)
        self.assertGreater(len(procs), 10)

    def test_process_dict_keys(self):
        """Each process dict must have the expected keys."""
        procs = enumerate_processes()
        required_keys = {
            "pid", "name", "thread_count", "handle_count",
            "working_set_bytes", "user_time_ns", "kernel_time_ns",
            "create_time_ns", "parent_pid", "session_id",
            "status",
        }
        for proc in procs[:5]:
            for key in required_keys:
                self.assertIn(key, proc, f"Missing key '{key}' in process {proc.get('pid')}")

    def test_contains_current_process(self):
        """The current Python process should appear in results."""
        my_pid = os.getpid()
        procs = enumerate_processes()
        pids = [p["pid"] for p in procs]
        self.assertIn(my_pid, pids)

    def test_current_process_has_name(self):
        """The current process should have 'python' in its name."""
        my_pid = os.getpid()
        procs = enumerate_processes()
        my_proc = next(p for p in procs if p["pid"] == my_pid)
        self.assertIn("python", my_proc["name"].lower())

    def test_system_idle_process(self):
        """PID 0 should be 'System Idle Process'."""
        procs = enumerate_processes()
        idle = next((p for p in procs if p["pid"] == 0), None)
        self.assertIsNotNone(idle, "PID 0 not found")
        self.assertEqual(idle["name"], "System Idle Process")

    def test_thread_and_handle_counts_are_positive(self):
        """Non-idle processes should have positive thread and handle counts."""
        procs = enumerate_processes()
        # PID 4 (System) always has threads and handles
        system_proc = next((p for p in procs if p["pid"] == 4), None)
        if system_proc:
            self.assertGreater(system_proc["thread_count"], 0)
            self.assertGreater(system_proc["handle_count"], 0)

    def test_working_set_bytes_reasonable(self):
        """Current process should have non-trivial working set."""
        my_pid = os.getpid()
        procs = enumerate_processes()
        my_proc = next(p for p in procs if p["pid"] == my_pid)
        # Python process should use at least 1 MB
        self.assertGreater(my_proc["working_set_bytes"], 1_000_000)

    def test_total_thread_count(self):
        """Total thread count across all processes should be substantial."""
        procs = enumerate_processes()
        total_threads = sum(p["thread_count"] for p in procs)
        # Any Windows system has at least 500 threads
        self.assertGreater(total_threads, 100)

    def test_total_handle_count(self):
        """Total handle count across all processes should be substantial."""
        procs = enumerate_processes()
        total_handles = sum(p["handle_count"] for p in procs)
        # Any Windows system has thousands of handles
        self.assertGreater(total_handles, 1000)

    def test_status_values(self):
        """Status should be 'running' for all processes (kernel perspective)."""
        procs = enumerate_processes()
        for proc in procs:
            self.assertEqual(proc["status"], "running")


if __name__ == "__main__":
    unittest.main()
