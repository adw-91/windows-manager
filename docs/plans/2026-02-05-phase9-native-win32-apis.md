# Phase 9: Replace Subprocess Calls with Native Win32 APIs — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate all 56 subprocess/PowerShell/WMIC calls, replacing them with direct Win32 API calls via pywin32, ctypes, winreg, and WMI COM for maximum performance.

**Architecture:** New `src/utils/win32/` package provides reusable helpers (registry, WMI COM, ctypes wrappers, security, GPO). Each existing service/UI file is then rewritten to use these helpers instead of subprocess.

**Tech Stack:** pywin32 (win32service, win32com.client, win32api, win32net, win32security), ctypes (kernel32, userenv), winreg (stdlib), psutil (existing)

---

### Task 1: Create `src/utils/win32/registry.py` — Registry Helpers

**Files:**
- Create: `src/utils/win32/__init__.py`
- Create: `src/utils/win32/registry.py`
- Create: `tests/test_win32_registry.py`

**Step 1: Write the failing test**

```python
# tests/test_win32_registry.py
"""Tests for win32 registry helpers."""
import unittest
import winreg
from src.utils.win32.registry import read_string, read_dword, enumerate_subkeys


class TestRegistry(unittest.TestCase):
    def test_read_string_known_key(self):
        """ProductName always exists in Windows registry."""
        result = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            "ProductName",
        )
        self.assertIsNotNone(result)
        self.assertIn("Windows", result)

    def test_read_string_missing_returns_none(self):
        result = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            "NonExistentValue12345",
        )
        self.assertIsNone(result)

    def test_read_string_bad_path_returns_none(self):
        result = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\NonExistent\Path12345",
            "Anything",
        )
        self.assertIsNone(result)

    def test_read_dword_known_key(self):
        result = read_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            "InstallDate",
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result, int)

    def test_enumerate_subkeys(self):
        """CentralProcessor always has at least one subkey (0)."""
        result = enumerate_subkeys(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor",
        )
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertIn("0", result)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_win32_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.utils.win32'`

**Step 3: Write the implementation**

```python
# src/utils/win32/__init__.py
"""Win32 native API helpers for WinManager."""

# src/utils/win32/registry.py
"""Safe wrappers around winreg with consistent error handling."""
import logging
import winreg
from typing import Optional

logger = logging.getLogger(__name__)


def read_string(root: int, path: str, name: str) -> Optional[str]:
    """Read a REG_SZ or REG_EXPAND_SZ value. Returns None on any failure."""
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_READ)
        try:
            value, reg_type = winreg.QueryValueEx(key, name)
            if reg_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                return str(value) if value else None
            return str(value) if value is not None else None
        finally:
            winreg.CloseKey(key)
    except OSError:
        return None


def read_dword(root: int, path: str, name: str) -> Optional[int]:
    """Read a REG_DWORD value. Returns None on any failure."""
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_READ)
        try:
            value, reg_type = winreg.QueryValueEx(key, name)
            if reg_type == winreg.REG_DWORD:
                return int(value)
            return int(value) if value is not None else None
        finally:
            winreg.CloseKey(key)
    except (OSError, ValueError):
        return None


def read_binary(root: int, path: str, name: str) -> Optional[bytes]:
    """Read a REG_BINARY value. Returns None on any failure."""
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_READ)
        try:
            value, reg_type = winreg.QueryValueEx(key, name)
            if isinstance(value, bytes):
                return value
            return None
        finally:
            winreg.CloseKey(key)
    except OSError:
        return None


def read_qword(root: int, path: str, name: str) -> Optional[int]:
    """Read a REG_QWORD value. Returns None on any failure."""
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, name)
            return int(value) if value is not None else None
        finally:
            winreg.CloseKey(key)
    except (OSError, ValueError):
        return None


def enumerate_subkeys(root: int, path: str) -> list[str]:
    """Enumerate all subkey names under a registry path. Returns empty list on failure."""
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_READ)
        try:
            subkeys = []
            i = 0
            while True:
                try:
                    subkeys.append(winreg.EnumKey(key, i))
                    i += 1
                except OSError:
                    break
            return subkeys
        finally:
            winreg.CloseKey(key)
    except OSError:
        return []
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_win32_registry.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/utils/win32/__init__.py src/utils/win32/registry.py tests/test_win32_registry.py
git commit -m "feat(win32): add registry helper module with read_string, read_dword, enumerate_subkeys"
```

---

### Task 2: Create `src/utils/win32/wmi.py` — WMI COM Helper

**Files:**
- Create: `src/utils/win32/wmi.py`
- Create: `tests/test_win32_wmi.py`

**Step 1: Write the failing test**

```python
# tests/test_win32_wmi.py
"""Tests for win32 WMI COM helper."""
import unittest
from src.utils.win32.wmi import WmiConnection


class TestWmiConnection(unittest.TestCase):
    def test_query_operating_system(self):
        """Win32_OperatingSystem always returns exactly one result."""
        conn = WmiConnection()
        results = conn.query("SELECT Caption FROM Win32_OperatingSystem")
        self.assertEqual(len(results), 1)
        self.assertIn("Caption", results[0])
        self.assertIn("Windows", results[0]["Caption"])

    def test_query_single(self):
        result = WmiConnection().query_single("SELECT Caption FROM Win32_OperatingSystem")
        self.assertIsNotNone(result)
        self.assertIn("Windows", result["Caption"])

    def test_query_single_no_results(self):
        result = WmiConnection().query_single(
            "SELECT Name FROM Win32_SystemDriver WHERE Name = 'NonExistentDriver12345'"
        )
        self.assertIsNone(result)

    def test_query_multiple_results(self):
        """Win32_SystemDriver always returns multiple drivers."""
        conn = WmiConnection()
        results = conn.query("SELECT Name FROM Win32_SystemDriver")
        self.assertGreater(len(results), 10)

    def test_root_wmi_namespace(self):
        """root\\WMI namespace should be accessible."""
        conn = WmiConnection(r"root\WMI")
        # MSAcpi_ThermalZoneTemperature may or may not exist, but connection should succeed
        self.assertIsNotNone(conn)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_win32_wmi.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
# src/utils/win32/wmi.py
"""Thread-safe WMI COM connection wrapper using win32com.client."""
import logging
import pythoncom
import win32com.client
from typing import Any, Optional

logger = logging.getLogger(__name__)


class WmiConnection:
    """WMI COM connection wrapper. Initialize once per thread.

    Uses win32com.client.Dispatch to connect to WMI.
    Handles COM initialization per-thread via pythoncom.CoInitialize.
    """

    def __init__(self, namespace: str = r"root\cimv2"):
        pythoncom.CoInitialize()
        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        self._conn = locator.ConnectServer(".", namespace)

    def query(self, wql: str) -> list[dict[str, Any]]:
        """Execute WQL query, return list of dicts."""
        results = []
        try:
            for obj in self._conn.ExecQuery(wql):
                row = {}
                for prop in obj.Properties_:
                    row[prop.Name] = prop.Value
                results.append(row)
        except Exception as e:
            logger.warning("WMI query failed: %s — %s", wql, e)
        return results

    def query_single(self, wql: str) -> Optional[dict[str, Any]]:
        """Execute WQL query, return first result or None."""
        results = self.query(wql)
        return results[0] if results else None
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_win32_wmi.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/utils/win32/wmi.py tests/test_win32_wmi.py
git commit -m "feat(win32): add WMI COM connection wrapper"
```

---

### Task 3: Create `src/utils/win32/system_info.py` — ctypes System Wrappers

**Files:**
- Create: `src/utils/win32/system_info.py`
- Create: `tests/test_win32_system_info.py`

**Step 1: Write the failing test**

```python
# tests/test_win32_system_info.py
"""Tests for win32 system info ctypes wrappers."""
import unittest
from src.utils.win32.system_info import (
    get_system_locale,
    get_total_physical_memory,
    get_firmware_type,
    is_secure_boot_enabled,
    get_computer_name_ex,
)


class TestSystemInfo(unittest.TestCase):
    def test_get_system_locale(self):
        locale = get_system_locale()
        self.assertIsInstance(locale, str)
        self.assertGreater(len(locale), 0)
        # Locale format is like "en-US"
        self.assertIn("-", locale)

    def test_get_total_physical_memory(self):
        mem = get_total_physical_memory()
        self.assertIsInstance(mem, int)
        # At least 512 MB
        self.assertGreater(mem, 512 * 1024 * 1024)

    def test_get_firmware_type(self):
        fw = get_firmware_type()
        self.assertIn(fw, ("UEFI", "BIOS", "Unknown"))

    def test_is_secure_boot_enabled(self):
        result = is_secure_boot_enabled()
        # Can be True, False, or None (if not UEFI)
        self.assertIn(result, (True, False, None))

    def test_get_computer_name_ex(self):
        # ComputerNameNetBIOS = 0
        name = get_computer_name_ex(0)
        self.assertIsNotNone(name)
        self.assertGreater(len(name), 0)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_win32_system_info.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
# src/utils/win32/system_info.py
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
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_win32_system_info.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/utils/win32/system_info.py tests/test_win32_system_info.py
git commit -m "feat(win32): add system_info ctypes wrappers (locale, memory, firmware, secure boot)"
```

---

### Task 4: Create `src/utils/win32/security.py` — Security Helpers

**Files:**
- Create: `src/utils/win32/security.py`
- Create: `tests/test_win32_security.py`

**Step 1: Write the failing test**

```python
# tests/test_win32_security.py
"""Tests for win32 security helpers."""
import os
import unittest
from src.utils.win32.security import (
    get_current_user_sid,
    is_user_admin,
    get_current_username,
    get_current_domain,
)


class TestSecurity(unittest.TestCase):
    def test_get_current_user_sid(self):
        sid = get_current_user_sid()
        self.assertIsNotNone(sid)
        # SIDs start with S-1-5-
        self.assertTrue(sid.startswith("S-1-5-"), f"SID format unexpected: {sid}")

    def test_is_user_admin(self):
        result = is_user_admin()
        self.assertIsInstance(result, bool)

    def test_get_current_username(self):
        name = get_current_username()
        self.assertIsInstance(name, str)
        self.assertGreater(len(name), 0)
        # Should match environment variable
        self.assertEqual(name, os.environ.get("USERNAME", name))

    def test_get_current_domain(self):
        domain = get_current_domain()
        self.assertIsInstance(domain, str)
        self.assertGreater(len(domain), 0)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_win32_security.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
# src/utils/win32/security.py
"""User identity and privilege checks using Win32 security APIs."""
import ctypes
import logging
import os
from typing import Optional

import win32api
import win32security
import win32process

logger = logging.getLogger(__name__)


def get_current_user_sid() -> Optional[str]:
    """Get current user's SID string via OpenProcessToken + GetTokenInformation."""
    try:
        token = win32security.OpenProcessToken(
            win32process.GetCurrentProcess(),
            win32security.TOKEN_QUERY,
        )
        user_info = win32security.GetTokenInformation(token, win32security.TokenUser)
        sid = user_info[0]
        return win32security.ConvertSidToStringSid(sid)
    except Exception as e:
        logger.warning("Failed to get user SID: %s", e)
        return None


def is_user_admin() -> bool:
    """Check if current user has admin privileges via shell32.IsUserAnAdmin."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def get_current_username() -> str:
    """Get current username via Win32 API, falling back to env var."""
    try:
        return win32api.GetUserName()
    except Exception:
        return os.environ.get("USERNAME", "Unknown")


def get_current_domain() -> str:
    """Get current user's domain via environment variable."""
    return os.environ.get("USERDOMAIN", "Unknown")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_win32_security.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/utils/win32/security.py tests/test_win32_security.py
git commit -m "feat(win32): add security helpers (SID, admin check, username, domain)"
```

---

### Task 5: Create `src/utils/win32/gpo.py` — Group Policy Enumeration

**Files:**
- Create: `src/utils/win32/gpo.py`
- Create: `tests/test_win32_gpo.py`

**Step 1: Write the failing test**

```python
# tests/test_win32_gpo.py
"""Tests for win32 GPO enumeration."""
import unittest
from src.utils.win32.gpo import get_applied_gpos


class TestGpo(unittest.TestCase):
    def test_get_machine_gpos_returns_list(self):
        """Machine GPO list should always be a list (may be empty on non-domain machines)."""
        result = get_applied_gpos(machine=True)
        self.assertIsInstance(result, list)

    def test_get_user_gpos_returns_list(self):
        result = get_applied_gpos(machine=False)
        self.assertIsInstance(result, list)

    def test_gpo_names_are_strings(self):
        for gpo in get_applied_gpos(machine=True):
            self.assertIsInstance(gpo, str)
            self.assertGreater(len(gpo), 0)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_win32_gpo.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Uses `GetAppliedGPOListW` from `userenv.dll` via ctypes. Defines the `GROUP_POLICY_OBJECTW` linked-list struct and walks it to extract `lpDisplayName`.

```python
# src/utils/win32/gpo.py
"""Group Policy enumeration via GetAppliedGPOListW from userenv.dll."""
import ctypes
import ctypes.wintypes
import logging
from typing import List

logger = logging.getLogger(__name__)

userenv = ctypes.windll.userenv


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.wintypes.DWORD),
        ("Data2", ctypes.wintypes.WORD),
        ("Data3", ctypes.wintypes.WORD),
        ("Data4", ctypes.c_byte * 8),
    ]


class GROUP_POLICY_OBJECTW(ctypes.Structure):
    """Linked list node for applied GPOs."""
    pass


GROUP_POLICY_OBJECTW._fields_ = [
    ("dwOptions", ctypes.wintypes.DWORD),
    ("dwVersion", ctypes.wintypes.DWORD),
    ("lpDSPath", ctypes.wintypes.LPWSTR),
    ("lpFileSysPath", ctypes.wintypes.LPWSTR),
    ("lpDisplayName", ctypes.wintypes.LPWSTR),
    ("szGPOName", ctypes.c_wchar * 50),
    ("GPOLink", ctypes.wintypes.DWORD),  # enum GPO_LINK
    ("lParam", ctypes.wintypes.LPARAM),
    ("pNext", ctypes.POINTER(GROUP_POLICY_OBJECTW)),
    ("pPrev", ctypes.POINTER(GROUP_POLICY_OBJECTW)),
    ("lpExtensions", ctypes.wintypes.LPWSTR),
    ("lParam2", ctypes.wintypes.LPARAM),
    ("lpLink", ctypes.wintypes.LPWSTR),
]

# GUID for "Registry" extension — required parameter for GetAppliedGPOListW
# {35378EAC-683F-11D2-A89A-00C04FBBCFA2}
REGISTRY_EXTENSION_GUID = GUID(
    0x35378EAC, 0x683F, 0x11D2,
    (ctypes.c_byte * 8)(0xA8, 0x9A, 0x00, 0xC0, 0x4F, 0xBB, 0xCF, 0xA2),
)

# GetAppliedGPOListW(dwFlags, pMachineName, pSidUser, pGuidExtension, ppGPOList)
userenv.GetAppliedGPOListW.argtypes = [
    ctypes.wintypes.DWORD,
    ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.LPCWSTR,
    ctypes.POINTER(GUID),
    ctypes.POINTER(ctypes.POINTER(GROUP_POLICY_OBJECTW)),
]
userenv.GetAppliedGPOListW.restype = ctypes.wintypes.DWORD

userenv.FreeGPOListW.argtypes = [ctypes.POINTER(GROUP_POLICY_OBJECTW)]
userenv.FreeGPOListW.restype = ctypes.wintypes.BOOL


def get_applied_gpos(machine: bool = True) -> List[str]:
    """Return display names of applied GPOs for machine or user scope.

    Args:
        machine: If True, get machine policies. If False, get user policies.

    Returns:
        List of GPO display name strings. Empty list if none applied or on error.
    """
    # dwFlags: 1 = GPO_LIST_FLAG_MACHINE, 0 = user
    flags = 1 if machine else 0
    gpo_list = ctypes.POINTER(GROUP_POLICY_OBJECTW)()
    guid = GUID(
        0x35378EAC, 0x683F, 0x11D2,
        (ctypes.c_byte * 8)(0xA8, 0x9A, 0x00, 0xC0, 0x4F, 0xBB, 0xCF, 0xA2),
    )

    try:
        result = userenv.GetAppliedGPOListW(
            flags,
            None,  # local machine
            None,  # current user SID
            ctypes.byref(guid),
            ctypes.byref(gpo_list),
        )

        if result != 0:
            logger.debug("GetAppliedGPOListW returned %d for machine=%s", result, machine)
            return []

        names = []
        current = gpo_list
        while current:
            try:
                obj = current.contents
                if obj.lpDisplayName:
                    name = obj.lpDisplayName
                    if name and name not in names:
                        names.append(name)
                current = obj.pNext
            except ValueError:
                # Null pointer dereference at end of list
                break

        # Free the list
        if gpo_list:
            userenv.FreeGPOListW(gpo_list)

        return names

    except Exception as e:
        logger.warning("Failed to enumerate GPOs (machine=%s): %s", machine, e)
        return []
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_win32_gpo.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/utils/win32/gpo.py tests/test_win32_gpo.py
git commit -m "feat(win32): add GPO enumeration via GetAppliedGPOListW ctypes"
```

---

### Task 6: Update `src/utils/win32/__init__.py` — Re-exports

**Files:**
- Modify: `src/utils/win32/__init__.py`

**Step 1: Write the re-exports**

```python
# src/utils/win32/__init__.py
"""Win32 native API helpers for WinManager.

Submodules:
    registry   - Safe winreg wrappers
    wmi        - WMI COM connection wrapper
    system_info - ctypes wrappers (locale, memory, firmware)
    security   - Token, SID, admin check helpers
    gpo        - Group Policy enumeration
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
```

**Step 2: Verify imports work**

Run: `python -c "from src.utils.win32 import read_string, WmiConnection, get_system_locale, get_current_user_sid, get_applied_gpos; print('All imports OK')"`
Expected: `All imports OK`

**Step 3: Commit**

```bash
git add src/utils/win32/__init__.py
git commit -m "feat(win32): add convenience re-exports in __init__.py"
```

---

### Task 7: Migrate `src/services/service_info.py` — SCM API

**Files:**
- Modify: `src/services/service_info.py` (rewrite entirely, 263 lines)
- Create: `tests/test_win32_services.py`

**Step 1: Write the failing test**

```python
# tests/test_win32_services.py
"""Tests for service_info using win32service API."""
import unittest
from src.services.service_info import ServiceInfo


class TestServiceInfo(unittest.TestCase):
    def test_get_all_services(self):
        svc = ServiceInfo()
        services = svc.get_all_services()
        self.assertIsInstance(services, list)
        self.assertGreater(len(services), 50)  # Windows has 100+ services

    def test_service_dict_keys(self):
        svc = ServiceInfo()
        services = svc.get_all_services()
        if services:
            s = services[0]
            for key in ("Name", "DisplayName", "Status", "StartMode", "PathName", "Description"):
                self.assertIn(key, s, f"Missing key: {key}")

    def test_get_service_info_existing(self):
        """'Spooler' service exists on all Windows machines."""
        svc = ServiceInfo()
        info = svc.get_service_info("Spooler")
        self.assertIsNotNone(info)
        self.assertEqual(info["Name"], "Spooler")
        self.assertIn(info["Status"], ("Running", "Stopped", "Start Pending", "Stop Pending",
                                        "Continue Pending", "Pause Pending", "Paused", "Unknown"))

    def test_get_service_info_nonexistent(self):
        svc = ServiceInfo()
        info = svc.get_service_info("NonExistentService12345")
        self.assertIsNone(info)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify baseline (old code)**

Run: `python -m pytest tests/test_win32_services.py -v`
Expected: Tests pass but slowly (wmic subprocess calls)

**Step 3: Rewrite `service_info.py` using `win32service`**

Replace the entire file. Key changes:
- `get_all_services()`: Use `win32service.EnumServicesStatusEx()` — returns list of tuples `(name, display_name, (svc_type, state, ...))`. Open SCM with `OpenSCManager`, then `EnumServicesStatusEx`. For each service, optionally call `QueryServiceConfig` + `QueryServiceConfig2` for description and path.
- `get_service_info(name)`: Use `OpenService` + `QueryServiceStatus` + `QueryServiceConfig` + `QueryServiceConfig2`
- `start_service(name)`: `win32service.StartService(handle, None)`
- `stop_service(name)`: `win32service.ControlService(handle, win32service.SERVICE_CONTROL_STOP)`
- `restart_service(name)`: stop + 0.5s sleep + start
- Remove `subprocess` import entirely
- Keep `_normalize_service()` signature compatibility (return dict with same keys)
- Map `win32service` state constants (1=Stopped, 2=StartPending, 3=StopPending, 4=Running, 5=ContinuePending, 6=PausePending, 7=Paused) to existing `ServiceStatus` enum strings
- Map start type constants to `ServiceStartMode` enum strings

Reference: `windows-manager-rust/crates/wm/src/services.rs` uses identical API pattern

**Step 4: Run tests to verify**

Run: `python -m pytest tests/test_win32_services.py -v`
Expected: All 4 tests PASS (significantly faster than before)

**Step 5: Commit**

```bash
git add src/services/service_info.py tests/test_win32_services.py
git commit -m "feat: migrate service_info.py from wmic/net to win32service API"
```

---

### Task 8: Migrate `src/services/windows_info.py` — Registry + ctypes

**Files:**
- Modify: `src/services/windows_info.py` (267 lines)
- Create: `tests/test_win32_windows_info.py`

**Step 1: Write the failing test**

```python
# tests/test_win32_windows_info.py
"""Tests for WindowsInfo using native APIs."""
import unittest
from src.services.windows_info import WindowsInfo


class TestWindowsInfo(unittest.TestCase):
    def setUp(self):
        self.info = WindowsInfo()

    def test_get_processor(self):
        proc = self.info.get_processor()
        self.assertIsInstance(proc, str)
        self.assertNotEqual(proc, "Unknown")

    def test_get_memory_info(self):
        mem = self.info.get_memory_info()
        self.assertIn("total_gb", mem)
        self.assertIn("formatted", mem)
        self.assertGreater(mem["total_gb"], 0)

    def test_get_manufacturer(self):
        mfr = self.info.get_manufacturer()
        self.assertIsInstance(mfr, str)
        # Should not be empty or "Unknown" on real hardware
        self.assertGreater(len(mfr), 0)

    def test_get_model(self):
        model = self.info.get_model()
        self.assertIsInstance(model, str)

    def test_get_bios_version(self):
        bios = self.info.get_bios_version()
        self.assertIsInstance(bios, str)

    def test_get_system_locale(self):
        locale = self.info.get_system_locale()
        self.assertIsInstance(locale, str)
        self.assertIn("-", locale)

    def test_get_domain_workgroup(self):
        domain = self.info.get_domain_workgroup()
        self.assertIsInstance(domain, str)
        self.assertGreater(len(domain), 0)

    def test_get_all_system_info(self):
        """Smoke test — all fields should return strings."""
        info = self.info.get_all_system_info()
        self.assertIsInstance(info, dict)
        self.assertGreater(len(info), 5)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify baseline**

Run: `python -m pytest tests/test_win32_windows_info.py -v`

**Step 3: Rewrite methods in `windows_info.py`**

Replace each method's subprocess call:

| Method | Old | New |
|--------|-----|-----|
| `get_processor()` | `wmic cpu get name` | `registry.read_string(HKLM, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")` |
| `_get_memory_stick_capacities()` | `wmic memorychip get capacity` | `get_total_physical_memory()` from system_info (for total); for per-stick, use WMI COM `Win32_PhysicalMemory` only if per-stick count matters |
| `get_domain_workgroup()` | `wmic computersystem get domain` | `win32net.NetGetJoinInformation(None)` returns `(name, status)` |
| `get_manufacturer()` | `wmic computersystem get manufacturer` | `registry.read_string(HKLM, r"SYSTEM\CurrentControlSet\Control\SystemInformation", "SystemManufacturer")` |
| `get_model()` | `wmic computersystem get model` | `registry.read_string(HKLM, ..., "SystemProductName")` |
| `get_bios_version()` | `wmic bios get smbiosbiosversion` | `registry.read_string(HKLM, r"HARDWARE\DESCRIPTION\System\BIOS", "BIOSVersion")` |
| `get_system_locale()` | `powershell Get-WinSystemLocale` | `system_info.get_system_locale()` |
| `get_timezone()` | `tzutil /g` | Keep `tzutil` — it's a fast native tool, OR use `time.tzname[0]` directly |

Remove `subprocess` import. Add:
```python
import winreg
import win32net
from src.utils.win32 import read_string, get_system_locale as _get_locale, get_total_physical_memory
```

For `get_timezone()`: Replace subprocess with pure Python `time.tzname[0]` or `datetime.datetime.now().astimezone().tzname()`. No native API needed.

**Step 4: Run tests**

Run: `python -m pytest tests/test_win32_windows_info.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/services/windows_info.py tests/test_win32_windows_info.py
git commit -m "feat: migrate windows_info.py from wmic/powershell to registry+ctypes"
```

---

### Task 9: Migrate `src/ui/system_tab.py` — Remove `_run_wmic`/`_run_powershell`

**Files:**
- Modify: `src/ui/system_tab.py:316-504` (the `_collect_all_info`, `_run_wmic`, `_run_powershell` methods)

**Step 1: Write the failing test**

```python
# tests/test_system_tab_data.py
"""Tests for SystemTab data collection (no UI, just the worker function)."""
import unittest
from src.ui.system_tab import SystemTab


class TestSystemTabData(unittest.TestCase):
    def test_collect_all_info_returns_all_sections(self):
        tab = SystemTab.__new__(SystemTab)  # Skip __init__ (needs Qt)
        tab._windows_info = __import__("src.services.windows_info", fromlist=["WindowsInfo"]).WindowsInfo()
        data = tab._collect_all_info()
        expected_sections = {"System Summary", "Hardware", "Components", "Software", "Security", "Network"}
        self.assertEqual(set(data.keys()), expected_sections)

    def test_system_summary_has_key_fields(self):
        tab = SystemTab.__new__(SystemTab)
        tab._windows_info = __import__("src.services.windows_info", fromlist=["WindowsInfo"]).WindowsInfo()
        summary = tab._get_system_summary()
        self.assertIn("Computer Name", summary)
        self.assertIn("Processor", summary)
        self.assertIn("RAM", summary)

    def test_components_has_display(self):
        tab = SystemTab.__new__(SystemTab)
        tab._windows_info = __import__("src.services.windows_info", fromlist=["WindowsInfo"]).WindowsInfo()
        components = tab._get_components()
        self.assertIn("Display", components)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify baseline**

Run: `python -m pytest tests/test_system_tab_data.py -v`

**Step 3: Replace `_run_wmic` and `_run_powershell` callsites**

In `system_tab.py`, replace each `self._run_wmic(...)` and `self._run_powershell(...)` call with the equivalent from `src/utils/win32/`:

| Callsite (method:line) | Old | New |
|------------------------|-----|-----|
| `_get_system_summary:334` | `_run_wmic("computersystem", "Manufacturer")` | `read_string(HKLM, r"SYSTEM\...\SystemInformation", "SystemManufacturer") or "Unknown"` |
| `_get_system_summary:335` | `_run_wmic("computersystem", "Model")` | `read_string(HKLM, ..., "SystemProductName") or "Unknown"` |
| `_get_system_summary:337` | `_run_wmic("cpu", "Name")` | `read_string(HKLM, r"HARDWARE\...\CentralProcessor\0", "ProcessorNameString") or "Unknown"` |
| `_get_hardware_resources:372` | `_run_wmic("bios", "SMBIOSBIOSVersion")` | `read_string(HKLM, r"HARDWARE\...\BIOS", "BIOSVersion") or "Unknown"` |
| `_get_hardware_resources:373` | `_run_wmic("baseboard", "Manufacturer")` + `_run_wmic("baseboard", "Product")` | `read_string(HKLM, r"HARDWARE\...\BIOS", "BaseBoardManufacturer")` + `read_string(..., "BaseBoardProduct")` |
| `_get_components:383` | `_run_wmic("path win32_videocontroller", "Name")` | `read_string(HKLM, r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000", "DriverDesc") or "Unknown"` |
| `_get_components:385` | `_run_wmic("path win32_videocontroller", "AdapterRAM")` | `registry.read_qword(HKLM, ..., "HardwareInformation.qwMemorySize")` or `read_binary` + unpack |
| `_get_components:389` | `_run_wmic("sounddev", "Name")` | Enumerate `{4d36e96c-e325-11ce-bfc1-08002be10318}` subkeys for first `DriverDesc` |
| `_get_components:398` | `_run_wmic("cdrom", "Name")` | `read_string(HKLM, r"SYSTEM\CurrentControlSet\Services\cdrom\Enum", "0")` or "None" |
| `_get_security_info:442` | `_run_powershell("Confirm-SecureBootUEFI")` | `is_secure_boot_enabled()` from system_info |

Then **delete** `_run_wmic` (lines 482-493) and `_run_powershell` (lines 495-504). Remove `subprocess` import.

Add imports at top:
```python
import winreg
from src.utils.win32 import read_string, read_qword, read_binary, enumerate_subkeys, is_secure_boot_enabled
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_system_tab_data.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ui/system_tab.py tests/test_system_tab_data.py
git commit -m "feat: migrate system_tab.py from wmic/powershell to registry+ctypes"
```

---

### Task 10: Migrate `src/services/driver_info.py` — WMI COM

**Files:**
- Modify: `src/services/driver_info.py` (240 lines → ~60 lines)

**Step 1: Write the failing test**

```python
# tests/test_win32_driver_info.py
"""Tests for DriverInfo using WMI COM."""
import unittest
from src.services.driver_info import DriverInfo


class TestDriverInfo(unittest.TestCase):
    def test_get_all_drivers(self):
        info = DriverInfo()
        drivers = info.get_all_drivers()
        self.assertIsInstance(drivers, list)
        self.assertGreater(len(drivers), 10)

    def test_driver_dict_keys(self):
        info = DriverInfo()
        drivers = info.get_all_drivers()
        if drivers:
            d = drivers[0]
            for key in ("Name", "DisplayName", "State", "StartMode"):
                self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify baseline**

Run: `python -m pytest tests/test_win32_driver_info.py -v`

**Step 3: Rewrite `driver_info.py`**

Replace entire file. Use `WmiConnection().query("SELECT Name, DisplayName, PathName, State, StartMode, Description FROM Win32_SystemDriver")`.

Delete:
- `_parse_csv_output` method
- `_parse_csv_line` method
- `_query_drivers_fallback` method
- `_parse_pipe_delimited_output` method
- `subprocess` import

The new `get_all_drivers()` is ~15 lines.

**Step 4: Run tests**

Run: `python -m pytest tests/test_win32_driver_info.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/services/driver_info.py tests/test_win32_driver_info.py
git commit -m "feat: migrate driver_info.py from powershell to WMI COM"
```

---

### Task 11: Migrate `src/services/task_scheduler_info.py` — Task Scheduler 2.0 COM

**Files:**
- Modify: `src/services/task_scheduler_info.py` (312 lines → ~200 lines)
- Create: `tests/test_win32_task_scheduler.py`

**Step 1: Write the failing test**

```python
# tests/test_win32_task_scheduler.py
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
```

**Step 2: Run test to verify baseline**

Run: `python -m pytest tests/test_win32_task_scheduler.py -v`

**Step 3: Rewrite `task_scheduler_info.py`**

Use `win32com.client.Dispatch('Schedule.Service')` COM interface.

Key mapping (from Rust `tasks.rs` reference):
- `get_all_tasks()`: Connect to `Schedule.Service`, get root folder, recursively enumerate tasks via `GetTasks()` and `GetFolders()`. Each `IRegisteredTask` has: `.Name`, `.Path`, `.State`, `.LastRunTime`, `.NextRunTime`, `.LastTaskResult`, `.Enabled`, `.Definition.RegistrationInfo.Author`
- Task state mapping: 1=Disabled, 2=Queued, 3=Ready, 4=Running
- `run_task(path)`: `root.GetTask(path).Run(None)`
- `enable_task(path)`: `root.GetTask(path).Enabled = True`
- `disable_task(path)`: `root.GetTask(path).Enabled = False`
- `end_task(path)`: `root.GetTask(path).Stop(0)`
- `delete_task(path)`: Find folder, `folder.DeleteTask(name, 0)`
- `create_task(...)`: `folder.RegisterTaskDefinition(...)` — this one is complex; keep `schtasks` subprocess as fallback for create only if COM registration is too complex

Delete: `_parse_csv_line`, `_get_col`, `subprocess` import

Important: COM calls need `pythoncom.CoInitialize()` at start of each method that might run on a worker thread.

**Step 4: Run tests**

Run: `python -m pytest tests/test_win32_task_scheduler.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/services/task_scheduler_info.py tests/test_win32_task_scheduler.py
git commit -m "feat: migrate task_scheduler_info.py from schtasks to COM"
```

---

### Task 12: Migrate `src/services/enterprise_info.py` — Mixed Win32 APIs

**Files:**
- Modify: `src/services/enterprise_info.py` (432 lines)
- Create: `tests/test_win32_enterprise_info.py`

**Step 1: Write the failing test**

```python
# tests/test_win32_enterprise_info.py
"""Tests for EnterpriseInfo using native APIs."""
import unittest
from src.services.enterprise_info import EnterpriseInfo


class TestEnterpriseInfo(unittest.TestCase):
    def test_get_domain_info(self):
        info = EnterpriseInfo()
        domain = info.get_domain_info()
        self.assertIn("domain_name", domain)
        self.assertIn("is_domain_joined", domain)
        self.assertIsInstance(domain["is_domain_joined"], bool)

    def test_get_computer_info(self):
        info = EnterpriseInfo()
        comp = info.get_computer_info()
        self.assertIn("computer_name", comp)
        self.assertGreater(len(comp["computer_name"]), 0)

    def test_get_current_user(self):
        info = EnterpriseInfo()
        user = info.get_current_user()
        self.assertIn("username", user)
        self.assertIn("sid", user)
        self.assertIn("is_admin", user)
        self.assertNotEqual(user["username"], "Unknown")
        # SID should start with S-1-5-
        self.assertTrue(user["sid"].startswith("S-"), f"Unexpected SID: {user['sid']}")

    def test_get_network_info(self):
        info = EnterpriseInfo()
        net = info.get_network_info()
        self.assertIn("primary_ip", net)

    def test_get_azure_ad_info(self):
        info = EnterpriseInfo()
        aad = info.get_azure_ad_info()
        self.assertIn("is_azure_ad_joined", aad)
        self.assertIsInstance(aad["is_azure_ad_joined"], bool)

    def test_get_group_policy_info(self):
        info = EnterpriseInfo()
        gp = info.get_group_policy_info()
        self.assertIn("gpos_applied", gp)
        self.assertIn("computer_policies", gp)
        self.assertIn("user_policies", gp)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify baseline**

Run: `python -m pytest tests/test_win32_enterprise_info.py -v`

**Step 3: Rewrite each method**

| Method | Old | New |
|--------|-----|-----|
| `get_domain_info()` | `wmic computersystem get domain,partofdomainbynet` | `win32net.NetGetJoinInformation(None)` returns `(name, join_status)`. `join_status == 3` means domain-joined |
| `get_computer_info()` | `wmic computersystem get name,workgroup,partofdomainbynet` | `win32api.GetComputerName()` + `win32net.NetGetJoinInformation(None)` |
| `get_current_user()` | 2x PowerShell (SID + admin) | `security.get_current_user_sid()`, `security.is_user_admin()`, env vars for username/domain |
| `get_network_info()` | 3x PowerShell (IP, DNS, IPv6) | `psutil.net_if_addrs()` + `psutil.net_if_stats()` for primary IP/adapter. DNS: `socket.getaddrinfo()` or `Win32_NetworkAdapterConfiguration` WMI for DNS servers |
| `get_azure_ad_info()` | `dsregcmd /status` subprocess | Registry: `HKLM\SYSTEM\CurrentControlSet\Control\CloudDomainJoin\JoinInfo` — enumerate subkeys for TenantId, etc. Fall back to `dsregcmd` if registry keys not found |
| `get_group_policy_info()` | 2x `gpresult /scope:...` | `gpo.get_applied_gpos(machine=True)` + `gpo.get_applied_gpos(machine=False)` |
| `_get_domain_controller()` | PowerShell AD query | `win32net.NetGetDCName(None, None)` — returns DC name or raises error |

Remove `subprocess` import. Add imports:
```python
import win32api
import win32net
from src.utils.win32 import get_current_user_sid, is_user_admin, get_applied_gpos, get_computer_name_ex
from src.utils.win32.registry import read_string, enumerate_subkeys
from src.utils.win32.wmi import WmiConnection
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_win32_enterprise_info.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/services/enterprise_info.py tests/test_win32_enterprise_info.py
git commit -m "feat: migrate enterprise_info.py from subprocess to win32 APIs"
```

---

### Task 13: Migrate `src/ui/widgets/battery_widget.py` — psutil + WMI COM

**Files:**
- Modify: `src/ui/widgets/battery_widget.py:203-493` (worker methods)

**Step 1: Write the failing test**

```python
# tests/test_battery_data.py
"""Tests for battery data collection (no UI)."""
import unittest
from src.ui.widgets.battery_widget import BatteryWidget


class TestBatteryData(unittest.TestCase):
    def test_collect_battery_info(self):
        """Smoke test — should not crash even without battery."""
        widget = BatteryWidget.__new__(BatteryWidget)
        widget._worker = None
        widget._detailed_info = {}
        data = widget._collect_battery_info()
        self.assertIsInstance(data, dict)
        self.assertIn("status", data)
        self.assertIn("power_plan", data)

    def test_collect_detailed_info(self):
        widget = BatteryWidget.__new__(BatteryWidget)
        widget._worker = None
        widget._detailed_info = {}
        data = widget._collect_detailed_info()
        self.assertIsInstance(data, dict)
        self.assertIn("manufacturer", data)
        self.assertIn("chemistry", data)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify baseline**

Run: `python -m pytest tests/test_battery_data.py -v`

**Step 3: Replace PowerShell calls**

| Old | New |
|-----|-----|
| `powercfg /getactivescheme` | Keep this one — it's fast and there's no clean API alternative. OR use `win32api.GetSystemPowerStatus()` for basics and registry `HKLM\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes\ActivePowerScheme` for plan GUID, then look up name from subkey |
| `_run_powershell(Win32_Battery ...)` | `psutil.sensors_battery()` for percent/plugged, `WmiConnection().query("SELECT ... FROM Win32_Battery")` for chemistry/design capacity/voltage |
| `_run_powershell(BatteryStaticData ...)` | `WmiConnection(r"root\WMI").query("SELECT DesignedCapacity, ManufactureName, SerialNumber, UniqueID FROM BatteryStaticData")` |
| `_run_powershell(BatteryFullChargedCapacity ...)` | `WmiConnection(r"root\WMI").query("SELECT FullChargedCapacity FROM BatteryFullChargedCapacity")` |
| `_run_powershell(BatteryCycleCount ...)` | `WmiConnection(r"root\WMI").query("SELECT CycleCount FROM BatteryCycleCount")` |
| `_run_powershell(BatteryStatus ...)` | `WmiConnection(r"root\WMI").query("SELECT Voltage FROM BatteryStatus")` |
| `_run_powershell(Win32_Battery.Name)` | Already covered by the Win32_Battery WMI query above |

Delete `_run_powershell` method. Remove `subprocess` import (keep `os`, `tempfile`, `xml` only if still used — check if they're actually used).

For `_collect_battery_info()`: Replace `powercfg` with registry read:
```python
import winreg
from src.utils.win32.registry import read_string

# Active power scheme GUID
guid = read_string(winreg.HKEY_LOCAL_MACHINE,
    r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes",
    "ActivePowerScheme")
if guid:
    name = read_string(winreg.HKEY_LOCAL_MACHINE,
        rf"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes\{guid}",
        "FriendlyName")
    # FriendlyName is like "@%SystemRoot%\system32\powrprof.dll,-1" or a plain string
    if name and not name.startswith("@"):
        result["power_plan"] = name
```

For `_collect_detailed_info()`: Single WMI connection reuse pattern:
```python
from src.utils.win32.wmi import WmiConnection

# Standard namespace
cimv2 = WmiConnection()
battery = cimv2.query_single("SELECT Name, DeviceID, DesignCapacity, DesignVoltage, Chemistry FROM Win32_Battery")

# root\WMI namespace
try:
    wmi_ns = WmiConnection(r"root\WMI")
    static = wmi_ns.query_single("SELECT DesignedCapacity, ManufactureName FROM BatteryStaticData")
    full = wmi_ns.query_single("SELECT FullChargedCapacity FROM BatteryFullChargedCapacity")
    cycle = wmi_ns.query_single("SELECT CycleCount FROM BatteryCycleCount")
    status = wmi_ns.query_single("SELECT Voltage FROM BatteryStatus")
except Exception:
    pass
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_battery_data.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ui/widgets/battery_widget.py tests/test_battery_data.py
git commit -m "feat: migrate battery_widget.py from powershell to WMI COM + registry"
```

---

### Task 14: Final Verification — No Remaining Subprocess Calls

**Files:**
- No changes (verification only)

**Step 1: Grep for remaining subprocess usage**

Run: `grep -rn "subprocess" src/ --include="*.py"`

Expected output should ONLY show:
- `src/ui/widgets/software_table.py` — `subprocess.Popen(['explorer', ...])` (legitimate)
- `src/ui/widgets/startup_table.py` — `subprocess.Popen(['explorer', ...])` (legitimate)

If any other files show up, they need to be fixed.

**Step 2: Grep for remaining wmic/powershell**

Run: `grep -rn "wmic\|powershell\|schtasks\|gpresult\|dsregcmd\|net start\|net stop" src/ --include="*.py"`

Expected: No matches (or only in comments)

**Step 3: Run ALL tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

**Step 4: Manual smoke test**

Run: `python -m src.main` (or however the app is launched)
Verify: All tabs load, data displays, no errors in console

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: verify no subprocess calls remain (Phase 9 complete)"
```

---

### Task 15: Update Documentation

**Files:**
- Modify: `docs/PROJECT_OVERVIEW.md` — Update architecture section
- Modify: `CLAUDE.md` — Update conventions to reflect new win32 package

**Step 1: Update PROJECT_OVERVIEW.md**

Add section about `src/utils/win32/` package. Remove references to "PowerShell CIM queries" and "WMIC where possible" from conventions.

**Step 2: Update CLAUDE.md**

Replace:
```
- Use PowerShell CIM queries instead of WMIC where possible (more reliable)
```
With:
```
- Use native Win32 APIs via `src/utils/win32/` package (registry, WMI COM, ctypes) — no subprocess calls for data gathering
```

**Step 3: Commit**

```bash
git add docs/PROJECT_OVERVIEW.md CLAUDE.md
git commit -m "docs: update documentation for Phase 9 native Win32 APIs"
```
