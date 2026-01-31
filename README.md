# Windows Manager

A lean combined system manager for Microsoft Windows that consolidates disparate views and reduces system noise.

## Overview

Windows Manager aims to provide a unified, streamlined interface for managing Windows system resources, processes, and services. Instead of juggling multiple built-in Windows tools (Task Manager, Resource Monitor, Services, Event Viewer, etc.), this tool brings essential information together in one clean interface.

## Features

### Current (v0.1.0)

**Overview Tab**:
- Live metrics dashboard with auto-refresh (2s intervals)
  - CPU usage percentage with progress indicator
  - Memory usage with GB breakdown
  - Disk usage across all drives
  - System uptime display
- Comprehensive system information table:
  - System name, manufacturer
  - OS version, locale, timezone
  - Processor model (via WMIC)
  - Memory details with per-stick capacity (e.g., "15.8 GB (7.9 GB x2)")
  - Total disk space, network adapter info
  - Domain/Workgroup status

**Additional Tabs** (placeholders):
- System: Detailed hardware, drivers, BIOS info
- Processes & Services: Task manager + services.msc integration
- Software: Installed programs + startup management
- Enterprise: Domain, Azure AD, Group Policy information

### Planned

- Process and service management with kill/restart capabilities
- Performance graphs and historical data
- Startup program management
- Installed software inventory
- Windows Update status
- Event log viewer integration

## Project Structure

```
WinManager/
├── src/
│   ├── ui/              # PySide6 UI components
│   ├── services/        # System interaction services
│   └── utils/           # Utility functions
├── tests/               # Test files
├── docs/                # Documentation
├── venv/                # Python virtual environment
└── .claude/             # Claude AI configuration
```

## Technology Stack

- Python 3.13
- PySide6 (Qt for Python) - UI Framework
- psutil - System and process monitoring
- pywin32 - Windows-specific operations

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
