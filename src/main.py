"""Main entry point for Windows Manager"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor

from src.ui.main_window import MainWindow
from src.ui.theme import apply_dark_theme, Colors


def main():
    """Main application entry point"""
    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Windows Manager")
    app.setOrganizationName("Windows Manager")

    # Apply dark theme BEFORE creating window
    apply_dark_theme(app)

    # Set application-wide dark background to prevent white flash
    palette = app.palette()
    dark_color = QColor(Colors.WINDOW.name())
    palette.setColor(QPalette.ColorRole.Window, dark_color)
    palette.setColor(QPalette.ColorRole.Base, dark_color)
    app.setPalette(palette)

    window = MainWindow()

    # Ensure window background is dark before showing
    window.setAutoFillBackground(True)

    # Show window immediately - dark theme prevents white flash
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
