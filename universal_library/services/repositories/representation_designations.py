"""
RepresentationDesignations - Proxy/render version designation operations.

Handles:
- Storing which version is designated as proxy vs render
- CRUD for designation records
- Query by version_group_id and variant
"""

import sqlite3
from datetime import datetime
from typing import Dict, Optional, Any, Callable, List
from contextlib import contextmanager


class RepresentationDesignations:
    """
    Manages proxy/render designation records.

    Each asset variant can have one proxy and one render designation
    pointing to specific archived versions.
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

    def get_designation(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> Optional[Dict[str, Any]]:
        """
        Get the proxy/render designation for an asset variant.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name (default 'Base')

        Returns:
            Dict with designation data or None if not set
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM representation_designations
            WHERE version_group_id = ? AND variant_name = ?
        ''', (version_group_id, variant_name))
        row = cursor.fetchone()
        return dict(row) if row else None

    def set_designation(
        self,
        version_group_id: str,
        variant_name: str = 'Base',
        proxy_version_uuid: Optional[str] = None,
        render_version_uuid: Optional[str] = None,
        proxy_version_label: Optional[str] = None,
        render_version_label: Optional[str] = None,
        proxy_blend_path: Optional[str] = None,
        render_blend_path: Optional[str] = None,
        proxy_source: Optional[str] = None,
    ) -> bool:
        """
        Set or update the proxy/render designation for an asset variant.

        Uses INSERT OR REPLACE to upsert based on the UNIQUE constraint.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name
            proxy_version_uuid: UUID of version designated as proxy (None = use v001 default)
            render_version_uuid: UUID of version designated as render (None = use latest default)
            proxy_version_label: Label like 'v001' for proxy
            render_version_label: Label like 'v003' for render
            proxy_blend_path: Path to .proxy.blend file
            render_blend_path: Path to .render.blend file
            proxy_source: 'version' or 'custom' to indicate proxy source type

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                # Check if proxy_source column exists
                cursor.execute("PRAGMA table_info(representation_designations)")
                columns = {col[1] for col in cursor.fetchall()}
                has_proxy_source = 'proxy_source' in columns

                if has_proxy_source:
                    cursor.execute('''
                        INSERT OR REPLACE INTO representation_designations (
                            version_group_id, variant_name,
                            proxy_version_uuid, render_version_uuid,
                            proxy_version_label, render_version_label,
                            proxy_blend_path, render_blend_path,
                            proxy_source, last_updated
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        version_group_id, variant_name,
                        proxy_version_uuid, render_version_uuid,
                        proxy_version_label, render_version_label,
                        proxy_blend_path, render_blend_path,
                        proxy_source or 'version',
                        datetime.now().isoformat(),
                    ))
                else:
                    cursor.execute('''
                        INSERT OR REPLACE INTO representation_designations (
                            version_group_id, variant_name,
                            proxy_version_uuid, render_version_uuid,
                            proxy_version_label, render_version_label,
                            proxy_blend_path, render_blend_path,
                            last_updated
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        version_group_id, variant_name,
                        proxy_version_uuid, render_version_uuid,
                        proxy_version_label, render_version_label,
                        proxy_blend_path, render_blend_path,
                        datetime.now().isoformat(),
                    ))
                return True
        except Exception as e:
            return False

    def clear_designation(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> bool:
        """
        Remove the proxy/render designation for an asset variant.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name

        Returns:
            True if a row was deleted
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM representation_designations
                    WHERE version_group_id = ? AND variant_name = ?
                ''', (version_group_id, variant_name))
                return cursor.rowcount > 0
        except Exception as e:
            return False

    def get_all_designations(
        self,
        version_group_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all designations, optionally filtered by version group.

        Args:
            version_group_id: Optional filter by version group

        Returns:
            List of designation dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if version_group_id:
            cursor.execute('''
                SELECT * FROM representation_designations
                WHERE version_group_id = ?
                ORDER BY variant_name
            ''', (version_group_id,))
        else:
            cursor.execute('''
                SELECT * FROM representation_designations
                ORDER BY version_group_id, variant_name
            ''')

        return [dict(row) for row in cursor.fetchall()]

    def update_render_path(
        self,
        version_group_id: str,
        variant_name: str,
        render_version_uuid: str,
        render_version_label: str,
        render_blend_path: str,
    ) -> bool:
        """
        Update just the render designation (used when a new version auto-updates render).

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name
            render_version_uuid: New render version UUID
            render_version_label: New render version label
            render_blend_path: New path to .render.blend

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE representation_designations
                    SET render_version_uuid = ?,
                        render_version_label = ?,
                        render_blend_path = ?,
                        last_updated = ?
                    WHERE version_group_id = ? AND variant_name = ?
                ''', (
                    render_version_uuid, render_version_label,
                    render_blend_path, datetime.now().isoformat(),
                    version_group_id, variant_name,
                ))
                return cursor.rowcount > 0
        except Exception as e:
            return False


__all__ = ['RepresentationDesignations']
