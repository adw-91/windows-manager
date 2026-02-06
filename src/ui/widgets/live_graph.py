"""
Real-time graph widget for performance monitoring.

Provides efficient scrolling graphs using pyqtgraph with ring buffer storage.
"""

from typing import Optional
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsView

from src.ui.theme import Colors

# Disable antialiasing globally for better performance
pg.setConfigOptions(antialias=False, useOpenGL=False)


class RingBuffer:
    """
    Fixed-size circular buffer for efficient scrolling data.

    Pre-allocates numpy array and maintains head pointer for O(1) operations.
    """

    def __init__(self, size: int, dtype=np.float64) -> None:
        self._size = size
        self._buffer = np.zeros(size, dtype=dtype)
        self._head = 0
        self._count = 0

    def append(self, value: float) -> None:
        """Add a value to the buffer, overwriting oldest if full."""
        self._buffer[self._head] = value
        self._head = (self._head + 1) % self._size
        if self._count < self._size:
            self._count += 1

    def get_data(self) -> np.ndarray:
        """
        Get buffer contents in chronological order.

        Returns:
            numpy array with oldest values first.
        """
        if self._count < self._size:
            # Buffer not yet full
            return self._buffer[:self._count].copy()
        else:
            # Reorder: [head:] + [:head] gives chronological order
            return np.concatenate([
                self._buffer[self._head:],
                self._buffer[:self._head]
            ])

    def clear(self) -> None:
        """Reset buffer to zeros."""
        self._buffer.fill(0)
        self._head = 0
        self._count = 0

    @property
    def size(self) -> int:
        return self._size

    @property
    def count(self) -> int:
        return self._count


class LiveGraph(pg.PlotWidget):
    """
    Real-time scrolling graph widget.

    Features:
    - Ring buffer for memory-efficient data storage
    - Configurable Y-axis range (fixed or auto-scaling)
    - Dark theme styling
    - Multiple series support
    - Resize debouncing for smoother window resizing

    Usage:
        graph = LiveGraph(max_points=60, y_range=(0, 100))
        graph.add_point(42.5)  # Add to default series
        graph.add_point(30.0, series="cpu")  # Named series
    """

    RESIZE_DEBOUNCE_MS = 150  # 150ms debounce for resize events

    def __init__(
        self,
        parent=None,
        max_points: int = 60,
        y_range: Optional[tuple[float, float]] = None,
        title: str = "",
        y_label: str = "",
        show_grid: bool = True,
    ) -> None:
        super().__init__(parent)

        self._max_points = max_points
        self._y_range = y_range
        self._auto_scale = y_range is None

        # Data storage: series_name -> (RingBuffer, PlotDataItem)
        self._series: dict[str, tuple[RingBuffer, pg.PlotDataItem]] = {}

        # X-axis values (shared across all series)
        self._x_data = np.arange(max_points)

        # Resize debouncing
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(self.RESIZE_DEBOUNCE_MS)
        self._resize_timer.timeout.connect(self._do_deferred_resize)
        self._pending_resize_event = None
        self._resizing = False  # Track if resize is in progress

        # Reduce repaint cost: only redraw changed regions, cache static background
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)

        # Configure appearance
        self._setup_style(title, y_label, show_grid)

        # Create default series
        self._create_series("default", Colors.ACCENT)

    def _setup_style(self, title: str, y_label: str, show_grid: bool) -> None:
        """Configure graph appearance to match dark theme."""
        # Background
        self.setBackground(Colors.WIDGET)

        # Axis styling
        axis_pen = pg.mkPen(color=Colors.BORDER.name(), width=1)
        text_color = Colors.TEXT_SECONDARY.name()

        for axis_name in ['left', 'bottom']:
            axis = self.getPlotItem().getAxis(axis_name)
            axis.setPen(axis_pen)
            axis.setTextPen(pg.mkPen(color=text_color))

        # Hide top and right axes
        self.showAxis('top', False)
        self.showAxis('right', False)

        # Grid
        if show_grid:
            self.showGrid(x=True, y=True, alpha=0.2)

        # Title
        if title:
            self.setTitle(title, color=Colors.TEXT_PRIMARY.name(), size='10pt')

        # Y-axis label
        if y_label:
            self.setLabel('left', y_label, color=text_color)

        # X-axis range (fixed)
        self.setXRange(0, self._max_points - 1, padding=0)

        # Y-axis range
        if self._y_range:
            self.setYRange(self._y_range[0], self._y_range[1], padding=0.05)
            self.disableAutoRange(axis='y')
        else:
            self.enableAutoRange(axis='y')

        # Disable mouse interaction (read-only display)
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)

    def _create_series(
        self,
        name: str,
        color: QColor,
        width: int = 2,
    ) -> None:
        """Create a new data series with its own buffer and plot line."""
        buffer = RingBuffer(self._max_points)
        pen = pg.mkPen(color=color.name(), width=width)
        # clipToView=True: only render points in visible range (performance)
        # connect='finite': skip NaN/inf values without breaking line
        curve = self.plot(pen=pen, clipToView=True, connect='finite')

        self._series[name] = (buffer, curve)

    def add_series(
        self,
        name: str,
        color: QColor = None,
        width: int = 2,
    ) -> None:
        """
        Add a named data series to the graph.

        Args:
            name: Unique identifier for this series
            color: Line color (defaults to a color from palette)
            width: Line width in pixels
        """
        if name in self._series:
            return

        # Default colors for additional series
        palette = [
            Colors.SUCCESS,
            Colors.WARNING,
            Colors.ERROR,
            Colors.INFO,
        ]
        if color is None:
            idx = len(self._series) % len(palette)
            color = palette[idx]

        self._create_series(name, color, width)

    def add_point(self, value: float, series: str = "default") -> None:
        """
        Add a data point to the specified series.

        Args:
            value: The data value to add
            series: Name of the series (default: "default")
        """
        if series not in self._series:
            return

        buffer, curve = self._series[series]
        buffer.append(value)

        # Skip curve update during resize (will refresh after resize completes)
        if self.is_resizing:
            return

        # Update plot
        y_data = buffer.get_data()
        # Align x_data to match y_data length (for partially filled buffers)
        x_data = self._x_data[-len(y_data):]
        curve.setData(x_data, y_data)

    def add_points(self, points: dict[str, float]) -> None:
        """
        Add multiple data points without intermediate repaints.

        More efficient than calling add_point multiple times when
        updating several series at once.

        Args:
            points: Dict mapping series name to value
        """
        # First pass: update all buffers
        for series, value in points.items():
            if series in self._series:
                buffer, _ = self._series[series]
                buffer.append(value)

        # Skip curve updates during resize (will refresh after resize completes)
        if self.is_resizing:
            return

        # Second pass: update all curves (single repaint batch)
        for series in points:
            if series in self._series:
                buffer, curve = self._series[series]
                y_data = buffer.get_data()
                x_data = self._x_data[-len(y_data):]
                curve.setData(x_data, y_data)

    def clear_data(self, series: str = None) -> None:
        """
        Clear data from series.

        Args:
            series: Name of series to clear, or None for all series.
        """
        if series:
            if series in self._series:
                buffer, curve = self._series[series]
                buffer.clear()
                curve.setData([], [])
        else:
            for buffer, curve in self._series.values():
                buffer.clear()
                curve.setData([], [])

    def set_y_range(self, min_val: float, max_val: float) -> None:
        """Set fixed Y-axis range."""
        self._y_range = (min_val, max_val)
        self._auto_scale = False
        self.setYRange(min_val, max_val, padding=0.05)
        self.disableAutoRange(axis='y')

    def enable_auto_scale(self) -> None:
        """Enable automatic Y-axis scaling."""
        self._auto_scale = True
        self._y_range = None
        self.enableAutoRange(axis='y')

    @property
    def is_resizing(self) -> bool:
        """Check if a resize is currently in progress."""
        return getattr(self, '_resizing', False)

    def resizeEvent(self, event) -> None:
        """
        Handle resize with debouncing.

        Instead of redrawing on every resize event during window drag,
        we defer the actual resize to reduce CPU usage.
        """
        # During parent __init__, timer may not exist yet
        if not hasattr(self, '_resize_timer'):
            super().resizeEvent(event)
            return

        self._resizing = True
        self._pending_resize_event = event
        self._resize_timer.start()

    def _do_deferred_resize(self) -> None:
        """Execute the deferred resize after debounce delay."""
        self._resizing = False
        if self._pending_resize_event is not None:
            super().resizeEvent(self._pending_resize_event)
            self._pending_resize_event = None
            # Refresh all curves after resize completes
            self._refresh_all_curves()

    def _refresh_all_curves(self) -> None:
        """Redraw all curves with current data."""
        for buffer, curve in self._series.values():
            y_data = buffer.get_data()
            x_data = self._x_data[-len(y_data):]
            curve.setData(x_data, y_data)


class MultiLineGraph(LiveGraph):
    """
    Convenience class for graphs with multiple pre-defined series.

    Usage:
        graph = MultiLineGraph(
            series_config={
                "user": Colors.ACCENT,
                "system": Colors.SUCCESS,
                "idle": Colors.TEXT_SECONDARY,
            }
        )
        graph.add_point(30.0, "user")
        graph.add_point(10.0, "system")
        graph.add_point(60.0, "idle")
    """

    def __init__(
        self,
        parent=None,
        max_points: int = 60,
        y_range: Optional[tuple[float, float]] = None,
        series_config: dict[str, QColor] = None,
        title: str = "",
        y_label: str = "",
        show_grid: bool = True,
        show_legend: bool = False,
    ) -> None:
        super().__init__(
            parent=parent,
            max_points=max_points,
            y_range=y_range,
            title=title,
            y_label=y_label,
            show_grid=show_grid,
        )

        # Remove default series
        if "default" in self._series:
            _, curve = self._series.pop("default")
            self.removeItem(curve)

        # Add configured series
        if series_config:
            for name, color in series_config.items():
                self.add_series(name, color)

        # Legend
        if show_legend and series_config:
            legend = self.addLegend(
                offset=(10, 10),
                labelTextColor=Colors.TEXT_SECONDARY.name(),
            )
            for name in series_config:
                _, curve = self._series[name]
                legend.addItem(curve, name)
