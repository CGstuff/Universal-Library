"""
FolderRepository - Folder CRUD operations

Pattern: Repository pattern for folder data access
Extracted from DatabaseService for separation of concerns.

Physical Folder Management:
- Creates physical folders alongside database entries
- Uses hybrid structure: library/{type}/{folder_path}/{asset}/
- Supports rename with physical folder updates
"""

import sqlite3
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

from .base_repository import BaseRepository
from ..config import Config


class FolderRepository(BaseRepository):
    """
    Repository for folder operations

    Handles all folder-related database operations:
    - Create, read, update, delete folders
    - Folder hierarchy management
    - Path calculations
    """

    def get_root_folder_id(self) -> int:
        """Get the ID of the root folder, creating it if needed"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT id FROM folders WHERE parent_id IS NULL LIMIT 1')
        result = cursor.fetchone()
        if result:
            return result[0]

        # No root folder exists, create one
        try:
            now = datetime.now()
            cursor.execute('''
                INSERT INTO folders (name, parent_id, path, created_date, modified_date)
                VALUES (?, ?, ?, ?, ?)
            ''', ("Root", None, "", now, now))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            cursor.execute('SELECT id FROM folders WHERE parent_id IS NULL LIMIT 1')
            result = cursor.fetchone()
            if result:
                return result[0]
            raise RuntimeError("Cannot find or create root folder")

    def create(self, name: str, parent_id: Optional[int] = None,
               description: str = "", create_physical: bool = True) -> Optional[int]:
        """
        Create new folder with optional physical folder creation.

        Creates both a database entry and physical folders on disk.
        Physical folders are created per asset type:
        library/{type}/{folder_path}/

        Args:
            name: Folder name
            parent_id: Parent folder ID (None for root-level)
            description: Optional description
            create_physical: Whether to create physical folders on disk

        Returns:
            New folder ID or None on error
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                # Sanitize folder name for filesystem
                safe_name = Config.sanitize_filename(name)

                # Build path based on parent
                if parent_id is not None:
                    cursor.execute('SELECT path FROM folders WHERE id = ?', (parent_id,))
                    result = cursor.fetchone()
                    if not result:
                        return None
                    parent_path = result['path'] or ""
                    full_path = f"{parent_path}/{safe_name}" if parent_path else safe_name
                else:
                    full_path = safe_name

                now = datetime.now()
                cursor.execute('''
                    INSERT INTO folders (name, parent_id, path, description, created_date, modified_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (name, parent_id, full_path, description, now, now))

                folder_id = cursor.lastrowid

                # Create physical folders for each asset type
                if create_physical and folder_id:
                    self._create_physical_folders(full_path)

                return folder_id
        except sqlite3.IntegrityError:
            return None

    def _create_physical_folders(self, folder_path: str):
        """
        Create physical folders for each asset type.

        Creates folders at: library/{type}/{folder_path}/

        Args:
            folder_path: The folder path relative to type folder
        """
        try:
            library_folder = Config.get_library_folder()
            for asset_type in Config.ASSET_TYPES:
                type_folder = library_folder / asset_type
                physical_path = type_folder / folder_path
                physical_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            pass

    def get_by_id(self, folder_id: int) -> Optional[Dict[str, Any]]:
        """Get folder by ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM folders WHERE id = ?', (folder_id,))
        result = cursor.fetchone()
        return dict(result) if result else None

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all folders ordered by path"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM folders ORDER BY path')
        return [dict(row) for row in cursor.fetchall()]

    def rename(self, folder_id: int, new_name: str, rename_physical: bool = True) -> bool:
        """
        Rename a folder with optional physical folder rename.

        Renames both the database entry and physical folders on disk.
        Also updates all asset paths affected by the rename.

        Args:
            folder_id: ID of folder to rename
            new_name: New folder name
            rename_physical: Whether to rename physical folders on disk

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                cursor.execute('SELECT parent_id, path FROM folders WHERE id = ?', (folder_id,))
                result = cursor.fetchone()
                if not result:
                    return False

                parent_id = result['parent_id']
                old_path = result['path'] or ""

                # Sanitize new name for filesystem
                safe_new_name = Config.sanitize_filename(new_name)

                # Calculate new path
                if parent_id is not None:
                    cursor.execute('SELECT path FROM folders WHERE id = ?', (parent_id,))
                    parent_result = cursor.fetchone()
                    parent_path = parent_result['path'] if parent_result else ""
                    new_path = f"{parent_path}/{safe_new_name}" if parent_path else safe_new_name
                else:
                    new_path = safe_new_name

                # Rename physical folders first (can fail, rollback possible)
                if rename_physical and old_path:
                    success, error = self._rename_physical_folders(old_path, new_path)
                    if not success:
                        # Continue with database update even if physical fails
                        pass

                cursor.execute(
                    'UPDATE folders SET name = ?, path = ?, modified_date = ? WHERE id = ?',
                    (new_name, new_path, datetime.now(), folder_id)
                )

                # Update child folder paths
                if old_path:
                    cursor.execute(
                        'UPDATE folders SET path = REPLACE(path, ?, ?) WHERE path LIKE ?',
                        (old_path, new_path, f"{old_path}/%")
                    )

                return cursor.rowcount > 0
        except Exception as e:
            return False

    def _rename_physical_folders(self, old_path: str, new_path: str) -> Tuple[bool, str]:
        """
        Rename physical folders for each asset type.

        Renames folders at: library/{type}/{old_path}/ -> library/{type}/{new_path}/

        Args:
            old_path: Old folder path relative to type folder
            new_path: New folder path relative to type folder

        Returns:
            Tuple of (success, error_message)
        """
        renamed = []
        try:
            library_folder = Config.get_library_folder()
            for asset_type in Config.ASSET_TYPES:
                type_folder = library_folder / asset_type
                old_physical = type_folder / old_path
                new_physical = type_folder / new_path

                if old_physical.exists():
                    # Ensure parent of new path exists
                    new_physical.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(str(old_physical), str(new_physical))
                    renamed.append((old_physical, new_physical))

            return True, ""

        except Exception as e:
            # Rollback: restore original folder names
            for old_p, new_p in reversed(renamed):
                try:
                    os.replace(str(new_p), str(old_p))
                except Exception:
                    pass
            return False, str(e)

    def delete(self, folder_id: int, delete_physical: bool = True) -> bool:
        """
        Delete folder by ID with optional physical folder deletion.

        Args:
            folder_id: ID of folder to delete
            delete_physical: Whether to delete physical folders on disk

        Returns:
            True if successful
        """
        try:
            # Get folder path before deleting
            folder = self.get_by_id(folder_id)
            folder_path = folder.get('path') if folder else None

            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM folders WHERE id = ?', (folder_id,))
                success = cursor.rowcount > 0

            # Delete physical folders after database deletion
            if success and delete_physical and folder_path:
                self._delete_physical_folders(folder_path)

            return success
        except Exception as e:
            return False

    def _delete_physical_folders(self, folder_path: str):
        """
        Delete physical folders for each asset type.

        Only deletes empty folders (does not delete assets).

        Args:
            folder_path: Folder path relative to type folder
        """
        try:
            library_folder = Config.get_library_folder()
            for asset_type in Config.ASSET_TYPES:
                type_folder = library_folder / asset_type
                physical_path = type_folder / folder_path

                if physical_path.exists():
                    # Only delete if empty (safety)
                    try:
                        physical_path.rmdir()  # Only works if empty
                    except OSError:
                        pass
        except Exception as e:
            pass

    def get_full_path(self, folder_id: int) -> Optional[str]:
        """
        Get the full path for a folder.

        Args:
            folder_id: Folder ID

        Returns:
            Full path string or None if not found
        """
        folder = self.get_by_id(folder_id)
        return folder.get('path') if folder else None

    def get_children(self, parent_id: int) -> List[Dict[str, Any]]:
        """Get child folders of a parent"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM folders WHERE parent_id = ? ORDER BY name',
            (parent_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_parent(self, folder_id: int, new_parent_id: int) -> bool:
        """
        Move a folder to a new parent folder

        Args:
            folder_id: ID of folder to move
            new_parent_id: ID of new parent folder

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                # Get current folder info
                cursor.execute('SELECT name, path FROM folders WHERE id = ?', (folder_id,))
                result = cursor.fetchone()
                if not result:
                    return False

                folder_name = result['name']
                old_path = result['path'] or ""

                # Get new parent's path
                cursor.execute('SELECT path, parent_id FROM folders WHERE id = ?', (new_parent_id,))
                parent_result = cursor.fetchone()
                if not parent_result:
                    return False

                # Calculate new path
                parent_path = parent_result['path'] or ""
                # If parent is root (parent_id is NULL), path is just the folder name
                if parent_result['parent_id'] is None:
                    new_path = folder_name
                else:
                    new_path = f"{parent_path}/{folder_name}" if parent_path else folder_name

                # Update the folder's parent and path
                cursor.execute(
                    'UPDATE folders SET parent_id = ?, path = ?, modified_date = ? WHERE id = ?',
                    (new_parent_id, new_path, datetime.now(), folder_id)
                )

                # Update all descendant folder paths
                if old_path:
                    cursor.execute(
                        'UPDATE folders SET path = REPLACE(path, ?, ?) WHERE path LIKE ?',
                        (old_path, new_path, f"{old_path}/%")
                    )

                return True
        except Exception:
            return False


__all__ = ['FolderRepository']
