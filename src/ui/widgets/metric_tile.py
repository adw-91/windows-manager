"""Metric tile widget for displaying live system metrics"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QFrame
from PySide6.QtCore import Qt


class MetricTile(QFrame):
    """A tile widget for displaying a single metric with progress bar"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.init_ui()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)

        # Title
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("font-size: 11px; color: gray;")
        layout.addWidget(self.title_label)

        # Value
        self.value_label = QLabel("--")
        self.value_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(self.value_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)

        # Secondary info
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("font-size: 10px; color: gray;")
        layout.addWidget(self.info_label)

    def update_value(self, value: str, progress: float = None, info: str = ""):
        """Update the metric value"""
        self.value_label.setText(value)
        if progress is not None:
            self.progress_bar.setValue(int(progress))
        self.info_label.setText(info)

    def update_progress(self, progress: float):
        """Update just the progress bar"""
        self.progress_bar.setValue(int(progress))
