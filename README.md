# Windows Manager

A lean combined system manager for Microsoft Windows that consolidates disparate views and reduces system noise.

## Overview

Windows Manager provides a unified, streamlined interface for managing Windows system resources, processes, and services. Instead of juggling multiple built-in Windows tools (Task Manager, Resource Monitor, Services, Event Viewer, etc.), this tool brings essential information together in one clean interface.

## Features

### Overview Tab
- Live metrics dashboard with auto-refresh (2s intervals)
  - CPU usage percentage with progress indicator
  - Memory usage with GB breakdown
  - Disk usage across all drives
  - System uptime display
- Collapsible sections that expand to fill vertical space
- Quick-access system information

### System Tab
- Card-based UI with msinfo32-style comprehensive system information
- Categories: System Summary, Hardware, Components, Software, Security, Network
- FlowLayout for natural key-value pair reflow on window resize
- Real-time data collection via WMI, PowerShell, and psutil

### Processes & Services Tab
- **Processes**: Real-time process monitoring with 1-second refresh
  - CPU and memory usage with RAG (Red/Amber/Green) coloring
  - Ctrl key pauses sorting for easy process inspection
  - System Idle Process with inverted RAG colors (high idle = green)
  - End task functionality with confirmation
  - Context menu for quick actions
- **Services**: Full service management
  - Start, Stop, Restart capabilities
  - RAG status coloring (Running=green, Stopped=amber)
  - Search/filter functionality

### Software Tab
- **Installed Programs**: Registry-based software inventory
- **Startup**: Startup program management

### Enterprise Tab
- **Current User**: Username, domain, SID, admin status
- **Entra ID**: Azure AD join status, tenant info
- **Domain**: Computer name, domain/workgroup, domain controller
- **Group Policy**: GPO application status and policies

### Task Scheduler Tab
- Modern UI for Windows Task Scheduler management
- Folder tree navigation
- Task management: Run, Enable, Disable, End
- Custom "New Task" dialog for creating scheduled tasks
- RAG coloring for task status and results

### Battery Widget (Sidebar)
- Design capacity vs full charge capacity
- Battery health percentage
- Cycle count and manufacturer info
- PowerShell CIM-based data collection

## Project Structure

```
WinManager/
├── src/
│   ├── ui/              # PySide6 UI components
│   │   ├── widgets/     # Reusable widgets (FlowLayout, MetricTile, etc.)
│   │   └── *.py         # Tab implementations
│   ├── services/        # System interaction services
│   └── utils/           # Utility functions
├── tests/               # Test files
├── docs/                # Documentation
└── plan/                # Development plans
```

## Technology Stack

- Python 3.13
- PySide6 (Qt for Python) - UI Framework
- psutil - System and process monitoring
- pywin32 - Windows-specific operations
- PowerShell/CIM - Battery and system queries
- schtasks - Task Scheduler interaction

## Getting Started

### Prerequisites

- Python 3.13+
- Windows 10/11
- Administrator privileges (for some system operations)

### Installation

1. Create and activate virtual environment:
```bash
python -m venv venv
venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Running the Application

Using the convenience scripts:
```bash
run.bat          # Windows CMD
./run.sh         # Git Bash
```

Or directly with Python:
```bash
python -m src.main
```

Or from activated virtual environment:
```bash
venv\Scripts\python -m src.main
```

### Development

Run tests:
```bash
python -m unittest discover tests
```

Run specific test:
```bash
python -m unittest tests.test_system_monitor
```

## Contributing

Contributions are welcome! Please ensure code passes linting and tests before submitting PRs.

## License

MIT
