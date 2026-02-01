"""Flow Layout - A layout that arranges widgets in rows, wrapping to new rows as needed."""

from PySide6.QtWidgets import QLayout, QWidgetItem, QSizePolicy
from PySide6.QtCore import Qt, QRect, QSize, QPoint


class FlowLayout(QLayout):
    """
    A layout that arranges child widgets horizontally, wrapping to new rows
    when there isn't enough horizontal space.

    This is ideal for key-value pairs that should flow naturally and reflow
    gracefully when the window is resized.
    """

    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 12, v_spacing: int = 8):
        """
        Initialize the flow layout.

        Args:
            parent: Parent widget
            margin: Margin around the layout
            h_spacing: Horizontal spacing between items
            v_spacing: Vertical spacing between rows
        """
        super().__init__(parent)
        self._item_list: list[QWidgetItem] = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing

        if margin >= 0:
            self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        """Clean up items when layout is deleted."""
        while self._item_list:
            self.takeAt(0)

    def addItem(self, item: QWidgetItem) -> None:
        """Add an item to the layout."""
        self._item_list.append(item)

    def horizontalSpacing(self) -> int:
        """Return the horizontal spacing between items."""
        return self._h_spacing

    def verticalSpacing(self) -> int:
        """Return the vertical spacing between rows."""
        return self._v_spacing

    def setHorizontalSpacing(self, spacing: int) -> None:
        """Set the horizontal spacing between items."""
        self._h_spacing = spacing

    def setVerticalSpacing(self, spacing: int) -> None:
        """Set the vertical spacing between rows."""
        self._v_spacing = spacing

    def count(self) -> int:
        """Return the number of items in the layout."""
        return len(self._item_list)

    def itemAt(self, index: int) -> QWidgetItem | None:
        """Return the item at the given index."""
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index: int) -> QWidgetItem | None:
        """Remove and return the item at the given index."""
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        """Return the expanding directions (horizontal only)."""
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        """Return True because height depends on width."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Calculate the height needed for the given width."""
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        """Set the geometry of the layout and arrange items."""
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        """Return the preferred size."""
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        """Return the minimum size needed by the layout."""
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())

        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """
        Arrange items in the given rectangle.

        Args:
            rect: The rectangle to arrange items in
            test_only: If True, just calculate height without moving widgets

        Returns:
            The height needed for the layout
        """
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())

        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._item_list:
            widget = item.widget()
            if widget is None:
                continue

            # Get the size hint for this item
            size_hint = item.sizeHint()
            item_width = size_hint.width()
            item_height = size_hint.height()

            # Check if we need to wrap to next line
            next_x = x + item_width
            if next_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + self._v_spacing
                next_x = x + item_width
                line_height = 0

            # Position the item
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), size_hint))

            x = next_x + self._h_spacing
            line_height = max(line_height, item_height)

        return y + line_height - rect.y() + margins.bottom()


class KeyValueWidget(QWidgetItem):
    """A widget that displays a key-value pair as a single unit."""
    pass
