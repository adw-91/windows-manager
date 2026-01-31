"""System Tab - Deeper system info, drivers, hardware"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Slot, QThreadPool

from src.ui.widgets.collapsible_section import CollapsibleSection
from src.ui.widgets.info_table import InfoTable
from src.services.windows_info import WindowsInfo
from src.utils.thread_utils import SingleRunWorker


class SystemTab(QWidget):
    """Tab for detailed system information"""

    def __init__(self):
        super().__init__()
        self._windows_info = WindowsInfo()
        self._loading_label = None
        self._system_info_table = None
        self._hardware_table = None
        self._os_table = None
        self._worker = None
        self.init_ui()
        self._load_system_info()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header with refresh button
        header_layout = QHBoxLayout()
        title = QLabel("System Information")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_button)

        layout.addLayout(header_layout)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        # Loading state
        self._loading_label = QLabel("Loading system information...")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet("color: gray; font-style: italic;")
        content_layout.addWidget(self._loading_label)

        # System Information section
        self._system_section = CollapsibleSection("System Information", expanded=True)
        self._system_info_table = InfoTable()
        self._system_section.set_content(self._system_info_table)
        content_layout.addWidget(self._system_section)
        self._system_section.setVisible(False)

        # Hardware section
        self._hardware_section = CollapsibleSection("Hardware", expanded=True)
        self._hardware_table = InfoTable()
        self._hardware_section.set_content(self._hardware_table)
        content_layout.addWidget(self._hardware_section)
        self._hardware_section.setVisible(False)

        # Operating System section
        self._os_section = CollapsibleSection("Operating System", expanded=True)
        self._os_table = InfoTable()
        self._os_section.set_content(self._os_table)
        content_layout.addWidget(self._os_section)
        self._os_section.setVisible(False)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _load_system_info(self):
        """Load system information in background"""
        self._loading_label.setVisible(True)
        self._system_section.setVisible(False)
        self._hardware_section.setVisible(False)
        self._os_section.setVisible(False)

        # Cancel any existing worker
        if self._worker:
            self._worker.signals.finished.disconnect()

        # Create and start worker
        self._worker = SingleRunWorker(self._windows_info.get_all_system_info)
        self._worker.signals.result.connect(self._on_data_loaded)
        self._worker.signals.error.connect(self._on_data_error)
        self._worker.signals.finished.connect(self._on_load_finished)

        QThreadPool.globalInstance().start(self._worker)

    @Slot(object)
    def _on_data_loaded(self, data: dict):
        """Handle loaded system information"""
        if not isinstance(data, dict):
            return

        # Organize data into sections
        system_info = {}
        hardware_info = {}
        os_info = {}

        # System section
        if "System Name" in data:
            system_info["System Name"] = data["System Name"]
        if "Manufacturer" in data:
            system_info["Manufacturer"] = data["Manufacturer"]
        if "Model" in data:
            system_info["Model"] = data["Model"]
        if "Domain/Workgroup" in data:
            system_info["Domain/Workgroup"] = data["Domain/Workgroup"]

        # Hardware section
        if "Processor" in data:
            hardware_info["Processor"] = data["Processor"]
        if "Total Memory" in data:
            hardware_info["Total Memory"] = data["Total Memory"]
        if "Total Disk Space" in data:
            hardware_info["Total Disk Space"] = data["Total Disk Space"]
        if "Connected Network" in data:
            hardware_info["Network Adapter"] = data["Connected Network"]
        if "BIOS Version" in data:
            hardware_info["BIOS Version"] = data["BIOS Version"]

        # OS section
        if "OS Version" in data:
            os_info["OS Version"] = data["OS Version"]
        if "OS Build" in data:
            os_info["OS Build"] = data["OS Build"]
        if "Architecture" in data:
            os_info["Architecture"] = data["Architecture"]
        if "System Locale" in data:
            os_info["System Locale"] = data["System Locale"]
        if "Time Zone" in data:
            os_info["Time Zone"] = data["Time Zone"]

        # Update UI
        if system_info:
            self._system_info_table.set_data(system_info)
            self._system_section.setVisible(True)

        if hardware_info:
            self._hardware_table.set_data(hardware_info)
            self._hardware_section.setVisible(True)

        if os_info:
            self._os_table.set_data(os_info)
            self._os_section.setVisible(True)

    @Slot(str)
    def _on_data_error(self, error_msg: str):
        """Handle error loading system information"""
        self._loading_label.setText(f"Error loading system information: {error_msg}")
        self._loading_label.setStyleSheet("color: red;")

    @Slot()
    def _on_load_finished(self):
        """Handle load finished"""
        # Hide loading label if sections are visible
        if self._system_section.isVisible() or self._hardware_section.isVisible() or self._os_section.isVisible():
            self._loading_label.setVisible(False)

    def refresh(self):
        """Refresh the data in this tab"""
        self._load_system_info()
