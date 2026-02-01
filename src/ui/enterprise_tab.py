"""Enterprise Tab - Modern card-based domain, workgroup, AAD information."""

from typing import Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, QThreadPool

from src.ui.theme import Colors
from src.services.enterprise_info import EnterpriseInfo
from src.utils.thread_utils import SingleRunWorker
from src.ui.widgets.flow_layout import FlowLayout


class KeyValuePair(QWidget):
    """A widget that displays a key-value pair as a single unit for flow layouts."""

    # Keys that should show RAG coloring for Yes/No values
    RAG_KEYS = {"Administrator", "Domain Joined", "Entra ID Joined", "GPOs Applied"}

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

        # Value label with conditional RAG coloring
        self._value_label = QLabel(str(self._value))
        style = f"color: {Colors.TEXT_PRIMARY.name()}; font-size: 11px;"

        # Apply RAG coloring for specific keys
        if self._key in self.RAG_KEYS:
            if self._value == "Yes":
                style = f"color: {Colors.SUCCESS.name()}; font-size: 11px; font-weight: bold;"
            elif self._value == "No":
                style = f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px;"

        self._value_label.setStyleSheet(style)
        self._value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._value_label)

        # Set size policy so this widget doesn't stretch excessively
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_value(self, value: str):
        """Update the value."""
        self._value = value
        if self._value_label:
            self._value_label.setText(str(value))


class EnterpriseCard(QFrame):
    """A modern card widget for displaying enterprise information with flow layout."""

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
            EnterpriseCard {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
            }}
            EnterpriseCard:hover {{
                border-color: {Colors.ACCENT.name()};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header with icon and title
        header = QHBoxLayout()
        header.setSpacing(8)

        if self._icon:
            icon_label = QLabel(self._icon)
            icon_label.setStyleSheet(f"font-size: 18px; color: {Colors.ACCENT.name()};")
            header.addWidget(icon_label)

        title_label = QLabel(self._title)
        title_label.setStyleSheet(f"""
            font-size: 13px;
            font-weight: bold;
            color: {Colors.ACCENT.name()};
            letter-spacing: 0.5px;
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

    def set_loading(self):
        """Show loading state."""
        while self._flow_layout.count():
            item = self._flow_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._kv_widgets.clear()

        loading = QLabel("Loading...")
        loading.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-style: italic;")
        self._flow_layout.addWidget(loading)

    def set_error(self, msg: str):
        """Show error state."""
        while self._flow_layout.count():
            item = self._flow_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._kv_widgets.clear()

        error = QLabel(f"Error: {msg}")
        error.setStyleSheet(f"color: {Colors.ERROR.name()};")
        self._flow_layout.addWidget(error)


class EnterpriseTab(QWidget):
    """Tab for enterprise and domain information with modern card-based UI."""

    def __init__(self):
        super().__init__()
        self._enterprise_info = EnterpriseInfo()
        self._load_worker = None
        self._cards: Dict[str, EnterpriseCard] = {}
        self._loading_label = None
        self.init_ui()
        self._load_data()

    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Compact header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        title = QLabel("Enterprise")
        title.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {Colors.TEXT_PRIMARY.name()};
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_data)
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
        self._loading_label = QLabel("Loading enterprise information...")
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
        self._card_layout.setSpacing(12)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_container.setVisible(False)

        # Create cards - order: Current User / Entra ID / Domain / Group Policy
        # Removed Network, merged Domain+Computer into Domain
        card_configs = [
            ("Current User", "👤"),
            ("Entra ID", "☁️"),
            ("Domain", "🏛️"),
            ("Group Policy", "📜"),
        ]

        for name, icon in card_configs:
            card = EnterpriseCard(name, icon)
            self._cards[name] = card
            self._card_layout.addWidget(card)

        content_layout.addWidget(self._card_container)
        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _load_data(self) -> None:
        """Load all enterprise information in background."""
        self._loading_label.setVisible(True)
        self._card_container.setVisible(False)

        for card in self._cards.values():
            card.set_loading()

        self._load_worker = SingleRunWorker(
            self._enterprise_info.get_all_enterprise_info
        )
        self._load_worker.signals.result.connect(self._on_data_loaded)
        self._load_worker.signals.error.connect(self._on_data_error)
        QThreadPool.globalInstance().start(self._load_worker)

    @Slot(object)
    def _on_data_loaded(self, all_data: dict) -> None:
        """Handle loaded enterprise information."""
        try:
            # Map old section names to new card names and format data
            card_data_map = {
                "Current User": self._format_current_user(all_data.get("Current User", {})),
                "Entra ID": self._format_entra_id(all_data.get("Azure AD", {})),
                "Domain": self._format_domain(
                    all_data.get("Domain", {}),
                    all_data.get("Computer", {})
                ),
                "Group Policy": self._format_group_policy(all_data.get("Group Policy", {})),
            }

            for card_name, formatted_data in card_data_map.items():
                if card_name in self._cards:
                    self._cards[card_name].set_data(formatted_data)

            self._loading_label.setVisible(False)
            self._card_container.setVisible(True)
        except Exception as e:
            self._on_data_error(str(e))

    @Slot(str)
    def _on_data_error(self, error_msg: str) -> None:
        """Handle error loading data."""
        self._loading_label.setText(f"Error: {error_msg}")
        self._loading_label.setStyleSheet(f"color: {Colors.ERROR.name()};")

    def _format_current_user(self, data: dict) -> dict:
        """Format current user data."""
        return {
            "Username": data.get("username", "N/A"),
            "Domain": data.get("user_domain", "N/A"),
            "Full Name": data.get("full_user", "N/A"),
            "SID": data.get("sid", "N/A"),
            "Administrator": "Yes" if data.get("is_admin", False) else "No",
        }

    def _format_entra_id(self, data: dict) -> dict:
        """Format Entra ID (Azure AD) data."""
        return {
            "Entra ID Joined": "Yes" if data.get("is_azure_ad_joined", False) else "No",
            "Tenant ID": data.get("tenant_id", "N/A"),
            "Tenant Name": data.get("tenant_name", "N/A"),
            "Device ID": data.get("device_id", "N/A"),
        }

    def _format_domain(self, domain_data: dict, computer_data: dict) -> dict:
        """Format merged domain and computer data."""
        is_domain_joined = domain_data.get("is_domain_joined", False) or computer_data.get("part_of_domain", False)
        return {
            "Computer Name": computer_data.get("computer_name", "N/A"),
            "Domain/Workgroup": computer_data.get("workgroup", "N/A") or domain_data.get("domain_name", "N/A"),
            "Domain Joined": "Yes" if is_domain_joined else "No",
            "Domain Controller": domain_data.get("domain_controller", "N/A"),
        }

    def _format_group_policy(self, data: dict) -> dict:
        """Format group policy data."""
        gpos = data.get("gpos_applied", False)
        result = {
            "GPOs Applied": "Yes" if gpos else "No",
            "Applied Count": str(data.get("applied_gpo_count", 0)),
        }

        comp_policies = data.get("computer_policies", [])
        user_policies = data.get("user_policies", [])

        if comp_policies:
            display = ", ".join(comp_policies[:2])
            if len(comp_policies) > 2:
                display += f" (+{len(comp_policies) - 2})"
            result["Computer GPOs"] = display

        if user_policies:
            display = ", ".join(user_policies[:2])
            if len(user_policies) > 2:
                display += f" (+{len(user_policies) - 2})"
            result["User GPOs"] = display

        return result

    def refresh(self) -> None:
        """Refresh the data in this tab."""
        self._load_data()
