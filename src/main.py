"""Main entry point for Windows Manager"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

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
    window.show()

    # Prewarm caches in background after window is displayed
    window.prewarm_caches()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
