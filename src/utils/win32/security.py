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
