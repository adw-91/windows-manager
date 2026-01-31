"""
Application theming and color palette.

Provides dark theme colors and palette configuration for the application.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


class Colors:
    """
    Color constants for the application theme.

    Based on a professional dark blue/grey palette.
    """

    # Background colors
    WINDOW = QColor(24, 28, 32)           # Main window background
    WINDOW_ALT = QColor(32, 36, 42)       # Alternate/elevated surfaces
    WIDGET = QColor(40, 44, 52)           # Widget backgrounds (inputs, cards)
    WIDGET_HOVER = QColor(50, 56, 66)     # Hovered widget state

    # Text colors
    TEXT_PRIMARY = QColor(220, 223, 228)  # Primary text
    TEXT_SECONDARY = QColor(140, 145, 155) # Secondary/muted text
    TEXT_DISABLED = QColor(90, 95, 105)   # Disabled text

    # Accent colors
    ACCENT = QColor(100, 149, 237)        # Cornflower blue - primary accent
    ACCENT_HOVER = QColor(120, 169, 255)  # Hovered accent
    ACCENT_PRESSED = QColor(80, 129, 217) # Pressed accent

    # Status colors
    SUCCESS = QColor(80, 200, 120)        # Green
    WARNING = QColor(255, 193, 7)         # Amber
    ERROR = QColor(244, 67, 54)           # Red
    INFO = QColor(33, 150, 243)           # Blue

    # Border colors
    BORDER = QColor(55, 60, 70)           # Default border
    BORDER_FOCUS = QColor(100, 149, 237)  # Focused element border

    # Progress/chart colors
    PROGRESS_BG = QColor(45, 50, 60)      # Progress bar background
    PROGRESS_FILL = QColor(100, 149, 237) # Progress bar fill

    # Table colors
    TABLE_HEADER = QColor(35, 40, 48)     # Table header background
    TABLE_ROW_ALT = QColor(28, 32, 38)    # Alternating row background


def create_dark_palette() -> QPalette:
    """
    Create a QPalette configured for dark theme.

    Returns:
        QPalette configured with dark theme colors.
    """
    palette = QPalette()

    # Window and base colors
    palette.setColor(QPalette.Window, Colors.WINDOW)
    palette.setColor(QPalette.WindowText, Colors.TEXT_PRIMARY)
    palette.setColor(QPalette.Base, Colors.WIDGET)
    palette.setColor(QPalette.AlternateBase, Colors.WINDOW_ALT)
    palette.setColor(QPalette.Text, Colors.TEXT_PRIMARY)
    palette.setColor(QPalette.BrightText, Qt.white)

    # Button colors
    palette.setColor(QPalette.Button, Colors.WIDGET)
    palette.setColor(QPalette.ButtonText, Colors.TEXT_PRIMARY)

    # Highlight colors
    palette.setColor(QPalette.Highlight, Colors.ACCENT)
    palette.setColor(QPalette.HighlightedText, Qt.white)

    # Disabled state
    palette.setColor(QPalette.Disabled, QPalette.WindowText, Colors.TEXT_DISABLED)
    palette.setColor(QPalette.Disabled, QPalette.Text, Colors.TEXT_DISABLED)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, Colors.TEXT_DISABLED)

    # Links
    palette.setColor(QPalette.Link, Colors.ACCENT)
    palette.setColor(QPalette.LinkVisited, Colors.ACCENT_PRESSED)

    # Tooltips
    palette.setColor(QPalette.ToolTipBase, Colors.WINDOW_ALT)
    palette.setColor(QPalette.ToolTipText, Colors.TEXT_PRIMARY)

    # Placeholder text
    palette.setColor(QPalette.PlaceholderText, Colors.TEXT_SECONDARY)

    return palette


def get_stylesheet() -> str:
    """
    Get additional stylesheet rules for components not covered by QPalette.

    Returns:
        CSS stylesheet string.
    """
    return f"""
        /* Scrollbars */
        QScrollBar:vertical {{
            background: {Colors.WINDOW.name()};
            width: 12px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {Colors.WIDGET_HOVER.name()};
            min-height: 30px;
            border-radius: 6px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {Colors.BORDER.name()};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: {Colors.WINDOW.name()};
            height: 12px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {Colors.WIDGET_HOVER.name()};
            min-width: 30px;
            border-radius: 6px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {Colors.BORDER.name()};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}

        /* Tab widget */
        QTabWidget::pane {{
            border: 1px solid {Colors.BORDER.name()};
            border-radius: 4px;
            margin-top: 4px;
        }}
        QTabBar {{
            margin-top: 8px;
        }}
        QTabBar::tab {{
            background: {Colors.WINDOW_ALT.name()};
            color: {Colors.TEXT_SECONDARY.name()};
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}
        QTabBar::tab:selected {{
            background: {Colors.WIDGET.name()};
            color: {Colors.TEXT_PRIMARY.name()};
        }}
        QTabBar::tab:hover:!selected {{
            background: {Colors.WIDGET_HOVER.name()};
        }}

        /* Progress bar */
        QProgressBar {{
            background: {Colors.PROGRESS_BG.name()};
            border: none;
            border-radius: 4px;
            text-align: center;
            color: {Colors.TEXT_PRIMARY.name()};
        }}
        QProgressBar::chunk {{
            background: {Colors.PROGRESS_FILL.name()};
            border-radius: 4px;
        }}

        /* Table/Tree views */
        QTableView, QTreeView, QListView {{
            background: {Colors.WIDGET.name()};
            alternate-background-color: {Colors.TABLE_ROW_ALT.name()};
            border: 1px solid {Colors.BORDER.name()};
            border-radius: 4px;
            gridline-color: {Colors.BORDER.name()};
        }}
        QHeaderView::section {{
            background: {Colors.TABLE_HEADER.name()};
            color: {Colors.TEXT_PRIMARY.name()};
            padding: 6px;
            border: none;
            border-right: 1px solid {Colors.BORDER.name()};
            border-bottom: 1px solid {Colors.BORDER.name()};
        }}

        /* Group box */
        QGroupBox {{
            border: 1px solid {Colors.BORDER.name()};
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            color: {Colors.TEXT_SECONDARY.name()};
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }}

        /* Menu */
        QMenu {{
            background: {Colors.WINDOW_ALT.name()};
            border: 1px solid {Colors.BORDER.name()};
            border-radius: 4px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 24px;
            border-radius: 2px;
        }}
        QMenu::item:selected {{
            background: {Colors.ACCENT.name()};
        }}
        QMenuBar {{
            background: {Colors.WINDOW.name()};
        }}
        QMenuBar::item:selected {{
            background: {Colors.WIDGET_HOVER.name()};
        }}

        /* Tooltips */
        QToolTip {{
            background: {Colors.WINDOW_ALT.name()};
            color: {Colors.TEXT_PRIMARY.name()};
            border: 1px solid {Colors.BORDER.name()};
            border-radius: 4px;
            padding: 4px 8px;
        }}
    """


def apply_dark_theme(app: QApplication) -> None:
    """
    Apply dark theme to the application.

    Args:
        app: The QApplication instance to style.
    """
    app.setStyle("Fusion")
    app.setPalette(create_dark_palette())
    app.setStyleSheet(get_stylesheet())
