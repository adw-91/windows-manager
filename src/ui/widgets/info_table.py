"""Vertical information table widget - labels on left, values on right"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QFrame, QSizePolicy
from PySide6.QtCore import Qt
from typing import Dict


class InfoTable(QWidget):
    """A vertical table widget with labels on the left and values on the right"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels = {}
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create grid for labels and values
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(16, 16, 16, 16)
        self.grid_layout.setVerticalSpacing(10)
        self.grid_layout.setHorizontalSpacing(16)
        self.grid_layout.setColumnStretch(1, 1)

        # Set alignment to top so rows don't stretch vertically
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addLayout(self.grid_layout)
        layout.addStretch()  # Push content to top

    def set_data(self, data: Dict[str, str]):
        """Set data to display in the table"""
        # Clear existing items
        self.clear()

        row = 0
        for label_text, value_text in data.items():
            # Label
            label = QLabel(f"{label_text}:")
            label.setStyleSheet("font-weight: bold;")
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.grid_layout.addWidget(label, row, 0)

            # Value
            value = QLabel(str(value_text))
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.grid_layout.addWidget(value, row, 1)

            self.labels[label_text] = (label, value)
            row += 1

    def update_value(self, label_text: str, value_text: str):
        """Update a specific value in the table"""
        if label_text in self.labels:
            _, value_widget = self.labels[label_text]
            value_widget.setText(str(value_text))

    def clear(self):
        """Clear all items from the table"""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.labels.clear()
