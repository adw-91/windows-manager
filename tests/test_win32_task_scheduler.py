"""Tests for TaskSchedulerInfo using COM."""
import unittest
from src.services.task_scheduler_info import TaskSchedulerInfo


class TestTaskScheduler(unittest.TestCase):
    def test_get_all_tasks(self):
        info = TaskSchedulerInfo()
        tasks = info.get_all_tasks()
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0)

    def test_task_dict_keys(self):
        info = TaskSchedulerInfo()
        tasks = info.get_all_tasks()
        if tasks:
            t = tasks[0]
            for key in ("name", "path", "state", "short_name"):
                self.assertIn(key, t, f"Missing key: {key}")

    def test_task_folders(self):
        info = TaskSchedulerInfo()
        folders = info.get_task_folders()
        self.assertIsInstance(folders, list)
        self.assertIn("\\", folders)


if __name__ == "__main__":
    unittest.main()
