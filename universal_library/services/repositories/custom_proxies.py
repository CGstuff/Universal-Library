"""
CustomProxies - CRUD operations for artist-authored custom proxy geometry.

Handles:
- Querying custom proxies by version_group_id and variant
- Adding new custom proxy records
- Deleting custom proxy records
- Version number management (p001, p002, etc.)
"""

import sqlite3
from datetime import datetime
from typing import Dict, Optional, Any, Callable, List


class CustomProxies:
    """
    Manages custom proxy records in the custom_proxies table.

    Custom proxies are hand-modeled lightweight representations
    that artists create in Blender and save alongside library assets.
    """

    def __init__(
        self,
        get_connection: Callable[[], sqlite3.Connection],
        transaction: Callable,
    ):
        """
        Initialize with repository callbacks.

        Args:
            get_connection: Function to get database connection
            transaction: Context manager for transactions
        """
        self._get_connection = get_connection
        self._transaction = transaction

    def get_proxies(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> List[Dict[str, Any]]:
        """
        Get all custom proxies for an asset variant.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name (default 'Base')

        Returns:
            List of custom proxy dicts, sorted by proxy_version ascending
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM custom_proxies
            WHERE version_group_id = ? AND variant_name = ?
            ORDER BY proxy_version ASC
        ''', (version_group_id, variant_name))
        return [dict(row) for row in cursor.fetchall()]

    def get_proxy_by_uuid(self, proxy_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get a single custom proxy by UUID.

        Args:
            proxy_uuid: Custom proxy UUID

        Returns:
            Custom proxy dict or None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM custom_proxies WHERE uuid = ?',
            (proxy_uuid,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_next_proxy_version(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> int:
        """
        Get the next proxy version number for an asset variant.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name

        Returns:
            Next version number (1 if no proxies exist)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT MAX(proxy_version) FROM custom_proxies
            WHERE version_group_id = ? AND variant_name = ?
        ''', (version_group_id, variant_name))
        row = cursor.fetchone()
        max_version = row[0] if row and row[0] is not None else 0
        return max_version + 1

    def add_proxy(self, proxy_data: Dict[str, Any]) -> bool:
        """
        Add a new custom proxy record.

        Args:
            proxy_data: Dict with keys matching custom_proxies columns

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO custom_proxies (
                        uuid, version_group_id, variant_name,
                        asset_id, asset_name, asset_type,
                        proxy_version, proxy_label,
                        blend_path, thumbnail_path,
                        polygon_count, notes, created_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    proxy_data['uuid'],
                    proxy_data['version_group_id'],
                    proxy_data.get('variant_name', 'Base'),
                    proxy_data['asset_id'],
                    proxy_data['asset_name'],
                    proxy_data.get('asset_type', 'mesh'),
                    proxy_data['proxy_version'],
                    proxy_data['proxy_label'],
                    proxy_data.get('blend_path'),
                    proxy_data.get('thumbnail_path'),
                    proxy_data.get('polygon_count'),
                    proxy_data.get('notes', ''),
                    datetime.now().isoformat(),
                ))
                return True
        except Exception as e:
            return False

    def delete_proxy(self, proxy_uuid: str) -> bool:
        """
        Delete a custom proxy record by UUID.

        Args:
            proxy_uuid: Custom proxy UUID

        Returns:
            True if a row was deleted
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM custom_proxies WHERE uuid = ?',
                    (proxy_uuid,)
                )
                return cursor.rowcount > 0
        except Exception as e:
            return False

    def get_proxy_count(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> int:
        """
        Get the number of custom proxies for an asset variant.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name

        Returns:
            Number of custom proxies
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM custom_proxies
            WHERE version_group_id = ? AND variant_name = ?
        ''', (version_group_id, variant_name))
        row = cursor.fetchone()
        return row[0] if row else 0


__all__ = ['CustomProxies']
