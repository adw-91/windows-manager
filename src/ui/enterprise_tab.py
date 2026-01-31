"""Enterprise Tab - Domain, workgroup, AAD information"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Slot, QThreadPool
from PySide6.QtGui import QFont

from src.ui.widgets.collapsible_section import CollapsibleSection
from src.ui.theme import Colors
from src.services.enterprise_info import EnterpriseInfo
from src.utils.thread_utils import SingleRunWorker


class EnterpriseInfoWidget(QWidget):
    """Widget for displaying key-value information in a formatted layout"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._labels = {}

    def set_data(self, data: dict) -> None:
        """Set key-value data and display it"""
        # Clear existing labels
        for label in self._labels.values():
            self._layout.removeWidget(label)
            label.deleteLater()
        self._labels.clear()

        # Add new labels for each key-value pair
        for key, value in data.items():
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)

            # Key label (left-aligned, secondary text color)
            key_label = QLabel(f"{key}:")
            key_label.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY.name()}; font-weight: bold; min-width: 150px;"
            )
            row_layout.addWidget(key_label)

            # Value label (selectable, primary text color)
            value_label = QLabel(str(value))
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value_label.setWordWrap(True)
            value_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY.name()};")
            row_layout.addWidget(value_label)

            self._layout.addWidget(row_widget)
            self._labels[key] = value_label

    def add_loading_label(self) -> None:
        """Show loading indicator"""
        self._layout.addWidget(
            QLabel("Loading...")
        )

    def add_error_label(self, error_msg: str) -> None:
        """Show error message"""
        error_label = QLabel(f"Error: {error_msg}")
        error_label.setStyleSheet(f"color: {Colors.ERROR.name()};")
        self._layout.addWidget(error_label)

    def clear(self) -> None:
        """Clear all content"""
        for label in self._labels.values():
            self._layout.removeWidget(label)
            label.deleteLater()
        self._labels.clear()

        # Remove all children
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class EnterpriseTab(QWidget):
    """Tab for enterprise and domain information"""

    def __init__(self):
        super().__init__()
        self._enterprise_info = EnterpriseInfo()
        self._load_worker = None
        self._thread_pool = QThreadPool.globalInstance()

        # Store section widgets
        self._sections = {}
        self._info_widgets = {}

        self.init_ui()
        self._load_data()

    def init_ui(self):
        """Initialize the user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # === Header with Refresh button ===
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        title_label = QLabel("Enterprise Information")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_data)
        header_layout.addWidget(refresh_btn)

        main_layout.addLayout(header_layout)

        # === Scrollable content area ===
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        # === Domain Information Section ===
        domain_section = CollapsibleSection("Domain Information", expanded=True)
        domain_info = EnterpriseInfoWidget()
        domain_section.set_content(domain_info)
        self._sections["Domain"] = domain_section
        self._info_widgets["Domain"] = domain_info
        content_layout.addWidget(domain_section)

        # === Computer Information Section ===
        computer_section = CollapsibleSection("Computer Information", expanded=True)
        computer_info = EnterpriseInfoWidget()
        computer_section.set_content(computer_info)
        self._sections["Computer"] = computer_section
        self._info_widgets["Computer"] = computer_info
        content_layout.addWidget(computer_section)

        # === Current User Section ===
        user_section = CollapsibleSection("Current User", expanded=True)
        user_info = EnterpriseInfoWidget()
        user_section.set_content(user_info)
        self._sections["Current User"] = user_section
        self._info_widgets["Current User"] = user_info
        content_layout.addWidget(user_section)

        # === Network Section ===
        network_section = CollapsibleSection("Network", expanded=False)
        network_info = EnterpriseInfoWidget()
        network_section.set_content(network_info)
        self._sections["Network"] = network_section
        self._info_widgets["Network"] = network_info
        content_layout.addWidget(network_section)

        # === Azure AD Section ===
        azure_section = CollapsibleSection("Azure AD", expanded=False)
        azure_info = EnterpriseInfoWidget()
        azure_section.set_content(azure_info)
        self._sections["Azure AD"] = azure_section
        self._info_widgets["Azure AD"] = azure_info
        content_layout.addWidget(azure_section)

        # === Group Policy Section ===
        gpo_section = CollapsibleSection("Group Policy", expanded=False)
        gpo_info = EnterpriseInfoWidget()
        gpo_section.set_content(gpo_info)
        self._sections["Group Policy"] = gpo_section
        self._info_widgets["Group Policy"] = gpo_info
        content_layout.addWidget(gpo_section)

        content_layout.addStretch()

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def _load_data(self) -> None:
        """Load all enterprise information in background"""
        # Show loading state
        for widget in self._info_widgets.values():
            widget.clear()
            widget.add_loading_label()

        # Start background worker
        self._load_worker = SingleRunWorker(
            self._enterprise_info.get_all_enterprise_info
        )
        self._load_worker.signals.result.connect(self._on_data_loaded)
        self._load_worker.signals.error.connect(self._on_data_error)
        self._thread_pool.start(self._load_worker)

    @Slot(object)
    def _on_data_loaded(self, all_data: dict) -> None:
        """Handle loaded enterprise information"""
        try:
            # Populate each section with its data
            for section_name, info_data in all_data.items():
                if section_name in self._info_widgets:
                    widget = self._info_widgets[section_name]
                    widget.clear()

                    # Format the data based on section
                    formatted_data = self._format_section_data(section_name, info_data)
                    widget.set_data(formatted_data)
        except Exception as e:
            print(f"Error updating enterprise data: {e}")
            self._on_data_error(str(e))

    @Slot(str)
    def _on_data_error(self, error_msg: str) -> None:
        """Handle error loading data"""
        print(f"Error loading enterprise information: {error_msg}")
        for widget in self._info_widgets.values():
            widget.clear()
            widget.add_error_label(error_msg)

    def _format_section_data(self, section_name: str, data: dict) -> dict:
        """Format section data for display"""
        if section_name == "Domain":
            return {
                "Domain Name": data.get("domain_name", "Unknown"),
                "Domain Controller": data.get("domain_controller", "Unknown"),
                "Is Domain Joined": "Yes" if data.get("is_domain_joined", False) else "No",
            }
        elif section_name == "Computer":
            return {
                "Computer Name": data.get("computer_name", "Unknown"),
                "Workgroup/Domain": data.get("workgroup", "Unknown"),
                "Part of Domain": "Yes" if data.get("part_of_domain", False) else "No",
            }
        elif section_name == "Current User":
            is_admin = data.get("is_admin", False)
            return {
                "Username": data.get("username", "Unknown"),
                "Domain": data.get("user_domain", "Unknown"),
                "Full User": data.get("full_user", "Unknown"),
                "SID": data.get("sid", "Unknown"),
                "Administrator": "Yes" if is_admin else "No",
            }
        elif section_name == "Network":
            dns_servers = data.get("dns_servers", [])
            dns_str = ", ".join(dns_servers) if dns_servers else "None"
            return {
                "Primary IP": data.get("primary_ip", "Unknown"),
                "Adapter": data.get("adapter_name", "Unknown"),
                "DNS Servers": dns_str,
                "IPv6 Address": data.get("ipv6_address", "Unknown"),
            }
        elif section_name == "Azure AD":
            is_aad_joined = data.get("is_azure_ad_joined", False)
            return {
                "Azure AD Joined": "Yes" if is_aad_joined else "No",
                "Tenant ID": data.get("tenant_id", "Unknown"),
                "Tenant Name": data.get("tenant_name", "Unknown"),
                "Device ID": data.get("device_id", "Unknown"),
                "Device Name": data.get("device_name", "Unknown"),
            }
        elif section_name == "Group Policy":
            gpos_applied = data.get("gpos_applied", False)
            gpo_count = data.get("applied_gpo_count", 0)
            gpresult_available = data.get("gpresult_available", True)

            result = {
                "GPOs Applied": "Yes" if gpos_applied else "No",
                "Applied GPO Count": str(gpo_count),
                "Gpresult Available": "Yes" if gpresult_available else "No",
            }

            # Add policy lists if available
            computer_policies = data.get("computer_policies", [])
            user_policies = data.get("user_policies", [])

            if computer_policies:
                result["Computer Policies"] = ", ".join(computer_policies[:3])
                if len(computer_policies) > 3:
                    result["Computer Policies"] += f", +{len(computer_policies) - 3} more"

            if user_policies:
                result["User Policies"] = ", ".join(user_policies[:3])
                if len(user_policies) > 3:
                    result["User Policies"] += f", +{len(user_policies) - 3} more"

            return result

        # Default: return data as-is
        return {str(k): str(v) for k, v in data.items()}

    def refresh(self) -> None:
        """Refresh the data in this tab"""
        self._load_data()
