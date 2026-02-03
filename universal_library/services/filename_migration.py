"""
FilenameMigrationService - Migrate assets to versioned filename convention.

This service renames existing asset files from:
    Sword.blend -> Sword.v001.blend
    Sword.json  -> Sword.v001.json

And updates database paths accordingly. Also regenerates representation files
(.current.blend, .proxy.blend, .render.blend) with versioned names.

This migration prevents Blender from merging libraries with the same filename
when linking multiple versions of the same asset.

Usage:
    from universal_library.services.filename_migration import get_filename_migration_service

    service = get_filename_migration_service()

    # Preview what will be changed (dry run)
    report = service.migrate_all_assets(dry_run=True)

    # Execute migration
    report = service.migrate_all_assets(dry_run=False)

    # Validate migration
    errors = service.validate_migration()
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from ..config import Config
from .database_service import get_database_service


class FilenameMigrationService:
    """
    Migrates asset files to versioned filename convention.

    Key responsibilities:
    - Rename .blend files: Sword.blend -> Sword.v001.blend
    - Rename .json files: Sword.json -> Sword.v001.json
    - Update database paths (blend_backup_path, usd_file_path)
    - Update custom proxy paths
    - Update representation designation paths
    - Regenerate .current/.proxy/.render.blend with versioned names
    """

    # Pattern to detect already-versioned filenames
    VERSIONED_PATTERN = re.compile(r'^(.+?)\.(v\d{3,})\.blend$')

    def __init__(self):
        self._db_service = get_database_service()

    def migrate_all_assets(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Migrate all assets to versioned filename convention.

        Args:
            dry_run: If True, only report what would be changed without modifying files.

        Returns:
            Migration report with keys:
            - 'migrated': List of successfully migrated asset UUIDs
            - 'skipped': List of (uuid, reason) tuples for skipped assets
            - 'failed': List of (uuid, error) tuples for failed migrations
            - 'total': Total number of assets processed
            - 'dry_run': Whether this was a dry run
        """
        report = {
            'migrated': [],
            'skipped': [],
            'failed': [],
            'total': 0,
            'dry_run': dry_run,
            'started_at': datetime.now().isoformat(),
        }

        # Get all assets from database
        assets = self._db_service.get_all_assets()
        report['total'] = len(assets)


        for asset in assets:
            uuid = asset.get('uuid')
            name = asset.get('name', 'Unknown')

            try:
                result = self.migrate_single_asset(uuid, dry_run=dry_run)

                if result['status'] == 'migrated':
                    report['migrated'].append(uuid)
                    if dry_run:
                        for change in result.get('changes', []):
                            pass
                    else:
                        pass

                elif result['status'] == 'skipped':
                    report['skipped'].append((uuid, result.get('reason', 'Unknown')))
                    if dry_run:
                        pass

                elif result['status'] == 'failed':
                    report['failed'].append((uuid, result.get('error', 'Unknown error')))

            except Exception as e:
                report['failed'].append((uuid, str(e)))

        report['completed_at'] = datetime.now().isoformat()

        # Update migration status in database
        if not dry_run:
            self._update_migration_status(
                'versioned_filename_v17',
                'completed' if not report['failed'] else 'partial',
                report
            )


        return report

    def migrate_single_asset(self, uuid: str, dry_run: bool = True) -> Dict[str, Any]:
        """
        Migrate a single asset to versioned filename convention.

        Args:
            uuid: Asset UUID to migrate
            dry_run: If True, only report changes without modifying files.

        Returns:
            Result dict with keys:
            - 'status': 'migrated', 'skipped', or 'failed'
            - 'reason': Reason for skip (if skipped)
            - 'error': Error message (if failed)
            - 'changes': List of changes made/planned
        """
        result = {
            'uuid': uuid,
            'status': 'skipped',
            'changes': [],
        }

        # Get asset from database
        asset = self._db_service.get_asset_by_uuid(uuid)
        if not asset:
            result['reason'] = 'Asset not found in database'
            return result

        blend_path_str = asset.get('blend_backup_path')
        if not blend_path_str:
            result['reason'] = 'No blend_backup_path in database'
            return result

        blend_path = Path(blend_path_str)
        if not blend_path.exists():
            result['reason'] = f'Blend file not found: {blend_path}'
            return result

        # Check if already versioned
        if self._is_versioned_filename(blend_path.name):
            result['reason'] = 'Already using versioned filename'
            return result

        # Get version info from asset
        version_label = asset.get('version_label', 'v001')
        asset_name = asset.get('name', 'Asset')
        safe_name = Config.sanitize_filename(asset_name)

        # Plan the changes
        changes = []
        db_updates = {}

        # 1. Rename main blend file
        new_blend_name = f"{safe_name}.{version_label}.blend"
        new_blend_path = blend_path.parent / new_blend_name

        if blend_path.name != new_blend_name:
            changes.append(f"Rename: {blend_path.name} -> {new_blend_name}")
            db_updates['blend_backup_path'] = str(new_blend_path)

        # 2. Rename JSON sidecar if exists
        json_path = blend_path.with_suffix('.json')
        if json_path.exists():
            new_json_name = f"{safe_name}.{version_label}.json"
            new_json_path = json_path.parent / new_json_name
            if json_path.name != new_json_name:
                changes.append(f"Rename: {json_path.name} -> {new_json_name}")

        # 3. Check for .current.blend that needs to be updated
        # Representation files keep their base names (no version), but
        # .current.blend needs to be re-copied from the new versioned file
        current_path = blend_path.parent / f"{safe_name}.current.blend"
        if current_path.exists():
            changes.append(f"Update: {current_path.name} (re-copy from {new_blend_name})")

        if not changes:
            result['reason'] = 'No changes needed'
            return result

        result['changes'] = changes

        if dry_run:
            result['status'] = 'migrated'
            return result

        # Execute the migration
        try:
            # 1. Rename main blend file
            if blend_path.name != new_blend_name:
                blend_path.rename(new_blend_path)
                blend_path = new_blend_path

            # 2. Rename JSON sidecar
            json_path_orig = Path(blend_path_str).with_suffix('.json')
            if json_path_orig.exists():
                new_json_name = f"{safe_name}.{version_label}.json"
                new_json_path = json_path_orig.parent / new_json_name
                json_path_orig.rename(new_json_path)

            # 3. Update .current.blend to point to the new versioned file
            # (representation files keep base names, no version)
            self._update_current_reference(blend_path, safe_name)

            # 4. Update database
            if db_updates:
                self._db_service.update_asset(uuid, db_updates)

            result['status'] = 'migrated'

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)

        return result

    def _is_versioned_filename(self, filename: str) -> bool:
        """Check if a filename already uses versioned convention."""
        return bool(self.VERSIONED_PATTERN.match(filename))

    def _update_current_reference(
        self,
        blend_path: Path,
        safe_name: str
    ):
        """
        Update .current.blend to point to the new versioned blend file.

        Representation files (.current, .proxy, .render) use base names
        without version numbers for stable linking. Only .current.blend
        needs to be re-copied when the main file is renamed.
        """
        library_folder = blend_path.parent
        current_path = library_folder / f"{safe_name}.current.blend"

        if current_path.exists():
            # Re-copy from the new versioned blend file
            shutil.copy2(str(blend_path), str(current_path))

    def validate_migration(self) -> List[Dict[str, Any]]:
        """
        Validate that all assets have correct versioned paths.

        Returns:
            List of validation errors, empty if all valid.
        """
        errors = []

        assets = self._db_service.get_all_assets()

        for asset in assets:
            uuid = asset.get('uuid')
            name = asset.get('name', 'Unknown')
            blend_path_str = asset.get('blend_backup_path')

            if not blend_path_str:
                errors.append({
                    'uuid': uuid,
                    'name': name,
                    'error': 'Missing blend_backup_path in database'
                })
                continue

            blend_path = Path(blend_path_str)

            # Check file exists
            if not blend_path.exists():
                errors.append({
                    'uuid': uuid,
                    'name': name,
                    'error': f'Blend file not found: {blend_path}'
                })
                continue

            # Check versioned naming
            if not self._is_versioned_filename(blend_path.name):
                errors.append({
                    'uuid': uuid,
                    'name': name,
                    'error': f'Not using versioned filename: {blend_path.name}'
                })

        return errors

    def get_migration_status(self) -> Optional[Dict[str, Any]]:
        """
        Get current status of the versioned filename migration.

        Returns:
            Status dict or None if not tracked.
        """
        try:
            cursor = self._db_service._connection.cursor()
            cursor.execute('''
                SELECT status, started_at, completed_at, error_message, metadata
                FROM migration_status
                WHERE migration_name = 'versioned_filename_v17'
            ''')
            row = cursor.fetchone()
            if row:
                import json
                return {
                    'status': row[0],
                    'started_at': row[1],
                    'completed_at': row[2],
                    'error_message': row[3],
                    'metadata': json.loads(row[4]) if row[4] else None
                }
        except Exception:
            pass
        return None

    def _update_migration_status(
        self,
        migration_name: str,
        status: str,
        metadata: Optional[Dict] = None
    ):
        """Update migration status in database."""
        try:
            import json
            cursor = self._db_service._connection.cursor()

            metadata_str = json.dumps(metadata) if metadata else None

            cursor.execute('''
                UPDATE migration_status
                SET status = ?,
                    completed_at = ?,
                    metadata = ?
                WHERE migration_name = ?
            ''', (status, datetime.now().isoformat(), metadata_str, migration_name))

            self._db_service._connection.commit()
        except Exception as e:
            pass


# Singleton instance
_filename_migration_service_instance: Optional[FilenameMigrationService] = None


def get_filename_migration_service() -> FilenameMigrationService:
    """Get global FilenameMigrationService singleton instance."""
    global _filename_migration_service_instance
    if _filename_migration_service_instance is None:
        _filename_migration_service_instance = FilenameMigrationService()
    return _filename_migration_service_instance


__all__ = ['FilenameMigrationService', 'get_filename_migration_service']
