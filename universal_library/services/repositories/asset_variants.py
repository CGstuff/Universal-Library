"""
AssetVariants - Variant management operations.

Handles:
- Variant queries
- Creating new variants
- Variant sets
- Variant counts
"""

import sqlite3
import uuid as uuid_module
from typing import List, Dict, Optional, Any, Callable


class AssetVariants:
    """
    Manages variant-related operations for assets.

    Variants allow multiple versions of an asset with different characteristics
    (e.g., Heavy_Armor, Light_Armor, etc.) that share the same asset_id.
    """

    def __init__(
        self,
        get_connection: Callable[[], sqlite3.Connection],
        get_by_uuid: Callable[[str], Optional[Dict[str, Any]]],
        add: Callable[[Dict[str, Any]], Optional[int]],
        row_to_dict: Callable,
    ):
        """
        Initialize with repository callbacks.

        Args:
            get_connection: Function to get database connection
            get_by_uuid: Function to get asset by UUID
            add: Function to add asset
            row_to_dict: Function to convert row to dict
        """
        self._get_connection = get_connection
        self._get_by_uuid = get_by_uuid
        self._add = add
        self._row_to_dict = row_to_dict

    def get_variant_counts(self) -> Dict[str, int]:
        """
        Get variant counts for all asset_ids.

        Returns:
            Dict mapping asset_id to variant count (excluding Base)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT asset_id, COUNT(DISTINCT variant_name) - 1 as variant_count
            FROM assets
            WHERE asset_id IS NOT NULL
            GROUP BY asset_id
            HAVING COUNT(DISTINCT variant_name) > 1
        ''')

        counts = {}
        for row in cursor.fetchall():
            counts[row[0]] = row[1]
        return counts

    def get_variants(self, asset_id: str) -> List[Dict[str, Any]]:
        """
        Get all variants of an asset.

        Args:
            asset_id: UUID shared across all variants of this asset

        Returns:
            List of dicts with variant info (variant_name, version_group_id, latest version)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT variant_name, version_group_id,
                   MAX(version) as max_version,
                   COUNT(*) as version_count
            FROM assets
            WHERE asset_id = ?
            GROUP BY variant_name, version_group_id
            ORDER BY variant_name
        ''', (asset_id,))

        variants = []
        for row in cursor.fetchall():
            variants.append({
                'variant_name': row[0],
                'version_group_id': row[1],
                'max_version': row[2],
                'version_count': row[3]
            })
        return variants

    def get_variant_versions(self, asset_id: str, variant_name: str) -> List[Dict[str, Any]]:
        """
        Get all versions within a specific variant.

        Args:
            asset_id: UUID shared across all variants
            variant_name: Name of the variant (e.g., 'Base', 'Heavy_Armor')

        Returns:
            List of asset dicts for this variant, ordered by version DESC
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM assets
            WHERE asset_id = ? AND variant_name = ?
            ORDER BY version DESC
        ''', (asset_id, variant_name))
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_latest_variant_version(self, asset_id: str, variant_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest version of a specific variant.

        Args:
            asset_id: UUID shared across all variants
            variant_name: Name of the variant

        Returns:
            Latest version asset dict or None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM assets
            WHERE asset_id = ? AND variant_name = ? AND is_latest = 1
            LIMIT 1
        ''', (asset_id, variant_name))
        result = cursor.fetchone()
        return self._row_to_dict(result) if result else None

    def create_new_variant(
        self,
        source_uuid: str,
        new_variant_name: str,
        asset_data: Dict[str, Any],
        variant_set: Optional[str] = None
    ) -> Optional[int]:
        """
        Create a new variant from an existing version.

        Args:
            source_uuid: UUID of the source version to branch from
            new_variant_name: Name for the new variant
            asset_data: Additional asset data (files, metadata)
            variant_set: Optional semantic grouping (Armor, Color, LOD, etc.)

        Returns:
            Database ID of the new variant's first version, or None on error
        """
        # Get source asset to inherit asset_id and provenance info
        source = self._get_by_uuid(source_uuid)
        if not source:
            return None

        asset_id = source.get('asset_id') or source.get('version_group_id')
        if not asset_id:
            return None

        # Generate new version_group_id for this variant
        new_version_group_id = str(uuid_module.uuid4())

        # Prepare new asset data with provenance tracking
        asset_data['asset_id'] = asset_id
        asset_data['variant_name'] = new_variant_name
        asset_data['variant_source_uuid'] = source_uuid
        asset_data['version_group_id'] = new_version_group_id
        asset_data['version'] = 1
        asset_data['version_label'] = 'v001'
        asset_data['is_latest'] = 1

        # Provenance fields - store source info for display
        asset_data['source_asset_name'] = source.get('name', 'Unknown')
        asset_data['source_version_label'] = source.get('version_label', 'v001')
        asset_data['variant_set'] = variant_set or asset_data.get('variant_set', 'Default')

        return self._add(asset_data)

    def get_all_asset_ids(self) -> List[str]:
        """
        Get all unique asset_ids in the library.

        Returns:
            List of asset_id UUIDs
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT asset_id FROM assets
            WHERE asset_id IS NOT NULL
            ORDER BY asset_id
        ''')
        return [row[0] for row in cursor.fetchall()]

    def get_variant_sets(self, asset_id: str) -> List[str]:
        """
        Get all unique variant sets used by variants of an asset.

        Args:
            asset_id: UUID of the asset family

        Returns:
            List of variant set names (e.g., ['Armor', 'Color', 'Default'])
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT variant_set FROM assets
            WHERE asset_id = ?
              AND variant_name != 'Base'
              AND variant_set IS NOT NULL
            ORDER BY variant_set
        ''', (asset_id,))
        return [row[0] for row in cursor.fetchall()]


__all__ = ['AssetVariants']
