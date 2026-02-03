"""
Services for Universal Library

Data access and business operation services.
"""

from .base_repository import BaseRepository
from .asset_repository import AssetRepository
from .folder_repository import FolderRepository
from .asset_folder_repository import AssetFolderRepository
from .database_service import DatabaseService, get_database_service
from .blender_service import BlenderService, get_blender_service
from .asset_manager import AssetManager, get_asset_manager
from .thumbnail_loader import ThumbnailLoader, ThumbnailLoadTask, get_thumbnail_loader
from .addon_installer_service import AddonInstallerService, get_addon_installer
from .cold_storage_service import ColdStorageService, get_cold_storage_service
from .archive_service import ArchiveService, get_archive_service
from .review_state_manager import ReviewStateManager, get_review_state_manager
from .data_change_notifier import DataChangeNotifier, get_data_change_notifier
from .metadata_service import MetadataService, get_metadata_service
from .generic_repository import GenericRepository, get_generic_repository
from .metadata_migration import MetadataMigration, get_metadata_migration, run_migration
from .asset_audit import AssetAudit, get_asset_audit, reset_asset_audit
from .control_authority import ControlAuthority, OperationMode, get_control_authority
from .current_reference_service import CurrentReferenceService, get_current_reference_service
from .retire_service import RetireService, get_retire_service

__all__ = [
    # Repositories
    'BaseRepository',
    'AssetRepository',
    'FolderRepository',
    'AssetFolderRepository',
    # Services
    'DatabaseService',
    'get_database_service',
    'BlenderService',
    'get_blender_service',
    'AssetManager',
    'get_asset_manager',
    'ThumbnailLoader',
    'ThumbnailLoadTask',
    'get_thumbnail_loader',
    'AddonInstallerService',
    'get_addon_installer',
    # Storage services
    'ColdStorageService',
    'get_cold_storage_service',
    'ArchiveService',
    'get_archive_service',
    # Review services
    'ReviewStateManager',
    'get_review_state_manager',
    # Data change notifications
    'DataChangeNotifier',
    'get_data_change_notifier',
    # Metadata service
    'MetadataService',
    'get_metadata_service',
    # Generic repository
    'GenericRepository',
    'get_generic_repository',
    # Metadata migration
    'MetadataMigration',
    'get_metadata_migration',
    'run_migration',
    # Asset audit (Studio Mode only)
    'AssetAudit',
    'get_asset_audit',
    'reset_asset_audit',
    # Control authority (Pipeline Control integration)
    'ControlAuthority',
    'OperationMode',
    'get_control_authority',
    # Current reference service (auto-updating links)
    'CurrentReferenceService',
    'get_current_reference_service',
    # Retire service (Studio/Pipeline mode soft delete)
    'RetireService',
    'get_retire_service',
]
