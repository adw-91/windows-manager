# Windows Manager

A lean combined system manager for Microsoft Windows that consolidates disparate views and reduces system noise.

## Overview

Windows Manager provides a unified interface for managing Windows system resources, processes, and services. Instead of juggling multiple built-in tools (Task Manager, Resource Monitor, Services, msinfo32, Device Manager, etc.), this tool brings essential information together in one clean interface.

## Features

- **Overview** — Live metrics dashboard (CPU, memory, disk, network) with real-time graphs, installed software, startup apps, battery health
- **System** — Comprehensive system information (msinfo32-style) with tabbed sub-sections: Summary, Hardware, Components, Security & BitLocker, TPM, Network, Boot & Firmware
- **Processes & Services** — Process monitoring with RAG coloring, service management (start/stop/restart)
- **Storage** — Drive overview tiles with RAG usage bars, on-demand recursive directory size scanning with cancellation
- **Devices** — Native Device Manager with categorized device tree, driver details, and problem code indicators (~50ms enumeration via SetupAPI)
- **Task Scheduler** — View, create, and manage scheduled tasks with schedule configuration
- **Enterprise** — User info, Entra ID status, domain/workgroup, Group Policy

See [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) for detailed feature documentation.

## Technology Stack

- Python 3.13 / PySide6
- psutil, pywin32, pyqtgraph, numpy
- Native Win32 APIs via ctypes:
  - NtQuerySystemInformation (process enumeration)
  - SetupAPI / CfgMgr32 (device enumeration)
  - TBS (TPM detection)
  - kernel32, userenv (system info, security)

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

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+1 | Overview |
| Ctrl+2 | System |
| Ctrl+3 | Processes & Services |
| Ctrl+4 | Storage |
| Ctrl+5 | Devices |
| Ctrl+6 | Tasks |
| Ctrl+7 | Enterprise |
| F5 | Refresh current tab |

### Development

Run tests:
```bash
python -m pytest tests/ -v
```

## License

MIT
