"""
Software table widget for displaying installed applications.

Provides searchable, sortable table with loading states and refresh capability.
"""

from typing import List, Dict, Optional
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QPushButton,
    QLabel,
    QHeaderView,
)

from src.ui.theme import Colors
from src.ui.widgets.loading_indicator import SkeletonRow, LoadingOverlay
from src.services.data_cache import CacheState


class SoftwareTableWidget(QWidget):
    """
    Table widget for displaying installed software.

    Features:
    - Sortable columns: Name, Publisher, Version, Install Date, Size,
      Install Location, Install Source, Uninstall String, Modify Path
    - Real-time search/filter
    - Loading state with skeleton rows
    - Refresh button
    - Async data loading support
    """

    # Signals
    refresh_requested = Signal()  # Emitted when user clicks refresh button

    # Column indices
    COL_NAME = 0
    COL_PUBLISHER = 1
    COL_VERSION = 2
    COL_INSTALL_DATE = 3
    COL_SIZE = 4
    COL_INSTALL_LOCATION = 5
    COL_INSTALL_SOURCE = 6
    COL_UNINSTALL_STRING = 7
    COL_MODIFY_PATH = 8

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._all_software: List[Dict[str, str]] = []
        self._filtered_software: List[Dict[str, str]] = []
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
        self._search_input.setPlaceholderText("Search by name, publisher, version, or location...")
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
        self._count_label = QLabel("0 applications")
        self._count_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px; padding: 2px 0;"
        )
        layout.addWidget(self._count_label)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels([
            "Name",
            "Publisher",
            "Version",
            "Install Date",
            "Size",
            "Install Location",
            "Install Source",
            "Uninstall String",
            "Modify Path"
        ])

        # Table styling
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)

        # Column sizing - all columns manually resizable
        header = self._table.horizontalHeader()

        # Set all columns to Interactive mode (user can drag to resize)
        for col in range(9):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        # Last column stretches to fill remaining space
        header.setStretchLastSection(True)

        # Set initial column widths with better proportions
        self._table.setColumnWidth(self.COL_NAME, 180)
        self._table.setColumnWidth(self.COL_PUBLISHER, 140)
        self._table.setColumnWidth(self.COL_VERSION, 80)
        self._table.setColumnWidth(self.COL_INSTALL_DATE, 100)
        self._table.setColumnWidth(self.COL_SIZE, 70)
        self._table.setColumnWidth(self.COL_INSTALL_LOCATION, 250)
        self._table.setColumnWidth(self.COL_INSTALL_SOURCE, 180)
        self._table.setColumnWidth(self.COL_UNINSTALL_STRING, 200)
        # Modify Path stretches to fill remaining space

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
            self._loading_overlay.show_loading("Loading installed software...")
            self._show_skeleton_rows()
        else:
            self._loading_overlay.hide_loading()

    def set_data(self, software_list: List[Dict[str, str]]) -> None:
        """
        Set the software data to display.

        Args:
            software_list: List of software dicts with Name, Publisher, Version, etc.
        """
        self._all_software = software_list
        self._apply_filter()

    def clear(self) -> None:
        """Clear the table."""
        self._all_software = []
        self._filtered_software = []
        self._table.setRowCount(0)
        self._update_count_label()

    def _show_skeleton_rows(self) -> None:
        """Show skeleton rows during loading."""
        self._table.setSortingEnabled(False)
        self._table.setRowCount(10)  # Show 10 skeleton rows

        for row in range(10):
            for col in range(9):
                # Create empty items for skeleton effect
                item = QTableWidgetItem("")
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # Not selectable
                item.setBackground(Colors.WIDGET_HOVER)
                self._table.setItem(row, col, item)

    def _apply_filter(self) -> None:
        """Apply current search filter and update table."""
        search_text = self._search_input.text().lower()

        if not search_text:
            self._filtered_software = self._all_software
        else:
            self._filtered_software = [
                app for app in self._all_software
                if search_text in app.get("Name", "").lower()
                or search_text in app.get("Publisher", "").lower()
                or search_text in app.get("Version", "").lower()
                or search_text in app.get("InstallLocation", "").lower()
            ]

        self._populate_table()

    def _populate_table(self) -> None:
        """Populate table with filtered software data."""
        self._table.setSortingEnabled(False)  # Disable while populating
        self._table.setRowCount(len(self._filtered_software))

        for row, app in enumerate(self._filtered_software):
            # Name
            name_item = QTableWidgetItem(app.get("Name", ""))
            self._table.setItem(row, self.COL_NAME, name_item)

            # Publisher
            publisher_item = QTableWidgetItem(app.get("Publisher", ""))
            self._table.setItem(row, self.COL_PUBLISHER, publisher_item)

            # Version
            version_item = QTableWidgetItem(app.get("Version", ""))
            self._table.setItem(row, self.COL_VERSION, version_item)

            # Install Date (with hidden sort value)
            date_str = app.get("InstallDate", "")
            date_item = QTableWidgetItem(date_str)
            # Use raw date for sorting if available
            if "_date_sort" in app and app["_date_sort"]:
                date_item.setData(Qt.ItemDataRole.UserRole, app["_date_sort"])
            self._table.setItem(row, self.COL_INSTALL_DATE, date_item)

            # Size (with hidden sort value)
            size_str = app.get("Size", "")
            size_item = QTableWidgetItem(size_str)
            # Use numeric size for sorting
            if "_size_sort" in app:
                size_item.setData(Qt.ItemDataRole.UserRole, app["_size_sort"])
            self._table.setItem(row, self.COL_SIZE, size_item)

            # Install Location
            location_item = QTableWidgetItem(app.get("InstallLocation", ""))
            self._table.setItem(row, self.COL_INSTALL_LOCATION, location_item)

            # Install Source
            source_item = QTableWidgetItem(app.get("InstallSource", ""))
            self._table.setItem(row, self.COL_INSTALL_SOURCE, source_item)

            # Uninstall String
            uninstall_item = QTableWidgetItem(app.get("UninstallString", ""))
            self._table.setItem(row, self.COL_UNINSTALL_STRING, uninstall_item)

            # Modify Path
            modify_item = QTableWidgetItem(app.get("ModifyPath", ""))
            self._table.setItem(row, self.COL_MODIFY_PATH, modify_item)

        self._table.setSortingEnabled(True)  # Re-enable sorting
        self._update_count_label()

    def _update_count_label(self) -> None:
        """Update the count label."""
        count = len(self._filtered_software)
        total = len(self._all_software)

        if count == total:
            self._count_label.setText(f"{count} application{'s' if count != 1 else ''}")
        else:
            self._count_label.setText(
                f"{count} of {total} application{'s' if total != 1 else ''}"
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
