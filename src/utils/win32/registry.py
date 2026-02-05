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
