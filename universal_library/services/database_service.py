"""
DatabaseService - Database facade and schema management

Pattern: Facade pattern coordinating repositories
Maintains backward-compatible API while delegating to specialized repositories.

Refactored to delegate to:
- SchemaManager: Schema creation and migrations
- DatabaseMaintenance: Stats, integrity, backup
- AssetFileOps: Rename, move operations
"""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)

from ..config import Config
from .base_repository import BaseRepository
from .asset_repository import AssetRepository
from .folder_repository import FolderRepository
from .tag_repository import TagRepository
from .asset_folder_repository import AssetFolderRepository
from .schema_manager import SchemaManager
from .database_maintenance import DatabaseMaintenance, VERSION_FEATURES
from .asset_file_ops import AssetFileOps
from .asset_audit import AssetAudit


class DatabaseService:
    """
    Database service facade for asset metadata storage

    Features:
    - Schema initialization and migrations (via SchemaManager)
    - Database maintenance (via DatabaseMaintenance)
    - Asset file operations (via AssetFileOps)
    - Coordinates AssetRepository and FolderRepository
    - Backward-compatible API for existing code
    """

    SCHEMA_VERSION = SchemaManager.SCHEMA_VERSION

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize database service

        Args:
            db_path: Path to database file (defaults to Config.get_database_path())
        """
        self.db_path = db_path or Config.get_database_path()

        # Initialize shared repository infrastructure
        BaseRepository.initialize(self.db_path)

        # Create repositories
        self._assets = AssetRepository()
        self._folders = FolderRepository()
        self._tags = TagRepository()
        self._asset_folders = AssetFolderRepository()

        # For backward compatibility with direct connection access
        self.local = threading.local()

        # Initialize sub-modules (lazy - after connection is available)
        self._schema_manager = None
        self._maintenance = None
        self._file_ops = None
        self._asset_audit = None

        # Initialize schema
        self._init_database()

        # Initialize sub-modules now that connection exists
        self._init_modules()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection (for schema init and backward compat)"""
        if not hasattr(self.local, 'connection') or self.local.connection is None:
            # Thread-local connections ensure thread safety without needing check_same_thread=False
            self.local.connection = sqlite3.connect(
                str(self.db_path),
                timeout=30.0
            )
            self.local.connection.execute("PRAGMA foreign_keys = ON")
            self.local.connection.execute("PRAGMA journal_mode = WAL")
            self.local.connection.row_factory = sqlite3.Row

        return self.local.connection

    @contextmanager
    def transaction(self):
        """Context manager for database transactions"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e

    def _init_modules(self):
        """Initialize sub-modules after database connection is ready."""
        conn = self._get_connection()

        # Schema manager
        self._schema_manager = SchemaManager(conn)

        # Database maintenance
        self._maintenance = DatabaseMaintenance(conn, self.db_path)

        # Asset file operations (with callbacks to database methods)
        self._file_ops = AssetFileOps(
            get_asset=self._assets.get_by_uuid,
            update_asset=self._assets.update,
            name_exists=self._assets.name_exists,
            get_versions=self._assets.get_versions,
            get_folder_path=self._folders.get_full_path,
            set_asset_folders=self._asset_folders.set_asset_folders,
            get_asset_folders=self._asset_folders.get_asset_folders,
            remove_asset_from_folder=self._asset_folders.remove_asset_from_folder,
        )

        # Asset audit logging (Studio Mode only)
        self._asset_audit = AssetAudit(conn)

    def _init_database(self):
        """Initialize database schema via SchemaManager."""
        conn = self._get_connection()
        schema_manager = SchemaManager(conn)
        schema_manager.initialize()
        # Ensure all metadata fields are registered (for existing databases)
        schema_manager.ensure_metadata_fields()


    # ==================== FOLDER OPERATIONS (delegates to FolderRepository) ====================

    def get_root_folder_id(self) -> int:
        """Get the ID of the root folder"""
        return self._folders.get_root_folder_id()

    def create_folder(self, name: str, parent_id: Optional[int] = None,
                      description: str = "") -> Optional[int]:
        """Create new folder"""
        return self._folders.create(name, parent_id, description)

    def get_folder_by_id(self, folder_id: int) -> Optional[Dict[str, Any]]:
        """Get folder by ID"""
        return self._folders.get_by_id(folder_id)

    def get_all_folders(self) -> List[Dict[str, Any]]:
        """Get all folders"""
        return self._folders.get_all()

    def rename_folder(self, folder_id: int, new_name: str) -> bool:
        """Rename a folder"""
        return self._folders.rename(folder_id, new_name)

    def delete_folder(self, folder_id: int) -> bool:
        """Delete folder"""
        return self._folders.delete(folder_id)

    def update_folder_parent(self, folder_id: int, new_parent_id: int) -> bool:
        """Move a folder to a new parent folder"""
        return self._folders.update_parent(folder_id, new_parent_id)

    def get_descendant_folder_ids(self, folder_id: int) -> List[int]:
        """
        Get all descendant folder IDs for a folder (recursive)

        Args:
            folder_id: Parent folder ID

        Returns:
            List of all descendant folder IDs (children, grandchildren, etc.)
        """
        descendant_ids = []
        all_folders = self._folders.get_all()

        def collect_descendants(parent_id: int):
            for folder in all_folders:
                if folder.get('parent_id') == parent_id:
                    child_id = folder.get('id')
                    if child_id:
                        descendant_ids.append(child_id)
                        collect_descendants(child_id)

        collect_descendants(folder_id)
        return descendant_ids

    # ==================== ASSET OPERATIONS (delegates to AssetRepository) ====================

    def add_asset(self, asset_data: Dict[str, Any]) -> Optional[int]:
        """Add asset to database"""
        return self._assets.add(asset_data)

    def asset_name_exists(self, name: str, folder_id: Optional[int] = None,
                          exclude_uuid: Optional[str] = None) -> bool:
        """Check if an asset with the given name already exists"""
        return self._assets.name_exists(name, folder_id, exclude_uuid)

    def get_asset_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get asset by UUID"""
        return self._assets.get_by_uuid(uuid)

    def get_all_assets(self, folder_id: Optional[int] = None,
                       asset_type: Optional[str] = None,
                       include_retired: bool = False) -> List[Dict[str, Any]]:
        """Get all assets, optionally filtered.

        Args:
            folder_id: Optional folder ID filter
            asset_type: Optional asset type filter
            include_retired: If True, include retired assets (default: False)

        Returns:
            List of asset dicts
        """
        return self._assets.get_all(folder_id, asset_type, include_retired)

    def update_asset(self, uuid: str, updates: Dict[str, Any]) -> bool:
        """Update asset metadata"""
        return self._assets.update(uuid, updates)

    def delete_asset(self, uuid: str) -> bool:
        """Delete asset by UUID"""
        result = self._assets.delete(uuid)
        return result

    def search_assets(self, query: str) -> List[Dict[str, Any]]:
        """Search assets by name or description"""
        return self._assets.search(query)

    def get_asset_count(self, folder_id: Optional[int] = None,
                        asset_type: Optional[str] = None) -> int:
        """Get count of assets"""
        return self._assets.get_count(folder_id, asset_type)

    # ==================== USER FEATURES (delegates to AssetRepository) ====================

    def toggle_favorite(self, uuid: str) -> bool:
        """Toggle favorite status for an asset"""
        return self._assets.toggle_favorite(uuid)

    def set_favorite(self, uuid: str, is_favorite: bool) -> bool:
        """Set favorite status for an asset"""
        return self._assets.set_favorite(uuid, is_favorite)

    def get_favorite_assets(self) -> List[Dict[str, Any]]:
        """Get all favorite assets"""
        return self._assets.get_favorites()

    def update_last_viewed(self, uuid: str) -> bool:
        """Update last viewed timestamp for an asset"""
        return self._assets.update_last_viewed(uuid)

    def update_asset_last_used(self, uuid: str) -> bool:
        """Alias for update_last_viewed"""
        return self._assets.update_last_viewed(uuid)

    def get_recent_assets(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recently viewed assets"""
        return self._assets.get_recent(limit)

    def get_all_tags(self) -> List[str]:
        """Get all unique tags used across all assets"""
        return self._assets.get_all_tags()

    def get_all_asset_types(self) -> List[str]:
        """Get all unique asset types used"""
        return self._assets.get_all_types()

    # ==================== STATUS MANAGEMENT ====================

    def set_asset_status(self, uuid: str, status: str) -> bool:
        """Set lifecycle status for an asset (wip, review, approved, deprecated, archived)"""
        return self._assets.set_status(uuid, status)

    def get_assets_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all assets with a specific status"""
        return self._assets.get_by_status(status)

    def get_all_statuses(self) -> List[str]:
        """Get all unique statuses used in the library"""
        return self._assets.get_all_statuses()

    # ==================== VERSION MANAGEMENT ====================

    def get_asset_versions(self, version_group_id: str) -> List[Dict[str, Any]]:
        """Get all versions of an asset by its version group ID"""
        return self._assets.get_versions(version_group_id)

    def get_latest_asset_version(self, version_group_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest version of an asset"""
        return self._assets.get_latest_version(version_group_id)

    def create_asset_version(self, version_group_id: str, asset_data: Dict[str, Any]) -> Optional[int]:
        """Create a new version of an existing asset"""
        return self._assets.create_new_version(version_group_id, asset_data)

    def set_asset_as_latest(self, uuid: str) -> bool:
        """Set a specific version as the latest version"""
        return self._assets.set_as_latest(uuid)

    def promote_asset_to_latest(self, uuid: str) -> bool:
        """Promote a version to be the latest (unsets current latest)"""
        return self._assets.promote_to_latest(uuid)

    def demote_asset_from_latest(self, uuid: str) -> bool:
        """Demote a version from latest status"""
        return self._assets.demote_from_latest(uuid)

    def update_version_notes(self, uuid: str, notes: str) -> bool:
        """Update version notes (changelog) for an asset version"""
        return self._assets.update(uuid, {'version_notes': notes})

    def publish_asset_version(self, uuid: str, published_by: str = "") -> bool:
        """Mark version as published/approved with timestamp and lock it"""
        return self._assets.publish_version(uuid, published_by)

    def lock_asset_version(self, uuid: str) -> bool:
        """Make asset version immutable (locked from changes)"""
        return self._assets.lock_version(uuid)

    def unlock_asset_version(self, uuid: str) -> bool:
        """Unlock asset version (allow changes again)"""
        return self._assets.unlock_version(uuid)

    def is_asset_immutable(self, uuid: str) -> bool:
        """Check if asset version is immutable"""
        return self._assets.is_immutable(uuid)

    def get_version_history(self, version_group_id: str) -> List[Dict[str, Any]]:
        """Get full version history with cold storage status"""
        return self._assets.get_version_history(version_group_id)

    def get_previous_latest_version(self, version_group_id: str, current_uuid: str) -> Optional[Dict[str, Any]]:
        """Get the previous latest version for rollback scenarios"""
        return self._assets.get_previous_latest(version_group_id, current_uuid)

    def set_asset_representation_type(self, uuid: str, rep_type: str) -> bool:
        """Set representation type for an asset (model, lookdev, rig, final)"""
        return self._assets.set_representation_type(uuid, rep_type)

    def get_assets_by_representation(self, rep_type: str, folder_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get assets by representation type"""
        return self._assets.get_by_representation(rep_type, folder_id)

    def get_latest_non_cold_assets(self) -> List[Dict[str, Any]]:
        """Get latest versions of assets not in cold storage"""
        return self._assets.get_latest_non_cold_assets()

    # ==================== REPRESENTATION DESIGNATIONS ====================

    def get_representation_designation(self, version_group_id: str, variant_name: str = 'Base'):
        """Get proxy/render designation for an asset variant."""
        return self._assets.get_representation_designation(version_group_id, variant_name)

    def set_representation_designation(self, version_group_id: str, **kwargs) -> bool:
        """Set proxy/render designation for an asset variant."""
        return self._assets.set_representation_designation(version_group_id, **kwargs)

    def clear_representation_designation(self, version_group_id: str, variant_name: str = 'Base') -> bool:
        """Clear proxy/render designation for an asset variant."""
        return self._assets.clear_representation_designation(version_group_id, variant_name)

    def get_all_representation_designations(self, version_group_id=None):
        """Get all representation designations."""
        return self._assets.get_all_representation_designations(version_group_id)

    def update_render_designation_path(self, version_group_id: str, variant_name: str,
                                        render_version_uuid: str, render_version_label: str,
                                        render_blend_path: str) -> bool:
        """Update render designation path (for auto-update on new version)."""
        return self._assets.update_render_designation_path(
            version_group_id, variant_name,
            render_version_uuid, render_version_label, render_blend_path
        )

    # ==================== CUSTOM PROXIES ====================

    def get_custom_proxies(self, version_group_id: str, variant_name: str = 'Base'):
        """Get all custom proxies for an asset variant."""
        return self._assets.get_custom_proxies(version_group_id, variant_name)

    def get_custom_proxy_by_uuid(self, proxy_uuid: str):
        """Get a custom proxy by UUID."""
        return self._assets.get_custom_proxy_by_uuid(proxy_uuid)

    def add_custom_proxy(self, proxy_data) -> bool:
        """Add a custom proxy record."""
        return self._assets.add_custom_proxy(proxy_data)

    def delete_custom_proxy(self, proxy_uuid: str) -> bool:
        """Delete a custom proxy record."""
        return self._assets.delete_custom_proxy(proxy_uuid)

    def get_custom_proxy_count(self, version_group_id: str, variant_name: str = 'Base') -> int:
        """Get count of custom proxies for an asset variant."""
        return self._assets.get_custom_proxy_count(version_group_id, variant_name)

    def get_next_custom_proxy_version(self, version_group_id: str, variant_name: str = 'Base') -> int:
        """Get next proxy version number."""
        return self._assets.get_next_custom_proxy_version(version_group_id, variant_name)

    # ==================== VARIANT MANAGEMENT ====================

    def get_variants(self, asset_id: str) -> List[Dict[str, Any]]:
        """Get all variants of an asset by its asset_id"""
        return self._assets.get_variants(asset_id)

    def get_variant_versions(self, asset_id: str, variant_name: str) -> List[Dict[str, Any]]:
        """Get all versions within a specific variant"""
        return self._assets.get_variant_versions(asset_id, variant_name)

    def get_latest_variant_version(self, asset_id: str, variant_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest version of a specific variant"""
        return self._assets.get_latest_variant_version(asset_id, variant_name)

    def create_new_variant(self, source_uuid: str, new_variant_name: str,
                           asset_data: Dict[str, Any],
                           variant_set: Optional[str] = None) -> Optional[int]:
        """Create a new variant from an existing version"""
        return self._assets.create_new_variant(source_uuid, new_variant_name, asset_data, variant_set)

    def get_all_asset_ids(self) -> List[str]:
        """Get all unique asset_ids in the library"""
        return self._assets.get_all_asset_ids()

    def get_variant_sets(self, asset_id: str) -> List[str]:
        """Get all variant sets used by variants of an asset"""
        return self._assets.get_variant_sets(asset_id)

    def get_variant_counts(self) -> Dict[str, int]:
        """Get variant counts for all asset_ids (excluding Base)"""
        return self._assets.get_variant_counts()

    # ==================== COLD STORAGE ====================

    def get_cold_assets(self) -> List[Dict[str, Any]]:
        """Get all assets currently in cold storage"""
        return self._assets.get_cold_assets()

    def get_non_cold_assets(self) -> List[Dict[str, Any]]:
        """Get all assets not in cold storage (hot/active)"""
        return self._assets.get_non_cold_assets()

    # ==================== TAG OPERATIONS (delegates to TagRepository) ====================

    def create_tag(self, name: str, color: Optional[str] = None) -> Optional[int]:
        """Create a new tag"""
        return self._tags.create(name, color)

    def get_tag_by_id(self, tag_id: int) -> Optional[Dict[str, Any]]:
        """Get tag by ID"""
        return self._tags.get_by_id(tag_id)

    def get_tag_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get tag by name"""
        return self._tags.get_by_name(name)

    def get_all_tags_v2(self) -> List[Dict[str, Any]]:
        """Get all tags (new tag system with colors)"""
        return self._tags.get_all()

    def update_tag(self, tag_id: int, name: Optional[str] = None, color: Optional[str] = None) -> bool:
        """Update a tag"""
        return self._tags.update(tag_id, name, color)

    def delete_tag(self, tag_id: int) -> bool:
        """Delete a tag"""
        return self._tags.delete(tag_id)

    def get_or_create_tag(self, name: str, color: Optional[str] = None) -> Optional[int]:
        """Get existing tag or create new one"""
        return self._tags.get_or_create(name, color)

    def add_tag_to_asset(self, asset_uuid: str, tag_id: int) -> bool:
        """Add a tag to an asset"""
        return self._tags.add_tag_to_asset(asset_uuid, tag_id)

    def remove_tag_from_asset(self, asset_uuid: str, tag_id: int) -> bool:
        """Remove a tag from an asset"""
        return self._tags.remove_tag_from_asset(asset_uuid, tag_id)

    def get_asset_tags(self, asset_uuid: str) -> List[Dict[str, Any]]:
        """Get all tags for an asset"""
        return self._tags.get_asset_tags(asset_uuid)

    def set_asset_tags(self, asset_uuid: str, tag_ids: List[int]) -> bool:
        """Set all tags for an asset (replaces existing)"""
        return self._tags.set_asset_tags(asset_uuid, tag_ids)

    def get_assets_by_tag(self, tag_id: int) -> List[str]:
        """Get all asset UUIDs with a specific tag"""
        return self._tags.get_assets_by_tag(tag_id)

    def get_assets_by_tags(self, tag_ids: List[int], match_all: bool = False) -> List[str]:
        """Get asset UUIDs matching tag criteria"""
        return self._tags.get_assets_by_tags(tag_ids, match_all)

    def get_tags_with_counts(self) -> List[Dict[str, Any]]:
        """Get all tags with their usage counts"""
        return self._tags.get_tags_with_counts()

    def search_tags(self, query: str) -> List[Dict[str, Any]]:
        """Search tags by name"""
        return self._tags.search_tags(query)

    # ==================== ASSET-FOLDER OPERATIONS (delegates to AssetFolderRepository) ====================

    def add_asset_to_folder(self, asset_uuid: str, folder_id: int) -> bool:
        """Add an asset to a folder (multi-folder membership)"""
        return self._asset_folders.add_asset_to_folder(asset_uuid, folder_id)

    def remove_asset_from_folder(self, asset_uuid: str, folder_id: int) -> bool:
        """Remove an asset from a folder"""
        return self._asset_folders.remove_asset_from_folder(asset_uuid, folder_id)

    def get_asset_folders(self, asset_uuid: str) -> List[Dict[str, Any]]:
        """Get all folders for an asset"""
        return self._asset_folders.get_asset_folders(asset_uuid)

    def set_asset_folders(self, asset_uuid: str, folder_ids: List[int]) -> bool:
        """Set all folders for an asset (replaces existing)"""
        return self._asset_folders.set_asset_folders(asset_uuid, folder_ids)

    def get_assets_in_folder(self, folder_id: int) -> List[str]:
        """Get all asset UUIDs in a specific folder"""
        return self._asset_folders.get_assets_in_folder(folder_id)

    def get_assets_in_folders(self, folder_ids: List[int], match_all: bool = False) -> List[str]:
        """Get asset UUIDs in specified folders"""
        return self._asset_folders.get_assets_in_folders(folder_ids, match_all)

    def get_folder_asset_counts(self) -> Dict[int, int]:
        """Get asset count for each folder (multi-folder system)"""
        return self._asset_folders.get_folder_asset_counts()

    def migrate_asset_to_multi_folder(self, asset_uuid: str, legacy_folder_id: int) -> bool:
        """Migrate asset's legacy folder_id to multi-folder system"""
        return self._asset_folders.migrate_legacy_folder_id(asset_uuid, legacy_folder_id)

    def copy_folders_to_asset(self, source_uuid: str, target_uuid: str) -> bool:
        """Copy folder memberships from one asset to another"""
        return self._asset_folders.copy_folders_to_asset(source_uuid, target_uuid)

    # ==================== DATABASE MAINTENANCE (delegates to DatabaseMaintenance) ====================

    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics for status display."""
        return self._maintenance.get_database_stats()

    def run_integrity_check(self) -> Tuple[bool, str]:
        """Run database integrity check."""
        return self._maintenance.run_integrity_check()

    def optimize_database(self) -> Tuple[int, int]:
        """Optimize database by running VACUUM."""
        return self._maintenance.optimize_database()

    def get_current_schema_version(self) -> int:
        """Get current schema version from database."""
        return self._maintenance.get_current_schema_version()

    def create_backup(self) -> Path:
        """Create a backup of the database."""
        return self._maintenance.create_backup()

    def get_backups(self) -> List[Dict[str, Any]]:
        """Get list of existing backups."""
        return self._maintenance.get_backups()

    def delete_backup(self, backup_path: Path) -> bool:
        """Delete a backup file."""
        return self._maintenance.delete_backup(backup_path)

    def run_schema_upgrade(self) -> Tuple[bool, str]:
        """Run schema upgrade (migrations)."""
        return self._maintenance.run_schema_upgrade(self._schema_manager)

    # ==================== ASSET FILE OPERATIONS (delegates to AssetFileOps) ====================

    def rename_asset(self, uuid: str, new_name: str) -> Tuple[bool, str]:
        """Rename an asset with atomic filesystem operations and rollback support."""
        return self._file_ops.rename_asset(uuid, new_name)

    def move_asset_to_folder(self, asset_uuid: str, target_folder_id: Optional[int]) -> Tuple[bool, str]:
        """Move asset to a different folder with physical file relocation."""
        return self._file_ops.move_asset_to_folder(asset_uuid, target_folder_id)

    # ==================== APP SETTINGS ====================

    def get_app_setting(self, key: str, default: str = "") -> str:
        """
        Get an application setting value.

        Args:
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value or default
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                'SELECT value FROM app_settings WHERE key = ?',
                (key,)
            )
            row = cursor.fetchone()
            if row:
                return row[0] or default
            return default
        except Exception as e:
            # Log the exception before returning default
            logger.warning(f"Failed to get app setting '{key}': {e}")
            return default

    def set_app_setting(self, key: str, value: str) -> bool:
        """
        Set an application setting value.

        Args:
            key: Setting key
            value: Setting value

        Returns:
            True if successful
        """
        conn = self._get_connection()
        try:
            conn.execute('''
                INSERT OR REPLACE INTO app_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
            conn.commit()
            return True
        except Exception as e:
            logger.warning(f"Failed to set app setting {key}: {e}")
            return False

    # ==================== AUDIT LOGGING (Studio Mode only) ====================

    @property
    def audit(self) -> AssetAudit:
        """Get the asset audit service for logging actions."""
        return self._asset_audit

    def log_audit_action(
        self,
        asset_uuid: str,
        action: str,
        details: dict = None,
        previous_value: str = None,
        new_value: str = None,
        source: str = 'desktop'
    ) -> Optional[int]:
        """
        Log an audit action for an asset.

        This is a convenience method that:
        - Auto-fills actor from current user
        - Auto-fills version info from asset

        Args:
            asset_uuid: UUID of the asset
            action: Action type (create, update, approve, etc.)
            details: Additional details dict
            previous_value: Value before change
            new_value: Value after change
            source: Source of action (desktop, blender, api)

        Returns:
            Log entry ID or None if disabled/failed
        """
        # Get asset info for context
        asset = self._assets.get_by_uuid(asset_uuid)
        version_group_id = asset.get('version_group_id') if asset else None
        version_label = asset.get('version_label') if asset else None
        variant_name = asset.get('variant_name', 'Base') if asset else 'Base'

        return self._asset_audit.log_action(
            asset_uuid=asset_uuid,
            action=action,
            version_group_id=version_group_id,
            version_label=version_label,
            variant_name=variant_name,
            details=details,
            previous_value=previous_value,
            new_value=new_value,
            source=source
        )

    def get_asset_audit_history(self, asset_uuid: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit history for an asset."""
        return self._asset_audit.get_asset_history(asset_uuid, limit)

    def get_audit_activity_summary(self, days: int = 30) -> Dict[str, Any]:
        """Get audit activity summary for dashboard."""
        return self._asset_audit.get_activity_summary(days)

    def close(self):
        """Close database connections"""
        if hasattr(self.local, 'connection') and self.local.connection:
            self.local.connection.close()
            self.local.connection = None
        self._assets.close()
        self._folders.close()
        self._tags.close()
        self._asset_folders.close()


# Singleton instance
_database_service_instance: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Get global DatabaseService singleton instance"""
    global _database_service_instance
    if _database_service_instance is None:
        _database_service_instance = DatabaseService()
    return _database_service_instance


__all__ = ['DatabaseService', 'get_database_service', 'VERSION_FEATURES']
