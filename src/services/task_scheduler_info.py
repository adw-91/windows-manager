"""Task Scheduler Service - Interface to Windows Task Scheduler via COM."""

import logging
import subprocess
import pythoncom
import win32com.client
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Task state mapping from COM constants
_STATE_MAP = {
    0: "Unknown",
    1: "Disabled",
    2: "Queued",
    3: "Ready",
    4: "Running",
}


@dataclass
class ScheduledTask:
    """Represents a Windows scheduled task."""
    name: str
    path: str
    state: str  # Ready, Running, Disabled, etc.
    last_run: Optional[str]
    next_run: Optional[str]
    last_result: str
    author: str
    description: str
    triggers: List[str]
    actions: List[str]


class TaskSchedulerInfo:
    """Interface to Windows Task Scheduler using COM (Schedule.Service)."""

    def __init__(self):
        self._tasks_cache: List[ScheduledTask] = []

    def _connect(self) -> win32com.client.CDispatch:
        """Connect to the Task Scheduler service."""
        pythoncom.CoInitialize()
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        return scheduler

    def get_all_tasks(self) -> List[Dict]:
        """Get all scheduled tasks via COM."""
        tasks = []
        try:
            scheduler = self._connect()
            root = scheduler.GetFolder("\\")
            self._enumerate_folder(root, tasks)
        except Exception as e:
            logger.warning("Failed to enumerate tasks: %s", e)
        return tasks

    def _enumerate_folder(self, folder: win32com.client.CDispatch, tasks: List[Dict]) -> None:
        """Recursively enumerate tasks in a folder."""
        try:
            for task in folder.GetTasks(0):  # 0 = include hidden tasks
                try:
                    full_path = task.Path
                    state_num = task.State
                    state_str = _STATE_MAP.get(state_num, "Unknown")

                    # Format datetime values
                    last_run = self._format_datetime(task.LastRunTime)
                    next_run = self._format_datetime(task.NextRunTime)
                    last_result = str(task.LastTaskResult)

                    # Get author from definition
                    author = ""
                    try:
                        author = task.Definition.RegistrationInfo.Author or ""
                    except Exception:
                        pass

                    # Get action info
                    action = ""
                    try:
                        actions = task.Definition.Actions
                        if actions.Count > 0:
                            action = actions.Item(1).Path or ""
                    except Exception:
                        pass

                    # Extract path and short name
                    if "\\" in full_path:
                        parts = full_path.rsplit("\\", 1)
                        path = parts[0] if parts[0] else "\\"
                        short_name = parts[1]
                    else:
                        path = "\\"
                        short_name = full_path

                    enabled = "Enabled" if task.Enabled else "Disabled"

                    if short_name:
                        tasks.append({
                            "name": full_path,
                            "state": state_str,
                            "last_run": last_run,
                            "next_run": next_run,
                            "last_result": last_result,
                            "author": author,
                            "action": action,
                            "enabled": enabled,
                            "path": path,
                            "short_name": short_name,
                        })
                except Exception:
                    continue

            # Recurse into subfolders
            for subfolder in folder.GetFolders(0):
                self._enumerate_folder(subfolder, tasks)
        except Exception as e:
            logger.debug("Error enumerating folder: %s", e)

    def _format_datetime(self, dt_value) -> str:
        """Format a COM datetime value to string."""
        try:
            if dt_value and hasattr(dt_value, "year"):
                if dt_value.year < 2000:
                    return "Never"
                return dt_value.strftime("%Y-%m-%d %H:%M")
            return str(dt_value) if dt_value else "N/A"
        except Exception:
            return "N/A"

    def run_task(self, task_path: str) -> bool:
        """Run a scheduled task immediately."""
        try:
            scheduler = self._connect()
            root = scheduler.GetFolder("\\")
            task = root.GetTask(task_path)
            task.Run(None)
            return True
        except Exception as e:
            logger.warning("Failed to run task '%s': %s", task_path, e)
            return False

    def enable_task(self, task_path: str) -> bool:
        """Enable a scheduled task."""
        try:
            scheduler = self._connect()
            root = scheduler.GetFolder("\\")
            task = root.GetTask(task_path)
            task.Enabled = True
            return True
        except Exception as e:
            logger.warning("Failed to enable task '%s': %s", task_path, e)
            return False

    def disable_task(self, task_path: str) -> bool:
        """Disable a scheduled task."""
        try:
            scheduler = self._connect()
            root = scheduler.GetFolder("\\")
            task = root.GetTask(task_path)
            task.Enabled = False
            return True
        except Exception as e:
            logger.warning("Failed to disable task '%s': %s", task_path, e)
            return False

    def end_task(self, task_path: str) -> bool:
        """End/stop a running task."""
        try:
            scheduler = self._connect()
            root = scheduler.GetFolder("\\")
            task = root.GetTask(task_path)
            task.Stop(0)
            return True
        except Exception as e:
            logger.warning("Failed to end task '%s': %s", task_path, e)
            return False

    def delete_task(self, task_path: str) -> bool:
        """Delete a scheduled task."""
        try:
            scheduler = self._connect()
            # Find the folder containing the task
            if "\\" in task_path:
                parts = task_path.rsplit("\\", 1)
                folder_path = parts[0] if parts[0] else "\\"
                task_name = parts[1]
            else:
                folder_path = "\\"
                task_name = task_path
            folder = scheduler.GetFolder(folder_path)
            folder.DeleteTask(task_name, 0)
            return True
        except Exception as e:
            logger.warning("Failed to delete task '%s': %s", task_path, e)
            return False

    def create_task(
        self,
        task_name: str,
        program: str,
        schedule_type: str,
        start_time: Optional[str] = None,
        start_date: Optional[str] = None,
        arguments: Optional[str] = None,
        working_dir: Optional[str] = None,
        run_as_system: bool = False,
        interval: int = 1,
        days: Optional[str] = None
    ) -> tuple[bool, str]:
        """Create a new scheduled task using schtasks (complex COM registration avoided)."""
        try:
            command = program
            if arguments:
                command = f'{program} {arguments}'

            cmd = [
                'schtasks', '/create',
                '/tn', task_name,
                '/tr', command,
                '/sc', schedule_type,
                '/f'
            ]

            if schedule_type in ('DAILY', 'WEEKLY', 'MONTHLY', 'ONCE'):
                if start_time:
                    cmd.extend(['/st', start_time])
                if start_date and schedule_type == 'ONCE':
                    cmd.extend(['/sd', start_date])

            if schedule_type in ('DAILY', 'WEEKLY', 'MONTHLY') and interval > 1:
                cmd.extend(['/mo', str(interval)])

            if schedule_type == 'WEEKLY' and days:
                cmd.extend(['/d', days])

            if schedule_type == 'MONTHLY' and days:
                cmd.extend(['/d', days])

            if run_as_system:
                cmd.extend(['/ru', 'SYSTEM'])

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )

            if result.returncode == 0:
                return True, ""
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                return False, error_msg

        except subprocess.TimeoutExpired:
            return False, "Task creation timed out"
        except Exception as e:
            return False, str(e)

    def get_task_folders(self) -> List[str]:
        """Get list of task scheduler folders via COM."""
        folders = set()
        try:
            scheduler = self._connect()
            root = scheduler.GetFolder("\\")
            folders.add("\\")
            self._enumerate_folders_recursive(root, folders)
        except Exception as e:
            logger.warning("Failed to enumerate task folders: %s", e)
        return sorted(folders)

    def _enumerate_folders_recursive(self, folder: win32com.client.CDispatch, folders: set) -> None:
        """Recursively collect folder paths."""
        try:
            for subfolder in folder.GetFolders(0):
                folders.add(subfolder.Path)
                self._enumerate_folders_recursive(subfolder, folders)
        except Exception:
            pass


_task_scheduler_info: Optional[TaskSchedulerInfo] = None


def get_task_scheduler_info() -> TaskSchedulerInfo:
    """Get the global TaskSchedulerInfo instance."""
    global _task_scheduler_info
    if _task_scheduler_info is None:
        _task_scheduler_info = TaskSchedulerInfo()
    return _task_scheduler_info
