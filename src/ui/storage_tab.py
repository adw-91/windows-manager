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
from src.utils.thread_utils import CancellableWorker, SingleRunWorker
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

    _STYLE_NORMAL = f"""
        DriveTile {{
            background-color: {Colors.WIDGET.name()};
            border: 1px solid {Colors.BORDER.name()};
            border-radius: 8px;
        }}
        DriveTile:hover {{
            border-color: {Colors.ACCENT.name()};
            background-color: {Colors.WIDGET_HOVER.name()};
        }}
    """
    _STYLE_SELECTED = f"""
        DriveTile {{
            background-color: {Colors.WIDGET_HOVER.name()};
            border: 2px solid {Colors.ACCENT.name()};
            border-radius: 8px;
        }}
    """

    def __init__(self, drive: DriveInfo, parent=None):
        super().__init__(parent)
        self._drive = drive
        self._selected = False
        self._init_ui()

    def set_selected(self, selected: bool) -> None:
        """Toggle accent border to indicate selection."""
        self._selected = selected
        self.setStyleSheet(self._STYLE_SELECTED if selected else self._STYLE_NORMAL)

    def _init_ui(self):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(260)
        self.setFixedHeight(110)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(self._STYLE_NORMAL)

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
        self._listing_worker: Optional[SingleRunWorker] = None
        self._subdir_workers: List[SingleRunWorker] = []
        self._data_loaded = False
        self._drives: List[DriveInfo] = []
        self._current_drive: Optional[DriveInfo] = None
        self._selected_tile: Optional[DriveTile] = None

        # Two-phase scan state
        self._path_to_item: Dict[str, QTreeWidgetItem] = {}
        self._size_workers: List[CancellableWorker] = []
        self._pending_sizes: int = 0
        self._completed_sizes: int = 0

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

        # Compact progress/cancel bar
        progress_bar = QHBoxLayout()
        progress_bar.setSpacing(8)
        progress_bar.addStretch()

        self._scan_progress = QProgressBar()
        self._scan_progress.setRange(0, 100)
        self._scan_progress.setFixedWidth(120)
        self._scan_progress.setFixedHeight(16)
        self._scan_progress.setTextVisible(False)
        self._scan_progress.setVisible(False)
        progress_bar.addWidget(self._scan_progress)

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
        progress_bar.addWidget(self._cancel_btn)

        tree_layout.addLayout(progress_bar)

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

        # Loading overlay for tree (shown during Phase 1 listing)
        self._tree_loading = LoadingOverlay(self._tree)

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

    # ── Phase 1: Instant listing ──────────────────────────────────────

    def _on_drive_clicked(self, drive: DriveInfo) -> None:
        """Start two-phase scan of the selected drive's root directory."""
        self._current_drive = drive
        self._tree_panel.setVisible(True)
        self._tree.clear()
        self._path_to_item.clear()

        # Update selected tile visual state
        if self._selected_tile:
            self._selected_tile.set_selected(False)
        # Find the DriveTile for this drive
        for i in range(self._tiles_layout.count()):
            item = self._tiles_layout.itemAt(i)
            if item and isinstance(item.widget(), DriveTile) and item.widget()._drive is drive:
                self._selected_tile = item.widget()
                self._selected_tile.set_selected(True)
                break

        # Cancel any existing scan
        self._cancel_all_workers()

        # Show loading spinner on tree
        self._tree_loading.show_loading("Scanning...")

        root_path = f"{drive.letter}\\"

        # Phase 1: fast listing via SingleRunWorker (stored to prevent GC)
        worker = SingleRunWorker(self._storage_info.list_directory, root_path)
        worker.signals.result.connect(
            lambda entries: self._on_listing_complete(root_path, entries)
        )
        worker.signals.error.connect(self._on_scan_error)
        self._listing_worker = worker
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _on_listing_complete(self, root_path: str, entries: List[DirEntry]) -> None:
        """Phase 1 complete — populate tree with unsized dirs, then start Phase 2."""
        self._listing_worker = None
        self._tree_loading.hide_loading()
        self._tree.clear()
        self._path_to_item.clear()

        # Build tree items
        dir_paths: List[str] = []
        for entry in entries:
            item = QTreeWidgetItem()
            icon = "📁" if entry.is_dir else "📄"
            if not entry.is_accessible:
                icon = "🚫"
            item.setText(0, f"{icon}  {entry.name}")

            if entry.is_dir and entry.is_accessible:
                if entry.size_known:
                    item.setText(1, _format_size(entry.size_bytes))
                else:
                    item.setText(1, "Calculating...")
                    dir_paths.append(entry.path)
            else:
                item.setText(1, _format_size(entry.size_bytes))

            item.setText(2, "")  # Percentage filled in after Phase 2
            item.setText(3, str(entry.item_count) if entry.is_dir and entry.item_count else "")
            item.setData(0, Qt.ItemDataRole.UserRole, entry)

            # Add placeholder for lazy expansion of directories
            if entry.is_dir and entry.is_accessible:
                placeholder = QTreeWidgetItem()
                placeholder.setText(0, "Loading...")
                placeholder.setData(0, Qt.ItemDataRole.UserRole, _PLACEHOLDER)
                item.addChild(placeholder)

            self._tree.addTopLevelItem(item)
            self._path_to_item[entry.path] = item

        # Start Phase 2 if there are directories to size
        if dir_paths:
            self._start_size_calculations(dir_paths)

    def _on_scan_error(self, error_msg: str) -> None:
        """Handle error from Phase 1 listing."""
        self._listing_worker = None
        self._tree_loading.hide_loading()
        self._scan_progress.setVisible(False)
        self._cancel_btn.setVisible(False)

    # ── Phase 2: Progressive size calculation ─────────────────────────

    def _start_size_calculations(self, dir_paths: List[str]) -> None:
        """Launch one CancellableWorker per directory for size calculation."""
        self._pending_sizes = len(dir_paths)
        self._completed_sizes = 0

        self._scan_progress.setRange(0, self._pending_sizes)
        self._scan_progress.setValue(0)
        self._scan_progress.setVisible(True)
        self._cancel_btn.setVisible(True)

        for dir_path in dir_paths:
            worker = CancellableWorker(
                lambda w, p=dir_path: self._storage_info.calculate_entry_size(p, w)
            )
            worker.signals.result.connect(self._on_entry_size_calculated)
            worker.signals.error.connect(self._on_entry_size_error)
            self._size_workers.append(worker)
            QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _on_entry_size_calculated(self, result: tuple) -> None:
        """Update a single tree item's size in-place as Phase 2 results arrive."""
        path, size_bytes, item_count = result
        item = self._path_to_item.get(path)
        if item:
            item.setText(1, _format_size(size_bytes))
            item.setText(3, str(item_count) if item_count else "")
            # Update the stored DirEntry
            entry = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(entry, DirEntry):
                entry.size_bytes = size_bytes
                entry.item_count = item_count
                entry.size_known = True

        self._completed_sizes += 1
        self._scan_progress.setValue(self._completed_sizes)

        if self._completed_sizes >= self._pending_sizes:
            self._finalize_sizes()

    @Slot(str)
    def _on_entry_size_error(self, error_msg: str) -> None:
        """Handle error from a single size calculation worker."""
        self._completed_sizes += 1
        self._scan_progress.setValue(self._completed_sizes)

        if self._completed_sizes >= self._pending_sizes:
            self._finalize_sizes()

    def _finalize_sizes(self) -> None:
        """All Phase 2 workers done — calculate percentages and re-sort."""
        self._scan_progress.setVisible(False)
        self._cancel_btn.setVisible(False)
        self._size_workers.clear()

        # Collect all top-level entries with their sizes
        items_with_sizes = []
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            entry = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(entry, DirEntry):
                items_with_sizes.append((item, entry))

        # Calculate parent total for percentages
        parent_total = sum(e.size_bytes for _, e in items_with_sizes) or 1

        # Update percentages
        for item, entry in items_with_sizes:
            pct = entry.size_bytes / parent_total * 100 if parent_total > 0 else 0
            item.setText(2, f"{pct:.1f}%")
            item.setData(2, Qt.ItemDataRole.UserRole, pct / 100)

        # Re-sort by size descending: take all items, sort, re-insert
        self._tree.setSortingEnabled(False)
        all_items = []
        while self._tree.topLevelItemCount():
            all_items.append(self._tree.takeTopLevelItem(0))

        all_items.sort(
            key=lambda item: (item.data(0, Qt.ItemDataRole.UserRole).size_bytes
                              if isinstance(item.data(0, Qt.ItemDataRole.UserRole), DirEntry)
                              else 0),
            reverse=True,
        )

        for item in all_items:
            self._tree.addTopLevelItem(item)

    # ── Subdirectory expansion (two-phase) ────────────────────────────

    @Slot()
    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Handle tree item expansion — lazy scan child directory with two-phase approach."""
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

        # Phase 1: fast listing
        loading_item = QTreeWidgetItem()
        loading_item.setText(0, "⏳ Loading...")
        loading_item.setData(0, Qt.ItemDataRole.UserRole, _PLACEHOLDER)
        item.addChild(loading_item)

        worker = SingleRunWorker(self._storage_info.list_directory, entry.path)
        worker.signals.result.connect(
            lambda entries, parent=item: self._on_subdir_listing_complete(parent, entries)
        )
        worker.signals.error.connect(
            lambda err, parent=item: self._on_subdir_scan_error(parent, err)
        )
        self._subdir_workers.append(worker)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _on_subdir_listing_complete(
        self, parent_item: QTreeWidgetItem, entries: List[DirEntry]
    ) -> None:
        """Phase 1 of subdirectory expansion complete — populate children, start Phase 2."""
        # Remove the loading placeholder
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child and child.data(0, Qt.ItemDataRole.UserRole) == _PLACEHOLDER:
                parent_item.removeChild(child)
                break

        dir_paths: List[str] = []
        sub_path_to_item: Dict[str, QTreeWidgetItem] = {}

        for entry in entries:
            item = QTreeWidgetItem()
            icon = "📁" if entry.is_dir else "📄"
            if not entry.is_accessible:
                icon = "🚫"
            item.setText(0, f"{icon}  {entry.name}")

            if entry.is_dir and entry.is_accessible:
                if entry.size_known:
                    item.setText(1, _format_size(entry.size_bytes))
                else:
                    item.setText(1, "Calculating...")
                    dir_paths.append(entry.path)
                    sub_path_to_item[entry.path] = item
            else:
                item.setText(1, _format_size(entry.size_bytes))

            item.setText(2, "")
            item.setText(3, str(entry.item_count) if entry.is_dir and entry.item_count else "")
            item.setData(0, Qt.ItemDataRole.UserRole, entry)

            if entry.is_dir and entry.is_accessible:
                placeholder = QTreeWidgetItem()
                placeholder.setText(0, "Loading...")
                placeholder.setData(0, Qt.ItemDataRole.UserRole, _PLACEHOLDER)
                item.addChild(placeholder)

            parent_item.addChild(item)

        # Register in global path map for size updates
        self._path_to_item.update(sub_path_to_item)

        # Phase 2: size calculation for subdirectories
        if dir_paths:
            self._start_subtree_size_calculations(parent_item, dir_paths, sub_path_to_item)

    def _start_subtree_size_calculations(
        self,
        parent_item: QTreeWidgetItem,
        dir_paths: List[str],
        sub_path_to_item: Dict[str, QTreeWidgetItem],
    ) -> None:
        """Launch size workers for expanded subdirectory children."""
        pending = len(dir_paths)
        completed = [0]  # mutable for closure

        def on_subtree_size(result: tuple) -> None:
            path, size_bytes, item_count = result
            item = sub_path_to_item.get(path)
            if item:
                item.setText(1, _format_size(size_bytes))
                item.setText(3, str(item_count) if item_count else "")
                entry = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(entry, DirEntry):
                    entry.size_bytes = size_bytes
                    entry.item_count = item_count
                    entry.size_known = True

            completed[0] += 1
            if completed[0] >= pending:
                self._finalize_subtree_sizes(parent_item)

        def on_subtree_error(err: str) -> None:
            completed[0] += 1
            if completed[0] >= pending:
                self._finalize_subtree_sizes(parent_item)

        for dir_path in dir_paths:
            worker = CancellableWorker(
                lambda w, p=dir_path: self._storage_info.calculate_entry_size(p, w)
            )
            worker.signals.result.connect(on_subtree_size)
            worker.signals.error.connect(on_subtree_error)
            self._size_workers.append(worker)
            QThreadPool.globalInstance().start(worker)

    def _finalize_subtree_sizes(self, parent_item: QTreeWidgetItem) -> None:
        """Calculate percentages for a subtree after all sizes are known."""
        children = []
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            entry = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(entry, DirEntry):
                children.append((child, entry))

        parent_total = sum(e.size_bytes for _, e in children) or 1

        for child_item, entry in children:
            pct = entry.size_bytes / parent_total * 100 if parent_total > 0 else 0
            child_item.setText(2, f"{pct:.1f}%")
            child_item.setData(2, Qt.ItemDataRole.UserRole, pct / 100)

    @Slot()
    def _on_subdir_scan_error(
        self, parent_item: QTreeWidgetItem, error_msg: str
    ) -> None:
        """Handle error during subdirectory listing."""
        # Remove loading placeholder
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child and child.data(0, Qt.ItemDataRole.UserRole) == _PLACEHOLDER:
                parent_item.removeChild(child)
                break

        error_item = QTreeWidgetItem()
        error_item.setText(0, f"🚫  Error: {error_msg}")
        parent_item.addChild(error_item)

    # ── Cancellation ──────────────────────────────────────────────────

    def _cancel_scan(self) -> None:
        """Cancel all active scans."""
        self._cancel_all_workers()
        self._scan_progress.setVisible(False)
        self._cancel_btn.setVisible(False)

    def _cancel_all_workers(self) -> None:
        """Cancel all workers — Phase 1 listing, Phase 2 size, subdirectory listing."""
        if self._current_scan_worker:
            self._current_scan_worker.cancel()
            self._current_scan_worker = None

        # Phase 1 listing worker (SingleRunWorker — not cancellable, just release ref)
        self._listing_worker = None

        # Subdirectory listing workers
        self._subdir_workers.clear()

        for worker in self._size_workers:
            worker.cancel()
        self._size_workers.clear()
        self._pending_sizes = 0
        self._completed_sizes = 0

        self._tree_loading.hide_loading()

    # ── Context menu ──────────────────────────────────────────────────

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

    # ── Lifecycle ─────────────────────────────────────────────────────

    @Slot()
    def _on_refresh(self) -> None:
        self._cancel_all_workers()
        if self._selected_tile:
            self._selected_tile.set_selected(False)
            self._selected_tile = None
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
        self._cancel_all_workers()
