"""
BulkEditController - Handles bulk edit operations on assets

Extracts bulk edit logic from MainWindow for better separation of concerns.
"""

from typing import List, Tuple, Callable, Optional
from PyQt6.QtWidgets import QWidget, QMessageBox

from ...services.cold_storage_service import get_cold_storage_service
from ...services.control_authority import get_control_authority


class BulkEditController:
    """
    Manages bulk edit operations on assets.

    Handles:
    - Change status for selected assets
    - Archive/Restore operations
    - Cold storage operations (file migration)
    - Publish/approve operations
    """

    def __init__(
        self,
        parent: QWidget,
        asset_view,
        asset_model,
        db_service,
        event_bus,
        status_bar,
        reload_assets_callback: Callable[[], None]
    ):
        """
        Initialize bulk edit controller.

        Args:
            parent: Parent widget for dialogs
            asset_view: Asset view widget
            asset_model: Asset list model
            db_service: Database service
            event_bus: Event bus for signals
            status_bar: Status bar for messages
            reload_assets_callback: Callback to reload assets after changes
        """
        self._parent = parent
        self._asset_view = asset_view
        self._asset_model = asset_model
        self._db_service = db_service
        self._event_bus = event_bus
        self._status_bar = status_bar
        self._reload_assets = reload_assets_callback
        self._cold_storage = get_cold_storage_service()
        self._control_authority = get_control_authority()

    def _get_selected_uuids(self) -> List[str]:
        """Get selected asset UUIDs from view."""
        return self._asset_view.get_selected_uuids()

    def _check_selection(self) -> Optional[List[str]]:
        """Check if there's a selection and return UUIDs or show warning."""
        selected_uuids = self._get_selected_uuids()
        if not selected_uuids:
            QMessageBox.warning(
                self._parent, "No Selection", "Please select assets first"
            )
            return None
        return selected_uuids

    def change_status(self, new_status: str) -> None:
        """
        Change status for all selected assets.

        Args:
            new_status: New status value (wip, review, approved, deprecated, archived)
        """
        # Check if status editing is allowed (blocked in Pipeline Mode)
        if not self._control_authority.can_edit_status():
            QMessageBox.information(
                self._parent,
                "Pipeline Mode",
                "Asset status is controlled by Pipeline Control.\n\n"
                "To change asset status, use Pipeline Control or switch "
                "to Standalone mode in Settings > Pipeline."
            )
            return

        selected_uuids = self._check_selection()
        if not selected_uuids:
            return

        # Status display names
        status_names = {
            'wip': 'WIP',
            'review': 'In Review',
            'approved': 'Approved',
            'deprecated': 'Deprecated',
            'archived': 'Archived'
        }
        status_name = status_names.get(new_status, new_status)

        # Confirm action
        count = len(selected_uuids)
        reply = QMessageBox.question(
            self._parent,
            "Confirm Status Change",
            f"Change status to '{status_name}' for {count} asset(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Update each asset
        success_count = 0
        failed_count = 0
        for uuid in selected_uuids:
            result = self._db_service.set_asset_status(uuid, new_status)
            if result:
                success_count += 1
            else:
                failed_count += 1

        # Reload and show status
        if success_count > 0:
            self._reload_assets()
            self._status_bar.set_status(
                f"Changed status to '{status_name}' for {success_count} asset(s)"
            )
            self._event_bus.bulk_operation_completed.emit("status_change", success_count)

        if failed_count > 0:
            if success_count == 0:
                QMessageBox.warning(
                    self._parent, "Error",
                    f"Failed to update status for all {failed_count} asset(s). Check console for details."
                )
            else:
                QMessageBox.warning(
                    self._parent, "Partial Success",
                    f"Updated {success_count} asset(s), but {failed_count} failed."
                )

    def archive_selected(self) -> None:
        """Move selected assets to archived status."""
        # Check if status editing is allowed (blocked in Pipeline Mode)
        if not self._control_authority.can_edit_status():
            QMessageBox.information(
                self._parent,
                "Pipeline Mode",
                "Asset status is controlled by Pipeline Control.\n\n"
                "To archive assets, use Pipeline Control or switch "
                "to Standalone mode in Settings > Pipeline."
            )
            return

        selected_uuids = self._check_selection()
        if not selected_uuids:
            return

        count = len(selected_uuids)
        reply = QMessageBox.question(
            self._parent,
            "Confirm Archive",
            f"Archive {count} asset(s)? They will be moved to 'Archived' status.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        success_count = 0
        failed_count = 0
        for uuid in selected_uuids:
            if self._db_service.set_asset_status(uuid, 'archived'):
                success_count += 1
            else:
                failed_count += 1

        if success_count > 0:
            self._reload_assets()
            self._status_bar.set_status(f"Archived {success_count} asset(s)")
            self._event_bus.bulk_operation_completed.emit("archive", success_count)

        if failed_count > 0:
            QMessageBox.warning(
                self._parent, "Error",
                f"Failed to archive {failed_count} asset(s). Check console for details."
            )

    def restore_selected(self) -> None:
        """Restore selected assets from archived status."""
        # Check if status editing is allowed (blocked in Pipeline Mode)
        if not self._control_authority.can_edit_status():
            QMessageBox.information(
                self._parent,
                "Pipeline Mode",
                "Asset status is controlled by Pipeline Control.\n\n"
                "To restore assets, use Pipeline Control or switch "
                "to Standalone mode in Settings > Pipeline."
            )
            return

        selected_uuids = self._check_selection()
        if not selected_uuids:
            return

        count = len(selected_uuids)
        reply = QMessageBox.question(
            self._parent,
            "Confirm Restore",
            f"Restore {count} asset(s)? They will be moved back to 'WIP' status.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        success_count = 0
        failed_count = 0
        for uuid in selected_uuids:
            if self._db_service.set_asset_status(uuid, 'wip'):
                success_count += 1
            else:
                failed_count += 1

        if success_count > 0:
            self._reload_assets()
            self._status_bar.set_status(f"Restored {success_count} asset(s)")
            self._event_bus.bulk_operation_completed.emit("restore", success_count)

        if failed_count > 0:
            QMessageBox.warning(
                self._parent, "Error",
                f"Failed to restore {failed_count} asset(s). Check console for details."
            )

    def move_to_cold_storage(self) -> None:
        """Move selected assets to cold storage (file migration)."""
        selected_uuids = self._check_selection()
        if not selected_uuids:
            return

        count = len(selected_uuids)
        reply = QMessageBox.question(
            self._parent,
            "Confirm Cold Storage",
            f"Move {count} asset(s) to cold storage?\n\n"
            f"Files will be migrated to the cold storage folder and "
            f"assets will be marked as immutable.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        success_count = 0
        failed_count = 0
        error_messages = []

        for uuid in selected_uuids:
            success, message = self._cold_storage.move_to_cold_storage(uuid)
            if success:
                success_count += 1
            else:
                failed_count += 1
                error_messages.append(f"{uuid[:8]}...: {message}")

        if success_count > 0:
            self._reload_assets()
            self._status_bar.set_status(f"Moved {success_count} asset(s) to cold storage")
            self._event_bus.bulk_operation_completed.emit("cold_storage", success_count)

        if failed_count > 0:
            error_detail = "\n".join(error_messages[:5])
            if len(error_messages) > 5:
                error_detail += f"\n... and {len(error_messages) - 5} more"
            QMessageBox.warning(
                self._parent, "Error",
                f"Failed to move {failed_count} asset(s) to cold storage.\n\n{error_detail}"
            )

    def restore_from_cold_storage(self) -> None:
        """Restore selected assets from cold storage."""
        selected_uuids = self._check_selection()
        if not selected_uuids:
            return

        count = len(selected_uuids)
        reply = QMessageBox.question(
            self._parent,
            "Confirm Restore from Cold",
            f"Restore {count} asset(s) from cold storage?\n\n"
            f"Files will be moved back to active storage.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        success_count = 0
        failed_count = 0
        error_messages = []

        for uuid in selected_uuids:
            success, message = self._cold_storage.restore_from_cold_storage(uuid)
            if success:
                success_count += 1
            else:
                failed_count += 1
                error_messages.append(f"{uuid[:8]}...: {message}")

        if success_count > 0:
            self._reload_assets()
            self._status_bar.set_status(f"Restored {success_count} asset(s) from cold storage")
            self._event_bus.bulk_operation_completed.emit("restore_cold", success_count)

        if failed_count > 0:
            error_detail = "\n".join(error_messages[:5])
            if len(error_messages) > 5:
                error_detail += f"\n... and {len(error_messages) - 5} more"
            QMessageBox.warning(
                self._parent, "Error",
                f"Failed to restore {failed_count} asset(s) from cold storage.\n\n{error_detail}"
            )

    def publish_selected(self) -> None:
        """Publish/approve selected assets (sets approved status + locks)."""
        # Check if status editing is allowed (blocked in Pipeline Mode)
        if not self._control_authority.can_edit_status():
            QMessageBox.information(
                self._parent,
                "Pipeline Mode",
                "Asset status is controlled by Pipeline Control.\n\n"
                "To publish assets, use Pipeline Control or switch "
                "to Standalone mode in Settings > Pipeline."
            )
            return

        selected_uuids = self._check_selection()
        if not selected_uuids:
            return

        count = len(selected_uuids)
        reply = QMessageBox.question(
            self._parent,
            "Confirm Publish",
            f"Publish {count} asset(s)?\n\n"
            f"This will set status to 'Approved' and lock them from changes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        success_count = 0
        failed_count = 0

        for uuid in selected_uuids:
            if self._db_service.publish_asset_version(uuid):
                success_count += 1
            else:
                failed_count += 1

        if success_count > 0:
            self._reload_assets()
            self._status_bar.set_status(f"Published {success_count} asset(s)")
            self._event_bus.bulk_operation_completed.emit("publish", success_count)

        if failed_count > 0:
            QMessageBox.warning(
                self._parent, "Error",
                f"Failed to publish {failed_count} asset(s). Check console for details."
            )

    def change_representation(self, rep_type: str) -> None:
        """
        Change representation type for all selected assets.

        Args:
            rep_type: New representation type (model, lookdev, rig, final)
        """
        selected_uuids = self._check_selection()
        if not selected_uuids:
            return

        # Representation display names
        from ...config import Config
        rep_name = Config.REPRESENTATION_TYPES.get(rep_type, {}).get('label', rep_type)

        # Confirm action
        count = len(selected_uuids)
        reply = QMessageBox.question(
            self._parent,
            "Confirm Representation Change",
            f"Change representation to '{rep_name}' for {count} asset(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Update each asset
        success_count = 0
        failed_count = 0
        for uuid in selected_uuids:
            result = self._db_service.update_asset(uuid, {'representation_type': rep_type})
            if result:
                success_count += 1
            else:
                failed_count += 1

        # Reload and show status
        if success_count > 0:
            self._reload_assets()
            self._status_bar.set_status(
                f"Changed representation to '{rep_name}' for {success_count} asset(s)"
            )
            self._event_bus.bulk_operation_completed.emit("representation_change", success_count)

        if failed_count > 0:
            if success_count == 0:
                QMessageBox.warning(
                    self._parent, "Error",
                    f"Failed to update representation for all {failed_count} asset(s)."
                )
            else:
                QMessageBox.warning(
                    self._parent, "Partial Success",
                    f"Updated {success_count} asset(s), but {failed_count} failed."
                )


__all__ = ['BulkEditController']
