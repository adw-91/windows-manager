"""Processes & Services Tab - Combined process and service management"""

import ctypes
from typing import List, Dict, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QLabel,
    QHeaderView, QTabWidget, QCheckBox, QMessageBox,
    QMenu, QApplication
)
from PySide6.QtCore import Qt, Slot, QThreadPool, QTimer
from PySide6.QtGui import QColor, QAction, QKeyEvent
from PySide6.QtWidgets import QApplication

# Windows API for real-time key state
VK_CONTROL = 0x11
user32 = ctypes.windll.user32

from src.services.process_manager import get_process_manager
from src.services.service_info import get_service_info
from src.services.data_cache import DataCache, CacheState
from src.utils.thread_utils import SingleRunWorker, LoopingWorker
from src.ui.theme import Colors
from src.ui.widgets.loading_indicator import LoadingOverlay


class NumericTableWidgetItem(QTableWidgetItem):
    """Table item that sorts numerically by UserRole data instead of lexicographically."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        self_val = self.data(Qt.ItemDataRole.UserRole)
        other_val = other.data(Qt.ItemDataRole.UserRole)
        if self_val is not None and other_val is not None:
            try:
                return float(self_val) < float(other_val)
            except (TypeError, ValueError):
                pass
        return super().__lt__(other)


class ProcessesServicesTab(QWidget):
    """Tab combining process management and services"""

    # Column indices for process table
    COL_PID = 0
    COL_NAME = 1
    COL_CPU = 2
    COL_MEMORY = 3
    COL_STATUS = 4

    # Auto-refresh intervals
    FAST_REFRESH_MS = 3000    # CPU-only update every 3s
    FULL_REFRESH_MS = 15000   # Full process enumeration every 15s

    def __init__(self) -> None:
        super().__init__()
        self._process_manager = get_process_manager()
        self._all_processes: List[Dict] = []
        self._filtered_processes: List[Dict] = []
        self._fast_refresh_worker: Optional[LoopingWorker] = None
        self._full_refresh_worker: Optional[LoopingWorker] = None
        self._sort_paused = False  # Ctrl key pauses sorting/reordering
        self._last_sort_column = self.COL_CPU  # Default sort by CPU
        self._last_sort_order = Qt.SortOrder.DescendingOrder

        # Services cache
        self._service_cache = DataCache(
            lambda: get_service_info().get_all_services(),
            fallback_value=[]
        )
        self._all_services: List[Dict[str, str]] = []
        self._filtered_services: List[Dict[str, str]] = []
        self._current_selected_service: Optional[str] = None

        self._init_ui()
        self._setup_services_cache()
        self._load_initial_processes()

    def _init_ui(self) -> None:
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create sub-tabs for Processes and Services
        self.sub_tabs = QTabWidget()
        self.sub_tabs.addTab(self._create_processes_view(), "Processes")
        self.sub_tabs.addTab(self._create_services_view(), "Services")

        layout.addWidget(self.sub_tabs)

    def _create_processes_view(self) -> QWidget:
        """Create processes view"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Top bar: Search and Auto-refresh checkbox
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Search box
        self._process_search = QLineEdit()
        self._process_search.setPlaceholderText("Filter processes by name...")
        self._process_search.textChanged.connect(self._on_search_changed)
        self._process_search.setStyleSheet(
            f"padding: 6px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        top_bar.addWidget(self._process_search)

        # Auto-refresh checkbox
        self._auto_refresh_checkbox = QCheckBox("Auto-refresh")
        self._auto_refresh_checkbox.setChecked(True)
        self._auto_refresh_checkbox.stateChanged.connect(self._on_auto_refresh_toggled)
        top_bar.addWidget(self._auto_refresh_checkbox)

        layout.addLayout(top_bar)

        # Count and status row
        status_row = QHBoxLayout()
        status_row.setSpacing(12)

        self._process_count_label = QLabel("0 processes")
        self._process_count_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px; padding: 2px 0;"
        )
        status_row.addWidget(self._process_count_label)

        self._sort_status_label = QLabel("")
        self._sort_status_label.setStyleSheet(
            f"color: {Colors.WARNING.name()}; font-size: 11px; padding: 2px 0;"
        )
        status_row.addWidget(self._sort_status_label)
        status_row.addStretch()

        layout.addLayout(status_row)

        # Process table
        self._process_table = QTableWidget()
        self._process_table.setColumnCount(5)
        self._process_table.setHorizontalHeaderLabels([
            "PID", "Name", "CPU %", "Memory (MB)", "Status"
        ])

        # Table styling
        self._process_table.setAlternatingRowColors(True)
        self._process_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._process_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._process_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._process_table.setSortingEnabled(True)
        self._process_table.verticalHeader().setVisible(False)

        # Track sort changes
        self._process_table.horizontalHeader().sortIndicatorChanged.connect(self._on_sort_changed)

        # Column sizing
        header = self._process_table.horizontalHeader()
        for col in range(5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        header.setStretchLastSection(True)

        # Set initial column widths
        self._process_table.setColumnWidth(self.COL_PID, 80)
        self._process_table.setColumnWidth(self.COL_NAME, 250)
        self._process_table.setColumnWidth(self.COL_CPU, 80)
        self._process_table.setColumnWidth(self.COL_MEMORY, 100)

        # Dark theme styling
        self._process_table.setStyleSheet(f"""
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

        # Connect selection change
        self._process_table.itemSelectionChanged.connect(self._on_selection_changed)

        # Enable context menu
        self._process_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._process_table.customContextMenuRequested.connect(self._show_process_context_menu)

        layout.addWidget(self._process_table)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._refresh_btn = QPushButton("Refresh Now")
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        self._refresh_btn.setStyleSheet(
            f"padding: 6px 12px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        button_layout.addWidget(self._refresh_btn)

        self._end_task_btn = QPushButton("End Task")
        self._end_task_btn.setEnabled(False)
        self._end_task_btn.clicked.connect(self._on_end_task_clicked)
        self._end_task_btn.setStyleSheet(
            f"padding: 6px 12px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        button_layout.addWidget(self._end_task_btn)

        layout.addLayout(button_layout)

        return widget

    def _create_services_view(self) -> QWidget:
        """Create services view with full management functionality"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Top bar: Search and Refresh
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Search box
        self._service_search = QLineEdit()
        self._service_search.setPlaceholderText("Search by name, display name, or status...")
        self._service_search.textChanged.connect(self._on_service_search_changed)
        self._service_search.setStyleSheet(
            f"padding: 6px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        top_bar.addWidget(self._service_search)

        # Refresh button
        self._refresh_services_btn = QPushButton("Refresh")
        self._refresh_services_btn.clicked.connect(self._on_refresh_services)
        self._refresh_services_btn.setStyleSheet(
            f"padding: 6px 12px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        top_bar.addWidget(self._refresh_services_btn)

        layout.addLayout(top_bar)

        # Count label
        self._service_count_label = QLabel("0 services")
        self._service_count_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px; padding: 2px 0;"
        )
        layout.addWidget(self._service_count_label)

        # Services table
        self._service_table = QTableWidget()
        self._service_table.setColumnCount(5)
        self._service_table.setHorizontalHeaderLabels([
            "Name", "Display Name", "Status", "Start Mode", "Path"
        ])

        # Table styling
        self._service_table.setAlternatingRowColors(True)
        self._service_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._service_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._service_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._service_table.setSortingEnabled(True)
        self._service_table.verticalHeader().setVisible(False)

        # Column sizing
        header = self._service_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        # Set initial column widths
        self._service_table.setColumnWidth(0, 120)
        self._service_table.setColumnWidth(1, 180)
        self._service_table.setColumnWidth(2, 80)
        self._service_table.setColumnWidth(3, 100)

        # Dark theme styling
        self._service_table.setStyleSheet(f"""
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

        self._service_table.itemSelectionChanged.connect(self._on_service_selection_changed)

        # Enable context menu
        self._service_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._service_table.customContextMenuRequested.connect(self._show_service_context_menu)

        layout.addWidget(self._service_table)

        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._start_service_btn = QPushButton("Start")
        self._start_service_btn.setEnabled(False)
        self._start_service_btn.clicked.connect(self._on_start_service)
        button_layout.addWidget(self._start_service_btn)

        self._stop_service_btn = QPushButton("Stop")
        self._stop_service_btn.setEnabled(False)
        self._stop_service_btn.clicked.connect(self._on_stop_service)
        button_layout.addWidget(self._stop_service_btn)

        self._restart_service_btn = QPushButton("Restart")
        self._restart_service_btn.setEnabled(False)
        self._restart_service_btn.clicked.connect(self._on_restart_service)
        button_layout.addWidget(self._restart_service_btn)

        layout.addLayout(button_layout)

        # Loading overlay
        self._loading_overlay = LoadingOverlay(self._service_table)

        return widget

    def _check_ctrl_state(self) -> bool:
        """Check if Ctrl key is currently pressed using Windows API."""
        # GetAsyncKeyState returns real-time key state
        # High-order bit (0x8000) is set if key is currently down
        return bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)

    @Slot(int, Qt.SortOrder)
    def _on_sort_changed(self, column: int, order: Qt.SortOrder) -> None:
        """Track sort column/order changes."""
        self._last_sort_column = column
        self._last_sort_order = order

    # Processes tab methods
    def _load_initial_processes(self) -> None:
        """Load processes asynchronously on startup using SingleRunWorker."""
        worker = SingleRunWorker(self._process_manager.get_all_processes)
        worker.signals.result.connect(self._on_processes_loaded)
        worker.signals.error.connect(self._on_load_error)
        QThreadPool.globalInstance().start(worker)
        self._start_auto_refresh()

    @Slot(list)
    def _on_processes_loaded(self, processes: List[Dict]) -> None:
        """Handle loaded process list."""
        self._all_processes = processes
        self._apply_filter()

    @Slot(str)
    def _on_load_error(self, error: str) -> None:
        """Handle loading error."""
        self._process_count_label.setText(f"Error loading processes: {error}")

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Apply current search filter and update table."""
        search_text = self._process_search.text().lower()

        if not search_text:
            self._filtered_processes = self._all_processes
        else:
            self._filtered_processes = [
                proc for proc in self._all_processes
                if search_text in proc.get("name", "").lower()
            ]

        self._populate_table()

    def _populate_table(self) -> None:
        """Populate table with filtered process data, reusing existing items."""
        ctrl_pressed = self._check_ctrl_state()

        if ctrl_pressed:
            self._sort_status_label.setText("⏸ Sorting paused (release Ctrl to resume)")
        else:
            self._sort_status_label.setText("")

        # Store current selection
        selected_pid = None
        selected_rows = self._process_table.selectedIndexes()
        if selected_rows:
            row = selected_rows[0].row()
            pid_item = self._process_table.item(row, self.COL_PID)
            if pid_item:
                selected_pid = pid_item.text()

        # Store current row order if Ctrl is pressed
        current_order = []
        if ctrl_pressed:
            for row in range(self._process_table.rowCount()):
                pid_item = self._process_table.item(row, self.COL_PID)
                if pid_item:
                    current_order.append(pid_item.data(Qt.ItemDataRole.UserRole))

        self._process_table.setSortingEnabled(False)

        # Determine row order
        proc_by_pid = {proc.get("pid"): proc for proc in self._filtered_processes}

        if ctrl_pressed and current_order:
            ordered_procs = []
            seen_pids = set()
            for pid in current_order:
                if pid in proc_by_pid:
                    ordered_procs.append(proc_by_pid[pid])
                    seen_pids.add(pid)
            for proc in self._filtered_processes:
                if proc.get("pid") not in seen_pids:
                    ordered_procs.append(proc)
        else:
            ordered_procs = self._filtered_processes

        # Adjust row count
        new_count = len(ordered_procs)
        self._process_table.setRowCount(new_count)

        for row, proc in enumerate(ordered_procs):
            # PID — reuse existing item or create new
            pid_item = self._process_table.item(row, self.COL_PID)
            if pid_item is None:
                pid_item = NumericTableWidgetItem()
                self._process_table.setItem(row, self.COL_PID, pid_item)
            pid_item.setData(Qt.ItemDataRole.DisplayRole, str(proc.get("pid", "")))
            pid_item.setData(Qt.ItemDataRole.UserRole, proc.get("pid", 0))

            # Name
            name_item = self._process_table.item(row, self.COL_NAME)
            if name_item is None:
                name_item = QTableWidgetItem()
                self._process_table.setItem(row, self.COL_NAME, name_item)
            name_item.setText(proc.get("name", ""))

            # CPU %
            cpu_val = min(proc.get('cpu_percent', 0), 100.0)
            cpu_item = self._process_table.item(row, self.COL_CPU)
            if cpu_item is None:
                cpu_item = NumericTableWidgetItem()
                self._process_table.setItem(row, self.COL_CPU, cpu_item)
            cpu_item.setData(Qt.ItemDataRole.DisplayRole, f"{cpu_val:.1f}%")
            cpu_item.setData(Qt.ItemDataRole.UserRole, cpu_val)

            # CPU coloring
            proc_name = proc.get("name", "")
            if proc_name == "System Idle Process":
                if cpu_val > 80:
                    cpu_item.setForeground(Colors.SUCCESS)
                elif cpu_val > 50:
                    cpu_item.setForeground(Colors.TEXT_PRIMARY)
                elif cpu_val > 20:
                    cpu_item.setForeground(Colors.WARNING)
                else:
                    cpu_item.setForeground(Colors.ERROR)
            else:
                if cpu_val > 50:
                    cpu_item.setForeground(Colors.ERROR)
                elif cpu_val > 20:
                    cpu_item.setForeground(Colors.WARNING)
                else:
                    cpu_item.setForeground(Colors.TEXT_PRIMARY)

            # Memory
            mem_val = proc.get('memory_mb', 0)
            memory_item = self._process_table.item(row, self.COL_MEMORY)
            if memory_item is None:
                memory_item = NumericTableWidgetItem()
                self._process_table.setItem(row, self.COL_MEMORY, memory_item)
            memory_item.setData(Qt.ItemDataRole.DisplayRole, f"{mem_val:.1f}")
            memory_item.setData(Qt.ItemDataRole.UserRole, mem_val)
            if mem_val > 1000:
                memory_item.setForeground(Colors.ERROR)
            elif mem_val > 500:
                memory_item.setForeground(Colors.WARNING)
            else:
                memory_item.setForeground(Colors.TEXT_PRIMARY)

            # Status
            status = proc.get("status", "")
            status_item = self._process_table.item(row, self.COL_STATUS)
            if status_item is None:
                status_item = QTableWidgetItem()
                self._process_table.setItem(row, self.COL_STATUS, status_item)
            status_item.setText(status)
            if status == "running":
                status_item.setForeground(Colors.SUCCESS)
            elif status in ("zombie", "dead"):
                status_item.setForeground(Colors.ERROR)
            elif status in ("stopped", "sleeping"):
                status_item.setForeground(Colors.TEXT_SECONDARY)
            else:
                status_item.setForeground(Colors.TEXT_PRIMARY)

        self._process_table.setSortingEnabled(True)

        if not ctrl_pressed and self._last_sort_column is not None:
            self._process_table.sortItems(self._last_sort_column, self._last_sort_order)

        # Restore selection
        if selected_pid:
            for row in range(self._process_table.rowCount()):
                pid_item = self._process_table.item(row, self.COL_PID)
                if pid_item and pid_item.text() == selected_pid:
                    self._process_table.selectRow(row)
                    break

        self._update_count_label()

    def _update_count_label(self) -> None:
        """Update the process count label."""
        count = len(self._filtered_processes)
        total = len(self._all_processes)

        if count == total:
            self._process_count_label.setText(f"{count} process{'es' if count != 1 else ''}")
        else:
            self._process_count_label.setText(
                f"{count} of {total} process{'es' if total != 1 else ''}"
            )

    @Slot()
    def _on_selection_changed(self) -> None:
        """Handle process selection change."""
        selected_rows = self._process_table.selectedIndexes()
        self._end_task_btn.setEnabled(len(selected_rows) > 0)

    @Slot()
    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        worker = SingleRunWorker(self._process_manager.get_all_processes)
        worker.signals.result.connect(self._on_processes_loaded)
        worker.signals.error.connect(self._on_load_error)
        QThreadPool.globalInstance().start(worker)

    def _start_auto_refresh(self) -> None:
        """Start dual refresh workers: fast (CPU-only) + slow (full enum)."""
        if self._fast_refresh_worker is None:
            self._fast_refresh_worker = LoopingWorker(
                self.FAST_REFRESH_MS,
                self._process_manager.get_fast_update,
            )
            self._fast_refresh_worker.signals.result.connect(self._on_processes_loaded)
            self._fast_refresh_worker.signals.error.connect(self._on_load_error)
            self._fast_refresh_worker.start()

        if self._full_refresh_worker is None:
            self._full_refresh_worker = LoopingWorker(
                self.FULL_REFRESH_MS,
                self._process_manager.get_all_processes,
            )
            self._full_refresh_worker.signals.result.connect(self._on_processes_loaded)
            self._full_refresh_worker.signals.error.connect(self._on_load_error)
            self._full_refresh_worker.start()

    def _stop_auto_refresh(self) -> None:
        """Stop both refresh workers."""
        if self._fast_refresh_worker is not None:
            self._fast_refresh_worker.stop()
            self._fast_refresh_worker = None
        if self._full_refresh_worker is not None:
            self._full_refresh_worker.stop()
            self._full_refresh_worker = None

    @Slot(int)
    def _on_auto_refresh_toggled(self, state: int) -> None:
        """Handle auto-refresh checkbox toggle."""
        if state == Qt.CheckState.Checked:
            self._start_auto_refresh()
        else:
            self._stop_auto_refresh()

    @Slot()
    def _on_end_task_clicked(self) -> None:
        """Handle End Task button click with confirmation dialog."""
        selected_rows = self._process_table.selectedIndexes()
        if not selected_rows:
            return

        # Get the row and retrieve process info
        row = selected_rows[0].row()
        pid_item = self._process_table.item(row, self.COL_PID)
        name_item = self._process_table.item(row, self.COL_NAME)

        if not pid_item or not name_item:
            return

        try:
            pid = int(pid_item.text())
            name = name_item.text()
        except ValueError:
            return

        # Show confirmation dialog
        reply = QMessageBox.warning(
            self,
            "End Task",
            f"Are you sure you want to terminate the process '{name}' (PID: {pid})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )

        if reply == QMessageBox.StandardButton.Yes:
            success = self._process_manager.kill_process(pid)
            if success:
                QMessageBox.information(
                    self,
                    "Success",
                    f"Process '{name}' (PID: {pid}) has been terminated."
                )
                # Refresh the process list
                self._on_refresh_clicked()
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to terminate process '{name}' (PID: {pid}).\n"
                    "The process may require administrator privileges or no longer exist."
                )

    # Services tab methods
    def _setup_services_cache(self) -> None:
        """Setup services cache signals."""
        self._service_cache.state_changed.connect(self._on_cache_state_changed)
        self._service_cache.data_loaded.connect(self._on_services_loaded)
        self._service_cache.error_occurred.connect(self._on_cache_error)
        # Load initial services
        self._service_cache.load()

    @Slot(str)
    def _on_service_search_changed(self, text: str) -> None:
        """Handle service search text change"""
        if not self._service_cache.is_loading:
            self._apply_service_filter()

    @Slot()
    def _on_service_selection_changed(self) -> None:
        """Handle service selection change"""
        selected_rows = self._service_table.selectedIndexes()
        has_selection = len(selected_rows) > 0

        self._start_service_btn.setEnabled(has_selection)
        self._stop_service_btn.setEnabled(has_selection)
        self._restart_service_btn.setEnabled(has_selection)

        if has_selection:
            row = selected_rows[0].row()
            if row < len(self._filtered_services):
                self._current_selected_service = self._filtered_services[row].get("Name")

    @Slot()
    def _on_refresh_services(self) -> None:
        """Refresh services list"""
        self._service_cache.refresh()

    @Slot(object)
    def _on_cache_state_changed(self, state: CacheState) -> None:
        """Handle cache state changes"""
        if state == CacheState.LOADING:
            self._loading_overlay.show_loading("Loading services...")
            self._service_search.setEnabled(False)
            self._refresh_services_btn.setEnabled(False)
        elif state in (CacheState.LOADED, CacheState.ERROR):
            self._loading_overlay.hide_loading()
            self._service_search.setEnabled(True)
            self._refresh_services_btn.setEnabled(True)

    @Slot(list)
    def _on_services_loaded(self, services: List[Dict[str, str]]) -> None:
        """Handle services data loaded"""
        self._all_services = services
        self._apply_service_filter()

    @Slot(str)
    def _on_cache_error(self, error_msg: str) -> None:
        """Handle cache error"""
        QMessageBox.warning(
            self,
            "Error Loading Services",
            f"Failed to load services:\n{error_msg}"
        )

    def _apply_service_filter(self) -> None:
        """Apply current search filter and update table"""
        search_text = self._service_search.text().lower()

        if not search_text:
            self._filtered_services = self._all_services
        else:
            self._filtered_services = [
                service for service in self._all_services
                if search_text in service.get("Name", "").lower()
                or search_text in service.get("DisplayName", "").lower()
                or search_text in service.get("Status", "").lower()
            ]

        self._populate_services_table()

    def _populate_services_table(self) -> None:
        """Populate services table with filtered data"""
        self._service_table.setSortingEnabled(False)
        self._service_table.setRowCount(len(self._filtered_services))

        for row, service in enumerate(self._filtered_services):
            # Name
            name_item = QTableWidgetItem(service.get("Name", ""))
            self._service_table.setItem(row, 0, name_item)

            # Display Name
            display_name_item = QTableWidgetItem(service.get("DisplayName", ""))
            self._service_table.setItem(row, 1, display_name_item)

            # Status with color coding
            status = service.get("Status", "Unknown")
            status_item = QTableWidgetItem(status)

            # Color code based on status
            if status == "Running":
                status_item.setForeground(Colors.SUCCESS)
            elif status == "Stopped":
                status_item.setForeground(Colors.WARNING)
            else:
                status_item.setForeground(Colors.TEXT_SECONDARY)

            self._service_table.setItem(row, 2, status_item)

            # Start Mode
            start_mode_item = QTableWidgetItem(service.get("StartMode", ""))
            self._service_table.setItem(row, 3, start_mode_item)

            # Path
            path_item = QTableWidgetItem(service.get("PathName", ""))
            self._service_table.setItem(row, 4, path_item)

        self._service_table.setSortingEnabled(True)
        self._update_service_count_label()

    def _update_service_count_label(self) -> None:
        """Update the service count label"""
        count = len(self._filtered_services)
        total = len(self._all_services)

        if count == total:
            self._service_count_label.setText(f"{count} service{'s' if count != 1 else ''}")
        else:
            self._service_count_label.setText(
                f"{count} of {total} service{'s' if total != 1 else ''}"
            )

    @Slot()
    def _on_start_service(self) -> None:
        """Start selected service"""
        if not self._current_selected_service:
            return

        service_name = self._current_selected_service
        self._execute_service_operation(
            "Starting service...",
            lambda: get_service_info().start_service(service_name),
            f"Service '{service_name}' started successfully",
            f"Failed to start service '{service_name}'"
        )

    @Slot()
    def _on_stop_service(self) -> None:
        """Stop selected service"""
        if not self._current_selected_service:
            return

        service_name = self._current_selected_service
        self._execute_service_operation(
            "Stopping service...",
            lambda: get_service_info().stop_service(service_name),
            f"Service '{service_name}' stopped successfully",
            f"Failed to stop service '{service_name}'"
        )

    @Slot()
    def _on_restart_service(self) -> None:
        """Restart selected service"""
        if not self._current_selected_service:
            return

        service_name = self._current_selected_service
        self._execute_service_operation(
            "Restarting service...",
            lambda: get_service_info().restart_service(service_name),
            f"Service '{service_name}' restarted successfully",
            f"Failed to restart service '{service_name}'"
        )

    def _execute_service_operation(
        self,
        loading_msg: str,
        operation_func,
        success_msg: str,
        error_msg: str
    ) -> None:
        """Execute a service operation in background thread"""
        # Disable buttons during operation
        self._start_service_btn.setEnabled(False)
        self._stop_service_btn.setEnabled(False)
        self._restart_service_btn.setEnabled(False)
        self._refresh_services_btn.setEnabled(False)

        self._loading_overlay.show_loading(loading_msg)

        # Create worker for service operation
        worker = SingleRunWorker(operation_func)
        worker.signals.result.connect(
            lambda result: self._on_service_operation_result(
                result, success_msg, error_msg
            )
        )
        worker.signals.error.connect(
            lambda err: self._on_service_operation_error(error_msg, err)
        )

        QThreadPool.globalInstance().start(worker)

    @Slot(bool)
    def _on_service_operation_result(
        self,
        success: bool,
        success_msg: str,
        error_msg: str
    ) -> None:
        """Handle service operation result"""
        self._loading_overlay.hide_loading()
        self._start_service_btn.setEnabled(True)
        self._stop_service_btn.setEnabled(True)
        self._restart_service_btn.setEnabled(True)
        self._refresh_services_btn.setEnabled(True)

        if success:
            QMessageBox.information(self, "Success", success_msg)
            # Refresh services list to show updated status
            self._service_cache.refresh()
        else:
            QMessageBox.warning(self, "Error", error_msg)

    @Slot(str)
    def _on_service_operation_error(self, error_msg: str, exception: str) -> None:
        """Handle service operation error"""
        self._loading_overlay.hide_loading()
        self._start_service_btn.setEnabled(True)
        self._stop_service_btn.setEnabled(True)
        self._restart_service_btn.setEnabled(True)
        self._refresh_services_btn.setEnabled(True)

        QMessageBox.critical(
            self,
            "Operation Failed",
            f"{error_msg}\n\nDetails: {exception}"
        )

    def closeEvent(self, event) -> None:
        """Clean up workers when tab is closed."""
        self._stop_auto_refresh()
        event.accept()

    def refresh(self) -> None:
        """Refresh the data in this tab"""
        self._on_refresh_clicked()
        self._service_cache.load()

    # Context menu handlers
    @Slot()
    def _show_process_context_menu(self, pos) -> None:
        """Show context menu for process table right-click."""
        item = self._process_table.itemAt(pos)
        if not item:
            return

        row = item.row()
        if row < 0 or row >= len(self._filtered_processes):
            return

        proc_data = self._filtered_processes[row]

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Colors.WINDOW_ALT.name()};
                color: {Colors.TEXT_PRIMARY.name()};
                border: 1px solid {Colors.BORDER.name()};
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background-color: {Colors.ACCENT.name()};
            }}
        """)

        # End Task
        end_task_action = QAction("End Task", self)
        end_task_action.triggered.connect(self._on_end_task_clicked)
        menu.addAction(end_task_action)

        menu.addSeparator()

        # Copy PID
        pid = str(proc_data.get("pid", ""))
        copy_pid_action = QAction("Copy PID", self)
        copy_pid_action.triggered.connect(lambda: self._copy_to_clipboard(pid))
        menu.addAction(copy_pid_action)

        # Copy Name
        name = proc_data.get("name", "")
        copy_name_action = QAction("Copy Name", self)
        copy_name_action.triggered.connect(lambda: self._copy_to_clipboard(name))
        menu.addAction(copy_name_action)

        menu.addSeparator()

        # Refresh
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self._on_refresh_clicked)
        menu.addAction(refresh_action)

        menu.exec(self._process_table.viewport().mapToGlobal(pos))

    @Slot()
    def _show_service_context_menu(self, pos) -> None:
        """Show context menu for service table right-click."""
        item = self._service_table.itemAt(pos)
        if not item:
            return

        row = item.row()
        if row < 0 or row >= len(self._filtered_services):
            return

        service_data = self._filtered_services[row]
        self._current_selected_service = service_data.get("Name")

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Colors.WINDOW_ALT.name()};
                color: {Colors.TEXT_PRIMARY.name()};
                border: 1px solid {Colors.BORDER.name()};
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background-color: {Colors.ACCENT.name()};
            }}
        """)

        # Service control actions
        status = service_data.get("Status", "")

        start_action = QAction("Start", self)
        start_action.setEnabled(status != "Running")
        start_action.triggered.connect(self._on_start_service)
        menu.addAction(start_action)

        stop_action = QAction("Stop", self)
        stop_action.setEnabled(status == "Running")
        stop_action.triggered.connect(self._on_stop_service)
        menu.addAction(stop_action)

        restart_action = QAction("Restart", self)
        restart_action.setEnabled(status == "Running")
        restart_action.triggered.connect(self._on_restart_service)
        menu.addAction(restart_action)

        menu.addSeparator()

        # Copy Name
        copy_name_action = QAction("Copy Name", self)
        copy_name_action.triggered.connect(
            lambda: self._copy_to_clipboard(service_data.get("Name", ""))
        )
        menu.addAction(copy_name_action)

        # Copy Display Name
        copy_display_action = QAction("Copy Display Name", self)
        copy_display_action.triggered.connect(
            lambda: self._copy_to_clipboard(service_data.get("DisplayName", ""))
        )
        menu.addAction(copy_display_action)

        # Copy Path
        copy_path_action = QAction("Copy Path", self)
        copy_path_action.triggered.connect(
            lambda: self._copy_to_clipboard(service_data.get("PathName", ""))
        )
        menu.addAction(copy_path_action)

        menu.addSeparator()

        # Refresh
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self._on_refresh_services)
        menu.addAction(refresh_action)

        menu.exec(self._service_table.viewport().mapToGlobal(pos))

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
