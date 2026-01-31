"""Performance Monitoring Tab with real-time graphs."""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QGridLayout,
    QFrame,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Slot

from src.ui.widgets import LiveGraph, MultiLineGraph
from src.ui.theme import Colors
from src.services.performance_monitor import get_performance_monitor
from src.utils.thread_utils import LoopingWorker
from src.utils.formatters import format_bytes


class PerformanceTab(QWidget):
    """Tab for viewing real-time performance metrics with graphs."""

    UPDATE_INTERVAL_MS = 500

    def __init__(self) -> None:
        super().__init__()
        self._monitor = get_performance_monitor()
        self._workers: list[LoopingWorker] = []

        self._init_ui()
        self._start_workers()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create splitter for sidebar + content
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # Stacked widget for different views (must be created before sidebar)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._create_cpu_view())
        self._stack.addWidget(self._create_memory_view())
        self._stack.addWidget(self._create_disk_view())
        self._stack.addWidget(self._create_network_view())

        # Sidebar navigation (references self._stack)
        self._sidebar = self._create_sidebar()
        splitter.addWidget(self._sidebar)
        splitter.addWidget(self._stack)

        # Set splitter proportions
        splitter.setSizes([150, 650])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    def _create_sidebar(self) -> QFrame:
        """Create navigation sidebar."""
        frame = QFrame()
        frame.setMaximumWidth(180)
        frame.setMinimumWidth(120)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)

        label = QLabel("Performance")
        label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-weight: bold;")
        layout.addWidget(label)

        self._nav_list = QListWidget()
        self._nav_list.setFrameShape(QFrame.NoFrame)
        self._nav_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 4px;
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QListWidget::item:selected {{
                background: {Colors.ACCENT.name()};
            }}
            QListWidget::item:hover:!selected {{
                background: {Colors.WIDGET_HOVER.name()};
            }}
        """)

        items = ["CPU", "Memory", "Disk", "Network"]
        for item_text in items:
            item = QListWidgetItem(item_text)
            self._nav_list.addItem(item)

        self._nav_list.setCurrentRow(0)
        self._nav_list.currentRowChanged.connect(self._stack.setCurrentIndex)

        layout.addWidget(self._nav_list)
        layout.addStretch()

        return frame

    def _create_cpu_view(self) -> QWidget:
        """Create CPU monitoring view with graphs."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Title
        title = QLabel("CPU Usage")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};")
        layout.addWidget(title)

        # Overall CPU graph
        cpu_group = QGroupBox("Overall Utilization")
        cpu_layout = QVBoxLayout(cpu_group)

        self._cpu_overall_graph = LiveGraph(
            max_points=60,
            y_range=(0, 100),
            y_label="%",
        )
        self._cpu_overall_graph.setMinimumHeight(150)
        cpu_layout.addWidget(self._cpu_overall_graph)

        # Current value label
        self._cpu_percent_label = QLabel("0%")
        self._cpu_percent_label.setStyleSheet(f"font-size: 24px; color: {Colors.ACCENT.name()};")
        cpu_layout.addWidget(self._cpu_percent_label)

        layout.addWidget(cpu_group)

        # CPU breakdown graph (user/system/idle)
        breakdown_group = QGroupBox("Time Breakdown")
        breakdown_layout = QVBoxLayout(breakdown_group)

        self._cpu_breakdown_graph = MultiLineGraph(
            max_points=60,
            y_range=(0, 100),
            series_config={
                "User": Colors.ACCENT,
                "System": Colors.SUCCESS,
                "Idle": Colors.TEXT_SECONDARY,
            },
            y_label="%",
            show_legend=True,
        )
        self._cpu_breakdown_graph.setMinimumHeight(150)
        breakdown_layout.addWidget(self._cpu_breakdown_graph)

        layout.addWidget(breakdown_group)

        # Context switches graph
        ctx_group = QGroupBox("Context Switches / sec")
        ctx_layout = QVBoxLayout(ctx_group)

        self._ctx_graph = LiveGraph(
            max_points=60,
            y_label="switches/s",
        )
        self._ctx_graph.setMinimumHeight(100)
        self._ctx_graph.enable_auto_scale()
        ctx_layout.addWidget(self._ctx_graph)

        layout.addWidget(ctx_group)

        layout.addStretch()
        return widget

    def _create_memory_view(self) -> QWidget:
        """Create memory monitoring view."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        title = QLabel("Memory Usage")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};")
        layout.addWidget(title)

        # Memory usage graph
        mem_group = QGroupBox("Utilization")
        mem_layout = QVBoxLayout(mem_group)

        self._mem_graph = LiveGraph(
            max_points=60,
            y_range=(0, 100),
            y_label="%",
        )
        self._mem_graph.setMinimumHeight(150)
        mem_layout.addWidget(self._mem_graph)

        # Stats row
        stats_layout = QHBoxLayout()
        self._mem_percent_label = QLabel("0%")
        self._mem_percent_label.setStyleSheet(f"font-size: 24px; color: {Colors.ACCENT.name()};")
        stats_layout.addWidget(self._mem_percent_label)

        self._mem_used_label = QLabel("0 GB used")
        self._mem_used_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()};")
        stats_layout.addWidget(self._mem_used_label)

        self._mem_avail_label = QLabel("0 GB available")
        self._mem_avail_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()};")
        stats_layout.addWidget(self._mem_avail_label)

        stats_layout.addStretch()
        mem_layout.addLayout(stats_layout)

        layout.addWidget(mem_group)
        layout.addStretch()
        return widget

    def _create_disk_view(self) -> QWidget:
        """Create disk I/O monitoring view."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        title = QLabel("Disk I/O")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};")
        layout.addWidget(title)

        # Read/Write graphs
        io_group = QGroupBox("Transfer Rate")
        io_layout = QVBoxLayout(io_group)

        self._disk_graph = MultiLineGraph(
            max_points=60,
            series_config={
                "Read": Colors.INFO,
                "Write": Colors.WARNING,
            },
            y_label="MB/s",
            show_legend=True,
        )
        self._disk_graph.setMinimumHeight(200)
        self._disk_graph.enable_auto_scale()
        io_layout.addWidget(self._disk_graph)

        # Current rates
        rates_layout = QHBoxLayout()
        self._disk_read_label = QLabel("Read: 0 MB/s")
        self._disk_read_label.setStyleSheet(f"color: {Colors.INFO.name()};")
        rates_layout.addWidget(self._disk_read_label)

        self._disk_write_label = QLabel("Write: 0 MB/s")
        self._disk_write_label.setStyleSheet(f"color: {Colors.WARNING.name()};")
        rates_layout.addWidget(self._disk_write_label)

        rates_layout.addStretch()
        io_layout.addLayout(rates_layout)

        layout.addWidget(io_group)
        layout.addStretch()
        return widget

    def _create_network_view(self) -> QWidget:
        """Create network I/O monitoring view."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        title = QLabel("Network I/O")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};")
        layout.addWidget(title)

        # Send/Recv graphs
        io_group = QGroupBox("Throughput")
        io_layout = QVBoxLayout(io_group)

        self._net_graph = MultiLineGraph(
            max_points=60,
            series_config={
                "Received": Colors.SUCCESS,
                "Sent": Colors.ACCENT,
            },
            y_label="KB/s",
            show_legend=True,
        )
        self._net_graph.setMinimumHeight(200)
        self._net_graph.enable_auto_scale()
        io_layout.addWidget(self._net_graph)

        # Current rates
        rates_layout = QHBoxLayout()
        self._net_recv_label = QLabel("Received: 0 KB/s")
        self._net_recv_label.setStyleSheet(f"color: {Colors.SUCCESS.name()};")
        rates_layout.addWidget(self._net_recv_label)

        self._net_sent_label = QLabel("Sent: 0 KB/s")
        self._net_sent_label.setStyleSheet(f"color: {Colors.ACCENT.name()};")
        rates_layout.addWidget(self._net_sent_label)

        rates_layout.addStretch()
        io_layout.addLayout(rates_layout)

        layout.addWidget(io_group)
        layout.addStretch()
        return widget

    def _start_workers(self) -> None:
        """Start background workers for live updates."""
        # CPU worker
        cpu_worker = LoopingWorker(
            self.UPDATE_INTERVAL_MS,
            self._collect_cpu_data,
        )
        cpu_worker.signals.result.connect(self._update_cpu_display)
        cpu_worker.start()
        self._workers.append(cpu_worker)

        # Memory worker
        mem_worker = LoopingWorker(
            self.UPDATE_INTERVAL_MS,
            self._collect_memory_data,
        )
        mem_worker.signals.result.connect(self._update_memory_display)
        mem_worker.start()
        self._workers.append(mem_worker)

        # Disk worker
        disk_worker = LoopingWorker(
            self.UPDATE_INTERVAL_MS,
            self._collect_disk_data,
        )
        disk_worker.signals.result.connect(self._update_disk_display)
        disk_worker.start()
        self._workers.append(disk_worker)

        # Network worker
        net_worker = LoopingWorker(
            self.UPDATE_INTERVAL_MS,
            self._collect_network_data,
        )
        net_worker.signals.result.connect(self._update_network_display)
        net_worker.start()
        self._workers.append(net_worker)

    def _collect_cpu_data(self) -> dict:
        """Collect CPU metrics (runs in worker thread)."""
        return {
            "percent": self._monitor.get_cpu_percent(),
            "times": self._monitor.get_cpu_times(),
            "ctx_rate": self._monitor.get_context_switch_rate(),
        }

    def _collect_memory_data(self) -> dict:
        """Collect memory metrics (runs in worker thread)."""
        return {
            "percent": self._monitor.get_memory_percent(),
            "used_gb": self._monitor.get_memory_used_gb(),
            "avail_gb": self._monitor.get_memory_available_gb(),
        }

    def _collect_disk_data(self) -> dict:
        """Collect disk I/O metrics (runs in worker thread)."""
        io = self._monitor.get_disk_io()
        return {
            "read_mb": io.read_bytes_per_sec / (1024 * 1024),
            "write_mb": io.write_bytes_per_sec / (1024 * 1024),
        }

    def _collect_network_data(self) -> dict:
        """Collect network I/O metrics (runs in worker thread)."""
        io = self._monitor.get_network_io()
        return {
            "recv_kb": io.bytes_recv_per_sec / 1024,
            "sent_kb": io.bytes_sent_per_sec / 1024,
        }

    @Slot(object)
    def _update_cpu_display(self, data: dict) -> None:
        """Update CPU graphs and labels (runs in UI thread)."""
        percent = data["percent"]
        times = data["times"]
        ctx_rate = data["ctx_rate"]

        # Overall CPU
        self._cpu_overall_graph.add_point(percent)
        self._cpu_percent_label.setText(f"{percent:.0f}%")

        # Breakdown
        self._cpu_breakdown_graph.add_point(times.user, "User")
        self._cpu_breakdown_graph.add_point(times.system, "System")
        self._cpu_breakdown_graph.add_point(times.idle, "Idle")

        # Context switches
        self._ctx_graph.add_point(ctx_rate)

    @Slot(object)
    def _update_memory_display(self, data: dict) -> None:
        """Update memory graphs and labels (runs in UI thread)."""
        self._mem_graph.add_point(data["percent"])
        self._mem_percent_label.setText(f"{data['percent']:.0f}%")
        self._mem_used_label.setText(f"{data['used_gb']:.1f} GB used")
        self._mem_avail_label.setText(f"{data['avail_gb']:.1f} GB available")

    @Slot(object)
    def _update_disk_display(self, data: dict) -> None:
        """Update disk I/O graphs and labels (runs in UI thread)."""
        self._disk_graph.add_point(data["read_mb"], "Read")
        self._disk_graph.add_point(data["write_mb"], "Write")
        self._disk_read_label.setText(f"Read: {data['read_mb']:.1f} MB/s")
        self._disk_write_label.setText(f"Write: {data['write_mb']:.1f} MB/s")

    @Slot(object)
    def _update_network_display(self, data: dict) -> None:
        """Update network I/O graphs and labels (runs in UI thread)."""
        self._net_graph.add_point(data["recv_kb"], "Received")
        self._net_graph.add_point(data["sent_kb"], "Sent")
        self._net_recv_label.setText(f"Received: {data['recv_kb']:.1f} KB/s")
        self._net_sent_label.setText(f"Sent: {data['sent_kb']:.1f} KB/s")

    def closeEvent(self, event) -> None:
        """Clean up workers when tab is closed."""
        for worker in self._workers:
            worker.stop()
        self._workers.clear()
        event.accept()

    def cleanup(self) -> None:
        """Stop all workers - call when removing tab or closing app."""
        for worker in self._workers:
            worker.stop()
        self._workers.clear()
