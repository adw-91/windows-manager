"""System Overview Tab with expandable metric tiles."""

import psutil
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QScrollArea,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Slot

from src.ui.widgets.expandable_metric_tile import ExpandableMetricTile
from src.ui.widgets.collapsible_section import CollapsibleSection
from src.ui.widgets.software_table import SoftwareTableWidget
from src.ui.widgets.startup_table import StartupAppsWidget
from src.ui.widgets.battery_widget import BatteryWidget
from src.ui.theme import Colors
from src.services.system_monitor import SystemMonitor
from src.services.windows_info import WindowsInfo
from src.services.process_manager import ProcessManager
from src.services.performance_monitor import get_performance_monitor
from src.services.software_info import get_software_cache
from src.services.startup_info import get_startup_cache, get_startup_info
from src.utils.formatters import format_uptime, format_bytes
from src.utils.thread_utils import LoopingWorker


class SystemInfoHeader(QFrame):
    """System info header with hostname as title and details as compact bar."""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._labels: dict[str, QLabel] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(6)

        # Hostname as header
        self._hostname_label = QLabel("")
        self._hostname_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};"
        )
        self._layout.addWidget(self._hostname_label)

        # Details row
        self._details_layout = QHBoxLayout()
        self._details_layout.setContentsMargins(0, 0, 0, 0)
        self._details_layout.setSpacing(20)
        self._layout.addLayout(self._details_layout)

    def set_data(self, hostname: str, details: dict[str, str]) -> None:
        """Set hostname and detail values."""
        self._hostname_label.setText(hostname)

        # Clear existing details
        while self._details_layout.count():
            item = self._details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._labels.clear()

        for label_text, value_text in details.items():
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(4)

            label = QLabel(f"{label_text}:")
            label.setStyleSheet(f"font-size: 10px; color: {Colors.TEXT_SECONDARY.name()};")
            item_layout.addWidget(label)

            value = QLabel(str(value_text))
            value.setStyleSheet(f"font-size: 10px; color: {Colors.TEXT_PRIMARY.name()};")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            item_layout.addWidget(value)

            self._labels[label_text] = value
            self._details_layout.addWidget(item_widget)

        self._details_layout.addStretch()

    def update_value(self, label_text: str, value_text: str) -> None:
        if label_text in self._labels:
            self._labels[label_text].setText(str(value_text))


class SystemOverviewTab(QWidget):
    """Tab showing system overview with expandable metric tiles."""

    UPDATE_INTERVAL_MS = 1000  # 1 second for tile values
    GRAPH_INTERVAL_MS = 1000  # 1 second for graph updates

    def __init__(self) -> None:
        super().__init__()
        self._system_monitor = SystemMonitor()
        self._windows_info = WindowsInfo()
        self._process_manager = ProcessManager()
        self._perf_monitor = get_performance_monitor()
        self._workers: list[LoopingWorker] = []
        self._expanded_tile = None  # Track which tile is expanded

        # Software cache for installed applications
        self._software_cache = get_software_cache()

        # Startup cache for startup applications
        self._startup_cache = get_startup_cache()
        self._startup_service = get_startup_info()

        self._init_ui()
        self._load_system_info_async()  # Changed to async
        self._start_workers()
        self._init_software_cache()
        self._init_startup_cache()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        # === ROW 1: System Info Header ===
        self._system_info_header = SystemInfoHeader()
        content_layout.addWidget(self._system_info_header)

        # === ROW 2: Metric tiles (4x1 horizontal when collapsed) ===
        self._tiles_container = QWidget()
        self._tiles_layout = QGridLayout(self._tiles_container)
        self._tiles_layout.setContentsMargins(0, 0, 0, 0)
        self._tiles_layout.setSpacing(8)

        # CPU tile
        self._cpu_tile = ExpandableMetricTile(
            "CPU Usage",
            metric_type="multi",
            y_range=(0, 100),
            series_config={
                "User": Colors.ACCENT,
                "System": Colors.SUCCESS,
                "Idle": Colors.TEXT_SECONDARY,
            },
            detail_labels=[
                "Cores",
                "Logical Processors",
                "Base Speed",
                "Processes",
                "Threads",
                "Handles",
                "Context Switches/s",
                "Interrupts/s",
            ],
        )
        self._cpu_tile.expanded.connect(self._on_tile_expanded)
        self._cpu_tile.collapsed.connect(self._on_tile_collapsed)
        self._tiles_layout.addWidget(self._cpu_tile, 0, 0)  # 4x1 horizontal layout

        # Memory tile
        self._memory_tile = ExpandableMetricTile(
            "Memory Usage",
            metric_type="single",
            y_range=(0, 100),
            detail_labels=[
                "Total",
                "Available",
                "Cached",
                "Committed",
                "Paged Pool",
                "Non-paged Pool",
            ],
        )
        self._memory_tile.expanded.connect(self._on_tile_expanded)
        self._memory_tile.collapsed.connect(self._on_tile_collapsed)
        self._tiles_layout.addWidget(self._memory_tile, 0, 1)  # 4x1 horizontal layout

        # Disk tile
        self._disk_tile = ExpandableMetricTile(
            "Disk Activity",
            metric_type="multi",
            y_range=None,
            series_config={
                "Read": Colors.INFO,
                "Write": Colors.WARNING,
            },
            detail_labels=[
                "Read Speed",
                "Write Speed",
                "Active Time",
                "Avg Response",
                "Read Count/s",
                "Write Count/s",
            ],
        )
        self._disk_tile.expanded.connect(self._on_tile_expanded)
        self._disk_tile.collapsed.connect(self._on_tile_collapsed)
        self._tiles_layout.addWidget(self._disk_tile, 0, 2)  # 4x1 horizontal layout

        # Network tile
        self._network_tile = ExpandableMetricTile(
            "Network",
            metric_type="multi",
            y_range=None,
            series_config={
                "Down": Colors.SUCCESS,
                "Up": Colors.ACCENT,
            },
            detail_labels=[
                "Adapter",
                "IPv4 Address",
                "Download",
                "Upload",
                "Packets In/s",
                "Packets Out/s",
            ],
        )
        self._network_tile.expanded.connect(self._on_tile_expanded)
        self._network_tile.collapsed.connect(self._on_tile_collapsed)
        self._tiles_layout.addWidget(self._network_tile, 0, 3)  # 4x1 horizontal layout

        content_layout.addWidget(self._tiles_container)

        # === ROW 3: Collapsible sections ===
        # Installed Software section (collapsed by default)
        self._software_section = CollapsibleSection("Installed Software", expanded=False)
        self._software_table = SoftwareTableWidget()
        self._software_table.refresh_requested.connect(self._on_software_refresh)
        self._software_section.set_content(self._software_table)
        self._software_section.toggled.connect(self._on_software_section_toggled)
        content_layout.addWidget(self._software_section)

        # Startup Apps section (collapsed by default)
        self._startup_section = CollapsibleSection("Startup Apps", expanded=False)
        self._startup_table = StartupAppsWidget()
        self._startup_table.refresh_requested.connect(self._on_startup_refresh)
        self._startup_table.enable_changed.connect(self._on_startup_enable_changed)
        self._startup_table.add_requested.connect(self._on_startup_add)
        self._startup_table.remove_requested.connect(self._on_startup_remove)
        self._startup_section.set_content(self._startup_table)
        self._startup_section.toggled.connect(self._on_startup_section_toggled)
        content_layout.addWidget(self._startup_section)

        # Battery section (conditional, collapsed by default)
        self._battery_widget = None
        self._battery_section = None
        if self._system_monitor.has_battery():
            self._battery_section = CollapsibleSection("Battery", expanded=False)
            self._battery_widget = BatteryWidget()
            self._battery_section.set_content(self._battery_widget)
            self._battery_section.toggled.connect(self._on_battery_section_toggled)
            content_layout.addWidget(self._battery_section)

        # Spacer widget that shrinks when sections expand
        self._spacer = QWidget()
        self._spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(self._spacer)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # Track which collapsible section is expanded
        self._expanded_section = None

    def _on_tile_expanded(self, tile: ExpandableMetricTile) -> None:
        """When a tile expands, collapse others and make it span full width."""
        self._expanded_tile = tile

        # Collapse other tiles
        all_tiles = [self._cpu_tile, self._memory_tile, self._disk_tile, self._network_tile]
        for t in all_tiles:
            if t != tile and t.is_expanded:
                t.collapse()

        # Remove all tiles from layout
        for t in all_tiles:
            self._tiles_layout.removeWidget(t)

        # Expanded tile at top spanning all 4 columns
        self._tiles_layout.addWidget(tile, 0, 0, 1, 4)

        # Other 3 tiles below in a single row (3 columns, will stretch to match)
        col = 0
        for t in all_tiles:
            if t != tile:
                self._tiles_layout.addWidget(t, 1, col)
                col += 1

        # Make the 4th column (empty in row 1) not stretch
        # Columns 0-2 should stretch equally to fill the width
        for i in range(3):
            self._tiles_layout.setColumnStretch(i, 1)
        self._tiles_layout.setColumnStretch(3, 0)

    def _on_tile_collapsed(self, tile: ExpandableMetricTile) -> None:
        """When tile collapses, restore normal 4x1 horizontal layout."""
        # Only clear if this tile is still the expanded one.
        # When switching tiles, _on_tile_expanded sets the new tile first,
        # then collapses the old one — don't overwrite the new reference.
        if self._expanded_tile == tile:
            self._expanded_tile = None
        else:
            # Another tile is expanding — it will handle the layout
            return

        # Remove all tiles from layout
        all_tiles = [self._cpu_tile, self._memory_tile, self._disk_tile, self._network_tile]
        for t in all_tiles:
            self._tiles_layout.removeWidget(t)

        # Restore 4x1 horizontal layout
        self._tiles_layout.addWidget(self._cpu_tile, 0, 0)
        self._tiles_layout.addWidget(self._memory_tile, 0, 1)
        self._tiles_layout.addWidget(self._disk_tile, 0, 2)
        self._tiles_layout.addWidget(self._network_tile, 0, 3)

        # Reset column stretches
        for i in range(4):
            self._tiles_layout.setColumnStretch(i, 1)

    def _on_software_section_toggled(self, expanded: bool) -> None:
        """Handle software section expand/collapse."""
        if expanded:
            # Collapse any expanded metric tiles to give table more space
            self._collapse_all_metric_tiles()
            # Collapse other sections
            self._collapse_other_sections(self._software_section)
            # Set expanding policy for the table to fill space
            self._software_table.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            self._software_table.setMinimumHeight(200)
            # Hide spacer when section is expanded
            self._spacer.hide()
            self._expanded_section = self._software_section
        else:
            # Reset size policy
            self._software_table.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self._software_table.setMinimumHeight(0)
            # Show spacer when no section is expanded
            if self._expanded_section == self._software_section:
                self._spacer.show()
                self._expanded_section = None

    def _on_startup_section_toggled(self, expanded: bool) -> None:
        """Handle startup section expand/collapse."""
        if expanded:
            # Collapse any expanded metric tiles to give table more space
            self._collapse_all_metric_tiles()
            # Collapse other sections
            self._collapse_other_sections(self._startup_section)
            # Set expanding policy for the table to fill space
            self._startup_table.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            self._startup_table.setMinimumHeight(200)
            # Hide spacer when section is expanded
            self._spacer.hide()
            self._expanded_section = self._startup_section
        else:
            # Reset size policy
            self._startup_table.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self._startup_table.setMinimumHeight(0)
            # Show spacer when no section is expanded
            if self._expanded_section == self._startup_section:
                self._spacer.show()
                self._expanded_section = None

    def _on_battery_section_toggled(self, expanded: bool) -> None:
        """Handle battery section expand/collapse."""
        if expanded:
            # Collapse any expanded metric tiles to give content more space
            self._collapse_all_metric_tiles()
            # Collapse other sections
            self._collapse_other_sections(self._battery_section)
            # Hide spacer when section is expanded
            self._spacer.hide()
            self._expanded_section = self._battery_section
        else:
            # Show spacer when no section is expanded
            if self._expanded_section == self._battery_section:
                self._spacer.show()
                self._expanded_section = None

    def _collapse_other_sections(self, current_section: CollapsibleSection) -> None:
        """Collapse all sections except the current one."""
        sections = [self._software_section, self._startup_section]
        if self._battery_section:
            sections.append(self._battery_section)

        for section in sections:
            if section != current_section and section.is_expanded():
                section.set_expanded(False)

    def _collapse_all_metric_tiles(self) -> None:
        """Collapse all expanded metric tiles."""
        all_tiles = [self._cpu_tile, self._memory_tile, self._disk_tile, self._network_tile]
        for tile in all_tiles:
            if tile.is_expanded:
                tile.collapse()

    def _load_system_info_async(self) -> None:
        """Load static system information asynchronously."""
        from src.utils.thread_utils import SingleRunWorker
        from PySide6.QtCore import QThreadPool

        def _fetch_system_info():
            return self._windows_info.get_all_system_info()

        worker = SingleRunWorker(_fetch_system_info)
        worker.signals.result.connect(self._on_system_info_loaded)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _on_system_info_loaded(self, system_info: dict) -> None:
        """Handle system info loaded from worker."""
        # Hostname as header, other info as compact details
        hostname = system_info.get("System Name", "Unknown")
        details = {
            "Manufacturer": system_info.get("Manufacturer", "N/A"),
            "OS": system_info.get("OS Version", "N/A"),
            "Domain": system_info.get("Domain/Workgroup", "N/A"),
            "Time Zone": system_info.get("Time Zone", "N/A"),
        }
        self._system_info_header.set_data(hostname, details)

        # Set processor name as CPU tile subtitle
        self._processor_name = system_info.get("Processor", "Unknown")
        self._cpu_tile.set_subtitle(self._processor_name)

    def _load_system_info(self) -> None:
        """Load static system information (synchronous, for refresh)."""
        system_info = self._windows_info.get_all_system_info()

        # Hostname as header, other info as compact details
        hostname = system_info.get("System Name", "Unknown")
        details = {
            "Manufacturer": system_info.get("Manufacturer", "N/A"),
            "OS": system_info.get("OS Version", "N/A"),
            "Domain": system_info.get("Domain/Workgroup", "N/A"),
            "Time Zone": system_info.get("Time Zone", "N/A"),
        }
        self._system_info_header.set_data(hostname, details)

        # Set processor name as CPU tile subtitle
        self._processor_name = system_info.get("Processor", "Unknown")
        self._cpu_tile.set_subtitle(self._processor_name)

    def _start_workers(self) -> None:
        """Start background workers for live updates."""
        # Main metrics worker (updates tile values)
        metrics_worker = LoopingWorker(
            self.UPDATE_INTERVAL_MS,
            self._collect_metrics,
        )
        metrics_worker.signals.result.connect(self._update_tiles)
        metrics_worker.start()
        self._workers.append(metrics_worker)

        # Graph data worker (faster updates for smooth graphs)
        graph_worker = LoopingWorker(
            self.GRAPH_INTERVAL_MS,
            self._collect_graph_data,
        )
        graph_worker.signals.result.connect(self._update_graphs)
        graph_worker.start()
        self._workers.append(graph_worker)

        # Details worker (slower updates for detailed info)
        details_worker = LoopingWorker(
            5000,  # 5 seconds for system metrics (CPU freq, memory, disk, network)
            self._collect_details,
        )
        details_worker.signals.result.connect(self._update_details)
        details_worker.start()
        self._workers.append(details_worker)

    def _collect_metrics(self) -> dict:
        """Collect metrics for tile display (runs in worker thread)."""
        cpu_usage = self._system_monitor.get_cpu_usage()
        mem_info = self._system_monitor.get_memory_info()

        disk_info = self._system_monitor.get_disk_info()
        if disk_info:
            avg_disk = sum(d['percent'] for d in disk_info) / len(disk_info)
            total_used = sum(d['used'] for d in disk_info)
            total_space = sum(d['total'] for d in disk_info)
        else:
            avg_disk = 0
            total_used = 0
            total_space = 0

        net_io = self._perf_monitor.get_network_io()

        return {
            "cpu": cpu_usage,
            "mem_percent": mem_info['percent'],
            "mem_used": mem_info['used'],
            "mem_total": mem_info['total'],
            "disk_percent": avg_disk,
            "disk_used": total_used,
            "disk_total": total_space,
            "net_down": net_io.bytes_recv_per_sec / 1024,
            "net_up": net_io.bytes_sent_per_sec / 1024,
        }

    def _collect_graph_data(self) -> dict:
        """Collect data for graphs (runs in worker thread)."""
        cpu_times = self._perf_monitor.get_cpu_times()
        mem_percent = self._perf_monitor.get_memory_percent()
        disk_io = self._perf_monitor.get_disk_io()
        net_io = self._perf_monitor.get_network_io()

        return {
            "cpu_user": cpu_times.user,
            "cpu_system": cpu_times.system,
            "cpu_idle": cpu_times.idle,
            "mem_percent": mem_percent,
            "disk_read": disk_io.read_bytes_per_sec / (1024 * 1024),
            "disk_write": disk_io.write_bytes_per_sec / (1024 * 1024),
            "net_down": net_io.bytes_recv_per_sec / 1024,
            "net_up": net_io.bytes_sent_per_sec / 1024,
        }

    def _collect_details(self) -> dict:
        """Collect detailed info (runs in worker thread)."""
        cpu_count = psutil.cpu_count(logical=False) or 0
        cpu_logical = psutil.cpu_count(logical=True) or 0
        cpu_freq = psutil.cpu_freq()
        ctx_rate, int_rate = self._perf_monitor.get_cpu_rates()

        process_count = self._process_manager.get_process_count()
        thread_count, handle_count = self._process_manager.get_thread_handle_totals()

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk_io = self._perf_monitor.get_disk_io()
        net_io = self._perf_monitor.get_network_io()
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        active_adapter = "Unknown"
        ipv4_addr = "N/A"
        for iface, addr_list in addrs.items():
            if iface in stats and stats[iface].isup:
                for addr in addr_list:
                    if addr.family.name == 'AF_INET' and not addr.address.startswith('127.'):
                        active_adapter = iface
                        ipv4_addr = addr.address
                        break
                if ipv4_addr != "N/A":
                    break

        return {
            "cpu": {
                "Cores": str(cpu_count),
                "Logical Processors": str(cpu_logical),
                "Base Speed": f"{cpu_freq.current:.0f} MHz" if cpu_freq else "N/A",
                "Processes": str(process_count),
                "Threads": f"{thread_count:,}",
                "Handles": f"{handle_count:,}",
                "Context Switches/s": f"{ctx_rate:,.0f}",
                "Interrupts/s": f"{int_rate:,.0f}",
            },
            "memory": {
                "Total": format_bytes(mem.total),
                "Available": format_bytes(mem.available),
                "Cached": format_bytes(getattr(mem, 'cached', 0)),
                "Committed": format_bytes(swap.used + mem.used),
                "Paged Pool": format_bytes(getattr(mem, 'buffers', 0)),
                "Non-paged Pool": "N/A",
            },
            "disk": {
                "Read Speed": f"{disk_io.read_bytes_per_sec / (1024*1024):.1f} MB/s",
                "Write Speed": f"{disk_io.write_bytes_per_sec / (1024*1024):.1f} MB/s",
                "Active Time": "N/A",
                "Avg Response": "N/A",
                "Read Count/s": f"{disk_io.read_count_per_sec:.0f}",
                "Write Count/s": f"{disk_io.write_count_per_sec:.0f}",
            },
            "network": {
                "Adapter": active_adapter[:20] + "..." if len(active_adapter) > 20 else active_adapter,
                "IPv4 Address": ipv4_addr,
                "Download": f"{net_io.bytes_recv_per_sec / 1024:.1f} KB/s",
                "Upload": f"{net_io.bytes_sent_per_sec / 1024:.1f} KB/s",
                "Packets In/s": f"{net_io.packets_recv_per_sec:.0f}",
                "Packets Out/s": f"{net_io.packets_sent_per_sec:.0f}",
            },
        }

    @Slot(object)
    def _update_tiles(self, data: dict) -> None:
        """Update tile values (runs in UI thread)."""
        self._cpu_tile.update_value(
            f"{data['cpu']:.0f}%",
            data['cpu'],
            "Real-time usage"
        )
        self._memory_tile.update_value(
            f"{data['mem_percent']:.0f}%",
            data['mem_percent'],
            f"{data['mem_used']:.1f} / {data['mem_total']:.1f} GB"
        )
        self._disk_tile.update_value(
            f"{data['disk_percent']:.0f}%",
            data['disk_percent'],
            f"{data['disk_used']:.0f} / {data['disk_total']:.0f} GB"
        )
        net_total = data['net_down'] + data['net_up']
        self._network_tile.update_value(
            f"{net_total:.0f} KB/s",
            min(net_total / 10, 100),
            f"↓{data['net_down']:.0f} ↑{data['net_up']:.0f} KB/s"
        )

    @Slot(object)
    def _update_graphs(self, data: dict) -> None:
        """Update graph data points (runs in UI thread).

        Only updates the currently expanded tile's graph to reduce CPU usage.
        """
        # Only update the expanded tile's graph (if any)
        if self._expanded_tile is None:
            return

        # Skip updates during expand animation to avoid render storm
        if self._expanded_tile._animating:
            return

        if self._expanded_tile == self._cpu_tile and self._cpu_tile._graph is not None:
            self._cpu_tile._graph.add_points({
                "User": data['cpu_user'],
                "System": data['cpu_system'],
                "Idle": data['cpu_idle'],
            })
        elif self._expanded_tile == self._memory_tile and self._memory_tile._graph is not None:
            self._memory_tile.add_graph_point(data['mem_percent'])
        elif self._expanded_tile == self._disk_tile and self._disk_tile._graph is not None:
            self._disk_tile._graph.add_points({
                "Read": data['disk_read'],
                "Write": data['disk_write'],
            })
        elif self._expanded_tile == self._network_tile and self._network_tile._graph is not None:
            self._network_tile._graph.add_points({
                "Down": data['net_down'],
                "Up": data['net_up'],
            })

    @Slot(object)
    def _update_details(self, data: dict) -> None:
        """Update detail values (runs in UI thread)."""
        self._cpu_tile.update_details(data["cpu"])
        self._memory_tile.update_details(data["memory"])
        self._disk_tile.update_details(data["disk"])
        self._network_tile.update_details(data["network"])

    def _init_software_cache(self) -> None:
        """Initialize and start loading software cache."""
        # Connect cache signals
        self._software_cache.state_changed.connect(self._on_software_state_changed)
        self._software_cache.data_loaded.connect(self._on_software_loaded)
        self._software_cache.error_occurred.connect(self._on_software_error)

        # Start background load
        self._software_cache.load()

    @Slot(object)
    def _on_software_state_changed(self, state) -> None:
        """Handle software cache state change."""
        from src.services.data_cache import CacheState

        is_loading = (state == CacheState.LOADING)
        self._software_table.set_loading(is_loading)

    @Slot(object)
    def _on_software_loaded(self, software_list: list) -> None:
        """Handle software data loaded."""
        self._software_table.set_data(software_list)

    @Slot(str)
    def _on_software_error(self, error_msg: str) -> None:
        """Handle software cache error."""
        print(f"Error loading software: {error_msg}")
        # Still clear loading state
        self._software_table.set_loading(False)

    @Slot()
    def _on_software_refresh(self) -> None:
        """Handle software refresh request."""
        self._software_cache.refresh()

    def _init_startup_cache(self) -> None:
        """Initialize and start loading startup cache."""
        # Connect cache signals
        self._startup_cache.state_changed.connect(self._on_startup_state_changed)
        self._startup_cache.data_loaded.connect(self._on_startup_loaded)
        self._startup_cache.error_occurred.connect(self._on_startup_error)

        # Start background load
        self._startup_cache.load()

    @Slot(object)
    def _on_startup_state_changed(self, state) -> None:
        """Handle startup cache state change."""
        from src.services.data_cache import CacheState

        is_loading = (state == CacheState.LOADING)
        self._startup_table.set_loading(is_loading)

    @Slot(object)
    def _on_startup_loaded(self, startup_list: list) -> None:
        """Handle startup data loaded."""
        self._startup_table.set_data(startup_list)

    @Slot(str)
    def _on_startup_error(self, error_msg: str) -> None:
        """Handle startup cache error."""
        print(f"Error loading startup items: {error_msg}")
        self._startup_table.set_loading(False)

    @Slot()
    def _on_startup_refresh(self) -> None:
        """Handle startup refresh request."""
        self._startup_cache.refresh()

    @Slot(str, str, bool, str)
    def _on_startup_enable_changed(self, name: str, location: str, enabled: bool, original_name: str) -> None:
        """Handle startup enable/disable request."""
        success = self._startup_service.set_startup_enabled(name, location, enabled, original_name)
        if success:
            # Refresh the list
            self._startup_cache.refresh()
        else:
            print(f"Failed to {'enable' if enabled else 'disable'} startup item: {name}")
            # Revert checkbox state by refreshing
            self._startup_cache.refresh()

    @Slot(str, str, str)
    def _on_startup_add(self, name: str, command: str, location: str) -> None:
        """Handle add startup request."""
        success = self._startup_service.add_startup_app(name, command, location)
        if success:
            # Refresh the list
            self._startup_cache.refresh()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Failed to Add",
                f"Failed to add startup item '{name}'.\nYou may need administrator privileges."
            )

    @Slot(str, str)
    def _on_startup_remove(self, name: str, location: str) -> None:
        """Handle remove startup request."""
        success = self._startup_service.remove_startup_app(name, location)
        if success:
            # Refresh the list
            self._startup_cache.refresh()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Failed to Remove",
                f"Failed to remove startup item '{name}'.\nYou may need administrator privileges."
            )

    def refresh(self) -> None:
        """Manual refresh (called from menu)."""
        self._load_system_info()

    def pause_updates(self) -> None:
        """Pause all background workers (call when tab not visible)."""
        for worker in self._workers:
            worker.pause()

    def resume_updates(self) -> None:
        """Resume all background workers (call when tab becomes visible)."""
        for worker in self._workers:
            worker.resume()

    def cleanup(self) -> None:
        """Stop all workers - call when removing tab or closing app."""
        for worker in self._workers:
            worker.stop()
        self._workers.clear()

        # Clean up battery widget if present
        if self._battery_widget:
            self._battery_widget.cleanup()

    def closeEvent(self, event) -> None:
        """Clean up workers when tab is closed."""
        self.cleanup()
        event.accept()
