"""
ReviewStatus - Status queries for UI display.

Handles:
- Getting comprehensive review status for badges
- Batch status queries for grid display
- Combining cycle and session info
"""

import sqlite3
from typing import Optional, Dict, Any, List


class ReviewStatus:
    """
    Provides review status queries optimized for UI display.

    Combines information from sessions, cycles, and notes
    into status summaries suitable for badges and tooltips.
    """

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    def get_review_status(
        self,
        asset_uuid: str,
        version_label: str,
        version_group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive review status for an asset version.

        This is the main method for getting all review info for display.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            version_group_id: Optional asset family ID for cycle lookup

        Returns:
            Dict with:
                - review_state: Current state (needs_review, in_progress, etc.)
                - cycle_id: Active cycle ID (if any)
                - cycle_type: Cycle type (if in a cycle)
                - cycle_start: Start version of cycle
                - note_counts: Dict of open/addressed/approved counts
                - has_notes: Whether any notes exist
                - has_open_notes: Whether any open notes exist
                - is_in_cycle: Whether version is part of a cycle
        """
        cursor = self._connection.cursor()

        result = {
            'review_state': None,
            'cycle_id': None,
            'cycle_type': None,
            'cycle_start': None,
            'note_counts': {'open': 0, 'addressed': 0, 'approved': 0, 'total': 0},
            'has_notes': False,
            'has_open_notes': False,
            'is_in_cycle': False,
        }

        # Get session info
        cursor.execute('''
            SELECT id, review_state, cycle_id
            FROM review_sessions
            WHERE asset_uuid = ? AND version_label = ?
        ''', (asset_uuid, version_label))
        session_row = cursor.fetchone()

        session_id = None
        if session_row:
            session_id = session_row['id']
            result['review_state'] = session_row['review_state']
            cycle_id = session_row['cycle_id']

            if cycle_id:
                result['cycle_id'] = cycle_id
                result['is_in_cycle'] = True

                # Get cycle info
                cursor.execute('''
                    SELECT cycle_type, start_version, review_state
                    FROM review_cycles WHERE id = ?
                ''', (cycle_id,))
                cycle_row = cursor.fetchone()
                if cycle_row:
                    result['cycle_type'] = cycle_row['cycle_type']
                    result['cycle_start'] = cycle_row['start_version']
                    # Use cycle's review_state instead of session's
                    result['review_state'] = cycle_row['review_state']

        # If no cycle from session, check for active cycle using version_group_id
        if not result['is_in_cycle'] and version_group_id:
            cursor.execute('''
                SELECT id, cycle_type, start_version, review_state
                FROM review_cycles
                WHERE asset_id = ? AND end_version IS NULL
                ORDER BY created_date DESC
                LIMIT 1
            ''', (version_group_id,))
            active_cycle = cursor.fetchone()

            if active_cycle:
                cycle_start = active_cycle['start_version']
                # Only include if version >= cycle start
                if version_label >= cycle_start:
                    result['cycle_id'] = active_cycle['id']
                    result['cycle_type'] = active_cycle['cycle_type']
                    result['cycle_start'] = cycle_start
                    result['review_state'] = active_cycle['review_state']
                    result['is_in_cycle'] = True

        # Get note counts
        if session_id:
            cursor.execute('''
                SELECT
                    SUM(CASE WHEN note_status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN note_status = 'addressed' THEN 1 ELSE 0 END) as addressed_count,
                    SUM(CASE WHEN note_status = 'approved' THEN 1 ELSE 0 END) as approved_count,
                    COUNT(*) as total
                FROM review_notes
                WHERE session_id = ? AND deleted = 0
            ''', (session_id,))
            counts_row = cursor.fetchone()
            if counts_row:
                result['note_counts'] = {
                    'open': counts_row['open_count'] or 0,
                    'addressed': counts_row['addressed_count'] or 0,
                    'approved': counts_row['approved_count'] or 0,
                    'total': counts_row['total'] or 0
                }
                result['has_notes'] = (counts_row['total'] or 0) > 0
                result['has_open_notes'] = (counts_row['open_count'] or 0) > 0

        return result

    def get_review_status_batch(
        self,
        asset_version_pairs: List[tuple]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get review status for multiple asset versions at once.

        Optimized for grid display where many statuses are needed.

        Args:
            asset_version_pairs: List of (asset_uuid, version_label) tuples

        Returns:
            Dict mapping 'uuid:version' -> status dict
        """
        if not asset_version_pairs:
            return {}

        result = {}

        for asset_uuid, version_label in asset_version_pairs:
            key = f"{asset_uuid}:{version_label}"
            result[key] = self.get_review_status(asset_uuid, version_label)

        return result

    def get_assets_with_open_notes(self) -> List[Dict[str, Any]]:
        """
        Get all assets that have open review notes.

        Returns:
            List of session dicts with open note counts
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT s.asset_uuid, s.version_label, s.review_state,
                   COUNT(n.id) as open_note_count
            FROM review_sessions s
            JOIN review_notes n ON n.session_id = s.id
            WHERE n.note_status = 'open' AND n.deleted = 0
            GROUP BY s.asset_uuid, s.version_label
            ORDER BY s.last_activity DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]

    def get_assets_awaiting_approval(self) -> List[Dict[str, Any]]:
        """
        Get assets that have addressed notes waiting for approval.

        Returns:
            List of session dicts with addressed note counts
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT s.asset_uuid, s.version_label, s.review_state,
                   COUNT(n.id) as addressed_note_count
            FROM review_sessions s
            JOIN review_notes n ON n.session_id = s.id
            WHERE n.note_status = 'addressed' AND n.deleted = 0
            GROUP BY s.asset_uuid, s.version_label
            ORDER BY s.last_activity DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]


__all__ = ['ReviewStatus']
