"""
AssetScanner - Scan library folder for assets

Discovers .blend and USD files, extracts metadata, and adds them to the database.
Primary focus is on Blender files (.blend), with USD support for interchange.
"""

import os
import uuid
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass

from .usd_service import get_usd_service, USDMetadata
from ..services.database_service import get_database_service
from ..config import Config

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of a library scan"""
    total_found: int = 0
    newly_imported: int = 0
    updated: int = 0
    failed: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class AssetScanner:
    """
    Scanner for discovering and importing assets

    Features:
    - Recursive folder scanning
    - Blender (.blend) and USD metadata extraction
    - Database import
    - Progress callbacks
    - Duplicate detection

    Primary focus is on Blender files, with USD support for interchange.

    Usage:
        scanner = AssetScanner()
        result = scanner.scan_folder("/path/to/assets")
    """

    # Supported file extensions (Blender files are primary)
    BLEND_EXTENSIONS = {'.blend'}
    USD_EXTENSIONS = {'.usd', '.usda', '.usdc', '.usdz'}  # For interchange
    ALL_EXTENSIONS = BLEND_EXTENSIONS | USD_EXTENSIONS

    def __init__(self):
        self._usd_service = get_usd_service()
        self._db_service = get_database_service()
        self._progress_callback: Optional[Callable[[int, int, str], None]] = None

    def set_progress_callback(self, callback: Callable[[int, int, str], None]):
        """
        Set progress callback

        Args:
            callback: Function(current, total, message)
        """
        self._progress_callback = callback

    def _report_progress(self, current: int, total: int, message: str):
        """Report progress via callback"""
        if self._progress_callback:
            self._progress_callback(current, total, message)

    def scan_folder(
        self,
        folder_path: str,
        recursive: bool = True,
        update_existing: bool = False,
        scan_blend: bool = True,
        scan_usd: bool = False
    ) -> ScanResult:
        """
        Scan folder for assets (.blend and optionally USD)

        Args:
            folder_path: Path to scan
            recursive: Scan subdirectories
            update_existing: Update metadata for existing assets
            scan_blend: Scan for .blend files (default: True)
            scan_usd: Scan for USD files (default: False)

        Returns:
            ScanResult with statistics
        """
        result = ScanResult()
        folder = Path(folder_path)

        if not folder.exists():
            result.errors.append(f"Folder not found: {folder_path}")
            return result

        # Determine which extensions to scan for
        extensions = set()
        if scan_blend:
            extensions |= self.BLEND_EXTENSIONS
        if scan_usd:
            extensions |= self.USD_EXTENSIONS

        # Find all asset files
        asset_files = self._find_asset_files(folder, recursive, extensions)
        result.total_found = len(asset_files)

        file_types = []
        if scan_blend:
            file_types.append(".blend")
        if scan_usd:
            file_types.append("USD")
        logger.info(f"Found {len(asset_files)} {'/'.join(file_types)} files in {folder_path}")

        # Process each file
        for i, asset_path in enumerate(asset_files):
            self._report_progress(i + 1, len(asset_files), f"Processing: {asset_path.name}")

            try:
                # Route to appropriate processor based on file type
                if asset_path.suffix.lower() in self.BLEND_EXTENSIONS:
                    imported = self._process_blend_file(asset_path, update_existing)
                else:
                    imported = self._process_usd_file(asset_path, update_existing)

                if imported == "new":
                    result.newly_imported += 1
                elif imported == "updated":
                    result.updated += 1
                # "skipped" doesn't count
            except Exception as e:
                result.failed += 1
                result.errors.append(f"{asset_path.name}: {str(e)}")
                logger.error(f"Error processing {asset_path}: {e}")

        logger.info(f"Scan complete: {result.newly_imported} new, {result.updated} updated, {result.failed} failed")
        return result

    def _find_asset_files(self, folder: Path, recursive: bool, extensions: set) -> List[Path]:
        """Find all asset files with given extensions in folder"""
        asset_files = []

        if recursive:
            for root, dirs, files in os.walk(folder):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]

                for filename in files:
                    if Path(filename).suffix.lower() in extensions:
                        asset_files.append(Path(root) / filename)
        else:
            for item in folder.iterdir():
                if item.is_file() and item.suffix.lower() in extensions:
                    asset_files.append(item)

        return sorted(asset_files)

    def _find_usd_files(self, folder: Path, recursive: bool) -> List[Path]:
        """Find all USD files in folder (legacy method)"""
        return self._find_asset_files(folder, recursive, self.USD_EXTENSIONS)

    def _process_usd_file(self, usd_path: Path, update_existing: bool) -> str:
        """
        Process a single USD file

        Args:
            usd_path: Path to USD file
            update_existing: Update if already exists

        Returns:
            "new", "updated", or "skipped"
        """
        # Generate UUID from file path (deterministic)
        file_uuid = self._generate_uuid(usd_path)

        # Check if already exists
        existing = self._db_service.get_asset_by_uuid(file_uuid)
        if existing and not update_existing:
            return "skipped"

        # Analyze USD file
        metadata = self._usd_service.analyze_usd_file(str(usd_path))
        if not metadata:
            raise ValueError("Failed to analyze USD file")

        # Determine asset type
        asset_type = self._detect_asset_type(metadata)

        # Build asset data
        asset_data = {
            'uuid': file_uuid,
            'name': usd_path.stem,
            'description': '',
            'folder_id': self._db_service.get_root_folder_id(),
            'asset_type': asset_type,
            'usd_file_path': str(usd_path),
            'blend_backup_path': None,
            'thumbnail_path': None,
            'preview_path': None,
            'file_size_mb': metadata.file_size_mb,
            'has_materials': 1 if metadata.has_materials else 0,
            'has_skeleton': 1 if metadata.has_skeleton else 0,
            'has_animations': 1 if metadata.has_animations else 0,
            'polygon_count': metadata.polygon_count,
            'material_count': metadata.material_count,
            'tags': [],
            'author': '',
            'source_application': 'Unknown',
        }

        if existing:
            # Update existing
            self._db_service.update_asset(file_uuid, asset_data)
            return "updated"
        else:
            # Add new
            self._db_service.add_asset(asset_data)
            return "new"

    def _process_blend_file(self, blend_path: Path, update_existing: bool) -> str:
        """
        Process a single .blend file

        Args:
            blend_path: Path to .blend file
            update_existing: Update if already exists

        Returns:
            "new", "updated", or "skipped"
        """
        # Look for JSON sidecar metadata file first
        json_path = blend_path.with_suffix('.json')
        json_metadata = self._read_json_metadata(json_path)

        # Use UUID from JSON if available, otherwise generate deterministic one
        if json_metadata and json_metadata.get('uuid'):
            file_uuid = json_metadata['uuid']
        else:
            file_uuid = self._generate_uuid(blend_path)

        # Check if already exists
        existing = self._db_service.get_asset_by_uuid(file_uuid)
        if existing and not update_existing:
            return "skipped"

        # Get file info (can't introspect .blend without Blender)
        file_size_mb = blend_path.stat().st_size / (1024 * 1024)

        # Build asset data - use JSON metadata if available, otherwise defaults
        if json_metadata:
            # Rich metadata from JSON sidecar
            extended = json_metadata.get('extended', {})
            asset_data = {
                'uuid': file_uuid,
                'name': json_metadata.get('name', blend_path.stem),
                'description': json_metadata.get('description', ''),
                'folder_id': self._db_service.get_root_folder_id(),
                'asset_type': json_metadata.get('asset_type', 'mesh'),
                'usd_file_path': None,
                'blend_backup_path': str(blend_path),
                'thumbnail_path': self._find_thumbnail(blend_path),
                'preview_path': None,
                'file_size_mb': file_size_mb,
                'has_materials': extended.get('has_materials', 0),
                'has_skeleton': extended.get('has_skeleton', 0),
                'has_animations': extended.get('has_animations', 0),
                'polygon_count': extended.get('polygon_count', 0),
                'material_count': extended.get('material_count', 0),
                'tags': json_metadata.get('tags', []),
                'author': json_metadata.get('author', ''),
                'source_application': json_metadata.get('source_application', 'Blender'),
                # Versioning fields
                'version': json_metadata.get('version', 1),
                'version_label': json_metadata.get('version_label', 'v001'),
                'version_group_id': json_metadata.get('version_group_id', file_uuid),
                'is_latest': 1 if json_metadata.get('is_latest', True) else 0,
                # Variant system fields
                'asset_id': json_metadata.get('asset_id', file_uuid),
                'variant_name': json_metadata.get('variant_name', 'Base'),
                # Pipeline fields
                'representation_type': json_metadata.get('representation_type', 'none'),
                # Extended metadata
                'bone_count': extended.get('bone_count'),
                'has_facial_rig': extended.get('has_facial_rig', 0),
                'control_count': extended.get('control_count'),
                'frame_start': extended.get('frame_start'),
                'frame_end': extended.get('frame_end'),
                'frame_rate': extended.get('frame_rate'),
                'texture_maps': json.dumps(extended.get('texture_maps', [])) if extended.get('texture_maps') else None,
                'texture_resolution': extended.get('texture_resolution'),
            }
        else:
            # Basic metadata without JSON
            asset_data = {
                'uuid': file_uuid,
                'name': blend_path.stem,
                'description': '',
                'folder_id': self._db_service.get_root_folder_id(),
                'asset_type': 'mesh',  # Default, can be updated later
                'usd_file_path': None,
                'blend_backup_path': str(blend_path),  # .blend is primary
                'thumbnail_path': self._find_thumbnail(blend_path),
                'preview_path': None,
                'file_size_mb': file_size_mb,
                'has_materials': 0,  # Unknown without Blender
                'has_skeleton': 0,
                'has_animations': 0,
                'polygon_count': 0,
                'material_count': 0,
                'tags': [],
                'author': '',
                'source_application': 'Blender',
            }

        if existing:
            # Update existing
            self._db_service.update_asset(file_uuid, asset_data)
            return "updated"
        else:
            # Add new
            self._db_service.add_asset(asset_data)
            return "new"

    def _read_json_metadata(self, json_path: Path) -> Optional[Dict[str, Any]]:
        """
        Read JSON sidecar metadata file.

        Args:
            json_path: Path to JSON file

        Returns:
            Metadata dictionary or None if not found/invalid
        """
        try:
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Error reading JSON metadata {json_path}: {e}")
        return None

    def _find_thumbnail(self, blend_path: Path) -> Optional[str]:
        """
        Find thumbnail file for a .blend file.

        Checks for thumbnail.png in the same directory.

        Args:
            blend_path: Path to .blend file

        Returns:
            Thumbnail path string or None
        """
        thumbnail_path = blend_path.parent / "thumbnail.png"
        if thumbnail_path.exists():
            return str(thumbnail_path)
        return None

    def _generate_uuid(self, file_path: Path) -> str:
        """
        Generate deterministic UUID from file path

        Uses file path relative to library root for consistency.
        """
        # Use absolute path for uniqueness
        path_str = str(file_path.resolve())
        return str(uuid.uuid5(uuid.NAMESPACE_URL, path_str))

    def _detect_asset_type(self, metadata: USDMetadata) -> str:
        """
        Detect asset type from USD metadata

        Args:
            metadata: USD metadata

        Returns:
            Asset type string: "model", "material", "rig", etc.
        """
        # Check for rig (has skeleton)
        if metadata.has_skeleton:
            return "rig"

        # Check for material-only (no geometry)
        if metadata.has_materials and not metadata.has_geometry:
            return "material"

        # Default to model
        return "mesh"

    def scan_single_file(self, file_path: str) -> Optional[str]:
        """
        Scan and import a single USD file

        Args:
            file_path: Path to USD file

        Returns:
            Asset UUID if successful, None otherwise
        """
        path = Path(file_path)

        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        if path.suffix.lower() not in self.USD_EXTENSIONS:
            logger.error(f"Not a USD file: {file_path}")
            return None

        try:
            result = self._process_usd_file(path, update_existing=True)
            file_uuid = self._generate_uuid(path)
            logger.info(f"Imported {path.name} ({result}): {file_uuid}")
            return file_uuid
        except Exception as e:
            logger.error(f"Failed to import {file_path}: {e}")
            return None

    def rescan_asset(self, asset_uuid: str) -> bool:
        """
        Rescan an existing asset to update metadata

        Args:
            asset_uuid: Asset UUID to rescan

        Returns:
            True if successful
        """
        asset = self._db_service.get_asset_by_uuid(asset_uuid)
        if not asset:
            logger.error(f"Asset not found: {asset_uuid}")
            return False

        usd_path = asset.get('usd_file_path')
        if not usd_path or not Path(usd_path).exists():
            logger.error(f"USD file not found: {usd_path}")
            return False

        try:
            self._process_usd_file(Path(usd_path), update_existing=True)
            return True
        except Exception as e:
            logger.error(f"Failed to rescan asset: {e}")
            return False


# Singleton
_scanner_instance: Optional[AssetScanner] = None


def get_asset_scanner() -> AssetScanner:
    """Get global AssetScanner singleton"""
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = AssetScanner()
    return _scanner_instance


__all__ = ['AssetScanner', 'ScanResult', 'get_asset_scanner']
