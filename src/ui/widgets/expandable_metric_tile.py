"""Expandable metric tile widget with embedded graphs and details."""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QProgressBar,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, Property, QTimer
from PySide6.QtGui import QCursor

from src.ui.theme import Colors
from src.ui.widgets.live_graph import LiveGraph, MultiLineGraph


class DetailLabel(QWidget):
    """A label pair for showing a detail item (label: value)."""

    def __init__(self, label: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._label = QLabel(label)
        self._label.setStyleSheet(
            f"font-size: 9px; color: {Colors.TEXT_SECONDARY.name()};"
        )
        layout.addWidget(self._label)

        self._value = QLabel("--")
        self._value.setStyleSheet(
            f"font-size: 11px; color: {Colors.TEXT_PRIMARY.name()};"
        )
        self._value.setWordWrap(True)
        layout.addWidget(self._value)

    def set_value(self, value: str) -> None:
        self._value.setText(value)


class ExpandableMetricTile(QFrame):
    """
    A metric tile that expands to show a detailed graph and stats when clicked.

    Signals:
        expanded: Emitted when tile expands (with tile reference)
        collapsed: Emitted when tile collapses (with tile reference)
    """

    expanded = Signal(object)
    collapsed = Signal(object)

    COLLAPSED_HEIGHT = 90  # Smaller for 4x1 horizontal layout
    EXPANDED_HEIGHT = 320  # Fits 4-column detail grid

    def __init__(
        self,
        title: str,
        metric_type: str = "single",  # "single" or "multi"
        y_range: tuple[float, float] = (0, 100),
        series_config: dict = None,
        detail_labels: list[str] = None,
        subtitle: str = None,  # Right-aligned subtitle (e.g., CPU name)
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._metric_type = metric_type
        self._y_range = y_range
        self._series_config = series_config
        self._detail_labels = detail_labels or []
        self._is_expanded = False
        self._animating = False  # Suppress graph updates during expand animation
        self._detail_widgets: dict[str, DetailLabel] = {}

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.COLLAPSED_HEIGHT)

        self._init_ui()
        self._setup_animation()
        self._apply_style()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.setSpacing(4)

        # Header row (title + expand indicator)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(4)

        self._title_label = QLabel(self._title)
        self._title_label.setStyleSheet(
            f"font-size: 10px; color: {Colors.TEXT_SECONDARY.name()};"
        )
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        # Subtitle label (right-aligned, e.g., CPU name) - hidden when collapsed
        self._subtitle_label = QLabel(self._subtitle or "")
        self._subtitle_label.setStyleSheet(
            f"font-size: 9px; color: {Colors.TEXT_SECONDARY.name()};"
        )
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._subtitle_label.setVisible(False)  # Only show when expanded
        header_layout.addWidget(self._subtitle_label)

        self._expand_indicator = QLabel("▼")
        self._expand_indicator.setStyleSheet(
            f"font-size: 9px; color: {Colors.TEXT_SECONDARY.name()};"
        )
        header_layout.addWidget(self._expand_indicator)

        self._layout.addLayout(header_layout)

        # Value label
        self._value_label = QLabel("--")
        self._value_label.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};"
        )
        self._layout.addWidget(self._value_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(4)
        self._layout.addWidget(self._progress_bar)

        # Info label
        self._info_label = QLabel("")
        self._info_label.setStyleSheet(
            f"font-size: 9px; color: {Colors.TEXT_SECONDARY.name()};"
        )
        self._layout.addWidget(self._info_label)

        # Expanded content container (hidden initially)
        self._expanded_container = QWidget()
        self._expanded_container.setVisible(False)
        self._expanded_layout = QVBoxLayout(self._expanded_container)
        self._expanded_layout.setContentsMargins(0, 8, 0, 0)
        self._expanded_layout.setSpacing(8)

        # Graph placeholder - created lazily on first expand
        self._graph: Optional[LiveGraph] = None
        self._graph_created = False

        # Details grid (if labels provided)
        if self._detail_labels:
            details_frame = QFrame()
            details_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {Colors.WINDOW_ALT.name()};
                    border-radius: 4px;
                    padding: 4px;
                }}
            """)
            details_grid = QGridLayout(details_frame)
            details_grid.setContentsMargins(8, 8, 8, 8)
            details_grid.setSpacing(8)
            details_grid.setHorizontalSpacing(24)

            # Arrange labels in a grid (4 columns when expanded to full width)
            cols = 4
            for i, label in enumerate(self._detail_labels):
                row = i // cols
                col = i % cols
                detail_widget = DetailLabel(label)
                self._detail_widgets[label] = detail_widget
                details_grid.addWidget(detail_widget, row, col)

            self._expanded_layout.addWidget(details_frame)

        self._layout.addWidget(self._expanded_container)
        self._layout.addStretch()

    def _setup_animation(self) -> None:
        """Setup expand/collapse animation."""
        self._animation = QPropertyAnimation(self, b"fixedHeight")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _apply_style(self) -> None:
        """Apply styling to the tile."""
        self.setStyleSheet(f"""
            ExpandableMetricTile {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
            }}
            ExpandableMetricTile:hover {{
                border-color: {Colors.ACCENT.name()};
            }}
        """)

    def _create_graph(self) -> None:
        """Create the graph widget on first expansion."""
        if self._graph_created:
            return

        if self._metric_type == "multi" and self._series_config:
            self._graph = MultiLineGraph(
                max_points=120,
                y_range=self._y_range,
                series_config=self._series_config,
                show_legend=True,
            )
        else:
            self._graph = LiveGraph(
                max_points=120,
                y_range=self._y_range,
            )

        self._graph.setMinimumHeight(130)
        self._graph.setMaximumHeight(150)

        # Insert at beginning of expanded layout (before details)
        self._expanded_layout.insertWidget(0, self._graph)
        self._graph_created = True

    def _get_fixed_height(self) -> int:
        return self.height()

    def _set_fixed_height(self, height: int) -> None:
        self.setFixedHeight(height)

    fixedHeight = Property(int, _get_fixed_height, _set_fixed_height)

    def mousePressEvent(self, event) -> None:
        """Toggle expansion on click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_expanded()
        super().mousePressEvent(event)

    def toggle_expanded(self) -> None:
        """Toggle between expanded and collapsed states."""
        if self._is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self) -> None:
        """Expand the tile to show the graph and details."""
        if self._is_expanded:
            return

        self._is_expanded = True
        self._animating = True  # Suppress graph updates during animation
        self._expand_indicator.setText("▲")

        self._expanded_container.setVisible(True)
        self._subtitle_label.setVisible(True)  # Show subtitle when expanded

        # Calculate target height based on content
        target_height = self.EXPANDED_HEIGHT
        if not self._detail_labels:
            target_height -= 80  # Less height if no details

        self._animation.setStartValue(self.height())
        self._animation.setEndValue(target_height)
        self._animation.start()

        # Defer graph creation to after the event loop processes the animation.
        # This prevents UI freeze on iGPU where PlotWidget creation is slow.
        if not self._graph_created:
            QTimer.singleShot(50, self._create_graph)

        # Allow graph updates after animation completes (200ms)
        QTimer.singleShot(250, self._on_expand_animation_done)

        self.expanded.emit(self)

    def _on_expand_animation_done(self) -> None:
        """Re-enable graph updates after expand animation finishes."""
        self._animating = False

    def collapse(self) -> None:
        """Collapse the tile to hide the graph and details."""
        if not self._is_expanded:
            return

        self._is_expanded = False
        self._expand_indicator.setText("▼")
        self._subtitle_label.setVisible(False)  # Hide subtitle when collapsed

        self._animation.setStartValue(self.height())
        self._animation.setEndValue(self.COLLAPSED_HEIGHT)
        self._animation.finished.connect(self._on_collapse_finished)
        self._animation.start()

        self.collapsed.emit(self)

    def _on_collapse_finished(self) -> None:
        """Hide expanded content after collapse animation finishes."""
        self._expanded_container.setVisible(False)
        try:
            self._animation.finished.disconnect(self._on_collapse_finished)
        except RuntimeError:
            pass

    @property
    def is_expanded(self) -> bool:
        return self._is_expanded

    @property
    def graph(self) -> Optional[LiveGraph]:
        """Access the underlying graph widget (may be None if not yet created)."""
        return self._graph

    def set_subtitle(self, subtitle: str) -> None:
        """Set the subtitle text (right-aligned in header)."""
        self._subtitle_label.setText(subtitle)

    def update_value(
        self,
        value: str,
        progress: float = None,
        info: str = "",
    ) -> None:
        """Update the metric value display."""
        self._value_label.setText(value)
        if progress is not None:
            self._progress_bar.setValue(int(progress))
        self._info_label.setText(info)

    def update_detail(self, label: str, value: str) -> None:
        """Update a specific detail value."""
        if label in self._detail_widgets:
            self._detail_widgets[label].set_value(value)

    def update_details(self, details: dict[str, str]) -> None:
        """Update multiple detail values at once."""
        for label, value in details.items():
            self.update_detail(label, value)

    def add_graph_point(self, value: float, series: str = "default") -> None:
        """Add a data point to the graph."""
        if self._graph is not None and not self._animating:
            self._graph.add_point(value, series)

    def update_progress(self, progress: float) -> None:
        """Update just the progress bar."""
        self._progress_bar.setValue(int(progress))
