# Windows Manager Implementation

## Overview

Windows Manager is a lean combined system manager for Microsoft Windows built with Python 3.13 and PySide6.

## Current Features

### Overview Tab
- **Live Metrics Tiles**: Real-time display of:
  - CPU Usage (percentage with progress bar)
  - Memory Usage (percentage and GB used/total)
  - Disk Usage (average across all drives)
  - System Uptime (formatted time display)

- **Collapsible Sections**: Expandable sections that fill available vertical space
  - System Information
  - Quick Actions
  - Recent Activity

- **Auto-refresh**: Metrics update every 2 seconds

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

### Software Tab
- **Installed Programs**: Registry-based software inventory
  - Searches HKLM Uninstall, HKCU Uninstall, Wow6432Node
  - Filters out system components
- **Startup**: Startup program management

### Enterprise Tab
- **Current User**: Username, domain, full name, SID, admin status
- **Entra ID**: Azure AD join status, tenant ID/name, device ID
- **Domain**: Computer name, domain/workgroup, domain joined status, DC
- **Group Policy**: GPO applied status, count, computer/user policies

### Task Scheduler Tab
- **Modern UI**: Tree navigation + task table + details panel
- **Task Management**: Run, Enable, Disable, End tasks
- **New Task Dialog**: Custom dialog for creating scheduled tasks
  - Schedule types: Once, Daily, Weekly, Monthly, At Startup, At Logon
  - Program path, arguments, working directory
  - Admin privileges warning banner
- **RAG Coloring**: Task status and last result indicators

### Sidebar
- **Navigation**: Tab switching via icon buttons
- **Battery Widget**:
  - Design capacity vs full charge capacity
  - Battery health percentage
  - Cycle count and manufacturer
  - PowerShell CIM-based queries (replaces WMIC)

## Architecture

### Services Layer
- `SystemMonitor`: CPU, memory, disk monitoring using psutil
- `ProcessManager`: Process enumeration with CPU caching for accurate readings
- `WindowsInfo`: System information retrieval using WMIC, PowerShell, platform
- `ServiceInfo`: Windows service management via psutil
- `EnterpriseInfo`: Domain, Azure AD, Group Policy information
- `TaskSchedulerInfo`: Task Scheduler interaction via schtasks command
- `DataCache[T]`: Generic caching with background loading

### UI Layer
- `MainWindow`: Main application window with sidebar navigation
- Tab implementations:
  - `SystemOverviewTab`: Live metrics with collapsible sections
  - `SystemTab`: Card-based system information
  - `ProcessesServicesTab`: Process and service management
  - `SoftwareTab`: Software inventory and startup
  - `EnterpriseTab`: Domain and Azure AD information
  - `TaskSchedulerTab`: Task Scheduler management

### Widgets
- `MetricTile`: Reusable tile for displaying metrics with progress bars
- `ExpandableMetricTile`: Tile with expandable details
- `CollapsibleSection`: Expandable/collapsible content section
- `FlowLayout`: Custom layout for natural key-value pair reflow
- `BatteryWidget`: Battery status display with health info
- `LoadingOverlay`: Loading indicator overlay
- `LiveGraph`: Real-time graph widget

### Utilities
- `formatters.py`: Data formatting (bytes, uptime, percentages)
- `thread_utils.py`: Threading workers (SingleRunWorker, LoopingWorker, CancellableWorker)

## Technology Stack
- Python 3.13
- PySide6 (Qt for Python)
- psutil (System monitoring)
- pywin32 (Windows-specific operations)
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

### FlowLayout
- Custom QLayout that arranges widgets horizontally
- Wraps to new rows when horizontal space exhausted
- Each key-value pair is a self-contained widget unit
- Implements `heightForWidth()` for proper container sizing
