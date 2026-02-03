"""
Action handlers for version history dialog.

Handles promote, publish, lock, cold storage, and review actions.
"""

from typing import Dict, Any, Optional, Callable, Tuple, Union

from PyQt6.QtWidgets import QMessageBox, QWidget

from ....config import REVIEW_CYCLE_TYPES
from ....services.review_state_manager import get_review_state_manager
from ....services.user_service import get_user_service
from ....events.event_bus import get_event_bus


class VersionActionHandlers:
    """
    Handles version actions with confirmations and UI updates.

    Actions:
    - Promote to latest
    - Move to/restore from cold storage
    - Publish (approve + lock)
    - Lock/unlock
    - Review
    - Mark final
    """

    def __init__(
        self,
        parent: QWidget,
        db_service,
        cold_storage_service,
        get_version_fn: Callable[[], Optional[Dict[str, Any]]],
        refresh_fn: Callable[[], None]
    ):
        """
        Initialize action handlers.

        Args:
            parent: Parent widget for dialogs
            db_service: Database service
            cold_storage_service: Cold storage service
            get_version_fn: Function to get selected version
            refresh_fn: Function to refresh view after action
        """
        self._parent = parent
        self._db_service = db_service
        self._cold_storage = cold_storage_service
        self._get_version = get_version_fn
        self._refresh = refresh_fn

    def _execute_action(
        self,
        action_name: str,
        title: str,
        message_template: str,
        action_fn: Callable,
        success_template: str
    ) -> bool:
        """
        Execute a version action with confirmation.

        Args:
            action_name: Name for error messages
            title: Dialog title
            message_template: Confirmation message with {label} placeholder
            action_fn: Function to call with uuid
            success_template: Success message with {label} placeholder

        Returns:
            True if action succeeded
        """
        version = self._get_version()
        if not version:
            return False

        uuid = version.get('uuid')
        version_label = version.get('version_label', 'Unknown')
        message = message_template.format(label=version_label)

        reply = QMessageBox.question(
            self._parent, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return False

        result = action_fn(uuid)
        success = result[0] if isinstance(result, tuple) else result

        if success:
            QMessageBox.information(
                self._parent, "Success",
                success_template.format(label=version_label)
            )
            self._refresh()
            return True
        else:
            error_msg = result[1] if isinstance(result, tuple) else f"Failed to {action_name}."
            QMessageBox.warning(self._parent, "Error", error_msg)
            return False

    def on_promote(self) -> bool:
        """Handle promote to latest action."""
        return self._execute_action(
            "promote",
            "Promote Version",
            "Promote {label} to be the latest version?\n\nThe current latest version will be demoted.",
            self._db_service.promote_asset_to_latest,
            "{label} is now the latest version."
        )

    def on_cold_storage(self) -> bool:
        """Handle cold storage toggle action."""
        version = self._get_version()
        if not version:
            return False

        is_cold = version.get('is_cold', 0) == 1

        if is_cold:
            return self._execute_action(
                "restore",
                "Restore from Cold Storage",
                "Restore {label} from cold storage?\n\nFiles will be moved back to active storage.",
                self._cold_storage.restore_from_cold_storage,
                "{label} has been restored from cold storage."
            )
        else:
            return self._execute_action(
                "archive",
                "Move to Cold Storage",
                "Move {label} to cold storage?\n\nFiles will be archived and version will be marked as immutable.",
                self._cold_storage.move_to_cold_storage,
                "{label} has been moved to cold storage."
            )

    def on_publish(self) -> bool:
        """Handle publish action."""
        return self._execute_action(
            "publish",
            "Publish Version",
            "Publish {label}?\n\nThis will set status to 'Approved' and lock the version.",
            self._db_service.publish_asset_version,
            "{label} has been published."
        )

    def on_lock(self) -> bool:
        """Handle lock/unlock toggle action."""
        version = self._get_version()
        if not version:
            return False

        is_locked = version.get('is_immutable', 0) == 1

        if is_locked:
            return self._execute_action(
                "unlock",
                "Unlock Version",
                "Unlock {label}?\n\nThis will allow changes to this version.",
                self._db_service.unlock_asset_version,
                "{label} has been unlocked."
            )
        else:
            return self._execute_action(
                "lock",
                "Lock Version",
                "Lock {label}?\n\nThis will prevent changes to this version.",
                self._db_service.lock_asset_version,
                "{label} has been locked."
            )

    def on_mark_final(self, populate_tree_fn: Callable[[], None]) -> bool:
        """
        Handle mark final action.

        Args:
            populate_tree_fn: Function to refresh tree view

        Returns:
            True if action succeeded
        """
        version = self._get_version()
        if not version:
            return False

        uuid = version.get('uuid')
        version_label = version.get('version_label', 'v001')

        state_manager = get_review_state_manager()
        cycle = state_manager.get_cycle_for_version(uuid, version_label)
        if not cycle:
            QMessageBox.warning(self._parent, "No Cycle", "This version is not in a review cycle.")
            return False

        cycle_type = cycle.get('cycle_type', 'general')
        cycle_label = REVIEW_CYCLE_TYPES.get(cycle_type, {}).get('label', cycle_type.title())

        reply = QMessageBox.question(
            self._parent,
            "Mark Cycle as Final",
            f"Mark the {cycle_label} review cycle as Final?\n\n"
            f"This will close the cycle at {version_label}.\n\n"
            "Note: Final cycles cannot be reopened. To review further changes, "
            "you will need to start a new review cycle.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return False

        user_service = get_user_service()
        current_user = user_service.get_current_username()

        success, message = state_manager.mark_as_final(uuid, version_label, current_user)

        if success:
            QMessageBox.information(
                self._parent,
                "Cycle Finalized",
                f"{cycle_label} review cycle has been marked as Final."
            )
            populate_tree_fn()
            get_event_bus().asset_updated.emit(uuid)
            return True
        else:
            QMessageBox.warning(self._parent, "Cannot Mark as Final", message)
            return False


__all__ = ['VersionActionHandlers']
