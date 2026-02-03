"""
TagRepository - Tag CRUD operations

Pattern: Repository pattern for tag data access
Handles tag management and asset-tag relationships.
"""

from datetime import datetime
from typing import List, Dict, Optional, Any

from .base_repository import BaseRepository


class TagRepository(BaseRepository):
    """
    Repository for tag operations

    Handles all tag-related database operations:
    - Create, read, update, delete tags
    - Add/remove tags from assets
    - Query assets by tags
    """

    # Default tag colors (Material Design palette)
    DEFAULT_COLORS = [
        '#F44336',  # Red
        '#E91E63',  # Pink
        '#9C27B0',  # Purple
        '#673AB7',  # Deep Purple
        '#3F51B5',  # Indigo
        '#2196F3',  # Blue
        '#03A9F4',  # Light Blue
        '#00BCD4',  # Cyan
        '#009688',  # Teal
        '#4CAF50',  # Green
        '#8BC34A',  # Light Green
        '#CDDC39',  # Lime
        '#FFC107',  # Amber
        '#FF9800',  # Orange
        '#FF5722',  # Deep Orange
        '#795548',  # Brown
        '#607D8B',  # Blue Grey
    ]

    def create(self, name: str, color: Optional[str] = None) -> Optional[int]:
        """
        Create a new tag

        Args:
            name: Tag name (must be unique)
            color: Hex color code (defaults to blue-grey)

        Returns:
            Tag ID or None on error
        """
        if not name or not name.strip():
            return None

        name = name.strip().lower()
        color = color or '#607D8B'

        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO tags (name, color, created_date)
                    VALUES (?, ?, ?)
                ''', (name, color, datetime.now()))
                return cursor.lastrowid
        except Exception as e:
            return None

    def get_by_id(self, tag_id: int) -> Optional[Dict[str, Any]]:
        """Get tag by ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tags WHERE id = ?', (tag_id,))
        result = cursor.fetchone()
        return dict(result) if result else None

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get tag by name (case-insensitive)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tags WHERE LOWER(name) = LOWER(?)', (name.strip(),))
        result = cursor.fetchone()
        return dict(result) if result else None

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all tags sorted by name"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tags ORDER BY name')
        return [dict(row) for row in cursor.fetchall()]

    def update(self, tag_id: int, name: Optional[str] = None, color: Optional[str] = None) -> bool:
        """
        Update a tag

        Args:
            tag_id: Tag ID to update
            name: New name (optional)
            color: New color (optional)

        Returns:
            True if successful
        """
        updates = {}
        if name is not None:
            updates['name'] = name.strip().lower()
        if color is not None:
            updates['color'] = color

        if not updates:
            return True

        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
                values = list(updates.values())
                values.append(tag_id)
                cursor.execute(f'UPDATE tags SET {set_clause} WHERE id = ?', values)
                return cursor.rowcount > 0
        except Exception as e:
            return False

    def delete(self, tag_id: int) -> bool:
        """
        Delete a tag (also removes from all assets via cascade)

        Args:
            tag_id: Tag ID to delete

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
                return cursor.rowcount > 0
        except Exception as e:
            return False

    def get_or_create(self, name: str, color: Optional[str] = None) -> Optional[int]:
        """
        Get existing tag or create new one

        Args:
            name: Tag name
            color: Color for new tag (ignored if tag exists)

        Returns:
            Tag ID or None on error
        """
        existing = self.get_by_name(name)
        if existing:
            return existing['id']
        return self.create(name, color)

    # ==================== ASSET-TAG RELATIONSHIPS ====================

    def add_tag_to_asset(self, asset_uuid: str, tag_id: int) -> bool:
        """
        Add a tag to an asset

        Args:
            asset_uuid: Asset UUID
            tag_id: Tag ID

        Returns:
            True if successful (or already exists)
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO asset_tags (asset_uuid, tag_id, created_date)
                    VALUES (?, ?, ?)
                ''', (asset_uuid, tag_id, datetime.now()))
                return True
        except Exception as e:
            return False

    def remove_tag_from_asset(self, asset_uuid: str, tag_id: int) -> bool:
        """
        Remove a tag from an asset

        Args:
            asset_uuid: Asset UUID
            tag_id: Tag ID

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM asset_tags WHERE asset_uuid = ? AND tag_id = ?
                ''', (asset_uuid, tag_id))
                return True
        except Exception as e:
            return False

    def get_asset_tags(self, asset_uuid: str) -> List[Dict[str, Any]]:
        """
        Get all tags for an asset

        Args:
            asset_uuid: Asset UUID

        Returns:
            List of tag dicts with id, name, color
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.id, t.name, t.color
            FROM tags t
            INNER JOIN asset_tags at ON t.id = at.tag_id
            WHERE at.asset_uuid = ?
            ORDER BY t.name
        ''', (asset_uuid,))
        return [dict(row) for row in cursor.fetchall()]

    def set_asset_tags(self, asset_uuid: str, tag_ids: List[int]) -> bool:
        """
        Set all tags for an asset (replaces existing)

        Args:
            asset_uuid: Asset UUID
            tag_ids: List of tag IDs to set

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                # Remove existing tags
                cursor.execute('DELETE FROM asset_tags WHERE asset_uuid = ?', (asset_uuid,))
                # Add new tags
                now = datetime.now()
                for tag_id in tag_ids:
                    cursor.execute('''
                        INSERT INTO asset_tags (asset_uuid, tag_id, created_date)
                        VALUES (?, ?, ?)
                    ''', (asset_uuid, tag_id, now))
                return True
        except Exception as e:
            return False

    def get_assets_by_tag(self, tag_id: int) -> List[str]:
        """
        Get all asset UUIDs with a specific tag

        Args:
            tag_id: Tag ID

        Returns:
            List of asset UUIDs
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT asset_uuid FROM asset_tags WHERE tag_id = ?
        ''', (tag_id,))
        return [row[0] for row in cursor.fetchall()]

    def get_assets_by_tags(self, tag_ids: List[int], match_all: bool = False) -> List[str]:
        """
        Get asset UUIDs matching tag criteria

        Args:
            tag_ids: List of tag IDs to match
            match_all: If True, asset must have ALL tags; if False, ANY tag

        Returns:
            List of asset UUIDs
        """
        if not tag_ids:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(tag_ids))

        if match_all:
            # Asset must have ALL specified tags
            cursor.execute(f'''
                SELECT asset_uuid
                FROM asset_tags
                WHERE tag_id IN ({placeholders})
                GROUP BY asset_uuid
                HAVING COUNT(DISTINCT tag_id) = ?
            ''', (*tag_ids, len(tag_ids)))
        else:
            # Asset must have ANY of the specified tags
            cursor.execute(f'''
                SELECT DISTINCT asset_uuid
                FROM asset_tags
                WHERE tag_id IN ({placeholders})
            ''', tag_ids)

        return [row[0] for row in cursor.fetchall()]

    def get_tag_usage_counts(self) -> Dict[int, int]:
        """
        Get usage count for each tag

        Returns:
            Dict mapping tag_id to count of assets using it
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tag_id, COUNT(*) as count
            FROM asset_tags
            GROUP BY tag_id
        ''')
        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_tags_with_counts(self) -> List[Dict[str, Any]]:
        """
        Get all tags with their usage counts

        Returns:
            List of tag dicts with id, name, color, count
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.id, t.name, t.color, COUNT(at.asset_uuid) as count
            FROM tags t
            LEFT JOIN asset_tags at ON t.id = at.tag_id
            GROUP BY t.id, t.name, t.color
            ORDER BY t.name
        ''')
        return [dict(row) for row in cursor.fetchall()]

    def search_tags(self, query: str) -> List[Dict[str, Any]]:
        """
        Search tags by name

        Args:
            query: Search string

        Returns:
            List of matching tags
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM tags
            WHERE name LIKE ?
            ORDER BY name
        ''', (f'%{query}%',))
        return [dict(row) for row in cursor.fetchall()]


__all__ = ['TagRepository']
