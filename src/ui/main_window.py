"""Main Window for Windows Manager with sidebar navigation"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QStatusBar, QPushButton, QFrame,
    QSizePolicy, QSplitter
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction

from .system_overview_tab import SystemOverviewTab
from .system_tab import SystemTab
from .processes_services_tab import ProcessesServicesTab
from .storage_tab import StorageTab
from .device_manager_tab import DeviceManagerTab
from .enterprise_tab import EnterpriseTab
from .task_scheduler_tab import TaskSchedulerTab
from .theme import Colors


class NavButton(QPushButton):
    """Navigation button for sidebar."""

    def __init__(self, text: str, icon_char: str = "", parent=None):
        super().__init__(parent)
        display_text = f"{icon_char}  {text}" if icon_char else text
        self.setText(display_text)
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(40)
        self._update_style(False)

    def _update_style(self, selected: bool) -> None:
        """Update button styling based on selection state."""
        if selected:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.ACCENT.name()};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 10px 16px;
                    text-align: left;
                    font-size: 13px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {Colors.ACCENT_HOVER.name()};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Colors.TEXT_PRIMARY.name()};
                    border: none;
                    border-radius: 4px;
                    padding: 10px 16px;
                    text-align: left;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: {Colors.WIDGET_HOVER.name()};
                }}
            """)

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._update_style(checked)


class SidebarWidget(QFrame):
    """Sidebar widget with navigation buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedWidth(180)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.WINDOW_ALT.name()};
                border-right: 1px solid {Colors.BORDER.name()};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(4)

        # Navigation buttons with icons
        self._buttons = []

        self._overview_btn = NavButton("Overview", "📊")
        self._overview_btn.clicked.connect(lambda: self._on_nav_clicked(0))
        layout.addWidget(self._overview_btn)
        self._buttons.append(self._overview_btn)

        self._system_btn = NavButton("System", "💻")
        self._system_btn.clicked.connect(lambda: self._on_nav_clicked(1))
        layout.addWidget(self._system_btn)
        self._buttons.append(self._system_btn)

        self._processes_btn = NavButton("Processes", "⚙️")
        self._processes_btn.clicked.connect(lambda: self._on_nav_clicked(2))
        layout.addWidget(self._processes_btn)
        self._buttons.append(self._processes_btn)

        self._storage_btn = NavButton("Storage", "💾")
        self._storage_btn.clicked.connect(lambda: self._on_nav_clicked(3))
        layout.addWidget(self._storage_btn)
        self._buttons.append(self._storage_btn)

        self._devices_btn = NavButton("Devices", "🖥️")
        self._devices_btn.clicked.connect(lambda: self._on_nav_clicked(4))
        layout.addWidget(self._devices_btn)
        self._buttons.append(self._devices_btn)

        self._tasks_btn = NavButton("Tasks", "📅")
        self._tasks_btn.clicked.connect(lambda: self._on_nav_clicked(5))
        layout.addWidget(self._tasks_btn)
        self._buttons.append(self._tasks_btn)

        self._enterprise_btn = NavButton("Enterprise", "🏢")
        self._enterprise_btn.clicked.connect(lambda: self._on_nav_clicked(6))
        layout.addWidget(self._enterprise_btn)
        self._buttons.append(self._enterprise_btn)

        layout.addStretch()

        # Callback for navigation
        self._nav_callback = None

        # Select first by default
        self._overview_btn.setChecked(True)

    def set_nav_callback(self, callback) -> None:
        """Set callback for navigation changes."""
        self._nav_callback = callback

    def _on_nav_clicked(self, index: int) -> None:
        """Handle navigation button click."""
        # Update button states
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)

        # Call callback
        if self._nav_callback:
            self._nav_callback(index)

    def set_selected(self, index: int) -> None:
        """Set selected navigation item."""
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Windows Manager")
        self.setMinimumSize(900, 650)
        self.resize(1000, 750)

        self.init_ui()
        self.create_menu_bar()
        self.create_status_bar()

    def init_ui(self):
        """Initialize the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar navigation
        self._sidebar = SidebarWidget()
        self._sidebar.set_nav_callback(self._on_nav_changed)
        layout.addWidget(self._sidebar)

        # Content area with stacked widget
        self._content_stack = QStackedWidget()
        self._content_stack.setStyleSheet(f"""
            QStackedWidget {{
                background-color: {Colors.WINDOW.name()};
            }}
        """)

        # Add pages (same order as sidebar buttons)
        self.overview_tab = SystemOverviewTab()
        self.system_tab = SystemTab()
        self.processes_services_tab = ProcessesServicesTab()
        self.storage_tab = StorageTab()
        self.device_manager_tab = DeviceManagerTab()
        self.tasks_tab = TaskSchedulerTab()
        self.enterprise_tab = EnterpriseTab()

        self._content_stack.addWidget(self.overview_tab)       # 0
        self._content_stack.addWidget(self.system_tab)         # 1
        self._content_stack.addWidget(self.processes_services_tab)  # 2
        self._content_stack.addWidget(self.storage_tab)        # 3
        self._content_stack.addWidget(self.device_manager_tab) # 4
        self._content_stack.addWidget(self.tasks_tab)          # 5
        self._content_stack.addWidget(self.enterprise_tab)     # 6

        layout.addWidget(self._content_stack)

    @Slot(int)
    def _on_nav_changed(self, index: int) -> None:
        """Handle navigation change."""
        # Pause/resume overview tab workers based on visibility
        if index == 0:
            # Overview tab is now visible
            self.overview_tab.resume_updates()
        else:
            # Overview tab is now hidden
            self.overview_tab.pause_updates()

        # Lazy load tabs on first activation
        if index == 3:  # Storage tab
            self.storage_tab.on_tab_activated()
        elif index == 4:  # Devices tab
            self.device_manager_tab.on_tab_activated()
        elif index == 5:  # Tasks tab
            self.tasks_tab.on_tab_activated()
        elif index == 6:  # Enterprise tab
            self.enterprise_tab.on_tab_activated()

        self._content_stack.setCurrentIndex(index)

    def prewarm_caches(self) -> None:
        """
        Pre-warm caches in background after window is shown.

        Note: With lazy loading enabled for Storage, Devices, Tasks, and Enterprise tabs,
        we no longer prewarm those caches here. Data is loaded on first tab activation.
        """
        # Currently no prewarming needed - tabs use lazy loading
        pass

    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        refresh_action = QAction("&Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_data)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Navigation shortcuts
        overview_action = QAction("&Overview", self)
        overview_action.setShortcut("Ctrl+1")
        overview_action.triggered.connect(lambda: self._navigate_to(0))
        view_menu.addAction(overview_action)

        system_action = QAction("&System", self)
        system_action.setShortcut("Ctrl+2")
        system_action.triggered.connect(lambda: self._navigate_to(1))
        view_menu.addAction(system_action)

        processes_action = QAction("&Processes", self)
        processes_action.setShortcut("Ctrl+3")
        processes_action.triggered.connect(lambda: self._navigate_to(2))
        view_menu.addAction(processes_action)

        storage_action = QAction("S&torage", self)
        storage_action.setShortcut("Ctrl+4")
        storage_action.triggered.connect(lambda: self._navigate_to(3))
        view_menu.addAction(storage_action)

        devices_action = QAction("&Devices", self)
        devices_action.setShortcut("Ctrl+5")
        devices_action.triggered.connect(lambda: self._navigate_to(4))
        view_menu.addAction(devices_action)

        tasks_action = QAction("&Tasks", self)
        tasks_action.setShortcut("Ctrl+6")
        tasks_action.triggered.connect(lambda: self._navigate_to(5))
        view_menu.addAction(tasks_action)

        enterprise_action = QAction("&Enterprise", self)
        enterprise_action.setShortcut("Ctrl+7")
        enterprise_action.triggered.connect(lambda: self._navigate_to(6))
        view_menu.addAction(enterprise_action)

        view_menu.addSeparator()

        always_on_top_action = QAction("Always on &Top", self)
        always_on_top_action.setCheckable(True)
        always_on_top_action.triggered.connect(self.toggle_always_on_top)
        view_menu.addAction(always_on_top_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _navigate_to(self, index: int) -> None:
        """Navigate to a specific page."""
        self._sidebar.set_selected(index)
        self._on_nav_changed(index)

    def create_status_bar(self):
        """Create status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def refresh_data(self):
        """Refresh all data in current page"""
        current_widget = self._content_stack.currentWidget()
        if hasattr(current_widget, 'refresh'):
            current_widget.refresh()
        self.status_bar.showMessage("Data refreshed", 2000)

    def toggle_always_on_top(self, checked: bool):
        """Toggle always on top window flag"""
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

    def show_about(self):
        """Show about dialog"""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "About Windows Manager",
            "Windows Manager v0.2.0\n\n"
            "A unified Windows management application\n"
            "combining Task Manager, services.msc,\n"
            "Device Manager, and more.\n\n"
            "Built with Python and PySide6"
        )

    def closeEvent(self, event):
        """Clean up resources when closing."""
        if hasattr(self, 'overview_tab'):
            self.overview_tab.cleanup()
        if hasattr(self, 'storage_tab'):
            self.storage_tab.cleanup()
        event.accept()
