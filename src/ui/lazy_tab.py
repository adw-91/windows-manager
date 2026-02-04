"""Lazy tab initialization for deferred widget creation."""

from typing import Callable, Optional
from PySide6.QtWidgets import QWidget


class LazyTab:
    """
    Factory for deferred tab widget creation.

    Creates the tab widget only on first access, reducing startup time
    by deferring expensive initialization until the tab is actually viewed.

    Usage:
        lazy = LazyTab(lambda: ExpensiveTab())
        widget = lazy.get_widget()  # Creates widget on first call
        widget = lazy.get_widget()  # Returns cached widget
    """

    def __init__(self, factory: Callable[[], QWidget]) -> None:
        self._factory = factory
        self._widget: Optional[QWidget] = None

    def get_widget(self) -> QWidget:
        """Get the tab widget, creating it if necessary."""
        if self._widget is None:
            self._widget = self._factory()
        return self._widget

    @property
    def is_created(self) -> bool:
        """Check if the widget has been created."""
        return self._widget is not None

    def cleanup(self) -> None:
        """Clean up the widget if it exists."""
        if self._widget is not None and hasattr(self._widget, 'cleanup'):
            self._widget.cleanup()
