"""Process Management Tab"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QLabel,
    QHeaderView
)
from PySide6.QtCore import Qt


class ProcessTab(QWidget):
    """Tab for viewing and managing processes"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter processes...")
        search_layout.addWidget(self.search_input)
        search_layout.addStretch()

        layout.addLayout(search_layout)

        # Process table
        self.process_table = QTableWidget()
        self.process_table.setColumnCount(5)
        self.process_table.setHorizontalHeaderLabels([
            "PID", "Name", "CPU %", "Memory (MB)", "Status"
        ])

        # Configure table
        header = self.process_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.process_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.process_table.setAlternatingRowColors(True)
        self.process_table.setSortingEnabled(True)

        layout.addWidget(self.process_table)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        button_layout.addWidget(self.refresh_button)

        self.end_task_button = QPushButton("End Task")
        self.end_task_button.setEnabled(False)
        button_layout.addWidget(self.end_task_button)

        layout.addLayout(button_layout)

        # Enable/disable end task button based on selection
        self.process_table.itemSelectionChanged.connect(self.on_selection_changed)

    def on_selection_changed(self):
        """Handle selection change in process table"""
        has_selection = len(self.process_table.selectedItems()) > 0
        self.end_task_button.setEnabled(has_selection)

    def refresh(self):
        """Refresh the process list"""
        # This will be connected to actual data later
        self.process_table.setRowCount(0)
