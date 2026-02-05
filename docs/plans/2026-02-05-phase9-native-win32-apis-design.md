# Phase 9: Replace Subprocess Calls with Native Win32 APIs

## Goal

Eliminate all subprocess/PowerShell/WMIC calls from WinManager, replacing them with direct Win32 API calls via pywin32, ctypes, and WMI COM. This removes process-spawn overhead (~50-200ms per call) and makes data gathering significantly faster.

## Current State

56 subprocess calls across 7 files:

| File | Commands | Count |
|------|----------|-------|
| `service_info.py` | `wmic service`, `sc start/stop` | 6 |
| `windows_info.py` | `wmic cpu/memorychip/bios/computersystem`, `powershell` | 8 |
| `system_tab.py` | `_run_wmic()` (12+ hardware queries), `_run_powershell()` | ~15 |
| `enterprise_info.py` | `wmic`, `powershell` (SID, admin, network), `dsregcmd`, `gpresult` | 11 |
| `task_scheduler_info.py` | `schtasks /query/run/change/end/delete/create` | 8 |
| `driver_info.py` | `powershell Get-WmiObject Win32_SystemDriver` | 2 |
| `battery_widget.py` | `powershell` CIM queries | 6 |

Legitimate subprocess uses (keep as-is):
- `software_table.py`: `subprocess.Popen(['explorer', path])` - launching file explorer
- `startup_table.py`: `subprocess.Popen(['explorer', ...])` - launching file explorer

## New Package: `src/utils/win32/`

```
src/utils/win32/
    __init__.py          # Re-exports for convenience
    registry.py          # Registry read helpers
    wmi.py               # WMI COM connection wrapper
    system_info.py       # ctypes wrappers for system APIs
    security.py          # Token, SID, admin check helpers
    gpo.py               # Group Policy enumeration via GetAppliedGPOListW
```

### `registry.py` - Registry Helpers

Safe wrappers around `winreg` with consistent error handling.

```python
def read_string(root: int, path: str, name: str) -> Optional[str]
def read_dword(root: int, path: str, name: str) -> Optional[int]
def enumerate_subkeys(root: int, path: str) -> list[str]
def read_subkey_values(root: int, path: str, subkey: str, names: list[str]) -> dict[str, Optional[str]]
```

### `wmi.py` - WMI COM Helper

Thread-safe WMI connection using `win32com.client`. Handles COM initialization per-thread.

```python
class WmiConnection:
    """WMI COM connection wrapper. Initialize once per thread."""

    def __init__(self, namespace: str = r"root\cimv2"):
        """Connect to WMI namespace. Calls CoInitialize if needed."""

    def query(self, wql: str) -> list[dict[str, Any]]:
        """Execute WQL query, return list of dicts."""

    def query_single(self, wql: str) -> Optional[dict[str, Any]]:
        """Execute WQL query, return first result or None."""
```

### `system_info.py` - System API Wrappers (ctypes)

Direct kernel32/user32 calls for system information.

```python
def get_system_locale() -> str                    # GetSystemDefaultLocaleName
def get_total_physical_memory() -> int            # GlobalMemoryStatusEx
def get_firmware_type() -> str                    # GetFirmwareType -> "UEFI" or "BIOS"
def is_secure_boot_enabled() -> Optional[bool]    # Registry SecureBoot\State
def get_power_status() -> dict                    # GetSystemPowerStatus
def get_computer_name_ex(fmt: int) -> Optional[str]  # GetComputerNameExW
```

### `security.py` - Security Helpers

User identity and privilege checks using Win32 security APIs.

```python
def get_current_user_sid() -> Optional[str]   # OpenProcessToken + GetTokenInformation + ConvertSidToStringSid
def is_user_admin() -> bool                   # shell32.IsUserAnAdmin or CheckTokenMembership
def get_current_username() -> str             # GetUserNameW or env var
def get_current_domain() -> str               # env var or NetGetJoinInformation
```

### `gpo.py` - Group Policy Enumeration

Uses `GetAppliedGPOListW` from `userenv.dll` via ctypes.

```python
def get_applied_gpos(machine: bool = True) -> list[str]
    """Return display names of applied GPOs for machine or user scope."""
```

Requires defining ctypes structs:
- `GROUP_POLICY_OBJECTW` (linked list with pNext/pPrev)
- `GUID` struct for extension parameter
- Walking the linked list to extract `lpDisplayName`
- Calling `FreeGPOList` to clean up

## Service-by-Service Migration

### 1. `service_info.py` -> `win32service` module

| Current | Replacement |
|---------|-------------|
| `wmic service get ...` (list all) | `win32service.EnumServicesStatusEx()` |
| `wmic service where name=X` (detail) | `win32service.OpenService()` + `QueryServiceConfig()` + `QueryServiceConfig2()` |
| `sc start` | `win32service.StartService()` |
| `sc stop` | `win32service.ControlService(SERVICE_CONTROL_STOP)` |
| `sc restart` | Stop + sleep + Start |

The Rust project's `services.rs` uses the exact same SCM API calls - use as reference.

### 2. `windows_info.py` -> Registry + ctypes

| Current | Replacement |
|---------|-------------|
| `wmic cpu get name` | `registry.read_string(HKLM, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")` |
| `wmic memorychip get capacity` | `system_info.get_total_physical_memory()` (GlobalMemoryStatusEx) |
| `wmic computersystem get domain` | `win32net.NetGetJoinInformation()` or `system_info.get_computer_name_ex()` |
| `wmic computersystem get manufacturer` | `registry.read_string(HKLM, r"SYSTEM\CurrentControlSet\Control\SystemInformation", "SystemManufacturer")` |
| `wmic computersystem get model` | `registry.read_string(..., "SystemProductName")` |
| `wmic bios get smbiosbiosversion` | `registry.read_string(HKLM, r"HARDWARE\DESCRIPTION\System\BIOS", "BIOSVersion")` |
| `powershell Get-WinSystemLocale` | `system_info.get_system_locale()` (GetSystemDefaultLocaleName) |
| `wmic os get lastbootuptime` | `psutil.boot_time()` (already available) |

### 3. `system_tab.py` -> Registry + ctypes + minimal WMI

Replace `_run_wmic()` and `_run_powershell()` helpers entirely.

| Current | Replacement |
|---------|-------------|
| `_run_wmic("cpu", "Name")` | Registry CentralProcessor |
| `_run_wmic("computersystem", "Manufacturer")` | Registry SystemInformation |
| `_run_wmic("computersystem", "Model")` | Registry SystemInformation |
| `_run_wmic("bios", "SMBIOSBIOSVersion")` | Registry BIOS |
| `_run_wmic("baseboard", "Manufacturer/Product")` | Registry BIOS (BaseBoardManufacturer/BaseBoardProduct) |
| `_run_wmic("path win32_videocontroller", "Name")` | Registry `{4d36e968-e325-11ce-bfc1-08002be10318}\0000\DriverDesc` |
| `_run_wmic("path win32_videocontroller", "AdapterRAM")` | Registry `HardwareInformation.qwMemorySize` |
| `_run_wmic("sounddev", "Name")` | Registry `{4d36e96c-e325-11ce-bfc1-08002be10318}\*\DriverDesc` |
| `_run_wmic("cdrom", "Name")` | Registry `Services\cdrom\Enum` or "None" |
| `_run_powershell("Confirm-SecureBootUEFI")` | `system_info.is_secure_boot_enabled()` (Registry SecureBoot\State) |

### 4. `driver_info.py` -> WMI COM

| Current | Replacement |
|---------|-------------|
| `powershell Get-WmiObject Win32_SystemDriver` | `WmiConnection().query("SELECT Name, DisplayName, PathName, State, StartMode, Description FROM Win32_SystemDriver")` |
| Fallback PowerShell query | Not needed - WMI COM is the same underlying mechanism |

### 5. `task_scheduler_info.py` -> Task Scheduler 2.0 COM

| Current | Replacement |
|---------|-------------|
| `schtasks /query /fo CSV /v` | `win32com.client.Dispatch('Schedule.Service')` -> recursive folder enumeration |
| `schtasks /run /tn X` | `task.Run(None)` |
| `schtasks /change /tn X /enable` | `task.Enabled = True` |
| `schtasks /change /tn X /disable` | `task.Enabled = False` |
| `schtasks /end /tn X` | `task.Stop(0)` |
| `schtasks /delete /tn X /f` | `folder.DeleteTask(name, 0)` |
| `schtasks /create ...` | `folder.RegisterTaskDefinition(...)` |

The Rust project's `tasks.rs` uses the exact same COM interfaces - use as reference.

### 6. `enterprise_info.py` -> Win32 APIs + ctypes

| Current | Replacement |
|---------|-------------|
| `wmic computersystem get domain,partofdomainbynet` | `win32net.NetGetJoinInformation()` |
| `wmic computersystem get name,workgroup` | `win32api.GetComputerName()` + `NetGetJoinInformation()` |
| `powershell [Security.Principal...]::GetCurrent()` (SID) | `security.get_current_user_sid()` |
| `powershell IsInRole(Administrator)` | `security.is_user_admin()` |
| `powershell Get-NetAdapter` | WMI COM `Win32_NetworkAdapterConfiguration WHERE IPEnabled=True` |
| `powershell Resolve-DnsName` | `socket.getaddrinfo()` or ctypes `DnsQuery_W` |
| `powershell Get-NetIPv6Protocol` | Registry or WMI `Win32_NetworkAdapterConfiguration` |
| `dsregcmd /status` | Registry `HKLM\SYSTEM\CurrentControlSet\Control\CloudDomainJoin\JoinInfo` |
| `gpresult /scope:computer /r` | `gpo.get_applied_gpos(machine=True)` |
| `gpresult /scope:user /r` | `gpo.get_applied_gpos(machine=False)` |
| `powershell nltest /dcname` | `win32net.NetGetDCName()` |

### 7. `battery_widget.py` -> psutil + WMI COM

| Current | Replacement |
|---------|-------------|
| `powershell Get-CimInstance Win32_Battery` | `psutil.sensors_battery()` for basics |
| `powershell BatteryStaticData` (root/WMI) | `WmiConnection(r"root\WMI").query("SELECT ... FROM BatteryStaticData")` |
| `powershell BatteryFullChargedCapacity` | `WmiConnection(r"root\WMI").query("SELECT ... FROM BatteryFullChargedCapacity")` |
| `powershell BatteryCycleCount` | `WmiConnection(r"root\WMI").query("SELECT ... FROM BatteryCycleCount")` |
| `powershell BatteryStatus` | `WmiConnection(r"root\WMI").query("SELECT ... FROM BatteryStatus")` |

## Error Handling

- Info-gathering functions return `Optional[T]`, log warnings on failure
- Service control functions raise typed exceptions (match existing `Error` patterns)
- WMI connection failures: fail fast with clear error messages
- Thread safety: WMI COM requires per-thread `CoInitialize` - handled in `WmiConnection.__init__`

## Testing

- Each `win32/` module gets unit tests with known-good queries
- Registry tests: read `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProductName`
- WMI tests: query `Win32_OperatingSystem`
- Service tests: enumerate services (always works)
- Task tests: enumerate root folder tasks
- GPO tests: call `GetAppliedGPOListW` (always returns at least local policy)

## Implementation Order

1. Create `src/utils/win32/` package with all helper modules
2. Migrate `service_info.py` (cleanest 1:1, high confidence)
3. Migrate `windows_info.py` (registry reads, straightforward)
4. Migrate `system_tab.py` (replaces `_run_wmic`/`_run_powershell`)
5. Migrate `driver_info.py` (WMI COM)
6. Migrate `task_scheduler_info.py` (Task Scheduler COM)
7. Migrate `enterprise_info.py` (mixed Win32 + ctypes + GPO)
8. Migrate `battery_widget.py` (psutil + WMI COM)
9. Verify: grep for remaining subprocess imports, ensure only explorer launches remain

## Dependencies

- `pywin32` (already installed) - `win32service`, `win32com.client`, `win32api`, `win32net`, `win32security`
- `psutil` (already installed) - battery basics, boot time
- `ctypes` (stdlib) - `kernel32`, `userenv`, `shell32`, `dnsapi`
- `winreg` (stdlib) - registry access
- No new pip dependencies required

## Performance Impact

- Eliminates ~54 process spawns (each ~50-200ms overhead)
- Registry reads: <1ms each
- ctypes calls: <1ms each
- WMI COM queries: ~10-100ms each (but no process spawn overhead)
- Win32 SCM API: ~5-20ms for full service enumeration
- Task Scheduler COM: ~50-200ms for full enumeration (comparable to schtasks but no spawn)
- Net improvement: system_tab hardware info goes from ~3s (15 x 200ms) to ~50ms

## Reference

The Rust project at `..\windows-manager-rust\crates\wm\src\` implements the same native APIs:
- `services.rs` - SCM API (exact pattern for service_info.py)
- `tasks.rs` - Task Scheduler 2.0 COM (exact pattern for task_scheduler_info.py)
- `drivers.rs` - WMI COM for Win32_SystemDriver
- `software.rs` - Registry API for installed software
- `enterprise.rs` - Win32 token/SID/domain APIs
- `wmi.rs` - WMI COM connection helper
