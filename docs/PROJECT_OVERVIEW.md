# Windows Manager - Project Overview

> High-level project documentation and progress tracker for Windows Manager

---

## Progress Tracker

| Phase | Status | Plan Document |
|-------|--------|---------------|
| Phase 1: Core Foundation | **Completed** | - |
| Phase 2: System Information | **Completed** | - |
| Phase 3: Process & Service Management | **Completed** | - |
| Phase 4: Enterprise Features | **Completed** | - |
| Phase 5: Task Scheduler | **Completed** | - |
| Phase 6: UI Polish | **Completed** | - |
| Phase 7: Performance Optimisation | **Completed** | - |
| Phase 8: Performance Bottlenecks | **Completed** | [2026-02-04-phase8-performance-design.md](plans/2026-02-04-phase8-performance-design.md) |
| Phase 9: Native Win32 APIs | **Completed** | [2026-02-05-phase9-native-win32-apis.md](plans/2026-02-05-phase9-native-win32-apis.md) |
| Bug Fix Pass | **Completed** | - |
| Phase 10: Feature Expansion | **Completed** | - |

---

## Overview

Windows Manager is a lean combined system manager for Microsoft Windows built with Python 3.13 and PySide6.

## Current Features

### Overview Tab
- **Expandable Metric Tiles**: Real-time display with click-to-expand live graphs:
  - CPU Usage (user/system/idle breakdown, context switches, interrupts)
  - Memory Usage (total, available, cached, committed)
  - Disk Activity (read/write MB/s, active time, IOPS)
  - Network (download/upload KB/s, adapter info, IPv4)

- **Collapsible Sections**: Expandable sections (accordion-style, one at a time):
  - Installed Software (table with name, publisher, version, size)
  - Startup Apps (registry, startup folder, task scheduler sources)
  - Battery (health, cycle count, capacity - shown only on laptops)

- **Auto-refresh**: Tile values update every 1 second, graphs every 500ms

### System Tab
- **Tabbed Sub-sections**: QTabWidget with 5 lazy-loaded sub-tabs:
  - Summary: Computer name, OS, version, manufacturer, model, processor, RAM, boot time, domain, timezone, processes, services, locale
  - Hardware: Compound card containing Hardware (processor, CPU cores/speed, RAM, memory config, manufacturer, product name, BIOS, baseboard) + Boot & Firmware (firmware type, Secure Boot, BIOS dates/versions, system family/SKU, SMBIOS, boot device)
  - Components: All display adapters (with VRAM and driver version), all sound devices, storage summary, optical drives
  - Security: Compound card containing Security Status (Security Center, Defender, Firewall, UAC, Secure Boot, Windows Update, VBS) + TPM (version, interface type via TBS API, enabled/activated/owned via WMI) + BitLocker (per-volume protection, encryption status, method)
  - Network: Active adapter, IPv4, subnet mask, link speed, MTU, hostname, FQDN, default gateway, DNS servers, adapter counts

- **Per-sub-tab lazy loading**: Only collects data for the visible sub-tab
- **Compound cards**: Multi-section tabs (Hardware, Security) use a single bordered container with multiple titled sections inside — no hard divisions between sections
- **SectionCard layout**: Two-column grid layout (key: value) with alternating row backgrounds

### Processes & Services Tab
- **Processes Sub-tab**:
  - Real-time process list with 1-second auto-refresh
  - CPU normalization (divide by CPU count for accurate percentages)
  - RAG coloring: High CPU (red), Medium CPU (amber), Normal (default)
  - System Idle Process: Inverted RAG (high idle = green/good)
  - Numeric sorting for PID, CPU%, and Memory columns (not lexicographic)
  - Ctrl key pauses sorting (uses Windows API GetAsyncKeyState)
  - End Task with confirmation dialog
  - Context menu: End Task, Copy PID, Copy Name, Refresh

- **Services Sub-tab**:
  - Full service management: Start, Stop, Restart
  - RAG status coloring: Running (green), Stopped (amber)
  - Search/filter by name, display name, or status
  - Context menu for quick actions

### Device Manager Tab
- **Categorized Device Tree**: Tree grouped by device class (Display, Net, USB, etc.) with RAG problem indicators
- **Native SetupAPI**: Uses SetupDiGetClassDevsW + CfgMgr32 for near-instant enumeration (~50ms vs 2-5s WMI)
- **Detail Panel**: QGridLayout-based device info and driver details (loaded lazily from registry), hardware IDs
- **Problem Codes**: CM_PROB_* code descriptions with RAG coloring on tree items
- **Search/Filter**: Case-insensitive filter by device name, manufacturer, or device ID
- **Context Menu**: Copy Device ID, Copy Name, Copy Hardware IDs
- **Lazy Loading**: Data loaded on first tab activation

### Storage Tab
- **Drive Overview Tiles**: Clickable tiles showing drive letter, label, filesystem, total/used/free with RAG progress bars
- **Selected Drive State**: Clicked tile shows accent border to indicate active selection
- **Loading Overlay**: Spinner overlay on tree during Phase 1 directory listing
- **Two-Phase Scanning**: Phase 1 instant directory listing, Phase 2 progressive size calculation with progress bar
- **Directory Size Tree**: On-demand recursive scanning with lazy tree expansion
- **Cancellable Scans**: Background scanning via CancellableWorker with progress bar and cancel button
- **Context Menu**: Open in Explorer, Copy Path
- **Lazy Loading**: Drive info loaded on first tab activation, directory scans triggered by user interaction

### Enterprise Tab
- **Compound Card Layout**: Single bordered container with four titled sections:
  - Current User: Username, domain, full name, SID, admin status
  - Entra ID: Azure AD join status, tenant ID/name, device ID
  - Domain: Computer name, domain/workgroup, domain joined status, DC
  - Group Policy: GPO applied status, count, computer/user policies
- **Grid Layout**: Two-column key-value grid with alternating row backgrounds and RAG coloring for status fields
- **Lazy Loading**: Data loaded on first tab activation

### Task Scheduler Tab
- **Modern UI**: Tree navigation + task table + details panel
- **Task Management**: Run, Enable, Disable, End tasks
- **New Task Dialog**: Custom dialog for creating scheduled tasks
  - Schedule types: Once, Daily, Weekly, Monthly, At Startup, At Logon
  - Program path, arguments, working directory
  - Admin privileges warning banner
- **RAG Coloring**: Task status and last result indicators
- **Lazy Loading**: Data loaded on first tab activation

### Sidebar
- **Navigation**: Tab switching via icon buttons (Overview, System, Processes, Storage, Devices, Tasks, Enterprise)
- **Keyboard Shortcuts**: Ctrl+1 through Ctrl+7 for quick tab switching

## Architecture

### Services Layer
- `SystemMonitor`: CPU, memory, disk monitoring using psutil
- `PerformanceMonitor`: Differential rate calculations (disk I/O, network I/O, context switches, interrupts) with thread-safe state
- `ProcessManager`: Native process enumeration via NtQuerySystemInformation with CPU time-delta tracking
- `WindowsInfo`: System information via registry, ctypes, WMI COM
- `ServiceInfo`: Windows service management via win32service SCM API
- `DeviceInfo`: Device enumeration via native SetupAPI/CfgMgr32 with lazy driver detail lookups
- `StorageInfo`: Drive overview (psutil + WMI) and on-demand directory size scanning
- `SoftwareInfo`: Installed software from registry (HKLM/HKCU Uninstall, Wow6432Node)
- `StartupInfo`: Startup apps from registry, startup folders, and Task Scheduler COM
- `EnterpriseInfo`: Domain, Azure AD, Group Policy via win32net, registry, ctypes
- `TaskSchedulerInfo`: Task Scheduler interaction via COM (Schedule.Service)
- `DataCache[T]`: Generic caching with background loading and thread-safe access

### UI Layer
- `MainWindow`: Main application window with sidebar navigation
- Tab implementations:
  - `SystemOverviewTab`: Live metric tiles with expandable graphs and collapsible sections
  - `SystemTab`: Tabbed sub-section system information with per-sub-tab lazy loading, compound cards, and SectionCard grid layout
  - `ProcessesServicesTab`: Process and service management
  - `StorageTab`: Drive overview tiles with drill-down directory tree
  - `DeviceManagerTab`: Categorized device tree with detail panel
  - `EnterpriseTab`: Domain and Azure AD information
  - `TaskSchedulerTab`: Task Scheduler management

### Widgets
- `ExpandableMetricTile`: Metric tile with click-to-expand live graph and detail labels
- `CollapsibleSection`: Expandable/collapsible content section (accordion)
- `PropertyList`: Two-column key-value grid layout for system information sub-tabs
- `FlowLayout`: Custom layout for natural widget reflow (Overview tab)
- `BatteryWidget`: Battery status display with health info
- `LiveGraph` / `MultiLineGraph`: Real-time graph widgets using pyqtgraph with ring buffers
- `LoadingOverlay`: Loading indicator overlay
- `SoftwareTableWidget`: Sortable/searchable software table
- `DriveTile`: Clickable drive overview tile with RAG progress bar

### Utilities
- `formatters.py`: Data formatting (bytes, uptime, percentages)
- `thread_utils.py`: Threading workers (SingleRunWorker, LoopingWorker, CancellableWorker)
- `win32/`: Native Win32 API wrappers:
  - `registry.py`: Safe winreg wrappers (read_string, read_dword, enumerate_subkeys)
  - `wmi.py`: Thread-safe WMI COM wrapper (WmiConnection)
  - `system_info.py`: ctypes kernel32 wrappers (locale, memory, firmware, secure boot)
  - `security.py`: Token-based SID, admin check, username/domain
  - `gpo.py`: GPO enumeration via GetAppliedGPOListW
  - `process_info.py`: Native process enumeration via NtQuerySystemInformation
  - `device_api.py`: Native device enumeration via SetupAPI/CfgMgr32

## Technology Stack
- Python 3.13
- PySide6 (Qt for Python)
- psutil (System monitoring)
- pywin32 (Windows service management, COM, security tokens)
- pyqtgraph (Real-time graphs with numpy backend)
- numpy (Efficient data storage via ring buffers)
- ctypes (Windows API: locale, memory, firmware, GPO, key state, NtQuerySystemInformation, SetupAPI, TBS)
- winreg (Registry access for system information)

## Key Implementation Details

### CPU Percentage Accuracy
- ProcessManager computes CPU% from kernel/user time deltas between NtQuerySystemInformation snapshots
- Normalized by dividing by `cpu_count` to get percentage of total system capacity
- PID reuse detected via `create_time_ns` to prevent spurious spikes
- Capped at 100% for display

### Ctrl Key Pause (Processes)
- Qt's `keyboardModifiers()` only returns state at last event
- Uses Windows API `GetAsyncKeyState(VK_CONTROL)` for real-time state

### Battery Information
- Uses WMI COM queries (root\cimv2 Win32_Battery + root\WMI BatteryStaticData/BatteryFullChargedCapacity)
- WMI property types vary by hardware (e.g. DesignVoltage may be string or int) — values are explicitly cast
- Power plan from registry (ActivePowerScheme GUID + FriendlyName lookup)
- Calculates health as `FullChargeCapacity / DesignCapacity * 100`
- Battery section only shown when battery hardware is detected

### FlowLayout
- Custom QLayout that arranges widgets horizontally
- Wraps to new rows when horizontal space exhausted
- Each key-value pair is a self-contained widget unit
- Implements `heightForWidth()` for proper container sizing
- Used in Overview tab (metric tile details) and Storage tab (drive tiles)

### TPM Detection
- Primary: `Tbsi_GetDeviceInfo` from `tbs.dll` — works without admin, returns TPM version (1.2/2.0) and interface type
- Fallback: WMI `Win32_Tpm` in `root\cimv2\Security\MicrosoftTpm` — provides enabled/activated/owned status, spec version, manufacturer version (requires admin)
- Both sources merged: TBS provides basic detection, WMI adds detail when available

---

## Performance Optimisations (Implemented)

### Phase 7 Optimisations

#### Deferred Graph Creation
- pyqtgraph widgets are created on first tile expansion (not at startup)
- Avoids OpenGL context setup until graphs are actually needed
- **Impact:** Tile clicks are responsive; graph creation cost paid once

#### Batch Graph Updates
- Multiple series updated in single repaint batch via `add_points()` method
- Reduces repaint count from N (number of series) to 1 per update cycle
- **Impact:** More efficient graph rendering for CPU, Disk, Network tiles

### Phase 8 Optimisations

#### Lazy Tab Loading
- Storage, Devices, Tasks, and Enterprise tabs load data on first activation
- Tables show loading overlay until data arrives
- **Impact:** Faster startup, no unnecessary subprocess calls

#### Graph Visibility Pausing
- LoopingWorkers pause when Overview tab is not visible
- Resume automatically when tab becomes active again
- **Impact:** Zero CPU cost from graphs when viewing other tabs

#### Expanded-Only Graph Updates
- Only the currently expanded tile's graph receives data updates
- Collapsed tile graphs are not rendered
- **Impact:** Reduced per-cycle rendering cost

#### Resize Debouncing
- Graph resize events debounce the expensive `curve.setData()` calls with 150ms delay
- pyqtgraph ViewBox geometry always updates immediately (cheap coordinate transforms)
- **Impact:** Smooth window resizing without dark background gaps or graph lag

#### Simplified Graph Rendering
- Antialiasing disabled globally for pyqtgraph
- clipToView enabled on all graph curves
- **Impact:** Faster graph draw calls

### Phase 9: Native Win32 APIs

#### Subprocess Elimination
- Replaced ~56 subprocess/PowerShell/WMIC calls with native Win32 APIs
- New `src/utils/win32/` package: registry, WMI COM, ctypes, security, GPO helpers
- Services: win32service SCM API instead of wmic/net commands
- System info: Registry + ctypes instead of wmic/PowerShell
- Drivers → Devices: SetupAPI/CfgMgr32 ctypes instead of WMI COM
- Task Scheduler: COM (Schedule.Service) instead of schtasks parsing
- Enterprise: win32net + registry + ctypes instead of dsregcmd/gpresult
- Battery: WMI COM + registry instead of PowerShell
- Process enumeration: NtQuerySystemInformation kernel call instead of psutil.process_iter() (228x faster, bypasses EDR)
- Thread/handle counts: Exact totals from kernel data instead of 20-process sampling/extrapolation
- **Impact:** Eliminated process spawning overhead, faster data collection, no shell parsing fragility

### Compilation Options

For significantly improved startup time, consider compiling with Nuitka:

```bash
pip install nuitka
nuitka --standalone --enable-plugin=pyside6 --windows-console-mode=disable run_app.py
```

**Expected improvement**: 2-4x faster startup, 10-20% faster runtime.

### Realistic Expectations

Python/Qt will never match native Rust/C++ responsiveness for this type of application. The optimisations above can improve perceived performance from "sluggish" to "acceptable", but not to "snappy". For maximum responsiveness, consider a parallel Rust implementation.
