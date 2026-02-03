"""
ReviewAudit - Audit logging for review operations.

Handles:
- Logging review actions (note changes, status changes, etc.)
- Querying audit history
- Recent activity tracking
"""

import sqlite3
from typing import Optional, List, Dict, Any


class ReviewAudit:
    """
    Manages audit logging for review operations.

    Provides a history of who did what and when for compliance
    and debugging purposes.
    """

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    def log_action(
        self,
        note_id: Optional[int],
        action: str,
        actor: str,
        actor_role: str = '',
        details: str = ''
    ) -> Optional[int]:
        """
        Log an action to the audit log.

        Args:
            note_id: Related note ID (can be None)
            action: Action type (add, edit, delete, status_change, etc.)
            actor: Username performing the action
            actor_role: Role of the user
            details: Additional details as text/JSON

        Returns:
            Log entry ID or None if failed
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                INSERT INTO review_audit_log (note_id, action, actor, actor_role, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (note_id, action, actor, actor_role, details))
            self._connection.commit()
            return cursor.lastrowid
        except Exception as e:
            return None

    def get_audit_log(
        self,
        note_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get audit log entries.

        Args:
            note_id: Optional filter by note ID
            limit: Max entries to return

        Returns:
            List of audit log entries
        """
        cursor = self._connection.cursor()

        if note_id is not None:
            cursor.execute('''
                SELECT * FROM review_audit_log
                WHERE note_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (note_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM review_audit_log
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

        return [dict(row) for row in cursor.fetchall()]

    def get_recent_activity(
        self,
        limit: int = 50,
        actor: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent activity across all notes.

        Args:
            limit: Max entries to return
            actor: Optional filter by actor username

        Returns:
            List of audit entries with note info
        """
        cursor = self._connection.cursor()

        if actor:
            cursor.execute('''
                SELECT a.*, n.note as note_text, s.asset_uuid, s.version_label
                FROM review_audit_log a
                LEFT JOIN review_notes n ON a.note_id = n.id
                LEFT JOIN review_sessions s ON n.session_id = s.id
                WHERE a.actor = ?
                ORDER BY a.timestamp DESC
                LIMIT ?
            ''', (actor, limit))
        else:
            cursor.execute('''
                SELECT a.*, n.note as note_text, s.asset_uuid, s.version_label
                FROM review_audit_log a
                LEFT JOIN review_notes n ON a.note_id = n.id
                LEFT JOIN review_sessions s ON n.session_id = s.id
                ORDER BY a.timestamp DESC
                LIMIT ?
            ''', (limit,))

        return [dict(row) for row in cursor.fetchall()]


__all__ = ['ReviewAudit']
