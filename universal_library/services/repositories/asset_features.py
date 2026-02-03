"""
AssetFeatures - User feature operations.

Handles:
- Favorites management
- Recent assets tracking
- Tags queries
- Asset types queries
"""

import json
import sqlite3
from typing import List, Dict, Any, Callable


class AssetFeatures:
    """
    Manages user feature operations for assets.

    Includes favorites, recently viewed, and tag/type queries.
    """

    def __init__(
        self,
        get_connection: Callable[[], sqlite3.Connection],
        transaction: Callable,
        row_to_dict: Callable,
        parse_tags: Callable,
    ):
        """
        Initialize with repository callbacks.

        Args:
            get_connection: Function to get database connection
            transaction: Context manager for transactions
            row_to_dict: Function to convert row to dict
            parse_tags: Function to parse tags JSON
        """
        self._get_connection = get_connection
        self._transaction = transaction
        self._row_to_dict = row_to_dict
        self._parse_tags = parse_tags

    def toggle_favorite(self, uuid: str) -> bool:
        """Toggle favorite status for an asset."""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                cursor.execute('SELECT is_favorite FROM assets WHERE uuid = ?', (uuid,))
                result = cursor.fetchone()
                if not result:
                    return False

                new_status = 0 if result[0] == 1 else 1

                cursor.execute(
                    'UPDATE assets SET is_favorite = ?, modified_date = CURRENT_TIMESTAMP WHERE uuid = ?',
                    (new_status, uuid)
                )

                return cursor.rowcount > 0
        except Exception:
            return False

    def set_favorite(self, uuid: str, is_favorite: bool) -> bool:
        """Set favorite status for an asset."""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE assets SET is_favorite = ?, modified_date = CURRENT_TIMESTAMP WHERE uuid = ?',
                    (1 if is_favorite else 0, uuid)
                )
                return cursor.rowcount > 0
        except Exception:
            return False

    def get_favorites(self) -> List[Dict[str, Any]]:
        """Get all favorite assets."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM assets WHERE is_favorite = 1 ORDER BY name')
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def update_last_viewed(self, uuid: str) -> bool:
        """Update last viewed timestamp for an asset."""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE assets SET last_viewed_date = CURRENT_TIMESTAMP WHERE uuid = ?',
                    (uuid,)
                )
                return cursor.rowcount > 0
        except Exception:
            return False

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recently viewed assets."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM assets
            WHERE last_viewed_date IS NOT NULL
            ORDER BY last_viewed_date DESC
            LIMIT ?
        ''', (limit,))

        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_all_tags(self) -> List[str]:
        """Get all unique tags used across all assets."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT DISTINCT tags FROM assets WHERE tags IS NOT NULL AND tags != ""')

        all_tags = set()
        for row in cursor.fetchall():
            tags = self._parse_tags(row[0])
            all_tags.update(tags)

        return sorted(list(all_tags))

    def get_all_types(self) -> List[str]:
        """Get all unique asset types used."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT asset_type FROM assets WHERE asset_type IS NOT NULL ORDER BY asset_type')
        return [row[0] for row in cursor.fetchall()]


__all__ = ['AssetFeatures']
