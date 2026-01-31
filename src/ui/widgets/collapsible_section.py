"""Collapsible Section Widget - Expandable/collapsible content container"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QFrame, QSizePolicy
from PySide6.QtCore import Qt, Signal


class CollapsibleSection(QWidget):
    """A widget that can expand/collapse to show/hide content"""

    toggled = Signal(bool)  # Emits True when expanded, False when collapsed

    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        self.title = title
        self._expanded = expanded  # Start collapsed by default
        self._content_widget = None
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header button
        self.toggle_button = QPushButton()
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(self._expanded)
        self.toggle_button.clicked.connect(self.toggle)
        self.toggle_button.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px 12px;
                border: none;
                background-color: palette(alternateBase);
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: palette(midlight);
            }
        """)
        self._update_button_text()
        layout.addWidget(self.toggle_button)

        # Content container
        self.content_container = QFrame()
        self.content_container.setFrameShape(QFrame.Shape.StyledPanel)
        self.content_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(10, 10, 10, 10)

        layout.addWidget(self.content_container)

        # Set initial visibility
        self.content_container.setVisible(self._expanded)

    def set_content(self, widget: QWidget):
        """Set the content widget to display"""
        # Remove existing content if any
        if self._content_widget:
            self.content_layout.removeWidget(self._content_widget)
            self._content_widget.deleteLater()

        # Add new content
        self._content_widget = widget
        self.content_layout.addWidget(widget)

    def toggle(self):
        """Toggle the expanded/collapsed state"""
        self._expanded = not self._expanded
        self.content_container.setVisible(self._expanded)
        self.toggle_button.setChecked(self._expanded)
        self._update_button_text()
        self.toggled.emit(self._expanded)

    def set_expanded(self, expanded: bool):
        """Set the expanded state explicitly"""
        if self._expanded != expanded:
            self.toggle()

    def is_expanded(self) -> bool:
        """Check if section is currently expanded"""
        return self._expanded

    def _update_button_text(self):
        """Update button text with expand/collapse icon"""
        icon = "▼" if self._expanded else "▶"
        self.toggle_button.setText(f"{icon}  {self.title}")
