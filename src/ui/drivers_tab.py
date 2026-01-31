"""Drivers Tab - Device drivers and hardware management"""

from typing import List, Dict
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QLineEdit, QPushButton, QLabel, QHeaderView
from PySide6.QtCore import Qt, Slot, Signal

from src.ui.theme import Colors
from src.ui.widgets.loading_indicator import LoadingOverlay
from src.services.data_cache import DataCache, CacheState
from src.services.driver_info import get_driver_info


class DriversTableWidget(QWidget):
    """
    Table widget for displaying Windows system drivers.

    Features:
    - Sortable columns: Name, Display Name, State, Start Mode, Path, Description
    - Real-time search/filter
    - Loading state with overlay
    - Refresh button
    - Async data loading support
    """

    # Signals
    refresh_requested = Signal()  # Emitted when user clicks refresh button

    # Column indices
    COL_NAME = 0
    COL_DISPLAY_NAME = 1
    COL_STATE = 2
    COL_START_MODE = 3
    COL_PATH = 4
    COL_DESCRIPTION = 5

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._all_drivers: List[Dict[str, str]] = []
        self._filtered_drivers: List[Dict[str, str]] = []
        self._is_loading = False

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Top bar: Search and Refresh
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Search box
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search by name, display name, state, or path...")
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.setStyleSheet(
            f"padding: 6px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        top_bar.addWidget(self._search_input)

        # Refresh button
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.clicked.connect(self._on_refresh_clicked)
        self._refresh_button.setStyleSheet(
            f"padding: 6px 12px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        top_bar.addWidget(self._refresh_button)

        layout.addLayout(top_bar)

        # Count label
        self._count_label = QLabel("0 drivers")
        self._count_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px; padding: 2px 0;"
        )
        layout.addWidget(self._count_label)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "Name",
            "Display Name",
            "State",
            "Start Mode",
            "Path",
            "Description"
        ])

        # Table styling
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)

        # Column sizing
        header = self._table.horizontalHeader()

        # Set all columns to Interactive mode (user can drag to resize)
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        # Last column stretches to fill remaining space
        header.setStretchLastSection(True)

        # Set initial column widths
        self._table.setColumnWidth(self.COL_NAME, 150)
        self._table.setColumnWidth(self.COL_DISPLAY_NAME, 180)
        self._table.setColumnWidth(self.COL_STATE, 100)
        self._table.setColumnWidth(self.COL_START_MODE, 100)
        self._table.setColumnWidth(self.COL_PATH, 300)
        # Description stretches to fill remaining space

        # Dark theme styling
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                gridline-color: {Colors.BORDER.name()};
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            QTableWidget::item:selected {{
                background-color: {Colors.ACCENT.name()};
                color: white;
            }}
            QHeaderView::section {{
                background-color: {Colors.TABLE_HEADER.name()};
                border: 1px solid {Colors.BORDER.name()};
                padding: 6px;
                font-weight: bold;
                color: {Colors.TEXT_PRIMARY.name()};
            }}
        """)

        layout.addWidget(self._table)

        # Loading overlay (hidden by default)
        self._loading_overlay = LoadingOverlay(self._table)

    def set_loading(self, is_loading: bool) -> None:
        """
        Set loading state.

        Args:
            is_loading: True to show loading state, False to hide
        """
        self._is_loading = is_loading
        self._refresh_button.setEnabled(not is_loading)
        self._search_input.setEnabled(not is_loading)

        if is_loading:
            self._loading_overlay.show_loading("Loading drivers...")
            self._show_skeleton_rows()
        else:
            self._loading_overlay.hide_loading()

    def set_data(self, drivers_list: List[Dict[str, str]]) -> None:
        """
        Set the drivers data to display.

        Args:
            drivers_list: List of driver dicts with Name, DisplayName, PathName, State, StartMode, Description
        """
        self._all_drivers = drivers_list
        self._apply_filter()

    def clear(self) -> None:
        """Clear the table."""
        self._all_drivers = []
        self._filtered_drivers = []
        self._table.setRowCount(0)
        self._update_count_label()

    def _show_skeleton_rows(self) -> None:
        """Show skeleton rows during loading."""
        self._table.setSortingEnabled(False)
        self._table.setRowCount(10)  # Show 10 skeleton rows

        for row in range(10):
            for col in range(6):
                # Create empty items for skeleton effect
                item = QTableWidgetItem("")
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # Not selectable
                item.setBackground(Colors.WIDGET_HOVER)
                self._table.setItem(row, col, item)

    def _apply_filter(self) -> None:
        """Apply current search filter and update table."""
        search_text = self._search_input.text().lower()

        if not search_text:
            self._filtered_drivers = self._all_drivers
        else:
            self._filtered_drivers = [
                driver for driver in self._all_drivers
                if search_text in driver.get("Name", "").lower()
                or search_text in driver.get("DisplayName", "").lower()
                or search_text in driver.get("State", "").lower()
                or search_text in driver.get("PathName", "").lower()
            ]

        self._populate_table()

    def _populate_table(self) -> None:
        """Populate table with filtered driver data."""
        self._table.setSortingEnabled(False)  # Disable while populating
        self._table.setRowCount(len(self._filtered_drivers))

        for row, driver in enumerate(self._filtered_drivers):
            # Name
            name_item = QTableWidgetItem(driver.get("Name", ""))
            self._table.setItem(row, self.COL_NAME, name_item)

            # Display Name
            display_name_item = QTableWidgetItem(driver.get("DisplayName", ""))
            self._table.setItem(row, self.COL_DISPLAY_NAME, display_name_item)

            # State
            state_item = QTableWidgetItem(driver.get("State", ""))
            self._table.setItem(row, self.COL_STATE, state_item)

            # Start Mode
            start_mode_item = QTableWidgetItem(driver.get("StartMode", ""))
            self._table.setItem(row, self.COL_START_MODE, start_mode_item)

            # Path
            path_item = QTableWidgetItem(driver.get("PathName", ""))
            self._table.setItem(row, self.COL_PATH, path_item)

            # Description
            description_item = QTableWidgetItem(driver.get("Description", ""))
            self._table.setItem(row, self.COL_DESCRIPTION, description_item)

        self._table.setSortingEnabled(True)  # Re-enable sorting
        self._update_count_label()

    def _update_count_label(self) -> None:
        """Update the count label."""
        count = len(self._filtered_drivers)
        total = len(self._all_drivers)

        if count == total:
            self._count_label.setText(f"{count} driver{'s' if count != 1 else ''}")
        else:
            self._count_label.setText(
                f"{count} of {total} driver{'s' if total != 1 else ''}"
            )

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        if not self._is_loading:
            self._apply_filter()

    @Slot()
    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        self.refresh_requested.emit()


class DriversTab(QWidget):
    """Tab for drivers and device management"""

    def __init__(self):
        super().__init__()
        self._driver_cache = DataCache(get_driver_info().get_all_drivers, fallback_value=[])
        self._table_widget = DriversTableWidget(self)

        self.init_ui()
        self._connect_signals()
        self._load_drivers()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self._table_widget)

    def _connect_signals(self) -> None:
        """Connect data cache and table signals."""
        # Cache signals
        self._driver_cache.state_changed.connect(self._on_cache_state_changed)
        self._driver_cache.data_loaded.connect(self._on_drivers_loaded)
        self._driver_cache.error_occurred.connect(self._on_cache_error)

        # Table signals
        self._table_widget.refresh_requested.connect(self._on_refresh_requested)

    def _load_drivers(self) -> None:
        """Load drivers in background."""
        self._driver_cache.load()

    @Slot(CacheState)
    def _on_cache_state_changed(self, state: CacheState) -> None:
        """Handle cache state change."""
        if state == CacheState.LOADING:
            self._table_widget.set_loading(True)
        elif state in (CacheState.LOADED, CacheState.ERROR):
            self._table_widget.set_loading(False)

    @Slot(object)
    def _on_drivers_loaded(self, drivers: List[Dict[str, str]]) -> None:
        """Handle successful driver load."""
        self._table_widget.set_data(drivers)

    @Slot(str)
    def _on_cache_error(self, error_msg: str) -> None:
        """Handle cache error."""
        # Try to display cached data if available, or show empty
        drivers = self._driver_cache.get_data(use_fallback=True) or []
        self._table_widget.set_data(drivers)

    @Slot()
    def _on_refresh_requested(self) -> None:
        """Handle refresh request from table."""
        self._driver_cache.refresh()

    def refresh(self):
        """Refresh the data in this tab"""
        self._driver_cache.refresh()
