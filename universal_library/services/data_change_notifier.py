"""
DataChangeNotifier - Centralized notification for database changes.

Provides:
- Immediate notification for single changes
- Batch mode for bulk operations (emit once at end)
- Debouncing for rapid changes
- Centralized logging for debugging

Usage:
    notifier = get_data_change_notifier()

    # Single change - emits immediately
    notifier.asset_updated(uuid)

    # Batch changes - emits once at end
    with notifier.batch():
        for uuid in uuids:
            db.update(uuid, {...})
            notifier.asset_updated(uuid)
    # Signal emitted here with all changed UUIDs
"""

import threading
from contextlib import contextmanager
from typing import Optional, List, Set
from PyQt6.QtCore import QObject, QTimer


class DataChangeNotifier(QObject):
    """
    Centralized notification for database changes.

    Wraps database operations and automatically emits event bus signals.
    Supports batch mode for grouping multiple changes into a single signal.
    """

    def __init__(self, event_bus=None):
        """
        Initialize notifier.

        Args:
            event_bus: EventBus instance (or None to use singleton)
        """
        super().__init__()

        # Lazy import to avoid circular dependency
        if event_bus is None:
            from universal_library.events.event_bus import get_event_bus
            event_bus = get_event_bus()

        self._event_bus = event_bus

        # Batch mode state (thread-protected)
        self._batch_lock = threading.Lock()
        self._batch_mode = False
        self._batch_depth = 0  # Support nested batch contexts

        # Pending changes for batch mode
        self._pending_adds: Set[str] = set()
        self._pending_updates: Set[str] = set()
        self._pending_deletes: Set[str] = set()

        # Folder changes
        self._pending_folder_adds: Set[int] = set()
        self._pending_folder_updates: Set[int] = set()
        self._pending_folder_deletes: Set[int] = set()

        # Debounce timer for rapid changes
        self._debounce_timer: Optional[QTimer] = None
        self._debounce_delay_ms = 50  # 50ms debounce window

        # Debug mode
        self._debug = False

    # ==================== BATCH MODE ====================

    @contextmanager
    def batch(self):
        """
        Context manager for batching multiple changes.

        All notifications within this context are collected and
        emitted as batch signals when the context exits.

        Supports nesting - only flushes when outermost batch exits.
        Thread-safe via lock protection.

        Example:
            with notifier.batch():
                for uuid in uuids:
                    notifier.asset_updated(uuid)
            # Single assets_batch_updated signal emitted here
        """
        with self._batch_lock:
            self._batch_depth += 1
            self._batch_mode = True

        try:
            yield
        finally:
            with self._batch_lock:
                self._batch_depth -= 1
                if self._batch_depth == 0:
                    self._batch_mode = False
            # Flush outside lock to avoid holding lock during signal emission
            if self._batch_depth == 0:
                self._flush()

    def _flush(self):
        """Emit all pending batch notifications."""
        # Collect all pending items under lock, then emit outside lock
        with self._batch_lock:
            pending_adds = list(self._pending_adds) if self._pending_adds else []
            pending_updates = list(self._pending_updates) if self._pending_updates else []
            pending_deletes = list(self._pending_deletes) if self._pending_deletes else []
            pending_folder_adds = list(self._pending_folder_adds) if self._pending_folder_adds else []
            pending_folder_deletes = list(self._pending_folder_deletes) if self._pending_folder_deletes else []

            self._pending_adds.clear()
            self._pending_updates.clear()
            self._pending_deletes.clear()
            self._pending_folder_adds.clear()
            self._pending_folder_deletes.clear()

        # Emit signals outside lock to avoid deadlock
        if pending_adds:
            self._log(f"Batch emit: {len(pending_adds)} assets added")
            self._event_bus.assets_batch_added.emit(pending_adds)

        if pending_updates:
            self._log(f"Batch emit: {len(pending_updates)} assets updated")
            self._event_bus.assets_batch_updated.emit(pending_updates)

        if pending_deletes:
            self._log(f"Batch emit: {len(pending_deletes)} assets deleted")
            self._event_bus.assets_batch_removed.emit(pending_deletes)

        if pending_folder_adds:
            self._log(f"Batch emit: {len(pending_folder_adds)} folders added")
            for folder_id in pending_folder_adds:
                self._event_bus.folder_added.emit(folder_id)

        if pending_folder_deletes:
            self._log(f"Batch emit: {len(pending_folder_deletes)} folders deleted")
            for folder_id in pending_folder_deletes:
                self._event_bus.folder_removed.emit(folder_id)

    # ==================== ASSET NOTIFICATIONS ====================

    def asset_added(self, uuid: str):
        """
        Notify that an asset was added.

        Args:
            uuid: UUID of the new asset
        """
        if not uuid:
            return

        with self._batch_lock:
            if self._batch_mode:
                self._pending_adds.add(uuid)
                self._log(f"Queued: asset_added({uuid[:8]}...)")
                return

        self._log(f"Emit: asset_added({uuid[:8]}...)")
        self._event_bus.asset_added.emit(uuid)

    def asset_updated(self, uuid: str):
        """
        Notify that an asset was updated.

        Args:
            uuid: UUID of the updated asset
        """
        if not uuid:
            return

        with self._batch_lock:
            if self._batch_mode:
                self._pending_updates.add(uuid)
                self._log(f"Queued: asset_updated({uuid[:8]}...)")
                return

        self._log(f"Emit: asset_updated({uuid[:8]}...)")
        self._event_bus.asset_updated.emit(uuid)

    def asset_removed(self, uuid: str):
        """
        Notify that an asset was removed/deleted.

        Args:
            uuid: UUID of the removed asset
        """
        if not uuid:
            return

        with self._batch_lock:
            if self._batch_mode:
                self._pending_deletes.add(uuid)
                self._log(f"Queued: asset_removed({uuid[:8]}...)")
                return

        self._log(f"Emit: asset_removed({uuid[:8]}...)")
        self._event_bus.asset_removed.emit(uuid)

    def assets_removed(self, uuids: List[str]):
        """
        Notify that multiple assets were removed.

        Args:
            uuids: List of UUIDs of removed assets
        """
        if not uuids:
            return

        with self._batch_lock:
            if self._batch_mode:
                self._pending_deletes.update(uuids)
                self._log(f"Queued: {len(uuids)} assets removed")
                return

        self._log(f"Emit: assets_batch_removed({len(uuids)} assets)")
        self._event_bus.assets_batch_removed.emit(uuids)

    # ==================== FOLDER NOTIFICATIONS ====================

    def folder_added(self, folder_id: int):
        """Notify that a folder was added."""
        with self._batch_lock:
            if self._batch_mode:
                self._pending_folder_adds.add(folder_id)
                self._log(f"Queued: folder_added({folder_id})")
                return

        self._log(f"Emit: folder_added({folder_id})")
        self._event_bus.folder_added.emit(folder_id)

    def folder_updated(self, folder_id: int, name: str = ""):
        """Notify that a folder was updated."""
        self._log(f"Emit: folder_renamed({folder_id}, {name})")
        self._event_bus.folder_renamed.emit(folder_id, name)

    def folder_removed(self, folder_id: int):
        """Notify that a folder was removed."""
        with self._batch_lock:
            if self._batch_mode:
                self._pending_folder_deletes.add(folder_id)
                self._log(f"Queued: folder_removed({folder_id})")
                return

        self._log(f"Emit: folder_removed({folder_id})")
        self._event_bus.folder_removed.emit(folder_id)

    # ==================== BULK OPERATIONS ====================

    def assets_moved(self, uuids: List[str], folder_id: int, success_count: int):
        """Notify that assets were moved to a folder."""
        self._log(f"Emit: assets_moved({len(uuids)} assets to folder {folder_id})")
        self._event_bus.assets_moved.emit(uuids, folder_id, success_count)

    def bulk_operation_completed(self, operation: str, count: int):
        """Notify that a bulk operation completed."""
        self._log(f"Emit: bulk_operation_completed({operation}, {count})")
        self._event_bus.bulk_operation_completed.emit(operation, count)

    # ==================== VERSION NOTIFICATIONS ====================

    def version_created(self, uuid: str, version_label: str,
                       version_group_id: str, variant_name: str):
        """Notify that a new version was created."""
        self._log(f"Emit: version_created({uuid[:8]}..., {version_label})")
        self._event_bus.asset_version_created.emit(
            uuid, version_label, version_group_id, variant_name
        )

    # ==================== REVIEW NOTIFICATIONS ====================

    def review_note_added(self, note_id: int):
        """Notify that a review note was added."""
        self._log(f"Emit: review_note_added({note_id})")
        self._event_bus.review_note_added.emit(note_id)

    def review_note_resolved(self, note_id: int):
        """Notify that a review note was resolved."""
        self._log(f"Emit: review_note_resolved({note_id})")
        self._event_bus.review_note_resolved.emit(note_id)

    def review_note_deleted(self, note_id: int):
        """Notify that a review note was deleted."""
        self._log(f"Emit: review_note_deleted({note_id})")
        self._event_bus.review_note_deleted.emit(note_id)

    # ==================== UTILITY ====================

    def set_debug(self, enabled: bool):
        """Enable/disable debug logging."""
        self._debug = enabled

    def _log(self, message: str):
        """Log message if debug mode is enabled."""
        if self._debug:
            pass


# Singleton instance
_notifier_instance: Optional[DataChangeNotifier] = None


def get_data_change_notifier() -> DataChangeNotifier:
    """
    Get global DataChangeNotifier singleton.

    Returns:
        Global DataChangeNotifier instance
    """
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = DataChangeNotifier()
    return _notifier_instance


__all__ = ['DataChangeNotifier', 'get_data_change_notifier']
