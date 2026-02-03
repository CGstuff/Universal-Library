"""
EntityEventBus - Entity-level events for the extensible entity system.

Provides signals for:
- Entity lifecycle (created, updated, deleted)
- Batch operations (for performance)
- Metadata schema changes (field added/removed)
- Entity type registration
"""

from typing import Optional, List, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal


class EntityEventBus(QObject):
    """
    Event bus for entity system events.

    This complements the main EventBus with entity-centric signals
    that work across all registered entity types.

    Usage:
        bus = get_entity_event_bus()

        # Subscribe to entity changes
        bus.entity_created.connect(on_entity_created)
        bus.entity_updated.connect(on_entity_updated)

        # Emit from repository
        bus.emit_entity_created('asset', uuid)
    """

    # ==================== ENTITY LIFECYCLE ====================
    # Generic entity events that work for any entity type

    # Single entity operations
    # Args: entity_type (str), uuid (str)
    entity_created = pyqtSignal(str, str)
    entity_updated = pyqtSignal(str, str)
    entity_deleted = pyqtSignal(str, str)

    # Batch operations (for performance when updating many entities)
    # Args: entity_type (str), uuids (list)
    entities_batch_created = pyqtSignal(str, list)
    entities_batch_updated = pyqtSignal(str, list)
    entities_batch_deleted = pyqtSignal(str, list)

    # ==================== METADATA SCHEMA ====================
    # Schema changes (new fields registered/removed)

    # Args: entity_type (str), field_name (str), field_info (dict)
    metadata_field_added = pyqtSignal(str, str, dict)

    # Args: entity_type (str), field_name (str)
    metadata_field_removed = pyqtSignal(str, str)

    # Field definition updated (display name, validation, etc.)
    # Args: entity_type (str), field_name (str), field_info (dict)
    metadata_field_updated = pyqtSignal(str, str, dict)

    # ==================== ENTITY TYPE REGISTRY ====================
    # New entity types registered

    # Args: entity_type (str), definition (dict)
    entity_type_registered = pyqtSignal(str, dict)

    # Args: entity_type (str)
    entity_type_unregistered = pyqtSignal(str)

    # ==================== METADATA VALUES ====================
    # Individual metadata value changes

    # Args: entity_type (str), uuid (str), field_name (str), old_value, new_value
    metadata_value_changed = pyqtSignal(str, str, str, object, object)

    # Batch metadata update (multiple fields at once)
    # Args: entity_type (str), uuid (str), changes (dict: field_name -> new_value)
    metadata_values_changed = pyqtSignal(str, str, dict)

    # ==================== MIGRATION EVENTS ====================
    # For tracking migration progress

    # Args: total_count (int)
    migration_started = pyqtSignal(int)

    # Args: current (int), total (int), entity_type (str)
    migration_progress = pyqtSignal(int, int, str)

    # Args: stats (dict)
    migration_completed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

    # ==================== EMIT HELPERS ====================

    def emit_entity_created(self, entity_type: str, uuid: str):
        """Emit entity created event."""
        self.entity_created.emit(entity_type, uuid)

    def emit_entity_updated(self, entity_type: str, uuid: str):
        """Emit entity updated event."""
        self.entity_updated.emit(entity_type, uuid)

    def emit_entity_deleted(self, entity_type: str, uuid: str):
        """Emit entity deleted event."""
        self.entity_deleted.emit(entity_type, uuid)

    def emit_entities_batch_created(self, entity_type: str, uuids: List[str]):
        """Emit batch created event."""
        if uuids:
            self.entities_batch_created.emit(entity_type, uuids)

    def emit_entities_batch_updated(self, entity_type: str, uuids: List[str]):
        """Emit batch updated event."""
        if uuids:
            self.entities_batch_updated.emit(entity_type, uuids)

    def emit_entities_batch_deleted(self, entity_type: str, uuids: List[str]):
        """Emit batch deleted event."""
        if uuids:
            self.entities_batch_deleted.emit(entity_type, uuids)

    def emit_metadata_field_added(
        self,
        entity_type: str,
        field_name: str,
        field_info: Dict[str, Any]
    ):
        """Emit field added event."""
        self.metadata_field_added.emit(entity_type, field_name, field_info)

    def emit_metadata_field_removed(self, entity_type: str, field_name: str):
        """Emit field removed event."""
        self.metadata_field_removed.emit(entity_type, field_name)

    def emit_metadata_value_changed(
        self,
        entity_type: str,
        uuid: str,
        field_name: str,
        old_value: Any,
        new_value: Any
    ):
        """Emit single metadata value change."""
        self.metadata_value_changed.emit(
            entity_type, uuid, field_name, old_value, new_value
        )

    def emit_metadata_values_changed(
        self,
        entity_type: str,
        uuid: str,
        changes: Dict[str, Any]
    ):
        """Emit batch metadata values change."""
        if changes:
            self.metadata_values_changed.emit(entity_type, uuid, changes)


# Singleton instance
_entity_event_bus: Optional[EntityEventBus] = None


def get_entity_event_bus() -> EntityEventBus:
    """Get global EntityEventBus singleton instance."""
    global _entity_event_bus
    if _entity_event_bus is None:
        _entity_event_bus = EntityEventBus()
    return _entity_event_bus


__all__ = ['EntityEventBus', 'get_entity_event_bus']
