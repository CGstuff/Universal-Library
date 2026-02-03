"""
MetadataMigration - Migrates type-specific columns to EAV storage.

Handles the one-time migration of existing asset metadata from
column-based storage to the entity_metadata EAV table.
"""

from typing import List, Dict, Any, Optional
from .base_repository import BaseRepository
from .metadata_service import get_metadata_service


class MetadataMigration(BaseRepository):
    """
    Migrates existing column data to entity_metadata EAV storage.

    This is a one-time migration that copies values from type-specific
    columns in the assets table to the entity_metadata table.

    Usage:
        migration = MetadataMigration()
        stats = migration.migrate_all_assets()
    """

    # Fields to migrate from assets table columns to EAV
    FIELDS_TO_MIGRATE = {
        # Core/Universal fields (all asset types)
        'polygon_count': 'integer',
        'material_count': 'integer',
        'has_materials': 'boolean',
        'has_skeleton': 'boolean',
        'has_animations': 'boolean',
        'file_size_mb': 'real',
        # Rig fields
        'bone_count': 'integer',
        'control_count': 'integer',
        'has_facial_rig': 'boolean',
        # Animation fields
        'frame_start': 'integer',
        'frame_end': 'integer',
        'frame_rate': 'real',
        'is_loop': 'boolean',
        # Material fields
        'texture_maps': 'json',
        'texture_resolution': 'string',
        # Light fields
        'light_type': 'string',
        'light_count': 'integer',
        # Camera fields
        'camera_type': 'string',
        'focal_length': 'real',
        # Collection fields
        'collection_name': 'string',
        'mesh_count': 'integer',
        'camera_count': 'integer',
        'armature_count': 'integer',
        'has_nested_collections': 'boolean',
        'nested_collection_count': 'integer',
    }

    def __init__(self):
        super().__init__()
        self._metadata_service = get_metadata_service()

    def migrate_all_assets(self, batch_size: int = 100) -> Dict[str, int]:
        """
        Migrate all assets from column storage to EAV.

        Args:
            batch_size: Number of assets to process per batch

        Returns:
            Statistics dict with migration counts
        """
        stats = {
            'assets_total': 0,
            'assets_migrated': 0,
            'fields_migrated': 0,
            'assets_skipped': 0,
            'errors': 0
        }

        conn = self._get_connection()
        cursor = conn.cursor()

        # Get total count
        cursor.execute('SELECT COUNT(*) FROM assets')
        stats['assets_total'] = cursor.fetchone()[0]

        if stats['assets_total'] == 0:
            return stats

        # Process in batches
        offset = 0
        while offset < stats['assets_total']:
            cursor.execute('''
                SELECT uuid, asset_type,
                       polygon_count, material_count, has_materials, has_skeleton, has_animations, file_size_mb,
                       bone_count, control_count, has_facial_rig,
                       frame_start, frame_end, frame_rate, is_loop,
                       texture_maps, texture_resolution,
                       light_type, light_count,
                       camera_type, focal_length,
                       collection_name, mesh_count, camera_count, armature_count,
                       has_nested_collections, nested_collection_count
                FROM assets
                LIMIT ? OFFSET ?
            ''', (batch_size, offset))

            rows = cursor.fetchall()
            for row in rows:
                result = self._migrate_asset(dict(row))
                if result['success']:
                    stats['assets_migrated'] += 1
                    stats['fields_migrated'] += result['fields_count']
                elif result['skipped']:
                    stats['assets_skipped'] += 1
                else:
                    stats['errors'] += 1

            offset += batch_size

        return stats

    def _migrate_asset(self, asset_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate a single asset's metadata.

        Args:
            asset_data: Asset row data

        Returns:
            Result dict with success, skipped, fields_count
        """
        uuid = asset_data.get('uuid')
        if not uuid:
            return {'success': False, 'skipped': False, 'fields_count': 0}

        # Check if already migrated (has any metadata in EAV)
        existing = self._metadata_service.get_entity_metadata(uuid)
        if existing:
            return {'success': False, 'skipped': True, 'fields_count': 0}

        # Collect non-null values to migrate
        metadata = {}
        for field_name, field_type in self.FIELDS_TO_MIGRATE.items():
            value = asset_data.get(field_name)
            if value is not None:
                # Handle booleans stored as integers
                if field_type == 'boolean':
                    value = bool(value)
                metadata[field_name] = value

        if not metadata:
            return {'success': False, 'skipped': True, 'fields_count': 0}

        # Save to EAV
        success = self._metadata_service.set_entity_metadata(uuid, 'asset', metadata)

        return {
            'success': success,
            'skipped': False,
            'fields_count': len(metadata) if success else 0
        }

    def migrate_single_asset(self, uuid: str) -> bool:
        """
        Migrate a single asset by UUID.

        Args:
            uuid: Asset UUID to migrate

        Returns:
            True if migrated successfully
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT uuid, asset_type,
                   polygon_count, material_count, has_materials, has_skeleton, has_animations, file_size_mb,
                   bone_count, control_count, has_facial_rig,
                   frame_start, frame_end, frame_rate, is_loop,
                   texture_maps, texture_resolution,
                   light_type, light_count,
                   camera_type, focal_length,
                   collection_name, mesh_count, camera_count, armature_count,
                   has_nested_collections, nested_collection_count
            FROM assets WHERE uuid = ?
        ''', (uuid,))

        row = cursor.fetchone()
        if not row:
            return False

        result = self._migrate_asset(dict(row))
        return result['success']

    def check_migration_status(self) -> Dict[str, Any]:
        """
        Check migration status for all assets.

        Returns:
            Status dict with counts of migrated/not migrated assets
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Total assets
        cursor.execute('SELECT COUNT(*) FROM assets')
        total = cursor.fetchone()[0]

        # Assets with EAV metadata
        cursor.execute('''
            SELECT COUNT(DISTINCT entity_uuid)
            FROM entity_metadata
            WHERE entity_type = 'asset'
        ''')
        migrated = cursor.fetchone()[0]

        # Assets with migrateable data (potential migration candidates)
        cursor.execute('''
            SELECT COUNT(*) FROM assets
            WHERE polygon_count IS NOT NULL
               OR material_count IS NOT NULL
               OR has_materials IS NOT NULL
               OR has_skeleton IS NOT NULL
               OR has_animations IS NOT NULL
               OR file_size_mb IS NOT NULL
               OR bone_count IS NOT NULL
               OR frame_start IS NOT NULL
               OR texture_maps IS NOT NULL
               OR light_type IS NOT NULL
               OR camera_type IS NOT NULL
               OR collection_name IS NOT NULL
        ''')
        has_type_data = cursor.fetchone()[0]

        return {
            'total_assets': total,
            'migrated_to_eav': migrated,
            'has_type_specific_data': has_type_data,
            'pending_migration': has_type_data - migrated if has_type_data > migrated else 0,
            'migration_complete': migrated >= has_type_data
        }

    def verify_migration(self, sample_size: int = 10) -> Dict[str, Any]:
        """
        Verify migration by comparing column and EAV values.

        Args:
            sample_size: Number of assets to verify

        Returns:
            Verification results
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get sample of assets with migrateable data
        cursor.execute('''
            SELECT uuid FROM assets
            WHERE polygon_count IS NOT NULL
               OR bone_count IS NOT NULL
               OR frame_start IS NOT NULL
               OR texture_maps IS NOT NULL
            LIMIT ?
        ''', (sample_size,))

        results = {
            'verified': 0,
            'mismatches': 0,
            'details': []
        }

        for row in cursor.fetchall():
            uuid = row[0]
            verification = self._verify_asset(uuid)
            if verification['match']:
                results['verified'] += 1
            else:
                results['mismatches'] += 1
                results['details'].append(verification)

        return results

    def _verify_asset(self, uuid: str) -> Dict[str, Any]:
        """Verify a single asset's migration."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get column values
        cursor.execute('''
            SELECT polygon_count, material_count, has_materials, has_skeleton, has_animations, file_size_mb,
                   bone_count, frame_start, frame_end, texture_maps
            FROM assets WHERE uuid = ?
        ''', (uuid,))
        row = cursor.fetchone()

        if not row:
            return {'uuid': uuid, 'match': False, 'error': 'Asset not found'}

        column_data = dict(row)

        # Get EAV values
        eav_data = self._metadata_service.get_entity_metadata(uuid)

        # Compare core fields and some type-specific fields
        mismatches = []
        for field in ['polygon_count', 'material_count', 'has_materials', 'has_skeleton', 'has_animations',
                      'file_size_mb', 'bone_count', 'frame_start', 'frame_end', 'texture_maps']:
            col_val = column_data.get(field)
            eav_val = eav_data.get(field)

            # Normalize None/missing
            if col_val is None and field not in eav_data:
                continue

            if col_val != eav_val:
                mismatches.append({
                    'field': field,
                    'column': col_val,
                    'eav': eav_val
                })

        return {
            'uuid': uuid,
            'match': len(mismatches) == 0,
            'mismatches': mismatches
        }


# Singleton instance
_metadata_migration: Optional[MetadataMigration] = None


def get_metadata_migration() -> MetadataMigration:
    """Get global MetadataMigration singleton instance."""
    global _metadata_migration
    if _metadata_migration is None:
        _metadata_migration = MetadataMigration()
    return _metadata_migration


def run_migration() -> Dict[str, int]:
    """
    Convenience function to run the full migration.

    Returns:
        Migration statistics
    """
    migration = get_metadata_migration()
    return migration.migrate_all_assets()


__all__ = ['MetadataMigration', 'get_metadata_migration', 'run_migration']
