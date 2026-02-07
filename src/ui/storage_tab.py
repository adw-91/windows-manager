"""Storage Tab - Drive overview tiles with drill-down directory tree."""

import subprocess
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QSizePolicy, QProgressBar, QTreeWidget, QTreeWidgetItem,
    QMenu, QApplication,
)
from PySide6.QtCore import Qt, Slot, QThreadPool, QRect
from PySide6.QtGui import QAction, QPainter, QColor, QPen, QBrush

from src.services.storage_info import get_storage_info, DriveInfo, DirEntry
from src.services.data_cache import DataCache, CacheState
from src.utils.thread_utils import CancellableWorker
from src.ui.theme import Colors
from src.ui.widgets.flow_layout import FlowLayout
from src.ui.widgets.loading_indicator import LoadingOverlay


# Drive type icons
DRIVE_ICONS: Dict[int, str] = {
    2: "🔌",  # Removable
    3: "💾",  # Local
    4: "🌐",  # Network
    5: "💿",  # CD/DVD
    6: "💾",  # RAM Disk
}

# Placeholder marker for lazy expansion
_PLACEHOLDER = "__placeholder__"


def _format_size(size_bytes: int) -> str:
    """Format byte count to human-readable string."""
    if size_bytes < 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


class DriveTile(QFrame):
    """Clickable tile showing drive overview with progress bar."""

    def __init__(self, drive: DriveInfo, parent=None):
        super().__init__(parent)
        self._drive = drive
        self._init_ui()

    def _init_ui(self):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(260)
        self.setFixedHeight(110)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            DriveTile {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
            }}
            DriveTile:hover {{
                border-color: {Colors.ACCENT.name()};
                background-color: {Colors.WIDGET_HOVER.name()};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Top: icon + drive letter + label
        top = QHBoxLayout()
        top.setSpacing(8)

        icon = DRIVE_ICONS.get(self._drive.drive_type, "💾")
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 20px;")
        top.addWidget(icon_label)

        name_parts = [self._drive.letter]
        if self._drive.label:
            name_parts.append(f"({self._drive.label})")
        name_label = QLabel(" ".join(name_parts))
        name_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};")
        top.addWidget(name_label)

        if self._drive.filesystem:
            fs_label = QLabel(self._drive.filesystem)
            fs_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px;")
            top.addWidget(fs_label)

        top.addStretch()
        layout.addLayout(top)

        # Size info
        used = _format_size(self._drive.used_bytes)
        total = _format_size(self._drive.total_bytes)
        free = _format_size(self._drive.free_bytes)
        size_label = QLabel(f"{used} / {total}  ({free} free)")
        size_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px;")
        layout.addWidget(size_label)

        # Progress bar with RAG color
        pbar = QProgressBar()
        pbar.setRange(0, 100)
        pbar.setValue(int(self._drive.percent))
        pbar.setFixedHeight(10)
        pbar.setTextVisible(False)

        if self._drive.percent < 70:
            chunk_color = Colors.SUCCESS.name()
        elif self._drive.percent < 90:
            chunk_color = Colors.WARNING.name()
        else:
            chunk_color = Colors.ERROR.name()

        pbar.setStyleSheet(f"""
            QProgressBar {{
                background: {Colors.PROGRESS_BG.name()};
                border: none;
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background: {chunk_color};
                border-radius: 5px;
            }}
        """)
        layout.addWidget(pbar)

        # Percent label
        pct_label = QLabel(f"{self._drive.percent:.0f}% used")
        pct_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()}; font-size: 11px;")
        pct_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(pct_label)

    def mousePressEvent(self, event):
        """Emit click by finding parent StorageTab and calling its method."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Walk up to find StorageTab
            parent = self.parent()
            while parent and not isinstance(parent, StorageTab):
                parent = parent.parent()
            if parent:
                parent._on_drive_clicked(self._drive)
        super().mousePressEvent(event)


class SizeBarDelegate:
    """Mixin/helper to paint inline size bars in the tree Size column."""

    @staticmethod
    def paint_size_bar(painter: QPainter, rect: QRect, pct: float, text: str):
        """Paint a size bar with text overlay."""
        # Background
        painter.fillRect(rect, QColor(Colors.WIDGET.name()))

        # Bar
        if pct > 0:
            bar_rect = QRect(rect.x() + 2, rect.y() + 2, int((rect.width() - 4) * pct), rect.height() - 4)
            bar_color = QColor(Colors.ACCENT.name())
            bar_color.setAlpha(100)
            painter.fillRect(bar_rect, bar_color)

        # Text
        painter.setPen(QPen(QColor(Colors.TEXT_PRIMARY.name())))
        painter.drawText(rect.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, text)


class StorageTab(QWidget):
    """Tab for storage overview and directory size analysis."""

    def __init__(self):
        super().__init__()
        self._storage_info = get_storage_info()
        self._drive_cache = DataCache(self._storage_info.get_drive_info, fallback_value=[])
        self._current_scan_worker: Optional[CancellableWorker] = None
        self._data_loaded = False
        self._drives: List[DriveInfo] = []
        self._current_drive: Optional[DriveInfo] = None
        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel("Storage")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 6px 16px;
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
                background: {Colors.WIDGET.name()};
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QPushButton:hover {{ background: {Colors.WIDGET_HOVER.name()}; }}
        """)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        # Drive tiles panel
        self._tiles_frame = QFrame()
        self._tiles_frame.setStyleSheet("background: transparent;")
        self._tiles_layout = FlowLayout(self._tiles_frame, margin=0, h_spacing=12, v_spacing=12)
        layout.addWidget(self._tiles_frame)

        # Loading overlay for tiles
        self._tiles_loading = LoadingOverlay(self._tiles_frame)

        # Tree panel (initially hidden)
        self._tree_panel = QFrame()
        self._tree_panel.setVisible(False)
        tree_layout = QVBoxLayout(self._tree_panel)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(6)

        # Tree header bar
        tree_header = QHBoxLayout()
        tree_header.setSpacing(8)

        self._tree_path_label = QLabel("")
        self._tree_path_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};")
        tree_header.addWidget(self._tree_path_label)
        tree_header.addStretch()

        self._scan_progress = QProgressBar()
        self._scan_progress.setRange(0, 100)
        self._scan_progress.setFixedWidth(120)
        self._scan_progress.setFixedHeight(16)
        self._scan_progress.setTextVisible(False)
        self._scan_progress.setVisible(False)
        tree_header.addWidget(self._scan_progress)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._cancel_scan)
        self._cancel_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 4px 12px;
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 3px;
                background: {Colors.WIDGET.name()};
                color: {Colors.TEXT_PRIMARY.name()};
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {Colors.WIDGET_HOVER.name()}; }}
        """)
        tree_header.addWidget(self._cancel_btn)

        tree_layout.addLayout(tree_header)

        # Directory tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Size", "% of Parent", "Items"])
        self._tree.setColumnCount(4)
        self._tree.setColumnWidth(0, 300)
        self._tree.setColumnWidth(1, 120)
        self._tree.setColumnWidth(2, 100)
        self._tree.setColumnWidth(3, 80)
        self._tree.setSortingEnabled(False)  # We handle sort order ourselves
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
                color: {Colors.TEXT_PRIMARY.name()};
            }}
            QTreeWidget::item {{ padding: 2px 0; }}
            QTreeWidget::item:selected {{
                background-color: {Colors.ACCENT.name()};
                color: white;
            }}
            QHeaderView::section {{
                background-color: {Colors.TABLE_HEADER.name()};
                border: 1px solid {Colors.BORDER.name()};
                padding: 4px;
                font-weight: bold;
                color: {Colors.TEXT_PRIMARY.name()};
            }}
        """)
        tree_layout.addWidget(self._tree)

        layout.addWidget(self._tree_panel)

    def _connect_signals(self) -> None:
        self._drive_cache.state_changed.connect(self._on_cache_state)
        self._drive_cache.data_loaded.connect(self._on_drives_loaded)
        self._drive_cache.error_occurred.connect(self._on_cache_error)

    @Slot(CacheState)
    def _on_cache_state(self, state: CacheState) -> None:
        if state == CacheState.LOADING:
            self._tiles_loading.show_loading("Loading drives...")
        elif state in (CacheState.LOADED, CacheState.ERROR):
            self._tiles_loading.hide_loading()

    @Slot(object)
    def _on_drives_loaded(self, drives: List[DriveInfo]) -> None:
        self._drives = drives
        self._populate_tiles()

    @Slot(str)
    def _on_cache_error(self, error_msg: str) -> None:
        pass  # Tiles stay empty

    def _populate_tiles(self) -> None:
        """Rebuild drive tile widgets."""
        # Clear existing tiles
        while self._tiles_layout.count():
            item = self._tiles_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for drive in self._drives:
            tile = DriveTile(drive)
            self._tiles_layout.addWidget(tile)

        self._tiles_frame.updateGeometry()

    def _on_drive_clicked(self, drive: DriveInfo) -> None:
        """Start scanning the selected drive's root directory."""
        self._current_drive = drive
        self._tree_panel.setVisible(True)
        self._tree_path_label.setText(f"{drive.letter}\\ — Scanning...")
        self._tree.clear()

        # Cancel any existing scan
        self._cancel_current_scan()

        # Start new scan
        self._scan_progress.setVisible(True)
        self._scan_progress.setValue(0)
        self._cancel_btn.setVisible(True)

        root_path = f"{drive.letter}\\"
        self._current_scan_worker = CancellableWorker(
            lambda w: self._storage_info.scan_directory(root_path, w)
        )
        self._current_scan_worker.signals.result.connect(
            lambda entries: self._on_scan_complete(root_path, entries)
        )
        self._current_scan_worker.signals.progress.connect(self._scan_progress.setValue)
        self._current_scan_worker.signals.error.connect(self._on_scan_error)
        QThreadPool.globalInstance().start(self._current_scan_worker)

    @Slot(object)
    def _on_scan_complete(self, root_path: str, entries: List[DirEntry]) -> None:
        """Populate tree with scan results."""
        self._scan_progress.setVisible(False)
        self._cancel_btn.setVisible(False)
        self._current_scan_worker = None

        if self._current_drive:
            self._tree_path_label.setText(f"{self._current_drive.letter}\\")

        # Calculate parent total for percentage
        parent_total = sum(e.size_bytes for e in entries) or 1

        self._tree.clear()
        for entry in entries:
            item = QTreeWidgetItem()
            icon = "📁" if entry.is_dir else "📄"
            if not entry.is_accessible:
                icon = "🚫"
            item.setText(0, f"{icon}  {entry.name}")
            item.setText(1, _format_size(entry.size_bytes))
            pct = entry.size_bytes / parent_total * 100 if parent_total > 0 else 0
            item.setText(2, f"{pct:.1f}%")
            item.setData(2, Qt.ItemDataRole.UserRole, pct / 100)  # For potential bar rendering
            item.setText(3, str(entry.item_count) if entry.is_dir else "")
            item.setData(0, Qt.ItemDataRole.UserRole, entry)

            # Add placeholder for lazy expansion of directories
            if entry.is_dir and entry.is_accessible:
                placeholder = QTreeWidgetItem()
                placeholder.setText(0, "Loading...")
                placeholder.setData(0, Qt.ItemDataRole.UserRole, _PLACEHOLDER)
                item.addChild(placeholder)

            self._tree.addTopLevelItem(item)

    @Slot(str)
    def _on_scan_error(self, error_msg: str) -> None:
        self._scan_progress.setVisible(False)
        self._cancel_btn.setVisible(False)
        self._current_scan_worker = None
        self._tree_path_label.setText(f"Error: {error_msg}")

    @Slot()
    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Handle tree item expansion — lazy scan child directory."""
        if item.childCount() != 1:
            return
        child = item.child(0)
        if child.data(0, Qt.ItemDataRole.UserRole) != _PLACEHOLDER:
            return

        # Remove placeholder
        item.removeChild(child)

        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(entry, DirEntry) or not entry.is_dir:
            return

        # Launch scan for this directory
        loading_item = QTreeWidgetItem()
        loading_item.setText(0, "⏳ Scanning...")
        loading_item.setData(0, Qt.ItemDataRole.UserRole, _PLACEHOLDER)
        item.addChild(loading_item)

        worker = CancellableWorker(
            lambda w: self._storage_info.scan_directory(entry.path, w)
        )
        worker.signals.result.connect(
            lambda entries, parent=item: self._on_subdir_scan_complete(parent, entries)
        )
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _on_subdir_scan_complete(self, parent_item: QTreeWidgetItem, entries: List[DirEntry]) -> None:
        """Populate children after sub-directory scan."""
        # Remove the scanning placeholder
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child and child.data(0, Qt.ItemDataRole.UserRole) == _PLACEHOLDER:
                parent_item.removeChild(child)
                break

        parent_total = sum(e.size_bytes for e in entries) or 1

        for entry in entries:
            item = QTreeWidgetItem()
            icon = "📁" if entry.is_dir else "📄"
            if not entry.is_accessible:
                icon = "🚫"
            item.setText(0, f"{icon}  {entry.name}")
            item.setText(1, _format_size(entry.size_bytes))
            pct = entry.size_bytes / parent_total * 100 if parent_total > 0 else 0
            item.setText(2, f"{pct:.1f}%")
            item.setData(2, Qt.ItemDataRole.UserRole, pct / 100)
            item.setText(3, str(entry.item_count) if entry.is_dir else "")
            item.setData(0, Qt.ItemDataRole.UserRole, entry)

            if entry.is_dir and entry.is_accessible:
                placeholder = QTreeWidgetItem()
                placeholder.setText(0, "Loading...")
                placeholder.setData(0, Qt.ItemDataRole.UserRole, _PLACEHOLDER)
                item.addChild(placeholder)

            parent_item.addChild(item)

    def _cancel_scan(self) -> None:
        """Cancel the current root scan."""
        self._cancel_current_scan()
        self._scan_progress.setVisible(False)
        self._cancel_btn.setVisible(False)
        if self._current_drive:
            self._tree_path_label.setText(f"{self._current_drive.letter}\\ — Cancelled")

    def _cancel_current_scan(self) -> None:
        """Cancel active scan worker if any."""
        if self._current_scan_worker:
            self._current_scan_worker.cancel()
            self._current_scan_worker = None

    @Slot()
    def _show_tree_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if not item:
            return
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(entry, DirEntry):
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Colors.WINDOW_ALT.name()};
                color: {Colors.TEXT_PRIMARY.name()};
                border: 1px solid {Colors.BORDER.name()};
            }}
            QMenu::item {{ padding: 6px 20px; }}
            QMenu::item:selected {{ background-color: {Colors.ACCENT.name()}; }}
        """)

        open_action = QAction("Open in Explorer", self)
        open_action.triggered.connect(
            lambda: subprocess.Popen(["explorer", "/select,", entry.path])
        )
        menu.addAction(open_action)

        copy_path = QAction("Copy Path", self)
        copy_path.triggered.connect(
            lambda: QApplication.clipboard().setText(entry.path)
        )
        menu.addAction(copy_path)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    @Slot()
    def _on_refresh(self) -> None:
        self._cancel_current_scan()
        self._tree_panel.setVisible(False)
        self._drive_cache.refresh()

    def on_tab_activated(self) -> None:
        """Called when this tab becomes visible. Loads data on first activation."""
        if not self._data_loaded:
            self._data_loaded = True
            self._drive_cache.load()

    def refresh(self):
        """Refresh the data in this tab."""
        self._on_refresh()

    def cleanup(self) -> None:
        """Cancel any running scans on close."""
        self._cancel_current_scan()
