"""
ReviewCycles - Review cycle operations.

Handles:
- Creating and closing review cycles
- Linking sessions to cycles
- Querying cycle information
- Cycle-level note aggregation
"""

import sqlite3
from typing import Optional, List, Dict, Any


class ReviewCycles:
    """
    Manages review cycle database operations.

    A review cycle spans multiple versions for a specific review phase
    (e.g., modeling, texturing). Each variant has independent cycles.
    """

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    def create_cycle(
        self,
        asset_id: str,
        cycle_type: str,
        start_version: str,
        submitted_by: str = '',
        variant_name: str = 'Base'
    ) -> Optional[int]:
        """
        Create a new review cycle for an asset variant.

        Args:
            asset_id: Asset UUID (version_group_id or asset UUID)
            cycle_type: Type from Config.REVIEW_CYCLE_TYPES
            start_version: Version label where cycle starts
            submitted_by: Username who started the cycle
            variant_name: Variant name (e.g., 'Base', 'Damaged')

        Returns:
            Cycle ID or None if failed
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                INSERT INTO review_cycles
                (asset_id, variant_name, cycle_type, start_version, submitted_by, review_state)
                VALUES (?, ?, ?, ?, ?, 'needs_review')
            ''', (asset_id, variant_name, cycle_type, start_version, submitted_by))
            self._connection.commit()
            return cursor.lastrowid
        except Exception as e:
            return None

    def get_active_cycle(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the currently active (non-finalized) review cycle for an asset.

        Args:
            asset_id: Asset UUID

        Returns:
            Cycle dict or None if no active cycle
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT * FROM review_cycles
            WHERE asset_id = ? AND end_version IS NULL
            ORDER BY created_date DESC
            LIMIT 1
        ''', (asset_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_active_cycle_for_variant(
        self,
        asset_id: str,
        variant_name: str = 'Base'
    ) -> Optional[Dict[str, Any]]:
        """
        Get the active (non-finalized) review cycle for a specific variant.

        Args:
            asset_id: Asset UUID (version_group_id)
            variant_name: Variant name

        Returns:
            Cycle dict or None if no active cycle for this variant
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT * FROM review_cycles
            WHERE asset_id = ? AND variant_name = ? AND end_version IS NULL
            ORDER BY created_date DESC
            LIMIT 1
        ''', (asset_id, variant_name))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_cycle(self, cycle_id: int) -> Optional[Dict[str, Any]]:
        """Get a cycle by ID."""
        cursor = self._connection.cursor()
        cursor.execute('SELECT * FROM review_cycles WHERE id = ?', (cycle_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_cycles_for_asset(self, asset_id: str) -> List[Dict[str, Any]]:
        """Get all review cycles for an asset, ordered by created date."""
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT * FROM review_cycles
            WHERE asset_id = ?
            ORDER BY created_date DESC
        ''', (asset_id,))
        return [dict(row) for row in cursor.fetchall()]

    def set_cycle_state(self, cycle_id: int, review_state: str) -> bool:
        """Update the review state of a cycle."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                UPDATE review_cycles SET review_state = ?
                WHERE id = ?
            ''', (review_state, cycle_id))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def close_cycle(
        self,
        cycle_id: int,
        end_version: str,
        finalized_by: str = ''
    ) -> bool:
        """
        Close a review cycle (mark as final).

        Args:
            cycle_id: Cycle ID
            end_version: The final version in this cycle
            finalized_by: Username who finalized

        Returns:
            True if successful
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                UPDATE review_cycles
                SET end_version = ?,
                    review_state = 'final',
                    finalized_by = ?,
                    finalized_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (end_version, finalized_by, cycle_id))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def link_session_to_cycle(self, session_id: int, cycle_id: int) -> bool:
        """Link a review session to a cycle."""
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

    def get_cycle_sessions(self, cycle_id: int) -> List[Dict[str, Any]]:
        """Get all sessions linked to a cycle."""
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT * FROM review_sessions
            WHERE cycle_id = ?
            ORDER BY version_label ASC
        ''', (cycle_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_cycle_notes(
        self,
        cycle_id: int,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all notes from all sessions in a cycle.

        Returns notes grouped by version, with version_label included.
        """
        cursor = self._connection.cursor()

        if include_deleted:
            cursor.execute('''
                SELECT n.*, s.version_label, sc.display_name as screenshot_name
                FROM review_notes n
                JOIN review_sessions s ON n.session_id = s.id
                LEFT JOIN review_screenshots sc ON n.screenshot_id = sc.id
                WHERE s.cycle_id = ?
                ORDER BY s.version_label ASC, n.screenshot_id NULLS FIRST, n.created_date ASC
            ''', (cycle_id,))
        else:
            cursor.execute('''
                SELECT n.*, s.version_label, sc.display_name as screenshot_name
                FROM review_notes n
                JOIN review_sessions s ON n.session_id = s.id
                LEFT JOIN review_screenshots sc ON n.screenshot_id = sc.id
                WHERE s.cycle_id = ? AND n.deleted = 0
                ORDER BY s.version_label ASC, n.screenshot_id NULLS FIRST, n.created_date ASC
            ''', (cycle_id,))

        return [dict(row) for row in cursor.fetchall()]

    def get_cycle_note_counts(self, cycle_id: int) -> Dict[str, int]:
        """
        Get note status counts across all sessions in a cycle.

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
            WHERE s.cycle_id = ? AND n.deleted = 0
        ''', (cycle_id,))

        row = cursor.fetchone()
        if row:
            return {
                'open': row['open_count'] or 0,
                'addressed': row['addressed_count'] or 0,
                'approved': row['approved_count'] or 0,
                'total': row['total'] or 0
            }
        return {'open': 0, 'addressed': 0, 'approved': 0, 'total': 0}


__all__ = ['ReviewCycles']
