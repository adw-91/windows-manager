"""Main Window for Windows Manager"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QStatusBar, QMenuBar, QMenu
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from .system_overview_tab import SystemOverviewTab
from .system_tab import SystemTab
from .processes_services_tab import ProcessesServicesTab
from .drivers_tab import DriversTab
from .enterprise_tab import EnterpriseTab


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Windows Manager")
        self.setMinimumSize(700, 600)
        self.resize(700, 700)  # Start at minimum width

        self.init_ui()
        self.create_menu_bar()
        self.create_status_bar()

    def init_ui(self):
        """Initialize the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 8, 0, 0)  # Add top margin below menu bar

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)

        # Add tabs
        self.overview_tab = SystemOverviewTab()
        self.system_tab = SystemTab()
        self.processes_services_tab = ProcessesServicesTab()
        self.drivers_tab = DriversTab()
        self.enterprise_tab = EnterpriseTab()

        self.tab_widget.addTab(self.overview_tab, "Overview")
        self.tab_widget.addTab(self.system_tab, "System")
        self.tab_widget.addTab(self.processes_services_tab, "Processes && Services")
        self.tab_widget.addTab(self.drivers_tab, "Drivers")
        self.tab_widget.addTab(self.enterprise_tab, "Enterprise")

        layout.addWidget(self.tab_widget)

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

        always_on_top_action = QAction("Always on &Top", self)
        always_on_top_action.setCheckable(True)
        always_on_top_action.triggered.connect(self.toggle_always_on_top)
        view_menu.addAction(always_on_top_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_status_bar(self):
        """Create status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def refresh_data(self):
        """Refresh all data in current tab"""
        current_tab = self.tab_widget.currentWidget()
        if hasattr(current_tab, 'refresh'):
            current_tab.refresh()
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
            "Windows Manager v0.1.0\n\n"
            "A lean combined system manager for Windows\n"
            "Built with Python and PySide6"
        )

    def closeEvent(self, event):
        """Clean up resources when closing."""
        # Stop overview tab workers
        if hasattr(self, 'overview_tab'):
            self.overview_tab.cleanup()
        event.accept()
