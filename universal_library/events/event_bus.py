"""
EventBus - Central event system for cross-widget communication

Pattern: Singleton event bus for decoupled component communication
Based on animation_library architecture.
"""

from typing import Optional, List, Any
from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    """
    Central event bus for application-wide signal coordination

    Features:
    - Selection state management
    - View state management
    - Request signals for actions
    - State getters/setters

    Usage:
        bus = get_event_bus()
        bus.asset_selected.connect(on_asset_selected)
        bus.emit_asset_selected(uuid)
    """

    # ==================== SELECTION SIGNALS ====================
    # Single asset selection
    asset_selected = pyqtSignal(str)  # uuid (empty string for deselect)

    # Multi-selection
    assets_selected = pyqtSignal(list)  # [uuids]

    # Folder selection
    folder_selected = pyqtSignal(int)  # folder_id (-1 for All, -2 for Favorites, -3 for Recent)

    # ==================== VIEW STATE SIGNALS ====================
    # View mode (grid/list)
    view_mode_changed = pyqtSignal(str)  # "grid" or "list"

    # Card size
    card_size_changed = pyqtSignal(int)  # size in pixels

    # Search text
    search_text_changed = pyqtSignal(str)  # search query

    # Sort order
    sort_changed = pyqtSignal(str, bool)  # field, ascending

    # ==================== REQUEST SIGNALS ====================
    # These request actions to be performed by services
    request_toggle_favorite = pyqtSignal(str)  # uuid
    request_delete_asset = pyqtSignal(str)  # uuid
    request_delete_assets = pyqtSignal(list)  # [uuids]
    request_retire_assets = pyqtSignal(list)  # [uuids] - for Studio/Pipeline mode
    request_edit_asset = pyqtSignal(str)  # uuid
    request_import_asset = pyqtSignal(str)  # uuid
    request_regenerate_thumbnail = pyqtSignal(str)  # uuid
    request_move_to_folder = pyqtSignal(list, int)  # [uuids], folder_id
    request_open_context_menu = pyqtSignal(str, object)  # uuid, QPoint

    # ==================== DATA SIGNALS ====================
    # Model updates - single asset
    assets_loaded = pyqtSignal(int)  # count
    asset_added = pyqtSignal(str)  # uuid
    asset_updated = pyqtSignal(str)  # uuid
    asset_removed = pyqtSignal(str)  # uuid

    # Batch data signals - for efficient bulk updates
    # Used by DataChangeNotifier for grouping multiple changes
    assets_batch_added = pyqtSignal(list)    # [uuids]
    assets_batch_updated = pyqtSignal(list)  # [uuids]
    assets_batch_removed = pyqtSignal(list)  # [uuids]

    # Version creation (for review auto-join)
    # Args: uuid, version_label, version_group_id, variant_name
    asset_version_created = pyqtSignal(str, str, str, str)

    # Folder updates
    folders_loaded = pyqtSignal()
    folder_added = pyqtSignal(int)  # folder_id
    folder_renamed = pyqtSignal(int, str)  # folder_id, new_name
    folder_removed = pyqtSignal(int)  # folder_id

    # Asset operations
    assets_moved = pyqtSignal(list, int, int)  # [uuids], folder_id, success_count

    # ==================== EDIT MODE SIGNALS ====================
    # Edit mode toggle
    edit_mode_changed = pyqtSignal(bool)  # enabled/disabled

    # Bulk operation completion
    bulk_operation_completed = pyqtSignal(str, int)  # operation_name, success_count

    # ==================== REVIEW SIGNALS ====================
    # Review system
    review_opened = pyqtSignal(str, str)  # asset_uuid, version_label
    review_note_added = pyqtSignal(int)   # note_id
    review_note_resolved = pyqtSignal(int)  # note_id
    review_note_deleted = pyqtSignal(int)  # note_id
    review_session_resolved = pyqtSignal(str)  # session_id (all notes resolved)
    screenshot_uploaded = pyqtSignal(int)  # screenshot_id
    screenshot_deleted = pyqtSignal(int)  # screenshot_id
    annotation_saved = pyqtSignal(str, str)  # asset_uuid, screenshot_name

    # ==================== UI STATE SIGNALS ====================
    # Status messages
    status_message = pyqtSignal(str)  # message
    status_error = pyqtSignal(str)  # error message

    # Progress
    progress_started = pyqtSignal(str)  # operation name
    progress_updated = pyqtSignal(int, int, str)  # current, total, message
    progress_finished = pyqtSignal()

    # ==================== STATE STORAGE ====================
    def __init__(self, parent=None):
        super().__init__(parent)

        # Current state
        self._current_asset_uuid: str = ""
        self._selected_asset_uuids: List[str] = []
        self._current_folder_id: int = -1  # All Assets
        self._view_mode: str = "grid"
        self._card_size: int = 200
        self._search_text: str = ""
        self._sort_field: str = "name"
        self._sort_ascending: bool = True
        self._edit_mode: bool = False

    # ==================== STATE GETTERS ====================
    @property
    def current_asset_uuid(self) -> str:
        """Get currently selected asset UUID"""
        return self._current_asset_uuid

    @property
    def selected_asset_uuids(self) -> List[str]:
        """Get list of selected asset UUIDs"""
        return self._selected_asset_uuids.copy()

    @property
    def current_folder_id(self) -> int:
        """Get currently selected folder ID"""
        return self._current_folder_id

    @property
    def view_mode(self) -> str:
        """Get current view mode (grid/list)"""
        return self._view_mode

    @property
    def card_size(self) -> int:
        """Get current card size"""
        return self._card_size

    @property
    def search_text(self) -> str:
        """Get current search text"""
        return self._search_text

    @property
    def edit_mode(self) -> bool:
        """Get edit mode state"""
        return self._edit_mode

    # ==================== EMIT HELPERS ====================
    def emit_asset_selected(self, uuid: str):
        """Select a single asset"""
        self._current_asset_uuid = uuid
        self._selected_asset_uuids = [uuid] if uuid else []
        self.asset_selected.emit(uuid)

    def emit_assets_selected(self, uuids: List[str]):
        """Select multiple assets"""
        self._selected_asset_uuids = uuids.copy()
        if uuids:
            self._current_asset_uuid = uuids[-1]  # Last selected
        else:
            self._current_asset_uuid = ""
        self.assets_selected.emit(uuids)

    def emit_folder_selected(self, folder_id: int):
        """Select a folder"""
        self._current_folder_id = folder_id
        self.folder_selected.emit(folder_id)

    def emit_view_mode_changed(self, mode: str):
        """Change view mode"""
        self._view_mode = mode
        self.view_mode_changed.emit(mode)

    def emit_card_size_changed(self, size: int):
        """Change card size"""
        self._card_size = size
        self.card_size_changed.emit(size)

    def emit_search_text_changed(self, text: str):
        """Change search text"""
        self._search_text = text
        self.search_text_changed.emit(text)

    def emit_sort_changed(self, field: str, ascending: bool):
        """Change sort order"""
        self._sort_field = field
        self._sort_ascending = ascending
        self.sort_changed.emit(field, ascending)

    def emit_status(self, message: str):
        """Emit status message"""
        self.status_message.emit(message)

    def emit_error(self, message: str):
        """Emit error message"""
        self.status_error.emit(message)

    def emit_edit_mode_changed(self, enabled: bool):
        """Toggle edit mode"""
        self._edit_mode = enabled
        self.edit_mode_changed.emit(enabled)


# Singleton instance
_event_bus_instance: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """
    Get global EventBus singleton

    Returns:
        Global EventBus instance
    """
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus()
    return _event_bus_instance


__all__ = ['EventBus', 'get_event_bus']
