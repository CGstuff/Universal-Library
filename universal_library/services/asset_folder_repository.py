"""
AssetFolderRepository - Asset-Folder relationship operations

Pattern: Repository pattern for asset-folder many-to-many relationships
Handles folder membership for assets (folders as tags).
"""

from datetime import datetime
from typing import List, Dict, Any

from .base_repository import BaseRepository


class AssetFolderRepository(BaseRepository):
    """
    Repository for asset-folder relationships

    Handles multi-folder membership for assets:
    - Add/remove assets from folders
    - Query assets by folders
    - Query folders for assets
    """

    def add_asset_to_folder(self, asset_uuid: str, folder_id: int) -> bool:
        """
        Add an asset to a folder

        Args:
            asset_uuid: Asset UUID
            folder_id: Folder ID

        Returns:
            True if successful (or already exists)
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO asset_folders (asset_uuid, folder_id, created_date)
                    VALUES (?, ?, ?)
                ''', (asset_uuid, folder_id, datetime.now()))
                return True
        except Exception as e:
            return False

    def remove_asset_from_folder(self, asset_uuid: str, folder_id: int) -> bool:
        """
        Remove an asset from a folder

        Args:
            asset_uuid: Asset UUID
            folder_id: Folder ID

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM asset_folders WHERE asset_uuid = ? AND folder_id = ?
                ''', (asset_uuid, folder_id))
                return True
        except Exception as e:
            return False

    def get_asset_folders(self, asset_uuid: str) -> List[Dict[str, Any]]:
        """
        Get all folders for an asset

        Args:
            asset_uuid: Asset UUID

        Returns:
            List of folder dicts with id, name, path
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT f.id, f.name, f.path, f.parent_id
            FROM folders f
            INNER JOIN asset_folders af ON f.id = af.folder_id
            WHERE af.asset_uuid = ?
            ORDER BY f.path
        ''', (asset_uuid,))
        return [dict(row) for row in cursor.fetchall()]

    def set_asset_folders(self, asset_uuid: str, folder_ids: List[int]) -> bool:
        """
        Set all folders for an asset (replaces existing)

        Args:
            asset_uuid: Asset UUID
            folder_ids: List of folder IDs to set

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                # Remove existing folder memberships
                cursor.execute('DELETE FROM asset_folders WHERE asset_uuid = ?', (asset_uuid,))
                # Add new folder memberships
                now = datetime.now()
                for folder_id in folder_ids:
                    cursor.execute('''
                        INSERT INTO asset_folders (asset_uuid, folder_id, created_date)
                        VALUES (?, ?, ?)
                    ''', (asset_uuid, folder_id, now))
                return True
        except Exception as e:
            return False

    def get_assets_in_folder(self, folder_id: int) -> List[str]:
        """
        Get all asset UUIDs in a specific folder

        Args:
            folder_id: Folder ID

        Returns:
            List of asset UUIDs
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT asset_uuid FROM asset_folders WHERE folder_id = ?
        ''', (folder_id,))
        return [row[0] for row in cursor.fetchall()]

    def get_assets_in_folders(self, folder_ids: List[int], match_all: bool = False) -> List[str]:
        """
        Get asset UUIDs in specified folders

        Args:
            folder_ids: List of folder IDs to match
            match_all: If True, asset must be in ALL folders; if False, ANY folder

        Returns:
            List of asset UUIDs
        """
        if not folder_ids:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(folder_ids))

        if match_all:
            # Asset must be in ALL specified folders
            cursor.execute(f'''
                SELECT asset_uuid
                FROM asset_folders
                WHERE folder_id IN ({placeholders})
                GROUP BY asset_uuid
                HAVING COUNT(DISTINCT folder_id) = ?
            ''', (*folder_ids, len(folder_ids)))
        else:
            # Asset must be in ANY of the specified folders
            cursor.execute(f'''
                SELECT DISTINCT asset_uuid
                FROM asset_folders
                WHERE folder_id IN ({placeholders})
            ''', folder_ids)

        return [row[0] for row in cursor.fetchall()]

    def get_folder_asset_counts(self) -> Dict[int, int]:
        """
        Get asset count for each folder

        Returns:
            Dict mapping folder_id to count of assets in it
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT folder_id, COUNT(*) as count
            FROM asset_folders
            GROUP BY folder_id
        ''')
        return {row[0]: row[1] for row in cursor.fetchall()}

    def migrate_legacy_folder_id(self, asset_uuid: str, legacy_folder_id: int) -> bool:
        """
        Migrate an asset's legacy folder_id to the new multi-folder system

        Adds the legacy folder to asset_folders if not already there.

        Args:
            asset_uuid: Asset UUID
            legacy_folder_id: The folder_id from assets table

        Returns:
            True if successful
        """
        return self.add_asset_to_folder(asset_uuid, legacy_folder_id)

    def copy_folders_to_asset(self, source_uuid: str, target_uuid: str) -> bool:
        """
        Copy folder memberships from one asset to another

        Args:
            source_uuid: Source asset UUID
            target_uuid: Target asset UUID

        Returns:
            True if successful
        """
        try:
            folders = self.get_asset_folders(source_uuid)
            folder_ids = [f['id'] for f in folders]
            return self.set_asset_folders(target_uuid, folder_ids)
        except Exception as e:
            return False


__all__ = ['AssetFolderRepository']
