"""
ArchiveService - Manages asset file storage with type-based folder structure

Structure:
    storage/
    ├── library/{type}/{name}/{variant}/              # Active/latest versions
    ├── _archive/{type}/{name}/{variant}/{version}/   # All versions
    └── reviews/{type}/{name}/{variant}/{version}/    # Review data

Types: meshes, materials, rigs, lights, cameras, collections, other

Pattern: Service for file management between library and archive folders.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)

from ..config import Config
from .database_service import get_database_service
# Lazy imports to avoid circular dependency
def get_current_reference_service():
    from .current_reference_service import get_current_reference_service as _get_svc
    return _get_svc()

def get_representation_service():
    from .representation_service import get_representation_service as _get_svc
    return _get_svc()


class ArchiveService:
    """
    Manages asset file storage with the new folder structure.

    Key concepts:
    - library/: Contains only the latest version of each variant (hot storage)
    - _archive/: Contains ALL versions including latest (complete history)
    - Files in library/ are the "working" copies
    - Files in _archive/ are immutable after creation

    Workflow:
    - NEW ASSET: Save to library/ AND archive/v001/
    - NEW VERSION: Archive current, save new to library/ AND archive/vXXX/
    - IMPORT LATEST: Read from library/
    - IMPORT SPECIFIC VERSION: Read from _archive/
    """

    def __init__(self):
        self._db_service = get_database_service()

    # ==================== PATH GENERATION ====================

    def get_library_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        asset_type: str = 'other'
    ) -> Path:
        """Get path for active/latest version in library folder."""
        return Config.get_asset_library_path(asset_id, asset_name, variant_name, asset_type)

    def get_archive_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        asset_type: str = 'other'
    ) -> Path:
        """Get path for specific version in archive folder."""
        return Config.get_asset_archive_path(asset_id, asset_name, variant_name, version_label, asset_type)

    def get_reviews_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        asset_type: str = 'other'
    ) -> Path:
        """Get path for review data."""
        return Config.get_asset_reviews_path(asset_id, asset_name, variant_name, version_label, asset_type)

    # ==================== FILE OPERATIONS ====================

    def save_new_asset(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        blend_source_path: Path,
        thumbnail_source_path: Optional[Path] = None,
        asset_type: str = 'other'
    ) -> Tuple[bool, Dict[str, str]]:
        """
        Save a new asset to both library and archive.

        Args:
            asset_id: Asset family UUID
            asset_name: Human-readable name
            variant_name: Variant name (e.g., 'Base')
            version_label: Version label (e.g., 'v001')
            blend_source_path: Path to source .blend file
            thumbnail_source_path: Optional path to thumbnail
            asset_type: Asset type for folder organization (mesh, material, etc.)

        Returns:
            Tuple of (success, paths_dict with 'library_path', 'archive_path', 'blend_path', 'thumbnail_path')
        """
        try:
            # Create directories
            library_dir = self.get_library_path(asset_id, asset_name, variant_name, asset_type)
            archive_dir = self.get_archive_path(asset_id, asset_name, variant_name, version_label, asset_type)
            library_dir.mkdir(parents=True, exist_ok=True)
            archive_dir.mkdir(parents=True, exist_ok=True)

            # Sanitize filename and include version in filename to prevent
            # Blender from merging libraries with same filename
            safe_name = Config.sanitize_filename(asset_name)
            blend_filename = f"{safe_name}.{version_label}.blend"
            json_filename = f"{safe_name}.{version_label}.json"
            thumbnail_filename = "thumbnail.png"

            paths = {
                'library_path': str(library_dir),
                'archive_path': str(archive_dir),
            }

            # Copy blend file to both locations
            library_blend = library_dir / blend_filename
            archive_blend = archive_dir / blend_filename

            shutil.copy2(str(blend_source_path), str(archive_blend))
            shutil.copy2(str(blend_source_path), str(library_blend))

            paths['blend_path'] = str(library_blend)
            paths['archive_blend_path'] = str(archive_blend)

            # Create .current.blend proxy for auto-updating links
            current_service = get_current_reference_service()
            success, result = current_service.create_current_reference(library_blend)
            if success:
                paths['current_blend_path'] = result
            else:
                pass

            # Copy thumbnail if provided
            if thumbnail_source_path and thumbnail_source_path.exists():
                library_thumb = library_dir / thumbnail_filename
                archive_thumb = archive_dir / thumbnail_filename

                shutil.copy2(str(thumbnail_source_path), str(archive_thumb))
                shutil.copy2(str(thumbnail_source_path), str(library_thumb))

                paths['thumbnail_path'] = str(library_thumb)
                paths['archive_thumbnail_path'] = str(archive_thumb)

            # Copy JSON metadata if exists in library
            library_json = library_dir / json_filename
            archive_json = archive_dir / json_filename
            if library_json.exists():
                shutil.copy2(str(library_json), str(archive_json))
                paths['json_path'] = str(library_json)
                paths['archive_json_path'] = str(archive_json)

            # Save metadata snapshot to archive
            self._save_archive_metadata(archive_dir, {
                'asset_id': asset_id,
                'asset_name': asset_name,
                'variant_name': variant_name,
                'version_label': version_label,
                'archived_at': datetime.utcnow().isoformat() + 'Z',
            })

            # Create symlink/junction for "latest" marker
            self._create_latest_marker(library_dir, archive_dir)

            return True, paths

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, {'error': str(e)}

    def save_new_version(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        new_version_label: str,
        blend_source_path: Path,
        thumbnail_source_path: Optional[Path] = None,
        previous_version_label: Optional[str] = None,
        asset_type: str = 'other'
    ) -> Tuple[bool, Dict[str, str]]:
        """
        Save a new version, archiving the previous one.

        Args:
            asset_id: Asset family UUID
            asset_name: Human-readable name
            variant_name: Variant name
            new_version_label: New version label (e.g., 'v002')
            blend_source_path: Path to new .blend file
            thumbnail_source_path: Optional path to new thumbnail
            previous_version_label: Label of previous version (for archiving current library files)
            asset_type: Asset type for folder organization (mesh, material, etc.)

        Returns:
            Tuple of (success, paths_dict)
        """
        try:
            library_dir = self.get_library_path(asset_id, asset_name, variant_name, asset_type)
            new_archive_dir = self.get_archive_path(asset_id, asset_name, variant_name, new_version_label, asset_type)

            # Archive current library files if they exist and previous version specified
            if previous_version_label and library_dir.exists():
                prev_archive_dir = self.get_archive_path(
                    asset_id, asset_name, variant_name, previous_version_label, asset_type
                )
                if not prev_archive_dir.exists():
                    # Archive current library to previous version folder
                    self._archive_library_to_version(library_dir, prev_archive_dir)

            # Now save the new version (same as save_new_asset)
            success, paths = self.save_new_asset(
                asset_id, asset_name, variant_name, new_version_label,
                blend_source_path, thumbnail_source_path, asset_type
            )

            # Notify RepresentationService so .render.blend auto-updates
            # if render designation is set to "latest" (default)
            if success:
                try:
                    rep_service = get_representation_service()
                    rep_service.on_new_version_created(
                        version_group_id=asset_id,
                        variant_name=variant_name,
                        asset_name=asset_name,
                        asset_type=asset_type,
                        asset_id=asset_id,
                    )
                except Exception as e:
                    logger.debug(f"RepresentationService notification failed: {e}")

            return success, paths

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, {'error': str(e)}

    def _archive_library_to_version(self, library_dir: Path, archive_dir: Path):
        """Copy files from library to a specific archive version folder.

        Copies all asset files including:
        - .blend files
        - .json metadata files
        - thumbnail.png
        - Any other asset files
        """
        if not library_dir.exists():
            return

        archive_dir.mkdir(parents=True, exist_ok=True)

        # Copy all files except marker files and representation references
        skip_files = {'latest', 'latest.txt'}
        skip_suffixes = {'.current.blend', '.proxy.blend', '.render.blend'}
        for file in library_dir.iterdir():
            if file.is_file() and file.name not in skip_files:
                if not any(file.name.endswith(s) for s in skip_suffixes):
                    shutil.copy2(str(file), str(archive_dir / file.name))

        # Save archive metadata
        self._save_archive_metadata(archive_dir, {
            'archived_at': datetime.utcnow().isoformat() + 'Z',
            'archived_from': 'library',
        })

    def _save_archive_metadata(self, archive_dir: Path, metadata: Dict):
        """Save metadata snapshot to archive folder."""
        meta_file = archive_dir / 'meta.json'
        try:
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not write archive metadata {meta_file}: {e}")

    def _create_latest_marker(self, library_dir: Path, archive_dir: Path):
        """Create a marker file pointing to the archive version."""
        # On Windows, symlinks require admin or developer mode
        # Use a simple text file instead for cross-platform compatibility
        marker_file = library_dir / 'latest.txt'
        try:
            with open(marker_file, 'w', encoding='utf-8') as f:
                f.write(str(archive_dir))
        except Exception as e:
            logger.debug(f"Could not create latest marker {marker_file}: {e}")

    # ==================== FILE ACCESS ====================

    def get_latest_blend_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        asset_type: str = 'other'
    ) -> Optional[Path]:
        """Get path to latest .blend file for an asset variant.

        Searches for versioned filenames first (e.g., Sword.v002.blend),
        then falls back to legacy unversioned filenames (Sword.blend).
        """
        library_dir = self.get_library_path(asset_id, asset_name, variant_name, asset_type)
        safe_name = Config.sanitize_filename(asset_name)

        if not library_dir.exists():
            return None

        # Try versioned pattern first: AssetName.vXXX.blend
        # Find highest version number
        import re
        version_pattern = re.compile(rf'^{re.escape(safe_name)}\.v(\d{{3,}})\.blend$')
        highest_version = -1
        highest_path = None

        for file in library_dir.glob(f"{safe_name}.v*.blend"):
            match = version_pattern.match(file.name)
            if match:
                version_num = int(match.group(1))
                if version_num > highest_version:
                    highest_version = version_num
                    highest_path = file

        if highest_path and highest_path.exists():
            return highest_path

        # Fallback: legacy unversioned filename
        legacy_path = library_dir / f"{safe_name}.blend"
        if legacy_path.exists():
            return legacy_path

        # Last resort: find any .blend file (excluding representation files)
        for file in library_dir.glob("*.blend"):
            if not any(file.name.endswith(s) for s in ('.current.blend', '.proxy.blend', '.render.blend')):
                return file

        return None

    def get_version_blend_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        asset_type: str = 'other'
    ) -> Optional[Path]:
        """Get path to a specific version's .blend file.

        Searches for versioned filename first (e.g., Sword.v001.blend),
        then falls back to legacy unversioned filename (Sword.blend).
        """
        archive_dir = self.get_archive_path(asset_id, asset_name, variant_name, version_label, asset_type)
        safe_name = Config.sanitize_filename(asset_name)

        if not archive_dir.exists():
            return None

        # Try versioned filename first: AssetName.vXXX.blend
        versioned_path = archive_dir / f"{safe_name}.{version_label}.blend"
        if versioned_path.exists():
            return versioned_path

        # Fallback: legacy unversioned filename
        legacy_path = archive_dir / f"{safe_name}.blend"
        if legacy_path.exists():
            return legacy_path

        # Last resort: find any .blend file
        for file in archive_dir.glob("*.blend"):
            return file

        return None

    def get_available_versions(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        asset_type: str = 'other'
    ) -> List[str]:
        """Get list of available version labels for an asset variant."""
        try:
            type_folder = Config.get_type_folder(asset_type)
            family_folder = Config.get_family_folder_name(asset_id, asset_name)
            archive_base = Config.get_archive_folder() / type_folder / family_folder / variant_name

            if not archive_base.exists():
                return []

            versions = []
            for item in archive_base.iterdir():
                if item.is_dir() and item.name.startswith('v'):
                    versions.append(item.name)

            return sorted(versions)

        except Exception as e:
            logger.debug(f"Could not list versions for {asset_name}/{variant_name}: {e}")
            return []

    # ==================== CLEANUP ====================

    def delete_asset_files(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: Optional[str] = None,
        delete_all_versions: bool = False,
        asset_type: str = 'other'
    ) -> Tuple[bool, str]:
        """
        Delete asset files.

        Args:
            asset_id: Asset family UUID
            asset_name: Asset name
            variant_name: Variant name
            version_label: Specific version to delete (if None, deletes from library only)
            delete_all_versions: If True, delete all versions and the variant folder
            asset_type: Asset type for folder organization (mesh, material, etc.)

        Returns:
            Tuple of (success, message)
        """
        try:
            type_folder = Config.get_type_folder(asset_type)
            family_folder = Config.get_family_folder_name(asset_id, asset_name)

            if delete_all_versions:
                # Delete entire variant from both library and archive
                library_variant = Config.get_library_folder() / type_folder / family_folder / variant_name
                archive_variant = Config.get_archive_folder() / type_folder / family_folder / variant_name
                reviews_variant = Config.get_reviews_folder() / type_folder / family_folder / variant_name

                for path in [library_variant, archive_variant, reviews_variant]:
                    if path.exists():
                        shutil.rmtree(str(path))

                return True, f"Deleted all versions of {variant_name}"

            elif version_label:
                # Delete specific version from archive only
                archive_version = self.get_archive_path(asset_id, asset_name, variant_name, version_label, asset_type)
                reviews_version = self.get_reviews_path(asset_id, asset_name, variant_name, version_label, asset_type)

                for path in [archive_version, reviews_version]:
                    if path.exists():
                        shutil.rmtree(str(path))

                return True, f"Deleted version {version_label}"

            else:
                # Delete from library only (keep archive)
                library_dir = self.get_library_path(asset_id, asset_name, variant_name, asset_type)
                if library_dir.exists():
                    shutil.rmtree(str(library_dir))
                return True, "Deleted from library"

        except Exception as e:
            return False, f"Error deleting files: {e}"


    # ==================== JSON METADATA MIGRATION ====================

    def create_json_for_asset(self, asset: Dict[str, Any]) -> bool:
        """
        Create JSON metadata file for an existing asset.

        This is used for migration - creating JSON files for assets
        that were created before JSON sidecar support was added.

        Args:
            asset: Asset dictionary from database

        Returns:
            True if JSON was created, False if skipped or failed
        """
        try:
            # Get the blend file path
            blend_path = asset.get('blend_backup_path')
            if not blend_path:
                return False

            blend_file = Path(blend_path)
            if not blend_file.exists():
                return False

            # Check if JSON already exists
            json_path = blend_file.with_suffix('.json')
            if json_path.exists():
                return False  # Already has JSON

            # Build metadata from database
            metadata = {
                "uuid": asset.get('uuid'),
                "name": asset.get('name'),
                "asset_type": asset.get('asset_type', 'mesh'),

                "variant_name": asset.get('variant_name', 'Base'),
                "asset_id": asset.get('asset_id') or asset.get('version_group_id') or asset.get('uuid'),
                "source_asset_name": asset.get('source_asset_name'),

                "version": asset.get('version', 1),
                "version_label": asset.get('version_label', 'v001'),
                "version_group_id": asset.get('version_group_id') or asset.get('uuid'),
                "is_latest": bool(asset.get('is_latest', 1)),

                "representation_type": asset.get('representation_type', 'none'),

                "description": asset.get('description', ''),
                "author": asset.get('author', ''),
                "tags": asset.get('tags', []),

                "created_date": asset.get('created_date'),
                "modified_date": asset.get('modified_date'),

                "source_application": asset.get('source_application', 'Blender'),

                "metadata_version": 1,

                # Extended metadata
                "extended": {
                    "polygon_count": asset.get('polygon_count'),
                    "material_count": asset.get('material_count'),
                    "has_materials": asset.get('has_materials'),
                    "has_skeleton": asset.get('has_skeleton'),
                    "has_animations": asset.get('has_animations'),
                    "bone_count": asset.get('bone_count'),
                    "has_facial_rig": asset.get('has_facial_rig'),
                    "control_count": asset.get('control_count'),
                    "frame_start": asset.get('frame_start'),
                    "frame_end": asset.get('frame_end'),
                    "frame_rate": asset.get('frame_rate'),
                    "texture_maps": asset.get('texture_maps'),
                    "texture_resolution": asset.get('texture_resolution'),
                    "light_type": asset.get('light_type'),
                    "light_count": asset.get('light_count'),
                    "camera_type": asset.get('camera_type'),
                    "focal_length": asset.get('focal_length'),
                }
            }

            # Remove None values from extended
            metadata['extended'] = {k: v for k, v in metadata['extended'].items() if v is not None}

            # Write JSON file
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            return True

        except Exception as e:
            return False

    def migrate_all_json_metadata(self) -> Tuple[int, int, int]:
        """
        Create JSON metadata files for all existing assets that don't have them.

        Returns:
            Tuple of (created_count, skipped_count, failed_count)
        """
        created = 0
        skipped = 0
        failed = 0

        all_assets = self._db_service.get_all_assets()

        for asset in all_assets:
            try:
                result = self.create_json_for_asset(asset)
                if result:
                    created += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.debug(f"JSON creation failed for {asset.get('name', 'unknown')}: {e}")
                failed += 1

        return created, skipped, failed


# Singleton instance
_archive_service_instance: Optional[ArchiveService] = None


def get_archive_service() -> ArchiveService:
    """Get global ArchiveService singleton instance."""
    global _archive_service_instance
    if _archive_service_instance is None:
        _archive_service_instance = ArchiveService()
    return _archive_service_instance


__all__ = ['ArchiveService', 'get_archive_service']
