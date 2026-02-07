# WinManager Development Context

## Architecture Patterns

- **Services**: Use singleton pattern with `get_<service>()` functions returning global instances
  - `ProcessManager`: Native process enumeration via NtQuerySystemInformation with CPU delta tracking
  - `ServiceInfo`: Windows service management
  - `EnterpriseInfo`: Domain, Azure AD, Group Policy
  - `TaskSchedulerInfo`: Task Scheduler via COM (Schedule.Service)
  - `WindowsInfo`: System information via registry, ctypes, WMI COM
  - `DeviceInfo`: Device enumeration via native SetupAPI/CfgMgr32
  - `StorageInfo`: Drive overview (psutil + WMI) and directory size scanning
- **Caching**: `DataCache[T]` class in `src/services/data_cache.py` for slow operations (registry, WMI)
  - Background loading with `SingleRunWorker` - never block UI thread
  - Thread-safe with QMutex
  - Signals: `state_changed`, `data_loaded`, `error_occurred`
- **Threading**: Always use workers from `src/utils/thread_utils.py`:
  - `SingleRunWorker` - one-shot async tasks (registry, WMI queries)
  - `LoopingWorker` - recurring tasks (metrics, process refresh)
  - `CancellableWorker` - long-running cancellable operations
- **Layouts**:
  - `SectionCard` / `EnterpriseCard` (QGridLayout-based) for key-value data with alternating row backgrounds
  - Compound cards: `_create_compound_card()` wraps multiple borderless SectionCards in a single bordered container
  - `FlowLayout` from `src/ui/widgets/flow_layout.py` for widgets that should reflow on resize (Overview tab, Storage drive tiles)

## Code Conventions

- Type hints required on all public methods
- Docstrings for classes and complex methods
- Error handling with sensible defaults (no crashes on missing WMI properties)
- Registry queries: Check 3 paths (HKLM Uninstall, HKCU Uninstall, HKLM Wow6432Node)
- Filter system components: Skip if `SystemComponent=1` or `ParentKeyName` exists
- Software registry keys: DisplayName, Publisher, DisplayVersion, InstallLocation, InstallDate, InstallSource, UninstallString, ModifyPath, EstimatedSize
- Use native Win32 APIs via `src/utils/win32/` package (registry, WMI COM, ctypes) — no subprocess calls for data gathering
- Process enumeration: Use `enumerate_processes()` from `src/utils/win32/process_info` — single kernel call, no per-process handles, bypasses EDR
- Device enumeration: Use `enumerate_devices()` from `src/utils/win32/device_api` — SetupAPI/CfgMgr32 ctypes (~50ms vs 2-5s WMI)
- CPU percentages: Normalize by dividing by `cpu_count` to get accurate readings

## UI Patterns

- **SectionCard / EnterpriseCard**: Two-column QGridLayout for key-value display with alternating row backgrounds
- **Compound cards**: Multi-section tabs use `_create_compound_card()` (System) or styled QFrame (Enterprise) wrapping borderless cards in a single bordered container
- **FlowLayout**: For widgets that should reflow naturally on resize (Overview tab, Storage drive tiles)
- **RAG coloring**: Use `Colors.SUCCESS` (green), `Colors.WARNING` (amber), `Colors.ERROR` (red) for status
- **Context menus**: Right-click menus for tables with common actions
- **Loading overlays**: Use `LoadingOverlay` widget for async operations (tiles, tree panels)
- **Tabbed sub-sections**: System tab uses QTabWidget with per-sub-tab lazy loading
- **Tree + detail panel**: Device Manager and Task Scheduler use QSplitter with tree/detail layout
- **Drive tiles**: Storage tab uses clickable DriveTile widgets with RAG progress bars and selected state (accent border)
- **TPM detection**: TBS API (`tbs.dll`) for non-admin detection, WMI fallback for detail

## Testing

- Quick verification: `python -c "from src.services.module import Class; ..."`
- Run tests: `python -m pytest tests/ -v`
- Registry enumeration can be slow (10s timeout recommended)
- Windows-specific: Requires pywin32, will fail on non-Windows

