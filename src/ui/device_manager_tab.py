"""Device Manager Tab - Categorized device tree with detail panel."""

from typing import List, Dict, Optional
from collections import defaultdict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QSplitter, QTreeWidget, QTreeWidgetItem, QScrollArea,
    QFrame, QTextEdit, QMenu, QApplication, QGridLayout,
)
from PySide6.QtCore import Qt, Slot, QThreadPool
from PySide6.QtGui import QAction

from src.services.device_info import get_device_info, DeviceInfo
from src.services.data_cache import DataCache, CacheState
from src.utils.thread_utils import SingleRunWorker
from src.ui.theme import Colors
from src.ui.widgets.loading_indicator import LoadingOverlay


# Category icons by class_name
CATEGORY_ICONS: Dict[str, str] = {
    "Display": "🖥️",
    "Net": "🌐",
    "USB": "🔌",
    "MEDIA": "🎵",
    "Processor": "⚙️",
    "DiskDrive": "💾",
    "Monitor": "🖥️",
    "Keyboard": "⌨️",
    "Mouse": "🖱️",
    "HIDClass": "🎮",
    "Printer": "🖨️",
    "Battery": "🔋",
    "System": "⚙️",
    "AudioEndpoint": "🔊",
    "Bluetooth": "📡",
    "SCSIAdapter": "💿",
    "hdc": "💿",
    "Image": "📷",
    "Biometric": "👆",
    "Camera": "📷",
    "Firmware": "⚡",
    "SoftwareDevice": "📦",
    "SecurityDevices": "🔒",
    "WPD": "📱",
}


class DeviceDetailPanel(QFrame):
    """Detail panel for a selected device."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._device_info_service = get_device_info()
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet(f"""
            DeviceDetailPanel {{
                background-color: {Colors.WINDOW.name()};
            }}
        """)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(8)

        # Device name
        self._name_label = QLabel("Select a device")
        self._name_label.setStyleSheet(f"""
            font-size: 14px; font-weight: bold;
            color: {Colors.TEXT_PRIMARY.name()};
        """)
        self._name_label.setWordWrap(True)
        self._layout.addWidget(self._name_label)

        # Status
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 12px;")
        self._layout.addWidget(self._status_label)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {Colors.BORDER.name()};")
        self._layout.addWidget(sep)

        # Device info grid
        info_header = QLabel("Device Information")
        info_header.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {Colors.ACCENT.name()};")
        self._layout.addWidget(info_header)

        self._info_grid = QGridLayout()
        self._info_grid.setContentsMargins(0, 0, 0, 0)
        self._info_grid.setHorizontalSpacing(12)
        self._info_grid.setVerticalSpacing(4)
        self._info_grid.setColumnMinimumWidth(0, 90)
        self._layout.addLayout(self._info_grid)

        # Driver info grid (populated lazily)
        self._driver_header = QLabel("Driver Information")
        self._driver_header.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {Colors.ACCENT.name()};")
        self._driver_header.setVisible(False)
        self._layout.addWidget(self._driver_header)

        self._driver_grid = QGridLayout()
        self._driver_grid.setContentsMargins(0, 0, 0, 0)
        self._driver_grid.setHorizontalSpacing(12)
        self._driver_grid.setVerticalSpacing(4)
        self._driver_grid.setColumnMinimumWidth(0, 90)
        self._layout.addLayout(self._driver_grid)

        # Hardware IDs section
        hw_header = QLabel("Hardware IDs")
        hw_header.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {Colors.ACCENT.name()};")
        self._layout.addWidget(hw_header)

        self._hw_ids_edit = QTextEdit()
        self._hw_ids_edit.setReadOnly(True)
        self._hw_ids_edit.setMaximumHeight(80)
        self._hw_ids_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Colors.WIDGET.name()};
                color: {Colors.TEXT_PRIMARY.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
                font-family: Consolas, monospace;
                font-size: 11px;
                padding: 4px;
            }}
        """)
        self._layout.addWidget(self._hw_ids_edit)

        self._layout.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _clear_grid(self, grid: QGridLayout) -> None:
        """Remove all widgets from a grid layout."""
        while grid.count():
            item = grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _add_grid_row(self, grid: QGridLayout, row: int, key: str, value: str) -> None:
        """Add a key-value row to a grid layout."""
        k = QLabel(f"{key}:")
        k.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px;")
        k.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        grid.addWidget(k, row, 0)

        v = QLabel(str(value))
        v.setStyleSheet(f"color: {Colors.TEXT_PRIMARY.name()}; font-size: 11px;")
        v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.setWordWrap(True)
        grid.addWidget(v, row, 1)

    def show_device(self, device: Dict) -> None:
        """Populate the panel with device data."""
        self._name_label.setText(device.get("name", "Unknown"))

        # Status with RAG color
        problem = device.get("problem_code", 0)
        if problem == 0:
            status_text = "Working properly"
            color = Colors.SUCCESS.name()
        else:
            status_text = DeviceInfo.get_problem_description(problem)
            color = Colors.ERROR.name()
        self._status_label.setText(f"● {status_text}")
        self._status_label.setStyleSheet(f"color: {color}; font-size: 12px;")

        # Device info grid
        self._clear_grid(self._info_grid)
        info_pairs = [
            ("Manufacturer", device.get("manufacturer", "")),
            ("Class", device.get("class_name", "")),
            ("Class GUID", device.get("class_guid", "")),
            ("Service", device.get("service", "")),
            ("Enumerator", device.get("enumerator", "")),
            ("Location", device.get("location", "")),
            ("Device ID", device.get("device_id", "")),
        ]
        row = 0
        for key, val in info_pairs:
            if val:
                self._add_grid_row(self._info_grid, row, key, val)
                row += 1

        # Hardware IDs
        hw_ids = device.get("hardware_ids", [])
        self._hw_ids_edit.setText("\n".join(hw_ids) if hw_ids else "(none)")

        # Clear driver info, load lazily
        self._clear_grid(self._driver_grid)
        self._driver_header.setVisible(False)

        # Load driver details in background
        worker = SingleRunWorker(self._device_info_service.get_driver_details, device)
        worker.signals.result.connect(self._on_driver_details_loaded)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _on_driver_details_loaded(self, details: Dict[str, str]) -> None:
        """Populate driver info section."""
        if not details:
            return

        self._clear_grid(self._driver_grid)
        for row, (key, val) in enumerate(details.items()):
            self._add_grid_row(self._driver_grid, row, key, val)
        self._driver_header.setVisible(True)


class DeviceManagerTab(QWidget):
    """Tab for device management with categorized tree and detail panel."""

    def __init__(self):
        super().__init__()
        self._device_cache = DataCache(get_device_info().get_all_devices, fallback_value=[])
        self._all_devices: List[Dict] = []
        self._data_loaded = False
        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Top bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search devices by name, manufacturer, or ID...")
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.setStyleSheet(
            f"padding: 6px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        top_bar.addWidget(self._search_input)

        self._count_label = QLabel("0 devices")
        self._count_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px; padding: 2px 8px;"
        )
        top_bar.addWidget(self._count_label)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh)
        refresh_btn.setStyleSheet(
            f"padding: 6px 12px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        top_bar.addWidget(refresh_btn)

        layout.addLayout(top_bar)

        # Splitter: tree | detail
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Colors.BORDER.name()};
                width: 1px;
            }}
        """)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(250)
        self._tree.currentItemChanged.connect(self._on_tree_selection_changed)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QTreeWidget::item {{
                padding: 3px 0;
            }}
            QTreeWidget::item:selected {{
                background-color: {Colors.ACCENT.name()};
                color: white;
            }}
        """)
        splitter.addWidget(self._tree)

        # Detail panel
        self._detail_panel = DeviceDetailPanel()
        splitter.addWidget(self._detail_panel)

        splitter.setSizes([280, 520])
        layout.addWidget(splitter)

        # Status label (compact)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px; padding: 2px 0;"
        )
        self._status_label.setFixedHeight(20)
        layout.addWidget(self._status_label)

        # Loading overlay on the tree
        self._loading_overlay = LoadingOverlay(self._tree)

    def _connect_signals(self) -> None:
        self._device_cache.state_changed.connect(self._on_cache_state_changed)
        self._device_cache.data_loaded.connect(self._on_devices_loaded)
        self._device_cache.error_occurred.connect(self._on_cache_error)

    @Slot(CacheState)
    def _on_cache_state_changed(self, state: CacheState) -> None:
        if state == CacheState.LOADING:
            self._search_input.setEnabled(False)
            self._loading_overlay.show_loading("Loading devices...")
        elif state in (CacheState.LOADED, CacheState.ERROR):
            self._search_input.setEnabled(True)
            self._loading_overlay.hide_loading()

    @Slot(object)
    def _on_devices_loaded(self, devices: List[Dict]) -> None:
        self._all_devices = devices
        self._populate_tree(devices)

    @Slot(str)
    def _on_cache_error(self, error_msg: str) -> None:
        self._status_label.setText(f"Error: {error_msg}")

    def _populate_tree(self, devices: List[Dict]) -> None:
        """Build categorized tree from device list."""
        self._tree.clear()
        search_text = self._search_input.text().lower()

        # Filter
        if search_text:
            devices = [
                d for d in devices
                if search_text in d.get("name", "").lower()
                or search_text in d.get("manufacturer", "").lower()
                or search_text in d.get("device_id", "").lower()
            ]

        # Group by class_name
        categories: Dict[str, List[Dict]] = defaultdict(list)
        for dev in devices:
            cat = dev.get("class_name") or "Other devices"
            categories[cat].append(dev)

        problem_count = 0
        total_count = len(devices)

        # Sort categories alphabetically, "Other devices" last
        sorted_cats = sorted(categories.keys(), key=lambda c: (c == "Other devices", c))

        for cat in sorted_cats:
            cat_devices = categories[cat]
            icon = CATEGORY_ICONS.get(cat, "📁")
            cat_item = QTreeWidgetItem(self._tree)
            cat_item.setText(0, f"{icon}  {cat} ({len(cat_devices)})")
            cat_item.setExpanded(True)

            for dev in sorted(cat_devices, key=lambda d: d.get("name", "")):
                dev_item = QTreeWidgetItem(cat_item)
                dev_item.setData(0, Qt.ItemDataRole.UserRole, dev)

                prefix = ""
                if dev.get("has_problem"):
                    prefix = "⚠ "
                    dev_item.setForeground(0, Colors.ERROR)
                    problem_count += 1

                dev_item.setText(0, f"{prefix}{dev.get('name', 'Unknown')}")

        self._count_label.setText(f"{total_count} devices")
        parts = [f"{total_count} devices in {len(categories)} categories"]
        if problem_count:
            parts.append(f"{problem_count} problems")
        self._status_label.setText(", ".join(parts))

    @Slot()
    def _on_tree_selection_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem) -> None:
        if not current:
            return
        device = current.data(0, Qt.ItemDataRole.UserRole)
        if device:
            self._detail_panel.show_device(device)

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        if self._all_devices:
            self._populate_tree(self._all_devices)

    @Slot()
    def _on_refresh(self) -> None:
        self._device_cache.refresh()

    @Slot()
    def _show_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if not item:
            return
        device = item.data(0, Qt.ItemDataRole.UserRole)
        if not device:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Colors.WINDOW_ALT.name()};
                color: {Colors.TEXT_PRIMARY.name()};
                border: 1px solid {Colors.BORDER.name()};
            }}
            QMenu::item {{ padding: 6px 20px; }}
            QMenu::item:selected {{ background-color: {Colors.ACCENT.name()}; }}
        """)

        copy_name = QAction("Copy Name", self)
        copy_name.triggered.connect(lambda: QApplication.clipboard().setText(device.get("name", "")))
        menu.addAction(copy_name)

        copy_id = QAction("Copy Device ID", self)
        copy_id.triggered.connect(lambda: QApplication.clipboard().setText(device.get("device_id", "")))
        menu.addAction(copy_id)

        hw_ids = device.get("hardware_ids", [])
        if hw_ids:
            copy_hw = QAction("Copy Hardware IDs", self)
            copy_hw.triggered.connect(lambda: QApplication.clipboard().setText("\n".join(hw_ids)))
            menu.addAction(copy_hw)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def on_tab_activated(self) -> None:
        """Called when this tab becomes visible. Loads data on first activation."""
        if not self._data_loaded:
            self._data_loaded = True
            self._device_cache.load()

    def refresh(self):
        """Refresh the data in this tab."""
        self._device_cache.refresh()
