"""
AssetColdStorage - Cold storage operations.

Handles:
- Querying cold storage assets
- Querying non-cold (active) assets
- Latest non-cold assets
"""

import sqlite3
from typing import List, Dict, Any, Callable


class AssetColdStorage:
    """
    Manages cold storage queries for assets.

    Cold storage allows archiving older versions to save space
    while keeping them accessible.
    """

    def __init__(
        self,
        get_connection: Callable[[], sqlite3.Connection],
        row_to_dict: Callable,
    ):
        """
        Initialize with repository callbacks.

        Args:
            get_connection: Function to get database connection
            row_to_dict: Function to convert row to dict
        """
        self._get_connection = get_connection
        self._row_to_dict = row_to_dict

    def get_cold_assets(self) -> List[Dict[str, Any]]:
        """Get all assets in cold storage."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM assets
            WHERE is_cold = 1
            ORDER BY name
        ''')
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_non_cold_assets(self) -> List[Dict[str, Any]]:
        """Get all assets not in cold storage (active/hot)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM assets
            WHERE is_cold = 0 OR is_cold IS NULL
            ORDER BY name
        ''')
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_latest_non_cold_assets(self) -> List[Dict[str, Any]]:
        """Get latest versions of assets not in cold storage."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM assets
            WHERE (is_cold = 0 OR is_cold IS NULL)
              AND (is_latest = 1 OR is_latest IS NULL)
            ORDER BY name
        ''')
        return [self._row_to_dict(row) for row in cursor.fetchall()]


__all__ = ['AssetColdStorage']
