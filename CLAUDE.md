# WinManager Development Context

## Architecture Patterns

- **Services**: Use singleton pattern with `get_<service>()` functions returning global instances
  - `ProcessManager`: Process enumeration with CPU caching
  - `ServiceInfo`: Windows service management
  - `EnterpriseInfo`: Domain, Azure AD, Group Policy
  - `TaskSchedulerInfo`: Task Scheduler via COM (Schedule.Service)
  - `WindowsInfo`: System information via registry, ctypes, WMI COM
- **Caching**: `DataCache[T]` class in `src/services/data_cache.py` for slow operations (registry, WMI)
  - Background loading with `SingleRunWorker` - never block UI thread
  - Thread-safe with QMutex
  - Signals: `state_changed`, `data_loaded`, `error_occurred`
- **Threading**: Always use workers from `src/utils/thread_utils.py`:
  - `SingleRunWorker` - one-shot async tasks (registry, WMI queries)
  - `LoopingWorker` - recurring tasks (metrics, process refresh)
  - `CancellableWorker` - long-running cancellable operations
- **Layouts**: Use `FlowLayout` from `src/ui/widgets/flow_layout.py` for key-value pairs that should reflow on resize

## Code Conventions

- Type hints required on all public methods
- Docstrings for classes and complex methods
- Error handling with sensible defaults (no crashes on missing WMI properties)
- Registry queries: Check 3 paths (HKLM Uninstall, HKCU Uninstall, HKLM Wow6432Node)
- Filter system components: Skip if `SystemComponent=1` or `ParentKeyName` exists
- Software registry keys: DisplayName, Publisher, DisplayVersion, InstallLocation, InstallDate, InstallSource, UninstallString, ModifyPath, EstimatedSize
- Use native Win32 APIs via `src/utils/win32/` package (registry, WMI COM, ctypes) — no subprocess calls for data gathering
- CPU percentages: Normalize by dividing by `cpu_count` to get accurate readings

## UI Patterns

- **Card-based layouts**: Use `InfoCard`/`EnterpriseCard` for grouped information
- **FlowLayout**: For key-value pairs that should reflow naturally on resize
- **RAG coloring**: Use `Colors.SUCCESS` (green), `Colors.WARNING` (amber), `Colors.ERROR` (red) for status
- **Context menus**: Right-click menus for tables with common actions
- **Loading overlays**: Use `LoadingOverlay` widget for async operations

## Testing

- Quick verification: `python -c "from src.services.module import Class; ..."`
- Registry enumeration can be slow (10s timeout recommended)
- Windows-specific: Requires pywin32, will fail on non-Windows

