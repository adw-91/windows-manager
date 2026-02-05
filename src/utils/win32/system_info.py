"""Direct kernel32/user32 ctypes calls for system information."""
import ctypes
import ctypes.wintypes
import logging
import winreg
from typing import Optional

from src.utils.win32.registry import read_dword

logger = logging.getLogger(__name__)

kernel32 = ctypes.windll.kernel32


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.wintypes.DWORD),
        ("dwMemoryLoad", ctypes.wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


def get_system_locale() -> str:
    """Get system default locale name via GetSystemDefaultLocaleName."""
    buf = ctypes.create_unicode_buffer(85)
    ret = kernel32.GetSystemDefaultLocaleName(buf, 85)
    if ret > 0:
        return buf.value
    return "en-US"


def get_total_physical_memory() -> int:
    """Get total physical memory in bytes via GlobalMemoryStatusEx."""
    mem = MEMORYSTATUSEX()
    mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
    return mem.ullTotalPhys


def get_firmware_type() -> str:
    """Get firmware type ('UEFI' or 'BIOS') via GetFirmwareType."""
    fw_type = ctypes.wintypes.DWORD(0)
    try:
        if kernel32.GetFirmwareType(ctypes.byref(fw_type)):
            # 1 = BIOS, 2 = UEFI
            if fw_type.value == 2:
                return "UEFI"
            elif fw_type.value == 1:
                return "BIOS"
    except Exception:
        pass
    return "Unknown"


def is_secure_boot_enabled() -> Optional[bool]:
    """Check Secure Boot status via registry. Returns None if not applicable."""
    val = read_dword(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\SecureBoot\State",
        "UEFISecureBootEnabled",
    )
    if val is not None:
        return val == 1
    return None


def get_computer_name_ex(fmt: int) -> Optional[str]:
    """Get computer name in specified format via GetComputerNameExW.

    fmt values: 0=NetBIOS, 1=DnsHostname, 2=DnsDomain, 3=DnsFullyQualified
    """
    size = ctypes.wintypes.DWORD(0)
    kernel32.GetComputerNameExW(fmt, None, ctypes.byref(size))
    if size.value == 0:
        return None
    buf = ctypes.create_unicode_buffer(size.value)
    if kernel32.GetComputerNameExW(fmt, buf, ctypes.byref(size)):
        return buf.value
    return None
