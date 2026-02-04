"""
Library Connection - Connect to Universal Library database

Provides read/write access to the asset library from Blender.
"""

import os
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from .constants import (
    META_FOLDER,
    LIBRARY_FOLDER,
    ARCHIVE_FOLDER,
    REVIEWS_FOLDER,
    CACHE_FOLDER,
    DATABASE_NAME,
    get_type_folder,
)
from .appdata import read_library_path as _read_appdata_library_path


class LibraryConnection:
    """
    Connection to the Universal Library

    Handles database access and file operations for the asset library.

    Usage:
        conn = LibraryConnection("/path/to/library")
        assets = conn.get_all_assets()
        conn.add_asset(asset_data)
    """

    def __init__(self, library_path: str = None):
        """
        Initialize library connection

        Args:
            library_path: Path to library folder. If None, uses default.
        """
        self._library_path = Path(library_path) if library_path else self._get_default_path()
        # Path structure uses constants for consistency
        self._db_path = self._library_path / META_FOLDER / DATABASE_NAME
        self._assets_path = self._library_path / LIBRARY_FOLDER
        self._connection: Optional[sqlite3.Connection] = None

    def _get_default_path(self) -> Path:
        """Get default library path from shared AppData config"""
        # 1. Check environment variable
        env_path = os.environ.get("UAL_LIBRARY_PATH")
        if env_path and Path(env_path).exists():
            return Path(env_path)

        # 2. Try reading from shared AppData config
        appdata_path = _read_appdata_library_path()
        if appdata_path:
            return Path(appdata_path)

        # 3. Default to user documents
        if os.name == 'nt':
            base = Path(os.environ.get("USERPROFILE", "")) / "Documents"
        else:
            base = Path.home() / "Documents"

        return base / "UniversalAssetLibrary"

    @property
    def library_path(self) -> Path:
        return self._library_path

    @property
    def assets_path(self) -> Path:
        return self._assets_path

    def ensure_directories(self):
        """Ensure library directories exist"""
        self._library_path.mkdir(parents=True, exist_ok=True)
        self._assets_path.mkdir(parents=True, exist_ok=True)
        (self._library_path / META_FOLDER).mkdir(parents=True, exist_ok=True)
        (self._library_path / ARCHIVE_FOLDER).mkdir(parents=True, exist_ok=True)
        (self._library_path / REVIEWS_FOLDER).mkdir(parents=True, exist_ok=True)
        (self._library_path / CACHE_FOLDER).mkdir(parents=True, exist_ok=True)

    def connect(self) -> bool:
        """Connect to database"""
        try:
            self.ensure_directories()

            self._connection = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")

            # Create tables if needed (schema matches desktop app)
            self._create_tables()

            return True
        except Exception:
            return False

    def disconnect(self):
        """Disconnect from database"""
        if self._connection:
            self._connection.close()
            self._connection = None

    def _create_tables(self):
        """
        Create database tables if they don't exist.

        IMPORTANT: Schema must match desktop app (schema_manager.py) exactly.
        Key differences from old schema:
        - assets.id INTEGER PRIMARY KEY (not uuid as primary key)
        - assets.uuid TEXT UNIQUE NOT NULL
        - created_date/modified_date (not created_at/updated_at)
        - status column included
        """
        cursor = self._connection.cursor()

        # Folders table (matches desktop app)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER,
                path TEXT,
                description TEXT,
                icon_name TEXT,
                icon_color TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES folders(id)
            )
        """)

        # Assets table (matches desktop app schema exactly)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                folder_id INTEGER DEFAULT 1,
                asset_type TEXT DEFAULT 'mesh',
                representation_type TEXT DEFAULT 'none',
                usd_file_path TEXT,
                blend_backup_path TEXT,
                thumbnail_path TEXT,
                preview_path TEXT,
                file_size_mb REAL DEFAULT 0,
                has_materials INTEGER DEFAULT 0,
                has_skeleton INTEGER DEFAULT 0,
                has_animations INTEGER DEFAULT 0,
                polygon_count INTEGER DEFAULT 0,
                material_count INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                author TEXT DEFAULT '',
                source_application TEXT DEFAULT 'Blender',
                is_favorite INTEGER DEFAULT 0,
                last_viewed_date TIMESTAMP,
                custom_order INTEGER,
                is_locked INTEGER DEFAULT 0,
                status TEXT DEFAULT 'wip',
                -- Versioning fields
                version INTEGER DEFAULT 1,
                version_label TEXT DEFAULT 'v001',
                version_group_id TEXT,
                is_latest INTEGER DEFAULT 1,
                parent_version_uuid TEXT,
                -- Variant system fields
                asset_id TEXT,
                variant_name TEXT DEFAULT 'Base',
                variant_source_uuid TEXT,
                -- Cold storage fields
                is_cold INTEGER DEFAULT 0,
                cold_storage_path TEXT,
                is_immutable INTEGER DEFAULT 0,
                -- Timestamps (matching desktop app naming)
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                -- Extended metadata
                bone_count INTEGER,
                has_facial_rig INTEGER DEFAULT 0,
                control_count INTEGER,
                frame_start INTEGER,
                frame_end INTEGER,
                frame_rate REAL,
                is_loop INTEGER DEFAULT 0,
                texture_maps TEXT,
                texture_resolution TEXT,
                light_type TEXT,
                light_count INTEGER,
                camera_type TEXT,
                focal_length REAL,
                FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
            )
        """)

        # Create indexes (matching desktop app)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_uuid ON assets(uuid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_folder ON assets(folder_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_name ON assets(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_favorite ON assets(is_favorite)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id)')

        # Asset folders junction table (for multi-folder membership)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asset_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_uuid TEXT NOT NULL,
                folder_id INTEGER NOT NULL,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE,
                UNIQUE(asset_uuid, folder_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_folders_uuid ON asset_folders(asset_uuid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_folders_folder ON asset_folders(folder_id)')

        # Insert root folder if not exists
        cursor.execute("SELECT COUNT(*) FROM folders WHERE id = 1")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO folders (id, name, parent_id, path) VALUES (1, 'Library', NULL, '')"
            )

        self._connection.commit()

    def get_all_assets(self, folder_id: int = None) -> List[Dict[str, Any]]:
        """Get all assets, optionally filtered by folder"""
        if not self._connection:
            self.connect()

        cursor = self._connection.cursor()

        if folder_id:
            cursor.execute("SELECT * FROM assets WHERE folder_id = ? ORDER BY name", (folder_id,))
        else:
            cursor.execute("SELECT * FROM assets ORDER BY name")

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_asset_by_uuid(self, asset_uuid: str) -> Optional[Dict[str, Any]]:
        """Get single asset by UUID"""
        if not self._connection:
            self.connect()

        cursor = self._connection.cursor()
        cursor.execute("SELECT * FROM assets WHERE uuid = ?", (asset_uuid,))
        row = cursor.fetchone()

        return dict(row) if row else None

    def get_version_history(self, version_group_id: str) -> List[Dict[str, Any]]:
        """
        Get all versions of an asset by version_group_id.

        Args:
            version_group_id: UUID grouping all versions of same asset

        Returns:
            List of version records sorted by version number descending
        """
        if not self._connection:
            self.connect()

        cursor = self._connection.cursor()
        cursor.execute("""
            SELECT uuid, name, version, version_label, thumbnail_path,
                   polygon_count, material_count, representation_type,
                   is_latest, is_cold, created_date, status, description,
                   has_skeleton, has_animations, variant_name, asset_id
            FROM assets
            WHERE version_group_id = ?
            ORDER BY version DESC
        """, (version_group_id,))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def add_asset(self, asset_data: Dict[str, Any]) -> str:
        """
        Add new asset to library

        Args:
            asset_data: Asset data dictionary

        Returns:
            UUID of created asset
        """
        if not self._connection:
            self.connect()

        # Generate UUID if not provided
        if 'uuid' not in asset_data:
            asset_data['uuid'] = str(uuid.uuid4())

        # Handle tags as JSON
        if 'tags' in asset_data and isinstance(asset_data['tags'], list):
            asset_data['tags'] = json.dumps(asset_data['tags'])

        cursor = self._connection.cursor()

        # Filter out keys that don't exist as columns in the table
        cursor.execute("PRAGMA table_info(assets)")
        table_columns = {col[1] for col in cursor.fetchall()}
        filtered_data = {k: v for k, v in asset_data.items() if k in table_columns}

        columns = ', '.join(filtered_data.keys())
        placeholders = ', '.join(['?' for _ in filtered_data])

        cursor.execute(
            f"INSERT INTO assets ({columns}) VALUES ({placeholders})",
            list(filtered_data.values())
        )

        self._connection.commit()
        return asset_data['uuid']

    def asset_name_exists(self, name: str, folder_id: Optional[int] = None,
                          asset_type: Optional[str] = None) -> bool:
        """
        Check if an asset with the given name already exists (with valid files).

        Names are unique per asset_type — a mesh named "Sword" and a material
        named "Sword" can coexist, but two meshes named "Sword" cannot.

        Args:
            name: Asset name to check
            folder_id: Optional folder to scope the check
            asset_type: Optional asset type to scope the check (mesh, collection, etc.)

        Returns:
            True if an asset with this name exists AND has valid files
        """
        if not self._connection:
            self.connect()

        cursor = self._connection.cursor()

        # Get asset with blend_backup_path to verify files exist
        query = "SELECT blend_backup_path FROM assets WHERE name = ?"
        params = [name]

        if asset_type is not None:
            query += " AND asset_type = ?"
            params.append(asset_type)

        if folder_id is not None:
            query += " AND folder_id = ?"
            params.append(folder_id)

        query += " LIMIT 1"
        cursor.execute(query, params)

        result = cursor.fetchone()
        if not result:
            return False

        # Check if the file actually exists on disk
        blend_path = result[0]
        if blend_path and Path(blend_path).exists():
            return True

        # Database record exists but file is missing - treat as not existing
        # This handles orphaned database records from deleted storage
        return False

    def update_asset(self, asset_uuid: str, updates: Dict[str, Any]) -> bool:
        """Update existing asset"""
        if not self._connection:
            self.connect()

        # Handle tags as JSON
        if 'tags' in updates and isinstance(updates['tags'], list):
            updates['tags'] = json.dumps(updates['tags'])

        cursor = self._connection.cursor()

        # Check if modified_date column exists before adding it
        cursor.execute("PRAGMA table_info(assets)")
        columns = {col[1] for col in cursor.fetchall()}
        if 'modified_date' in columns:
            updates['modified_date'] = datetime.now().isoformat()

        set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [asset_uuid]

        cursor.execute(
            f"UPDATE assets SET {set_clause} WHERE uuid = ?",
            values
        )

        self._connection.commit()
        return cursor.rowcount > 0

    def _ensure_asset_folders_table(self):
        """
        Create asset_folders junction table if it doesn't exist.
        
        Forward-compatible: the Blender addon creates the table if the
        desktop app hasn't run schema migration yet.
        """
        if not self._connection:
            self.connect()
        
        cursor = self._connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asset_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_uuid TEXT NOT NULL,
                folder_id INTEGER NOT NULL,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE,
                UNIQUE(asset_uuid, folder_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_folders_uuid ON asset_folders(asset_uuid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_folders_folder ON asset_folders(folder_id)')
        self._connection.commit()

    def copy_folders_to_asset(self, source_uuid: str, target_uuid: str) -> bool:
        """
        Copy folder memberships from one asset to another.
        
        Used when creating new versions to inherit folder organization.
        
        Args:
            source_uuid: Source asset UUID (e.g., v001)
            target_uuid: Target asset UUID (e.g., v002)
            
        Returns:
            True if successful
        """
        if not self._connection:
            self.connect()
        
        self._ensure_asset_folders_table()
        
        try:
            cursor = self._connection.cursor()
            
            # Get folders from source asset
            cursor.execute('''
                SELECT folder_id FROM asset_folders WHERE asset_uuid = ?
            ''', (source_uuid,))
            folder_ids = [row[0] for row in cursor.fetchall()]
            
            # Add target to same folders
            for folder_id in folder_ids:
                cursor.execute('''
                    INSERT OR IGNORE INTO asset_folders (asset_uuid, folder_id, created_date)
                    VALUES (?, ?, ?)
                ''', (target_uuid, folder_id, datetime.now()))
            
            self._connection.commit()
            return True
        except Exception as e:
            return False

    def delete_asset(self, asset_uuid: str) -> bool:
        """Delete asset from library"""
        if not self._connection:
            self.connect()

        # Get asset to find files to delete
        asset = self.get_asset_by_uuid(asset_uuid)
        if not asset:
            return False

        # Delete files
        for path_key in ['usd_file_path', 'blend_backup_path', 'thumbnail_path', 'preview_path']:
            file_path = asset.get(path_key)
            if file_path and Path(file_path).exists():
                try:
                    Path(file_path).unlink()
                except Exception:
                    pass

        # Delete from database
        cursor = self._connection.cursor()
        cursor.execute("DELETE FROM assets WHERE uuid = ?", (asset_uuid,))
        self._connection.commit()

        return cursor.rowcount > 0

    def get_asset_folder(self, asset_uuid: str) -> Path:
        """Get folder path for asset files (legacy method)"""
        folder = self._assets_path / asset_uuid
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def get_library_folder_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str = 'Base',
        asset_type: str = 'other'
    ) -> Path:
        """
        Get folder path for asset in library structure.

        Structure: library/{type}/{name}/{variant}/

        Args:
            asset_id: Asset family UUID (shared by all variants)
            asset_name: Human-readable asset name
            variant_name: Variant name (default 'Base')
            asset_type: Asset type for folder organization (mesh, material, etc.)

        Returns:
            Path to library folder for this asset variant
        """
        type_folder = self._get_type_folder(asset_type)
        family_folder = self._get_family_folder_name(asset_id, asset_name)

        # Create path: library/{type}/{family}/{variant}/
        folder = self._library_path / LIBRARY_FOLDER / type_folder / family_folder / variant_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def get_archive_folder_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        asset_type: str = 'other'
    ) -> Path:
        """
        Get folder path for archived version.

        Structure: _archive/{type}/{name}/{variant}/{version}/

        Args:
            asset_id: Asset family UUID
            asset_name: Human-readable asset name
            variant_name: Variant name
            version_label: Version label (e.g., 'v001')
            asset_type: Asset type for folder organization (mesh, material, etc.)

        Returns:
            Path to archive folder for this version
        """
        type_folder = self._get_type_folder(asset_type)
        family_folder = self._get_family_folder_name(asset_id, asset_name)

        folder = self._library_path / ARCHIVE_FOLDER / type_folder / family_folder / variant_name / version_label
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize asset name for use in folder/file names"""
        import re
        # Replace invalid characters with underscore
        safe = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Remove leading/trailing spaces and dots
        safe = safe.strip(' .')
        # Collapse multiple underscores
        safe = re.sub(r'_+', '_', safe)
        return safe or 'unnamed'

    def _get_family_folder_name(self, asset_id: str, asset_name: str) -> str:
        """
        Generate family folder name - human readable, no UUID.

        Industry standard: UUIDs live in database, folders are human-readable.
        """
        return self._sanitize_filename(asset_name)

    def _get_type_folder(self, asset_type: str) -> str:
        """
        Map asset type to folder name.

        Args:
            asset_type: Asset type string (mesh, material, rig, etc.)

        Returns:
            Folder name string. Returns 'other' for unknown types.
        """
        # Use centralized get_type_folder from constants module
        return get_type_folder(asset_type)

    def get_custom_proxy_folder_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        proxy_label: str,
        asset_type: str = 'mesh'
    ) -> Path:
        """
        Get folder path for a custom proxy version.

        DEPRECATED: Custom proxies (p001, p002) legacy format.
        Use update_proxy operator instead for new proxy saves.

        Structure: library/{type}/{name}/{variant}/_proxy/{proxy_label}/

        Args:
            asset_id: Asset family UUID
            asset_name: Human-readable asset name
            variant_name: Variant name
            proxy_label: Proxy label (e.g., 'p001')
            asset_type: Asset type

        Returns:
            Path to custom proxy folder
        """
        type_folder = self._get_type_folder(asset_type)
        family_folder = self._get_family_folder_name(asset_id, asset_name)

        folder = (
            self._library_path / LIBRARY_FOLDER / type_folder
            / family_folder / variant_name / '_proxy' / proxy_label
        )
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _ensure_custom_proxies_table(self):
        """
        Create custom_proxies table if it doesn't exist.

        Forward-compatible: the Blender addon creates the table if the
        desktop app hasn't run schema migration yet.
        """
        if not self._connection:
            self.connect()

        cursor = self._connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE NOT NULL,
                version_group_id TEXT NOT NULL,
                variant_name TEXT NOT NULL DEFAULT 'Base',
                asset_id TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                asset_type TEXT NOT NULL DEFAULT 'mesh',
                proxy_version INTEGER NOT NULL DEFAULT 1,
                proxy_label TEXT NOT NULL DEFAULT 'p001',
                blend_path TEXT,
                thumbnail_path TEXT,
                polygon_count INTEGER,
                notes TEXT DEFAULT '',
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(version_group_id, variant_name, proxy_version)
            )
        ''')
        self._connection.commit()

    def add_custom_proxy(self, proxy_data: Dict[str, Any]) -> bool:
        """
        Add a custom proxy record to the database.

        DEPRECATED: Custom proxies (p001, p002) legacy format.
        Use update_proxy operator instead for new proxy saves.

        Args:
            proxy_data: Dict with keys: uuid, version_group_id, variant_name,
                asset_id, asset_name, asset_type, proxy_version, proxy_label,
                blend_path, thumbnail_path, polygon_count, notes

        Returns:
            True if successful
        """
        if not self._connection:
            self.connect()

        self._ensure_custom_proxies_table()

        try:
            cursor = self._connection.cursor()

            # Filter to valid columns
            cursor.execute("PRAGMA table_info(custom_proxies)")
            table_columns = {col[1] for col in cursor.fetchall()}
            filtered_data = {k: v for k, v in proxy_data.items() if k in table_columns}

            columns = ', '.join(filtered_data.keys())
            placeholders = ', '.join(['?' for _ in filtered_data])

            cursor.execute(
                f"INSERT INTO custom_proxies ({columns}) VALUES ({placeholders})",
                list(filtered_data.values())
            )
            self._connection.commit()
            return True
        except Exception:
            return False

    def get_next_custom_proxy_version(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> int:
        """
        Get the next proxy version number.

        DEPRECATED: Custom proxies (p001, p002) legacy format.
        Use update_proxy operator instead for new proxy saves.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name

        Returns:
            Next version number (1 if none exist)
        """
        if not self._connection:
            self.connect()

        self._ensure_custom_proxies_table()

        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                SELECT MAX(proxy_version) FROM custom_proxies
                WHERE version_group_id = ? AND variant_name = ?
            ''', (version_group_id, variant_name))
            row = cursor.fetchone()
            max_version = row[0] if row and row[0] is not None else 0
            return max_version + 1
        except Exception:
            return 1

    def get_custom_proxy_count(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> int:
        """
        Get the count of custom proxies for an asset variant.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name

        Returns:
            Number of custom proxies
        """
        if not self._connection:
            self.connect()

        self._ensure_custom_proxies_table()

        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM custom_proxies
                WHERE version_group_id = ? AND variant_name = ?
            ''', (version_group_id, variant_name))
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def _ensure_representation_designations_table(self):
        """Create representation_designations table if it doesn't exist."""
        if not self._connection:
            self.connect()

        cursor = self._connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS representation_designations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_group_id TEXT NOT NULL,
                variant_name TEXT NOT NULL DEFAULT 'Base',
                proxy_version_uuid TEXT,
                render_version_uuid TEXT,
                proxy_version_label TEXT,
                render_version_label TEXT,
                proxy_blend_path TEXT,
                render_blend_path TEXT,
                proxy_source TEXT DEFAULT 'version',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(version_group_id, variant_name)
            )
        ''')
        self._connection.commit()

    def _get_representation_designation(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> Optional[Dict[str, Any]]:
        """Read existing representation designation from DB."""
        if not self._connection:
            self.connect()

        self._ensure_representation_designations_table()

        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT * FROM representation_designations
            WHERE version_group_id = ? AND variant_name = ?
        ''', (version_group_id, variant_name))
        row = cursor.fetchone()
        return dict(row) if row else None

    def designate_custom_proxy(
        self,
        version_group_id: str,
        variant_name: str,
        proxy_uuid: str,
        proxy_label: str,
        proxy_blend_path: str,
        asset_name: str,
        asset_id: str,
        asset_type: str = 'mesh',
    ) -> bool:
        """
        Designate a custom proxy as the active proxy representation.

        DEPRECATED: Custom proxies (p001, p002) legacy format.
        Use update_proxy operator instead for new proxy saves.

        Also auto-creates .render.blend (from latest version) and
        .current.blend if they don't exist yet.

        Representation files use BASE names (no version) for stable linking:
        - Sword.proxy.blend, Sword.render.blend, Sword.current.blend

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name (e.g. 'Base')
            proxy_uuid: UUID of the custom proxy record
            proxy_label: Label (e.g. 'p001')
            proxy_blend_path: Absolute path to the custom proxy .blend file
            asset_name: Human-readable asset name
            asset_id: Asset family UUID
            asset_type: Asset type (mesh, rig)

        Returns:
            True if designation succeeded
        """
        import re
        import shutil

        library_folder = self.get_library_folder_path(
            asset_id, asset_name, variant_name, asset_type
        )

        # Find the latest versioned .blend file in the library folder
        # Pattern: AssetName.vXXX.blend
        safe_name = self._sanitize_filename(asset_name)
        version_pattern = re.compile(rf'^{re.escape(safe_name)}\.v(\d{{3,}})\.blend$')
        highest_version = -1
        library_blend = None

        if library_folder.exists():
            for file in library_folder.glob(f"{safe_name}.v*.blend"):
                match = version_pattern.match(file.name)
                if match:
                    version_num = int(match.group(1))
                    if version_num > highest_version:
                        highest_version = version_num
                        library_blend = file

        # Fallback to legacy unversioned filename
        if library_blend is None:
            legacy_path = library_folder / f"{safe_name}.blend"
            if legacy_path.exists():
                library_blend = legacy_path

        if library_blend is None or not library_blend.exists():
            return False

        # Representation files use BASE name (no version) for stable linking
        # e.g., Sword.proxy.blend, Sword.render.blend, Sword.current.blend

        # 1. Copy custom proxy → .proxy.blend
        proxy_output = library_folder / f"{safe_name}.proxy.blend"
        proxy_src = Path(proxy_blend_path)

        # Fallback: if stored path doesn't exist, try alternative naming
        if not proxy_src.exists():
            # Try versioned path: Sword.p001.blend
            versioned_src = proxy_src.parent / f"{safe_name}.{proxy_label}.blend"
            if versioned_src.exists():
                proxy_src = versioned_src
            else:
                # Try legacy path: Sword.blend
                legacy_src = proxy_src.parent / f"{safe_name}.blend"
                if legacy_src.exists():
                    proxy_src = legacy_src
                else:
                    return False

        try:
            shutil.copy2(str(proxy_src), str(proxy_output))
        except Exception:
            return False

        # 2. Create .render.blend from latest version if missing
        render_output = library_folder / f"{safe_name}.render.blend"
        render_blend_path_str = None
        if not render_output.exists():
            try:
                shutil.copy2(str(library_blend), str(render_output))
                render_blend_path_str = str(render_output)
            except Exception:
                pass  # Non-critical

        # 3. Ensure .current.blend exists
        current_output = library_folder / f"{safe_name}.current.blend"
        if not current_output.exists():
            try:
                shutil.copy2(str(library_blend), str(current_output))
            except Exception:
                pass  # Non-critical

        # 4. Update representation_designations in DB
        self._ensure_representation_designations_table()

        try:
            existing = self._get_representation_designation(version_group_id, variant_name)
            cursor = self._connection.cursor()
            now = datetime.now().isoformat()

            if existing:
                # Update proxy columns; preserve existing render
                cursor.execute('''
                    UPDATE representation_designations
                    SET proxy_version_uuid = ?, proxy_version_label = ?,
                        proxy_blend_path = ?, proxy_source = ?, last_updated = ?
                    WHERE version_group_id = ? AND variant_name = ?
                ''', (proxy_uuid, proxy_label, str(proxy_output), 'custom', now,
                      version_group_id, variant_name))

                # Set render path only if not already set
                if render_blend_path_str and not existing.get('render_blend_path'):
                    cursor.execute('''
                        UPDATE representation_designations
                        SET render_blend_path = ?
                        WHERE version_group_id = ? AND variant_name = ?
                    ''', (render_blend_path_str, version_group_id, variant_name))
            else:
                # Insert new row with proxy + render
                cursor.execute('''
                    INSERT INTO representation_designations (
                        version_group_id, variant_name,
                        proxy_version_uuid, proxy_version_label, proxy_blend_path,
                        render_version_uuid, render_version_label, render_blend_path,
                        proxy_source, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (version_group_id, variant_name,
                      proxy_uuid, proxy_label, str(proxy_output),
                      None, None, render_blend_path_str,
                      'custom', now))

            self._connection.commit()
            return True
        except Exception:
            return False

    def search_assets(self, query: str) -> List[Dict[str, Any]]:
        """Search assets by name or tags"""
        if not self._connection:
            self.connect()

        cursor = self._connection.cursor()
        search_term = f"%{query}%"

        cursor.execute("""
            SELECT * FROM assets
            WHERE name LIKE ? OR description LIKE ? OR tags LIKE ?
            ORDER BY name
        """, (search_term, search_term, search_term))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_folders(self, parent_id: int = None) -> List[Dict[str, Any]]:
        """Get folders, optionally by parent"""
        if not self._connection:
            self.connect()

        cursor = self._connection.cursor()

        if parent_id is not None:
            cursor.execute(
                "SELECT * FROM folders WHERE parent_id = ? ORDER BY name",
                (parent_id,)
            )
        else:
            cursor.execute("SELECT * FROM folders ORDER BY name")

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def move_to_cold_storage(self, asset_uuid: str) -> bool:
        """
        Move asset to cold storage (archive).

        This moves the asset files to the archive folder and updates
        the database to mark the asset as cold.

        Args:
            asset_uuid: UUID of asset to move to cold storage

        Returns:
            True if successful, False otherwise
        """
        import shutil

        if not self._connection:
            self.connect()

        asset = self.get_asset_by_uuid(asset_uuid)
        if not asset:
            return False

        # Get info for archive path
        asset_id = asset.get('asset_id') or asset.get('version_group_id') or asset_uuid
        asset_name = asset.get('name', 'Asset')
        variant_name = asset.get('variant_name') or 'Base'
        version_label = asset.get('version_label') or 'v001'
        asset_type = asset.get('asset_type') or 'other'

        # Use archive path structure: _archive/{type}/{name}/{variant}/{version}/
        cold_dir = self.get_archive_folder_path(asset_id, asset_name, variant_name, version_label, asset_type)

        moved_files = []

        try:
            # Move USD file
            usd_path = asset.get('usd_file_path')
            if usd_path and Path(usd_path).exists():
                new_usd_path = cold_dir / Path(usd_path).name
                shutil.move(usd_path, new_usd_path)
                moved_files.append(('usd_file_path', str(new_usd_path)))

            # Move blend backup
            blend_path = asset.get('blend_backup_path')
            if blend_path and Path(blend_path).exists():
                new_blend_path = cold_dir / Path(blend_path).name
                shutil.move(blend_path, new_blend_path)
                moved_files.append(('blend_backup_path', str(new_blend_path)))

            # Move thumbnail
            thumb_path = asset.get('thumbnail_path')
            if thumb_path and Path(thumb_path).exists():
                new_thumb_path = cold_dir / Path(thumb_path).name
                shutil.move(thumb_path, new_thumb_path)
                moved_files.append(('thumbnail_path', str(new_thumb_path)))

            # Update database
            updates = {
                'is_cold': 1,
                'cold_storage_path': str(cold_dir),
                'is_immutable': 1,
            }

            # Update file paths
            for key, new_path in moved_files:
                updates[key] = new_path

            self.update_asset(asset_uuid, updates)

            # Clean up empty source folder
            source_folder = self._assets_path / asset_uuid
            if source_folder.exists() and not any(source_folder.iterdir()):
                source_folder.rmdir()

            return True

        except Exception:
            # Try to restore moved files on failure
            for key, new_path in moved_files:
                try:
                    original_path = self._assets_path / asset_uuid / Path(new_path).name
                    original_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(new_path, original_path)
                except Exception:
                    pass
            return False


# Global connection instance
_library_connection: Optional[LibraryConnection] = None


def get_library_connection(library_path: str = None) -> LibraryConnection:
    """Get global library connection"""
    global _library_connection
    if _library_connection is None:
        _library_connection = LibraryConnection(library_path)
        _library_connection.connect()
    return _library_connection


def set_library_path(path: str):
    """Set library path and reconnect"""
    global _library_connection
    if _library_connection:
        _library_connection.disconnect()
    _library_connection = LibraryConnection(path)
    _library_connection.connect()


__all__ = ['LibraryConnection', 'get_library_connection', 'set_library_path']
