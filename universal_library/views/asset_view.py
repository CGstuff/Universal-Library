"""
AssetView - QListView subclass for displaying USD assets

Pattern: Custom view with grid/list mode switching
Based on animation_library architecture.
"""

from typing import Optional, List
from PyQt6.QtWidgets import QListView, QAbstractItemView
from PyQt6.QtCore import (
    Qt, QSize, QModelIndex, pyqtSignal, QItemSelectionModel
)

from ..config import Config
from ..events.event_bus import get_event_bus
from ..models.asset_list_model import AssetRole
from .asset_card_delegate import AssetCardDelegate


class AssetView(QListView):
    """
    Custom list view for displaying USD assets

    Features:
    - Grid/List mode switching
    - Virtual scrolling for performance
    - Drag & drop support
    - Multi-selection support
    - Keyboard navigation

    Signals:
        asset_double_clicked(str): UUID of double-clicked asset

    Usage:
        view = AssetView()
        view.set_view_mode("grid")
        view.set_card_size(200)
        view.setModel(proxy_model)
    """

    # Signals
    asset_double_clicked = pyqtSignal(str)  # uuid

    def __init__(self, parent=None):
        super().__init__(parent)

        self._view_mode = "grid"
        self._card_size = Config.DEFAULT_CARD_SIZE
        self._event_bus = get_event_bus()

        self._setup_view()
        self._connect_signals()

    def _setup_view(self):
        """Configure view settings"""

        # Create and set custom delegate for rendering asset cards
        self._delegate = AssetCardDelegate(parent=self, view_mode=self._view_mode)
        self._delegate.set_card_size(self._card_size)
        self.setItemDelegate(self._delegate)

        # Selection
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)

        # Scrolling
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        # Drag & drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        # Performance
        self.setUniformItemSizes(True)  # Enable for better scrolling performance
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(50)


        # Apply initial view mode
        self._apply_view_mode()

    def _connect_signals(self):
        """Connect internal signals"""
        self.doubleClicked.connect(self._on_double_clicked)
        self.selectionModel()  # Will be connected when model is set

    def setModel(self, model):
        """Override to connect selection signals"""
        super().setModel(model)

        # Connect selection changed
        if self.selectionModel():
            self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def set_view_mode(self, mode: str):
        """
        Set view mode

        Args:
            mode: "grid" or "list"
        """
        if mode in ("grid", "list") and mode != self._view_mode:
            self._view_mode = mode
            self._apply_view_mode()

            # Notify delegate
            self._delegate.set_view_mode(mode)

            # Emit event
            self._event_bus.emit_view_mode_changed(mode)

    def get_view_mode(self) -> str:
        """Get current view mode"""
        return self._view_mode

    def set_card_size(self, size: int):
        """
        Set card size for grid mode

        Args:
            size: Size in pixels
        """
        size = max(Config.MIN_CARD_SIZE, min(size, Config.MAX_CARD_SIZE))
        if size != self._card_size:
            self._card_size = size
            self._apply_view_mode()

            # Notify delegate
            self._delegate.set_card_size(size)

            # Emit event
            self._event_bus.emit_card_size_changed(size)

    def get_card_size(self) -> int:
        """Get current card size"""
        return self._card_size

    def set_edit_mode(self, enabled: bool):
        """
        Enable/disable edit mode (shows checkboxes for selection)

        Args:
            enabled: True to show checkboxes
        """
        self._delegate.set_edit_mode(enabled)
        # Force repaint to show/hide checkboxes
        self.viewport().update()

    def _apply_view_mode(self):
        """Apply current view mode settings"""
        if self._view_mode == "grid":
            self.setViewMode(QListView.ViewMode.IconMode)
            self.setFlow(QListView.Flow.LeftToRight)
            self.setWrapping(True)
            self.setResizeMode(QListView.ResizeMode.Adjust)
            self.setSpacing(0)  # Tight grid: cards touching for sleek look
            # IconMode uses Snap movement for proper drag behavior
            self.setMovement(QListView.Movement.Snap)

            # Calculate grid size (card + name below) - no extra padding
            name_height = 28
            self.setGridSize(QSize(
                self._card_size,  # No extra spacing
                self._card_size + name_height
            ))
        else:
            # List mode
            self.setViewMode(QListView.ViewMode.ListMode)
            self.setFlow(QListView.Flow.TopToBottom)
            self.setWrapping(False)
            self.setResizeMode(QListView.ResizeMode.Adjust)
            self.setSpacing(0)  # Tight list: rows touching
            self.setGridSize(QSize(-1, Config.LIST_ROW_HEIGHT))
            # ListMode defaults to Static, but we need Snap for drag to work
            self.setMovement(QListView.Movement.Snap)

        # Re-enable drag after mode change (setViewMode can reset settings)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

    def get_selected_uuids(self) -> List[str]:
        """
        Get list of selected asset UUIDs

        Returns:
            List of UUID strings
        """
        uuids = []
        for index in self.selectedIndexes():
            uuid = index.data(AssetRole.UUIDRole)
            if uuid:
                uuids.append(uuid)
        return uuids

    def select_asset(self, uuid: str, clear_selection: bool = True):
        """
        Select asset by UUID

        Args:
            uuid: Asset UUID to select
            clear_selection: Clear existing selection first
        """
        model = self.model()
        if not model:
            return

        # Find index for UUID
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if index.data(AssetRole.UUIDRole) == uuid:
                if clear_selection:
                    self.selectionModel().select(
                        index,
                        QItemSelectionModel.SelectionFlag.ClearAndSelect
                    )
                else:
                    self.selectionModel().select(
                        index,
                        QItemSelectionModel.SelectionFlag.Select
                    )
                self.scrollTo(index)
                break

    def clear_selection(self):
        """Clear all selection"""
        self.selectionModel().clearSelection()
        self._event_bus.emit_asset_selected("")

    def scroll_to_asset(self, uuid: str):
        """
        Scroll to make asset visible

        Args:
            uuid: Asset UUID to scroll to
        """
        model = self.model()
        if not model:
            return

        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if index.data(AssetRole.UUIDRole) == uuid:
                self.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)
                break

    def _on_double_clicked(self, index: QModelIndex):
        """Handle double-click on item"""
        uuid = index.data(AssetRole.UUIDRole)
        if uuid:
            self.asset_double_clicked.emit(uuid)
            # Also emit import request via event bus
            self._event_bus.request_import_asset.emit(uuid)

    def _on_selection_changed(self, selected, deselected):
        """Handle selection changes"""
        uuids = self.get_selected_uuids()

        # Always emit assets_selected for bulk edit toolbar
        self._event_bus.emit_assets_selected(uuids)

        if len(uuids) == 1:
            # Single selection - also emit for metadata panel
            self._event_bus.emit_asset_selected(uuids[0])
        elif len(uuids) == 0:
            # No selection
            self._event_bus.emit_asset_selected("")

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        key = event.key()
        modifiers = event.modifiers()

        # Select all (Ctrl+A)
        if key == Qt.Key.Key_A and modifiers == Qt.KeyboardModifier.ControlModifier:
            self.selectAll()
            return

        # Delete (Del)
        if key == Qt.Key.Key_Delete:
            uuids = self.get_selected_uuids()
            if uuids:
                self._event_bus.request_delete_assets.emit(uuids)
            return

        # Favorite toggle (F)
        if key == Qt.Key.Key_F and not modifiers:
            uuids = self.get_selected_uuids()
            if len(uuids) == 1:
                self._event_bus.request_toggle_favorite.emit(uuids[0])
            return

        # Enter/Return - import
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            uuids = self.get_selected_uuids()
            if len(uuids) == 1:
                self._event_bus.request_import_asset.emit(uuids[0])
            return

        # Escape - clear selection
        if key == Qt.Key.Key_Escape:
            self.clear_selection()
            return

        super().keyPressEvent(event)

    def startDrag(self, supportedActions):
        """
        Override startDrag to force viewport cleanup after drag completes

        This fixes visual artifacts when cards are dragged and dropped in empty space.
        The default QListView drag implementation can leave pixmap artifacts on screen
        when the drag is cancelled (ESC) or dropped on invalid targets.

        Args:
            supportedActions: Qt.DropActions supported by this view
        """
        # Call parent's drag implementation (blocks until drag completes)
        super().startDrag(supportedActions)

        # Force immediate viewport repaint to clear drag visual artifacts
        self.viewport().repaint()

        # Also force layout recalculation to ensure proper redraw
        self.scheduleDelayedItemsLayout()

        # Update the view itself as well
        self.update()


__all__ = ['AssetView']
