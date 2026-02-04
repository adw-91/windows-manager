"""Main entry point for Windows Manager"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer

from src.ui.main_window import MainWindow
from src.ui.theme import apply_dark_theme


def main():
    """Main application entry point"""
    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Windows Manager")
    app.setOrganizationName("Windows Manager")

    # Apply dark theme
    apply_dark_theme(app)

    window = MainWindow()

    # Prevent window from showing until ready
    # WA_DontShowOnScreen prevents the window from appearing on screen
    # even if show() is called, until we remove the attribute
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

    # Track if window has been shown
    shown = False

    def show_window():
        nonlocal shown
        if not shown:
            shown = True
            # Process pending events to ensure UI is fully rendered
            app.processEvents()
            # Remove the attribute that prevents showing
            window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
            window.show()
            # Activate and raise to bring to front
            window.activateWindow()
            window.raise_()

    # Show window when ready (critical content loaded)
    window.ready_to_show.connect(show_window)

    # Timeout fallback - show after 5s even if not fully ready
    QTimer.singleShot(5000, show_window)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
