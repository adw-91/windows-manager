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
- **Card-based UI**: Modern card layout with msinfo32-style information
- **Categories**:
  - System Summary: Computer name, OS, version, manufacturer, model, processor, RAM
  - Hardware: CPU cores, speed, memory config, BIOS, baseboard
  - Components: Display, VRAM, sound, storage, optical drives
  - Software: User, processes, services, Windows dir, locale
  - Security: Security Center, Defender, Firewall, UAC, Secure Boot, Windows Update
  - Network: Active adapter, IPv4, speed, hostname, FQDN

- **FlowLayout**: Custom layout that reflows key-value pairs naturally on resize

### Processes & Services Tab
- **Processes Sub-tab**:
  - Real-time process list with 1-second auto-refresh
  - CPU normalization (divide by CPU count for accurate percentages)
  - RAG coloring: High CPU (red), Medium CPU (amber), Normal (default)
  - System Idle Process: Inverted RAG (high idle = green/good)
  - Ctrl key pauses sorting (uses Windows API GetAsyncKeyState)
  - End Task with confirmation dialog
  - Context menu: End Task, Copy PID, Copy Name, Refresh

- **Services Sub-tab**:
  - Full service management: Start, Stop, Restart
  - RAG status coloring: Running (green), Stopped (amber)
  - Search/filter by name, display name, or status
  - Context menu for quick actions

### Drivers Tab
- **Device Driver Inventory**: PowerShell WMI-based driver enumeration
- **Lazy Loading**: Data loaded on first tab activation
- **Loading Overlay**: Shows loading state while data is fetched

### Enterprise Tab
- **Current User**: Username, domain, full name, SID, admin status
- **Entra ID**: Azure AD join status, tenant ID/name, device ID
- **Domain**: Computer name, domain/workgroup, domain joined status, DC
- **Group Policy**: GPO applied status, count, computer/user policies
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
- **Navigation**: Tab switching via icon buttons (Overview, System, Processes, Drivers, Tasks, Enterprise)
- **Keyboard Shortcuts**: Ctrl+1 through Ctrl+6 for quick tab switching

## Architecture

### Services Layer
- `SystemMonitor`: CPU, memory, disk monitoring using psutil
- `PerformanceMonitor`: Differential rate calculations (disk I/O, network I/O, context switches, interrupts) with thread-safe state
- `ProcessManager`: Process enumeration with CPU caching for accurate readings
- `WindowsInfo`: System information retrieval using WMIC, PowerShell, platform
- `ServiceInfo`: Windows service management via psutil
- `DriverInfo`: Device driver enumeration via PowerShell WMI
- `SoftwareInfo`: Installed software from registry (HKLM/HKCU Uninstall, Wow6432Node)
- `StartupInfo`: Startup apps from registry, startup folders, and Task Scheduler COM
- `EnterpriseInfo`: Domain, Azure AD, Group Policy information
- `TaskSchedulerInfo`: Task Scheduler interaction via schtasks command
- `DataCache[T]`: Generic caching with background loading and thread-safe access

### UI Layer
- `MainWindow`: Main application window with sidebar navigation
- Tab implementations:
  - `SystemOverviewTab`: Live metric tiles with expandable graphs and collapsible sections
  - `SystemTab`: Card-based system information
  - `ProcessesServicesTab`: Process and service management
  - `DriversTab`: Device driver inventory
  - `EnterpriseTab`: Domain and Azure AD information
  - `TaskSchedulerTab`: Task Scheduler management

### Widgets
- `ExpandableMetricTile`: Metric tile with click-to-expand live graph and detail labels
- `CollapsibleSection`: Expandable/collapsible content section (accordion)
- `FlowLayout`: Custom layout for natural key-value pair reflow
- `BatteryWidget`: Battery status display with health info
- `LiveGraph` / `MultiLineGraph`: Real-time graph widgets using pyqtgraph with ring buffers
- `LoadingOverlay`: Loading indicator overlay
- `SoftwareTableWidget`: Sortable/searchable software table

### Utilities
- `formatters.py`: Data formatting (bytes, uptime, percentages)
- `thread_utils.py`: Threading workers (SingleRunWorker, LoopingWorker, CancellableWorker)

## Technology Stack
- Python 3.13
- PySide6 (Qt for Python)
- psutil (System monitoring)
- pywin32 (Windows-specific operations, COM)
- pyqtgraph (Real-time graphs with numpy backend)
- numpy (Efficient data storage via ring buffers)
- subprocess (WMIC, PowerShell, schtasks commands)
- ctypes (Windows API for key state detection)

## Key Implementation Details

### CPU Percentage Accuracy
- psutil returns CPU as percentage of all cores combined
- Normalized by dividing by `cpu_count` to get per-core average
- Capped at 100% for display

### Ctrl Key Pause (Processes)
- Qt's `keyboardModifiers()` only returns state at last event
- Uses Windows API `GetAsyncKeyState(VK_CONTROL)` for real-time state

### Battery Information
- WMIC queries unreliable, switched to PowerShell CIM
- Uses `Get-CimInstance Win32_Battery` with JSON output
- Calculates health as `FullChargeCapacity / DesignCapacity * 100`
- Battery section only shown when battery hardware is detected

### FlowLayout
- Custom QLayout that arranges widgets horizontally
- Wraps to new rows when horizontal space exhausted
- Each key-value pair is a self-contained widget unit
- Implements `heightForWidth()` for proper container sizing

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
- Drivers, Tasks, and Enterprise tabs load data on first activation
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
- Graph resize events are debounced with 150ms delay
- Skip rendering during resize, refresh all curves after resize completes
- **Impact:** Smooth window resizing without graph lag

#### Simplified Graph Rendering
- Antialiasing disabled globally for pyqtgraph
- clipToView enabled on all graph curves
- **Impact:** Faster graph draw calls

### Compilation Options

For significantly improved startup time, consider compiling with Nuitka:

```bash
pip install nuitka
nuitka --standalone --enable-plugin=pyside6 --windows-console-mode=disable run_app.py
```

**Expected improvement**: 2-4x faster startup, 10-20% faster runtime.

### Realistic Expectations

Python/Qt will never match native Rust/C++ responsiveness for this type of application. The optimisations above can improve perceived performance from "sluggish" to "acceptable", but not to "snappy". For maximum responsiveness, consider a parallel Rust implementation.
