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

- **System Information Table**: Static system details displayed in a vertical table format:
  - System Name (hostname)
  - Processor (CPU model)
  - Total Memory (with number of RAM sticks)
  - Total Disk Space (across all drives)
  - Connected Network (active adapter with IP)
  - OS Version
  - Domain/Workgroup

- **Layout**:
  - Top: 4 metric tiles spanning full width
  - Bottom: Split 40/60 horizontally
    - Left 40%: System information table
    - Right 60%: Placeholder for future content

- **Auto-refresh**: Metrics update every 2 seconds

### Other Tabs (Placeholder)
- **System**: Deeper system info, drivers, hardware details
- **Processes & Services**: Combined process and service management
  - Sub-tabs for Processes and Services
- **Software**: Installed programs and startup management
  - Sub-tabs for Installed Programs and Startup
- **Enterprise**: Domain, workgroup, Azure AD information

## Architecture

### Services Layer
- `SystemMonitor`: CPU, memory, disk monitoring using psutil
- `ProcessManager`: Process enumeration and management
- `WindowsInfo`: System information retrieval using wmic and platform

### UI Layer
- `MainWindow`: Main application window with tab structure
- `SystemOverviewTab`: Live metrics and system info display
- **Widgets**:
  - `MetricTile`: Reusable tile for displaying metrics with progress bars
  - `InfoTable`: Vertical table widget for label:value pairs

### Utilities
- `formatters.py`: Data formatting (bytes, uptime, percentages)

## Technology Stack
- Python 3.13
- PySide6 (Qt for Python)
- psutil (System monitoring)
- pywin32 (Windows-specific operations)
- subprocess (WMIC commands for detailed Windows info)

## Next Steps
- Populate System tab with detailed hardware information
- Implement process management in Processes & Services tab
- Add services management functionality
- Implement software inventory and startup management
- Add enterprise/domain information display
- Add graphs and charts for performance history
