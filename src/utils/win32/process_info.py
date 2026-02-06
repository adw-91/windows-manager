"""Native process enumeration via NtQuerySystemInformation.

Uses a single kernel call to get all process data (PID, name, threads,
handles, memory, CPU times) without opening per-process handles.
This bypasses EDR interception that makes psutil.process_iter() slow
on enterprise machines.
"""
import ctypes
from ctypes import wintypes
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

ntdll = ctypes.windll.ntdll

# Constants
SystemProcessInformation = 5
STATUS_SUCCESS = 0
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", ctypes.c_ushort),
        ("MaximumLength", ctypes.c_ushort),
        ("Buffer", ctypes.c_wchar_p),
    ]


class SYSTEM_PROCESS_INFORMATION(ctypes.Structure):
    """Kernel process information struct returned by NtQuerySystemInformation.

    64-bit layout. Fields documented at:
    https://ntdoc.m417z.com/system_process_information
    """
    _fields_ = [
        ("NextEntryOffset", wintypes.ULONG),
        ("NumberOfThreads", wintypes.ULONG),
        ("WorkingSetPrivateSize", ctypes.c_longlong),
        ("HardFaultCount", wintypes.ULONG),
        ("NumberOfThreadsHighWatermark", wintypes.ULONG),
        ("CycleTime", ctypes.c_ulonglong),
        ("CreateTime", ctypes.c_longlong),
        ("UserTime", ctypes.c_longlong),
        ("KernelTime", ctypes.c_longlong),
        ("ImageName", UNICODE_STRING),
        ("BasePriority", ctypes.c_long),
        ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p),
        ("HandleCount", wintypes.ULONG),
        ("SessionId", wintypes.ULONG),
        ("UniqueProcessKey", ctypes.c_size_t),
        ("PeakVirtualSize", ctypes.c_size_t),
        ("VirtualSize", ctypes.c_size_t),
        ("PageFaultCount", wintypes.ULONG),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivatePageCount", ctypes.c_size_t),
        ("ReadOperationCount", ctypes.c_longlong),
        ("WriteOperationCount", ctypes.c_longlong),
        ("OtherOperationCount", ctypes.c_longlong),
        ("ReadTransferCount", ctypes.c_longlong),
        ("WriteTransferCount", ctypes.c_longlong),
        ("OtherTransferCount", ctypes.c_longlong),
    ]


# Set up function signature once at module level
ntdll.NtQuerySystemInformation.argtypes = [
    wintypes.ULONG,
    ctypes.c_void_p,
    wintypes.ULONG,
    ctypes.POINTER(wintypes.ULONG),
]
ntdll.NtQuerySystemInformation.restype = ctypes.c_ulong


def _query_system_process_information() -> ctypes.Array:
    """Call NtQuerySystemInformation and return the raw byte buffer.

    Handles the two-pass pattern: first call to get required size,
    second call with allocated buffer. Retries if buffer is too small
    (processes can spawn between calls).
    """
    return_length = wintypes.ULONG(0)

    # Pass 1: get required buffer size
    ntdll.NtQuerySystemInformation(
        SystemProcessInformation, None, 0, ctypes.byref(return_length),
    )

    # Allocate with 64KB margin for processes spawning between calls
    buf_size = return_length.value + 0x10000
    buf = (ctypes.c_byte * buf_size)()

    # Pass 2: query the data
    status = ntdll.NtQuerySystemInformation(
        SystemProcessInformation,
        ctypes.byref(buf),
        buf_size,
        ctypes.byref(return_length),
    )

    if status & 0xFFFFFFFF == STATUS_INFO_LENGTH_MISMATCH:
        # Retry with double the returned size
        buf_size = return_length.value * 2
        buf = (ctypes.c_byte * buf_size)()
        status = ntdll.NtQuerySystemInformation(
            SystemProcessInformation,
            ctypes.byref(buf),
            buf_size,
            ctypes.byref(return_length),
        )

    if status != STATUS_SUCCESS:
        raise OSError(
            f"NtQuerySystemInformation failed with NTSTATUS 0x{status:08X}"
        )

    return buf


def enumerate_processes() -> List[Dict[str, Any]]:
    """Enumerate all processes using a single NtQuerySystemInformation call.

    Returns a list of dicts with:
        pid: int - process ID
        name: str - process image name
        parent_pid: int - parent process ID
        session_id: int - session ID
        thread_count: int - exact number of threads
        handle_count: int - exact number of open handles
        working_set_bytes: int - physical memory (RSS equivalent)
        user_time_ns: int - user-mode CPU time in nanoseconds
        kernel_time_ns: int - kernel-mode CPU time in nanoseconds
        create_time_ns: int - creation time as Windows FILETIME (100ns since 1601)
        status: str - always "running" (kernel only tracks live processes)
    """
    buf = _query_system_process_information()
    processes = []
    offset = 0

    while True:
        spi = ctypes.cast(
            ctypes.byref(buf, offset),
            ctypes.POINTER(SYSTEM_PROCESS_INFORMATION),
        ).contents

        pid = spi.UniqueProcessId or 0
        parent_pid = spi.InheritedFromUniqueProcessId or 0
        name = spi.ImageName.Buffer if spi.ImageName.Buffer else "System Idle Process"

        processes.append({
            "pid": pid,
            "name": name,
            "parent_pid": parent_pid,
            "session_id": spi.SessionId,
            "thread_count": spi.NumberOfThreads,
            "handle_count": spi.HandleCount,
            "working_set_bytes": spi.WorkingSetSize,
            "user_time_ns": spi.UserTime * 100,       # 100ns units -> nanoseconds
            "kernel_time_ns": spi.KernelTime * 100,    # 100ns units -> nanoseconds
            "create_time_ns": spi.CreateTime,           # Windows FILETIME (100ns since 1601)
            "status": "running",
        })

        if spi.NextEntryOffset == 0:
            break
        offset += spi.NextEntryOffset

    return processes
