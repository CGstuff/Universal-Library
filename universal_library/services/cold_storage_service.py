"""
ColdStorageService - Manages cold storage operations for versioning

Pattern: Service for file migration between hot and cold storage.
Cold storage is for archived/superseded versions that are read-only but recoverable.
"""

import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from ..config import Config
from .database_service import get_database_service


class ColdStorageService:
    """
    Manages cold storage operations for asset versioning.

    Cold storage is used for:
    - Superseded versions (when a new version becomes latest)
    - Archived assets (manually archived by user)
    - Deprecated assets

    Features:
    - Move files to cold storage folder
    - Restore files from cold storage
    - Track original paths for restoration
    - Maintain immutability in cold storage
    """

    def __init__(self):
        self._db_service = get_database_service()

    def move_to_cold_storage(self, uuid: str) -> Tuple[bool, str]:
        """
        Move asset files to cold storage folder.

        Args:
            uuid: Asset UUID to move to cold storage

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Get asset from database
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            return False, f"Asset not found: {uuid}"

        # Check if already in cold storage
        if asset.get('is_cold', 0) == 1:
            return False, "Asset is already in cold storage"

        # Get paths
        usd_path = asset.get('usd_file_path', '')
        blend_path = asset.get('blend_backup_path', '')
        thumbnail_path = asset.get('thumbnail_path', '')
        # Use 'or' to handle both missing keys AND None values
        version_group_id = asset.get('version_group_id') or uuid
        version_label = asset.get('version_label') or 'v001'

        if not usd_path and not blend_path and not thumbnail_path:
            return False, "No files to move to cold storage"

        # Get cold storage destination
        cold_dir = Config.get_cold_storage_asset_path(version_group_id, version_label)

        moved_files = []
        original_paths = {}

        try:
            # Move USD file
            if usd_path and Path(usd_path).exists():
                usd_src = Path(usd_path)
                usd_dst = cold_dir / usd_src.name
                shutil.move(str(usd_src), str(usd_dst))
                moved_files.append(('usd', str(usd_dst)))
                original_paths['original_usd_path'] = usd_path

            # Move blend file
            if blend_path and Path(blend_path).exists():
                blend_src = Path(blend_path)
                blend_dst = cold_dir / blend_src.name
                shutil.move(str(blend_src), str(blend_dst))
                moved_files.append(('blend', str(blend_dst)))
                original_paths['original_blend_path'] = blend_path

            # Move thumbnail file
            if thumbnail_path and Path(thumbnail_path).exists():
                thumb_src = Path(thumbnail_path)
                thumb_dst = cold_dir / thumb_src.name
                shutil.move(str(thumb_src), str(thumb_dst))
                moved_files.append(('thumbnail', str(thumb_dst)))
                original_paths['original_thumbnail_path'] = thumbnail_path

            if not moved_files:
                return False, "No files found to move"

            # Update database
            updates = {
                'is_cold': 1,
                'cold_storage_path': str(cold_dir),
                'is_immutable': 1,  # Cold storage assets are immutable
            }

            # Store original paths for restoration
            if 'original_usd_path' in original_paths:
                updates['original_usd_path'] = original_paths['original_usd_path']
            if 'original_blend_path' in original_paths:
                updates['original_blend_path'] = original_paths['original_blend_path']
            if 'original_thumbnail_path' in original_paths:
                updates['original_thumbnail_path'] = original_paths['original_thumbnail_path']

            # Update file paths to cold storage locations
            for file_type, new_path in moved_files:
                if file_type == 'usd':
                    updates['usd_file_path'] = new_path
                elif file_type == 'blend':
                    updates['blend_backup_path'] = new_path
                elif file_type == 'thumbnail':
                    updates['thumbnail_path'] = new_path

            if self._db_service.update_asset(uuid, updates):
                return True, f"Moved {len(moved_files)} file(s) to cold storage"
            else:
                # Rollback file moves on DB failure
                self._rollback_file_moves(moved_files, original_paths)
                return False, "Database update failed"

        except Exception as e:
            # Rollback on any error
            self._rollback_file_moves(moved_files, original_paths)
            return False, f"Error moving to cold storage: {e}"

    def restore_from_cold_storage(self, uuid: str) -> Tuple[bool, str]:
        """
        Restore asset files from cold storage to original location.

        Args:
            uuid: Asset UUID to restore

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Get asset from database
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            return False, f"Asset not found: {uuid}"

        # Check if in cold storage
        if asset.get('is_cold', 0) != 1:
            return False, "Asset is not in cold storage"

        # Get paths
        current_usd = asset.get('usd_file_path', '')
        current_blend = asset.get('blend_backup_path', '')
        current_thumbnail = asset.get('thumbnail_path', '')
        original_usd = asset.get('original_usd_path', '')
        original_blend = asset.get('original_blend_path', '')
        original_thumbnail = asset.get('original_thumbnail_path', '')

        restored_files = []

        try:
            # Restore USD file
            if current_usd and Path(current_usd).exists() and original_usd:
                usd_src = Path(current_usd)
                usd_dst = Path(original_usd)
                usd_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(usd_src), str(usd_dst))
                restored_files.append(('usd', str(usd_dst)))

            # Restore blend file
            if current_blend and Path(current_blend).exists() and original_blend:
                blend_src = Path(current_blend)
                blend_dst = Path(original_blend)
                blend_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(blend_src), str(blend_dst))
                restored_files.append(('blend', str(blend_dst)))

            # Restore thumbnail file
            if current_thumbnail and Path(current_thumbnail).exists() and original_thumbnail:
                thumb_src = Path(current_thumbnail)
                thumb_dst = Path(original_thumbnail)
                thumb_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(thumb_src), str(thumb_dst))
                restored_files.append(('thumbnail', str(thumb_dst)))

            if not restored_files:
                return False, "No files found to restore"

            # Update database
            updates = {
                'is_cold': 0,
                'cold_storage_path': None,
                'is_immutable': 0,
            }

            # Restore original paths
            for file_type, restored_path in restored_files:
                if file_type == 'usd':
                    updates['usd_file_path'] = restored_path
                elif file_type == 'blend':
                    updates['blend_backup_path'] = restored_path
                elif file_type == 'thumbnail':
                    updates['thumbnail_path'] = restored_path

            # Clear original path fields
            updates['original_usd_path'] = None
            updates['original_blend_path'] = None
            updates['original_thumbnail_path'] = None

            if self._db_service.update_asset(uuid, updates):
                # Clean up empty cold storage folder
                self._cleanup_empty_cold_folder(asset)
                return True, f"Restored {len(restored_files)} file(s) from cold storage"
            else:
                return False, "Database update failed"

        except Exception as e:
            return False, f"Error restoring from cold storage: {e}"

    def get_cold_assets(self) -> List[Dict]:
        """
        Get all assets currently in cold storage.

        Returns:
            List of asset dictionaries
        """
        return self._db_service.get_cold_assets()

    def get_cold_asset_count(self) -> int:
        """Get count of assets in cold storage."""
        return len(self.get_cold_assets())

    def cleanup_orphaned_cold_files(self) -> Tuple[int, List[str]]:
        """
        Remove cold storage files that have no corresponding database entry.

        Returns:
            Tuple of (count of removed files, list of removed paths)
        """
        cold_root = Config.get_cold_storage_path()
        if not cold_root.exists():
            return 0, []

        removed = []
        cold_assets = self.get_cold_assets()
        valid_paths = {a.get('cold_storage_path') for a in cold_assets if a.get('cold_storage_path')}

        # Walk cold storage directory
        for version_group_dir in cold_root.iterdir():
            if not version_group_dir.is_dir():
                continue
            for version_dir in version_group_dir.iterdir():
                if not version_dir.is_dir():
                    continue
                if str(version_dir) not in valid_paths:
                    # Orphaned folder - remove it
                    try:
                        shutil.rmtree(str(version_dir))
                        removed.append(str(version_dir))
                    except Exception as e:
                        pass

            # Remove empty version group folders
            if version_group_dir.exists() and not any(version_group_dir.iterdir()):
                try:
                    version_group_dir.rmdir()
                except Exception:
                    pass

        return len(removed), removed

    def _rollback_file_moves(self, moved_files: List[Tuple[str, str]], original_paths: Dict):
        """Rollback file moves on error."""
        for file_type, new_path in moved_files:
            try:
                new_file = Path(new_path)
                if new_file.exists():
                    if file_type == 'usd' and 'original_usd_path' in original_paths:
                        shutil.move(str(new_file), original_paths['original_usd_path'])
                    elif file_type == 'blend' and 'original_blend_path' in original_paths:
                        shutil.move(str(new_file), original_paths['original_blend_path'])
                    elif file_type == 'thumbnail' and 'original_thumbnail_path' in original_paths:
                        shutil.move(str(new_file), original_paths['original_thumbnail_path'])
            except Exception as e:
                pass

    def _cleanup_empty_cold_folder(self, asset: Dict):
        """Remove empty cold storage folders after restoration."""
        cold_path = asset.get('cold_storage_path')
        if not cold_path:
            return

        version_dir = Path(cold_path)
        if version_dir.exists() and not any(version_dir.iterdir()):
            try:
                version_dir.rmdir()
                # Also try to remove parent if empty
                parent = version_dir.parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
            except Exception:
                pass


# Singleton instance
_cold_storage_service_instance: Optional[ColdStorageService] = None


def get_cold_storage_service() -> ColdStorageService:
    """Get global ColdStorageService singleton instance."""
    global _cold_storage_service_instance
    if _cold_storage_service_instance is None:
        _cold_storage_service_instance = ColdStorageService()
    return _cold_storage_service_instance


__all__ = ['ColdStorageService', 'get_cold_storage_service']
