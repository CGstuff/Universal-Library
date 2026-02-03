"""
RetireService - Manages retiring assets (soft delete with file preservation).

Pattern: Service for moving assets to retired storage while keeping DB records.

In Studio/Pipeline modes, assets are retired instead of permanently deleted:
- DB record stays with is_retired = 1
- Files move to _retired/{type}/{name}/{variant}/ folder
- Variants can still reference retired bases (reference intact)
- Admins can restore retired assets later
"""

import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Set

from ..config import Config
from .database_service import get_database_service
from .user_service import get_user_service

logger = logging.getLogger(__name__)


class RetireService:
    """
    Service for retiring assets (moving files to _retired/ folder).

    Key behavior:
    - Keeps DB record in assets table with is_retired = 1
    - Moves files/folders to _retired/ based on actual file paths in DB
    - Updates file paths in DB record for ALL versions
    - ALL versions of a variant retire together
    - Variants stay active (don't cascade) - they still reference the retired base
    """

    def __init__(self):
        self._db_service = get_database_service()
        self._user_service = get_user_service()

    def retire_asset(self, uuid: str) -> Tuple[bool, str]:
        """
        Retire an asset and all its versions.

        Uses actual file paths from DB to determine what folders to move.
        Moves all files to _retired/ folder structure.

        Args:
            uuid: Asset UUID to retire

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Get asset from database
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            return False, f"Asset not found: {uuid}"

        # Check if already retired
        if asset.get('is_retired', 0) == 1:
            return False, "Asset is already retired"

        # Get asset info
        asset_type = asset.get('asset_type', 'other')
        asset_name = asset.get('name', 'Unknown')
        variant_name = asset.get('variant_name', 'Base')
        version_group_id = asset.get('version_group_id') or asset.get('asset_id') or uuid

        # Get ALL versions in this version group for this variant
        all_versions = self._db_service.get_asset_versions(version_group_id)
        if not all_versions:
            all_versions = [asset]

        # Filter to only versions of this specific variant
        versions_to_retire = [
            v for v in all_versions
            if v.get('variant_name', 'Base') == variant_name
        ]

        if not versions_to_retire:
            versions_to_retire = [asset]

        # Get current user for audit trail
        current_user = self._user_service.get_current_username()
        retire_time = datetime.now()

        try:
            storage_path = Config.load_library_path()
            if not storage_path:
                return False, "Storage path not configured"

            # Destination base path
            retired_base = Config.get_retired_asset_path(asset_type, asset_name, variant_name)
            retired_base.mkdir(parents=True, exist_ok=True)

            # Collect all source folders that need to be moved
            # (based on actual file paths in DB)
            folders_to_move: Set[Path] = set()

            for version in versions_to_retire:
                for path_key in ['blend_backup_path', 'thumbnail_path', 'usd_file_path', 'preview_path']:
                    file_path = version.get(path_key, '')
                    if file_path:
                        p = Path(file_path)
                        if p.exists():
                            # Add parent folder to set of folders to move
                            folders_to_move.add(p.parent)

            # Also find library folder files (.current.blend, .proxy.blend, etc.)
            # These are in the library folder, not archive
            type_folder = Config.get_type_folder(asset_type)
            family_folder = Config.sanitize_filename(asset_name)

            # Check both naming conventions for library
            library_variants = [
                storage_path / Config.LIBRARY_FOLDER / type_folder / family_folder / variant_name,
                # Legacy naming: type/name/ without variant subfolder
                storage_path / Config.LIBRARY_FOLDER / type_folder / family_folder,
            ]

            for lib_path in library_variants:
                if lib_path.exists() and any(lib_path.iterdir()):
                    folders_to_move.add(lib_path)

            # IMPORTANT: Also add the archive folder for this variant
            # The archive stores ALL versions, but DB paths may only reference library for latest
            archive_variant_path = storage_path / Config.ARCHIVE_FOLDER / type_folder / family_folder / variant_name
            if archive_variant_path.exists() and any(archive_variant_path.iterdir()):
                # Add each version subfolder individually so they get proper destination paths
                for version_dir in archive_variant_path.iterdir():
                    if version_dir.is_dir():
                        folders_to_move.add(version_dir)

            # Track what we moved for rollback
            moved_items: List[Tuple[Path, Path]] = []
            errors = []

            # Move each folder's contents
            for src_folder in folders_to_move:
                if not src_folder.exists():
                    continue

                # Determine destination subfolder based on source location
                try:
                    rel_path = src_folder.relative_to(storage_path)
                    # Check if it's in library or archive
                    parts = rel_path.parts

                    if parts[0] == Config.LIBRARY_FOLDER:
                        # Goes to retired/library/
                        dst_subfolder = retired_base / "library"
                    elif parts[0] == Config.ARCHIVE_FOLDER:
                        # Goes to retired/archive/{rest_of_path}
                        # Extract version folder name if present
                        if len(parts) > 3:
                            # _archive/type/name/variant_version or similar
                            version_part = parts[-1]  # Last part (e.g., "v003" or "Base v003")
                            dst_subfolder = retired_base / "archive" / version_part
                        else:
                            dst_subfolder = retired_base / "archive"
                    else:
                        # Unknown location, put in archive
                        dst_subfolder = retired_base / "archive" / src_folder.name

                except ValueError:
                    # Not relative to storage - use folder name
                    dst_subfolder = retired_base / "archive" / src_folder.name

                dst_subfolder.mkdir(parents=True, exist_ok=True)

                # Move all files from source to destination
                for item in list(src_folder.iterdir()):
                    dst_item = dst_subfolder / item.name
                    try:
                        if dst_item.exists():
                            if dst_item.is_dir():
                                shutil.rmtree(str(dst_item))
                            else:
                                dst_item.unlink()
                        shutil.move(str(item), str(dst_item))
                        moved_items.append((dst_item, item))
                        logger.info(f"Moved: {item} -> {dst_item}")
                    except Exception as e:
                        errors.append(f"Failed to move {item.name}: {e}")
                        logger.warning(f"Failed to move {item}: {e}")

                # Try to remove empty source folder
                self._remove_empty_parents(src_folder, storage_path)

            # Update database paths for ALL versions
            retired_count = 0

            for version in versions_to_retire:
                v_uuid = version.get('uuid')
                v_label = version.get('version_label', 'v001')

                try:
                    updates = self._compute_retired_paths(version, retired_base)
                    updates['is_retired'] = 1
                    updates['retired_date'] = retire_time.isoformat()
                    updates['retired_by'] = current_user

                    if self._db_service.update_asset(v_uuid, updates):
                        retired_count += 1
                    else:
                        errors.append(f"{v_label}: DB update failed")
                except Exception as e:
                    errors.append(f"{v_label}: {e}")
                    logger.exception(f"Error updating DB for version {v_uuid}")

            if retired_count == 0:
                # Rollback moves
                self._rollback_moves(moved_items)
                return False, f"Failed to retire any versions: {'; '.join(errors)}"

            if errors:
                return True, f"Retired {retired_count} version(s) with {len(errors)} warning(s)"

            return True, f"Retired {retired_count} version(s) of {asset_name}/{variant_name}"

        except Exception as e:
            logger.exception(f"Error retiring asset {uuid}")
            return False, f"Error: {e}"

    def _compute_retired_paths(self, asset: Dict[str, Any], retired_base: Path) -> Dict[str, Any]:
        """
        Compute new file paths after move to retired folder.
        Searches for files in the retired folder structure.
        """
        updates = {}

        for path_key in ['blend_backup_path', 'thumbnail_path', 'usd_file_path', 'preview_path']:
            old_path = asset.get(path_key, '')
            if not old_path:
                continue

            old_file = Path(old_path)
            filename = old_file.name

            # Search for the file in retired folder
            for found_file in retired_base.rglob(filename):
                updates[path_key] = str(found_file)
                break

        return updates

    def _remove_empty_parents(self, folder: Path, stop_at: Path):
        """Remove folder and empty parent folders up to stop_at."""
        try:
            current = folder
            while current != stop_at and current.exists():
                if not any(current.iterdir()):
                    current.rmdir()
                    logger.info(f"Removed empty folder: {current}")
                    current = current.parent
                else:
                    break
        except Exception as e:
            logger.warning(f"Error removing empty folders: {e}")

    def _rollback_moves(self, moved_items: List[Tuple[Path, Path]]):
        """Rollback file moves on error."""
        for dst, src in reversed(moved_items):
            try:
                if dst.exists():
                    src.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(src))
            except Exception as e:
                logger.error(f"Rollback failed for {dst}: {e}")

    def restore_from_retired(self, uuid: str) -> Tuple[bool, str]:
        """
        Restore a retired asset back to active library.

        Args:
            uuid: Asset UUID to restore

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Get asset from database
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            return False, f"Asset not found: {uuid}"

        # Check if actually retired
        if asset.get('is_retired', 0) != 1:
            return False, "Asset is not retired"

        # Get asset info
        asset_type = asset.get('asset_type', 'other')
        asset_name = asset.get('name', 'Unknown')
        variant_name = asset.get('variant_name', 'Base')
        version_group_id = asset.get('version_group_id') or asset.get('asset_id') or uuid

        # Get all retired versions of this variant
        all_versions = self._db_service.get_asset_versions(version_group_id)
        versions_to_restore = [
            v for v in all_versions
            if v.get('variant_name', 'Base') == variant_name and v.get('is_retired', 0) == 1
        ]

        if not versions_to_restore:
            versions_to_restore = [asset]

        try:
            storage_path = Config.load_library_path()
            if not storage_path:
                return False, "Storage path not configured"

            retired_base = Config.get_retired_asset_path(asset_type, asset_name, variant_name)

            if not retired_base.exists():
                return False, "Retired folder not found"

            # Destination paths
            type_folder = Config.get_type_folder(asset_type)
            family_folder = Config.sanitize_filename(asset_name)

            dst_library = storage_path / Config.LIBRARY_FOLDER / type_folder / family_folder / variant_name
            dst_archive = storage_path / Config.ARCHIVE_FOLDER / type_folder / family_folder / variant_name

            moved_items: List[Tuple[Path, Path]] = []
            errors = []

            # Move library folder back
            src_library = retired_base / "library"
            if src_library.exists() and any(src_library.iterdir()):
                dst_library.mkdir(parents=True, exist_ok=True)
                for item in list(src_library.iterdir()):
                    dst_item = dst_library / item.name
                    try:
                        if dst_item.exists():
                            if dst_item.is_dir():
                                shutil.rmtree(str(dst_item))
                            else:
                                dst_item.unlink()
                        shutil.move(str(item), str(dst_item))
                        moved_items.append((dst_item, item))
                    except Exception as e:
                        errors.append(f"Library {item.name}: {e}")

            # Move archive folders back
            src_archive = retired_base / "archive"
            if src_archive.exists():
                for version_folder in list(src_archive.iterdir()):
                    if version_folder.is_dir():
                        dst_version = dst_archive / version_folder.name
                        dst_version.mkdir(parents=True, exist_ok=True)
                        for item in list(version_folder.iterdir()):
                            dst_item = dst_version / item.name
                            try:
                                if dst_item.exists():
                                    dst_item.unlink()
                                shutil.move(str(item), str(dst_item))
                                moved_items.append((dst_item, item))
                            except Exception as e:
                                errors.append(f"Archive {item.name}: {e}")

            # Update database paths for ALL versions
            restored_count = 0

            for version in versions_to_restore:
                v_uuid = version.get('uuid')
                v_label = version.get('version_label', 'v001')

                try:
                    updates = self._compute_active_paths(version, dst_library, dst_archive)
                    updates['is_retired'] = 0
                    updates['retired_date'] = None
                    updates['retired_by'] = None

                    if self._db_service.update_asset(v_uuid, updates):
                        restored_count += 1
                    else:
                        errors.append(f"{v_label}: DB update failed")
                except Exception as e:
                    errors.append(f"{v_label}: {e}")

            # Cleanup empty retired folders
            self._cleanup_empty_retired_folders(asset)

            if restored_count == 0:
                self._rollback_moves(moved_items)
                return False, f"Failed to restore: {'; '.join(errors)}"

            return True, f"Restored {restored_count} version(s) of {asset_name}/{variant_name}"

        except Exception as e:
            logger.exception(f"Error restoring asset {uuid}")
            return False, f"Error: {e}"

    def _compute_active_paths(
        self,
        asset: Dict[str, Any],
        dst_library: Path,
        dst_archive: Path
    ) -> Dict[str, Any]:
        """Compute paths after restoring to active library."""
        updates = {}

        for path_key in ['blend_backup_path', 'thumbnail_path', 'usd_file_path', 'preview_path']:
            old_path = asset.get(path_key, '')
            if not old_path:
                continue

            old_file = Path(old_path)
            filename = old_file.name

            # Search in archive first (versioned files)
            for found_file in dst_archive.rglob(filename):
                updates[path_key] = str(found_file)
                break
            else:
                # Search in library
                for found_file in dst_library.rglob(filename):
                    updates[path_key] = str(found_file)
                    break

        return updates

    def _cleanup_empty_retired_folders(self, asset: Dict[str, Any]):
        """Remove empty retired folders after restoration."""
        asset_type = asset.get('asset_type', 'other')
        asset_name = asset.get('name', 'Unknown')
        variant_name = asset.get('variant_name', 'Base')

        try:
            retired_path = Config.get_retired_asset_path(asset_type, asset_name, variant_name)

            # Remove empty subfolders
            for subfolder in ['archive', 'library']:
                sub_path = retired_path / subfolder
                if sub_path.exists():
                    # Remove empty version folders inside archive
                    if subfolder == 'archive':
                        for version_dir in list(sub_path.iterdir()):
                            if version_dir.is_dir() and not any(version_dir.iterdir()):
                                version_dir.rmdir()
                    # Remove subfolder if empty
                    if not any(sub_path.iterdir()):
                        sub_path.rmdir()

            # Remove variant folder if empty
            if retired_path.exists() and not any(retired_path.iterdir()):
                retired_path.rmdir()

            # Remove asset name folder if empty
            name_folder = retired_path.parent
            if name_folder.exists() and not any(name_folder.iterdir()):
                name_folder.rmdir()

            # Remove type folder if empty
            type_folder = name_folder.parent
            if type_folder.exists() and not any(type_folder.iterdir()):
                type_folder.rmdir()

        except Exception as e:
            logger.warning(f"Failed to cleanup retired folders: {e}")

    def get_retired_assets(self, include_all_versions: bool = False) -> List[Dict[str, Any]]:
        """Get all retired assets."""
        conn = self._db_service._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM assets WHERE is_retired = 1"
        if not include_all_versions:
            query += " AND is_latest = 1"
        query += " ORDER BY retired_date DESC, name"

        cursor.execute(query)

        results = []
        for row in cursor.fetchall():
            results.append(dict(row))
        return results

    def is_retired(self, uuid: str) -> bool:
        """Check if a specific asset is retired."""
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            return False
        return asset.get('is_retired', 0) == 1

    def get_retire_info(self, uuid: str) -> Dict[str, Any]:
        """Get information about what will be retired."""
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            return {'error': 'Asset not found'}

        variant_name = asset.get('variant_name', 'Base')
        version_group_id = asset.get('version_group_id') or asset.get('asset_id') or uuid

        all_versions = self._db_service.get_asset_versions(version_group_id)
        versions_in_variant = [
            v for v in all_versions
            if v.get('variant_name', 'Base') == variant_name
        ]

        return {
            'name': asset.get('name', 'Unknown'),
            'variant_name': variant_name,
            'version_count': len(versions_in_variant),
            'version_labels': [v.get('version_label', 'v???') for v in versions_in_variant],
            'is_base': variant_name == 'Base',
            'asset_type': asset.get('asset_type', 'other'),
        }


# Singleton instance
_retire_service_instance: Optional[RetireService] = None


def get_retire_service() -> RetireService:
    """Get global RetireService singleton instance."""
    global _retire_service_instance
    if _retire_service_instance is None:
        _retire_service_instance = RetireService()
    return _retire_service_instance


__all__ = ['RetireService', 'get_retire_service']
