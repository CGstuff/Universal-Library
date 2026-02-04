"""
FolderRepository - Folder CRUD operations

Pattern: Repository pattern for folder data access
Extracted from DatabaseService for separation of concerns.

Virtual Folder System:
- Folders exist only in the database as organizational containers
- Assets are organized by folder membership (asset_folders table)
- Moving assets between folders = database update only, no file operations
- This ensures linked/instanced assets never have broken paths
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Any

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
               description: str = "", create_physical: bool = False) -> Optional[int]:
        """
        Create new folder (virtual - database only).

        Folders are virtual organizational containers. Assets are organized
        by folder membership in the database, not by physical file location.
        This ensures that moving assets between folders never breaks links.

        Args:
            name: Folder name
            parent_id: Parent folder ID (None for root-level)
            description: Optional description
            create_physical: Deprecated, ignored (kept for API compatibility)

        Returns:
            New folder ID or None on error
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                # Sanitize folder name (for display/path consistency)
                safe_name = Config.sanitize_filename(name)

                # Build virtual path based on parent (for hierarchy display)
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

                # Virtual folders - no physical folder creation
                # Assets are organized by database membership, not file location

                return folder_id
        except sqlite3.IntegrityError:
            return None

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

    def rename(self, folder_id: int, new_name: str, rename_physical: bool = False) -> bool:
        """
        Rename a folder (virtual - database only).

        Updates the folder name and path in the database.
        No physical file operations - folders are virtual.

        Args:
            folder_id: ID of folder to rename
            new_name: New folder name
            rename_physical: Deprecated, ignored (kept for API compatibility)

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

                # Sanitize new name
                safe_new_name = Config.sanitize_filename(new_name)

                # Calculate new virtual path
                if parent_id is not None:
                    cursor.execute('SELECT path FROM folders WHERE id = ?', (parent_id,))
                    parent_result = cursor.fetchone()
                    parent_path = parent_result['path'] if parent_result else ""
                    new_path = f"{parent_path}/{safe_new_name}" if parent_path else safe_new_name
                else:
                    new_path = safe_new_name

                # Virtual folders - database update only
                cursor.execute(
                    'UPDATE folders SET name = ?, path = ?, modified_date = ? WHERE id = ?',
                    (new_name, new_path, datetime.now(), folder_id)
                )

                # Update child folder paths (virtual hierarchy)
                if old_path:
                    cursor.execute(
                        'UPDATE folders SET path = REPLACE(path, ?, ?) WHERE path LIKE ?',
                        (old_path, new_path, f"{old_path}/%")
                    )

                return cursor.rowcount > 0
        except Exception as e:
            return False

    def delete(self, folder_id: int, delete_physical: bool = False) -> bool:
        """
        Delete folder by ID (virtual - database only).

        Removes the folder from the database. Assets that were in this
        folder remain in place (physically) but lose this folder membership.

        Args:
            folder_id: ID of folder to delete
            delete_physical: Deprecated, ignored (kept for API compatibility)

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM folders WHERE id = ?', (folder_id,))
                success = cursor.rowcount > 0

            # Virtual folders - no physical deletion
            # Assets remain in their physical locations

            return success
        except Exception as e:
            return False

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

    def get_descendant_ids(self, folder_id: int) -> List[int]:
        """
        Get all descendant folder IDs (recursive).
        
        Returns the folder_id itself plus all nested children at any depth.
        Used for recursive folder filtering (click parent, see all nested items).
        
        Args:
            folder_id: Parent folder ID
            
        Returns:
            List of folder IDs including the parent and all descendants
        """
        result = [folder_id]
        children = self.get_children(folder_id)
        for child in children:
            child_id = child.get('id')
            if child_id:
                result.extend(self.get_descendant_ids(child_id))
        return result

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
