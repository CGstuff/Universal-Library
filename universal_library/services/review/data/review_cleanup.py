"""
ReviewCleanup - Cleanup and maintenance operations.

Handles:
- Cleaning up orphaned sessions
- Archiving inactive sessions
- Purging deleted notes
- Getting statistics
"""

import sqlite3
from typing import Dict, Any


class ReviewCleanup:
    """
    Manages cleanup and maintenance operations for the reviews database.

    Provides methods for housekeeping tasks that can be run periodically
    or on-demand to keep the database tidy.
    """

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    def cleanup_orphaned_sessions(self) -> int:
        """
        Remove sessions that have no notes and no screenshots.

        Returns:
            Number of sessions deleted
        """
        cursor = self._connection.cursor()

        cursor.execute('''
            DELETE FROM review_sessions
            WHERE id NOT IN (
                SELECT DISTINCT session_id FROM review_notes
            ) AND id NOT IN (
                SELECT DISTINCT session_id FROM review_screenshots
            ) AND review_state IS NULL
        ''')

        deleted = cursor.rowcount
        self._connection.commit()
        return deleted

    def archive_inactive_sessions(self, days_inactive: int = 90) -> int:
        """
        Archive sessions that have been inactive for a period.

        Args:
            days_inactive: Number of days of inactivity

        Returns:
            Number of sessions archived
        """
        cursor = self._connection.cursor()

        cursor.execute('''
            UPDATE review_sessions
            SET status = 'archived'
            WHERE status = 'open'
              AND last_activity < datetime('now', ? || ' days')
        ''', (f'-{days_inactive}',))

        archived = cursor.rowcount
        self._connection.commit()
        return archived

    def delete_archived_sessions(self) -> int:
        """
        Permanently delete archived sessions.

        Returns:
            Number of sessions deleted
        """
        cursor = self._connection.cursor()

        cursor.execute('''
            DELETE FROM review_sessions
            WHERE status = 'archived'
        ''')

        deleted = cursor.rowcount
        self._connection.commit()
        return deleted

    def purge_deleted_notes(self, days_old: int = 30) -> int:
        """
        Permanently delete soft-deleted notes older than specified days.

        Args:
            days_old: Minimum age in days for deletion

        Returns:
            Number of notes purged
        """
        cursor = self._connection.cursor()

        cursor.execute('''
            DELETE FROM review_notes
            WHERE deleted = 1
              AND deleted_at < datetime('now', ? || ' days')
        ''', (f'-{days_old}',))

        purged = cursor.rowcount
        self._connection.commit()
        return purged

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the reviews database.

        Returns:
            Dict with various counts and metrics
        """
        cursor = self._connection.cursor()

        stats = {}

        # Session counts
        cursor.execute('SELECT COUNT(*) FROM review_sessions')
        stats['total_sessions'] = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM review_sessions WHERE status = ?', ('open',))
        stats['open_sessions'] = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM review_sessions WHERE status = ?', ('archived',))
        stats['archived_sessions'] = cursor.fetchone()[0]

        # Cycle counts
        cursor.execute('SELECT COUNT(*) FROM review_cycles')
        stats['total_cycles'] = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM review_cycles WHERE end_version IS NULL')
        stats['active_cycles'] = cursor.fetchone()[0]

        # Note counts
        cursor.execute('SELECT COUNT(*) FROM review_notes WHERE deleted = 0')
        stats['total_notes'] = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM review_notes WHERE deleted = 1')
        stats['deleted_notes'] = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM review_notes WHERE note_status = ?', ('open',))
        stats['open_notes'] = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM review_notes WHERE note_status = ?', ('addressed',))
        stats['addressed_notes'] = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM review_notes WHERE note_status = ?', ('approved',))
        stats['approved_notes'] = cursor.fetchone()[0]

        # Screenshot counts
        cursor.execute('SELECT COUNT(*) FROM review_screenshots')
        stats['total_screenshots'] = cursor.fetchone()[0]

        # Drawover counts
        cursor.execute('SELECT COUNT(*) FROM drawover_metadata')
        stats['total_drawovers'] = cursor.fetchone()[0]

        # User counts
        cursor.execute('SELECT COUNT(*) FROM studio_users WHERE is_active = 1')
        stats['active_users'] = cursor.fetchone()[0]

        return stats


__all__ = ['ReviewCleanup']
