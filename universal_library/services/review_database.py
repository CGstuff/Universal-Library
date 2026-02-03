"""
ReviewDatabase - Coordinator for review data access modules.

This is the main entry point for review database operations.
Delegates to focused sub-modules in services/review/data/

Architecture:
    ReviewDatabase (this file)
        ├── ReviewSchema (schema + migrations)
        ├── ReviewCycles (cycle operations)
        ├── ReviewSessions (session management)
        ├── ReviewNotes (note CRUD)
        ├── ReviewScreenshots (screenshot management)
        ├── ReviewState (state transitions)
        ├── ReviewDrawover (drawover metadata)
        ├── ReviewStatus (status queries)
        ├── ReviewAudit (audit logging)
        ├── ReviewCleanup (maintenance)
        └── ReviewSettings (settings + users)
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from ..config import Config

# Import sub-modules
from .review.data.review_schema import ReviewSchema
from .review.data.review_cycles import ReviewCycles
from .review.data.review_sessions import ReviewSessions
from .review.data.review_notes import ReviewNotes
from .review.data.review_screenshots import ReviewScreenshots
from .review.data.review_state import ReviewState
from .review.data.review_drawover import ReviewDrawover
from .review.data.review_status import ReviewStatus
from .review.data.review_audit import ReviewAudit
from .review.data.review_cleanup import ReviewCleanup
from .review.data.review_settings import ReviewSettings


class ReviewDatabase:
    """
    Coordinator for the separate reviews.db database.

    Features:
    - Review sessions per asset version
    - Screenshot management for review
    - Soft delete with restore capability
    - Audit logging for all actions
    - User management for Studio Mode
    - App settings storage
    - Drawover metadata tracking
    """

    SCHEMA_VERSION = 5
    DB_NAME = "reviews.db"

    def __init__(self):
        self._connection: Optional[sqlite3.Connection] = None
        self._db_path: Optional[Path] = None

        # Sub-modules (lazy initialized)
        self._schema: Optional[ReviewSchema] = None
        self._cycles: Optional[ReviewCycles] = None
        self._sessions: Optional[ReviewSessions] = None
        self._notes: Optional[ReviewNotes] = None
        self._screenshots: Optional[ReviewScreenshots] = None
        self._state: Optional[ReviewState] = None
        self._drawover: Optional[ReviewDrawover] = None
        self._status: Optional[ReviewStatus] = None
        self._audit: Optional[ReviewAudit] = None
        self._cleanup: Optional[ReviewCleanup] = None
        self._settings: Optional[ReviewSettings] = None

    def initialize(self) -> bool:
        """Initialize the reviews database."""
        try:
            db_folder = Config.get_database_folder()
            self._db_path = db_folder / self.DB_NAME

            self._connection = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")

            # Initialize sub-modules
            self._init_modules()

            # Create/migrate schema
            self._schema.create_schema()
            self._schema.migrate_if_needed()

            return True
        except Exception as e:
            return False

    def _init_modules(self):
        """Initialize all sub-modules with the database connection."""
        conn = self._connection
        self._schema = ReviewSchema(conn)
        self._cycles = ReviewCycles(conn)
        self._sessions = ReviewSessions(conn)
        self._notes = ReviewNotes(conn)
        self._screenshots = ReviewScreenshots(conn)
        self._state = ReviewState(conn)
        self._drawover = ReviewDrawover(conn)
        self._status = ReviewStatus(conn)
        self._audit = ReviewAudit(conn)
        self._cleanup = ReviewCleanup(conn)
        self._settings = ReviewSettings(conn)

    def close(self):
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    # ==================== CYCLE OPERATIONS ====================

    def create_cycle(self, asset_id: str, cycle_type: str, start_version: str,
                     submitted_by: str = '', variant_name: str = 'Base') -> Optional[int]:
        """Create a new review cycle."""
        return self._cycles.create_cycle(asset_id, cycle_type, start_version, submitted_by, variant_name)

    def get_active_cycle(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Get the active (non-finalized) cycle for an asset."""
        return self._cycles.get_active_cycle(asset_id)

    def get_active_cycle_for_variant(self, asset_id: str, variant_name: str = 'Base') -> Optional[Dict[str, Any]]:
        """Get the active cycle for a specific variant."""
        return self._cycles.get_active_cycle_for_variant(asset_id, variant_name)

    def get_cycle(self, cycle_id: int) -> Optional[Dict[str, Any]]:
        """Get a cycle by ID."""
        return self._cycles.get_cycle(cycle_id)

    def get_cycles_for_asset(self, asset_id: str) -> List[Dict[str, Any]]:
        """Get all cycles for an asset."""
        return self._cycles.get_cycles_for_asset(asset_id)

    def set_cycle_state(self, cycle_id: int, review_state: str) -> bool:
        """Update the review state of a cycle."""
        return self._cycles.set_cycle_state(cycle_id, review_state)

    def close_cycle(self, cycle_id: int, end_version: str, finalized_by: str = '') -> bool:
        """Close a review cycle (mark as final)."""
        return self._cycles.close_cycle(cycle_id, end_version, finalized_by)

    def link_session_to_cycle(self, session_id: int, cycle_id: int) -> bool:
        """Link a session to a cycle."""
        return self._cycles.link_session_to_cycle(session_id, cycle_id)

    def get_cycle_sessions(self, cycle_id: int) -> List[Dict[str, Any]]:
        """Get all sessions in a cycle."""
        return self._cycles.get_cycle_sessions(cycle_id)

    def get_cycle_notes(self, cycle_id: int, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """Get all notes from all sessions in a cycle."""
        return self._cycles.get_cycle_notes(cycle_id, include_deleted)

    def get_cycle_note_counts(self, cycle_id: int) -> Dict[str, int]:
        """Get note status counts for a cycle."""
        return self._cycles.get_cycle_note_counts(cycle_id)

    # ==================== SESSION OPERATIONS ====================

    def get_or_create_session(self, asset_uuid: str, version_label: str) -> Optional[int]:
        """Get existing session or create new one."""
        return self._sessions.get_or_create_session(asset_uuid, version_label)

    def get_session(self, asset_uuid: str, version_label: str) -> Optional[Dict[str, Any]]:
        """Get session by asset UUID and version label."""
        return self._sessions.get_session(asset_uuid, version_label)

    def update_session_status(self, session_id: int, status: str, update_activity: bool = True) -> bool:
        """Update session status."""
        return self._sessions.update_session_status(session_id, status, update_activity)

    # ==================== NOTE OPERATIONS ====================

    def get_notes_for_version(self, asset_uuid: str, version_label: str,
                               include_deleted: bool = False) -> List[Dict[str, Any]]:
        """Get all notes for a specific version."""
        return self._notes.get_notes_for_version(asset_uuid, version_label, include_deleted)

    def get_notes_for_screenshot(self, screenshot_id: int, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """Get notes for a specific screenshot."""
        return self._notes.get_notes_for_screenshot(screenshot_id, include_deleted)

    def add_note(self, asset_uuid: str, version_label: str, text: str,
                 screenshot_id: Optional[int] = None, author: str = '',
                 author_role: str = 'artist') -> Optional[int]:
        """Add a new review note."""
        return self._notes.add_note(asset_uuid, version_label, text, screenshot_id, author, author_role)

    def update_note(self, note_id: int, text: str) -> bool:
        """Update note text."""
        return self._notes.update_note(note_id, text)

    def get_note_by_id(self, note_id: int) -> Optional[Dict[str, Any]]:
        """Get a note by ID."""
        return self._notes.get_note_by_id(note_id)

    def soft_delete_note(self, note_id: int, deleted_by: str = '') -> bool:
        """Soft delete a note."""
        return self._notes.soft_delete_note(note_id, deleted_by)

    def restore_note(self, note_id: int) -> bool:
        """Restore a soft-deleted note."""
        return self._notes.restore_note(note_id)

    def delete_note(self, note_id: int, deleted_by: str = '') -> bool:
        """Delete a note (soft delete)."""
        return self._notes.delete_note(note_id, deleted_by)

    def hard_delete_note(self, note_id: int) -> bool:
        """Permanently delete a note."""
        return self._notes.hard_delete_note(note_id)

    def set_note_resolved(self, note_id: int, resolved: bool, resolved_by: str = '') -> bool:
        """Set the resolved flag on a note."""
        return self._notes.set_note_resolved(note_id, resolved, resolved_by)

    def set_note_status(self, note_id: int, status: str, actor: str = '', actor_role: str = '') -> bool:
        """Set note status (open, addressed, approved)."""
        return self._notes.set_note_status(note_id, status, actor, actor_role)

    def mark_note_addressed(self, note_id: int, addressed_by: str = '', addressed_role: str = '') -> bool:
        """Mark note as addressed by artist."""
        return self._notes.mark_note_addressed(note_id, addressed_by, addressed_role)

    def approve_note(self, note_id: int, approved_by: str = '', approved_role: str = '') -> bool:
        """Approve a note (lead confirms fix)."""
        return self._notes.approve_note(note_id, approved_by, approved_role)

    def reopen_note(self, note_id: int, reopened_by: str = '', reopened_role: str = '') -> bool:
        """Reopen a note back to 'open' status."""
        return self._notes.reopen_note(note_id, reopened_by, reopened_role)

    def get_note_status_counts(self, asset_uuid: str, version_label: str) -> Dict[str, int]:
        """Get note counts by status for a version."""
        return self._notes.get_note_status_counts(asset_uuid, version_label)

    # ==================== SCREENSHOT OPERATIONS ====================

    def add_screenshot(self, asset_uuid: str, version_label: str, filename: str,
                       file_path: str, display_name: str = '', uploaded_by: str = '') -> Optional[int]:
        """Add a screenshot to a review session."""
        return self._screenshots.add_screenshot(asset_uuid, version_label, filename, file_path, display_name, uploaded_by)

    def get_screenshots(self, asset_uuid: str, version_label: str) -> List[Dict[str, Any]]:
        """Get all screenshots for a version."""
        return self._screenshots.get_screenshots(asset_uuid, version_label)

    def get_screenshot_by_id(self, screenshot_id: int) -> Optional[Dict[str, Any]]:
        """Get a screenshot by ID."""
        return self._screenshots.get_screenshot_by_id(screenshot_id)

    def update_screenshot(self, screenshot_id: int, display_name: Optional[str] = None,
                          display_order: Optional[int] = None) -> bool:
        """Update screenshot properties."""
        return self._screenshots.update_screenshot(screenshot_id, display_name, display_order)

    def delete_screenshot(self, screenshot_id: int) -> bool:
        """Delete a screenshot."""
        return self._screenshots.delete_screenshot(screenshot_id)

    def reorder_screenshots(self, asset_uuid: str, version_label: str, screenshot_ids: List[int]) -> bool:
        """Reorder screenshots for a version."""
        return self._screenshots.reorder_screenshots(asset_uuid, version_label, screenshot_ids)

    # ==================== STATE OPERATIONS ====================

    def set_review_state(self, asset_uuid: str, version_label: str, review_state: str, user: str = '') -> Tuple[bool, str]:
        """Set review state for a version."""
        return self._state.set_review_state(asset_uuid, version_label, review_state, user)

    def submit_for_review(self, asset_uuid: str, version_label: str, user: str = '') -> Tuple[bool, str]:
        """Submit asset for review."""
        return self._state.submit_for_review(asset_uuid, version_label, user)

    def finalize_review(self, asset_uuid: str, version_label: str, user: str = '') -> Tuple[bool, str]:
        """Finalize review (mark as final)."""
        return self._state.finalize_review(asset_uuid, version_label, user)

    def reopen_review(self, asset_uuid: str, version_label: str, target_state: str = 'needs_review') -> Tuple[bool, str]:
        """Reopen a finalized review."""
        return self._state.reopen_review(asset_uuid, version_label, target_state)

    def get_assets_by_review_state(self, review_state: str) -> List[Dict[str, Any]]:
        """Get all assets in a specific review state."""
        return self._state.get_assets_by_review_state(review_state)

    def get_all_review_states(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all sessions grouped by review state."""
        return self._state.get_all_review_states()

    # ==================== DRAWOVER OPERATIONS ====================

    def update_drawover_metadata(self, asset_uuid: str, version_label: str, screenshot_id: int,
                                  stroke_count: int, authors: str, file_path: str = '') -> bool:
        """Update drawover metadata."""
        return self._drawover.update_drawover_metadata(asset_uuid, version_label, screenshot_id, stroke_count, authors, file_path)

    def get_drawover_metadata(self, asset_uuid: str, version_label: str, screenshot_id: int) -> Optional[Dict[str, Any]]:
        """Get drawover metadata for a screenshot."""
        return self._drawover.get_drawover_metadata(asset_uuid, version_label, screenshot_id)

    def get_version_drawovers(self, asset_uuid: str, version_label: str) -> List[Dict[str, Any]]:
        """Get all drawovers for a version."""
        return self._drawover.get_version_drawovers(asset_uuid, version_label)

    def delete_drawover_metadata(self, asset_uuid: str, version_label: str, screenshot_id: int) -> bool:
        """Delete drawover metadata."""
        return self._drawover.delete_drawover_metadata(asset_uuid, version_label, screenshot_id)

    def log_drawover_action(self, asset_uuid: str, version_label: str, screenshot_id: int,
                            action: str, actor: str, actor_role: str = '',
                            stroke_id: str = '', details: str = '') -> Optional[int]:
        """Log a drawover action."""
        return self._drawover.log_drawover_action(asset_uuid, version_label, screenshot_id, action, actor, actor_role, stroke_id, details)

    def get_drawover_audit_log(self, asset_uuid: str, version_label: str,
                               screenshot_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get drawover audit log."""
        return self._drawover.get_drawover_audit_log(asset_uuid, version_label, screenshot_id, limit)

    # ==================== STATUS QUERIES ====================

    def get_review_status(self, asset_uuid: str, version_label: str,
                          version_group_id: Optional[str] = None) -> Dict[str, Any]:
        """Get comprehensive review status for a version."""
        return self._status.get_review_status(asset_uuid, version_label, version_group_id)

    def get_review_status_batch(self, asset_version_pairs: List[tuple]) -> Dict[str, Dict[str, Any]]:
        """Get review status for multiple versions at once."""
        return self._status.get_review_status_batch(asset_version_pairs)

    def get_assets_with_open_notes(self) -> List[Dict[str, Any]]:
        """Get assets with open review notes."""
        return self._status.get_assets_with_open_notes()

    def get_assets_awaiting_approval(self) -> List[Dict[str, Any]]:
        """Get assets with addressed notes waiting for approval."""
        return self._status.get_assets_awaiting_approval()

    # ==================== AUDIT OPERATIONS ====================

    def log_action(self, note_id: Optional[int], action: str, actor: str,
                   actor_role: str = '', details: str = '') -> Optional[int]:
        """Log an action to the audit log."""
        return self._audit.log_action(note_id, action, actor, actor_role, details)

    def _log_action(self, note_id: Optional[int], action: str, actor: str,
                    actor_role: str = '', details: str = '') -> Optional[int]:
        """Internal alias for log_action."""
        return self._audit.log_action(note_id, action, actor, actor_role, details)

    def get_audit_log(self, note_id: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit log entries."""
        return self._audit.get_audit_log(note_id, limit)

    def get_recent_activity(self, limit: int = 50, actor: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent activity across all notes."""
        return self._audit.get_recent_activity(limit, actor)

    # ==================== CLEANUP OPERATIONS ====================

    def cleanup_orphaned_sessions(self) -> int:
        """Remove orphaned sessions."""
        return self._cleanup.cleanup_orphaned_sessions()

    def archive_inactive_sessions(self, days_inactive: int = 90) -> int:
        """Archive inactive sessions."""
        return self._cleanup.archive_inactive_sessions(days_inactive)

    def delete_archived_sessions(self) -> int:
        """Delete archived sessions."""
        return self._cleanup.delete_archived_sessions()

    def purge_deleted_notes(self, days_old: int = 30) -> int:
        """Purge old deleted notes."""
        return self._cleanup.purge_deleted_notes(days_old)

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        return self._cleanup.get_stats()

    # ==================== SETTINGS OPERATIONS ====================

    def get_setting(self, key: str, default: str = '') -> str:
        """Get an app setting."""
        return self._settings.get_setting(key, default)

    def set_setting(self, key: str, value: str) -> bool:
        """Set an app setting."""
        return self._settings.set_setting(key, value)

    def is_studio_mode(self) -> bool:
        """Check if in studio mode."""
        return self._settings.is_studio_mode()

    def set_studio_mode(self, enabled: bool) -> bool:
        """Enable/disable studio mode."""
        return self._settings.set_studio_mode(enabled)

    def get_current_user(self) -> str:
        """Get current user."""
        return self._settings.get_current_user()

    def set_current_user(self, username: str) -> bool:
        """Set current user."""
        return self._settings.set_current_user(username)

    def get_show_deleted(self) -> bool:
        """Check if showing deleted notes."""
        return self._settings.get_show_deleted()

    def set_show_deleted(self, show: bool) -> bool:
        """Set show deleted preference."""
        return self._settings.set_show_deleted(show)

    def get_all_users(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all studio users."""
        return self._settings.get_all_users(include_inactive)

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a user by username."""
        return self._settings.get_user(username)

    def add_user(self, username: str, display_name: str, role: str = 'artist') -> Optional[int]:
        """Add a new user."""
        return self._settings.add_user(username, display_name, role)

    def update_user(self, username: str, display_name: Optional[str] = None, role: Optional[str] = None) -> bool:
        """Update a user."""
        return self._settings.update_user(username, display_name, role)

    def deactivate_user(self, username: str) -> bool:
        """Deactivate a user."""
        return self._settings.deactivate_user(username)

    def reactivate_user(self, username: str) -> bool:
        """Reactivate a user."""
        return self._settings.reactivate_user(username)


# Singleton instance
_review_db_instance: Optional[ReviewDatabase] = None


def get_review_database() -> ReviewDatabase:
    """Get the global ReviewDatabase singleton instance."""
    global _review_db_instance
    if _review_db_instance is None:
        _review_db_instance = ReviewDatabase()
        _review_db_instance.initialize()
    return _review_db_instance


__all__ = ['ReviewDatabase', 'get_review_database']
