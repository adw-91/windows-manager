# WinManager Development Context

## Architecture Patterns

- **Services**: Use singleton pattern with `get_<service>()` functions returning global instances
- **Caching**: `DataCache[T]` class in `src/services/data_cache.py` for slow operations (registry, WMI)
  - Background loading with `SingleRunWorker` - never block UI thread
  - Thread-safe with QMutex
  - Signals: `state_changed`, `data_loaded`, `error_occurred`
- **Threading**: Always use workers from `src/utils/thread_utils.py`:
  - `SingleRunWorker` - one-shot async tasks (registry, WMI queries)
  - `LoopingWorker` - recurring tasks (metrics, graphs)
  - `CancellableWorker` - long-running cancellable operations

## Code Conventions

- Type hints required on all public methods
- Docstrings for classes and complex methods
- Error handling with sensible defaults (no crashes on missing WMI properties)
- Registry queries: Check 3 paths (HKLM Uninstall, HKCU Uninstall, HKLM Wow6432Node)
- Filter system components: Skip if `SystemComponent=1` or `ParentKeyName` exists
- Software registry keys: DisplayName, Publisher, DisplayVersion, InstallLocation, InstallDate, InstallSource, UninstallString, ModifyPath, EstimatedSize

## Testing

- Quick verification: `python -c "from src.services.module import Class; ..."`
- Registry enumeration can be slow (10s timeout recommended)
- Windows-specific: Requires pywin32, will fail on non-Windows

## Development Plan

- Active plan: `plan/2026-01-25-plan.md`
- Check "Next Steps" section for current task
- Update Progress Log after completing tasks
