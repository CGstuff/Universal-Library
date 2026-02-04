"""
AssetFileOps - Asset file operations (rename, move).

Handles:
- Renaming assets (filesystem + database)
- Moving assets between folders (virtual - database only)
- Atomic operations with rollback support for renames
"""

import logging
import os
import re
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Callable, Dict, Any

from ..config import Config

logger = logging.getLogger(__name__)


class AssetFileOps:
    """
    Handles filesystem operations for assets.

    Rename uses two-phase commit pattern:
    1. Filesystem changes (with rollback)
    2. Database updates (transactional)

    Move is virtual (database only) - folders are organizational
    containers that don't affect physical file locations.
    """

    def __init__(
        self,
        get_asset: Callable[[str], Optional[Dict[str, Any]]],
        update_asset: Callable[[str, Dict[str, Any]], bool],
        name_exists: Callable[..., bool],
        get_versions: Callable[[str], list],
        get_folder_path: Callable[[int], Optional[str]],
        set_asset_folders: Callable[[str, list], bool],
        get_asset_folders: Callable[[str], list],
        remove_asset_from_folder: Callable[[str, int], bool],
    ):
        """
        Initialize with database operation callbacks.

        Args:
            get_asset: Function to get asset by UUID
            update_asset: Function to update asset
            name_exists: Function to check if name exists
            get_versions: Function to get asset versions
            get_folder_path: Function to get folder full path
            set_asset_folders: Function to set asset folder memberships
            get_asset_folders: Function to get asset folders
            remove_asset_from_folder: Function to remove asset from folder
        """
        self._get_asset = get_asset
        self._update_asset = update_asset
        self._name_exists = name_exists
        self._get_versions = get_versions
        self._get_folder_path = get_folder_path
        self._set_asset_folders = set_asset_folders
        self._get_asset_folders = get_asset_folders
        self._remove_asset_from_folder = remove_asset_from_folder

    def rename_asset(self, uuid: str, new_name: str) -> Tuple[bool, str]:
        """
        Rename an asset with atomic filesystem operations and rollback support.

        Uses two-phase commit pattern:
        1. Rename filesystem (can fail, has rollback)
        2. Update database in transaction

        Args:
            uuid: Asset UUID
            new_name: New asset name (will be sanitized)

        Returns:
            Tuple of (success, message)
        """
        asset = self._get_asset(uuid)
        if not asset:
            return False, f"Asset not found: {uuid}"

        old_name = asset.get('name')
        if not old_name:
            return False, "Asset has no name"

        # Sanitize new name
        safe_new_name = re.sub(r'[<>:"/\\|?*]', '_', new_name)
        safe_new_name = safe_new_name.strip(' .')
        safe_new_name = re.sub(r'_+', '_', safe_new_name) or 'unnamed'

        if safe_new_name == old_name:
            return True, "Name unchanged"

        # Check for name collision (exclude current asset from check)
        if self._name_exists(safe_new_name, folder_id=None, exclude_uuid=uuid):
            return False, f"An asset with the name '{safe_new_name}' already exists"

        # Get paths
        blend_path = asset.get('blend_backup_path')
        if not blend_path:
            return False, "Asset has no blend file path"

        blend_file = Path(blend_path)
        if not blend_file.exists():
            return False, f"Blend file not found: {blend_path}"

        # Calculate old and new folder paths
        # Structure: library/{type}/{name}/{variant}/
        variant_folder = blend_file.parent
        asset_folder = variant_folder.parent
        type_folder = asset_folder.parent
        new_asset_folder = type_folder / safe_new_name

        # Track renamed items for rollback
        renamed_items = []

        try:
            # Phase 1: Rename asset folder
            if asset_folder.exists() and asset_folder != new_asset_folder:
                if new_asset_folder.exists():
                    return False, f"Target folder already exists: {new_asset_folder}"

                self._rename_with_retry(asset_folder, new_asset_folder)
                renamed_items.append((new_asset_folder, asset_folder))

            # Phase 2: Rename files inside each variant folder
            for vf in new_asset_folder.iterdir():
                if not vf.is_dir():
                    continue

                for ext in ['.blend', '.json', '.usd', '.usda', '.usdc']:
                    old_file = vf / f"{old_name}{ext}"
                    new_file = vf / f"{safe_new_name}{ext}"
                    if old_file.exists():
                        self._rename_with_retry(old_file, new_file)
                        renamed_items.append((new_file, old_file))

                # Rename representation reference files (.current, .proxy, .render)
                for suffix in ['.current', '.proxy', '.render']:
                    old_ref = vf / f"{old_name}{suffix}.blend"
                    new_ref = vf / f"{safe_new_name}{suffix}.blend"
                    if old_ref.exists():
                        self._rename_with_retry(old_ref, new_ref)
                        renamed_items.append((new_ref, old_ref))

            # Phase 3: Update JSON sidecar content
            for vf in new_asset_folder.iterdir():
                if not vf.is_dir():
                    continue

                json_file = vf / f"{safe_new_name}.json"
                if json_file.exists():
                    self._update_json_name(json_file, safe_new_name)

            # Phase 4: Update database
            variant_name = asset.get('variant_name', 'Base')
            version_label = asset.get('version_label', 'v001')
            new_variant_folder = new_asset_folder / variant_name
            new_blend_path = new_variant_folder / f"{safe_new_name}.{version_label}.blend"
            new_thumbnail_path = new_variant_folder / f"thumbnail.{version_label}.png"

            updates = {
                'name': safe_new_name,
                'blend_backup_path': str(new_blend_path) if new_blend_path.exists() else None,
                'thumbnail_path': str(new_thumbnail_path) if new_thumbnail_path.exists() else None,
                'modified_date': datetime.now().isoformat(),
            }

            # Update USD path if exists
            usd_path = asset.get('usd_file_path')
            if usd_path:
                old_usd = Path(usd_path)
                if old_usd.suffix:
                    new_usd = new_variant_folder / f"{safe_new_name}{old_usd.suffix}"
                    if new_usd.exists():
                        updates['usd_file_path'] = str(new_usd)

            self._update_asset(uuid, updates)

            # Also update all other versions of this asset
            version_group_id = asset.get('version_group_id')
            if version_group_id:
                self._update_version_paths(
                    version_group_id, uuid, safe_new_name, new_asset_folder
                )

            return True, f"Successfully renamed to '{safe_new_name}'"

        except Exception as e:
            # Rollback: Restore original names
            for new_path, old_path in reversed(renamed_items):
                try:
                    os.replace(str(new_path), str(old_path))
                except Exception as rollback_err:
                    logger.warning(f"Rollback failed for {new_path}: {rollback_err}")
            return False, f"Rename failed: {e}"

    def move_asset_to_folder(
        self,
        asset_uuid: str,
        target_folder_id: Optional[int]
    ) -> Tuple[bool, str]:
        """
        Move asset to a different folder (virtual - database only).

        Folders are virtual organizational containers. This operation only
        updates the asset's folder membership in the database. Physical files
        remain in place, ensuring linked/instanced assets never break.

        Args:
            asset_uuid: Asset UUID to move
            target_folder_id: Target folder ID (None = remove from all folders)

        Returns:
            Tuple of (success, message)
        """
        asset = self._get_asset(asset_uuid)
        if not asset:
            return False, f"Asset not found: {asset_uuid}"

        try:
            # Virtual move - update folder membership only
            if target_folder_id:
                # Move to target folder
                self._set_asset_folders(asset_uuid, [target_folder_id])
            else:
                # Remove from all folders (root level)
                current_folders = self._get_asset_folders(asset_uuid)
                for folder in current_folders:
                    self._remove_asset_from_folder(asset_uuid, folder.get('id'))

            # Update modified date
            self._update_asset(asset_uuid, {
                'modified_date': datetime.now().isoformat(),
            })

            return True, "Successfully moved to folder"

        except Exception as e:
            return False, f"Move failed: {e}"

    def _rename_with_retry(
        self,
        src: Path,
        dst: Path,
        max_retries: int = 3,
        delay: float = 0.2
    ) -> bool:
        """Rename with retry for file lock issues."""
        for attempt in range(max_retries):
            try:
                os.replace(str(src), str(dst))
                return True
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(delay)
                else:
                    raise
        return False

    def _update_json_name(self, json_file: Path, new_name: str):
        """Update name in JSON sidecar file."""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            json_data['name'] = new_name
            json_data['modified_date'] = datetime.utcnow().isoformat() + 'Z'
            # Atomic write
            temp_path = json_file.with_suffix('.json.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            os.replace(str(temp_path), str(json_file))
        except Exception as e:
            logger.warning(f"Could not update JSON: {e}")

    def _update_version_paths(
        self,
        version_group_id: str,
        exclude_uuid: str,
        new_name: str,
        new_asset_folder: Path
    ):
        """Update paths for all versions after rename."""
        all_versions = self._get_versions(version_group_id)
        for version in all_versions:
            v_uuid = version.get('uuid')
            if v_uuid and v_uuid != exclude_uuid:
                v_variant = version.get('variant_name', 'Base')
                v_version_label = version.get('version_label', 'v001')
                v_variant_folder = new_asset_folder / v_variant
                v_blend = v_variant_folder / f"{new_name}.{v_version_label}.blend"
                v_thumb = v_variant_folder / f"thumbnail.{v_version_label}.png"
                v_updates = {
                    'name': new_name,
                    'modified_date': datetime.now().isoformat(),
                }
                if v_blend.exists():
                    v_updates['blend_backup_path'] = str(v_blend)
                if v_thumb.exists():
                    v_updates['thumbnail_path'] = str(v_thumb)
                self._update_asset(v_uuid, v_updates)


__all__ = ['AssetFileOps']
