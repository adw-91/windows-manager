"""Win32 native API helpers for WinManager.

Submodules:
    registry   - Safe winreg wrappers
    wmi        - WMI COM connection wrapper
    system_info - ctypes wrappers (locale, memory, firmware)
    security   - Token, SID, admin check helpers
    gpo        - Group Policy enumeration
    process_info - Native process enumeration via NtQuerySystemInformation
"""
from src.utils.win32.registry import read_string, read_dword, read_binary, read_qword, enumerate_subkeys
from src.utils.win32.wmi import WmiConnection
from src.utils.win32.system_info import (
    get_system_locale,
    get_total_physical_memory,
    get_firmware_type,
    is_secure_boot_enabled,
    get_computer_name_ex,
)
from src.utils.win32.security import (
    get_current_user_sid,
    is_user_admin,
    get_current_username,
    get_current_domain,
)
from src.utils.win32.gpo import get_applied_gpos
from src.utils.win32.process_info import enumerate_processes
from src.utils.win32.cert import get_cert_subject_cn
