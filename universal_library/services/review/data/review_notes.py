"""
ReviewNotes - Note CRUD operations for reviews database.

Handles:
- Creating, reading, updating, deleting notes
- Note status transitions (open -> addressed -> approved)
- Soft delete and restore functionality
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any


class ReviewNotes:
    """
    Manages review note database operations.

    Notes follow a 3-state workflow:
    - open: Initial state, needs attention
    - addressed: Artist claims to have fixed it
    - approved: Lead confirms the fix
    """

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    def get_notes_for_version(
        self,
        asset_uuid: str,
        version_label: str,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all notes for a specific asset version.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            include_deleted: Include soft-deleted notes

        Returns:
            List of note dicts with screenshot info
        """
        cursor = self._connection.cursor()

        if include_deleted:
            cursor.execute('''
                SELECT n.*, s.display_name as screenshot_name
                FROM review_notes n
                JOIN review_sessions rs ON n.session_id = rs.id
                LEFT JOIN review_screenshots s ON n.screenshot_id = s.id
                WHERE rs.asset_uuid = ? AND rs.version_label = ?
                ORDER BY n.screenshot_id NULLS FIRST, n.created_date ASC
            ''', (asset_uuid, version_label))
        else:
            cursor.execute('''
                SELECT n.*, s.display_name as screenshot_name
                FROM review_notes n
                JOIN review_sessions rs ON n.session_id = rs.id
                LEFT JOIN review_screenshots s ON n.screenshot_id = s.id
                WHERE rs.asset_uuid = ? AND rs.version_label = ? AND n.deleted = 0
                ORDER BY n.screenshot_id NULLS FIRST, n.created_date ASC
            ''', (asset_uuid, version_label))

        return [dict(row) for row in cursor.fetchall()]

    def get_notes_for_screenshot(
        self,
        screenshot_id: int,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Get notes attached to a specific screenshot."""
        cursor = self._connection.cursor()

        if include_deleted:
            cursor.execute('''
                SELECT * FROM review_notes
                WHERE screenshot_id = ?
                ORDER BY created_date ASC
            ''', (screenshot_id,))
        else:
            cursor.execute('''
                SELECT * FROM review_notes
                WHERE screenshot_id = ? AND deleted = 0
                ORDER BY created_date ASC
            ''', (screenshot_id,))

        return [dict(row) for row in cursor.fetchall()]

    def add_note(
        self,
        asset_uuid: str,
        version_label: str,
        text: str,
        screenshot_id: Optional[int] = None,
        author: str = '',
        author_role: str = 'artist'
    ) -> Optional[int]:
        """
        Add a new review note.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            text: Note content
            screenshot_id: Optional screenshot to attach to
            author: Note author username
            author_role: Author role (artist, lead, admin)

        Returns:
            Note ID or None if failed
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

        try:
            cursor.execute('''
                INSERT INTO review_notes (session_id, screenshot_id, note, author, author_role)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, screenshot_id, text, author, author_role))
            self._connection.commit()

            # Update session activity
            cursor.execute('''
                UPDATE review_sessions SET last_activity = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (session_id,))
            self._connection.commit()

            return cursor.lastrowid
        except Exception as e:
            return None

    def update_note(self, note_id: int, text: str) -> bool:
        """Update note text."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                UPDATE review_notes
                SET note = ?, modified_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (text, note_id))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def get_note_by_id(self, note_id: int) -> Optional[Dict[str, Any]]:
        """Get a note by ID."""
        cursor = self._connection.cursor()
        cursor.execute('SELECT * FROM review_notes WHERE id = ?', (note_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def soft_delete_note(self, note_id: int, deleted_by: str = '') -> bool:
        """Soft delete a note (mark as deleted but keep in database)."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                UPDATE review_notes
                SET deleted = 1, deleted_by = ?, deleted_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (deleted_by, note_id))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def restore_note(self, note_id: int) -> bool:
        """Restore a soft-deleted note."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                UPDATE review_notes
                SET deleted = 0, deleted_by = NULL, deleted_at = NULL
                WHERE id = ?
            ''', (note_id,))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def delete_note(self, note_id: int, deleted_by: str = '') -> bool:
        """Soft delete a note (alias for soft_delete_note)."""
        return self.soft_delete_note(note_id, deleted_by)

    def hard_delete_note(self, note_id: int) -> bool:
        """Permanently delete a note from the database."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('DELETE FROM review_notes WHERE id = ?', (note_id,))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def set_note_resolved(
        self,
        note_id: int,
        resolved: bool,
        resolved_by: str = ''
    ) -> bool:
        """Set the legacy resolved flag on a note."""
        try:
            cursor = self._connection.cursor()
            if resolved:
                cursor.execute('''
                    UPDATE review_notes
                    SET resolved = 1, resolved_by = ?, resolved_date = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (resolved_by, note_id))
            else:
                cursor.execute('''
                    UPDATE review_notes
                    SET resolved = 0, resolved_by = NULL, resolved_date = NULL
                    WHERE id = ?
                ''', (note_id,))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def set_note_status(
        self,
        note_id: int,
        status: str,
        actor: str = '',
        actor_role: str = ''
    ) -> bool:
        """
        Set note status directly.

        Args:
            note_id: Note ID
            status: New status (open, addressed, approved)
            actor: Username making the change
            actor_role: Role of the user

        Returns:
            True if successful
        """
        try:
            cursor = self._connection.cursor()
            now = datetime.now().isoformat()

            if status == 'addressed':
                cursor.execute('''
                    UPDATE review_notes
                    SET note_status = 'addressed', addressed_by = ?, addressed_date = ?
                    WHERE id = ?
                ''', (actor, now, note_id))
            elif status == 'approved':
                cursor.execute('''
                    UPDATE review_notes
                    SET note_status = 'approved', approved_by = ?, approved_date = ?,
                        resolved = 1, resolved_by = ?, resolved_date = ?
                    WHERE id = ?
                ''', (actor, now, actor, now, note_id))
            else:  # open
                cursor.execute('''
                    UPDATE review_notes
                    SET note_status = 'open',
                        addressed_by = NULL, addressed_date = NULL,
                        approved_by = NULL, approved_date = NULL,
                        resolved = 0, resolved_by = NULL, resolved_date = NULL
                    WHERE id = ?
                ''', (note_id,))

            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def mark_note_addressed(
        self,
        note_id: int,
        addressed_by: str = '',
        addressed_role: str = ''
    ) -> bool:
        """Mark note as addressed by artist."""
        return self.set_note_status(note_id, 'addressed', addressed_by, addressed_role)

    def approve_note(
        self,
        note_id: int,
        approved_by: str = '',
        approved_role: str = ''
    ) -> bool:
        """Approve a note (lead confirms the fix)."""
        return self.set_note_status(note_id, 'approved', approved_by, approved_role)

    def reopen_note(
        self,
        note_id: int,
        reopened_by: str = '',
        reopened_role: str = ''
    ) -> bool:
        """Reopen a note back to 'open' status."""
        return self.set_note_status(note_id, 'open', reopened_by, reopened_role)

    def get_note_status_counts(
        self,
        asset_uuid: str,
        version_label: str
    ) -> Dict[str, int]:
        """
        Get counts of notes by status for a version.

        Returns:
            Dict with 'open', 'addressed', 'approved', 'total' counts
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT
                SUM(CASE WHEN n.note_status = 'open' THEN 1 ELSE 0 END) as open_count,
                SUM(CASE WHEN n.note_status = 'addressed' THEN 1 ELSE 0 END) as addressed_count,
                SUM(CASE WHEN n.note_status = 'approved' THEN 1 ELSE 0 END) as approved_count,
                COUNT(*) as total
            FROM review_notes n
            JOIN review_sessions s ON n.session_id = s.id
            WHERE s.asset_uuid = ? AND s.version_label = ? AND n.deleted = 0
        ''', (asset_uuid, version_label))

        row = cursor.fetchone()
        if row:
            return {
                'open': row['open_count'] or 0,
                'addressed': row['addressed_count'] or 0,
                'approved': row['approved_count'] or 0,
                'total': row['total'] or 0
            }
        return {'open': 0, 'addressed': 0, 'approved': 0, 'total': 0}


__all__ = ['ReviewNotes']
