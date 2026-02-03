"""
Asset Switcher Database - Read-only cached database accessor for the switcher panel.

Opens its own read-only SQLite connection to avoid write conflicts with
the desktop app. Uses a simple time-based cache to avoid repeated queries
while the panel redraws.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Any


class SwitcherDatabase:
    """Read-only, cached database accessor for the switcher panel."""

    CACHE_TTL = 5.0  # seconds

    def __init__(self, db_path: str):
        """
        Initialize with path to the library database.

        Args:
            db_path: Absolute path to database.db
        """
        self._db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None
        self._cache: Dict[str, Any] = {}
        self._cache_times: Dict[str, float] = {}
        self.cache_generation: int = 0

    def connect(self) -> bool:
        """Open read-only connection via file: URI with ?mode=ro."""
        try:
            if self._connection:
                return True
            db_path = Path(self._db_path)
            if not db_path.exists():
                return False
            # Use file URI for read-only mode
            uri = f"file:{db_path.as_posix()}?mode=ro"
            self._connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")
            return True
        except Exception as e:
            self._connection = None
            return False

    def disconnect(self):
        """Close the database connection."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None
        self._cache.clear()
        self._cache_times.clear()

    def _get_cached(self, key: str) -> Optional[Any]:
        """Return cached result if still valid, else None."""
        if key in self._cache:
            if time.time() - self._cache_times[key] < self.CACHE_TTL:
                return self._cache[key]
        return None

    def _set_cached(self, key: str, value: Any):
        """Store a result in cache."""
        self._cache[key] = value
        self._cache_times[key] = time.time()

    def _ensure_connected(self) -> bool:
        """Ensure we have an active connection."""
        if self._connection:
            return True
        return self.connect()

    def get_version_siblings(self, version_group_id: str) -> List[Dict[str, Any]]:
        """
        All versions sharing a version_group_id, ordered by version DESC.

        Returns list of dicts with keys:
            uuid, name, version, version_label, is_latest, is_cold,
            representation_type, blend_backup_path, polygon_count,
            created_date, variant_name, asset_id
        """
        cache_key = f"versions:{version_group_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if not self._ensure_connected():
            return []

        try:
            cursor = self._connection.cursor()
            cursor.execute("""
                SELECT uuid, name, version, version_label, is_latest, is_cold,
                       representation_type, blend_backup_path, polygon_count,
                       created_date, variant_name, asset_id, thumbnail_path
                FROM assets
                WHERE version_group_id = ?
                ORDER BY version DESC
            """, (version_group_id,))
            rows = [dict(row) for row in cursor.fetchall()]
            self._set_cached(cache_key, rows)
            return rows
        except Exception as e:
            return []

    def get_variant_siblings(self, asset_id: str) -> List[Dict[str, Any]]:
        """
        Latest version per variant sharing an asset_id.

        Returns list of dicts with keys:
            uuid, name, version, version_label, variant_name,
            version_group_id, polygon_count, blend_backup_path
        """
        cache_key = f"variants:{asset_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if not self._ensure_connected():
            return []

        try:
            cursor = self._connection.cursor()
            cursor.execute("""
                SELECT uuid, name, version, version_label, variant_name,
                       version_group_id, polygon_count, blend_backup_path,
                       thumbnail_path
                FROM assets
                WHERE asset_id = ? AND is_latest = 1
                ORDER BY variant_name
            """, (asset_id,))
            rows = [dict(row) for row in cursor.fetchall()]
            self._set_cached(cache_key, rows)
            return rows
        except Exception as e:
            return []

    def get_representation_designation(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> Optional[Dict[str, Any]]:
        """
        Proxy/render designation from representation_designations table.

        Returns dict with keys:
            proxy_version_uuid, render_version_uuid,
            proxy_version_label, render_version_label,
            proxy_blend_path, render_blend_path
        Or None if no designation exists.
        """
        cache_key = f"repr:{version_group_id}:{variant_name}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if not self._ensure_connected():
            return None

        try:
            cursor = self._connection.cursor()
            # Check if table exists first
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='representation_designations'
            """)
            if not cursor.fetchone():
                self._set_cached(cache_key, None)
                return None

            cursor.execute("""
                SELECT proxy_version_uuid, render_version_uuid,
                       proxy_version_label, render_version_label,
                       proxy_blend_path, render_blend_path
                FROM representation_designations
                WHERE version_group_id = ? AND variant_name = ?
            """, (version_group_id, variant_name))
            row = cursor.fetchone()
            result = dict(row) if row else None
            self._set_cached(cache_key, result)
            return result
        except Exception as e:
            return None

    def get_asset_blend_path(self, uuid: str) -> Optional[str]:
        """
        Get blend_backup_path for a specific asset UUID.

        Args:
            uuid: Asset UUID

        Returns:
            Blend file path string, or None if not found
        """
        cache_key = f"blend_path:{uuid}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if not self._ensure_connected():
            return None

        try:
            cursor = self._connection.cursor()
            cursor.execute(
                "SELECT blend_backup_path FROM assets WHERE uuid = ?",
                (uuid,)
            )
            row = cursor.fetchone()
            result = row['blend_backup_path'] if row else None
            self._set_cached(cache_key, result)
            return result
        except Exception as e:
            return None

    def get_custom_proxy_count(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> int:
        """
        Get the number of custom proxies for an asset variant.

        Returns 0 if the custom_proxies table doesn't exist.
        """
        cache_key = f"cp_count:{version_group_id}:{variant_name}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if not self._ensure_connected():
            return 0

        try:
            cursor = self._connection.cursor()
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='custom_proxies'
            """)
            if not cursor.fetchone():
                self._set_cached(cache_key, 0)
                return 0

            cursor.execute("""
                SELECT COUNT(*) FROM custom_proxies
                WHERE version_group_id = ? AND variant_name = ?
            """, (version_group_id, variant_name))
            row = cursor.fetchone()
            result = row[0] if row else 0
            self._set_cached(cache_key, result)
            return result
        except Exception as e:
            return 0

    def get_custom_proxies(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> List[Dict[str, Any]]:
        """
        Get all custom proxies for an asset variant.

        Returns empty list if the custom_proxies table doesn't exist.
        """
        cache_key = f"cp_list:{version_group_id}:{variant_name}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if not self._ensure_connected():
            return []

        try:
            cursor = self._connection.cursor()
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='custom_proxies'
            """)
            if not cursor.fetchone():
                self._set_cached(cache_key, [])
                return []

            cursor.execute("""
                SELECT uuid, proxy_label, proxy_version, polygon_count,
                       blend_path, thumbnail_path, notes, created_date
                FROM custom_proxies
                WHERE version_group_id = ? AND variant_name = ?
                ORDER BY proxy_version ASC
            """, (version_group_id, variant_name))
            rows = [dict(row) for row in cursor.fetchall()]
            self._set_cached(cache_key, rows)
            return rows
        except Exception as e:
            return []

    def invalidate_cache(self):
        """Clear cache -- called after each switch operation or refresh."""
        self._cache.clear()
        self._cache_times.clear()
        self.cache_generation += 1


# Singleton instance
_switcher_db: Optional[SwitcherDatabase] = None


def get_switcher_db() -> Optional[SwitcherDatabase]:
    """
    Get or create the singleton SwitcherDatabase instance.

    Uses the library path from get_library_connection() to find the database.

    Returns:
        SwitcherDatabase instance, or None if library is not connected
    """
    global _switcher_db

    try:
        from .library_connection import get_library_connection
        from .constants import META_FOLDER, DATABASE_NAME

        library = get_library_connection()
        db_path = str(library.library_path / META_FOLDER / DATABASE_NAME)

        if _switcher_db is None:
            _switcher_db = SwitcherDatabase(db_path)
            _switcher_db.connect()
        else:
            # Reconnect if path changed
            if _switcher_db._db_path != db_path:
                _switcher_db.disconnect()
                _switcher_db = SwitcherDatabase(db_path)
                _switcher_db.connect()

        return _switcher_db
    except Exception as e:
        return None


def close_switcher_db():
    """Close and discard the singleton instance."""
    global _switcher_db
    if _switcher_db:
        _switcher_db.disconnect()
        _switcher_db = None


__all__ = [
    'SwitcherDatabase',
    'get_switcher_db',
    'close_switcher_db',
]
