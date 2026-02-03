"""
AssetTreeView - QTreeView subclass for displaying asset families

Pattern: Custom view with card-style delegate rendering
Shows base assets as parents with variant assets as indented children.
"""

from typing import List, Optional
from PyQt6.QtWidgets import QTreeView, QAbstractItemView
from PyQt6.QtCore import Qt, QModelIndex, pyqtSignal, QPoint, QItemSelectionModel

from ..config import Config
from ..events.event_bus import get_event_bus
from ..models.asset_tree_model import TREE_UUID_ROLE, TREE_ASSET_ROLE
from .asset_tree_delegate import AssetTreeDelegate


class AssetTreeView(QTreeView):
    """
    Tree view for displaying asset families (base + variants).

    Features:
    - Base assets as expandable parent rows
    - Variants as indented child rows
    - Card-style delegate rendering
    - Single-column (no headers)
    - Auto-expand all on load
    - Context menu, double-click, selection signals

    Signals:
        asset_selected(str): UUID of selected asset
        asset_double_clicked(str): UUID of double-clicked asset
        context_menu_requested(str, QPoint): UUID and position for context menu
    """

    asset_selected = pyqtSignal(str)
    asset_double_clicked = pyqtSignal(str)
    context_menu_requested = pyqtSignal(str, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._event_bus = get_event_bus()

        self._setup_view()
        self._connect_signals()

    def _setup_view(self):
        """Configure tree view settings."""
        # Delegate
        self._delegate = AssetTreeDelegate(parent=self)
        self.setItemDelegate(self._delegate)

        # Single column, no header
        self.setHeaderHidden(True)

        # Indentation
        self.setIndentation(Config.TREE_INDENT)

        # Expander arrows on parents
        self.setRootIsDecorated(True)
        self.setItemsExpandable(True)
        self.setAnimated(True)

        # Selection
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # Scrolling
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # No column resizing (single column fills width)
        self.setExpandsOnDoubleClick(False)  # We handle double-click ourselves

    def _connect_signals(self):
        """Connect internal signals."""
        self.doubleClicked.connect(self._on_double_clicked)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.clicked.connect(self._on_clicked)

    def setModel(self, model):
        """Override to connect selection signals and expand all."""
        super().setModel(model)
        if self.selectionModel():
            self.selectionModel().selectionChanged.connect(self._on_selection_changed)
        # Expand all families by default
        self.expandAll()

    def refresh_expansion(self):
        """Re-expand all items (call after model rebuild)."""
        self.expandAll()

    def get_selected_uuid(self) -> Optional[str]:
        """Get the UUID of the currently selected asset."""
        indexes = self.selectedIndexes()
        if indexes:
            return indexes[0].data(TREE_UUID_ROLE)
        return None

    def select_asset(self, uuid: str):
        """Select an asset by UUID."""
        model = self.model()
        if not model:
            return

        # Search top-level items
        for row in range(model.rowCount()):
            parent_index = model.index(row, 0)
            if parent_index.data(TREE_UUID_ROLE) == uuid:
                self.selectionModel().select(
                    parent_index,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                )
                self.scrollTo(parent_index)
                return

            # Search children
            child_count = model.rowCount(parent_index)
            for child_row in range(child_count):
                child_index = model.index(child_row, 0, parent_index)
                if child_index.data(TREE_UUID_ROLE) == uuid:
                    # Expand parent first
                    self.expand(parent_index)
                    self.selectionModel().select(
                        child_index,
                        QItemSelectionModel.SelectionFlag.ClearAndSelect
                    )
                    self.scrollTo(child_index)
                    return

    def _on_clicked(self, index: QModelIndex):
        """Handle click - emit asset selected."""
        uuid = index.data(TREE_UUID_ROLE)
        if uuid:
            self.asset_selected.emit(uuid)

    def _on_double_clicked(self, index: QModelIndex):
        """Handle double-click - emit for import."""
        uuid = index.data(TREE_UUID_ROLE)
        if uuid:
            self.asset_double_clicked.emit(uuid)
            self._event_bus.request_import_asset.emit(uuid)

    def _on_context_menu(self, position: QPoint):
        """Handle context menu request."""
        index = self.indexAt(position)
        if index.isValid():
            uuid = index.data(TREE_UUID_ROLE)
            if uuid:
                global_pos = self.viewport().mapToGlobal(position)
                self.context_menu_requested.emit(uuid, global_pos)
                self._event_bus.request_open_context_menu.emit(uuid, global_pos)

    def _on_selection_changed(self, selected, deselected):
        """Handle selection change - emit to event bus."""
        uuid = self.get_selected_uuid()
        if uuid:
            self._event_bus.emit_asset_selected(uuid)
            self._event_bus.emit_assets_selected([uuid])
        else:
            self._event_bus.emit_asset_selected("")
            self._event_bus.emit_assets_selected([])


__all__ = ['AssetTreeView']
