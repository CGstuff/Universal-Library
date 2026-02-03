"""
BackupService - Export and Import .assetlib archives

Handles:
- Exporting entire library to compressed .assetlib archive
- Importing archives with full database replacement
- Archive validation and manifest reading
- Schema evolution support (import triggers upgrade if needed)
"""

import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime

from ..config import Config


class BackupService:
    """Service for backing up and restoring asset libraries"""

    # Archive format version
    ARCHIVE_VERSION = "1.0"

    # File extensions to include in backup
    ASSET_EXTENSIONS = ('.blend', '.usd', '.usda', '.usdc', '.usdz', '.png', '.jpg', '.jpeg', '.json')

    @classmethod
    def export_library(
        cls,
        storage_path: Path,
        output_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        """
        Export entire library to .assetlib archive

        Args:
            storage_path: Path to the storage root (contains library/, _archive/, etc.)
            output_path: Path where .assetlib file should be saved
            progress_callback: Optional callback(current, total, message)

        Returns:
            True if export succeeded
        """
        try:
            # Ensure output has .assetlib extension
            if not str(output_path).endswith('.assetlib'):
                output_path = Path(str(output_path) + '.assetlib')

            # Collect files to archive
            if progress_callback:
                progress_callback(0, 0, "Scanning library...")

            files_to_archive = cls._collect_files(storage_path)
            total_files = len(files_to_archive)

            if total_files == 0:
                if progress_callback:
                    progress_callback(0, 0, "No files to export")
                return False

            # Create manifest
            manifest = cls._create_manifest(storage_path, files_to_archive)

            # Create ZIP archive
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Write manifest
                manifest_json = json.dumps(manifest, indent=2)
                zipf.writestr('manifest.json', manifest_json)

                if progress_callback:
                    progress_callback(0, total_files, "Starting export...")

                # Add all files
                for idx, (file_path, archive_name) in enumerate(files_to_archive):
                    if progress_callback:
                        progress_callback(
                            idx + 1,
                            total_files,
                            f"Exporting: {Path(archive_name).name}"
                        )

                    zipf.write(file_path, archive_name)

            if progress_callback:
                progress_callback(total_files, total_files, "Export complete!")

            return True

        except Exception as e:
            if progress_callback:
                progress_callback(0, 0, f"Error: {str(e)}")
            raise

    @classmethod
    def import_library(
        cls,
        archive_path: Path,
        storage_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Import library from .assetlib archive (Full Replace Mode)

        Args:
            archive_path: Path to .assetlib file
            storage_path: Path to the storage root
            progress_callback: Optional callback(current, total, message)

        Returns:
            Dictionary with import statistics
        """
        stats = {
            'imported': 0,
            'databases_replaced': 0,
            'errors': []
        }

        try:
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                # Read and validate manifest
                if progress_callback:
                    progress_callback(0, 0, "Validating archive...")

                manifest_data = zipf.read('manifest.json')
                manifest = json.loads(manifest_data)

                # Check version compatibility
                if not cls._is_compatible_version(manifest.get('version', '1.0')):
                    raise ValueError(f"Incompatible archive version: {manifest.get('version')}")

                # Backup existing databases before replacing
                if progress_callback:
                    progress_callback(0, 0, "Backing up existing databases...")

                cls._backup_existing_databases(storage_path)

                # Get list of files to extract
                file_list = [
                    name for name in zipf.namelist()
                    if name != 'manifest.json'
                ]
                total_files = len(file_list)

                # Clear existing content folders (Full Replace Mode)
                if progress_callback:
                    progress_callback(0, total_files, "Clearing existing library...")

                cls._clear_content_folders(storage_path)

                if progress_callback:
                    progress_callback(0, total_files, "Starting import...")

                # Extract files
                for idx, file_name in enumerate(file_list):
                    if progress_callback:
                        progress_callback(
                            idx + 1,
                            total_files,
                            f"Importing: {Path(file_name).name}"
                        )

                    try:
                        target_path = storage_path / file_name

                        # Ensure parent directory exists
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        # Extract file
                        with zipf.open(file_name) as source:
                            with open(target_path, 'wb') as target:
                                shutil.copyfileobj(source, target)

                        # Track database replacements
                        if file_name.endswith('.db'):
                            stats['databases_replaced'] += 1
                        else:
                            stats['imported'] += 1

                    except Exception as e:
                        stats['errors'].append(f"{file_name}: {str(e)}")

            if progress_callback:
                progress_callback(total_files, total_files, "Import complete! Please restart the application.")

        except Exception as e:
            stats['errors'].append(f"Archive error: {str(e)}")
            if progress_callback:
                progress_callback(0, 0, f"Error: {str(e)}")

        return stats

    @classmethod
    def _collect_files(cls, storage_path: Path) -> List[tuple]:
        """
        Collect all files to be archived

        Args:
            storage_path: Path to storage root

        Returns:
            List of (file_path, archive_name) tuples
        """
        files = []

        # Folders to include
        content_folders = [
            Config.LIBRARY_FOLDER,   # library/ - active versions
            Config.ARCHIVE_FOLDER,   # _archive/ - all versions
            Config.REVIEWS_FOLDER,   # reviews/ - review data
        ]

        # Collect asset files from content folders
        for folder_name in content_folders:
            folder = storage_path / folder_name
            if folder.exists():
                for root, dirs, filenames in os.walk(folder):
                    root_path = Path(root)

                    for filename in filenames:
                        file_path = root_path / filename

                        # Skip hidden files and system files
                        if filename.startswith('.') or filename == 'desktop.ini':
                            continue

                        # Include asset files
                        if filename.lower().endswith(cls.ASSET_EXTENSIONS):
                            rel_path = file_path.relative_to(storage_path)
                            files.append((file_path, str(rel_path).replace('\\', '/')))

        # Include databases from .meta folder
        meta_folder = storage_path / Config.META_FOLDER
        if meta_folder.exists():
            # Main database
            db_path = meta_folder / Config.DEFAULT_DB_NAME
            if db_path.exists():
                rel_path = db_path.relative_to(storage_path)
                files.append((db_path, str(rel_path).replace('\\', '/')))

            # Reviews database
            reviews_db_path = meta_folder / Config.REVIEWS_DB_NAME
            if reviews_db_path.exists():
                rel_path = reviews_db_path.relative_to(storage_path)
                files.append((reviews_db_path, str(rel_path).replace('\\', '/')))

        return files

    @classmethod
    def _create_manifest(cls, storage_path: Path, files: List[tuple]) -> Dict:
        """Create manifest with archive metadata"""
        # Calculate total size
        total_size = sum(f[0].stat().st_size for f in files if f[0].exists())
        total_size_mb = total_size / (1024 * 1024)

        # Count assets (unique .blend files in library/ and _archive/)
        asset_files = [f for f in files if str(f[1]).endswith('.blend')]
        asset_count = len([f for f in asset_files if f[1].startswith(Config.LIBRARY_FOLDER)])

        # Get database stats
        db_stats = cls._get_database_stats(storage_path)

        return {
            'version': cls.ARCHIVE_VERSION,
            'created': datetime.now().isoformat(),
            'app_version': Config.APP_VERSION,
            'schema_version': db_stats.get('schema_version', 0),
            'asset_count': db_stats.get('asset_count', asset_count),
            'folder_count': db_stats.get('folder_count', 0),
            'tag_count': db_stats.get('tag_count', 0),
            'total_size_mb': round(total_size_mb, 2),
            'file_count': len(files),
            'includes_database': True,
            'includes_reviews': any(Config.REVIEWS_FOLDER in str(f[1]) for f in files)
        }

    @classmethod
    def _get_database_stats(cls, storage_path: Path) -> Dict[str, Any]:
        """Get statistics from database for manifest"""
        import sqlite3

        stats = {}
        db_path = storage_path / Config.META_FOLDER / Config.DEFAULT_DB_NAME

        if not db_path.exists():
            return stats

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Get schema version
            cursor.execute("PRAGMA user_version")
            stats['schema_version'] = cursor.fetchone()[0]

            # Get asset count
            cursor.execute("SELECT COUNT(*) FROM assets WHERE is_latest = 1")
            stats['asset_count'] = cursor.fetchone()[0]

            # Get folder count
            cursor.execute("SELECT COUNT(*) FROM folders")
            stats['folder_count'] = cursor.fetchone()[0]

            # Get tag count
            cursor.execute("SELECT COUNT(*) FROM tags")
            stats['tag_count'] = cursor.fetchone()[0]

            conn.close()
        except Exception:
            pass

        return stats

    @classmethod
    def _backup_existing_databases(cls, storage_path: Path):
        """Backup existing databases before import"""
        meta_folder = storage_path / Config.META_FOLDER
        backup_folder = meta_folder / 'backups'
        backup_folder.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Backup main database
        db_path = meta_folder / Config.DEFAULT_DB_NAME
        if db_path.exists():
            backup_path = backup_folder / f"pre_import_{timestamp}_{Config.DEFAULT_DB_NAME}"
            shutil.copy2(db_path, backup_path)

        # Backup reviews database
        reviews_db_path = meta_folder / Config.REVIEWS_DB_NAME
        if reviews_db_path.exists():
            backup_path = backup_folder / f"pre_import_{timestamp}_{Config.REVIEWS_DB_NAME}"
            shutil.copy2(reviews_db_path, backup_path)

    @classmethod
    def _clear_content_folders(cls, storage_path: Path):
        """Clear existing content folders for full replace"""
        folders_to_clear = [
            Config.LIBRARY_FOLDER,
            Config.ARCHIVE_FOLDER,
            Config.REVIEWS_FOLDER,
        ]

        for folder_name in folders_to_clear:
            folder = storage_path / folder_name
            if folder.exists():
                shutil.rmtree(folder)

        # Also remove existing databases (they'll be replaced)
        meta_folder = storage_path / Config.META_FOLDER
        for db_name in [Config.DEFAULT_DB_NAME, Config.REVIEWS_DB_NAME]:
            db_path = meta_folder / db_name
            if db_path.exists():
                db_path.unlink()

    @classmethod
    def _is_compatible_version(cls, version: str) -> bool:
        """Check if archive version is compatible"""
        try:
            major = int(version.split('.')[0])
            return major == 1
        except (ValueError, IndexError):
            return False

    @classmethod
    def get_archive_info(cls, archive_path: Path) -> Optional[Dict]:
        """
        Get information about an archive without extracting it

        Args:
            archive_path: Path to .assetlib file

        Returns:
            Manifest dictionary with added info, or None if invalid
        """
        try:
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                manifest_data = zipf.read('manifest.json')
                manifest = json.loads(manifest_data)

                # Add computed info if not in manifest
                if 'file_count' not in manifest:
                    manifest['file_count'] = len(zipf.namelist()) - 1  # Exclude manifest

                if 'total_size_mb' not in manifest:
                    total_size = sum(info.file_size for info in zipf.infolist())
                    manifest['total_size_mb'] = round(total_size / (1024 * 1024), 2)

                return manifest
        except Exception:
            return None

    @classmethod
    def validate_archive(cls, archive_path: Path) -> tuple:
        """
        Validate an archive file

        Args:
            archive_path: Path to .assetlib file

        Returns:
            (is_valid, message) tuple
        """
        if not archive_path.exists():
            return False, "File does not exist"

        if not str(archive_path).endswith('.assetlib'):
            return False, "File is not a .assetlib archive"

        try:
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                # Check for manifest
                if 'manifest.json' not in zipf.namelist():
                    return False, "Archive is missing manifest.json"

                # Read and validate manifest
                manifest_data = zipf.read('manifest.json')
                manifest = json.loads(manifest_data)

                # Check version
                version = manifest.get('version', '0.0')
                if not cls._is_compatible_version(version):
                    return False, f"Incompatible archive version: {version}"

                # Check integrity
                bad_file = zipf.testzip()
                if bad_file:
                    return False, f"Corrupted file in archive: {bad_file}"

                return True, "Archive is valid"

        except zipfile.BadZipFile:
            return False, "File is not a valid ZIP archive"
        except json.JSONDecodeError:
            return False, "Manifest is not valid JSON"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    @classmethod
    def get_library_stats(cls, storage_path: Path) -> Dict[str, Any]:
        """
        Get current library statistics for export preview

        Args:
            storage_path: Path to storage root

        Returns:
            Dictionary with library stats
        """
        stats = {
            'asset_count': 0,
            'folder_count': 0,
            'tag_count': 0,
            'estimated_size_mb': 0.0,
            'has_reviews': False
        }

        # Get database stats
        db_stats = cls._get_database_stats(storage_path)
        stats.update(db_stats)

        # Calculate estimated size
        total_size = 0
        content_folders = [
            Config.LIBRARY_FOLDER,
            Config.ARCHIVE_FOLDER,
            Config.REVIEWS_FOLDER,
        ]

        for folder_name in content_folders:
            folder = storage_path / folder_name
            if folder.exists():
                for root, dirs, filenames in os.walk(folder):
                    for filename in filenames:
                        file_path = Path(root) / filename
                        try:
                            total_size += file_path.stat().st_size
                        except Exception:
                            pass

                if folder_name == Config.REVIEWS_FOLDER:
                    stats['has_reviews'] = True

        # Add database sizes
        meta_folder = storage_path / Config.META_FOLDER
        for db_name in [Config.DEFAULT_DB_NAME, Config.REVIEWS_DB_NAME]:
            db_path = meta_folder / db_name
            if db_path.exists():
                try:
                    total_size += db_path.stat().st_size
                except Exception:
                    pass

        stats['estimated_size_mb'] = round(total_size / (1024 * 1024), 2)

        return stats


__all__ = ['BackupService']
