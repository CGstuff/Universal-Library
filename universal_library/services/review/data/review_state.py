"""
ReviewState - Review state transitions for reviews database.

Handles:
- Setting review state (needs_review, in_progress, approved, final)
- Submitting for review
- Finalizing reviews
- Reopening reviews
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple


class ReviewState:
    """
    Manages review state transitions.

    States flow:
    - needs_review: Waiting for review to start
    - in_progress: Under active review
    - approved: Review passed, ready for finalization
    - final: Locked, no more changes
    """

    VALID_STATES = ['needs_review', 'in_progress', 'approved', 'final']

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    def set_review_state(
        self,
        asset_uuid: str,
        version_label: str,
        review_state: str,
        user: str = ''
    ) -> Tuple[bool, str]:
        """
        Set review state for an asset version.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            review_state: New state
            user: Username making the change

        Returns:
            Tuple of (success, message)
        """
        if review_state not in self.VALID_STATES:
            return False, f"Invalid state: {review_state}"

        cursor = self._connection.cursor()

        # Get or create session
        cursor.execute('''
            SELECT id FROM review_sessions
            WHERE asset_uuid = ? AND version_label = ?
        ''', (asset_uuid, version_label))
        row = cursor.fetchone()

        if not row:
            cursor.execute('''
                INSERT INTO review_sessions (asset_uuid, version_label)
                VALUES (?, ?)
            ''', (asset_uuid, version_label))
            self._connection.commit()
            cursor.execute('''
                SELECT id FROM review_sessions
                WHERE asset_uuid = ? AND version_label = ?
            ''', (asset_uuid, version_label))
            row = cursor.fetchone()

        session_id = row[0]

        try:
            now = datetime.now().isoformat()
            updates = {'review_state': review_state}

            if review_state == 'approved':
                updates['approved_date'] = now
            elif review_state == 'final':
                updates['finalized_date'] = now
                updates['finalized_by'] = user
            elif review_state == 'in_progress':
                updates['submitted_for_review_date'] = now
                updates['submitted_by'] = user

            set_clause = ', '.join([f'{k} = ?' for k in updates.keys()])
            params = list(updates.values()) + [session_id]

            cursor.execute(f'''
                UPDATE review_sessions
                SET {set_clause}
                WHERE id = ?
            ''', params)
            self._connection.commit()

            return True, f"State changed to {review_state}"
        except Exception as e:
            return False, f"Failed to set state: {e}"

    def submit_for_review(
        self,
        asset_uuid: str,
        version_label: str,
        user: str = ''
    ) -> Tuple[bool, str]:
        """
        Submit asset for review (transitions to in_progress).

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            user: Username submitting

        Returns:
            Tuple of (success, message)
        """
        cursor = self._connection.cursor()

        # Get or create session
        cursor.execute('''
            SELECT id, review_state FROM review_sessions
            WHERE asset_uuid = ? AND version_label = ?
        ''', (asset_uuid, version_label))
        row = cursor.fetchone()

        if row:
            session_id = row[0]
            current_state = row[1]
            if current_state == 'final':
                return False, "Cannot submit - already finalized"
        else:
            cursor.execute('''
                INSERT INTO review_sessions (asset_uuid, version_label)
                VALUES (?, ?)
            ''', (asset_uuid, version_label))
            self._connection.commit()
            session_id = cursor.lastrowid

        try:
            cursor.execute('''
                UPDATE review_sessions
                SET review_state = 'in_progress',
                    submitted_for_review_date = CURRENT_TIMESTAMP,
                    submitted_by = ?
                WHERE id = ?
            ''', (user, session_id))
            self._connection.commit()
            return True, "Submitted for review"
        except Exception as e:
            return False, f"Failed to submit: {e}"

    def finalize_review(
        self,
        asset_uuid: str,
        version_label: str,
        user: str = ''
    ) -> Tuple[bool, str]:
        """
        Finalize review (transitions to final state).

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            user: Username finalizing

        Returns:
            Tuple of (success, message)
        """
        cursor = self._connection.cursor()

        cursor.execute('''
            SELECT id, review_state FROM review_sessions
            WHERE asset_uuid = ? AND version_label = ?
        ''', (asset_uuid, version_label))
        row = cursor.fetchone()

        if not row:
            return False, "No review session found"

        session_id = row[0]
        current_state = row[1]

        if current_state == 'final':
            return True, "Already finalized"

        if current_state != 'approved':
            return False, f"Cannot finalize from '{current_state}' state - must be approved first"

        try:
            cursor.execute('''
                UPDATE review_sessions
                SET review_state = 'final',
                    finalized_date = CURRENT_TIMESTAMP,
                    finalized_by = ?
                WHERE id = ?
            ''', (user, session_id))
            self._connection.commit()
            return True, "Review finalized"
        except Exception as e:
            return False, f"Failed to finalize: {e}"

    def reopen_review(
        self,
        asset_uuid: str,
        version_label: str,
        target_state: str = 'needs_review'
    ) -> Tuple[bool, str]:
        """
        Reopen a finalized or approved review.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            target_state: State to reopen to

        Returns:
            Tuple of (success, message)
        """
        if target_state not in ['needs_review', 'in_progress']:
            return False, "Can only reopen to 'needs_review' or 'in_progress'"

        cursor = self._connection.cursor()

        cursor.execute('''
            SELECT id, review_state FROM review_sessions
            WHERE asset_uuid = ? AND version_label = ?
        ''', (asset_uuid, version_label))
        row = cursor.fetchone()

        if not row:
            return False, "No review session found"

        session_id = row[0]

        try:
            cursor.execute('''
                UPDATE review_sessions
                SET review_state = ?,
                    approved_date = NULL,
                    finalized_date = NULL,
                    finalized_by = NULL
                WHERE id = ?
            ''', (target_state, session_id))
            self._connection.commit()
            return True, f"Review reopened to '{target_state}'"
        except Exception as e:
            return False, f"Failed to reopen: {e}"

    def get_assets_by_review_state(
        self,
        review_state: str
    ) -> List[Dict[str, Any]]:
        """
        Get all assets in a specific review state.

        Args:
            review_state: State to filter by

        Returns:
            List of session dicts
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT * FROM review_sessions
            WHERE review_state = ?
            ORDER BY last_activity DESC
        ''', (review_state,))
        return [dict(row) for row in cursor.fetchall()]

    def get_all_review_states(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all sessions grouped by review state.

        Returns:
            Dict mapping state -> list of sessions
        """
        result = {state: [] for state in self.VALID_STATES}

        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT * FROM review_sessions
            WHERE review_state IS NOT NULL
            ORDER BY last_activity DESC
        ''')

        for row in cursor.fetchall():
            state = row['review_state']
            if state in result:
                result[state].append(dict(row))

        return result


__all__ = ['ReviewState']
