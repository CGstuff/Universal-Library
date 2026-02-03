"""
ReviewDrawover - Drawover metadata management for reviews database.

Handles:
- Tracking drawover annotations metadata
- Audit logging for drawover actions
- Querying drawover history
"""

import sqlite3
from typing import Optional, List, Dict, Any


class ReviewDrawover:
    """
    Manages drawover annotation metadata in the database.

    Actual stroke data is stored in JSON files, but metadata
    (authors, stroke count, timestamps) is tracked in DB.
    """

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    def update_drawover_metadata(
        self,
        asset_uuid: str,
        version_label: str,
        screenshot_id: int,
        stroke_count: int,
        authors: str,
        file_path: str = ''
    ) -> bool:
        """
        Update or create drawover metadata.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            screenshot_id: Screenshot ID
            stroke_count: Number of strokes
            authors: Comma-separated list of authors
            file_path: Path to the drawover JSON file

        Returns:
            True if successful
        """
        try:
            cursor = self._connection.cursor()

            # Try update first
            cursor.execute('''
                UPDATE drawover_metadata
                SET stroke_count = ?, authors = ?, modified_at = CURRENT_TIMESTAMP, file_path = ?
                WHERE asset_uuid = ? AND version_label = ? AND screenshot_id = ?
            ''', (stroke_count, authors, file_path, asset_uuid, version_label, screenshot_id))

            if cursor.rowcount == 0:
                # Insert new record
                cursor.execute('''
                    INSERT INTO drawover_metadata
                    (asset_uuid, version_label, screenshot_id, stroke_count, authors, file_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (asset_uuid, version_label, screenshot_id, stroke_count, authors, file_path))

            self._connection.commit()
            return True
        except Exception as e:
            return False

    def get_drawover_metadata(
        self,
        asset_uuid: str,
        version_label: str,
        screenshot_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get drawover metadata for a screenshot.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            screenshot_id: Screenshot ID

        Returns:
            Metadata dict or None
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT * FROM drawover_metadata
            WHERE asset_uuid = ? AND version_label = ? AND screenshot_id = ?
        ''', (asset_uuid, version_label, screenshot_id))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_version_drawovers(
        self,
        asset_uuid: str,
        version_label: str
    ) -> List[Dict[str, Any]]:
        """
        Get all drawover metadata for a version.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label

        Returns:
            List of metadata dicts
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT d.*, s.display_name as screenshot_name
            FROM drawover_metadata d
            LEFT JOIN review_screenshots s ON d.screenshot_id = s.id
            WHERE d.asset_uuid = ? AND d.version_label = ?
            ORDER BY s.display_order ASC
        ''', (asset_uuid, version_label))
        return [dict(row) for row in cursor.fetchall()]

    def delete_drawover_metadata(
        self,
        asset_uuid: str,
        version_label: str,
        screenshot_id: int
    ) -> bool:
        """Delete drawover metadata for a screenshot."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                DELETE FROM drawover_metadata
                WHERE asset_uuid = ? AND version_label = ? AND screenshot_id = ?
            ''', (asset_uuid, version_label, screenshot_id))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def log_drawover_action(
        self,
        asset_uuid: str,
        version_label: str,
        screenshot_id: int,
        action: str,
        actor: str,
        actor_role: str = '',
        stroke_id: str = '',
        details: str = ''
    ) -> Optional[int]:
        """
        Log a drawover action to the audit log.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            screenshot_id: Screenshot ID
            action: Action type (add_stroke, delete_stroke, clear, etc.)
            actor: Username performing the action
            actor_role: Role of the user
            stroke_id: Optional stroke ID
            details: Additional details

        Returns:
            Log entry ID or None
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                INSERT INTO drawover_audit_log
                (asset_uuid, version_label, screenshot_id, stroke_id, action, actor, actor_role, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (asset_uuid, version_label, screenshot_id, stroke_id, action, actor, actor_role, details))
            self._connection.commit()
            return cursor.lastrowid
        except Exception as e:
            return None

    def get_drawover_audit_log(
        self,
        asset_uuid: str,
        version_label: str,
        screenshot_id: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get drawover audit log entries.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            screenshot_id: Optional filter by screenshot
            limit: Max entries to return

        Returns:
            List of audit log entries
        """
        cursor = self._connection.cursor()

        if screenshot_id is not None:
            cursor.execute('''
                SELECT * FROM drawover_audit_log
                WHERE asset_uuid = ? AND version_label = ? AND screenshot_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (asset_uuid, version_label, screenshot_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM drawover_audit_log
                WHERE asset_uuid = ? AND version_label = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (asset_uuid, version_label, limit))

        return [dict(row) for row in cursor.fetchall()]


__all__ = ['ReviewDrawover']
