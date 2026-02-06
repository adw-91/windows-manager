"""System Tab - Modern card-based system information display."""

import os
import winreg

import psutil
import platform
import socket
from typing import Dict, List, Optional

from src.utils.win32.registry import read_string, read_binary, read_qword, enumerate_subkeys
from src.utils.win32.system_info import is_secure_boot_enabled
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, QThreadPool, QTimer

from src.services.windows_info import WindowsInfo
from src.utils.thread_utils import SingleRunWorker
from src.ui.theme import Colors
from src.ui.widgets.flow_layout import FlowLayout


class KeyValuePair(QWidget):
    """A widget that displays a key-value pair as a single unit for flow layouts."""

    def __init__(self, key: str, value: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._value = value
        self._value_label = None
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 16, 2)  # Right margin for spacing between pairs
        layout.setSpacing(6)

        # Key label
        key_label = QLabel(f"{self._key}:")
        key_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px;")
        key_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(key_label)

        # Value label
        self._value_label = QLabel(str(self._value))
        self._value_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY.name()}; font-size: 11px;")
        self._value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._value_label)

        # Set size policy so this widget doesn't stretch excessively
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_value(self, value: str):
        """Update the value."""
        self._value = value
        if self._value_label:
            self._value_label.setText(str(value))


class InfoCard(QFrame):
    """A modern card widget for displaying a group of related information with flow layout."""

    def __init__(self, title: str, icon: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._icon = icon
        self._kv_widgets: Dict[str, KeyValuePair] = {}
        self._flow_layout = None
        self._content_widget = None
        self._init_ui()

    def _init_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            InfoCard {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
            }}
            InfoCard:hover {{
                border-color: {Colors.ACCENT.name()};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Header with icon and title
        header = QHBoxLayout()
        header.setSpacing(8)

        if self._icon:
            icon_label = QLabel(self._icon)
            icon_label.setStyleSheet(f"font-size: 16px;")
            header.addWidget(icon_label)

        title_label = QLabel(self._title)
        title_label.setStyleSheet(f"""
            font-size: 13px;
            font-weight: bold;
            color: {Colors.ACCENT.name()};
        """)
        header.addWidget(title_label)
        header.addStretch()

        layout.addLayout(header)

        # Separator line
        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background-color: {Colors.BORDER.name()};")
        layout.addWidget(separator)

        # Content widget with flow layout
        self._content_widget = QWidget()
        self._flow_layout = FlowLayout(self._content_widget, margin=0, h_spacing=8, v_spacing=6)
        layout.addWidget(self._content_widget)

    def set_data(self, data: Dict[str, str]):
        """Set the card data using flow layout for natural reflow."""
        # Clear existing widgets
        while self._flow_layout.count():
            item = self._flow_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._kv_widgets.clear()

        # Create key-value pair widgets
        items = [(k, v) for k, v in data.items() if k != "Error"]

        for key, value in items:
            kv_widget = KeyValuePair(key, value)
            self._kv_widgets[key] = kv_widget
            self._flow_layout.addWidget(kv_widget)

        # Force layout update
        self._content_widget.updateGeometry()


class StatusIndicator(QFrame):
    """A small status indicator with icon and text."""

    def __init__(self, label: str, value: str = "", status: str = "neutral", parent=None):
        super().__init__(parent)
        self._init_ui(label, value, status)

    def _init_ui(self, label: str, value: str, status: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Status dot
        dot = QLabel("●")
        if status == "good":
            dot.setStyleSheet(f"color: {Colors.SUCCESS.name()}; font-size: 10px;")
        elif status == "warning":
            dot.setStyleSheet(f"color: {Colors.WARNING.name()}; font-size: 10px;")
        elif status == "error":
            dot.setStyleSheet(f"color: {Colors.ERROR.name()}; font-size: 10px;")
        else:
            dot.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 10px;")
        layout.addWidget(dot)

        # Label
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px;")
        layout.addWidget(lbl)

        layout.addStretch()

        # Value
        val = QLabel(value)
        val.setStyleSheet(f"color: {Colors.TEXT_PRIMARY.name()}; font-size: 11px; font-weight: 500;")
        layout.addWidget(val)

        self.setStyleSheet(f"""
            StatusIndicator {{
                background-color: {Colors.WINDOW_ALT.name()};
                border-radius: 4px;
            }}
        """)


class SystemTab(QWidget):
    """Tab for detailed system information with modern card-based UI."""

    def __init__(self):
        super().__init__()
        self._windows_info = WindowsInfo()
        self._cards: Dict[str, InfoCard] = {}
        self._worker = None
        self._loading_label = None
        self.init_ui()
        self._load_system_info()

        self._resize_timer = QTimer(self)
        self._resize_timer.setInterval(100)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_done)

    def resizeEvent(self, event) -> None:
        """Suppress card repaints during resize drag, batch at end."""
        if not self._resize_timer.isActive():
            self._card_container.setUpdatesEnabled(False)
        self._resize_timer.start()
        super().resizeEvent(event)

    def _on_resize_done(self) -> None:
        """Re-enable updates after resize drag ends."""
        self._card_container.setUpdatesEnabled(True)
        self._card_container.update()

    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Compact header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        title = QLabel("System Information")
        title.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {Colors.TEXT_PRIMARY.name()};
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 6px 16px;
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
                background: {Colors.WIDGET.name()};
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QPushButton:hover {{
                background: {Colors.WIDGET_HOVER.name()};
            }}
        """)
        header_layout.addWidget(refresh_btn)

        layout.addLayout(header_layout)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        # Loading label
        self._loading_label = QLabel("Loading system information...")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY.name()};
            font-style: italic;
            padding: 40px;
        """)
        content_layout.addWidget(self._loading_label)

        # Card container - single column layout
        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setSpacing(10)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_container.setVisible(False)

        # Create cards with icons - single column
        card_configs = [
            ("System Summary", "💻"),
            ("Hardware", "🔧"),
            ("Components", "🖥️"),
            ("Software", "📦"),
            ("Security", "🛡️"),
            ("Network", "🌐"),
        ]

        for name, icon in card_configs:
            card = InfoCard(name, icon)
            self._cards[name] = card
            self._card_layout.addWidget(card)

        content_layout.addWidget(self._card_container)
        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _load_system_info(self):
        """Load system information in background."""
        self._loading_label.setVisible(True)
        self._card_container.setVisible(False)

        if self._worker:
            try:
                self._worker.signals.finished.disconnect()
            except RuntimeError:
                pass

        self._worker = SingleRunWorker(self._collect_all_info)
        self._worker.signals.result.connect(self._on_data_loaded)
        self._worker.signals.error.connect(self._on_data_error)

        QThreadPool.globalInstance().start(self._worker)

    def _collect_all_info(self) -> Dict[str, Dict[str, str]]:
        """Collect all system information (runs in worker thread)."""
        return {
            "System Summary": self._get_system_summary(),
            "Hardware": self._get_hardware_resources(),
            "Components": self._get_components(),
            "Software": self._get_software_environment(),
            "Security": self._get_security_info(),
            "Network": self._get_network_info(),
        }

    def _get_system_summary(self) -> Dict[str, str]:
        """Get system summary information."""
        info = {}
        try:
            info["Computer Name"] = socket.gethostname()
            info["OS"] = f"{platform.system()} {platform.release()}"
            info["Version"] = platform.version()
            info["Manufacturer"] = self._windows_info.get_manufacturer()
            info["Model"] = self._windows_info.get_model()
            info["Architecture"] = platform.machine()
            info["Processor"] = self._windows_info.get_processor()

            mem = psutil.virtual_memory()
            info["RAM"] = f"{mem.total / (1024**3):.1f} GB"
            info["Available RAM"] = f"{mem.available / (1024**3):.1f} GB ({100-mem.percent:.0f}%)"

            boot_time = psutil.boot_time()
            from datetime import datetime
            boot_dt = datetime.fromtimestamp(boot_time)
            info["Boot Time"] = boot_dt.strftime("%Y-%m-%d %H:%M")

            info["Domain"] = self._windows_info.get_domain_workgroup()
            info["Time Zone"] = self._windows_info.get_timezone()

        except Exception as e:
            info["Error"] = str(e)
        return info

    def _get_hardware_resources(self) -> Dict[str, str]:
        """Get hardware resources information."""
        info = {}
        try:
            cpu_count = psutil.cpu_count(logical=False) or 0
            cpu_logical = psutil.cpu_count(logical=True) or 0
            info["CPU Cores"] = f"{cpu_count} physical, {cpu_logical} logical"

            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                info["CPU Speed"] = f"{cpu_freq.current:.0f} MHz (max {cpu_freq.max:.0f})"

            memory_sticks = self._windows_info._get_memory_stick_capacities()
            if memory_sticks:
                stick_gb = [f"{c/(1024**3):.0f}GB" for c in memory_sticks]
                info["Memory Config"] = f"{len(memory_sticks)} stick(s): {', '.join(stick_gb)}"

            info["BIOS"] = read_string(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\BIOS",
                "BIOSVersion",
            ) or "Unknown"
            bb_mfr = read_string(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\BIOS",
                "BaseBoardManufacturer",
            ) or "Unknown"
            bb_prod = read_string(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\BIOS",
                "BaseBoardProduct",
            ) or ""
            info["Baseboard"] = f"{bb_mfr} {bb_prod}".strip()

        except Exception as e:
            info["Error"] = str(e)
        return info

    def _get_components(self) -> Dict[str, str]:
        """Get components information."""
        info = {}
        try:
            # Display adapter from registry
            display = read_string(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000",
                "DriverDesc",
            )
            info["Display"] = display or "Unknown"

            # VRAM from registry (try qword first, then binary)
            vram_bytes = read_qword(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000",
                "HardwareInformation.qwMemorySize",
            )
            if vram_bytes and vram_bytes > 0:
                info["VRAM"] = f"{vram_bytes / (1024**3):.1f} GB"
            else:
                vram_bin = read_binary(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000",
                    "HardwareInformation.MemorySize",
                )
                if vram_bin and len(vram_bin) >= 4:
                    import struct
                    vram_val = struct.unpack_from("<Q" if len(vram_bin) >= 8 else "<I", vram_bin)[0]
                    if vram_val > 0:
                        info["VRAM"] = f"{vram_val / (1024**3):.1f} GB"

            # Sound device from registry
            sound_class = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e96c-e325-11ce-bfc1-08002be10318}"
            sound_subkeys = enumerate_subkeys(winreg.HKEY_LOCAL_MACHINE, sound_class)
            sound_name = None
            for sk in sound_subkeys:
                if sk.isdigit():
                    desc = read_string(
                        winreg.HKEY_LOCAL_MACHINE,
                        f"{sound_class}\\{sk}",
                        "DriverDesc",
                    )
                    if desc:
                        sound_name = desc
                        break
            info["Sound"] = sound_name or "Unknown"

            total_disk = sum(
                psutil.disk_usage(p.mountpoint).total
                for p in psutil.disk_partitions()
                if not p.mountpoint.startswith('/snap')
            )
            info["Storage"] = f"{total_disk / (1024**3):.0f} GB ({len(psutil.disk_partitions())} partitions)"

            # Optical drive
            optical = read_string(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Services\cdrom\Enum",
                "0",
            )
            info["Optical"] = optical or "None"

        except Exception as e:
            info["Error"] = str(e)
        return info

    def _get_software_environment(self) -> Dict[str, str]:
        """Get software environment information."""
        info = {}
        try:
            info["User"] = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"
            from src.services.process_manager import get_process_manager
            info["Processes"] = str(get_process_manager().get_process_count())

            services = list(psutil.win_service_iter()) if hasattr(psutil, 'win_service_iter') else []
            running = sum(1 for s in services if s.status() == 'running')
            info["Services"] = f"{running} running / {len(services)} total"

            info["Windows Dir"] = os.environ.get("WINDIR", "C:\\Windows")
            info["PATH Entries"] = str(len(os.environ.get("PATH", "").split(";")))
            info["Locale"] = self._windows_info.get_system_locale()

        except Exception as e:
            info["Error"] = str(e)
        return info

    def _get_security_info(self) -> Dict[str, str]:
        """Get security information."""
        info = {}
        try:
            info["Security Center"] = "Active" if self._is_service_running("wscsvc") else "Inactive"
            info["Defender"] = "Running" if self._is_service_running("WinDefend") else "Stopped"
            info["Firewall"] = "Running" if self._is_service_running("mpssvc") else "Stopped"

            from src.utils.win32.registry import read_dword
            uac_val = read_dword(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
                "EnableLUA",
            )
            if uac_val is not None:
                info["UAC"] = "Enabled" if uac_val else "Disabled"
            else:
                info["UAC"] = "Unknown"

            sb = is_secure_boot_enabled()
            info["Secure Boot"] = "Enabled" if sb is True else ("Disabled" if sb is False else "N/A")

            info["Windows Update"] = "Running" if self._is_service_running("wuauserv") else "Stopped"

        except Exception as e:
            info["Error"] = str(e)
        return info

    def _get_network_info(self) -> Dict[str, str]:
        """Get network information."""
        info = {}
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            for iface, addr_list in addrs.items():
                if iface in stats and stats[iface].isup:
                    for addr in addr_list:
                        if addr.family.name == 'AF_INET' and not addr.address.startswith('127.'):
                            info["Active Adapter"] = iface
                            info["IPv4"] = addr.address
                            if stats[iface].speed > 0:
                                info["Speed"] = f"{stats[iface].speed} Mbps"
                            break
                    if "IPv4" in info:
                        break

            info["Hostname"] = socket.gethostname()
            try:
                info["FQDN"] = socket.getfqdn()
            except Exception:
                pass

            info["Adapters"] = str(len([s for s in stats.values() if s.isup]))

        except Exception as e:
            info["Error"] = str(e)
        return info

    def _is_service_running(self, service_name: str) -> bool:
        """Check if a Windows service is running."""
        try:
            service = psutil.win_service_get(service_name)
            return service.status() == 'running'
        except Exception:
            return False

    @Slot(object)
    def _on_data_loaded(self, data: Dict[str, Dict[str, str]]):
        """Handle loaded system information."""
        if not isinstance(data, dict):
            return

        for section_name, section_data in data.items():
            if section_name in self._cards and section_data:
                self._cards[section_name].set_data(section_data)

        self._loading_label.setVisible(False)
        self._card_container.setVisible(True)

    @Slot(str)
    def _on_data_error(self, error_msg: str):
        """Handle error loading system information."""
        self._loading_label.setText(f"Error: {error_msg}")
        self._loading_label.setStyleSheet(f"color: {Colors.ERROR.name()};")

    def refresh(self):
        """Refresh the data in this tab."""
        self._load_system_info()
