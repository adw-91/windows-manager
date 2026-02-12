"""System Tab - Tabbed sub-section system information display."""

import ctypes
import os
import struct
import winreg

import psutil
import platform
import socket
from ctypes import wintypes
from datetime import datetime
from typing import Dict, List, Optional

from src.utils.win32.registry import (
    read_string, read_binary, read_dword, read_qword, enumerate_subkeys,
)
from src.utils.win32.system_info import is_secure_boot_enabled, get_firmware_type
from src.utils.win32.wmi import WmiConnection
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy, QTabWidget, QGridLayout,
)
from PySide6.QtCore import Qt, Slot, QThreadPool

from src.services.windows_info import WindowsInfo
from src.utils.thread_utils import SingleRunWorker
from src.ui.theme import Colors


class SectionCard(QFrame):
    """A card with accent title, bordered container, and alternating-row key-value grid.

    Visual design:
    - WIDGET background with 1px BORDER, 8px border-radius
    - Accent-colored bold title with separator line
    - Left-aligned keys (160px column), left-aligned values
    - Alternating row backgrounds (WINDOW_ALT vs transparent)
    """

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._grid: Optional[QGridLayout] = None
        self._row_count = 0
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet(f"""
            SectionCard {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if self._title:
            title_label = QLabel(self._title)
            title_label.setStyleSheet(f"""
                font-size: 13px;
                font-weight: bold;
                color: {Colors.ACCENT.name()};
                padding: 10px 12px 6px 12px;
                background: transparent;
            """)
            layout.addWidget(title_label)

            separator = QFrame()
            separator.setFixedHeight(1)
            separator.setStyleSheet(
                f"background-color: {Colors.BORDER.name()}; margin: 0 8px;"
            )
            layout.addWidget(separator)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setHorizontalSpacing(0)
        self._grid.setVerticalSpacing(0)
        self._grid.setColumnMinimumWidth(0, 160)
        layout.addLayout(self._grid)
        layout.addStretch()

    def set_data(self, data: Dict[str, str]) -> None:
        """Replace all rows with new data."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._row_count = 0

        for key, value in data.items():
            if key == "Error":
                continue
            self._add_row(key, str(value))

    def _add_row(self, key: str, value: str) -> None:
        # Alternating row background
        if self._row_count % 2 == 0:
            row_bg = f"background-color: {Colors.WINDOW_ALT.name()};"
        else:
            row_bg = "background: transparent;"

        key_label = QLabel(f"{key}:")
        key_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 12px; "
            f"padding: 6px 8px; {row_bg}"
        )
        key_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        key_label.setMinimumWidth(160)

        value_label = QLabel(value)
        value_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY.name()}; font-size: 12px; "
            f"font-weight: 500; padding: 6px 8px; {row_bg}"
        )
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setWordWrap(True)

        self._grid.addWidget(key_label, self._row_count, 0)
        self._grid.addWidget(value_label, self._row_count, 1)
        self._row_count += 1


# Sub-tab index constants
TAB_SUMMARY = 0
TAB_HARDWARE = 1
TAB_COMPONENTS = 2
TAB_SECURITY = 3
TAB_NETWORK = 4


class SystemTab(QWidget):
    """Tab for detailed system information with tabbed sub-sections."""

    def __init__(self):
        super().__init__()
        self._windows_info = WindowsInfo()
        self._loaded_subtabs: set = set()
        self._workers: Dict[int, SingleRunWorker] = {}

        # Per-subtab card references
        self._summary_card: Optional[SectionCard] = None
        self._hardware_card: Optional[SectionCard] = None
        self._boot_firmware_card: Optional[SectionCard] = None
        self._components_card: Optional[SectionCard] = None
        self._security_card: Optional[SectionCard] = None
        self._tpm_card: Optional[SectionCard] = None
        self._bitlocker_card: Optional[SectionCard] = None
        self._network_card: Optional[SectionCard] = None

        # Per-subtab loading labels
        self._loading_labels: Dict[int, QLabel] = {}

        self.init_ui()
        # Load summary tab immediately
        self._load_subtab_data(TAB_SUMMARY)

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

        # Tab widget for sub-sections (5 tabs)
        self._tab_widget = QTabWidget()
        self._tab_widget.currentChanged.connect(self._on_subtab_changed)

        self._tab_widget.addTab(self._create_summary_tab(), "Summary")
        self._tab_widget.addTab(self._create_hardware_tab(), "Hardware")
        self._tab_widget.addTab(self._create_components_tab(), "Components")
        self._tab_widget.addTab(self._create_security_tab(), "Security")
        self._tab_widget.addTab(self._create_network_tab(), "Network")

        layout.addWidget(self._tab_widget)

    def _create_loading_label(self, tab_index: int) -> QLabel:
        """Create a loading label for a sub-tab."""
        label = QLabel("Loading...")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY.name()};
            font-style: italic;
            padding: 40px;
        """)
        self._loading_labels[tab_index] = label
        return label

    def _create_subtab_container(self, tab_index: int, content_widget: QWidget) -> QWidget:
        """Create a scrollable container for a sub-tab with a pre-built content widget."""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Loading label
        loading = self._create_loading_label(tab_index)
        container_layout.addWidget(loading)

        # Scroll area wrapping the content widget
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        scroll.setWidget(content_widget)
        scroll.setVisible(False)
        container_layout.addWidget(scroll)

        # Store scroll ref on container for later show/hide
        container._scroll = scroll
        return container

    def _create_summary_tab(self) -> QWidget:
        self._summary_card = SectionCard("System Summary")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(16)
        lay.addWidget(self._summary_card)
        return self._create_subtab_container(TAB_SUMMARY, content)

    def _create_compound_card(self, *cards: SectionCard) -> QFrame:
        """Wrap multiple SectionCards in a single bordered container."""
        borderless = "SectionCard { background: transparent; border: none; border-radius: 0; }"
        for card in cards:
            card.setStyleSheet(borderless)

        container = QFrame()
        container.setObjectName("compound_card")
        container.setStyleSheet(f"""
            #compound_card {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
            }}
        """)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for card in cards:
            layout.addWidget(card)
        layout.addStretch()

        return container

    def _create_hardware_tab(self) -> QWidget:
        """Single card containing Hardware + Boot & Firmware sections."""
        self._hardware_card = SectionCard("Hardware")
        self._boot_firmware_card = SectionCard("Boot & Firmware")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(16)
        lay.addWidget(self._create_compound_card(
            self._hardware_card, self._boot_firmware_card,
        ))

        return self._create_subtab_container(TAB_HARDWARE, content)

    def _create_components_tab(self) -> QWidget:
        self._components_card = SectionCard("Components")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(16)
        lay.addWidget(self._components_card)
        return self._create_subtab_container(TAB_COMPONENTS, content)

    def _create_security_tab(self) -> QWidget:
        """Single card containing Security Status + TPM + BitLocker sections."""
        self._security_card = SectionCard("Security Status")
        self._tpm_card = SectionCard("TPM")
        self._bitlocker_card = SectionCard("BitLocker Encryption")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)
        lay.addWidget(self._create_compound_card(
            self._security_card, self._tpm_card, self._bitlocker_card,
        ))

        return self._create_subtab_container(TAB_SECURITY, content)

    def _create_network_tab(self) -> QWidget:
        self._network_card = SectionCard("Network")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(16)
        lay.addWidget(self._network_card)
        return self._create_subtab_container(TAB_NETWORK, content)

    @Slot(int)
    def _on_subtab_changed(self, index: int) -> None:
        """Handle sub-tab change — trigger lazy load if needed."""
        if index not in self._loaded_subtabs:
            self._load_subtab_data(index)

    def _load_subtab_data(self, tab_index: int) -> None:
        """Load data for a specific sub-tab in background."""
        collectors = {
            TAB_SUMMARY: self._collect_summary_info,
            TAB_HARDWARE: self._collect_hardware_info,
            TAB_COMPONENTS: self._collect_components_info,
            TAB_SECURITY: self._collect_security_info,
            TAB_NETWORK: self._collect_network_info,
        }

        collector = collectors.get(tab_index)
        if not collector:
            return

        # Show loading state
        if tab_index in self._loading_labels:
            self._loading_labels[tab_index].setVisible(True)
            container = self._tab_widget.widget(tab_index)
            if hasattr(container, '_scroll'):
                container._scroll.setVisible(False)

        worker = SingleRunWorker(collector)
        worker.signals.result.connect(lambda data, idx=tab_index: self._on_subtab_data_loaded(idx, data))
        worker.signals.error.connect(lambda err, idx=tab_index: self._on_subtab_error(idx, err))
        self._workers[tab_index] = worker
        QThreadPool.globalInstance().start(worker)

    @Slot()
    def _on_subtab_data_loaded(self, tab_index: int, data: dict) -> None:
        """Handle loaded sub-tab data."""
        self._loaded_subtabs.add(tab_index)

        # Hide loading, show scroll area
        if tab_index in self._loading_labels:
            self._loading_labels[tab_index].setVisible(False)
        container = self._tab_widget.widget(tab_index)
        if hasattr(container, '_scroll'):
            container._scroll.setVisible(True)

        # Populate cards
        if tab_index == TAB_SUMMARY and self._summary_card:
            self._summary_card.set_data(data)
        elif tab_index == TAB_HARDWARE:
            if self._hardware_card:
                self._hardware_card.set_data(data.get("hardware", {}))
            if self._boot_firmware_card:
                self._boot_firmware_card.set_data(data.get("boot_firmware", {}))
        elif tab_index == TAB_COMPONENTS and self._components_card:
            self._components_card.set_data(data)
        elif tab_index == TAB_SECURITY:
            if self._security_card:
                self._security_card.set_data(data.get("security", {}))
            if self._tpm_card:
                self._tpm_card.set_data(data.get("tpm", {}))
            if self._bitlocker_card:
                self._bitlocker_card.set_data(data.get("bitlocker", {}))
        elif tab_index == TAB_NETWORK and self._network_card:
            self._network_card.set_data(data)

    @Slot()
    def _on_subtab_error(self, tab_index: int, error_msg: str) -> None:
        """Handle error loading sub-tab data."""
        if tab_index in self._loading_labels:
            self._loading_labels[tab_index].setText(f"Error: {error_msg}")
            self._loading_labels[tab_index].setStyleSheet(f"color: {Colors.ERROR.name()};")

    # -- Data collectors (run in worker threads) --

    def _collect_summary_info(self) -> Dict[str, str]:
        """Collect summary information (identity/status only)."""
        info = {}
        try:
            info["Computer Name"] = socket.gethostname()
            info["OS"] = f"{platform.system()} {platform.release()}"
            info["Version"] = platform.version()
            info["Model"] = self._windows_info.get_model()
            info["Architecture"] = platform.machine()

            boot_dt = datetime.fromtimestamp(psutil.boot_time())
            info["Boot Time"] = boot_dt.strftime("%Y-%m-%d %H:%M")

            info["Domain"] = self._windows_info.get_domain_workgroup()
            info["Time Zone"] = self._windows_info.get_timezone()

            info["User"] = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"

            from src.services.process_manager import get_process_manager
            info["Processes"] = str(get_process_manager().get_process_count())

            services = list(psutil.win_service_iter()) if hasattr(psutil, 'win_service_iter') else []
            running = sum(1 for s in services if s.status() == 'running')
            info["Services"] = f"{running} running / {len(services)} total"

            info["Locale"] = self._windows_info.get_system_locale()

        except Exception as e:
            info["Error"] = str(e)
        return info

    def _collect_hardware_info(self) -> Dict[str, dict]:
        """Collect hardware + boot/firmware information as merged dict."""
        hardware = {}
        try:
            hardware["Processor"] = self._windows_info.get_processor()

            cpu_count = psutil.cpu_count(logical=False) or 0
            cpu_logical = psutil.cpu_count(logical=True) or 0
            hardware["CPU Cores"] = f"{cpu_count} physical, {cpu_logical} logical"

            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                hardware["CPU Speed"] = f"{cpu_freq.current:.0f} MHz (max {cpu_freq.max:.0f})"

            mem = psutil.virtual_memory()
            hardware["Total RAM"] = f"{mem.total / (1024**3):.1f} GB"

            memory_sticks = self._windows_info._get_memory_stick_capacities()
            if memory_sticks:
                stick_gb = [f"{c/(1024**3):.0f}GB" for c in memory_sticks]
                hardware["Memory Config"] = f"{len(memory_sticks)} stick(s): {', '.join(stick_gb)}"

            bios_path = r"HARDWARE\DESCRIPTION\System\BIOS"
            hardware["Manufacturer"] = read_string(
                winreg.HKEY_LOCAL_MACHINE, bios_path, "SystemManufacturer",
            ) or "Unknown"
            hardware["Product Name"] = read_string(
                winreg.HKEY_LOCAL_MACHINE, bios_path, "SystemProductName",
            ) or "Unknown"
            hardware["BIOS"] = read_string(
                winreg.HKEY_LOCAL_MACHINE, bios_path, "BIOSVersion",
            ) or "Unknown"

            bb_mfr = read_string(
                winreg.HKEY_LOCAL_MACHINE, bios_path, "BaseBoardManufacturer",
            ) or "Unknown"
            bb_prod = read_string(
                winreg.HKEY_LOCAL_MACHINE, bios_path, "BaseBoardProduct",
            ) or ""
            hardware["Baseboard"] = f"{bb_mfr} {bb_prod}".strip()

        except Exception as e:
            hardware["Error"] = str(e)

        boot_firmware = self._get_boot_firmware_info()

        return {"hardware": hardware, "boot_firmware": boot_firmware}

    def _collect_components_info(self) -> Dict[str, str]:
        """Collect components information."""
        info = {}
        try:
            display_class = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"

            # Enumerate all display adapters
            display_subkeys = enumerate_subkeys(winreg.HKEY_LOCAL_MACHINE, display_class)
            adapter_idx = 0
            for sk in display_subkeys:
                if sk.isdigit():
                    desc = read_string(
                        winreg.HKEY_LOCAL_MACHINE, f"{display_class}\\{sk}", "DriverDesc",
                    )
                    if desc:
                        prefix = "Display" if adapter_idx == 0 else f"Display {adapter_idx + 1}"
                        info[prefix] = desc

                        # VRAM for this adapter
                        vram_bytes = read_qword(
                            winreg.HKEY_LOCAL_MACHINE, f"{display_class}\\{sk}",
                            "HardwareInformation.qwMemorySize",
                        )
                        if vram_bytes and vram_bytes > 0:
                            info[f"{prefix} VRAM"] = f"{vram_bytes / (1024**3):.1f} GB"
                        else:
                            vram_bin = read_binary(
                                winreg.HKEY_LOCAL_MACHINE, f"{display_class}\\{sk}",
                                "HardwareInformation.MemorySize",
                            )
                            if vram_bin and len(vram_bin) >= 4:
                                vram_val = struct.unpack_from(
                                    "<Q" if len(vram_bin) >= 8 else "<I", vram_bin
                                )[0]
                                if vram_val > 0:
                                    info[f"{prefix} VRAM"] = f"{vram_val / (1024**3):.1f} GB"

                        driver_ver = read_string(
                            winreg.HKEY_LOCAL_MACHINE, f"{display_class}\\{sk}", "DriverVersion",
                        )
                        if driver_ver:
                            info[f"{prefix} Driver"] = driver_ver

                        adapter_idx += 1

            # Sound devices
            sound_class = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e96c-e325-11ce-bfc1-08002be10318}"
            sound_subkeys = enumerate_subkeys(winreg.HKEY_LOCAL_MACHINE, sound_class)
            sound_idx = 0
            for sk in sound_subkeys:
                if sk.isdigit():
                    desc = read_string(
                        winreg.HKEY_LOCAL_MACHINE, f"{sound_class}\\{sk}", "DriverDesc",
                    )
                    if desc:
                        prefix = "Sound" if sound_idx == 0 else f"Sound {sound_idx + 1}"
                        info[prefix] = desc
                        sound_idx += 1

            total_disk = sum(
                psutil.disk_usage(p.mountpoint).total
                for p in psutil.disk_partitions()
                if not p.mountpoint.startswith('/snap')
            )
            info["Storage"] = f"{total_disk / (1024**3):.0f} GB ({len(psutil.disk_partitions())} partitions)"

            optical = read_string(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Services\cdrom\Enum",
                "0",
            )
            info["Optical Drive"] = optical or "None"

        except Exception as e:
            info["Error"] = str(e)
        return info

    def _collect_security_info(self) -> Dict[str, dict]:
        """Collect security + TPM + BitLocker information."""
        security = {}
        try:
            security["Security Center"] = "Active" if self._is_service_running("wscsvc") else "Inactive"
            security["Windows Defender"] = "Running" if self._is_service_running("WinDefend") else "Stopped"
            security["Firewall"] = "Running" if self._is_service_running("mpssvc") else "Stopped"

            uac_val = read_dword(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
                "EnableLUA",
            )
            if uac_val is not None:
                security["UAC"] = "Enabled" if uac_val else "Disabled"
            else:
                security["UAC"] = "Unknown"

            sb = is_secure_boot_enabled()
            security["Secure Boot"] = "Enabled" if sb is True else ("Disabled" if sb is False else "N/A")

            security["Windows Update"] = "Running" if self._is_service_running("wuauserv") else "Stopped"

            # Credential Guard
            cg_val = read_dword(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\DeviceGuard",
                "EnableVirtualizationBasedSecurity",
            )
            if cg_val is not None:
                security["Virtualization-Based Security"] = "Enabled" if cg_val else "Disabled"

        except Exception as e:
            security["Error"] = str(e)

        tpm = self._get_tpm_info()
        bitlocker = self._get_bitlocker_info()

        return {"security": security, "tpm": tpm, "bitlocker": bitlocker}

    def _collect_network_info(self) -> Dict[str, str]:
        """Collect network information."""
        info = {}
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            # Find active adapter with non-loopback IPv4
            for iface, addr_list in addrs.items():
                if iface in stats and stats[iface].isup:
                    for addr in addr_list:
                        if addr.family.name == 'AF_INET' and not addr.address.startswith('127.'):
                            info["Active Adapter"] = iface
                            info["IPv4 Address"] = addr.address
                            if addr.netmask:
                                info["Subnet Mask"] = addr.netmask
                            if stats[iface].speed > 0:
                                info["Link Speed"] = f"{stats[iface].speed} Mbps"
                            info["MTU"] = str(stats[iface].mtu) if stats[iface].mtu else "N/A"
                            break
                    if "IPv4 Address" in info:
                        break

            info["Hostname"] = socket.gethostname()
            try:
                info["FQDN"] = socket.getfqdn()
            except Exception:
                pass

            # Default gateway from registry
            try:
                gateway = read_string(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters",
                    "DefaultGateway",
                )
                if gateway:
                    info["Default Gateway"] = gateway
            except Exception:
                pass

            # DNS servers
            try:
                dns = read_string(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters",
                    "NameServer",
                )
                if dns:
                    info["DNS Servers"] = dns
            except Exception:
                pass

            up_count = len([s for s in stats.values() if s.isup])
            info["Active Adapters"] = str(up_count)
            info["Total Adapters"] = str(len(stats))

        except Exception as e:
            info["Error"] = str(e)
        return info

    # -- Helpers --

    def _get_bitlocker_info(self) -> Dict[str, str]:
        """Query BitLocker status via WMI, with registry fallback for non-admin."""
        PROTECTION_STATUS = {0: "Off", 1: "On", 2: "Unknown"}
        CONVERSION_STATUS = {
            0: "Fully Decrypted", 1: "Fully Encrypted", 2: "Encryption In Progress",
            3: "Decryption In Progress", 4: "Encryption Paused", 5: "Decryption Paused",
        }
        ENCRYPTION_METHOD = {
            0: "None", 1: "AES 128 with Diffuser", 2: "AES 256 with Diffuser",
            3: "AES 128", 4: "AES 256", 5: "Hardware Encryption",
            6: "XTS-AES 128", 7: "XTS-AES 256",
        }

        info = {}
        try:
            conn = WmiConnection(r"root\cimv2\Security\MicrosoftVolumeEncryption")
            volumes = conn.query(
                "SELECT DriveLetter, ProtectionStatus, ConversionStatus, EncryptionMethod "
                "FROM Win32_EncryptableVolume"
            )
            if not volumes:
                info["Status"] = "No encryptable volumes found"
                return info

            for vol in volumes:
                letter = vol.get("DriveLetter") or "?"
                prot = int(vol.get("ProtectionStatus") or 0)
                conv = int(vol.get("ConversionStatus") or 0)
                method = int(vol.get("EncryptionMethod") or 0)

                info[f"{letter} Protection"] = PROTECTION_STATUS.get(prot, str(prot))
                info[f"{letter} Status"] = CONVERSION_STATUS.get(conv, str(conv))
                if method > 0:
                    info[f"{letter} Method"] = ENCRYPTION_METHOD.get(method, str(method))

        except Exception:
            # WMI requires admin — fall back to registry for partial info
            info = self._get_bitlocker_registry_fallback()
        return info

    def _get_bitlocker_registry_fallback(self) -> Dict[str, str]:
        """Read BitLocker policy/status from registry when WMI is access-denied."""
        info = {}

        # Basic encryption state
        boot_status = read_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\BitlockerStatus",
            "BootStatus",
        )
        if boot_status is not None:
            info["Boot Status"] = "Encrypted" if boot_status else "Not encrypted"

        # Encryption method policy (from Intune / GPO)
        POLICY_METHODS = {
            3: "AES-CBC 128-bit", 4: "AES-CBC 256-bit",
            6: "XTS-AES 128-bit", 7: "XTS-AES 256-bit",
        }
        enc_method = read_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\FVE",
            "EncryptionMethodWithXtsOs",
        )
        if enc_method is not None:
            info["OS Drive Policy"] = POLICY_METHODS.get(enc_method, str(enc_method))

        enc_method_fixed = read_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Policies\Microsoft\FVE",
            "EncryptionMethodWithXtsFdv",
        )
        if enc_method_fixed is not None:
            info["Fixed Drive Policy"] = POLICY_METHODS.get(enc_method_fixed, str(enc_method_fixed))

        # Check if BitLocker policy is configured via Intune/MDM
        policy_keys = enumerate_subkeys(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\PolicyManager\current\device\BitLocker",
        )
        if policy_keys:
            info["MDM Policy"] = "Configured"

        if not info:
            info["Status"] = "BitLocker not available"
        else:
            info["Note"] = "Run as administrator for full details"

        return info

    def _get_tpm_info(self) -> Dict[str, str]:
        """Query TPM information via TBS API (non-admin), with WMI fallback (admin)."""
        info = {}

        # TBS API — works without admin privileges
        try:
            class TPM_DEVICE_INFO(ctypes.Structure):
                _fields_ = [
                    ("structVersion", wintypes.DWORD),
                    ("tpmVersion", wintypes.DWORD),
                    ("tpmInterfaceType", wintypes.DWORD),
                    ("tpmImpRevision", wintypes.DWORD),
                ]

            tbs = ctypes.WinDLL("tbs.dll")
            dev_info = TPM_DEVICE_INFO()
            dev_info.structVersion = 1
            result = tbs.Tbsi_GetDeviceInfo(
                ctypes.sizeof(dev_info), ctypes.byref(dev_info)
            )

            if result == 0:  # TBS_SUCCESS
                info["Present"] = "Yes"
                version_map = {1: "1.2", 2: "2.0"}
                info["TPM Version"] = version_map.get(dev_info.tpmVersion, str(dev_info.tpmVersion))

                interface_map = {
                    1: "Trust Zone", 2: "Hardware TPM", 3: "Emulator", 4: "SPB",
                }
                info["Interface Type"] = interface_map.get(
                    dev_info.tpmInterfaceType, str(dev_info.tpmInterfaceType)
                )

                if dev_info.tpmImpRevision:
                    info["Implementation Revision"] = str(dev_info.tpmImpRevision)
        except Exception:
            pass

        # WMI — provides more detail but requires admin
        try:
            conn = WmiConnection(r"root\cimv2\Security\MicrosoftTpm")
            tpm = conn.query_single("SELECT * FROM Win32_Tpm")
            if tpm:
                if "Present" not in info:
                    info["Present"] = "Yes"

                enabled = tpm.get("IsEnabled_InitialValue")
                info["Enabled"] = "Yes" if enabled else "No"

                activated = tpm.get("IsActivated_InitialValue")
                info["Activated"] = "Yes" if activated else "No"

                owned = tpm.get("IsOwned_InitialValue")
                info["Owned"] = "Yes" if owned else "No"

                spec = tpm.get("SpecVersion")
                if spec:
                    info["Spec Version"] = str(spec)

                mfr_ver = tpm.get("ManufacturerVersion")
                if mfr_ver:
                    info["Manufacturer Version"] = str(mfr_ver)

                pp_ver = tpm.get("PhysicalPresenceVersionInfo")
                if pp_ver:
                    info["Physical Presence Version"] = str(pp_ver)
        except Exception:
            pass

        if not info:
            info["Status"] = "No TPM detected"

        return info

    def _get_boot_firmware_info(self) -> Dict[str, str]:
        """Collect boot and firmware info from ctypes + registry."""
        info = {}
        try:
            info["Firmware Type"] = get_firmware_type()

            sb = is_secure_boot_enabled()
            info["Secure Boot"] = "Enabled" if sb is True else ("Disabled" if sb is False else "N/A")

            bios_path = r"HARDWARE\DESCRIPTION\System\BIOS"

            release_date = read_string(winreg.HKEY_LOCAL_MACHINE, bios_path, "BIOSReleaseDate")
            if release_date:
                info["BIOS Release Date"] = release_date

            bios_ver = read_string(winreg.HKEY_LOCAL_MACHINE, bios_path, "SystemBiosVersion")
            if bios_ver:
                info["System BIOS Version"] = bios_ver

            sys_family = read_string(winreg.HKEY_LOCAL_MACHINE, bios_path, "SystemFamily")
            if sys_family:
                info["System Family"] = sys_family

            bios_version = read_string(winreg.HKEY_LOCAL_MACHINE, bios_path, "BIOSVersion")
            if bios_version:
                info["BIOS Version"] = bios_version

            sys_sku = read_string(winreg.HKEY_LOCAL_MACHINE, bios_path, "SystemSKU")
            if sys_sku:
                info["System SKU"] = sys_sku

            smbios_major = read_dword(winreg.HKEY_LOCAL_MACHINE, bios_path, "SmbiosMajorVersion")
            smbios_minor = read_dword(winreg.HKEY_LOCAL_MACHINE, bios_path, "SmbiosMinorVersion")
            if smbios_major is not None and smbios_minor is not None:
                info["SMBIOS Version"] = f"{smbios_major}.{smbios_minor}"

            # Boot device
            boot_dev = read_string(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control",
                "SystemBootDevice",
            )
            if boot_dev:
                info["Boot Device"] = boot_dev

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

    def refresh(self):
        """Refresh the data in the active sub-tab."""
        current = self._tab_widget.currentIndex()
        self._loaded_subtabs.discard(current)
        self._load_subtab_data(current)
