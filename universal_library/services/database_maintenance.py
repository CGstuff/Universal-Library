"""
DatabaseMaintenance - Database maintenance and backup operations.

Handles:
- Database statistics
- Integrity checks
- Optimization (VACUUM)
- Backup creation and management
- Schema upgrades
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple

from .schema_manager import SchemaManager


# Feature descriptions for each schema version (for UI display)
VERSION_FEATURES: Dict[int, List[str]] = {
    2: ["Folder descriptions and icons", "Preview paths", "Lock support"],
    3: ["Lifecycle status (WIP, Review, Approved)", "Custom ordering"],
    4: ["Version history", "Version labels", "Parent version tracking"],
    5: ["Cold storage support", "Representations (Model, Lookdev, Rig)", "Publish/lock workflow"],
    6: ["Extended metadata by asset type", "Material/light/camera fields"],
    7: ["Collection support", "Mesh/camera/armature counts"],
    8: ["Variant system", "Provenance tracking", "Variant sets"],
    9: ["Version notes/changelog per version"],
}


class DatabaseMaintenance:
    """
    Manages database maintenance operations.

    Provides statistics, integrity checks, optimization,
    and backup functionality.
    """

    def __init__(self, connection: sqlite3.Connection, db_path: Path):
        """
        Initialize with database connection and path.

        Args:
            connection: SQLite connection to library database
            db_path: Path to the database file
        """
        self._connection = connection
        self._db_path = db_path

    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics for status display.

        Returns:
            Dict containing schema version, record counts, file size, pending features, etc.
        """
        cursor = self._connection.cursor()

        # Get current schema version
        cursor.execute('SELECT MAX(version) FROM schema_version')
        result = cursor.fetchone()
        current_version = result[0] if result and result[0] else 0

        # Get record counts
        cursor.execute('SELECT COUNT(*) FROM assets')
        asset_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM folders')
        folder_count = cursor.fetchone()[0]

        # Get cold storage count
        cursor.execute('SELECT COUNT(*) FROM assets WHERE is_cold = 1')
        cold_count = cursor.fetchone()[0]

        # Get database file size
        db_size = 0
        if self._db_path.exists():
            db_size = self._db_path.stat().st_size

        # Determine pending features
        pending_features = []
        for version in range(current_version + 1, SchemaManager.SCHEMA_VERSION + 1):
            if version in VERSION_FEATURES:
                pending_features.extend(VERSION_FEATURES[version])

        return {
            'schema_version': current_version,
            'latest_version': SchemaManager.SCHEMA_VERSION,
            'needs_upgrade': current_version < SchemaManager.SCHEMA_VERSION,
            'asset_count': asset_count,
            'folder_count': folder_count,
            'cold_count': cold_count,
            'db_size_bytes': db_size,
            'db_size_mb': round(db_size / (1024 * 1024), 2),
            'pending_features': pending_features,
        }

    def run_integrity_check(self) -> Tuple[bool, str]:
        """
        Run database integrity check.

        Returns:
            Tuple of (is_ok, message)
        """
        cursor = self._connection.cursor()

        results = []

        # Run integrity check
        cursor.execute('PRAGMA integrity_check')
        integrity_result = cursor.fetchall()
        integrity_ok = len(integrity_result) == 1 and integrity_result[0][0] == 'ok'

        if integrity_ok:
            results.append("Integrity check: OK")
        else:
            results.append(f"Integrity check: FAILED - {integrity_result}")

        # Run foreign key check
        cursor.execute('PRAGMA foreign_key_check')
        fk_results = cursor.fetchall()
        fk_ok = len(fk_results) == 0

        if fk_ok:
            results.append("Foreign key check: OK")
        else:
            results.append(f"Foreign key check: FAILED - {len(fk_results)} violations")
            for row in fk_results[:5]:  # Show first 5 violations
                results.append(f"  - Table: {row[0]}, rowid: {row[1]}")

        is_ok = integrity_ok and fk_ok
        message = "\n".join(results)

        return is_ok, message

    def optimize_database(self) -> Tuple[int, int]:
        """
        Optimize database by running VACUUM.

        Returns:
            Tuple of (size_before, size_after) in bytes
        """
        # Get size before
        size_before = self._db_path.stat().st_size if self._db_path.exists() else 0

        # Checkpoint WAL first
        cursor = self._connection.cursor()
        cursor.execute('PRAGMA wal_checkpoint(TRUNCATE)')

        # Run VACUUM
        self._connection.execute('VACUUM')
        self._connection.commit()

        # Get size after
        size_after = self._db_path.stat().st_size if self._db_path.exists() else 0

        return size_before, size_after

    def get_current_schema_version(self) -> int:
        """Get current schema version from database."""
        cursor = self._connection.cursor()
        cursor.execute('SELECT MAX(version) FROM schema_version')
        result = cursor.fetchone()
        return result[0] if result and result[0] else 0

    def create_backup(self) -> Path:
        """
        Create a backup of the database.

        Returns:
            Path to the backup file
        """
        # Checkpoint WAL first for consistency
        cursor = self._connection.cursor()
        cursor.execute('PRAGMA wal_checkpoint(TRUNCATE)')

        # Create backups directory
        backup_dir = self._db_path.parent / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"database_backup_{timestamp}.db"

        # Use SQLite backup API for consistency
        source = sqlite3.connect(str(self._db_path))
        dest = sqlite3.connect(str(backup_path))
        source.backup(dest)
        source.close()
        dest.close()

        return backup_path

    def get_backups(self) -> List[Dict[str, Any]]:
        """
        Get list of existing backups.

        Returns:
            List of backup info dicts with 'path', 'filename', 'size_mb', 'date'
        """
        backup_dir = self._db_path.parent / 'backups'
        if not backup_dir.exists():
            return []

        backups = []
        for backup_file in sorted(backup_dir.glob('database_backup_*.db'), reverse=True):
            stat = backup_file.stat()
            backups.append({
                'path': str(backup_file),
                'filename': backup_file.name,
                'size_mb': stat.st_size / (1024 * 1024),
                'date': datetime.fromtimestamp(stat.st_mtime),
            })

        return backups

    def delete_backup(self, backup_path: Path) -> bool:
        """
        Delete a backup file.

        Args:
            backup_path: Path to the backup file

        Returns:
            True if deleted successfully
        """
        try:
            backup_path = Path(backup_path)
            if backup_path.exists() and backup_path.suffix == '.db':
                backup_path.unlink()
                return True
        except Exception:
            pass
        return False

    def run_schema_upgrade(self, schema_manager: SchemaManager) -> Tuple[bool, str]:
        """
        Run schema upgrade (migrations).

        Creates a backup first, then runs migrations.

        Args:
            schema_manager: SchemaManager instance for running migrations

        Returns:
            Tuple of (success, message)
        """
        try:
            # Get current version before upgrade
            before_version = self.get_current_schema_version()

            # Create backup before migration
            backup_path = self.create_backup()

            # Re-run migrations
            cursor = self._connection.cursor()
            schema_manager._run_migrations(cursor, before_version)

            # Update version
            cursor.execute(
                'INSERT OR REPLACE INTO schema_version (version) VALUES (?)',
                (SchemaManager.SCHEMA_VERSION,)
            )
            self._connection.commit()

            # Get version after upgrade
            after_version = self.get_current_schema_version()

            if after_version > before_version:
                return True, f"Upgraded from v{before_version} to v{after_version}. Backup created at: {backup_path}"
            else:
                return True, f"Already at latest version (v{after_version}). Backup created at: {backup_path}"

        except Exception as e:
            return False, f"Upgrade failed: {str(e)}"


__all__ = ['DatabaseMaintenance', 'VERSION_FEATURES']
