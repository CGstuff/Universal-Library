"""
ReviewSessions - Session management for reviews database.

Handles:
- Creating and retrieving review sessions
- Session status updates
- Session-cycle linking
"""

import sqlite3
from typing import Optional, Dict, Any


class ReviewSessions:
    """
    Manages review session database operations.

    A session represents a review context for a specific asset version.
    Multiple sessions can be linked to a single review cycle.
    """

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    def get_or_create_session(
        self,
        asset_uuid: str,
        version_label: str
    ) -> Optional[int]:
        """
        Get existing session or create new one.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label (e.g., 'v001')

        Returns:
            Session ID or None if failed
        """
        cursor = self._connection.cursor()

        # Try to get existing
        cursor.execute('''
            SELECT id FROM review_sessions
            WHERE asset_uuid = ? AND version_label = ?
        ''', (asset_uuid, version_label))

        row = cursor.fetchone()
        if row:
            return row[0]

        # Create new session
        try:
            cursor.execute('''
                INSERT INTO review_sessions (asset_uuid, version_label)
                VALUES (?, ?)
            ''', (asset_uuid, version_label))
            self._connection.commit()
            return cursor.lastrowid
        except Exception as e:
            return None

    def get_session(
        self,
        asset_uuid: str,
        version_label: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get session by asset UUID and version label.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label

        Returns:
            Session dict or None
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT * FROM review_sessions
            WHERE asset_uuid = ? AND version_label = ?
        ''', (asset_uuid, version_label))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_session_by_id(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get session by ID."""
        cursor = self._connection.cursor()
        cursor.execute('SELECT * FROM review_sessions WHERE id = ?', (session_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_session_status(
        self,
        session_id: int,
        status: str,
        update_activity: bool = True
    ) -> bool:
        """
        Update session status.

        Args:
            session_id: Session ID
            status: New status (e.g., 'open', 'archived')
            update_activity: Also update last_activity timestamp

        Returns:
            True if successful
        """
        try:
            cursor = self._connection.cursor()
            if update_activity:
                cursor.execute('''
                    UPDATE review_sessions
                    SET status = ?, last_activity = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, session_id))
            else:
                cursor.execute('''
                    UPDATE review_sessions SET status = ?
                    WHERE id = ?
                ''', (status, session_id))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def update_session_activity(self, session_id: int) -> bool:
        """Update last_activity timestamp for a session."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                UPDATE review_sessions
                SET last_activity = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (session_id,))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception:
            return False

    def link_to_cycle(self, session_id: int, cycle_id: int) -> bool:
        """Link a session to a review cycle."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                UPDATE review_sessions SET cycle_id = ?
                WHERE id = ?
            ''', (cycle_id, session_id))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False


__all__ = ['ReviewSessions']
