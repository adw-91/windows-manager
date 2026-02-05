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
