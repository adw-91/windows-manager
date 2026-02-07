"""Native device enumeration via SetupAPI and CfgMgr32.

Uses SetupDiGetClassDevsW to enumerate all present PnP devices — the same
API that Device Manager uses. Near-instant (~50ms for ~200 devices) compared
to WMI Win32_PnPEntity which takes 2-5 seconds.
"""
import ctypes
from ctypes import wintypes
from typing import List, Dict, Any

# DLL references
setupapi = ctypes.windll.setupapi
cfgmgr32 = ctypes.windll.CfgMgr32

# ── Constants ─────────────────────────────────────────────────────────

DIGCF_PRESENT = 0x02
DIGCF_ALLCLASSES = 0x04

# SPDRP_* property codes for SetupDiGetDeviceRegistryPropertyW
SPDRP_DEVICEDESC = 0x00
SPDRP_HARDWAREID = 0x01
SPDRP_SERVICE = 0x04
SPDRP_CLASS = 0x07
SPDRP_CLASSGUID = 0x08
SPDRP_DRIVER = 0x09
SPDRP_MFG = 0x0B
SPDRP_FRIENDLYNAME = 0x0C
SPDRP_LOCATION_INFORMATION = 0x0D
SPDRP_ENUMERATOR_NAME = 0x16

# DN_HAS_PROBLEM flag from cfg.h
DN_HAS_PROBLEM = 0x00000400

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# REG_SZ = 1, REG_MULTI_SZ = 7
REG_SZ = 1
REG_MULTI_SZ = 7


# ── Structures ────────────────────────────────────────────────────────

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]


# ── Function signatures ──────────────────────────────────────────────

# SetupDiGetClassDevsW
setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID),  # ClassGuid (NULL for all)
    wintypes.LPCWSTR,      # Enumerator
    wintypes.HWND,         # hwndParent
    wintypes.DWORD,        # Flags
]
setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p

# SetupDiEnumDeviceInfo
setupapi.SetupDiEnumDeviceInfo.argtypes = [
    ctypes.c_void_p,                  # DeviceInfoSet
    wintypes.DWORD,                   # MemberIndex
    ctypes.POINTER(SP_DEVINFO_DATA),  # DeviceInfoData
]
setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL

# SetupDiGetDeviceRegistryPropertyW
setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
    ctypes.c_void_p,                  # DeviceInfoSet
    ctypes.POINTER(SP_DEVINFO_DATA),  # DeviceInfoData
    wintypes.DWORD,                   # Property
    ctypes.POINTER(wintypes.DWORD),   # PropertyRegDataType
    ctypes.c_void_p,                  # PropertyBuffer
    wintypes.DWORD,                   # PropertyBufferSize
    ctypes.POINTER(wintypes.DWORD),   # RequiredSize
]
setupapi.SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL

# SetupDiGetDeviceInstanceIdW
setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
    ctypes.c_void_p,                  # DeviceInfoSet
    ctypes.POINTER(SP_DEVINFO_DATA),  # DeviceInfoData
    wintypes.LPWSTR,                  # DeviceInstanceId
    wintypes.DWORD,                   # DeviceInstanceIdSize
    ctypes.POINTER(wintypes.DWORD),   # RequiredSize
]
setupapi.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL

# SetupDiDestroyDeviceInfoList
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

# CM_Get_DevNode_Status
cfgmgr32.CM_Get_DevNode_Status.argtypes = [
    ctypes.POINTER(wintypes.ULONG),  # pulStatus
    ctypes.POINTER(wintypes.ULONG),  # pulProblemNumber
    wintypes.DWORD,                  # dnDevInst
    wintypes.ULONG,                  # ulFlags
]
cfgmgr32.CM_Get_DevNode_Status.restype = wintypes.DWORD


# ── Helpers ───────────────────────────────────────────────────────────

def _get_device_registry_property(
    h_dev_info: ctypes.c_void_p,
    dev_info_data: SP_DEVINFO_DATA,
    prop: int,
) -> Any:
    """Read a single device registry property via two-pass buffer sizing.

    Returns str for REG_SZ, List[str] for REG_MULTI_SZ, or "" on failure.
    """
    reg_type = wintypes.DWORD(0)
    required = wintypes.DWORD(0)

    # Pass 1: get required size
    setupapi.SetupDiGetDeviceRegistryPropertyW(
        h_dev_info, ctypes.byref(dev_info_data), prop,
        ctypes.byref(reg_type), None, 0, ctypes.byref(required),
    )
    if required.value == 0:
        return "" if prop != SPDRP_HARDWAREID else []

    # Pass 2: get the data
    buf = ctypes.create_unicode_buffer(required.value // 2 + 1)
    if not setupapi.SetupDiGetDeviceRegistryPropertyW(
        h_dev_info, ctypes.byref(dev_info_data), prop,
        ctypes.byref(reg_type), ctypes.byref(buf), required.value,
        ctypes.byref(required),
    ):
        return "" if prop != SPDRP_HARDWAREID else []

    if reg_type.value == REG_MULTI_SZ:
        # REG_MULTI_SZ: null-separated strings, double-null terminated
        raw = ctypes.wstring_at(ctypes.addressof(buf), required.value // 2)
        return [s for s in raw.split('\x00') if s]

    return buf.value


def enumerate_devices() -> List[Dict[str, Any]]:
    """Enumerate all present PnP devices via SetupAPI + CfgMgr32.

    Returns list of dicts with:
        device_id: str -- device instance ID
        name: str -- friendly name or device description
        manufacturer: str
        class_name: str -- setup class (e.g. "Display", "Net", "USB")
        class_guid: str
        service: str -- driver service name
        hardware_ids: List[str]
        location: str
        enumerator: str -- bus type (PCI, USB, ACPI, etc.)
        status_flags: int -- DN_* flags from CM_Get_DevNode_Status
        problem_code: int -- CM_PROB_* code (0 = no problem)
        has_problem: bool -- True if DN_HAS_PROBLEM set
    """
    h_dev_info = setupapi.SetupDiGetClassDevsW(
        None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES,
    )
    if h_dev_info == INVALID_HANDLE_VALUE or h_dev_info is None:
        raise OSError("SetupDiGetClassDevsW failed")

    devices = []
    try:
        index = 0
        while True:
            dev_info_data = SP_DEVINFO_DATA()
            dev_info_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)

            if not setupapi.SetupDiEnumDeviceInfo(
                h_dev_info, index, ctypes.byref(dev_info_data),
            ):
                break  # No more devices

            # Device instance ID
            id_buf = ctypes.create_unicode_buffer(512)
            id_required = wintypes.DWORD(0)
            device_id = ""
            if setupapi.SetupDiGetDeviceInstanceIdW(
                h_dev_info, ctypes.byref(dev_info_data),
                id_buf, 512, ctypes.byref(id_required),
            ):
                device_id = id_buf.value

            # Properties
            friendly = _get_device_registry_property(h_dev_info, dev_info_data, SPDRP_FRIENDLYNAME)
            desc = _get_device_registry_property(h_dev_info, dev_info_data, SPDRP_DEVICEDESC)
            name = friendly if friendly else (desc if desc else device_id)

            manufacturer = _get_device_registry_property(h_dev_info, dev_info_data, SPDRP_MFG)
            class_name = _get_device_registry_property(h_dev_info, dev_info_data, SPDRP_CLASS)
            class_guid = _get_device_registry_property(h_dev_info, dev_info_data, SPDRP_CLASSGUID)
            service = _get_device_registry_property(h_dev_info, dev_info_data, SPDRP_SERVICE)
            hardware_ids = _get_device_registry_property(h_dev_info, dev_info_data, SPDRP_HARDWAREID)
            location = _get_device_registry_property(h_dev_info, dev_info_data, SPDRP_LOCATION_INFORMATION)
            enumerator = _get_device_registry_property(h_dev_info, dev_info_data, SPDRP_ENUMERATOR_NAME)
            driver_key = _get_device_registry_property(h_dev_info, dev_info_data, SPDRP_DRIVER)

            # Status and problem code via CfgMgr32
            status_flags = wintypes.ULONG(0)
            problem_code = wintypes.ULONG(0)
            cfgmgr32.CM_Get_DevNode_Status(
                ctypes.byref(status_flags), ctypes.byref(problem_code),
                dev_info_data.DevInst, 0,
            )

            devices.append({
                "device_id": device_id,
                "name": name,
                "manufacturer": manufacturer or "",
                "class_name": class_name or "",
                "class_guid": class_guid or "",
                "service": service or "",
                "hardware_ids": hardware_ids if isinstance(hardware_ids, list) else [],
                "location": location or "",
                "enumerator": enumerator or "",
                "driver_key": driver_key or "",
                "status_flags": status_flags.value,
                "problem_code": problem_code.value,
                "has_problem": bool(status_flags.value & DN_HAS_PROBLEM),
            })

            index += 1

    finally:
        setupapi.SetupDiDestroyDeviceInfoList(h_dev_info)

    return devices
