"""
ReviewStateManager - Manages automatic review state transitions

This service handles the review workflow state machine with CYCLE support:

Review Cycles:
- A Review Cycle spans multiple versions for a specific phase (modeling, texturing, etc.)
- When an artist submits v001 for review, a cycle is created
- New versions (v002, v003) auto-join the active cycle
- Notes are per-version, but the cycle tracks overall state
- When marked final, the cycle is closed and cannot be reopened

Workflow States (per cycle):
- None -> needs_review (artist submits for review, cycle created)
- needs_review -> in_review (lead adds first comment)
- in_review -> in_progress (artist marks first note as "addressed")
- in_progress -> approved (lead approves all notes)
- approved -> in_review (lead adds more comments - pushback)
- in_progress -> in_review (lead adds more comments while artist fixing)
- approved -> final (lead explicitly finalizes, cycle closed)

Note States (3-state):
- open: Lead added comment, awaiting artist
- addressed: Artist marked "I fixed it", awaiting lead approval
- approved: Lead approved the fix
"""

from typing import Optional, Tuple, Dict, List
from PyQt6.QtCore import QObject, pyqtSignal

from ..config import Config, REVIEW_CYCLE_TYPES
from .review_database import get_review_database


class ReviewStateManager(QObject):
    """
    Manages automatic review state transitions based on comment activity.

    Now cycle-aware: Review state is tracked at the CYCLE level, not version level.
    A cycle spans multiple versions for a review phase (e.g., modeling, texturing).

    Signals:
        state_changed: Emitted when review state changes (asset_uuid, version_label, old_state, new_state)
        submitted_for_review: Emitted when asset is submitted for review (asset_uuid, version_label)
        finalized: Emitted when asset is marked as final (asset_uuid, version_label)
        cycle_created: Emitted when a new review cycle is created (asset_uuid, cycle_id, cycle_type)
        cycle_closed: Emitted when a review cycle is closed/finalized (asset_uuid, cycle_id)
    """

    state_changed = pyqtSignal(str, str, str, str)  # uuid, version, old_state, new_state
    submitted_for_review = pyqtSignal(str, str)  # uuid, version
    finalized = pyqtSignal(str, str)  # uuid, version
    cycle_created = pyqtSignal(str, int, str)  # asset_uuid, cycle_id, cycle_type
    cycle_closed = pyqtSignal(str, int)  # asset_uuid, cycle_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._review_db = get_review_database()

    # =========================================================================
    # Cycle Management
    # =========================================================================

    def get_active_cycle(self, asset_uuid: str) -> Optional[Dict]:
        """
        Get the active (non-final) review cycle for an asset.

        Args:
            asset_uuid: Asset UUID

        Returns:
            Cycle dict or None if no active cycle
        """
        return self._review_db.get_active_cycle(asset_uuid)

    def get_cycle(self, cycle_id: int) -> Optional[Dict]:
        """Get a specific cycle by ID."""
        return self._review_db.get_cycle(cycle_id)

    def get_cycles_for_asset(self, asset_uuid: str) -> List[Dict]:
        """Get all cycles (active and closed) for an asset."""
        return self._review_db.get_cycles_for_asset(asset_uuid)

    def get_cycle_for_version(self, asset_uuid: str, version_label: str) -> Optional[Dict]:
        """
        Get the cycle that a specific version belongs to.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label

        Returns:
            Cycle dict or None if version is not in any cycle
        """
        session = self._review_db.get_session(asset_uuid, version_label)
        if session and session.get('cycle_id'):
            return self._review_db.get_cycle(session['cycle_id'])
        return None

    def link_version_to_active_cycle(
        self,
        asset_uuid: str,
        version_label: str
    ) -> Tuple[bool, str]:
        """
        Auto-join a new version to the active cycle for the asset.

        Called when a new version is created/exported.

        Args:
            asset_uuid: Asset UUID
            version_label: New version label

        Returns:
            Tuple of (success, message)
        """
        active_cycle = self.get_active_cycle(asset_uuid)
        if not active_cycle:
            return False, "No active cycle to join"

        # Ensure session exists for this version
        # get_or_create_session returns the session ID (int), not a dict
        session_id = self._review_db.get_or_create_session(asset_uuid, version_label)
        if not session_id:
            return False, "Failed to create session for version"

        # Link session to cycle
        success = self._review_db.link_session_to_cycle(session_id, active_cycle['id'])
        if success:
            return True, f"Version {version_label} joined cycle: {active_cycle['cycle_type']}"
        return False, "Failed to link version to cycle"

    # =========================================================================
    # State Queries (Cycle-Aware)
    # =========================================================================

    def get_current_state(self, asset_uuid: str, version_label: str) -> Optional[str]:
        """
        Get the current review state for an asset version.

        Now cycle-aware: Returns the cycle's state if the version belongs to a cycle.
        """
        # First check if version belongs to a cycle
        cycle = self.get_cycle_for_version(asset_uuid, version_label)
        if cycle:
            return cycle.get('review_state')

        # Fallback to session state for backward compatibility
        session = self._review_db.get_session(asset_uuid, version_label)
        return session.get('review_state') if session else None

    def get_cycle_state(self, asset_uuid: str) -> Optional[str]:
        """
        Get the review state of the active cycle for an asset.

        Returns None if no active cycle exists.
        """
        cycle = self.get_active_cycle(asset_uuid)
        return cycle.get('review_state') if cycle else None

    def is_in_review_workflow(self, asset_uuid: str, version_label: str) -> bool:
        """Check if asset version is in review workflow (belongs to a cycle)."""
        cycle = self.get_cycle_for_version(asset_uuid, version_label)
        if cycle:
            return True
        # Fallback check
        state = self.get_current_state(asset_uuid, version_label)
        return state is not None

    def has_active_cycle(self, asset_uuid: str) -> bool:
        """Check if asset has an active (non-final) review cycle."""
        return self.get_active_cycle(asset_uuid) is not None

    def can_add_comments(self, asset_uuid: str, version_label: str) -> bool:
        """
        Check if comments can be added to this asset version.

        Comments allowed when version belongs to an active (non-final) cycle.
        """
        cycle = self.get_cycle_for_version(asset_uuid, version_label)
        if cycle:
            state = cycle.get('review_state')
            return state in ('needs_review', 'in_review', 'in_progress', 'approved')
        # Fallback for legacy
        state = self.get_current_state(asset_uuid, version_label)
        return state in ('needs_review', 'in_review', 'in_progress', 'approved')

    def can_start_new_cycle(self, asset_uuid: str) -> bool:
        """
        Check if a new review cycle can be started for the asset.

        Returns True if there is no active cycle.
        """
        return not self.has_active_cycle(asset_uuid)

    # =========================================================================
    # Review Submission (Creates Cycle)
    # =========================================================================

    def submit_for_review(
        self,
        asset_uuid: str,
        version_label: str,
        cycle_type: str = 'general',
        submitted_by: str = ''
    ) -> Tuple[bool, str]:
        """
        Submit asset for review by creating a new review cycle.

        Creates a new cycle for the specified phase and links the version to it.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label (will be the cycle's start_version)
            cycle_type: Type of review cycle (must be a key in REVIEW_CYCLE_TYPES)
            submitted_by: Username of who submitted

        Returns:
            Tuple of (success, message)
        """
        # Validate cycle type
        if cycle_type not in REVIEW_CYCLE_TYPES:
            valid_types = ', '.join(REVIEW_CYCLE_TYPES.keys())
            return False, f"Invalid cycle type '{cycle_type}'. Valid types: {valid_types}"

        # Check if there's already an active cycle
        if self.has_active_cycle(asset_uuid):
            active = self.get_active_cycle(asset_uuid)
            cycle_label = REVIEW_CYCLE_TYPES.get(active['cycle_type'], {}).get('label', active['cycle_type'])
            return False, f"Asset already has an active cycle: {cycle_label} (started at {active['start_version']})"

        # Create the cycle
        cycle_id = self._review_db.create_cycle(
            asset_id=asset_uuid,
            cycle_type=cycle_type,
            start_version=version_label,
            submitted_by=submitted_by
        )

        if not cycle_id:
            return False, "Failed to create review cycle"

        # Ensure session exists and link to cycle
        # get_or_create_session returns the session ID (int), not a dict
        session_id = self._review_db.get_or_create_session(asset_uuid, version_label)
        if session_id:
            self._review_db.link_session_to_cycle(session_id, cycle_id)
            # Also set the session's review_state for backward compatibility
            self._review_db.submit_for_review(asset_uuid, version_label, submitted_by)

        # Emit signals
        cycle_label = REVIEW_CYCLE_TYPES.get(cycle_type, {}).get('label', cycle_type)
        self.cycle_created.emit(asset_uuid, cycle_id, cycle_type)
        self.state_changed.emit(asset_uuid, version_label, '', 'needs_review')
        self.submitted_for_review.emit(asset_uuid, version_label)

        return True, f"Started {cycle_label} review cycle"

    # =========================================================================
    # State Transitions (Cycle-Aware)
    # =========================================================================

    def _update_cycle_state(
        self,
        asset_uuid: str,
        version_label: str,
        new_state: str
    ) -> bool:
        """
        Update the cycle state for an asset version.

        Updates the cycle if version belongs to one, otherwise updates the session.
        """
        cycle = self.get_cycle_for_version(asset_uuid, version_label)
        if cycle:
            return self._review_db.set_cycle_state(cycle['id'], new_state)
        # Fallback to session state for backward compatibility
        return self._review_db.set_review_state(asset_uuid, version_label, new_state)

    def on_comment_added(
        self,
        asset_uuid: str,
        version_label: str,
        author_role: str
    ) -> Tuple[Optional[str], str]:
        """
        Handle comment being added - may trigger state transition.

        Transitions (at CYCLE level):
        - 'needs_review' -> 'in_review' (if author is elevated role)
        - 'approved' -> 'in_review' (if author is elevated role - pushback)
        - 'in_progress' -> 'in_review' (if author is elevated role - more feedback)

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            author_role: Role of the comment author

        Returns:
            Tuple of (new_state or None if no change, message)
        """
        current_state = self.get_current_state(asset_uuid, version_label)
        is_elevated = author_role in Config.ELEVATED_ROLES

        # Only elevated roles trigger state transitions when adding comments
        if not is_elevated:
            return None, "No state change"

        # Transition: needs_review -> in_review (when lead comments)
        if current_state == 'needs_review':
            success = self._update_cycle_state(asset_uuid, version_label, 'in_review')
            if success:
                self.state_changed.emit(asset_uuid, version_label, 'needs_review', 'in_review')
                return 'in_review', "Review started - lead added comments"
            return None, "Failed to transition state"

        # Transition: approved -> in_review (pushback when lead adds more comments)
        if current_state == 'approved':
            success = self._update_cycle_state(asset_uuid, version_label, 'in_review')
            if success:
                self.state_changed.emit(asset_uuid, version_label, 'approved', 'in_review')
                return 'in_review', "Review reopened - lead added more comments"
            return None, "Failed to transition state"

        # Transition: in_progress -> in_review (more feedback while artist fixing)
        if current_state == 'in_progress':
            success = self._update_cycle_state(asset_uuid, version_label, 'in_review')
            if success:
                self.state_changed.emit(asset_uuid, version_label, 'in_progress', 'in_review')
                return 'in_review', "More feedback added - back to review"
            return None, "Failed to transition state"

        return None, "No state change"

    def on_note_addressed(
        self,
        asset_uuid: str,
        version_label: str
    ) -> Tuple[Optional[str], str]:
        """
        Handle note being marked as addressed by artist.

        Transition (at CYCLE level):
        - 'in_review' -> 'in_progress' (when artist starts addressing notes)

        Args:
            asset_uuid: Asset UUID
            version_label: Version label

        Returns:
            Tuple of (new_state or None if no change, message)
        """
        current_state = self.get_current_state(asset_uuid, version_label)

        # Transition: in_review -> in_progress (artist started fixing)
        if current_state == 'in_review':
            success = self._update_cycle_state(asset_uuid, version_label, 'in_progress')
            if success:
                self.state_changed.emit(asset_uuid, version_label, 'in_review', 'in_progress')
                return 'in_progress', "Artist started addressing feedback"
            return None, "Failed to transition state"

        return None, "No state change"

    def on_note_approved(
        self,
        asset_uuid: str,
        version_label: str
    ) -> Tuple[Optional[str], str]:
        """
        Handle note being approved by lead.

        Checks if ALL notes in the CYCLE are now approved and transitions if so.

        Transition (at CYCLE level):
        - 'in_progress' -> 'approved' (when all cycle notes approved by lead)
        - 'in_review' -> 'approved' (when all cycle notes approved directly)

        Args:
            asset_uuid: Asset UUID
            version_label: Version label

        Returns:
            Tuple of (new_state or None if no change, message)
        """
        current_state = self.get_current_state(asset_uuid, version_label)

        # Only transition from in_review or in_progress
        if current_state not in ('in_review', 'in_progress'):
            return None, "No state change"

        # Check if ALL notes in the CYCLE are approved
        cycle = self.get_cycle_for_version(asset_uuid, version_label)
        if cycle:
            # Get note counts for the entire cycle
            note_counts = self._review_db.get_cycle_note_counts(cycle['id'])
        else:
            # Fallback to version-level counts
            note_counts = self._review_db.get_note_status_counts(asset_uuid, version_label)

        open_count = note_counts.get('open', 0)
        addressed_count = note_counts.get('addressed', 0)

        # All notes must be approved (none open or addressed)
        if open_count == 0 and addressed_count == 0:
            success = self._update_cycle_state(asset_uuid, version_label, 'approved')
            if success:
                self.state_changed.emit(asset_uuid, version_label, current_state, 'approved')
                return 'approved', "All notes approved - cycle approved"
            return None, "Failed to transition state"

        remaining = open_count + addressed_count
        return None, f"{remaining} note(s) still need approval"

    def on_note_reopened(
        self,
        asset_uuid: str,
        version_label: str,
        actor_role: str
    ) -> Tuple[Optional[str], str]:
        """
        Handle note being reopened (set back to 'open').

        Transition (at CYCLE level):
        - 'approved' -> 'in_review' (if lead reopens a note)
        - 'in_progress' -> stays in_progress (artist can reopen their own addressed notes)

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            actor_role: Role of who reopened

        Returns:
            Tuple of (new_state or None if no change, message)
        """
        current_state = self.get_current_state(asset_uuid, version_label)
        is_elevated = actor_role in Config.ELEVATED_ROLES

        # Lead reopening in approved state pushes back to in_review
        if current_state == 'approved' and is_elevated:
            success = self._update_cycle_state(asset_uuid, version_label, 'in_review')
            if success:
                self.state_changed.emit(asset_uuid, version_label, 'approved', 'in_review')
                return 'in_review', "Note reopened - back to review"
            return None, "Failed to transition state"

        return None, "No state change"

    # Legacy method for backward compatibility
    def on_comment_resolved(
        self,
        asset_uuid: str,
        version_label: str
    ) -> Tuple[Optional[str], str]:
        """
        Handle comment being resolved (legacy - maps to on_note_approved).
        """
        return self.on_note_approved(asset_uuid, version_label)

    # =========================================================================
    # Finalization (Closes Cycle)
    # =========================================================================

    def mark_as_final(
        self,
        asset_uuid: str,
        version_label: str,
        finalized_by: str = ''
    ) -> Tuple[bool, str]:
        """
        Mark review as final and CLOSE the cycle.

        Transition: 'approved' -> 'final'
        Closes the cycle with end_version set to version_label.

        Final cycles CANNOT be reopened - must start a new cycle.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label (will be the cycle's end_version)
            finalized_by: Username of who finalized

        Returns:
            Tuple of (success, message)
        """
        current_state = self.get_current_state(asset_uuid, version_label)

        if current_state != 'approved':
            return False, f"Can only finalize from 'approved' state (current: {current_state})"

        cycle = self.get_cycle_for_version(asset_uuid, version_label)
        if cycle:
            # Close the cycle with end_version
            success = self._review_db.close_cycle(
                cycle_id=cycle['id'],
                end_version=version_label,
                finalized_by=finalized_by
            )
            if success:
                self.cycle_closed.emit(asset_uuid, cycle['id'])
                self.state_changed.emit(asset_uuid, version_label, 'approved', 'final')
                self.finalized.emit(asset_uuid, version_label)
                cycle_type = cycle.get('cycle_type', 'unknown')
                cycle_label = REVIEW_CYCLE_TYPES.get(cycle_type, {}).get('label', cycle_type)
                return True, f"{cycle_label} review cycle finalized"
            return False, "Failed to close cycle"

        # Fallback for legacy (no cycle)
        success = self._review_db.finalize_review(asset_uuid, version_label, finalized_by)

        if success:
            self.state_changed.emit(asset_uuid, version_label, 'approved', 'final')
            self.finalized.emit(asset_uuid, version_label)
            return True, "Review marked as final"

        return False, "Failed to finalize review"

    def reopen_review(
        self,
        asset_uuid: str,
        version_label: str
    ) -> Tuple[bool, str]:
        """
        Reopen a finalized review - NOT SUPPORTED for cycles.

        Final cycles cannot be reopened - start a new cycle instead.
        This method is kept for backward compatibility only.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label

        Returns:
            Tuple of (success, message)
        """
        current_state = self.get_current_state(asset_uuid, version_label)

        if current_state != 'final':
            return False, f"Can only reopen from 'final' state (current: {current_state})"

        # Check if version belongs to a cycle
        cycle = self.get_cycle_for_version(asset_uuid, version_label)
        if cycle:
            # Final cycles cannot be reopened
            cycle_type = cycle.get('cycle_type', 'unknown')
            cycle_label = REVIEW_CYCLE_TYPES.get(cycle_type, {}).get('label', cycle_type)
            return False, f"Cannot reopen final cycles. Start a new review cycle instead. (Previous: {cycle_label})"

        # Legacy fallback only for non-cycle reviews
        success = self._review_db.reopen_review(asset_uuid, version_label)

        if success:
            self.state_changed.emit(asset_uuid, version_label, 'final', 'in_review')
            return True, "Review reopened"

        return False, "Failed to reopen review"

    def cancel_review(
        self,
        asset_uuid: str,
        version_label: str
    ) -> Tuple[bool, str]:
        """
        Cancel/withdraw from review workflow.

        Note: This only unlinks the version from the cycle, it doesn't delete the cycle.
        Use with caution - cycles are meant to span versions.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label

        Returns:
            Tuple of (success, message)
        """
        current_state = self.get_current_state(asset_uuid, version_label)

        if current_state is None:
            return False, "Asset not in review workflow"

        # For cycle-based reviews, we don't fully support cancel
        # as it would break the cycle's version range
        cycle = self.get_cycle_for_version(asset_uuid, version_label)
        if cycle and cycle.get('start_version') == version_label:
            # Can't cancel the start version of a cycle
            return False, "Cannot cancel review for the start version of a cycle"

        success = self._review_db.set_review_state(asset_uuid, version_label, None)

        if success:
            self.state_changed.emit(asset_uuid, version_label, current_state or '', '')
            return True, "Review cancelled"

        return False, "Failed to cancel review"


# Singleton instance
_review_state_manager: Optional[ReviewStateManager] = None


def get_review_state_manager() -> ReviewStateManager:
    """Get global ReviewStateManager singleton instance."""
    global _review_state_manager
    if _review_state_manager is None:
        _review_state_manager = ReviewStateManager()
    return _review_state_manager


__all__ = ['ReviewStateManager', 'get_review_state_manager']
