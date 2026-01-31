"""
Loading indicator widgets for async operations.

Provides visual feedback while data is being fetched or processed.
"""

from PySide6.QtCore import Qt, QTimer, QSize, Property
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QSizePolicy,
)


class SpinnerWidget(QWidget):
    """
    Animated spinner widget.

    A circular loading indicator that rotates continuously.
    """

    def __init__(
        self,
        parent: QWidget = None,
        size: int = 32,
        color: QColor = None,
        line_width: int = 3,
    ) -> None:
        super().__init__(parent)
        self._size = size
        self._color = color or QColor(100, 149, 237)  # Cornflower blue
        self._line_width = line_width
        self._angle = 0
        self._arc_length = 270  # Degrees of arc to draw

        self.setFixedSize(QSize(size, size))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)

    def start(self) -> None:
        """Start the spinning animation."""
        self._timer.start(16)  # ~60fps

    def stop(self) -> None:
        """Stop the spinning animation."""
        self._timer.stop()

    def _rotate(self) -> None:
        """Rotate the spinner by a small amount."""
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event) -> None:
        """Draw the spinner arc."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate drawing area with padding for line width
        padding = self._line_width
        rect = self.rect().adjusted(padding, padding, -padding, -padding)

        # Set up pen
        pen = QPen(self._color)
        pen.setWidth(self._line_width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        # Draw arc (Qt uses 1/16th degree units)
        start_angle = self._angle * 16
        span_angle = self._arc_length * 16
        painter.drawArc(rect, start_angle, span_angle)


class LoadingOverlay(QWidget):
    """
    Semi-transparent overlay with spinner and optional message.

    Place this over any widget to indicate loading state.

    Usage:
        overlay = LoadingOverlay(parent_widget)
        overlay.show_loading("Loading data...")
        # Later...
        overlay.hide_loading()
    """

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)

        # Make overlay cover parent
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAutoFillBackground(True)

        # Semi-transparent background
        palette = self.palette()
        bg_color = palette.window().color()
        bg_color.setAlpha(200)
        palette.setColor(self.backgroundRole(), bg_color)
        self.setPalette(palette)

        # Layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Spinner
        self._spinner = SpinnerWidget(self, size=48)
        layout.addWidget(self._spinner, alignment=Qt.AlignCenter)

        # Message label
        self._message = QLabel()
        self._message.setAlignment(Qt.AlignCenter)
        self._message.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self._message, alignment=Qt.AlignCenter)

        # Start hidden
        self.hide()

    def show_loading(self, message: str = "") -> None:
        """Show the overlay with optional message."""
        self._message.setText(message)
        self._message.setVisible(bool(message))

        # Resize to cover parent
        if self.parent():
            self.setGeometry(self.parent().rect())

        self._spinner.start()
        self.show()
        self.raise_()

    def hide_loading(self) -> None:
        """Hide the overlay."""
        self._spinner.stop()
        self.hide()

    def resizeEvent(self, event) -> None:
        """Keep overlay sized to parent."""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)


class SkeletonWidget(QWidget):
    """
    Animated skeleton placeholder for content that's loading.

    Shows a pulsing grey rectangle as a placeholder.
    """

    def __init__(
        self,
        parent: QWidget = None,
        width: int = None,
        height: int = 20,
    ) -> None:
        super().__init__(parent)

        self._alpha = 60
        self._alpha_direction = 1
        self._base_color = QColor(128, 128, 128)

        if width:
            self.setFixedWidth(width)
        if height:
            self.setFixedHeight(height)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._timer.start(30)

    def _pulse(self) -> None:
        """Animate the alpha value for pulsing effect."""
        self._alpha += self._alpha_direction * 2
        if self._alpha >= 100:
            self._alpha = 100
            self._alpha_direction = -1
        elif self._alpha <= 40:
            self._alpha = 40
            self._alpha_direction = 1
        self.update()

    def paintEvent(self, event) -> None:
        """Draw the skeleton rectangle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        color = QColor(self._base_color)
        color.setAlpha(self._alpha)

        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 4, 4)


class SkeletonRow(QFrame):
    """
    A row of skeleton placeholders mimicking a table row.

    Usage:
        row = SkeletonRow(column_widths=[100, 200, 150])
    """

    def __init__(
        self,
        parent: QWidget = None,
        column_widths: list[int] = None,
        height: int = 24,
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(16)

        widths = column_widths or [100, 150, 100]

        for width in widths:
            skeleton = SkeletonWidget(self, width=width, height=height - 8)
            layout.addWidget(skeleton)

        layout.addStretch()
        self.setFixedHeight(height)


class LoadingPlaceholder(QFrame):
    """
    A placeholder widget showing multiple skeleton rows.

    Use this to show loading state for tables or lists.

    Usage:
        placeholder = LoadingPlaceholder(row_count=5, column_widths=[100, 200])
        # When data arrives:
        placeholder.hide()
    """

    def __init__(
        self,
        parent: QWidget = None,
        row_count: int = 5,
        column_widths: list[int] = None,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        for _ in range(row_count):
            row = SkeletonRow(self, column_widths=column_widths)
            layout.addWidget(row)

        layout.addStretch()
