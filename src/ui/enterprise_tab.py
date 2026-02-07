"""Enterprise Tab - Modern card-based domain, workgroup, AAD information."""

from typing import Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QPushButton, QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Slot, QThreadPool

from src.ui.theme import Colors
from src.services.enterprise_info import EnterpriseInfo
from src.utils.thread_utils import SingleRunWorker

# Keys that should show RAG coloring for Yes/No values
_RAG_KEYS = {"Administrator", "Domain Joined", "Entra ID Joined", "GPOs Applied"}


class EnterpriseCard(QFrame):
    """A card section displaying enterprise information as a key-value grid."""

    def __init__(self, title: str, icon: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._icon = icon
        self._grid: QGridLayout = None
        self._row_count = 0
        self._init_ui()

    def _init_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            EnterpriseCard {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with icon and title
        title_text = f"{self._icon}  {self._title}" if self._icon else self._title
        title_label = QLabel(title_text)
        title_label.setStyleSheet(f"""
            font-size: 13px;
            font-weight: bold;
            color: {Colors.ACCENT.name()};
            padding: 10px 12px 6px 12px;
            background: transparent;
        """)
        layout.addWidget(title_label)

        # Separator line
        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet(
            f"background-color: {Colors.BORDER.name()}; margin: 0 8px;"
        )
        layout.addWidget(separator)

        # Grid for key-value rows
        self._grid = QGridLayout()
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setHorizontalSpacing(0)
        self._grid.setVerticalSpacing(0)
        self._grid.setColumnMinimumWidth(0, 160)
        layout.addLayout(self._grid)
        layout.addStretch()

    def _clear_grid(self) -> None:
        """Remove all widgets from the grid."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._row_count = 0

    def set_data(self, data: Dict[str, str]) -> None:
        """Replace all rows with new data."""
        self._clear_grid()

        for key, value in data.items():
            if key == "Error":
                continue
            self._add_row(key, str(value))

    def _add_row(self, key: str, value: str) -> None:
        """Add a key-value row with alternating background and RAG coloring."""
        row_bg = (
            f"background-color: {Colors.WINDOW_ALT.name()};"
            if self._row_count % 2 == 0
            else "background: transparent;"
        )

        key_label = QLabel(f"{key}:")
        key_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 12px; "
            f"padding: 6px 8px; {row_bg}"
        )
        key_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        key_label.setMinimumWidth(160)

        # Value style with RAG coloring for specific keys
        value_style = (
            f"color: {Colors.TEXT_PRIMARY.name()}; font-size: 12px; "
            f"font-weight: 500; padding: 6px 8px; {row_bg}"
        )
        if key in _RAG_KEYS:
            if value == "Yes":
                value_style = (
                    f"color: {Colors.SUCCESS.name()}; font-size: 12px; "
                    f"font-weight: bold; padding: 6px 8px; {row_bg}"
                )
            elif value == "No":
                value_style = (
                    f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 12px; "
                    f"padding: 6px 8px; {row_bg}"
                )

        value_label = QLabel(value)
        value_label.setStyleSheet(value_style)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setWordWrap(True)

        self._grid.addWidget(key_label, self._row_count, 0)
        self._grid.addWidget(value_label, self._row_count, 1)
        self._row_count += 1

    def set_loading(self) -> None:
        """Show loading state."""
        self._clear_grid()
        loading = QLabel("Loading...")
        loading.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY.name()}; font-style: italic; padding: 6px 8px;"
        )
        self._grid.addWidget(loading, 0, 0, 1, 2)

    def set_error(self, msg: str) -> None:
        """Show error state."""
        self._clear_grid()
        error = QLabel(f"Error: {msg}")
        error.setStyleSheet(f"color: {Colors.ERROR.name()}; padding: 6px 8px;")
        self._grid.addWidget(error, 0, 0, 1, 2)


class EnterpriseTab(QWidget):
    """Tab for enterprise and domain information with modern card-based UI."""

    def __init__(self):
        super().__init__()
        self._enterprise_info = EnterpriseInfo()
        self._load_worker = None
        self._cards: Dict[str, EnterpriseCard] = {}
        self._loading_label = None
        self._data_loaded = False  # Track if data has been loaded
        self.init_ui()
        # Don't load data here - will be loaded on first tab activation (lazy loading)

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

        # Single compound card containing all sections
        self._card_container = QFrame()
        self._card_container.setObjectName("enterprise_card")
        self._card_container.setStyleSheet(f"""
            #enterprise_card {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
            }}
        """)
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setSpacing(0)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_container.setVisible(False)

        borderless = "EnterpriseCard { background: transparent; border: none; border-radius: 0; }"

        # Create cards - order: Current User / Entra ID / Domain / Group Policy
        card_configs = [
            ("Current User", "👤"),
            ("Entra ID", "☁️"),
            ("Domain", "🏛️"),
            ("Group Policy", "📜"),
        ]

        for name, icon in card_configs:
            card = EnterpriseCard(name, icon)
            card.setStyleSheet(borderless)
            self._cards[name] = card
            self._card_layout.addWidget(card)

        self._card_layout.addStretch()

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

    def on_tab_activated(self) -> None:
        """Called when this tab becomes visible. Loads data on first activation."""
        if not self._data_loaded:
            self._data_loaded = True
            self._load_data()

    def refresh(self) -> None:
        """Refresh the data in this tab."""
        self._load_data()
