"""
Entity system for Universal Library.

Provides:
- Entity base class for all data types
- Behavior mixins (Versionable, Variantable, Reviewable, etc.)
- EntityRegistry for type registration
- AssetEntity concrete implementation

Usage:
    from universal_library.core.entity import (
        Entity, EntityDefinition, EntityRegistry,
        Versionable, Variantable, Reviewable, Taggable, Folderable,
        AssetEntity, get_entity_registry
    )
"""

from .base import Entity, EntityDefinition
from .behaviors import Versionable, Variantable, Reviewable, Taggable, Folderable
from .registry import EntityRegistry, get_entity_registry
from .asset import AssetEntity

__all__ = [
    # Base
    'Entity',
    'EntityDefinition',
    # Behaviors
    'Versionable',
    'Variantable',
    'Reviewable',
    'Taggable',
    'Folderable',
    # Registry
    'EntityRegistry',
    'get_entity_registry',
    # Concrete entities
    'AssetEntity',
]
