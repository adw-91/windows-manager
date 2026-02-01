"""Task Scheduler Service - Interface to Windows Task Scheduler."""

import subprocess
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime


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
    """Interface to Windows Task Scheduler using schtasks command."""

    def __init__(self):
        self._tasks_cache: List[ScheduledTask] = []

    def get_all_tasks(self) -> List[Dict]:
        """Get all scheduled tasks."""
        tasks = []
        try:
            # Use schtasks to get task list in CSV format
            result = subprocess.run(
                ['schtasks', '/query', '/fo', 'CSV', '/v'],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    # Parse CSV header
                    headers = self._parse_csv_line(lines[0])

                    # Find column indices
                    col_map = {}
                    for i, h in enumerate(headers):
                        h_lower = h.lower().strip('"')
                        if 'taskname' in h_lower or h_lower == 'taskname':
                            col_map['name'] = i
                        elif 'status' in h_lower:
                            col_map['state'] = i
                        elif 'last run time' in h_lower:
                            col_map['last_run'] = i
                        elif 'next run time' in h_lower:
                            col_map['next_run'] = i
                        elif 'last result' in h_lower:
                            col_map['last_result'] = i
                        elif 'author' in h_lower:
                            col_map['author'] = i
                        elif 'task to run' in h_lower:
                            col_map['action'] = i
                        elif 'scheduled task state' in h_lower:
                            col_map['enabled'] = i

                    # Parse task rows
                    for line in lines[1:]:
                        if not line.strip():
                            continue

                        values = self._parse_csv_line(line)
                        if len(values) > max(col_map.values(), default=0):
                            task = {
                                'name': self._get_col(values, col_map, 'name', ''),
                                'state': self._get_col(values, col_map, 'state', 'Unknown'),
                                'last_run': self._get_col(values, col_map, 'last_run', 'Never'),
                                'next_run': self._get_col(values, col_map, 'next_run', 'N/A'),
                                'last_result': self._get_col(values, col_map, 'last_result', '0'),
                                'author': self._get_col(values, col_map, 'author', ''),
                                'action': self._get_col(values, col_map, 'action', ''),
                                'enabled': self._get_col(values, col_map, 'enabled', 'Enabled'),
                            }

                            # Extract path from full task name
                            full_name = task['name']
                            if '\\' in full_name:
                                parts = full_name.rsplit('\\', 1)
                                task['path'] = parts[0] if parts[0] else '\\'
                                task['short_name'] = parts[1]
                            else:
                                task['path'] = '\\'
                                task['short_name'] = full_name

                            # Skip empty names
                            if task['short_name']:
                                tasks.append(task)

        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            pass

        return tasks

    def _parse_csv_line(self, line: str) -> List[str]:
        """Parse a CSV line handling quoted fields."""
        values = []
        current = ""
        in_quotes = False

        for char in line:
            if char == '"':
                in_quotes = not in_quotes
            elif char == ',' and not in_quotes:
                values.append(current.strip('"').strip())
                current = ""
            else:
                current += char

        values.append(current.strip('"').strip())
        return values

    def _get_col(self, values: List[str], col_map: Dict, key: str, default: str) -> str:
        """Safely get column value."""
        if key in col_map and col_map[key] < len(values):
            return values[col_map[key]]
        return default

    def run_task(self, task_name: str) -> bool:
        """Run a scheduled task immediately."""
        try:
            result = subprocess.run(
                ['schtasks', '/run', '/tn', task_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except:
            return False

    def enable_task(self, task_name: str) -> bool:
        """Enable a scheduled task."""
        try:
            result = subprocess.run(
                ['schtasks', '/change', '/tn', task_name, '/enable'],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except:
            return False

    def disable_task(self, task_name: str) -> bool:
        """Disable a scheduled task."""
        try:
            result = subprocess.run(
                ['schtasks', '/change', '/tn', task_name, '/disable'],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except:
            return False

    def end_task(self, task_name: str) -> bool:
        """End/stop a running task."""
        try:
            result = subprocess.run(
                ['schtasks', '/end', '/tn', task_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except:
            return False

    def delete_task(self, task_name: str) -> bool:
        """Delete a scheduled task."""
        try:
            result = subprocess.run(
                ['schtasks', '/delete', '/tn', task_name, '/f'],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except:
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
        """
        Create a new scheduled task.

        Args:
            task_name: Name of the task
            program: Path to program to run
            schedule_type: ONCE, DAILY, WEEKLY, MONTHLY, ONSTART, ONLOGON
            start_time: Start time in HH:MM format
            start_date: Start date in MM/DD/YYYY format (for ONCE)
            arguments: Arguments to pass to program
            working_dir: Working directory
            run_as_system: Run as SYSTEM user
            interval: Interval modifier (e.g., every N days)
            days: Days for WEEKLY (MON,TUE,etc) or day of month

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Build command to run
            command = program
            if arguments:
                command = f'{program} {arguments}'

            # Build schtasks command
            cmd = [
                'schtasks', '/create',
                '/tn', task_name,
                '/tr', command,
                '/sc', schedule_type,
                '/f'  # Force overwrite if exists
            ]

            # Add schedule-specific parameters
            if schedule_type in ('DAILY', 'WEEKLY', 'MONTHLY', 'ONCE'):
                if start_time:
                    cmd.extend(['/st', start_time])
                if start_date and schedule_type == 'ONCE':
                    cmd.extend(['/sd', start_date])

            # Add interval modifier
            if schedule_type in ('DAILY', 'WEEKLY', 'MONTHLY') and interval > 1:
                cmd.extend(['/mo', str(interval)])

            # Add days for WEEKLY
            if schedule_type == 'WEEKLY' and days:
                cmd.extend(['/d', days])

            # Add day of month for MONTHLY
            if schedule_type == 'MONTHLY' and days:
                cmd.extend(['/d', days])

            # Run as SYSTEM or interactive user
            if run_as_system:
                cmd.extend(['/ru', 'SYSTEM'])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15
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
        """Get list of task scheduler folders."""
        folders = set()
        tasks = self.get_all_tasks()
        for task in tasks:
            path = task.get('path', '\\')
            if path:
                folders.add(path)
                # Add parent folders
                parts = path.split('\\')
                for i in range(1, len(parts)):
                    parent = '\\'.join(parts[:i+1])
                    if parent:
                        folders.add(parent)
        return sorted(folders)


_task_scheduler_info: Optional[TaskSchedulerInfo] = None


def get_task_scheduler_info() -> TaskSchedulerInfo:
    """Get the global TaskSchedulerInfo instance."""
    global _task_scheduler_info
    if _task_scheduler_info is None:
        _task_scheduler_info = TaskSchedulerInfo()
    return _task_scheduler_info
