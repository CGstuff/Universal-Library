"""
AssetManager - Centralized asset operations service

Pattern: Service layer for business logic
Extracted from MainWindow for proper separation of concerns.
"""

import logging
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from .database_service import get_database_service
from .blender_service import get_blender_service
from ..events.event_bus import get_event_bus
from ..core.exceptions import AssetNotFoundError, FileOperationError, DatabaseError

logger = logging.getLogger(__name__)


class AssetManager(QObject):
    """
    Centralized service for asset operations

    Features:
    - Delete assets (single and batch)
    - Toggle favorites
    - Move assets between folders
    - Queue thumbnail regeneration
    - Emits signals for UI updates

    Usage:
        manager = get_asset_manager()
        manager.asset_deleted.connect(on_asset_deleted)
        success = manager.delete_asset(uuid)
    """

    # Signals for UI updates
    asset_deleted = pyqtSignal(str)  # uuid
    assets_deleted = pyqtSignal(list, int)  # [uuids], deleted_count
    favorite_toggled = pyqtSignal(str, bool)  # uuid, is_favorite
    asset_moved = pyqtSignal(str, int)  # uuid, new_folder_id
    assets_moved = pyqtSignal(list, int, int)  # [uuids], folder_id, success_count
    thumbnail_queued = pyqtSignal(str)  # uuid
    operation_error = pyqtSignal(str, str)  # operation, error_message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db_service = get_database_service()
        self._blender_service = get_blender_service()
        self._event_bus = get_event_bus()

    def delete_asset(self, uuid: str, delete_files: bool = True) -> Tuple[bool, str]:
        """
        Delete a single asset

        Uses atomic operation: if file deletion fails, database deletion is skipped
        to prevent orphaned database records pointing to deleted files.

        Args:
            uuid: Asset UUID
            delete_files: Whether to delete asset files from disk

        Returns:
            Tuple of (success, message)
        """
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            error_msg = f"Asset not found: {uuid}"
            logger.warning(error_msg)
            self.operation_error.emit("delete", error_msg)
            return False, "Asset not found"

        asset_name = asset.get('name', 'Unknown')
        file_deleted = False
        asset_folder = None

        # Phase 1: Delete files if requested
        if delete_files:
            usd_path = asset.get('usd_file_path', '')
            blend_path = asset.get('blend_backup_path', '')

            # Use blend_path if usd_path is empty
            file_path = usd_path or blend_path
            if file_path:
                # Structure: library/meshes/AssetName/VariantName/files
                # variant_folder = Path(file_path).parent  (e.g., .../AssetName/Base)
                # asset_folder = variant_folder.parent     (e.g., .../AssetName)
                variant_folder = Path(file_path).parent
                asset_folder = variant_folder.parent


                try:
                    # Delete the variant folder
                    if variant_folder.exists():
                        shutil.rmtree(variant_folder)

                    # If asset folder is now empty, delete it too
                    if asset_folder.exists():
                        remaining = list(asset_folder.iterdir())
                        if not remaining:
                            asset_folder.rmdir()
                        else:
                            pass

                    # Also check for and delete archived versions
                    # Structure: storage/library/meshes/AssetName/Base/file.blend
                    # asset_folder = storage/library/meshes/AssetName
                    # storage_root = storage/ (where _archive/ and reviews/ live)
                    storage_root = asset_folder.parent.parent.parent  # Go up: meshes -> library -> storage
                    asset_type_folder = asset_folder.parent.name  # e.g., "meshes"

                    # Archives are at: storage/_archive/meshes/AssetName/...
                    archive_folder = storage_root / "_archive"
                    archived_asset = archive_folder / asset_type_folder / asset_folder.name

                    if archived_asset.exists():
                        shutil.rmtree(archived_asset)

                    # Reviews are at: storage/reviews/meshes/AssetName/...
                    reviews_folder = storage_root / "reviews"
                    reviews_asset = reviews_folder / asset_type_folder / asset_folder.name

                    if reviews_asset.exists():
                        shutil.rmtree(reviews_asset)

                    file_deleted = True

                except Exception as e:
                    # File deletion failed - do NOT proceed with database deletion
                    # This prevents orphaned DB records
                    error_msg = f"Could not delete asset folder: {e}"
                    logger.error(error_msg)
                    self.operation_error.emit("delete_files", str(e))
                    return False, f"File deletion failed: {e}"
            else:
                # No file path, nothing to delete
                file_deleted = True
        else:
            file_deleted = True  # Skipped by request

        # Phase 2: Delete from database (only if file deletion succeeded or was skipped)
        if file_deleted:
            if self._db_service.delete_asset(uuid):
                logger.info(f"Deleted asset: {asset_name} ({uuid})")
                self.asset_deleted.emit(uuid)
                return True, f"Deleted '{asset_name}'"
            else:
                # Database deletion failed after file deletion - this is a problem
                # Log as error since we now have orphaned files
                error_msg = f"Failed to delete '{asset_name}' from database (files already deleted)"
                logger.error(error_msg)
                self.operation_error.emit("delete", error_msg)
                return False, error_msg

        return False, "Unexpected state in delete operation"

    def delete_assets_batch(self, uuids: List[str], delete_files: bool = True) -> Tuple[int, int]:
        """
        Delete multiple assets

        Uses atomic per-asset deletion: for each asset, file deletion must succeed
        before database deletion proceeds.

        Args:
            uuids: List of asset UUIDs
            delete_files: Whether to delete asset files from disk

        Returns:
            Tuple of (deleted_count, total_count)
        """
        deleted_count = 0
        file_errors = []
        db_errors = []

        for uuid in uuids:
            asset = self._db_service.get_asset_by_uuid(uuid)
            if not asset:
                logger.warning(f"Asset not found for batch delete: {uuid}")
                continue

            asset_name = asset.get('name', uuid)
            file_deleted = False

            # Phase 1: Delete files if requested
            if delete_files:
                usd_path = asset.get('usd_file_path', '')
                if usd_path:
                    asset_folder = Path(usd_path).parent
                    try:
                        if asset_folder.exists():
                            shutil.rmtree(asset_folder)
                            file_deleted = True
                        else:
                            file_deleted = True  # Already gone
                    except Exception as e:
                        file_errors.append(f"{asset_name}: {e}")
                        logger.warning(f"Could not delete folder for {uuid}: {e}")
                        # Skip DB deletion for this asset
                        continue
                else:
                    file_deleted = True
            else:
                file_deleted = True

            # Phase 2: Delete from database (only if file deletion succeeded)
            if file_deleted:
                if self._db_service.delete_asset(uuid):
                    deleted_count += 1
                else:
                    db_errors.append(f"{asset_name}: database error")

        # Report errors
        total_errors = len(file_errors) + len(db_errors)
        if total_errors > 0:
            error_msg = f"{len(file_errors)} file errors, {len(db_errors)} db errors"
            self.operation_error.emit("batch_delete", error_msg)

        logger.info(f"Batch delete: {deleted_count}/{len(uuids)} assets deleted")
        self.assets_deleted.emit(uuids, deleted_count)
        return deleted_count, len(uuids)

    def toggle_favorite(self, uuid: str) -> Tuple[bool, bool]:
        """
        Toggle favorite status for an asset

        Args:
            uuid: Asset UUID

        Returns:
            Tuple of (success, new_is_favorite_state)
        """
        if self._db_service.toggle_favorite(uuid):
            # Get the new state
            asset = self._db_service.get_asset_by_uuid(uuid)
            is_favorite = asset.get('is_favorite', False) if asset else False
            logger.debug(f"Toggled favorite for {uuid}: {is_favorite}")
            self.favorite_toggled.emit(uuid, is_favorite)
            return True, is_favorite

        logger.warning(f"Failed to toggle favorite for: {uuid}")
        self.operation_error.emit("toggle_favorite", f"Failed for {uuid}")
        return False, False

    def set_favorite(self, uuid: str, is_favorite: bool) -> bool:
        """
        Set favorite status for an asset

        Args:
            uuid: Asset UUID
            is_favorite: New favorite state

        Returns:
            True if successful
        """
        if self._db_service.set_favorite(uuid, is_favorite):
            self.favorite_toggled.emit(uuid, is_favorite)
            return True
        return False

    def set_favorites_batch(self, uuids: List[str], is_favorite: bool) -> int:
        """
        Set favorite status for multiple assets

        Args:
            uuids: List of asset UUIDs
            is_favorite: New favorite state

        Returns:
            Number of successfully updated assets
        """
        success_count = 0
        for uuid in uuids:
            if self._db_service.set_favorite(uuid, is_favorite):
                success_count += 1
                self.favorite_toggled.emit(uuid, is_favorite)
        return success_count

    def move_to_folder(self, uuid: str, folder_id: int) -> bool:
        """
        Move asset to a folder

        Args:
            uuid: Asset UUID
            folder_id: Target folder ID

        Returns:
            True if successful
        """
        if self._db_service.update_asset(uuid, {'folder_id': folder_id}):
            self.asset_moved.emit(uuid, folder_id)
            return True
        return False

    def move_to_folder_batch(self, uuids: List[str], folder_id: int) -> int:
        """
        Move multiple assets to a folder

        Args:
            uuids: List of asset UUIDs
            folder_id: Target folder ID

        Returns:
            Number of successfully moved assets
        """
        success_count = 0
        for uuid in uuids:
            if self._db_service.update_asset(uuid, {'folder_id': folder_id}):
                success_count += 1

        self.assets_moved.emit(uuids, folder_id, success_count)
        return success_count

    def queue_regenerate_thumbnail(self, uuid: str) -> Tuple[bool, str]:
        """
        Queue thumbnail regeneration in Blender

        Args:
            uuid: Asset UUID

        Returns:
            Tuple of (success, message)
        """
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            error_msg = f"Asset not found: {uuid}"
            logger.warning(error_msg)
            self.operation_error.emit("regenerate_thumbnail", error_msg)
            return False, "Asset not found"

        usd_path = asset.get('usd_file_path', '')
        if not usd_path:
            error_msg = f"No USD file path for asset: {uuid}"
            logger.warning(error_msg)
            self.operation_error.emit("regenerate_thumbnail", error_msg)
            return False, "No USD file path for this asset"

        # Get or create thumbnail path
        thumbnail_path = asset.get('thumbnail_path', '')
        if not thumbnail_path:
            thumbnail_path = str(Path(usd_path).parent / "thumbnail.png")

        success = self._blender_service.queue_regenerate_thumbnail(
            uuid=uuid,
            asset_name=asset.get('name', 'Unknown'),
            usd_file_path=usd_path,
            thumbnail_path=thumbnail_path
        )

        if success:
            logger.info(f"Queued thumbnail regeneration: {asset.get('name')} ({uuid})")
            self.thumbnail_queued.emit(uuid)
            return True, f"Thumbnail regeneration queued for '{asset.get('name')}'"
        else:
            error_msg = "Failed to queue thumbnail regeneration. Is Blender running?"
            logger.error(error_msg)
            self.operation_error.emit("regenerate_thumbnail", error_msg)
            return False, error_msg

    def get_asset_names(self, uuids: List[str], max_count: int = 5) -> List[str]:
        """
        Get asset names for display (e.g., in confirmation dialogs)

        Args:
            uuids: List of asset UUIDs
            max_count: Maximum number of names to return

        Returns:
            List of asset names
        """
        names = []
        for uuid in uuids[:max_count]:
            asset = self._db_service.get_asset_by_uuid(uuid)
            if asset:
                names.append(asset.get('name', 'Unknown'))
        return names

    def delete_asset_complete(self, uuid: str) -> Tuple[bool, str]:
        """
        Delete asset with ALL versions, variants, and related data.

        This is the comprehensive delete that removes:
        - All versions of the variant (by version_group_id)
        - All variants if deleting Base (by asset_id)
        - All related data: reviews, screenshots, draw-overs, custom proxies, EAV
        - All files: USD, .blend, thumbnails, review folders

        Args:
            uuid: Asset UUID to delete

        Returns:
            Tuple of (success, message)
        """
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            error_msg = f"Asset not found: {uuid}"
            logger.warning(error_msg)
            return False, "Asset not found"

        asset_id = asset.get('asset_id')
        variant_name = asset.get('variant_name', 'Base')
        asset_name = asset.get('name', 'Unknown')


        # Collect all assets to delete
        assets_to_delete = []

        if variant_name == 'Base':
            # Delete ALL variants when deleting Base
            variants = self._db_service.get_variants(asset_id)
            for v in variants:
                v_name = v.get('variant_name', 'Base')
                # Get all versions of this variant
                versions = self._db_service.get_variant_versions(asset_id, v_name)
                assets_to_delete.extend(versions)
        else:
            # Delete only this variant's versions
            assets_to_delete = self._db_service.get_variant_versions(asset_id, variant_name)

        if not assets_to_delete:
            # Fallback: just delete the single asset
            assets_to_delete = [asset]

        # Delete each asset (files + DB + related data)
        deleted_count = 0
        errors = []


        for rec in assets_to_delete:
            rec_uuid = rec.get('uuid')
            if not rec_uuid:
                continue

            success, msg = self.delete_asset(rec_uuid, delete_files=True)
            if success:
                deleted_count += 1
            else:
                errors.append(f"{rec.get('name', rec_uuid)}: {msg}")

        # Log result
        if deleted_count == len(assets_to_delete):
            logger.info(f"Complete delete of '{asset_name}': {deleted_count} records")
            return True, f"Deleted {deleted_count} asset(s)"
        elif deleted_count > 0:
            logger.warning(f"Partial delete of '{asset_name}': {deleted_count}/{len(assets_to_delete)}")
            return True, f"Deleted {deleted_count}/{len(assets_to_delete)} assets ({len(errors)} errors)"
        else:
            error_msg = f"Failed to delete any assets: {'; '.join(errors[:3])}"
            logger.error(error_msg)
            return False, error_msg

    def get_delete_info(self, uuid: str) -> dict:
        """
        Get information about what would be deleted for an asset.

        Args:
            uuid: Asset UUID

        Returns:
            Dict with delete scope information:
            - name: Asset name
            - variant_name: Variant being deleted
            - is_base: Whether this is the Base variant
            - version_count: Number of versions to delete
            - variant_count: Number of variants to delete (if Base)
            - variants: List of variant names (if Base)
        """
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            return {'error': 'Asset not found'}

        asset_id = asset.get('asset_id')
        variant_name = asset.get('variant_name', 'Base')
        is_base = variant_name == 'Base'

        result = {
            'name': asset.get('name', 'Unknown'),
            'variant_name': variant_name,
            'is_base': is_base,
            'version_count': 0,
            'variant_count': 0,
            'variants': []
        }

        if is_base:
            # Get all variants
            variants = self._db_service.get_variants(asset_id)
            result['variant_count'] = len(variants)
            result['variants'] = [v.get('variant_name', 'Base') for v in variants]

            # Count total versions across all variants
            total_versions = 0
            for v in variants:
                v_name = v.get('variant_name', 'Base')
                versions = self._db_service.get_variant_versions(asset_id, v_name)
                total_versions += len(versions)
            result['version_count'] = total_versions
        else:
            # Just count versions of this variant
            versions = self._db_service.get_variant_versions(asset_id, variant_name)
            result['version_count'] = len(versions)
            result['variant_count'] = 1
            result['variants'] = [variant_name]

        return result


# Singleton instance
_asset_manager_instance: Optional[AssetManager] = None


def get_asset_manager() -> AssetManager:
    """
    Get global AssetManager singleton

    Returns:
        Global AssetManager instance
    """
    global _asset_manager_instance
    if _asset_manager_instance is None:
        _asset_manager_instance = AssetManager()
    return _asset_manager_instance


__all__ = ['AssetManager', 'get_asset_manager']
