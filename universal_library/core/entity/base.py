"""
Entity base class and definition.

Provides the foundation for all entity types in the system.
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class EntityDefinition:
    """
    Schema definition for an entity type.

    Attributes:
        name: Entity type name ('asset', 'task', etc.)
        table_name: Database table name ('assets', 'tasks')
        behaviors: List of behavior names this entity supports
        core_fields: Fields stored in main table (not in EAV)
    """
    name: str
    table_name: str
    behaviors: List[str] = field(default_factory=list)
    core_fields: List[str] = field(default_factory=list)

    def has_behavior(self, behavior: str) -> bool:
        """Check if entity has a specific behavior."""
        return behavior in self.behaviors


class Entity(ABC):
    """
    Base class for all entities.

    Wraps dictionary data with typed access and supports
    both core fields (from main table) and dynamic metadata (from EAV).

    Usage:
        class MyEntity(Entity):
            _definition = EntityDefinition(
                name='my_entity',
                table_name='my_entities',
                behaviors=['versionable'],
                core_fields=['uuid', 'name']
            )

        entity = MyEntity({'uuid': '123', 'name': 'Test'})
    """

    _definition: EntityDefinition = None

    def __init__(self, data: Dict[str, Any]):
        """
        Initialize entity with data dictionary.

        Args:
            data: Dictionary of entity data (core + dynamic)
        """
        self._data = data.copy()
        self._dynamic_metadata: Dict[str, Any] = {}
        self._dirty_fields: set = set()

    @classmethod
    def get_definition(cls) -> EntityDefinition:
        """Get entity type definition."""
        return cls._definition

    @property
    def uuid(self) -> str:
        """Get entity UUID (required field)."""
        return self._data.get('uuid', '')

    @property
    def entity_type(self) -> str:
        """Get entity type name."""
        return self._definition.name if self._definition else 'unknown'

    def get(self, field_name: str, default: Any = None) -> Any:
        """
        Get field value.

        Checks dynamic metadata first, then core data.

        Args:
            field_name: Name of field to get
            default: Default value if field not found

        Returns:
            Field value or default
        """
        if field_name in self._dynamic_metadata:
            return self._dynamic_metadata[field_name]
        return self._data.get(field_name, default)

    def set(self, field_name: str, value: Any):
        """
        Set field value.

        Stores in appropriate location based on whether field is core or dynamic.

        Args:
            field_name: Name of field to set
            value: Value to set
        """
        if self._definition and field_name in self._definition.core_fields:
            self._data[field_name] = value
        else:
            self._dynamic_metadata[field_name] = value
        self._dirty_fields.add(field_name)

    def has_field(self, field_name: str) -> bool:
        """Check if field has a value."""
        return field_name in self._data or field_name in self._dynamic_metadata

    def get_core_data(self) -> Dict[str, Any]:
        """Get only core field data."""
        if not self._definition:
            return self._data.copy()
        return {
            k: v for k, v in self._data.items()
            if k in self._definition.core_fields
        }

    def get_dynamic_data(self) -> Dict[str, Any]:
        """Get only dynamic metadata."""
        return self._dynamic_metadata.copy()

    def to_dict(self) -> Dict[str, Any]:
        """
        Export entity as dictionary.

        Merges core data with dynamic metadata.

        Returns:
            Complete entity data dictionary
        """
        result = self._data.copy()
        result.update(self._dynamic_metadata)
        return result

    def is_dirty(self) -> bool:
        """Check if entity has unsaved changes."""
        return len(self._dirty_fields) > 0

    def get_dirty_fields(self) -> set:
        """Get set of modified field names."""
        return self._dirty_fields.copy()

    def mark_clean(self):
        """Clear dirty state after save."""
        self._dirty_fields.clear()

    def load_dynamic_metadata(self, metadata: Dict[str, Any]):
        """
        Load dynamic metadata from storage.

        Called by repository after loading from entity_metadata table.

        Args:
            metadata: Dictionary of dynamic field values
        """
        self._dynamic_metadata.update(metadata)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} uuid={self.uuid}>"


__all__ = ['Entity', 'EntityDefinition']
