"""
AssetVersions - Version management operations.

Handles:
- Version queries
- Creating new versions
- Latest version management
- Publish/lock workflow
- Representation types
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Any, Callable


class AssetVersions:
    """
    Manages version-related operations for assets.

    All operations work through callbacks to the parent repository
    for database access and asset operations.
    """

    def __init__(
        self,
        get_connection: Callable[[], sqlite3.Connection],
        transaction: Callable,
        get_by_uuid: Callable[[str], Optional[Dict[str, Any]]],
        update: Callable[[str, Dict[str, Any]], bool],
        add: Callable[[Dict[str, Any]], Optional[int]],
        row_to_dict: Callable,
    ):
        """
        Initialize with repository callbacks.

        Args:
            get_connection: Function to get database connection
            transaction: Context manager for transactions
            get_by_uuid: Function to get asset by UUID
            update: Function to update asset
            add: Function to add asset
            row_to_dict: Function to convert row to dict
        """
        self._get_connection = get_connection
        self._transaction = transaction
        self._get_by_uuid = get_by_uuid
        self._update = update
        self._add = add
        self._row_to_dict = row_to_dict

    def get_versions(self, version_group_id: str) -> List[Dict[str, Any]]:
        """Get all versions of an asset by version group ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM assets
            WHERE version_group_id = ?
            ORDER BY version DESC
        ''', (version_group_id,))
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_latest_version(self, version_group_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest version of an asset."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM assets
            WHERE version_group_id = ? AND is_latest = 1
            LIMIT 1
        ''', (version_group_id,))
        result = cursor.fetchone()
        return self._row_to_dict(result) if result else None

    def create_new_version(self, version_group_id: str, asset_data: Dict[str, Any]) -> Optional[int]:
        """Create a new version of an existing asset."""
        # Compute version number and mark existing as not-latest in a single
        # transaction so two concurrent calls cannot both read the same max
        # and produce duplicate version labels.
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                # Authoritative max inside the write-lock
                cursor.execute(
                    'SELECT MAX(version) FROM assets WHERE version_group_id = ?',
                    (version_group_id,)
                )
                row = cursor.fetchone()
                max_version = row[0] if row and row[0] else 0

                if max_version == 0:
                    return None  # No existing versions

                new_version = max_version + 1
                new_label = f'v{new_version:03d}'

                # Guard: abort if this label already exists (double-click protection)
                cursor.execute(
                    'SELECT COUNT(*) FROM assets '
                    'WHERE version_group_id = ? AND version_label = ?',
                    (version_group_id, new_label)
                )
                if cursor.fetchone()[0] > 0:
                    return None

                # Mark all existing versions as not latest
                cursor.execute(
                    'UPDATE assets SET is_latest = 0 WHERE version_group_id = ?',
                    (version_group_id,)
                )
        except Exception:
            return None

        # Add version info to asset data
        asset_data['version_group_id'] = version_group_id
        asset_data['version'] = new_version
        asset_data['version_label'] = new_label
        asset_data['is_latest'] = 1

        return self._add(asset_data)

    def set_as_latest(self, uuid: str) -> bool:
        """Set a specific version as the latest."""
        asset = self._get_by_uuid(uuid)
        if not asset:
            return False

        version_group_id = asset.get('version_group_id')
        if not version_group_id:
            return False

        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                # First, unset all as latest and mark as cold (archived)
                cursor.execute(
                    'UPDATE assets SET is_latest = 0, is_cold = 1 WHERE version_group_id = ?',
                    (version_group_id,)
                )
                # Then set this one as latest and mark as NOT cold (active)
                cursor.execute(
                    'UPDATE assets SET is_latest = 1, is_cold = 0 WHERE uuid = ?',
                    (uuid,)
                )
                return cursor.rowcount > 0
        except Exception:
            return False

    def get_version_history(self, version_group_id: str) -> List[Dict[str, Any]]:
        """Get full version history with cold storage status."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM assets
            WHERE version_group_id = ?
            ORDER BY version DESC
        ''', (version_group_id,))
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def promote_to_latest(self, uuid: str) -> bool:
        """
        Promote a version to be the latest.

        This will:
        1. Mark the current latest as not latest (and mark as cold)
        2. Mark the specified version as latest (and mark as NOT cold)
        """
        asset = self._get_by_uuid(uuid)
        if not asset:
            return False

        version_group_id = asset.get('version_group_id')
        if not version_group_id:
            return False

        # Already latest
        if asset.get('is_latest', 0) == 1:
            return True

        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                # Unset current latest and mark as cold (archived)
                cursor.execute(
                    'UPDATE assets SET is_latest = 0, is_cold = 1 WHERE version_group_id = ? AND is_latest = 1',
                    (version_group_id,)
                )

                # Set new latest and mark as NOT cold (active)
                cursor.execute(
                    'UPDATE assets SET is_latest = 1, is_cold = 0 WHERE uuid = ?',
                    (uuid,)
                )

                return cursor.rowcount > 0
        except Exception as e:
            return False

    def demote_from_latest(self, uuid: str) -> bool:
        """Demote a version from latest (used when moving to cold storage)."""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE assets SET is_latest = 0 WHERE uuid = ?',
                    (uuid,)
                )
                return cursor.rowcount > 0
        except Exception as e:
            return False

    def publish_version(self, uuid: str, published_by: str = "") -> bool:
        """
        Mark version as published/approved with timestamp.

        Sets status to 'approved', published_date, published_by, and is_immutable.
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                # Check if columns exist
                cursor.execute("PRAGMA table_info(assets)")
                columns = {col[1] for col in cursor.fetchall()}

                updates = {'status': 'approved'}

                if 'published_date' in columns:
                    updates['published_date'] = datetime.now().isoformat()
                if 'published_by' in columns:
                    updates['published_by'] = published_by
                if 'is_immutable' in columns:
                    updates['is_immutable'] = 1
                if 'modified_date' in columns:
                    updates['modified_date'] = datetime.now().isoformat()

                set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
                values = list(updates.values())
                values.append(uuid)

                cursor.execute(
                    f'UPDATE assets SET {set_clause} WHERE uuid = ?',
                    values
                )

                return cursor.rowcount > 0
        except Exception as e:
            return False

    def lock_version(self, uuid: str) -> bool:
        """Make version immutable (locked from changes)."""
        return self._update(uuid, {'is_immutable': 1})

    def unlock_version(self, uuid: str) -> bool:
        """Unlock a version (allow changes again)."""
        return self._update(uuid, {'is_immutable': 0})

    def is_immutable(self, uuid: str) -> bool:
        """Check if a version is immutable."""
        asset = self._get_by_uuid(uuid)
        if not asset:
            return False
        return asset.get('is_immutable', 0) == 1

    def get_previous_latest(self, version_group_id: str, current_uuid: str) -> Optional[Dict[str, Any]]:
        """Get the previous latest version (for rollback scenarios)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM assets
            WHERE version_group_id = ? AND uuid != ?
            ORDER BY version DESC
            LIMIT 1
        ''', (version_group_id, current_uuid))
        result = cursor.fetchone()
        return self._row_to_dict(result) if result else None

    def set_representation_type(self, uuid: str, rep_type: str) -> bool:
        """Set representation type for an asset."""
        valid_types = ['model', 'lookdev', 'rig', 'final']
        if rep_type not in valid_types:
            return False
        return self._update(uuid, {'representation_type': rep_type})

    def get_by_representation(self, rep_type: str, folder_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get assets by representation type."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM assets WHERE representation_type = ?"
        params = [rep_type]

        if folder_id is not None:
            query += " AND folder_id = ?"
            params.append(folder_id)

        query += " ORDER BY name"
        cursor.execute(query, params)

        return [self._row_to_dict(row) for row in cursor.fetchall()]


__all__ = ['AssetVersions']
