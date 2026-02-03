"""
AssetRepository - Asset CRUD operations

Pattern: Repository pattern for asset data access
Extracted from DatabaseService for separation of concerns.

Refactored to delegate to:
- AssetVersions: Version management
- AssetVariants: Variant management
- AssetFeatures: User features (favorites, recent)
- AssetColdStorage: Cold storage queries
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

from .base_repository import BaseRepository
from .repositories.asset_versions import AssetVersions
from .repositories.asset_variants import AssetVariants
from .repositories.asset_features import AssetFeatures
from .repositories.asset_cold_storage import AssetColdStorage
from .repositories.representation_designations import RepresentationDesignations
from .repositories.custom_proxies import CustomProxies
from .metadata_service import get_metadata_service
from ..events.entity_events import get_entity_event_bus
from ..config import Config


class AssetRepository(BaseRepository):
    """
    Repository for asset operations

    Handles core asset database operations:
    - Create, read, update, delete assets
    - Search and filtering
    - Status management

    Delegates to sub-modules for:
    - Version management (AssetVersions)
    - Variant management (AssetVariants)
    - User features (AssetFeatures)
    - Cold storage (AssetColdStorage)
    """

    # All metadata fields stored in EAV (during dual-write transition)
    # These are also still in columns for backward compatibility
    DYNAMIC_FIELDS = {
        # Core/Universal fields (all asset types)
        'polygon_count', 'material_count', 'has_materials', 'has_skeleton',
        'has_animations', 'file_size_mb',
        # Mesh extended
        'vertex_group_count', 'shape_key_count',
        # Type-specific fields
        'bone_count', 'control_count', 'has_facial_rig',  # rig
        'frame_start', 'frame_end', 'frame_rate', 'is_loop',  # animation
        'texture_maps', 'texture_resolution',  # material
        'light_type', 'light_count',  # light
        'light_power', 'light_color', 'light_shadow',  # light extended
        'light_spot_size', 'light_area_shape',  # light extended
        'camera_type', 'focal_length',  # camera
        'camera_sensor_width', 'camera_clip_start', 'camera_clip_end',  # camera extended
        'camera_dof_enabled', 'camera_ortho_scale',  # camera extended
        'collection_name', 'mesh_count', 'camera_count', 'armature_count',
        'has_nested_collections', 'nested_collection_count',  # collection
    }

    def __init__(self):
        """Initialize repository with sub-modules."""
        super().__init__()
        self._metadata_service = get_metadata_service()
        self._entity_event_bus = get_entity_event_bus()

        # Initialize sub-modules with callbacks
        self._versions = AssetVersions(
            get_connection=self._get_connection,
            transaction=self._transaction,
            get_by_uuid=self.get_by_uuid,
            update=self.update,
            add=self.add,
            row_to_dict=self._row_to_dict,
        )

        self._variants = AssetVariants(
            get_connection=self._get_connection,
            get_by_uuid=self.get_by_uuid,
            add=self.add,
            row_to_dict=self._row_to_dict,
        )

        self._features = AssetFeatures(
            get_connection=self._get_connection,
            transaction=self._transaction,
            row_to_dict=self._row_to_dict,
            parse_tags=self._parse_tags,
        )

        self._cold_storage = AssetColdStorage(
            get_connection=self._get_connection,
            row_to_dict=self._row_to_dict,
        )

        self._representations = RepresentationDesignations(
            get_connection=self._get_connection,
            transaction=self._transaction,
        )

        self._custom_proxies = CustomProxies(
            get_connection=self._get_connection,
            transaction=self._transaction,
        )

    def add(self, asset_data: Dict[str, Any]) -> Optional[int]:
        """
        Add asset to database

        Args:
            asset_data: Asset metadata dict with keys:
                - uuid (required)
                - name (required)
                - folder_id (required)
                - asset_type (required)
                - ... other optional fields

        Returns:
            Asset database ID or None on error
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                tags = asset_data.get('tags', [])
                tags_json = json.dumps(tags) if isinstance(tags, list) else tags

                now = datetime.now()

                # Handle versioning - use version_group_id as uuid if not provided
                version_group_id = asset_data.get('version_group_id') or asset_data.get('uuid')
                version = asset_data.get('version', 1)
                version_label = asset_data.get('version_label', f'v{version:03d}')

                # Handle variant system - use version_group_id as asset_id if not provided
                asset_id = asset_data.get('asset_id') or version_group_id
                variant_name = asset_data.get('variant_name', 'Base')
                variant_source_uuid = asset_data.get('variant_source_uuid')

                cursor.execute('''
                    INSERT INTO assets (
                        uuid, name, description, folder_id, asset_type,
                        usd_file_path, blend_backup_path, thumbnail_path, preview_path,
                        file_size_mb, has_materials, has_skeleton, has_animations,
                        polygon_count, material_count, tags, author, source_application,
                        status, version, version_label, version_group_id, is_latest,
                        asset_id, variant_name, variant_source_uuid,
                        created_date, modified_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    asset_data.get('uuid'),
                    asset_data.get('name'),
                    asset_data.get('description', ''),
                    asset_data.get('folder_id'),
                    asset_data.get('asset_type'),
                    asset_data.get('usd_file_path'),
                    asset_data.get('blend_backup_path'),
                    asset_data.get('thumbnail_path'),
                    asset_data.get('preview_path'),
                    asset_data.get('file_size_mb'),
                    asset_data.get('has_materials', 0),
                    asset_data.get('has_skeleton', 0),
                    asset_data.get('has_animations', 0),
                    asset_data.get('polygon_count'),
                    asset_data.get('material_count'),
                    tags_json,
                    asset_data.get('author', ''),
                    asset_data.get('source_application', 'Blender'),
                    asset_data.get('status', 'wip'),
                    version,
                    version_label,
                    version_group_id,
                    asset_data.get('is_latest', 1),
                    asset_id,
                    variant_name,
                    variant_source_uuid,
                    now,
                    now
                ))

                row_id = cursor.lastrowid

                # Note: EAV write moved outside transaction to avoid lock
                return row_id, asset_data.get('uuid')  # Return tuple for post-commit EAV write

        except Exception:
            return None, None

    def add(self, asset_data: Dict[str, Any]) -> Optional[int]:
        """
        Add asset to database

        Args:
            asset_data: Asset metadata dict with keys:
                - uuid (required)
                - name (required)
                - folder_id (required)
                - asset_type (required)
                - ... other optional fields

        Returns:
            Asset database ID or None on error
        """
        result = self._add_core(asset_data)
        if result is None:
            return None

        row_id, uuid = result
        if row_id is None:
            return None

        # Write dynamic fields to EAV (outside transaction to avoid lock)
        if row_id:
            self._write_dynamic_to_eav(uuid, asset_data)

        # Emit entity created event
        if row_id:
            try:
                self._entity_event_bus.emit_entity_created('asset', uuid)
            except Exception as e:
                logger.debug(f"Event emission failed for asset create: {e}")

        # Emit event for review auto-join (handled by ReviewService)
        version_group_id = asset_data.get('version_group_id') or asset_data.get('uuid')
        version_label = asset_data.get('version_label', f"v{asset_data.get('version', 1):03d}")
        variant_name = asset_data.get('variant_name', 'Base')

        if row_id and version_group_id:
            try:
                from ..events.event_bus import get_event_bus
                get_event_bus().asset_version_created.emit(
                    uuid,
                    version_label,
                    version_group_id,
                    variant_name
                )
            except Exception as e:
                logger.debug(f"Event emission failed for version create: {e}")

        return row_id

    def _add_core(self, asset_data: Dict[str, Any]) -> Optional[tuple]:
        """
        Core add operation - inserts into assets table.

        Returns:
            Tuple of (row_id, uuid) or (None, None) on error
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                tags = asset_data.get('tags', [])
                tags_json = json.dumps(tags) if isinstance(tags, list) else tags

                now = datetime.now()

                # Handle versioning - use version_group_id as uuid if not provided
                version_group_id = asset_data.get('version_group_id') or asset_data.get('uuid')
                version = asset_data.get('version', 1)
                version_label = asset_data.get('version_label', f'v{version:03d}')

                # Handle variant system - use version_group_id as asset_id if not provided
                asset_id = asset_data.get('asset_id') or version_group_id
                variant_name = asset_data.get('variant_name', 'Base')
                variant_source_uuid = asset_data.get('variant_source_uuid')

                cursor.execute('''
                    INSERT INTO assets (
                        uuid, name, description, folder_id, asset_type,
                        usd_file_path, blend_backup_path, thumbnail_path, preview_path,
                        file_size_mb, has_materials, has_skeleton, has_animations,
                        polygon_count, material_count, tags, author, source_application,
                        status, version, version_label, version_group_id, is_latest,
                        asset_id, variant_name, variant_source_uuid,
                        created_date, modified_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    asset_data.get('uuid'),
                    asset_data.get('name'),
                    asset_data.get('description', ''),
                    asset_data.get('folder_id'),
                    asset_data.get('asset_type'),
                    asset_data.get('usd_file_path'),
                    asset_data.get('blend_backup_path'),
                    asset_data.get('thumbnail_path'),
                    asset_data.get('preview_path'),
                    asset_data.get('file_size_mb'),
                    asset_data.get('has_materials', 0),
                    asset_data.get('has_skeleton', 0),
                    asset_data.get('has_animations', 0),
                    asset_data.get('polygon_count'),
                    asset_data.get('material_count'),
                    tags_json,
                    asset_data.get('author', ''),
                    asset_data.get('source_application', 'Blender'),
                    asset_data.get('status', 'wip'),
                    version,
                    version_label,
                    version_group_id,
                    asset_data.get('is_latest', 1),
                    asset_id,
                    variant_name,
                    variant_source_uuid,
                    now,
                    now
                ))

                row_id = cursor.lastrowid
                return row_id, asset_data.get('uuid')

        except Exception:
            return None, None

    def get_by_uuid(self, uuid: str, include_dynamic: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get asset by UUID with optional EAV metadata.

        Args:
            uuid: Asset UUID
            include_dynamic: Whether to include dynamic metadata from EAV storage

        Returns:
            Asset dict with merged column + EAV data, or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM assets WHERE uuid = ?', (uuid,))
        result = cursor.fetchone()

        if result:
            data = dict(result)
            data['tags'] = self._parse_tags(data.get('tags'))

            # Merge EAV metadata (EAV takes precedence over columns for dynamic fields)
            if include_dynamic:
                self._enrich_with_metadata(data)

            return data
        return None

    def name_exists(self, name: str, folder_id: Optional[int] = None,
                    exclude_uuid: Optional[str] = None) -> bool:
        """
        Check if an asset with the given name already exists.

        Args:
            name: Asset name to check
            folder_id: Optional folder to scope the check (None = global)
            exclude_uuid: Optional UUID to exclude (for updates)

        Returns:
            True if an asset with this name exists
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT 1 FROM assets WHERE name = ?"
        params = [name]

        if folder_id is not None:
            query += " AND folder_id = ?"
            params.append(folder_id)

        if exclude_uuid:
            query += " AND uuid != ?"
            params.append(exclude_uuid)

        query += " LIMIT 1"
        cursor.execute(query, params)

        return cursor.fetchone() is not None

    def get_all(self, folder_id: Optional[int] = None,
                asset_type: Optional[str] = None,
                include_retired: bool = False) -> List[Dict[str, Any]]:
        """Get all assets, optionally filtered by folder or type.

        Args:
            folder_id: Optional folder ID filter
            asset_type: Optional asset type filter
            include_retired: If True, include retired assets (default: False)

        Returns:
            List of asset dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM assets WHERE 1=1"
        params = []

        # Filter out retired assets by default
        if not include_retired:
            query += " AND (is_retired = 0 OR is_retired IS NULL)"

        if folder_id is not None:
            query += " AND folder_id = ?"
            params.append(folder_id)

        if asset_type is not None:
            query += " AND asset_type = ?"
            params.append(asset_type)

        query += " ORDER BY name"
        cursor.execute(query, params)

        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def update(self, uuid: str, updates: Dict[str, Any]) -> bool:
        """
        Update asset metadata.

        Writes to both column storage and EAV for dynamic fields (dual-write).
        """
        # Separate dynamic fields for EAV write
        dynamic_updates = {}
        column_updates = {}

        for key, value in updates.items():
            if key in self.DYNAMIC_FIELDS:
                dynamic_updates[key] = value
                # Still write to column as well during transition
                column_updates[key] = value
            else:
                column_updates[key] = value

        # Update columns and EAV atomically in same transaction
        success = False
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                if 'tags' in column_updates and isinstance(column_updates['tags'], list):
                    column_updates['tags'] = json.dumps(column_updates['tags'])

                # Check if modified_date column exists before adding it
                cursor.execute("PRAGMA table_info(assets)")
                columns = {col[1] for col in cursor.fetchall()}
                if 'modified_date' in columns:
                    column_updates['modified_date'] = datetime.now().isoformat()

                # Update columns
                if column_updates:
                    set_clause = ', '.join([f"{key} = ?" for key in column_updates.keys()])
                    values = list(column_updates.values())
                    values.append(uuid)

                    cursor.execute(
                        f'UPDATE assets SET {set_clause} WHERE uuid = ?',
                        values
                    )

                success = cursor.rowcount > 0

                # Write dynamic fields to EAV inside transaction for atomicity
                if success and dynamic_updates:
                    self._write_dynamic_to_eav(uuid, dynamic_updates, conn=conn)

        except Exception as e:
            return False

        # Emit entity updated event
        if success:
            try:
                self._entity_event_bus.emit_entity_updated('asset', uuid)
                # Also emit specific metadata changes if we have dynamic updates
                if dynamic_updates:
                    self._entity_event_bus.emit_metadata_values_changed(
                        'asset', uuid, dynamic_updates
                    )
            except Exception as e:
                logger.debug(f"Event emission failed for asset update: {e}")

        return success

    def delete(self, uuid: str) -> bool:
        """Delete asset by UUID and its EAV metadata."""
        deleted = False
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                # Temporarily disable foreign key checks to avoid constraint issues
                cursor.execute('PRAGMA foreign_keys = OFF')

                # Delete from asset_tags junction table
                try:
                    cursor.execute('DELETE FROM asset_tags WHERE asset_uuid = ?', (uuid,))
                except Exception as e:
                    logger.debug(f"Could not delete asset_tags for {uuid}: {e}")

                # Delete from asset_folders junction table
                try:
                    cursor.execute('DELETE FROM asset_folders WHERE asset_uuid = ?', (uuid,))
                except Exception as e:
                    logger.debug(f"Could not delete asset_folders for {uuid}: {e}")

                # Now delete the asset itself
                cursor.execute('DELETE FROM assets WHERE uuid = ?', (uuid,))
                deleted = cursor.rowcount > 0

                # Re-enable foreign key checks
                cursor.execute('PRAGMA foreign_keys = ON')
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False

        # Delete EAV metadata (outside transaction to avoid lock)
        if deleted:
            try:
                self._metadata_service.delete_entity_metadata(uuid)
            except Exception as e:
                logger.debug(f"EAV cleanup failed for {uuid}: {e}")

        # Emit entity deleted event
        if deleted:
            try:
                self._entity_event_bus.emit_entity_deleted('asset', uuid)
            except Exception as e:
                logger.debug(f"Event emission failed for asset delete: {e}")

        return deleted

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search assets by name, description, or tags"""
        conn = self._get_connection()
        cursor = conn.cursor()

        search_pattern = f"%{query}%"
        cursor.execute('''
            SELECT * FROM assets
            WHERE name LIKE ? OR description LIKE ? OR tags LIKE ?
            ORDER BY name
        ''', (search_pattern, search_pattern, search_pattern))

        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_count(self, folder_id: Optional[int] = None,
                  asset_type: Optional[str] = None) -> int:
        """Get count of assets"""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT COUNT(*) FROM assets WHERE 1=1"
        params = []

        if folder_id is not None:
            query += " AND folder_id = ?"
            params.append(folder_id)

        if asset_type is not None:
            query += " AND asset_type = ?"
            params.append(asset_type)

        cursor.execute(query, params)
        result = cursor.fetchone()
        return result[0] if result else 0

    # ==================== USER FEATURES (delegates to AssetFeatures) ====================

    def toggle_favorite(self, uuid: str) -> bool:
        """Toggle favorite status for an asset."""
        return self._features.toggle_favorite(uuid)

    def set_favorite(self, uuid: str, is_favorite: bool) -> bool:
        """Set favorite status for an asset."""
        return self._features.set_favorite(uuid, is_favorite)

    def get_favorites(self) -> List[Dict[str, Any]]:
        """Get all favorite assets."""
        return self._features.get_favorites()

    def update_last_viewed(self, uuid: str) -> bool:
        """Update last viewed timestamp for an asset."""
        return self._features.update_last_viewed(uuid)

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recently viewed assets."""
        return self._features.get_recent(limit)

    def get_all_tags(self) -> List[str]:
        """Get all unique tags used across all assets."""
        return self._features.get_all_tags()

    def get_all_types(self) -> List[str]:
        """Get all unique asset types used."""
        return self._features.get_all_types()

    # ==================== STATUS MANAGEMENT ====================

    # Valid status values (from Config.LIFECYCLE_STATUSES)
    VALID_STATUSES = list(Config.LIFECYCLE_STATUSES.keys())

    def set_status(self, uuid: str, status: str) -> bool:
        """Set lifecycle status for an asset"""
        if status not in self.VALID_STATUSES:
            return False
        return self.update(uuid, {'status': status})

    def get_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get assets by lifecycle status"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM assets WHERE status = ? ORDER BY name', (status,))
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_all_statuses(self) -> List[str]:
        """Get all unique statuses used"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT status FROM assets WHERE status IS NOT NULL ORDER BY status')
        return [row[0] for row in cursor.fetchall() if row[0]]

    # ==================== VERSION MANAGEMENT (delegates to AssetVersions) ====================

    def get_versions(self, version_group_id: str) -> List[Dict[str, Any]]:
        """Get all versions of an asset by version group ID."""
        return self._versions.get_versions(version_group_id)

    def get_latest_version(self, version_group_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest version of an asset."""
        return self._versions.get_latest_version(version_group_id)

    def create_new_version(self, version_group_id: str, asset_data: Dict[str, Any]) -> Optional[int]:
        """Create a new version of an existing asset."""
        return self._versions.create_new_version(version_group_id, asset_data)

    def set_as_latest(self, uuid: str) -> bool:
        """Set a specific version as the latest."""
        return self._versions.set_as_latest(uuid)

    # ==================== COLD STORAGE (delegates to AssetColdStorage) ====================

    def get_cold_assets(self) -> List[Dict[str, Any]]:
        """Get all assets in cold storage."""
        return self._cold_storage.get_cold_assets()

    def get_non_cold_assets(self) -> List[Dict[str, Any]]:
        """Get all assets not in cold storage (active/hot)."""
        return self._cold_storage.get_non_cold_assets()

    def get_latest_non_cold_assets(self) -> List[Dict[str, Any]]:
        """Get latest versions of assets not in cold storage."""
        return self._cold_storage.get_latest_non_cold_assets()

    # ==================== ADVANCED VERSION MANAGEMENT (delegates to AssetVersions) ====================

    def get_version_history(self, version_group_id: str) -> List[Dict[str, Any]]:
        """Get full version history with cold storage status."""
        return self._versions.get_version_history(version_group_id)

    def promote_to_latest(self, uuid: str) -> bool:
        """Promote a version to be the latest."""
        return self._versions.promote_to_latest(uuid)

    def demote_from_latest(self, uuid: str) -> bool:
        """Demote a version from latest (used when moving to cold storage)."""
        return self._versions.demote_from_latest(uuid)

    def publish_version(self, uuid: str, published_by: str = "") -> bool:
        """Mark version as published/approved with timestamp."""
        return self._versions.publish_version(uuid, published_by)

    def lock_version(self, uuid: str) -> bool:
        """Make version immutable (locked from changes)."""
        return self._versions.lock_version(uuid)

    def unlock_version(self, uuid: str) -> bool:
        """Unlock a version (allow changes again)."""
        return self._versions.unlock_version(uuid)

    def is_immutable(self, uuid: str) -> bool:
        """Check if a version is immutable."""
        return self._versions.is_immutable(uuid)

    def get_previous_latest(self, version_group_id: str, current_uuid: str) -> Optional[Dict[str, Any]]:
        """Get the previous latest version (for rollback scenarios)."""
        return self._versions.get_previous_latest(version_group_id, current_uuid)

    def set_representation_type(self, uuid: str, rep_type: str) -> bool:
        """Set representation type for an asset."""
        return self._versions.set_representation_type(uuid, rep_type)

    def get_by_representation(self, rep_type: str, folder_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get assets by representation type."""
        return self._versions.get_by_representation(rep_type, folder_id)

    # ==================== VARIANT MANAGEMENT (delegates to AssetVariants) ====================

    def get_variant_counts(self) -> Dict[str, int]:
        """Get variant counts for all asset_ids."""
        return self._variants.get_variant_counts()

    def get_variants(self, asset_id: str) -> List[Dict[str, Any]]:
        """Get all variants of an asset."""
        return self._variants.get_variants(asset_id)

    def get_variant_versions(self, asset_id: str, variant_name: str) -> List[Dict[str, Any]]:
        """Get all versions within a specific variant."""
        return self._variants.get_variant_versions(asset_id, variant_name)

    def get_latest_variant_version(self, asset_id: str, variant_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest version of a specific variant."""
        return self._variants.get_latest_variant_version(asset_id, variant_name)

    def create_new_variant(
        self,
        source_uuid: str,
        new_variant_name: str,
        asset_data: Dict[str, Any],
        variant_set: Optional[str] = None
    ) -> Optional[int]:
        """Create a new variant from an existing version."""
        return self._variants.create_new_variant(source_uuid, new_variant_name, asset_data, variant_set)

    def get_all_asset_ids(self) -> List[str]:
        """Get all unique asset_ids in the library."""
        return self._variants.get_all_asset_ids()

    def get_variant_sets(self, asset_id: str) -> List[str]:
        """Get all unique variant sets used by variants of an asset."""
        return self._variants.get_variant_sets(asset_id)

    # ==================== REPRESENTATION DESIGNATIONS (delegates to RepresentationDesignations) ====================

    def get_representation_designation(self, version_group_id: str, variant_name: str = 'Base'):
        """Get proxy/render designation for an asset variant."""
        return self._representations.get_designation(version_group_id, variant_name)

    def set_representation_designation(self, version_group_id: str, **kwargs) -> bool:
        """Set proxy/render designation for an asset variant."""
        return self._representations.set_designation(version_group_id, **kwargs)

    def clear_representation_designation(self, version_group_id: str, variant_name: str = 'Base') -> bool:
        """Clear proxy/render designation for an asset variant."""
        return self._representations.clear_designation(version_group_id, variant_name)

    def get_all_representation_designations(self, version_group_id=None):
        """Get all representation designations."""
        return self._representations.get_all_designations(version_group_id)

    def update_render_designation_path(self, version_group_id: str, variant_name: str,
                                        render_version_uuid: str, render_version_label: str,
                                        render_blend_path: str) -> bool:
        """Update render designation path (for auto-update on new version)."""
        return self._representations.update_render_path(
            version_group_id, variant_name,
            render_version_uuid, render_version_label, render_blend_path
        )

    # ==================== CUSTOM PROXIES ====================

    def get_custom_proxies(self, version_group_id: str, variant_name: str = 'Base'):
        """Get all custom proxies for an asset variant."""
        return self._custom_proxies.get_proxies(version_group_id, variant_name)

    def get_custom_proxy_by_uuid(self, proxy_uuid: str):
        """Get a custom proxy by UUID."""
        return self._custom_proxies.get_proxy_by_uuid(proxy_uuid)

    def add_custom_proxy(self, proxy_data: Dict[str, Any]) -> bool:
        """Add a custom proxy record."""
        return self._custom_proxies.add_proxy(proxy_data)

    def delete_custom_proxy(self, proxy_uuid: str) -> bool:
        """Delete a custom proxy record."""
        return self._custom_proxies.delete_proxy(proxy_uuid)

    def get_custom_proxy_count(self, version_group_id: str, variant_name: str = 'Base') -> int:
        """Get count of custom proxies for an asset variant."""
        return self._custom_proxies.get_proxy_count(version_group_id, variant_name)

    def get_next_custom_proxy_version(self, version_group_id: str, variant_name: str = 'Base') -> int:
        """Get next proxy version number."""
        return self._custom_proxies.get_next_proxy_version(version_group_id, variant_name)

    # ==================== HELPERS ====================

    def _parse_tags(self, tags_json: Optional[str]) -> List[str]:
        """Parse tags JSON string to list"""
        if not tags_json:
            return []
        try:
            tags = json.loads(tags_json)
            return tags if isinstance(tags, list) else []
        except Exception:
            return []

    def _row_to_dict(self, row, include_dynamic: bool = True) -> Dict[str, Any]:
        """
        Convert database row to dict with parsed tags and optional EAV metadata.

        Args:
            row: Database row
            include_dynamic: Whether to merge EAV metadata

        Returns:
            Dict with asset data
        """
        data = dict(row)
        data['tags'] = self._parse_tags(data.get('tags'))

        if include_dynamic:
            self._enrich_with_metadata(data)

        return data

    def _enrich_with_metadata(self, data: Dict[str, Any]) -> None:
        """
        Enrich asset dict with dynamic metadata from EAV storage.

        EAV values take precedence over column values for dynamic fields.
        This allows gradual migration from columns to EAV.

        Args:
            data: Asset dict to enrich (modified in place)
        """
        uuid = data.get('uuid')
        if not uuid:
            return

        try:
            eav_data = self._metadata_service.get_entity_metadata(uuid)
            if eav_data:
                # EAV values override column values for dynamic fields
                for field_name, value in eav_data.items():
                    if value is not None:
                        data[field_name] = value
        except Exception as e:
            # Don't fail the read if EAV lookup fails
            pass

    def _write_dynamic_to_eav(self, uuid: str, data: Dict[str, Any], conn=None) -> None:
        """
        Write dynamic fields to EAV storage.

        This is called during dual-write to ensure data is in both
        column and EAV storage during the transition period.

        Args:
            uuid: Asset UUID
            data: Dict containing field values (filters to DYNAMIC_FIELDS only)
            conn: Optional connection for participating in existing transaction
        """
        if not uuid:
            return

        # Filter to only dynamic fields with non-None values
        dynamic_data = {
            k: v for k, v in data.items()
            if k in self.DYNAMIC_FIELDS and v is not None
        }

        if not dynamic_data:
            return

        try:
            self._metadata_service.set_entity_metadata(uuid, 'asset', dynamic_data, conn=conn)
        except Exception as e:
            # Log but don't fail - column write already succeeded
            pass


__all__ = ['AssetRepository']
