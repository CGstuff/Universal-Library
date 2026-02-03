"""
Core functionality for Universal Library

Contains:
- Base classes: BaseService (singleton pattern), ServiceLocator (DI)
- Entity system: Entity, behaviors, registry
- USD import/export, thumbnail generation, asset scanning
- Custom exceptions for error handling
"""

from .base_service import BaseService, create_service_getter
from .service_locator import ServiceLocator, ServiceNames
from .usd_service import USDService, USDMetadata, get_usd_service
from .asset_scanner import AssetScanner, ScanResult, get_asset_scanner
from .exceptions import (
    AssetLibraryError,
    DatabaseError,
    AssetNotFoundError,
    FolderNotFoundError,
    DuplicateAssetError,
    DuplicateFolderError,
    FileOperationError,
    BlenderConnectionError,
    ThumbnailError,
)

# Entity system
from .entity import (
    Entity,
    EntityDefinition,
    EntityRegistry,
    get_entity_registry,
    Versionable,
    Variantable,
    Reviewable,
    Taggable,
    Folderable,
    AssetEntity,
)

__all__ = [
    # Base classes
    'BaseService',
    'create_service_getter',
    'ServiceLocator',
    'ServiceNames',
    # Entity system
    'Entity',
    'EntityDefinition',
    'EntityRegistry',
    'get_entity_registry',
    'Versionable',
    'Variantable',
    'Reviewable',
    'Taggable',
    'Folderable',
    'AssetEntity',
    # Services
    'USDService',
    'USDMetadata',
    'get_usd_service',
    'AssetScanner',
    'ScanResult',
    'get_asset_scanner',
    # Exceptions
    'AssetLibraryError',
    'DatabaseError',
    'AssetNotFoundError',
    'FolderNotFoundError',
    'DuplicateAssetError',
    'DuplicateFolderError',
    'FileOperationError',
    'BlenderConnectionError',
    'ThumbnailError',
]
