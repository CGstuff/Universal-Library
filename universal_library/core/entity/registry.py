"""
Entity type registry.

Central registry for all entity types in the system.
Enables dynamic entity type lookup and instantiation.
"""

from typing import Dict, Type, Optional, List
from .base import Entity, EntityDefinition


class EntityRegistry:
    """
    Central registry for entity types.

    Provides registration, lookup, and instantiation of entity types.
    Singleton pattern ensures consistent registry across the application.

    Usage:
        # Get registry instance
        registry = get_entity_registry()

        # Register entity type
        registry.register(AssetEntity)

        # Get entity class
        entity_class = registry.get('asset')

        # Create entity instance
        entity = registry.create('asset', data_dict)

        # List all types
        types = registry.list_types()
    """

    _instance: 'EntityRegistry' = None

    def __init__(self):
        """Initialize empty registry."""
        self._types: Dict[str, Type[Entity]] = {}
        self._definitions: Dict[str, EntityDefinition] = {}

    @classmethod
    def get_instance(cls) -> 'EntityRegistry':
        """
        Get singleton registry instance.

        Returns:
            The global EntityRegistry instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (for testing)."""
        cls._instance = None

    def register(self, entity_class: Type[Entity]) -> bool:
        """
        Register an entity type.

        Args:
            entity_class: Entity class to register

        Returns:
            True if registered successfully

        Raises:
            ValueError: If entity class has no definition
        """
        definition = entity_class.get_definition()
        if not definition:
            raise ValueError(f"Entity class {entity_class.__name__} has no definition")

        if definition.name in self._types:
            # Already registered - update
            pass

        self._types[definition.name] = entity_class
        self._definitions[definition.name] = definition

        return True

    def unregister(self, type_name: str) -> bool:
        """
        Unregister an entity type.

        Args:
            type_name: Name of entity type to unregister

        Returns:
            True if unregistered successfully
        """
        if type_name in self._types:
            del self._types[type_name]
            del self._definitions[type_name]
            return True
        return False

    def get(self, type_name: str) -> Optional[Type[Entity]]:
        """
        Get entity class by type name.

        Args:
            type_name: Entity type name

        Returns:
            Entity class or None if not found
        """
        return self._types.get(type_name)

    def get_definition(self, type_name: str) -> Optional[EntityDefinition]:
        """
        Get entity definition by type name.

        Args:
            type_name: Entity type name

        Returns:
            EntityDefinition or None if not found
        """
        return self._definitions.get(type_name)

    def list_types(self) -> List[str]:
        """
        List all registered entity type names.

        Returns:
            List of entity type names
        """
        return list(self._types.keys())

    def list_definitions(self) -> List[EntityDefinition]:
        """
        List all entity definitions.

        Returns:
            List of EntityDefinition objects
        """
        return list(self._definitions.values())

    def create(self, type_name: str, data: Dict) -> Optional[Entity]:
        """
        Create entity instance from data.

        Args:
            type_name: Entity type name
            data: Entity data dictionary

        Returns:
            Entity instance or None if type not found
        """
        entity_class = self.get(type_name)
        if entity_class:
            return entity_class(data)
        return None

    def is_registered(self, type_name: str) -> bool:
        """Check if entity type is registered."""
        return type_name in self._types

    def get_types_with_behavior(self, behavior: str) -> List[str]:
        """
        Get all entity types that have a specific behavior.

        Args:
            behavior: Behavior name (e.g., 'versionable', 'reviewable')

        Returns:
            List of entity type names with that behavior
        """
        result = []
        for name, definition in self._definitions.items():
            if definition.has_behavior(behavior):
                result.append(name)
        return result


# Module-level singleton accessor
_registry: Optional[EntityRegistry] = None


def get_entity_registry() -> EntityRegistry:
    """
    Get global EntityRegistry singleton instance.

    Returns:
        The global EntityRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = EntityRegistry.get_instance()
    return _registry


__all__ = ['EntityRegistry', 'get_entity_registry']
