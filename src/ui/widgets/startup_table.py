"""
Startup apps table widget for displaying and managing startup applications.

Provides searchable, sortable table with enable/disable, add, and remove functionality.
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
    QCheckBox,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QComboBox,
)

from src.ui.theme import Colors
from src.ui.widgets.loading_indicator import LoadingOverlay
from src.services.data_cache import CacheState


class AddStartupDialog(QDialog):
    """Dialog for adding a new startup entry."""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Startup Entry")
        self.setMinimumWidth(500)

        layout = QFormLayout(self)

        # Name input
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g., MyApplication")
        layout.addRow("Name:", self._name_input)

        # Command input
        self._command_input = QLineEdit()
        self._command_input.setPlaceholderText(r'e.g., "C:\Program Files\MyApp\app.exe"')
        layout.addRow("Command:", self._command_input)

        # Location selector
        self._location_combo = QComboBox()
        self._location_combo.addItems([
            "HKCU Run (Current User)",
            "HKCU RunOnce (Current User, Once)",
            "HKLM Run (All Users - Requires Admin)",
            "HKLM RunOnce (All Users, Once - Requires Admin)",
        ])
        layout.addRow("Location:", self._location_combo)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        # Apply dark theme styling
        self.setStyleSheet(f"""
            QDialog {{
                background: {Colors.WINDOW.name()};
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QLineEdit, QComboBox {{
                background: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 3px;
                padding: 6px;
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QLabel {{
                color: {Colors.TEXT_PRIMARY.name()};
            }}
        """)

    def get_values(self) -> tuple[str, str, str]:
        """
        Get the dialog values.

        Returns:
            Tuple of (name, command, location)
        """
        location_map = {
            0: "HKCU Run",
            1: "HKCU RunOnce",
            2: "HKLM Run",
            3: "HKLM RunOnce",
        }
        location = location_map[self._location_combo.currentIndex()]
        return (
            self._name_input.text().strip(),
            self._command_input.text().strip(),
            location
        )


class StartupAppsWidget(QWidget):
    """
    Table widget for displaying and managing startup applications.

    Features:
    - Sortable columns: Enabled, Name, Command, Location, Type
    - Enable/disable toggle
    - Add new startup entry
    - Remove startup entry
    - Real-time search/filter
    - Loading state with overlay
    - Refresh button
    - Async data loading support
    """

    # Signals
    refresh_requested = Signal()
    enable_changed = Signal(str, str, bool, str)  # name, location, enabled, original_name
    add_requested = Signal(str, str, str)  # name, command, location
    remove_requested = Signal(str, str)  # name, location

    # Column indices
    COL_ENABLED = 0
    COL_NAME = 1
    COL_COMMAND = 2
    COL_LOCATION = 3
    COL_TYPE = 4

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._all_startup: List[Dict[str, str]] = []
        self._filtered_startup: List[Dict[str, str]] = []
        self._is_loading = False

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Top bar: Search, Add, and Refresh
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Search box
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search by name, command, or location...")
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.setStyleSheet(
            f"padding: 6px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        top_bar.addWidget(self._search_input)

        # Add button
        self._add_button = QPushButton("Add")
        self._add_button.clicked.connect(self._on_add_clicked)
        self._add_button.setStyleSheet(
            f"padding: 6px 12px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        top_bar.addWidget(self._add_button)

        # Remove button
        self._remove_button = QPushButton("Remove")
        self._remove_button.clicked.connect(self._on_remove_clicked)
        self._remove_button.setEnabled(False)
        self._remove_button.setStyleSheet(
            f"padding: 6px 12px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        top_bar.addWidget(self._remove_button)

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
        self._count_label = QLabel("0 startup items")
        self._count_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px; padding: 2px 0;"
        )
        layout.addWidget(self._count_label)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "Enabled",
            "Name",
            "Command",
            "Location",
            "Type"
        ])

        # Table styling
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        # Column sizing - all manually resizable
        header = self._table.horizontalHeader()
        for col in range(5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        # Set initial widths
        self._table.setColumnWidth(self.COL_ENABLED, 80)
        self._table.setColumnWidth(self.COL_NAME, 200)
        self._table.setColumnWidth(self.COL_COMMAND, 300)
        self._table.setColumnWidth(self.COL_LOCATION, 150)

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
        self._add_button.setEnabled(not is_loading)

        if is_loading:
            self._loading_overlay.show_loading("Loading startup items...")
        else:
            self._loading_overlay.hide_loading()

    def set_data(self, startup_list: List[Dict[str, str]]) -> None:
        """
        Set the startup data to display.

        Args:
            startup_list: List of startup dicts
        """
        self._all_startup = startup_list
        self._apply_filter()

    def clear(self) -> None:
        """Clear the table."""
        self._all_startup = []
        self._filtered_startup = []
        self._table.setRowCount(0)
        self._update_count_label()

    def _apply_filter(self) -> None:
        """Apply current search filter and update table."""
        search_text = self._search_input.text().lower()

        if not search_text:
            self._filtered_startup = self._all_startup
        else:
            self._filtered_startup = [
                app for app in self._all_startup
                if search_text in app.get("Name", "").lower()
                or search_text in app.get("Command", "").lower()
                or search_text in app.get("Location", "").lower()
            ]

        self._populate_table()

    def _populate_table(self) -> None:
        """Populate table with filtered startup data."""
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._filtered_startup))

        for row, app in enumerate(self._filtered_startup):
            # Enabled checkbox (centered)
            enabled_widget = QWidget()
            enabled_layout = QHBoxLayout(enabled_widget)
            enabled_layout.setContentsMargins(0, 0, 0, 0)
            enabled_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            checkbox = QCheckBox()
            checkbox.setChecked(app.get("Enabled", "Yes") == "Yes")
            checkbox.setProperty("row_data", app)
            checkbox.stateChanged.connect(self._on_enabled_changed)

            # Disable checkbox for non-registry items
            if app.get("Type") != "Registry":
                checkbox.setEnabled(False)
                checkbox.setToolTip("Only registry items can be enabled/disabled")

            enabled_layout.addWidget(checkbox)
            self._table.setCellWidget(row, self.COL_ENABLED, enabled_widget)

            # Create a dummy item for sorting
            enabled_item = QTableWidgetItem()
            enabled_item.setData(Qt.ItemDataRole.UserRole, 1 if checkbox.isChecked() else 0)
            self._table.setItem(row, self.COL_ENABLED, enabled_item)

            # Name
            name_item = QTableWidgetItem(app.get("Name", ""))
            self._table.setItem(row, self.COL_NAME, name_item)

            # Command
            command_item = QTableWidgetItem(app.get("Command", ""))
            self._table.setItem(row, self.COL_COMMAND, command_item)

            # Location
            location_item = QTableWidgetItem(app.get("Location", ""))
            self._table.setItem(row, self.COL_LOCATION, location_item)

            # Type
            type_item = QTableWidgetItem(app.get("Type", ""))
            self._table.setItem(row, self.COL_TYPE, type_item)

        self._table.setSortingEnabled(True)
        self._update_count_label()

    def _update_count_label(self) -> None:
        """Update the count label."""
        count = len(self._filtered_startup)
        total = len(self._all_startup)

        if count == total:
            self._count_label.setText(f"{count} startup item{'s' if count != 1 else ''}")
        else:
            self._count_label.setText(
                f"{count} of {total} startup item{'s' if total != 1 else ''}"
            )

    @Slot()
    def _on_selection_changed(self) -> None:
        """Handle table selection change."""
        selected = len(self._table.selectedItems()) > 0
        self._remove_button.setEnabled(selected)

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        if not self._is_loading:
            self._apply_filter()

    @Slot()
    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        self.refresh_requested.emit()

    @Slot(int)
    def _on_enabled_changed(self, state: int) -> None:
        """Handle enabled checkbox change."""
        checkbox = self.sender()
        if not checkbox:
            return

        app_data = checkbox.property("row_data")
        if not app_data:
            return

        enabled = (state == Qt.CheckState.Checked.value)
        name = app_data.get("Name", "")
        location = app_data.get("Location", "")
        original_name = app_data.get("_original_name", name)

        self.enable_changed.emit(name, location, enabled, original_name)

    @Slot()
    def _on_add_clicked(self) -> None:
        """Handle add button click."""
        dialog = AddStartupDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, command, location = dialog.get_values()

            if not name or not command:
                QMessageBox.warning(
                    self,
                    "Invalid Input",
                    "Name and Command are required."
                )
                return

            self.add_requested.emit(name, command, location)

    @Slot()
    def _on_remove_clicked(self) -> None:
        """Handle remove button click."""
        current_row = self._table.currentRow()
        if current_row < 0:
            return

        name_item = self._table.item(current_row, self.COL_NAME)
        location_item = self._table.item(current_row, self.COL_LOCATION)

        if not name_item or not location_item:
            return

        name = name_item.text()
        location = location_item.text()

        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to remove '{name}' from startup?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.remove_requested.emit(name, location)
