"""
ReviewService - Unified facade for all review operations.

This is the SINGLE ENTRY POINT for review functionality.
Adding a new review feature should:
1. Add method here
2. Add UI in one widget
3. Connect signal

No need to touch 20 files anymore!

Architecture:
    ReviewService (this file)
        ├── Uses: ReviewDatabase (data access)
        ├── Uses: ReviewStateManager (state machine)
        ├── Uses: ReviewStorage (screenshot files)
        └── Uses: DrawoverStorage (annotation files)

Variant Support:
    Each variant (Base, Damaged, etc.) has independent review cycles.
    Cycles are keyed by (asset_id, variant_name) not just asset_id.
"""

from typing import Optional, Dict, Any, List, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from ...core import BaseService


class ReviewService(BaseService, QObject):
    """
    Unified facade for all review operations.

    Signals:
        cycle_started: Emitted when a new review cycle starts
        cycle_closed: Emitted when a cycle is marked final
        state_changed: Emitted when review state changes
        note_added: Emitted when a note is added
        note_status_changed: Emitted when note status changes
    """

    # Signals for UI updates
    cycle_started = pyqtSignal(str, str, str)  # asset_id, variant_name, cycle_type
    cycle_closed = pyqtSignal(str, str)         # asset_id, variant_name
    state_changed = pyqtSignal(str, str, str)   # asset_uuid, version_label, new_state
    note_added = pyqtSignal(str, str, int)      # asset_uuid, version_label, note_id
    note_status_changed = pyqtSignal(int, str)  # note_id, new_status

    def __init__(self):
        # Initialize QObject first for signals
        QObject.__init__(self)
        # BaseService init is handled by get_instance()

        # Lazy-loaded services (avoid import cycles)
        self._review_db = None
        self._state_manager = None
        self._review_storage = None
        self._drawover_storage = None

    def initialize(self) -> None:
        """Initialize the service and its dependencies."""
        # Services are lazy-loaded on first use

        # Connect to asset_version_created event for auto-join
        # This replaces the circular dependency in AssetRepository
        try:
            from ...events.event_bus import get_event_bus
            get_event_bus().asset_version_created.connect(self._on_asset_version_created)
        except Exception as e:
            pass

    @property
    def _db(self):
        """Lazy load review database."""
        if self._review_db is None:
            from ..review_database import get_review_database
            self._review_db = get_review_database()
        return self._review_db

    @property
    def _state(self):
        """Lazy load state manager."""
        if self._state_manager is None:
            from ..review_state_manager import get_review_state_manager
            self._state_manager = get_review_state_manager()
        return self._state_manager

    @property
    def _storage(self):
        """Lazy load review storage."""
        if self._review_storage is None:
            from ..review_storage import get_review_storage
            self._review_storage = get_review_storage()
        return self._review_storage

    @property
    def _drawover(self):
        """Lazy load drawover storage."""
        if self._drawover_storage is None:
            from ..drawover_storage import get_drawover_storage
            self._drawover_storage = get_drawover_storage()
        return self._drawover_storage

    # ==================== CYCLE OPERATIONS ====================

    def start_cycle(
        self,
        asset_id: str,
        variant_name: str,
        cycle_type: str,
        version_label: str,
        user: str
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Start a new review cycle for a specific variant.

        Args:
            asset_id: Asset family ID (version_group_id)
            variant_name: Variant name (e.g., 'Base', 'Damaged')
            cycle_type: Cycle type (e.g., 'modeling', 'texturing')
            version_label: Starting version (e.g., 'v001')
            user: Username starting the cycle

        Returns:
            Tuple of (success, message, cycle_id)
        """
        # Check if there's already an active cycle for this variant
        active = self.get_active_cycle(asset_id, variant_name)
        if active:
            return False, f"Active {active.get('cycle_type')} cycle already exists", None

        # Create the cycle with variant awareness
        cycle_id = self._db.create_cycle(
            asset_id=asset_id,
            cycle_type=cycle_type,
            start_version=version_label,
            submitted_by=user,
            variant_name=variant_name
        )

        if cycle_id:
            self.cycle_started.emit(asset_id, variant_name, cycle_type)
            return True, f"Started {cycle_type} review cycle", cycle_id

        return False, "Failed to create cycle", None

    def close_cycle(
        self,
        asset_id: str,
        variant_name: str,
        end_version: str,
        user: str
    ) -> Tuple[bool, str]:
        """
        Close (finalize) the active review cycle for a variant.

        Args:
            asset_id: Asset family ID
            variant_name: Variant name
            end_version: Final version in the cycle
            user: Username closing the cycle

        Returns:
            Tuple of (success, message)
        """
        cycle = self.get_active_cycle(asset_id, variant_name)
        if not cycle:
            return False, "No active cycle to close"

        if cycle.get('review_state') != 'approved':
            return False, "Cycle must be approved before marking final"

        success = self._db.close_cycle(
            cycle_id=cycle['id'],
            end_version=end_version,
            finalized_by=user
        )

        if success:
            self.cycle_closed.emit(asset_id, variant_name)
            return True, "Cycle marked as final"

        return False, "Failed to close cycle"

    def get_active_cycle(
        self,
        asset_id: str,
        variant_name: str = 'Base'
    ) -> Optional[Dict[str, Any]]:
        """
        Get the active (non-final) review cycle for a variant.

        Args:
            asset_id: Asset family ID
            variant_name: Variant name (default: 'Base')

        Returns:
            Cycle dict or None
        """
        return self._db.get_active_cycle_for_variant(asset_id, variant_name)

    def get_cycle_for_version(
        self,
        asset_uuid: str,
        version_label: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the cycle that a specific version belongs to.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label

        Returns:
            Cycle dict or None
        """
        return self._state.get_cycle_for_version(asset_uuid, version_label)

    # ==================== STATUS OPERATIONS ====================

    def get_status(
        self,
        asset_uuid: str,
        version_label: str,
        variant_name: str = 'Base',
        version_group_id: str = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive review status for an asset version.

        This is the main method for getting all review info.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            variant_name: Variant name
            version_group_id: Asset family ID (for cycle lookup)

        Returns:
            Dict with:
                - review_state: Current state (needs_review, in_progress, etc.)
                - cycle: Active cycle info (if any)
                - note_counts: Counts by status
                - can_add_notes: Whether notes can be added
        """
        # Get base status from database
        status = self._db.get_review_status(
            asset_uuid,
            version_label,
            version_group_id
        )

        # Enhance with variant-aware cycle info
        if version_group_id:
            cycle = self.get_active_cycle(version_group_id, variant_name)
            if cycle:
                status['cycle'] = cycle
                status['review_state'] = cycle.get('review_state')

        # Add capabilities
        status['can_add_notes'] = self._state.can_add_comments(
            asset_uuid, version_label
        )
        status['can_start_cycle'] = self._state.can_start_new_cycle(
            version_group_id or asset_uuid
        )

        return status

    # ==================== NOTE OPERATIONS ====================

    def add_note(
        self,
        asset_uuid: str,
        version_label: str,
        text: str,
        author: str,
        author_role: str,
        screenshot_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Add a review note.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            text: Note text
            author: Author username
            author_role: Author role (artist, lead, etc.)
            screenshot_id: Optional screenshot to attach to

        Returns:
            Note ID or None
        """
        note_id = self._db.add_note(
            asset_uuid=asset_uuid,
            version_label=version_label,
            text=text,
            screenshot_id=screenshot_id,
            author=author,
            author_role=author_role
        )

        if note_id:
            # Trigger state transition
            new_state, _ = self._state.on_comment_added(
                asset_uuid, version_label, author_role
            )
            self.note_added.emit(asset_uuid, version_label, note_id)
            if new_state:
                self.state_changed.emit(asset_uuid, version_label, new_state)

        return note_id

    def address_note(
        self,
        note_id: int,
        user: str,
        user_role: str
    ) -> bool:
        """
        Mark a note as addressed (artist says 'I fixed it').

        Args:
            note_id: Note ID
            user: Username
            user_role: User role

        Returns:
            True if successful
        """
        result = self._db.mark_note_addressed(note_id, user, user_role)
        if result:
            self.note_status_changed.emit(note_id, 'addressed')
        return result

    def approve_note(
        self,
        note_id: int,
        user: str,
        user_role: str
    ) -> bool:
        """
        Approve a note (lead confirms the fix).

        Args:
            note_id: Note ID
            user: Username
            user_role: User role

        Returns:
            True if successful
        """
        result = self._db.approve_note(note_id, user, user_role)
        if result:
            self.note_status_changed.emit(note_id, 'approved')
        return result

    def reopen_note(
        self,
        note_id: int,
        user: str,
        user_role: str
    ) -> bool:
        """
        Reopen a note back to 'open' status.

        Args:
            note_id: Note ID
            user: Username
            user_role: User role

        Returns:
            True if successful
        """
        result = self._db.reopen_note(note_id, user, user_role)
        if result:
            self.note_status_changed.emit(note_id, 'open')
        return result

    def get_notes(
        self,
        asset_uuid: str,
        version_label: str,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get notes for a specific version.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            include_deleted: Include soft-deleted notes

        Returns:
            List of note dicts
        """
        return self._db.get_notes_for_version(
            asset_uuid, version_label, include_deleted
        )

    def get_cycle_notes(
        self,
        cycle_id: int,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all notes for a cycle (across all versions in cycle).

        Args:
            cycle_id: Cycle ID
            include_deleted: Include soft-deleted notes

        Returns:
            List of note dicts with version info
        """
        return self._db.get_cycle_notes(cycle_id, include_deleted)

    # ==================== SCREENSHOT OPERATIONS ====================

    def add_screenshot(
        self,
        asset_uuid: str,
        version_label: str,
        file_path: str,
        display_name: str,
        user: str
    ) -> Optional[int]:
        """
        Add a screenshot for review.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label
            file_path: Path to screenshot file
            display_name: Display name
            user: Uploader username

        Returns:
            Screenshot ID or None
        """
        return self._db.add_screenshot(
            asset_uuid=asset_uuid,
            version_label=version_label,
            filename=file_path,
            file_path=file_path,
            display_name=display_name,
            uploaded_by=user
        )

    def get_screenshots(
        self,
        asset_uuid: str,
        version_label: str
    ) -> List[Dict[str, Any]]:
        """
        Get screenshots for a version.

        Args:
            asset_uuid: Asset UUID
            version_label: Version label

        Returns:
            List of screenshot dicts
        """
        return self._db.get_screenshots(asset_uuid, version_label)

    # ==================== DRAWOVER OPERATIONS ====================

    def save_drawover(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int,
        strokes: List[Dict],
        user: str,
        canvas_size: tuple
    ) -> bool:
        """
        Save drawover annotations for a screenshot.

        Args:
            asset_id: Asset family ID
            asset_name: Asset name
            variant_name: Variant name
            version_label: Version label
            screenshot_id: Screenshot ID
            strokes: List of stroke dicts
            user: Author username
            canvas_size: (width, height) of canvas

        Returns:
            True if successful
        """
        return self._drawover.save_drawover(
            asset_id, asset_name, variant_name, version_label,
            screenshot_id, strokes, user, canvas_size
        )

    def load_drawover(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Load drawover annotations for a screenshot.

        Args:
            asset_id: Asset family ID
            asset_name: Asset name
            variant_name: Variant name
            version_label: Version label
            screenshot_id: Screenshot ID

        Returns:
            Dict with strokes and canvas_size, or None
        """
        return self._drawover.load_drawover(
            asset_id, asset_name, variant_name, version_label, screenshot_id
        )

    # ==================== CONVENIENCE METHODS ====================

    def mark_as_final(
        self,
        asset_uuid: str,
        version_label: str,
        user: str
    ) -> Tuple[bool, str]:
        """
        Convenience method to mark current cycle as final.

        Wraps close_cycle with version-based lookup.
        """
        return self._state.mark_as_final(asset_uuid, version_label, user)

    def can_start_cycle(self, asset_id: str, variant_name: str = 'Base') -> bool:
        """Check if a new cycle can be started for this variant."""
        active = self.get_active_cycle(asset_id, variant_name)
        return active is None

    # ==================== EVENT HANDLERS ====================

    def _on_asset_version_created(
        self,
        asset_uuid: str,
        version_label: str,
        version_group_id: str,
        variant_name: str
    ) -> None:
        """
        Auto-join new version to active review cycle.

        Called when a new asset version is created. If there's an active
        review cycle for this variant, the new version's session is linked
        to that cycle.

        This replaces the old circular dependency where AssetRepository
        directly imported ReviewDatabase.

        Args:
            asset_uuid: The new asset's UUID
            version_label: Version label (e.g., 'v002')
            version_group_id: Asset family ID for cycle lookup
            variant_name: Variant name (e.g., 'Base', 'Damaged')
        """
        if not version_group_id or not variant_name:
            return

        try:
            # Check for active cycle for this variant
            active_cycle = self.get_active_cycle(version_group_id, variant_name)
            if not active_cycle:
                return

            # Only join if version >= cycle's start_version
            cycle_start = active_cycle.get('start_version', 'v001')
            if version_label < cycle_start:
                # Version is before cycle started - don't include it
                return

            # Check if session already exists with a cycle
            existing_session = self._db.get_session(asset_uuid, version_label)
            if existing_session and existing_session.get('cycle_id'):
                # Already belongs to a cycle - don't steal it
                return

            # Get or create session for the new version
            session_id = self._db.get_or_create_session(asset_uuid, version_label)
            if not session_id:
                return

            # Link session to the active cycle
            self._db.link_session_to_cycle(session_id, active_cycle['id'])

            # Emit event for UI updates
            from ...events.event_bus import get_event_bus
            get_event_bus().asset_updated.emit(asset_uuid)

        except Exception as e:
            pass


# Singleton instance
_review_service_instance: Optional[ReviewService] = None


def get_review_service() -> ReviewService:
    """Get the ReviewService singleton instance."""
    global _review_service_instance
    if _review_service_instance is None:
        _review_service_instance = ReviewService()
        _review_service_instance.initialize()
    return _review_service_instance


__all__ = ['ReviewService', 'get_review_service']
