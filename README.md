# Windows Manager

A lean combined system manager for Microsoft Windows that consolidates disparate views and reduces system noise.

## Overview

Windows Manager provides a unified interface for managing Windows system resources, processes, and services. Instead of juggling multiple built-in tools (Task Manager, Resource Monitor, Services, msinfo32, etc.), this tool brings essential information together in one clean interface.

## Features

- **Overview** - Live metrics dashboard (CPU, memory, disk, uptime) with real-time graphs
- **System** - Comprehensive system information (msinfo32-style) in card-based layout
- **Processes & Services** - Process monitoring with RAG coloring, service management
- **Software** - Installed programs inventory and startup management
- **Enterprise** - User info, Entra ID status, domain/workgroup, Group Policy
- **Task Scheduler** - View and manage scheduled tasks

See [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) for detailed feature documentation.

## Technology Stack

- Python 3.13 / PySide6
- psutil, pywin32, pyqtgraph

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

## License

MIT
