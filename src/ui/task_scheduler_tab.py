"""Task Scheduler Tab - Modern UI for Windows Task Scheduler."""

from typing import List, Dict, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QLabel,
    QHeaderView, QSplitter, QTreeWidget, QTreeWidgetItem,
    QFrame, QTextEdit, QMessageBox, QMenu, QApplication,
    QDialog, QFormLayout, QComboBox, QTimeEdit, QDateEdit,
    QCheckBox, QFileDialog, QSpinBox, QGroupBox
)
from PySide6.QtCore import Qt, Slot, QThreadPool, QTime, QDate
from PySide6.QtGui import QAction

from src.services.task_scheduler_info import get_task_scheduler_info
from src.services.data_cache import DataCache, CacheState
from src.utils.thread_utils import SingleRunWorker
from src.ui.theme import Colors
from src.ui.widgets.loading_indicator import LoadingOverlay


class NewTaskDialog(QDialog):
    """Dialog for creating a new scheduled task."""

    SCHEDULE_TYPES = [
        ("Once", "ONCE"),
        ("Daily", "DAILY"),
        ("Weekly", "WEEKLY"),
        ("Monthly", "MONTHLY"),
        ("At Startup", "ONSTART"),
        ("At Logon", "ONLOGON"),
    ]

    DAYS_OF_WEEK = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Task")
        self.setMinimumWidth(500)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Apply dark theme
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.WINDOW.name()};
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QLabel {{
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QLineEdit, QComboBox, QTimeEdit, QDateEdit, QSpinBox {{
                padding: 6px;
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
                background: {Colors.WIDGET.name()};
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                color: {Colors.ACCENT.name()};
            }}
            QPushButton {{
                padding: 8px 16px;
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
                background: {Colors.WIDGET.name()};
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QPushButton:hover {{
                background: {Colors.WIDGET_HOVER.name()};
            }}
            QCheckBox {{
                color: {Colors.TEXT_PRIMARY.name()};
            }}
        """)

        # Warning banner about admin privileges
        warning_frame = QFrame()
        warning_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.WARNING.name()};
                border-radius: 4px;
                padding: 8px;
            }}
            QLabel {{
                color: #000000;
                font-weight: normal;
            }}
        """)
        warning_layout = QHBoxLayout(warning_frame)
        warning_layout.setContentsMargins(12, 8, 12, 8)
        warning_icon = QLabel("⚠️")
        warning_icon.setStyleSheet("font-size: 16px;")
        warning_layout.addWidget(warning_icon)
        warning_text = QLabel("Creating scheduled tasks may require administrator privileges.")
        warning_text.setWordWrap(True)
        warning_layout.addWidget(warning_text, 1)
        layout.addWidget(warning_frame)

        # Basic Info Group
        basic_group = QGroupBox("Basic Information")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Enter task name...")
        basic_layout.addRow("Task Name:", self._name_edit)

        layout.addWidget(basic_group)

        # Action Group
        action_group = QGroupBox("Action")
        action_layout = QFormLayout(action_group)
        action_layout.setSpacing(8)

        # Program path with browse button
        program_layout = QHBoxLayout()
        self._program_edit = QLineEdit()
        self._program_edit.setPlaceholderText("Path to program or script...")
        program_layout.addWidget(self._program_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_program)
        program_layout.addWidget(browse_btn)

        action_layout.addRow("Program:", program_layout)

        self._args_edit = QLineEdit()
        self._args_edit.setPlaceholderText("Optional arguments...")
        action_layout.addRow("Arguments:", self._args_edit)

        # Working directory with browse
        workdir_layout = QHBoxLayout()
        self._workdir_edit = QLineEdit()
        self._workdir_edit.setPlaceholderText("Optional working directory...")
        workdir_layout.addWidget(self._workdir_edit)

        browse_dir_btn = QPushButton("Browse...")
        browse_dir_btn.clicked.connect(self._browse_workdir)
        workdir_layout.addWidget(browse_dir_btn)

        action_layout.addRow("Start In:", workdir_layout)

        layout.addWidget(action_group)

        # Schedule Group
        schedule_group = QGroupBox("Schedule")
        schedule_layout = QFormLayout(schedule_group)
        schedule_layout.setSpacing(8)

        self._schedule_combo = QComboBox()
        for display_name, _ in self.SCHEDULE_TYPES:
            self._schedule_combo.addItem(display_name)
        self._schedule_combo.currentIndexChanged.connect(self._on_schedule_changed)
        schedule_layout.addRow("Trigger:", self._schedule_combo)

        # Time and date (shown for most schedule types)
        time_layout = QHBoxLayout()
        self._time_edit = QTimeEdit()
        self._time_edit.setTime(QTime(9, 0))
        self._time_edit.setDisplayFormat("HH:mm")
        time_layout.addWidget(self._time_edit)
        time_layout.addStretch()
        self._time_label = QLabel("Start Time:")
        schedule_layout.addRow(self._time_label, time_layout)

        # Date (for ONCE schedule)
        date_layout = QHBoxLayout()
        self._date_edit = QDateEdit()
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        date_layout.addWidget(self._date_edit)
        date_layout.addStretch()
        self._date_label = QLabel("Start Date:")
        schedule_layout.addRow(self._date_label, date_layout)

        # Interval (for DAILY, WEEKLY, MONTHLY)
        interval_layout = QHBoxLayout()
        self._interval_spin = QSpinBox()
        self._interval_spin.setMinimum(1)
        self._interval_spin.setMaximum(365)
        self._interval_spin.setValue(1)
        interval_layout.addWidget(self._interval_spin)
        self._interval_suffix = QLabel("day(s)")
        interval_layout.addWidget(self._interval_suffix)
        interval_layout.addStretch()
        self._interval_label = QLabel("Repeat every:")
        schedule_layout.addRow(self._interval_label, interval_layout)

        # Days of week (for WEEKLY)
        self._days_widget = QWidget()
        days_layout = QHBoxLayout(self._days_widget)
        days_layout.setContentsMargins(0, 0, 0, 0)
        days_layout.setSpacing(8)
        self._day_checks = {}
        for day in self.DAYS_OF_WEEK:
            cb = QCheckBox(day)
            self._day_checks[day] = cb
            days_layout.addWidget(cb)
        days_layout.addStretch()
        self._days_label = QLabel("On:")
        schedule_layout.addRow(self._days_label, self._days_widget)

        # Day of month (for MONTHLY)
        day_month_layout = QHBoxLayout()
        self._day_of_month_spin = QSpinBox()
        self._day_of_month_spin.setMinimum(1)
        self._day_of_month_spin.setMaximum(31)
        self._day_of_month_spin.setValue(1)
        day_month_layout.addWidget(self._day_of_month_spin)
        day_month_layout.addStretch()
        self._day_of_month_label = QLabel("Day of month:")
        schedule_layout.addRow(self._day_of_month_label, day_month_layout)

        layout.addWidget(schedule_group)

        # Options Group
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self._run_as_system = QCheckBox("Run with highest privileges (SYSTEM)")
        options_layout.addWidget(self._run_as_system)

        layout.addWidget(options_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        create_btn = QPushButton("Create Task")
        create_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT.name()};
                border-color: {Colors.ACCENT.name()};
                color: white;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_HOVER.name()};
            }}
        """)
        create_btn.clicked.connect(self._on_create)
        button_layout.addWidget(create_btn)

        layout.addLayout(button_layout)

        # Initialize visibility
        self._on_schedule_changed(0)

    def _browse_program(self) -> None:
        """Browse for program file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Program",
            "",
            "Executables (*.exe *.bat *.cmd *.ps1);;All Files (*.*)"
        )
        if file_path:
            self._program_edit.setText(file_path)

    def _browse_workdir(self) -> None:
        """Browse for working directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Working Directory"
        )
        if dir_path:
            self._workdir_edit.setText(dir_path)

    @Slot(int)
    def _on_schedule_changed(self, index: int) -> None:
        """Update UI based on selected schedule type."""
        schedule_type = self.SCHEDULE_TYPES[index][1]

        # Show/hide time (hide for ONSTART, ONLOGON)
        show_time = schedule_type not in ('ONSTART', 'ONLOGON')
        self._time_label.setVisible(show_time)
        self._time_edit.setVisible(show_time)

        # Show date only for ONCE
        show_date = schedule_type == 'ONCE'
        self._date_label.setVisible(show_date)
        self._date_edit.setVisible(show_date)

        # Show interval for DAILY, WEEKLY, MONTHLY
        show_interval = schedule_type in ('DAILY', 'WEEKLY', 'MONTHLY')
        self._interval_label.setVisible(show_interval)
        self._interval_spin.setVisible(show_interval)
        self._interval_suffix.setVisible(show_interval)

        # Update interval suffix text
        if schedule_type == 'DAILY':
            self._interval_suffix.setText("day(s)")
        elif schedule_type == 'WEEKLY':
            self._interval_suffix.setText("week(s)")
        elif schedule_type == 'MONTHLY':
            self._interval_suffix.setText("month(s)")

        # Show days of week for WEEKLY
        show_days = schedule_type == 'WEEKLY'
        self._days_label.setVisible(show_days)
        self._days_widget.setVisible(show_days)

        # Show day of month for MONTHLY
        show_day_of_month = schedule_type == 'MONTHLY'
        self._day_of_month_label.setVisible(show_day_of_month)
        self._day_of_month_spin.setVisible(show_day_of_month)

    def _on_create(self) -> None:
        """Validate and create the task."""
        # Validate inputs
        task_name = self._name_edit.text().strip()
        if not task_name:
            QMessageBox.warning(self, "Validation Error", "Please enter a task name.")
            return

        program = self._program_edit.text().strip()
        if not program:
            QMessageBox.warning(self, "Validation Error", "Please specify a program to run.")
            return

        # Get schedule info
        schedule_idx = self._schedule_combo.currentIndex()
        schedule_type = self.SCHEDULE_TYPES[schedule_idx][1]

        # Build parameters
        start_time = None
        start_date = None
        days = None
        interval = 1

        if schedule_type not in ('ONSTART', 'ONLOGON'):
            start_time = self._time_edit.time().toString("HH:mm")

        if schedule_type == 'ONCE':
            start_date = self._date_edit.date().toString("MM/dd/yyyy")

        if schedule_type in ('DAILY', 'WEEKLY', 'MONTHLY'):
            interval = self._interval_spin.value()

        if schedule_type == 'WEEKLY':
            selected_days = [d for d, cb in self._day_checks.items() if cb.isChecked()]
            if not selected_days:
                QMessageBox.warning(self, "Validation Error", "Please select at least one day of the week.")
                return
            days = ",".join(selected_days)

        if schedule_type == 'MONTHLY':
            days = str(self._day_of_month_spin.value())

        # Create the task
        service = get_task_scheduler_info()
        success, error_msg = service.create_task(
            task_name=task_name,
            program=program,
            schedule_type=schedule_type,
            start_time=start_time,
            start_date=start_date,
            arguments=self._args_edit.text().strip() or None,
            working_dir=self._workdir_edit.text().strip() or None,
            run_as_system=self._run_as_system.isChecked(),
            interval=interval,
            days=days
        )

        if success:
            QMessageBox.information(
                self,
                "Success",
                f"Task '{task_name}' created successfully."
            )
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create task:\n\n{error_msg}\n\n"
                "Note: Creating tasks may require administrator privileges."
            )


class TaskSchedulerTab(QWidget):
    """Tab for managing Windows Task Scheduler with modern UI."""

    # Column indices
    COL_NAME = 0
    COL_STATUS = 1
    COL_LAST_RUN = 2
    COL_NEXT_RUN = 3
    COL_LAST_RESULT = 4

    def __init__(self) -> None:
        super().__init__()
        self._task_service = get_task_scheduler_info()
        self._all_tasks: List[Dict] = []
        self._filtered_tasks: List[Dict] = []
        self._current_folder: str = "\\"
        self._current_task: Optional[Dict] = None
        self._data_loaded = False  # Track if data has been loaded

        # Task cache
        self._task_cache = DataCache(
            lambda: self._task_service.get_all_tasks(),
            fallback_value=[]
        )

        self._init_ui()
        self._setup_cache()
        # Show loading state initially, but don't load data yet (lazy loading)
        self._loading_overlay.show_loading("Loading tasks...")

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Compact header with search inline
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        title = QLabel("Task Scheduler")
        title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};")
        header_layout.addWidget(title)

        # Search box - compact
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search tasks...")
        self._search_box.setMaximumWidth(250)
        self._search_box.textChanged.connect(self._on_search_changed)
        self._search_box.setStyleSheet(
            f"padding: 4px 8px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        header_layout.addWidget(self._search_box)

        self._count_label = QLabel("0 tasks")
        self._count_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px;")
        header_layout.addWidget(self._count_label)

        header_layout.addStretch()

        # Add Task button
        add_btn = QPushButton("+ New Task")
        add_btn.clicked.connect(self._on_add_task)
        add_btn.setStyleSheet(
            f"padding: 4px 12px; border: 1px solid {Colors.ACCENT.name()}; "
            f"border-radius: 3px; background: {Colors.ACCENT.name()}; color: white;"
        )
        header_layout.addWidget(add_btn)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh)
        refresh_btn.setStyleSheet(
            f"padding: 4px 12px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )
        header_layout.addWidget(refresh_btn)
        layout.addLayout(header_layout)

        # Main content splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Folder tree
        left_panel = QFrame()
        left_panel.setFrameShape(QFrame.Shape.StyledPanel)
        left_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
            }}
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)

        folder_label = QLabel("Task Folders")
        folder_label.setStyleSheet(f"font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};")
        left_layout.addWidget(folder_label)

        self._folder_tree = QTreeWidget()
        self._folder_tree.setHeaderHidden(True)
        self._folder_tree.itemClicked.connect(self._on_folder_clicked)
        self._folder_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {Colors.WIDGET.name()};
                border: none;
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QTreeWidget::item:selected {{
                background-color: {Colors.ACCENT.name()};
            }}
            QTreeWidget::item:hover {{
                background-color: {Colors.WIDGET_HOVER.name()};
            }}
        """)
        left_layout.addWidget(self._folder_tree)

        splitter.addWidget(left_panel)

        # Right panel: Task list and details
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Task table
        self._task_table = QTableWidget()
        self._task_table.setColumnCount(5)
        self._task_table.setHorizontalHeaderLabels([
            "Task Name", "Status", "Last Run", "Next Run", "Last Result"
        ])

        # Table styling
        self._task_table.setAlternatingRowColors(True)
        self._task_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._task_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._task_table.setSortingEnabled(True)
        self._task_table.verticalHeader().setVisible(False)

        # Column sizing - all interactive/resizable
        header = self._task_table.horizontalHeader()
        for col in range(5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        # Set reasonable initial widths
        self._task_table.setColumnWidth(0, 250)  # Name - wider
        self._task_table.setColumnWidth(1, 80)   # Status
        self._task_table.setColumnWidth(2, 140)  # Last Run
        self._task_table.setColumnWidth(3, 140)  # Next Run
        self._task_table.setColumnWidth(4, 100)  # Last Result

        # Dark theme styling
        self._task_table.setStyleSheet(f"""
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

        self._task_table.itemSelectionChanged.connect(self._on_task_selected)
        self._task_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._task_table.customContextMenuRequested.connect(self._show_context_menu)

        right_layout.addWidget(self._task_table)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._run_btn = QPushButton("Run")
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._on_run_task)
        self._run_btn.setStyleSheet(self._button_style())
        button_layout.addWidget(self._run_btn)

        self._enable_btn = QPushButton("Enable")
        self._enable_btn.setEnabled(False)
        self._enable_btn.clicked.connect(self._on_enable_task)
        self._enable_btn.setStyleSheet(self._button_style())
        button_layout.addWidget(self._enable_btn)

        self._disable_btn = QPushButton("Disable")
        self._disable_btn.setEnabled(False)
        self._disable_btn.clicked.connect(self._on_disable_task)
        self._disable_btn.setStyleSheet(self._button_style())
        button_layout.addWidget(self._disable_btn)

        self._end_btn = QPushButton("End")
        self._end_btn.setEnabled(False)
        self._end_btn.clicked.connect(self._on_end_task)
        self._end_btn.setStyleSheet(self._button_style())
        button_layout.addWidget(self._end_btn)

        right_layout.addLayout(button_layout)

        # Task details panel
        details_frame = QFrame()
        details_frame.setFrameShape(QFrame.Shape.StyledPanel)
        details_frame.setFixedHeight(100)
        details_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
            }}
        """)
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(8, 6, 8, 6)

        details_header = QLabel("Task Details")
        details_header.setStyleSheet(f"font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};")
        details_layout.addWidget(details_header)

        self._details_text = QLabel("Select a task to view details")
        self._details_text.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()};")
        self._details_text.setWordWrap(True)
        self._details_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(self._details_text)

        right_layout.addWidget(details_frame)

        splitter.addWidget(right_panel)

        # Set splitter sizes
        splitter.setSizes([200, 600])

        layout.addWidget(splitter)

        # Loading overlay
        self._loading_overlay = LoadingOverlay(self._task_table)

    def _button_style(self) -> str:
        """Get standard button style."""
        return (
            f"padding: 6px 12px; border: 1px solid {Colors.BORDER.name()}; "
            f"border-radius: 3px; background: {Colors.WIDGET.name()};"
        )

    def _setup_cache(self) -> None:
        """Setup cache signals."""
        self._task_cache.state_changed.connect(self._on_cache_state_changed)
        self._task_cache.data_loaded.connect(self._on_tasks_loaded)
        self._task_cache.error_occurred.connect(self._on_cache_error)

    @Slot(object)
    def _on_cache_state_changed(self, state: CacheState) -> None:
        """Handle cache state changes."""
        if state == CacheState.LOADING:
            self._loading_overlay.show_loading("Loading tasks...")
            self._search_box.setEnabled(False)
        elif state in (CacheState.LOADED, CacheState.ERROR):
            self._loading_overlay.hide_loading()
            self._search_box.setEnabled(True)

    @Slot(list)
    def _on_tasks_loaded(self, tasks: List[Dict]) -> None:
        """Handle tasks data loaded."""
        self._all_tasks = tasks
        self._build_folder_tree()
        self._apply_filter()

    @Slot(str)
    def _on_cache_error(self, error_msg: str) -> None:
        """Handle cache error."""
        QMessageBox.warning(self, "Error", f"Failed to load tasks: {error_msg}")

    def _build_folder_tree(self) -> None:
        """Build folder tree from tasks."""
        self._folder_tree.clear()

        # Build folder structure
        folders = {}
        root_item = QTreeWidgetItem(["Task Scheduler Library"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, "\\")
        self._folder_tree.addTopLevelItem(root_item)
        folders["\\"] = root_item

        for task in self._all_tasks:
            path = task.get('path', '\\')
            if path and path != "\\":
                parts = path.strip("\\").split("\\")
                current_path = ""
                parent = root_item

                for part in parts:
                    current_path = current_path + "\\" + part if current_path else "\\" + part
                    if current_path not in folders:
                        item = QTreeWidgetItem([part])
                        item.setData(0, Qt.ItemDataRole.UserRole, current_path)
                        parent.addChild(item)
                        folders[current_path] = item
                    parent = folders[current_path]

        root_item.setExpanded(True)

    @Slot(QTreeWidgetItem, int)
    def _on_folder_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle folder tree item click."""
        self._current_folder = item.data(0, Qt.ItemDataRole.UserRole)
        self._apply_filter()

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Apply folder and search filters."""
        search_text = self._search_box.text().lower()

        self._filtered_tasks = []
        for task in self._all_tasks:
            # Folder filter
            task_path = task.get('path', '\\')
            if self._current_folder != "\\":
                if not task_path.startswith(self._current_folder):
                    continue

            # Search filter
            if search_text:
                task_name = task.get('short_name', '').lower()
                if search_text not in task_name:
                    continue

            self._filtered_tasks.append(task)

        self._populate_table()

    def _populate_table(self) -> None:
        """Populate task table."""
        self._task_table.setSortingEnabled(False)
        self._task_table.setRowCount(len(self._filtered_tasks))

        for row, task in enumerate(self._filtered_tasks):
            # Name
            name_item = QTableWidgetItem(task.get('short_name', ''))
            self._task_table.setItem(row, self.COL_NAME, name_item)

            # Status with RAG coloring
            state = task.get('state', 'Unknown')
            enabled = task.get('enabled', 'Enabled')
            status = state if enabled == 'Enabled' else 'Disabled'

            status_item = QTableWidgetItem(status)
            if status == 'Running':
                status_item.setForeground(Colors.SUCCESS)
            elif status == 'Ready':
                status_item.setForeground(Colors.INFO)
            elif status == 'Disabled':
                status_item.setForeground(Colors.WARNING)
            else:
                status_item.setForeground(Colors.TEXT_SECONDARY)
            self._task_table.setItem(row, self.COL_STATUS, status_item)

            # Last run
            last_run = task.get('last_run', 'Never')
            last_run_item = QTableWidgetItem(last_run if last_run != 'N/A' else 'Never')
            self._task_table.setItem(row, self.COL_LAST_RUN, last_run_item)

            # Next run
            next_run = task.get('next_run', 'N/A')
            next_run_item = QTableWidgetItem(next_run)
            self._task_table.setItem(row, self.COL_NEXT_RUN, next_run_item)

            # Last result with coloring
            result = task.get('last_result', '0')
            result_item = QTableWidgetItem(result)
            if result == '0' or result == 'The operation completed successfully.':
                result_item.setForeground(Colors.SUCCESS)
                result_item.setText('Success (0)')
            elif 'never' in result.lower():
                result_item.setForeground(Colors.TEXT_SECONDARY)
            else:
                result_item.setForeground(Colors.ERROR)
            self._task_table.setItem(row, self.COL_LAST_RESULT, result_item)

        self._task_table.setSortingEnabled(True)
        self._update_count_label()

    def _update_count_label(self) -> None:
        """Update task count label."""
        count = len(self._filtered_tasks)
        total = len(self._all_tasks)
        if count == total:
            self._count_label.setText(f"{count} tasks")
        else:
            self._count_label.setText(f"{count} of {total} tasks")

    @Slot()
    def _on_task_selected(self) -> None:
        """Handle task selection."""
        selected = self._task_table.selectedIndexes()
        has_selection = len(selected) > 0

        self._run_btn.setEnabled(has_selection)
        self._enable_btn.setEnabled(has_selection)
        self._disable_btn.setEnabled(has_selection)
        self._end_btn.setEnabled(has_selection)

        if has_selection:
            row = selected[0].row()
            if row < len(self._filtered_tasks):
                self._current_task = self._filtered_tasks[row]
                self._update_details()
        else:
            self._current_task = None
            self._details_text.setText("Select a task to view details")

    def _update_details(self) -> None:
        """Update task details panel."""
        if not self._current_task:
            return

        task = self._current_task
        details = []
        details.append(f"<b>Full Name:</b> {task.get('name', 'N/A')}")
        details.append(f"<b>Author:</b> {task.get('author', 'N/A')}")
        details.append(f"<b>Action:</b> {task.get('action', 'N/A')[:100]}...")

        self._details_text.setText("<br>".join(details))

    @Slot()
    def _on_refresh(self) -> None:
        """Refresh task list."""
        self._task_cache.refresh()

    @Slot()
    def _on_run_task(self) -> None:
        """Run selected task."""
        if not self._current_task:
            return

        task_name = self._current_task.get('name', '')
        success = self._task_service.run_task(task_name)

        if success:
            QMessageBox.information(self, "Success", f"Task '{task_name}' started.")
            self._task_cache.refresh()
        else:
            QMessageBox.warning(self, "Error", f"Failed to run task '{task_name}'.\nAdministrator privileges may be required.")

    @Slot()
    def _on_enable_task(self) -> None:
        """Enable selected task."""
        if not self._current_task:
            return

        task_name = self._current_task.get('name', '')
        success = self._task_service.enable_task(task_name)

        if success:
            QMessageBox.information(self, "Success", f"Task '{task_name}' enabled.")
            self._task_cache.refresh()
        else:
            QMessageBox.warning(self, "Error", f"Failed to enable task.\nAdministrator privileges may be required.")

    @Slot()
    def _on_disable_task(self) -> None:
        """Disable selected task."""
        if not self._current_task:
            return

        task_name = self._current_task.get('name', '')
        success = self._task_service.disable_task(task_name)

        if success:
            QMessageBox.information(self, "Success", f"Task '{task_name}' disabled.")
            self._task_cache.refresh()
        else:
            QMessageBox.warning(self, "Error", f"Failed to disable task.\nAdministrator privileges may be required.")

    @Slot()
    def _on_end_task(self) -> None:
        """End/stop selected task."""
        if not self._current_task:
            return

        task_name = self._current_task.get('name', '')
        success = self._task_service.end_task(task_name)

        if success:
            QMessageBox.information(self, "Success", f"Task '{task_name}' stopped.")
            self._task_cache.refresh()
        else:
            QMessageBox.warning(self, "Error", f"Failed to end task.\nThe task may not be running.")

    @Slot()
    def _show_context_menu(self, pos) -> None:
        """Show context menu for task table."""
        item = self._task_table.itemAt(pos)
        if not item:
            return

        row = item.row()
        if row < 0 or row >= len(self._filtered_tasks):
            return

        task = self._filtered_tasks[row]
        self._current_task = task

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

        run_action = QAction("Run", self)
        run_action.triggered.connect(self._on_run_task)
        menu.addAction(run_action)

        menu.addSeparator()

        enable_action = QAction("Enable", self)
        enable_action.triggered.connect(self._on_enable_task)
        menu.addAction(enable_action)

        disable_action = QAction("Disable", self)
        disable_action.triggered.connect(self._on_disable_task)
        menu.addAction(disable_action)

        end_action = QAction("End", self)
        end_action.triggered.connect(self._on_end_task)
        menu.addAction(end_action)

        menu.addSeparator()

        copy_name_action = QAction("Copy Task Name", self)
        copy_name_action.triggered.connect(lambda: self._copy_to_clipboard(task.get('name', '')))
        menu.addAction(copy_name_action)

        copy_action_action = QAction("Copy Action", self)
        copy_action_action.triggered.connect(lambda: self._copy_to_clipboard(task.get('action', '')))
        menu.addAction(copy_action_action)

        menu.addSeparator()

        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self._on_refresh)
        menu.addAction(refresh_action)

        menu.exec(self._task_table.viewport().mapToGlobal(pos))

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    @Slot()
    def _on_add_task(self) -> None:
        """Show dialog to create a new scheduled task."""
        dialog = NewTaskDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Refresh to show the new task
            self._task_cache.refresh()

    def on_tab_activated(self) -> None:
        """Called when this tab becomes visible. Loads data on first activation."""
        if not self._data_loaded:
            self._data_loaded = True
            self._task_cache.load()

    def refresh(self) -> None:
        """Refresh the data in this tab."""
        self._task_cache.refresh()
