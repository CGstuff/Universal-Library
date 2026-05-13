"""
CustomProxies - CRUD operations for artist-authored custom proxy geometry.

Handles:
- Querying custom proxies by version_group_id and variant
- Adding new custom proxy records
- Deleting custom proxy records (DB row + .blend/.glb/.json on disk)
- Version number management via the proxy_counters high-water-mark table:
  numbers are identity (p001, p002, ...) and never reused after deletion.
"""

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, Callable, List

logger = logging.getLogger(__name__)


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
        Allocate and return the next proxy version number for an asset variant.

        Reads + increments the high-water-mark counter in `proxy_counters`.
        The counter never decrements, so once a number is handed out it is
        never reused — even if the proxy carrying that number is later
        deleted. This makes labels (p001, p002, ...) stable identities.

        Side effect: increments the counter. Cancellations after this call
        will leave a "wasted" number, manifesting as a gap in the labels.
        That's acceptable per the design — gaps are fine, reuse is not.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name

        Returns:
            Next version number (1 for the first proxy of a new variant)
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                # Try to read existing counter
                cursor.execute('''
                    SELECT next_number FROM proxy_counters
                    WHERE version_group_id = ? AND variant_name = ?
                ''', (version_group_id, variant_name))
                row = cursor.fetchone()
                if row is not None:
                    next_num = int(row[0])
                    cursor.execute('''
                        UPDATE proxy_counters
                        SET next_number = next_number + 1
                        WHERE version_group_id = ? AND variant_name = ?
                    ''', (version_group_id, variant_name))
                else:
                    # First proxy for this variant — seed counter at 2,
                    # return 1 as the allocated number.
                    next_num = 1
                    cursor.execute('''
                        INSERT INTO proxy_counters
                            (version_group_id, variant_name, next_number)
                        VALUES (?, ?, 2)
                    ''', (version_group_id, variant_name))
                return next_num
        except Exception:
            logger.exception(
                "get_next_proxy_version failed for %s / %s",
                version_group_id, variant_name,
            )
            # Fallback so the caller doesn't crash. Picks a number that
            # might collide; the DB UNIQUE constraint will reject if so.
            return 1

    def add_proxy(self, proxy_data: Dict[str, Any]) -> bool:
        """
        Add a new custom proxy record.

        Args:
            proxy_data: Dict with keys matching custom_proxies columns.
                        New: `glb_path` for the proxy's preview .glb so the
                        app can render a 3D preview when this proxy is
                        selected.

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
                        blend_path, glb_path, thumbnail_path,
                        polygon_count, notes, created_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    proxy_data.get('glb_path'),
                    proxy_data.get('thumbnail_path'),
                    proxy_data.get('polygon_count'),
                    proxy_data.get('notes', ''),
                    datetime.now().isoformat(),
                ))
                return True
        except Exception:
            logger.exception("add_proxy failed for uuid=%s", proxy_data.get('uuid'))
            return False

    def delete_proxy(self, proxy_uuid: str) -> bool:
        """
        Delete a custom proxy: removes the DB row, plus the .blend, .glb,
        .json sidecar, and any thumbnail file on disk.

        File-cleanup is best-effort — a failure to delete one file doesn't
        block the DB delete or the other files. We log but don't raise so
        a partially-broken filesystem doesn't strand the user with an
        un-deletable proxy in the UI.

        The high-water counter is NOT decremented — labels stay stable
        per the project's design decision (see `proxy_counters`).

        Args:
            proxy_uuid: Custom proxy UUID

        Returns:
            True if a row was deleted (file cleanup status is separate).
        """
        # 1. Look up the row so we know which files to delete.
        proxy = self.get_proxy_by_uuid(proxy_uuid)
        if proxy is None:
            return False

        # 2. Delete the DB row first. If THIS fails the files survive
        # untouched, which is recoverable. The other order would leave
        # the DB pointing at deleted files — strictly worse.
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM custom_proxies WHERE uuid = ?',
                    (proxy_uuid,),
                )
                deleted = cursor.rowcount > 0
        except Exception:
            logger.exception("delete_proxy DB delete failed for uuid=%s", proxy_uuid)
            return False

        if not deleted:
            return False

        # 3. Clean up files on disk (best effort).
        for key in ('blend_path', 'glb_path', 'thumbnail_path'):
            path_str = proxy.get(key)
            if not path_str:
                continue
            self._unlink_quiet(Path(path_str))

        # 4. JSON sidecar lives next to the .blend with .json suffix.
        blend_path_str = proxy.get('blend_path')
        if blend_path_str:
            blend_path = Path(blend_path_str)
            sidecar = blend_path.with_suffix('.json')
            self._unlink_quiet(sidecar)

        return True

    @staticmethod
    def _unlink_quiet(path: Path) -> None:
        """Delete a file if it exists; never raise. Logs failures at debug."""
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError as e:
            logger.debug("unlink failed for %s: %s", path, e)

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
