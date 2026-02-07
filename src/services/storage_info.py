"""
Storage Information Service.

Provides drive overview (psutil + WMI) and on-demand directory scanning.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import psutil
from src.utils.win32.wmi import WmiConnection

logger = logging.getLogger(__name__)

# WMI DriveType values
DRIVE_TYPE_NAMES = {
    0: "Unknown",
    1: "No Root",
    2: "Removable",
    3: "Local",
    4: "Network",
    5: "CD/DVD",
    6: "RAM Disk",
}


@dataclass
class DriveInfo:
    """Information about a logical drive."""
    letter: str
    label: str
    filesystem: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float
    drive_type: int  # WMI DriveType code
    drive_type_name: str


@dataclass
class DirEntry:
    """Information about a directory entry for the size tree."""
    name: str
    path: str
    size_bytes: int
    item_count: int
    is_dir: bool
    is_accessible: bool = True


class StorageInfo:
    """Retrieve storage information and scan directories."""

    def get_drive_info(self) -> List[DriveInfo]:
        """Get info for all logical drives (instant — no scanning)."""
        drives: List[DriveInfo] = []

        # Get volume labels and drive types from WMI
        wmi_data = {}
        try:
            conn = WmiConnection()
            for row in conn.query(
                "SELECT DeviceID, VolumeName, DriveType, FileSystem "
                "FROM Win32_LogicalDisk"
            ):
                did = row.get("DeviceID") or ""
                wmi_data[did.upper()] = row
        except Exception as e:
            logger.warning("WMI LogicalDisk query failed: %s", e)

        for part in psutil.disk_partitions():
            mount = part.mountpoint
            letter = mount.rstrip("\\")

            try:
                usage = psutil.disk_usage(mount)
            except Exception:
                continue

            wmi_row = wmi_data.get(letter.upper(), {})
            label = wmi_row.get("VolumeName") or ""
            dtype = int(wmi_row.get("DriveType") or 3)
            fs = wmi_row.get("FileSystem") or part.fstype or ""

            drives.append(DriveInfo(
                letter=letter,
                label=label,
                filesystem=fs,
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                percent=usage.percent,
                drive_type=dtype,
                drive_type_name=DRIVE_TYPE_NAMES.get(dtype, "Unknown"),
            ))

        return drives

    def scan_directory(self, path: str, worker) -> List[DirEntry]:
        """Scan a directory's immediate children with sizes.

        For each child directory, recursively calculates total size.
        The worker parameter must have an `is_cancelled` property.
        Progress is emitted via worker.signals.progress.
        """
        entries: List[DirEntry] = []

        try:
            children = list(os.scandir(path))
        except (PermissionError, OSError):
            return [DirEntry(
                name="(Access denied)",
                path=path,
                size_bytes=0,
                item_count=0,
                is_dir=False,
                is_accessible=False,
            )]

        total = len(children)
        for i, entry in enumerate(children):
            if worker.is_cancelled:
                return entries

            if i % 50 == 0 and total > 0:
                worker.signals.progress.emit(int(i * 100 / total))

            try:
                if entry.is_dir(follow_symlinks=False):
                    size, count = self._calculate_dir_size(entry.path, worker)
                    entries.append(DirEntry(
                        name=entry.name,
                        path=entry.path,
                        size_bytes=size,
                        item_count=count,
                        is_dir=True,
                    ))
                else:
                    try:
                        st = entry.stat(follow_symlinks=False)
                        size = st.st_size
                    except (PermissionError, OSError):
                        size = 0
                    entries.append(DirEntry(
                        name=entry.name,
                        path=entry.path,
                        size_bytes=size,
                        item_count=1,
                        is_dir=False,
                    ))
            except (PermissionError, OSError):
                entries.append(DirEntry(
                    name=entry.name,
                    path=entry.path,
                    size_bytes=0,
                    item_count=0,
                    is_dir=entry.is_dir(follow_symlinks=False),
                    is_accessible=False,
                ))

        # Sort by size descending
        entries.sort(key=lambda e: e.size_bytes, reverse=True)
        return entries

    def _calculate_dir_size(self, path: str, worker, _depth: int = 0) -> tuple:
        """Recursively calculate total size and item count for a directory."""
        total_size = 0
        total_count = 0
        check_interval = 100

        try:
            with os.scandir(path) as it:
                for i, entry in enumerate(it):
                    if i % check_interval == 0 and worker.is_cancelled:
                        return total_size, total_count

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            sub_size, sub_count = self._calculate_dir_size(
                                entry.path, worker, _depth + 1,
                            )
                            total_size += sub_size
                            total_count += sub_count
                        else:
                            st = entry.stat(follow_symlinks=False)
                            total_size += st.st_size
                            total_count += 1
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError):
            pass

        return total_size, total_count


# Global instance
_storage_info_instance: Optional[StorageInfo] = None


def get_storage_info() -> StorageInfo:
    """Get the global StorageInfo instance (singleton)."""
    global _storage_info_instance
    if _storage_info_instance is None:
        _storage_info_instance = StorageInfo()
    return _storage_info_instance
