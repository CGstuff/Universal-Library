"""
ReviewScreenshots - Screenshot management for reviews database.

Handles:
- Adding and retrieving screenshots
- Screenshot ordering
- Screenshot deletion
"""

import sqlite3
from typing import Optional, List, Dict, Any


class ReviewScreenshots:
    """
    Manages review screenshot database operations.

    Screenshots are visual references attached to review sessions.
    Notes can be linked to specific screenshots.
    """

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    def add_screenshot(
        self,
        asset_uuid: str,
        version_label: str,
        filename: str,
        file_path: str,
        display_name: str = '',
        uploaded_by: str = ''
    ) -> Optional[int]:
        """
        Add a screenshot to a review session.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            filename: Original filename
            file_path: Path to the screenshot file
            display_name: Optional display name
            uploaded_by: Username who uploaded

        Returns:
            Screenshot ID or None if failed
        """
        # Get or create session
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT id FROM review_sessions
            WHERE asset_uuid = ? AND version_label = ?
        ''', (asset_uuid, version_label))
        row = cursor.fetchone()

        if row:
            session_id = row[0]
        else:
            cursor.execute('''
                INSERT INTO review_sessions (asset_uuid, version_label)
                VALUES (?, ?)
            ''', (asset_uuid, version_label))
            self._connection.commit()
            session_id = cursor.lastrowid

        # Get next display order
        cursor.execute('''
            SELECT COALESCE(MAX(display_order), -1) + 1
            FROM review_screenshots WHERE session_id = ?
        ''', (session_id,))
        display_order = cursor.fetchone()[0]

        try:
            cursor.execute('''
                INSERT INTO review_screenshots
                (session_id, filename, file_path, display_name, display_order, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, filename, file_path, display_name or filename, display_order, uploaded_by))
            self._connection.commit()
            return cursor.lastrowid
        except Exception as e:
            return None

    def get_screenshots(
        self,
        asset_uuid: str,
        version_label: str
    ) -> List[Dict[str, Any]]:
        """
        Get all screenshots for a version.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label

        Returns:
            List of screenshot dicts ordered by display_order
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT s.*
            FROM review_screenshots s
            JOIN review_sessions rs ON s.session_id = rs.id
            WHERE rs.asset_uuid = ? AND rs.version_label = ?
            ORDER BY s.display_order ASC
        ''', (asset_uuid, version_label))
        return [dict(row) for row in cursor.fetchall()]

    def get_screenshot_by_id(self, screenshot_id: int) -> Optional[Dict[str, Any]]:
        """Get a screenshot by ID."""
        cursor = self._connection.cursor()
        cursor.execute('SELECT * FROM review_screenshots WHERE id = ?', (screenshot_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_screenshot(
        self,
        screenshot_id: int,
        display_name: Optional[str] = None,
        display_order: Optional[int] = None
    ) -> bool:
        """
        Update screenshot properties.

        Args:
            screenshot_id: Screenshot ID
            display_name: New display name (optional)
            display_order: New display order (optional)

        Returns:
            True if successful
        """
        try:
            cursor = self._connection.cursor()
            updates = []
            params = []

            if display_name is not None:
                updates.append('display_name = ?')
                params.append(display_name)

            if display_order is not None:
                updates.append('display_order = ?')
                params.append(display_order)

            if not updates:
                return True

            params.append(screenshot_id)
            cursor.execute(f'''
                UPDATE review_screenshots
                SET {', '.join(updates)}
                WHERE id = ?
            ''', params)
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def delete_screenshot(self, screenshot_id: int) -> bool:
        """Delete a screenshot (cascades to notes)."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('DELETE FROM review_screenshots WHERE id = ?', (screenshot_id,))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def reorder_screenshots(
        self,
        asset_uuid: str,
        version_label: str,
        screenshot_ids: List[int]
    ) -> bool:
        """
        Reorder screenshots for a version.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            screenshot_ids: List of screenshot IDs in desired order

        Returns:
            True if successful
        """
        try:
            cursor = self._connection.cursor()
            for order, screenshot_id in enumerate(screenshot_ids):
                cursor.execute('''
                    UPDATE review_screenshots
                    SET display_order = ?
                    WHERE id = ?
                ''', (order, screenshot_id))
            self._connection.commit()
            return True
        except Exception as e:
            return False


__all__ = ['ReviewScreenshots']
