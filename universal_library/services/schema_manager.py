"""
SchemaManager - Database schema creation and migrations.

Handles:
- Initial schema creation
- Column migrations for folders and assets
- Junction table creation (tags, asset_folders, dependencies)
- Index creation and maintenance
"""

import logging
import sqlite3
from datetime import datetime
from typing import Set

logger = logging.getLogger(__name__)


class SchemaManager:
    """
    Manages database schema initialization and migrations.

    Supports incremental migrations that add columns and tables
    while preserving existing data.
    """

    SCHEMA_VERSION = 17  # Versioned filename convention migration marker

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to library database
        """
        self._connection = connection

    def initialize(self):
        """
        Initialize database schema.

        Creates schema if new database, runs migrations for existing.
        Uses a transaction to ensure atomic schema creation/migration.
        """
        cursor = self._connection.cursor()

        try:
            # Schema version table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Check current version
            cursor.execute('SELECT MAX(version) FROM schema_version')
            result = cursor.fetchone()
            current_version = result[0] if result[0] is not None else 0

            if current_version == 0:
                self._create_schema(cursor)
                cursor.execute(
                    'INSERT OR REPLACE INTO schema_version (version) VALUES (?)',
                    (self.SCHEMA_VERSION,)
                )
            else:
                # Run migrations for existing databases
                self._run_migrations(cursor, current_version)

            # Always ensure root folder exists
            self._ensure_root_folder(cursor)

            # Commit only if everything succeeded
            self._connection.commit()

        except Exception as e:
            # Rollback on any failure to prevent partial schema
            self._connection.rollback()
            raise RuntimeError(f"Schema initialization failed: {e}") from e

    def _create_schema(self, cursor: sqlite3.Cursor):
        """Create database schema for USD assets."""

        # Folders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER,
                path TEXT UNIQUE,
                description TEXT,
                icon_name TEXT,
                icon_color TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES folders (id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id)')

        # Assets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                folder_id INTEGER NOT NULL,
                asset_type TEXT NOT NULL,
                usd_file_path TEXT,
                blend_backup_path TEXT,
                thumbnail_path TEXT,
                preview_path TEXT,
                file_size_mb REAL,
                has_materials INTEGER DEFAULT 0,
                has_skeleton INTEGER DEFAULT 0,
                has_animations INTEGER DEFAULT 0,
                polygon_count INTEGER,
                material_count INTEGER,
                tags TEXT,
                author TEXT,
                source_application TEXT,
                is_favorite INTEGER DEFAULT 0,
                last_viewed_date TIMESTAMP,
                custom_order INTEGER,
                is_locked INTEGER DEFAULT 0,
                status TEXT DEFAULT 'wip',
                version INTEGER DEFAULT 1,
                version_label TEXT DEFAULT 'v001',
                version_group_id TEXT,
                is_latest INTEGER DEFAULT 1,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (folder_id) REFERENCES folders (id) ON DELETE CASCADE
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_uuid ON assets(uuid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_folder ON assets(folder_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_name ON assets(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_favorite ON assets(is_favorite)')

        # Ensure all columns exist (for existing databases being upgraded)
        self._run_migrations(cursor, 0)

        # Create indexes for columns added by migrations
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_last_viewed ON assets(last_viewed_date)')

        self._ensure_root_folder(cursor)

    def _ensure_root_folder(self, cursor: sqlite3.Cursor):
        """Ensure a root folder exists in the database."""
        cursor.execute('SELECT id FROM folders WHERE parent_id IS NULL LIMIT 1')
        if not cursor.fetchone():
            now = datetime.now()
            # Check if path column exists
            cursor.execute("PRAGMA table_info(folders)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'path' in columns:
                cursor.execute('''
                    INSERT INTO folders (name, parent_id, path, created_date, modified_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', ("Root", None, "", now, now))
            else:
                cursor.execute('''
                    INSERT INTO folders (name, parent_id, created_date, modified_date)
                    VALUES (?, ?, ?, ?)
                ''', ("Root", None, now, now))

    def _run_migrations(self, cursor: sqlite3.Cursor, current_version: int):
        """Run database migrations for existing databases."""
        # Migrate folders table
        cursor.execute("PRAGMA table_info(folders)")
        folder_columns_existing = {col[1] for col in cursor.fetchall()}

        folder_columns = {
            'path': 'TEXT',
            'description': 'TEXT',
            'icon_name': 'TEXT',
            'icon_color': 'TEXT',
        }

        self._add_missing_columns(cursor, 'folders', folder_columns, folder_columns_existing)

        # Migrate assets table
        cursor.execute("PRAGMA table_info(assets)")
        asset_columns_existing = {col[1] for col in cursor.fetchall()}

        asset_columns = {
            'blend_backup_path': 'TEXT',
            'preview_path': 'TEXT',
            'last_viewed_date': 'TIMESTAMP',
            'custom_order': 'INTEGER',
            'is_locked': 'INTEGER DEFAULT 0',
            'created_date': 'TIMESTAMP',
            'modified_date': 'TIMESTAMP',
            'status': "TEXT DEFAULT 'wip'",
            'version': 'INTEGER DEFAULT 1',
            'version_label': "TEXT DEFAULT 'v001'",
            'version_group_id': 'TEXT',
            'is_latest': 'INTEGER DEFAULT 1',
            'parent_version_uuid': 'TEXT',
            'representation_type': "TEXT DEFAULT 'none'",
            'is_cold': 'INTEGER DEFAULT 0',
            'cold_storage_path': 'TEXT',
            'original_usd_path': 'TEXT',
            'original_blend_path': 'TEXT',
            'original_thumbnail_path': 'TEXT',
            'is_immutable': 'INTEGER DEFAULT 0',
            'published_date': 'TIMESTAMP',
            'published_by': 'TEXT',
            'bone_count': 'INTEGER',
            'has_facial_rig': 'INTEGER DEFAULT 0',
            'control_count': 'INTEGER',
            'frame_start': 'INTEGER',
            'frame_end': 'INTEGER',
            'frame_rate': 'REAL',
            'is_loop': 'INTEGER DEFAULT 0',
            'texture_maps': 'TEXT',
            'texture_resolution': 'TEXT',
            'light_type': 'TEXT',
            'light_count': 'INTEGER',
            'camera_type': 'TEXT',
            'focal_length': 'REAL',
            'mesh_count': 'INTEGER',
            'camera_count': 'INTEGER',
            'armature_count': 'INTEGER',
            'collection_name': 'TEXT',
            'has_nested_collections': 'INTEGER DEFAULT 0',
            'nested_collection_count': 'INTEGER',
            'asset_id': 'TEXT',
            'variant_name': "TEXT DEFAULT 'Base'",
            'variant_source_uuid': 'TEXT',
            'source_asset_name': 'TEXT',
            'source_version_label': 'TEXT',
            'variant_set': 'TEXT',
            'version_notes': 'TEXT',
            # Grease Pencil metadata
            'layer_count': 'INTEGER',
            'stroke_count': 'INTEGER',
            'frame_count': 'INTEGER',
            # Curve metadata
            'curve_type': 'TEXT',
            'point_count': 'INTEGER',
            'spline_count': 'INTEGER',
            # Scene metadata
            'scene_name': 'TEXT',
            'object_count': 'INTEGER',
            'collection_count': 'INTEGER',
            'render_engine': 'TEXT',
            'resolution_x': 'INTEGER',
            'resolution_y': 'INTEGER',
            'world_name': 'TEXT',
            # Mesh extended metadata
            'vertex_group_count': 'INTEGER',
            'shape_key_count': 'INTEGER',
            # Light extended metadata
            'light_power': 'REAL',
            'light_color': 'TEXT',
            'light_shadow': 'INTEGER DEFAULT 0',
            'light_spot_size': 'REAL',
            'light_area_shape': 'TEXT',
            # Camera extended metadata
            'camera_sensor_width': 'REAL',
            'camera_clip_start': 'REAL',
            'camera_clip_end': 'REAL',
            'camera_dof_enabled': 'INTEGER DEFAULT 0',
            'camera_ortho_scale': 'REAL',
            # Retire system columns
            'is_retired': 'INTEGER DEFAULT 0',
            'retired_date': 'TIMESTAMP',
            'retired_by': 'TEXT',
        }

        self._add_missing_columns(cursor, 'assets', asset_columns, asset_columns_existing)

        # Create junction and supporting tables
        self._create_dependencies_table(cursor)
        self._create_tags_tables(cursor)
        self._create_asset_folders_table(cursor)
        self._create_entity_system_tables(cursor)
        self._create_asset_audit_table(cursor)
        self._create_app_settings_table(cursor)
        self._create_representation_designations_table(cursor)
        self._create_custom_proxies_table(cursor)
        self._create_migration_status_table(cursor)

        # Migrate representation_designations for v16
        self._migrate_representation_designations_v16(cursor)

        # Mark v17 filename migration as pending (actual migration is manual)
        self._mark_filename_migration_v17(cursor)

        # Create indexes
        self._create_indexes(cursor)

        # Data migrations
        self._migrate_variant_data(cursor, asset_columns_existing)

        # Seed entity system
        self._seed_entity_types(cursor)

    def _add_missing_columns(
        self,
        cursor: sqlite3.Cursor,
        table: str,
        columns: dict,
        existing: Set[str]
    ):
        """Add missing columns to a table."""
        for col_name, col_type in columns.items():
            if col_name not in existing:
                try:
                    cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type}')
                    logger.debug(f"Added column '{col_name}' to {table} table")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not add column '{col_name}' to {table}: {e}")

    def _create_dependencies_table(self, cursor: sqlite3.Cursor):
        """Create dependencies table for tracking asset references."""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dependencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                dependency_type TEXT NOT NULL,
                relative_path TEXT,
                absolute_path TEXT,
                status TEXT DEFAULT 'unknown',
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_dependencies_asset ON dependencies(asset_id)')

    def _create_tags_tables(self, cursor: sqlite3.Cursor):
        """Create tags and asset_tags junction tables."""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT DEFAULT '#607D8B',
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asset_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_uuid TEXT NOT NULL,
                tag_id INTEGER NOT NULL,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                UNIQUE(asset_uuid, tag_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_tags_uuid ON asset_tags(asset_uuid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_tags_tag ON asset_tags(tag_id)')

    def _create_asset_folders_table(self, cursor: sqlite3.Cursor):
        """Create asset_folders junction table for multi-folder membership."""
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

    def _create_entity_system_tables(self, cursor: sqlite3.Cursor):
        """
        Create entity system tables for extensible metadata.

        Tables:
        - entity_types: Registry of entity types (asset, task, shot, etc.)
        - metadata_fields: Schema-driven field definitions
        - entity_metadata: Dynamic EAV storage for entity metadata
        """
        # Entity type registry
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entity_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                table_name TEXT NOT NULL,
                behaviors TEXT DEFAULT '[]',
                icon_name TEXT,
                icon_color TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_types_name ON entity_types(name)')

        # Field definitions (schema-driven metadata)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                field_type TEXT NOT NULL,
                ui_widget TEXT DEFAULT 'text',
                category TEXT DEFAULT 'general',
                sort_order INTEGER DEFAULT 100,
                default_value TEXT,
                validation_rules TEXT,
                is_required INTEGER DEFAULT 0,
                is_searchable INTEGER DEFAULT 0,
                show_in_card INTEGER DEFAULT 0,
                show_in_details INTEGER DEFAULT 1,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (entity_type_id) REFERENCES entity_types(id) ON DELETE CASCADE,
                UNIQUE(entity_type_id, field_name)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_metadata_fields_type ON metadata_fields(entity_type_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_metadata_fields_category ON metadata_fields(category)')

        # Dynamic metadata storage (EAV pattern)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entity_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_uuid TEXT NOT NULL,
                field_id INTEGER NOT NULL,
                value_text TEXT,
                value_int INTEGER,
                value_real REAL,
                value_json TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (field_id) REFERENCES metadata_fields(id) ON DELETE CASCADE,
                UNIQUE(entity_uuid, field_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_metadata_uuid ON entity_metadata(entity_uuid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_metadata_field ON entity_metadata(field_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_metadata_type ON entity_metadata(entity_type)')

    def _create_asset_audit_table(self, cursor: sqlite3.Cursor):
        """
        Create asset_audit_log table for studio audit trail.

        This table tracks all asset lifecycle events when Studio Mode is enabled.
        It's append-only and should never be modified after creation.
        """
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asset_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                -- What asset
                asset_uuid TEXT NOT NULL,
                version_group_id TEXT,
                version_label TEXT,
                variant_name TEXT DEFAULT 'Base',

                -- What happened
                action TEXT NOT NULL,
                action_category TEXT,

                -- Who did it
                actor TEXT NOT NULL,
                actor_role TEXT DEFAULT '',
                actor_display_name TEXT,

                -- When
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Details
                details TEXT,
                previous_value TEXT,
                new_value TEXT,

                -- Context
                source TEXT DEFAULT 'desktop',
                session_id TEXT
            )
        ''')

        # Create indexes for common queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_audit_asset ON asset_audit_log(asset_uuid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_audit_actor ON asset_audit_log(actor)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_audit_action ON asset_audit_log(action)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_audit_timestamp ON asset_audit_log(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_audit_version_group ON asset_audit_log(version_group_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_audit_category ON asset_audit_log(action_category)')

    def _create_app_settings_table(self, cursor: sqlite3.Cursor):
        """
        Create app_settings table for application-wide settings.

        This table stores settings like operation_mode that need to be
        accessible by external tools (e.g., Pipeline Control).
        """
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    def _create_representation_designations_table(self, cursor: sqlite3.Cursor):
        """
        Create representation_designations table for proxy/render version switching.

        Stores which archived version is designated as proxy (lightweight)
        and render (high-quality) for each asset variant. Shot Library uses
        the resulting .proxy.blend and .render.blend files during playblast
        and lookdev renders.
        """
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
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(version_group_id, variant_name)
            )
        ''')
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_rep_designations_vgroup '
            'ON representation_designations(version_group_id)'
        )

    def _create_custom_proxies_table(self, cursor: sqlite3.Cursor):
        """
        Create custom_proxies table for artist-authored proxy geometry.

        Custom proxies are hand-modeled lightweight representations saved
        from Blender. They have their own versioning (p001, p002, etc.)
        and are stored in _proxy/ folders within the library asset folder.
        """
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
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_custom_proxies_vgroup '
            'ON custom_proxies(version_group_id)'
        )
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_custom_proxies_uuid '
            'ON custom_proxies(uuid)'
        )

    def _migrate_representation_designations_v16(self, cursor: sqlite3.Cursor):
        """Add proxy_source column to representation_designations (schema v16)."""
        cursor.execute("PRAGMA table_info(representation_designations)")
        existing = {col[1] for col in cursor.fetchall()}
        if 'proxy_source' not in existing:
            try:
                cursor.execute('''
                    ALTER TABLE representation_designations
                    ADD COLUMN proxy_source TEXT DEFAULT 'version'
                ''')
                logger.debug("Added column 'proxy_source' to representation_designations table")
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not add proxy_source column: {e}")

        # Add proxy_variant_name column for cross-variant proxy designation
        if 'proxy_variant_name' not in existing:
            try:
                cursor.execute('''
                    ALTER TABLE representation_designations
                    ADD COLUMN proxy_variant_name TEXT
                ''')
                logger.debug("Added column 'proxy_variant_name' to representation_designations table")
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not add proxy_variant_name column: {e}")

    def _create_migration_status_table(self, cursor: sqlite3.Cursor):
        """
        Create migration_status table for tracking data migrations.

        Unlike schema migrations (which run automatically), some migrations
        require user initiation (e.g., file renames). This table tracks their status.
        """
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS migration_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_name TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                metadata TEXT
            )
        ''')

    def _mark_filename_migration_v17(self, cursor: sqlite3.Cursor):
        """
        Mark the v17 versioned filename migration as pending.

        This migration renames existing files and updates database paths.
        It's marked here but executed separately via FilenameMigrationService.
        """
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO migration_status (migration_name, status)
                VALUES ('versioned_filename_v17', 'pending')
            ''')
            if cursor.rowcount > 0:
                logger.info("Marked versioned_filename_v17 migration as pending")
        except sqlite3.OperationalError as e:
            logger.warning(f"Could not mark filename migration: {e}")

    def _create_indexes(self, cursor: sqlite3.Cursor):
        """Create all required indexes."""
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status)',
            'CREATE INDEX IF NOT EXISTS idx_assets_version_group ON assets(version_group_id)',
            'CREATE INDEX IF NOT EXISTS idx_assets_is_cold ON assets(is_cold)',
            'CREATE INDEX IF NOT EXISTS idx_assets_is_latest ON assets(is_latest)',
            'CREATE INDEX IF NOT EXISTS idx_assets_asset_id ON assets(asset_id)',
            'CREATE INDEX IF NOT EXISTS idx_assets_variant ON assets(variant_name)',
            'CREATE INDEX IF NOT EXISTS idx_assets_representation ON assets(representation_type)',
            'CREATE INDEX IF NOT EXISTS idx_assets_is_retired ON assets(is_retired)',
        ]
        for index_sql in indexes:
            cursor.execute(index_sql)

    def _migrate_variant_data(self, cursor: sqlite3.Cursor, existing_columns: Set[str]):
        """Run data migrations for variant system."""
        # Migrate existing assets to variant system - run unconditionally to catch any
        # assets that might have NULL asset_id (e.g., added before migration ran)
        cursor.execute('''
            UPDATE assets
            SET asset_id = version_group_id
            WHERE (asset_id IS NULL OR asset_id = '') AND version_group_id IS NOT NULL
        ''')
        cursor.execute('''
            UPDATE assets
            SET variant_name = 'Base'
            WHERE variant_name IS NULL OR variant_name = ''
        ''')

        # Populate provenance fields
        if 'source_asset_name' not in existing_columns:
            cursor.execute('''
                UPDATE assets
                SET source_asset_name = (
                    SELECT source.name FROM assets AS source
                    WHERE source.uuid = assets.variant_source_uuid
                ),
                source_version_label = (
                    SELECT source.version_label FROM assets AS source
                    WHERE source.uuid = assets.variant_source_uuid
                )
                WHERE variant_source_uuid IS NOT NULL
                  AND source_asset_name IS NULL
            ''')
            cursor.execute('''
                UPDATE assets
                SET variant_set = 'Default'
                WHERE variant_name != 'Base'
                  AND variant_set IS NULL
            ''')

    def _seed_entity_types(self, cursor: sqlite3.Cursor):
        """
        Seed entity types and metadata fields.

        Creates the 'asset' entity type and registers all type-specific
        metadata fields that will eventually migrate to the EAV system.
        """
        import json

        # Get or create asset entity type
        cursor.execute('SELECT id FROM entity_types WHERE name = ?', ('asset',))
        row = cursor.fetchone()
        if not row:
            # Register asset entity type
            behaviors = json.dumps(['versionable', 'variantable', 'reviewable', 'taggable', 'folderable'])
            cursor.execute('''
                INSERT INTO entity_types (name, table_name, behaviors, icon_name, icon_color)
                VALUES (?, ?, ?, ?, ?)
            ''', ('asset', 'assets', behaviors, 'mesh_data', '#4CAF50'))
            cursor.execute('SELECT id FROM entity_types WHERE name = ?', ('asset',))
            row = cursor.fetchone()

        entity_type_id = row[0]

        # Define all metadata fields to register
        # These will be migrated from columns to EAV storage
        fields = [
            # Core/Universal fields (shown on all asset types)
            ('polygon_count', 'Polygons', 'integer', 'number', 'mesh', 10),
            ('material_count', 'Materials', 'integer', 'number', 'mesh', 20),
            ('has_materials', 'Has Materials', 'boolean', 'checkbox', 'mesh', 30),
            ('has_skeleton', 'Has Skeleton', 'boolean', 'checkbox', 'mesh', 40),
            ('has_animations', 'Has Animations', 'boolean', 'checkbox', 'mesh', 50),
            ('file_size_mb', 'File Size (MB)', 'real', 'number', 'file', 10),
            # Rig category
            ('bone_count', 'Bone Count', 'integer', 'number', 'rig', 10),
            ('control_count', 'Control Count', 'integer', 'number', 'rig', 20),
            ('has_facial_rig', 'Has Facial Rig', 'boolean', 'checkbox', 'rig', 30),
            # Animation category
            ('frame_start', 'Frame Start', 'integer', 'number', 'animation', 10),
            ('frame_end', 'Frame End', 'integer', 'number', 'animation', 20),
            ('frame_rate', 'Frame Rate', 'real', 'number', 'animation', 30),
            ('is_loop', 'Is Looping', 'boolean', 'checkbox', 'animation', 40),
            # Material category
            ('texture_maps', 'Texture Maps', 'json', 'text', 'material', 10),
            ('texture_resolution', 'Texture Resolution', 'string', 'text', 'material', 20),
            # Mesh extended
            ('vertex_group_count', 'Vertex Groups', 'integer', 'number', 'mesh', 60),
            ('shape_key_count', 'Shape Keys', 'integer', 'number', 'mesh', 70),
            # Light category
            ('light_type', 'Light Type', 'string', 'text', 'light', 10),
            ('light_count', 'Light Count', 'integer', 'number', 'light', 20),
            ('light_power', 'Power', 'real', 'number', 'light', 30),
            ('light_color', 'Color', 'string', 'text', 'light', 40),
            ('light_shadow', 'Shadow', 'boolean', 'checkbox', 'light', 50),
            ('light_spot_size', 'Spot Size', 'real', 'number', 'light', 60),
            ('light_area_shape', 'Area Shape', 'string', 'text', 'light', 70),
            # Camera category
            ('camera_type', 'Camera Type', 'string', 'text', 'camera', 10),
            ('focal_length', 'Focal Length', 'real', 'number', 'camera', 20),
            ('camera_sensor_width', 'Sensor Width', 'real', 'number', 'camera', 30),
            ('camera_clip_start', 'Clip Start', 'real', 'number', 'camera', 40),
            ('camera_clip_end', 'Clip End', 'real', 'number', 'camera', 50),
            ('camera_dof_enabled', 'DOF Enabled', 'boolean', 'checkbox', 'camera', 60),
            ('camera_ortho_scale', 'Ortho Scale', 'real', 'number', 'camera', 70),
            # Collection category
            ('collection_name', 'Collection Name', 'string', 'text', 'collection', 10),
            ('mesh_count', 'Mesh Count', 'integer', 'number', 'collection', 20),
            ('camera_count', 'Camera Count', 'integer', 'number', 'collection', 30),
            ('armature_count', 'Armature Count', 'integer', 'number', 'collection', 40),
            ('has_nested_collections', 'Has Nested Collections', 'boolean', 'checkbox', 'collection', 50),
            ('nested_collection_count', 'Nested Collection Count', 'integer', 'number', 'collection', 60),
            # Grease Pencil category
            ('layer_count', 'Layers', 'integer', 'number', 'grease_pencil', 10),
            ('stroke_count', 'Strokes', 'integer', 'number', 'grease_pencil', 20),
            ('frame_count', 'Frames', 'integer', 'number', 'grease_pencil', 30),
            # Curve category
            ('curve_type', 'Curve Type', 'string', 'text', 'curve', 10),
            ('point_count', 'Points', 'integer', 'number', 'curve', 20),
            ('spline_count', 'Splines', 'integer', 'number', 'curve', 30),
            # Scene category
            ('scene_name', 'Scene Name', 'string', 'text', 'scene', 10),
            ('object_count', 'Objects', 'integer', 'number', 'scene', 20),
            ('collection_count', 'Collections', 'integer', 'number', 'scene', 30),
            ('render_engine', 'Render Engine', 'string', 'text', 'scene', 40),
            ('resolution_x', 'Resolution X', 'integer', 'number', 'scene', 50),
            ('resolution_y', 'Resolution Y', 'integer', 'number', 'scene', 60),
            ('world_name', 'World', 'string', 'text', 'scene', 70),
        ]

        for field_name, display_name, field_type, ui_widget, category, sort_order in fields:
            cursor.execute('''
                INSERT OR IGNORE INTO metadata_fields
                (entity_type_id, field_name, display_name, field_type, ui_widget, category, sort_order, show_in_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ''', (entity_type_id, field_name, display_name, field_type, ui_widget, category, sort_order))

        logger.debug("Seeded entity types and metadata fields")

    def ensure_metadata_fields(self):
        """
        Ensure all metadata fields are registered.

        This can be called on existing databases to register any new fields
        that were added after initial seeding.
        """
        import json
        cursor = self._connection.cursor()

        # Get asset entity type ID
        cursor.execute('SELECT id FROM entity_types WHERE name = ?', ('asset',))
        row = cursor.fetchone()
        if not row:
            logger.warning("No 'asset' entity type found - run full seeding first")
            return

        entity_type_id = row[0]

        # All fields that should exist (same as in _seed_entity_types)
        fields = [
            # Core/Universal fields
            ('polygon_count', 'Polygons', 'integer', 'number', 'mesh', 10),
            ('material_count', 'Materials', 'integer', 'number', 'mesh', 20),
            ('has_materials', 'Has Materials', 'boolean', 'checkbox', 'mesh', 30),
            ('has_skeleton', 'Has Skeleton', 'boolean', 'checkbox', 'mesh', 40),
            ('has_animations', 'Has Animations', 'boolean', 'checkbox', 'mesh', 50),
            ('file_size_mb', 'File Size (MB)', 'real', 'number', 'file', 10),
            # Rig category
            ('bone_count', 'Bone Count', 'integer', 'number', 'rig', 10),
            ('control_count', 'Control Count', 'integer', 'number', 'rig', 20),
            ('has_facial_rig', 'Has Facial Rig', 'boolean', 'checkbox', 'rig', 30),
            # Animation category
            ('frame_start', 'Frame Start', 'integer', 'number', 'animation', 10),
            ('frame_end', 'Frame End', 'integer', 'number', 'animation', 20),
            ('frame_rate', 'Frame Rate', 'real', 'number', 'animation', 30),
            ('is_loop', 'Is Looping', 'boolean', 'checkbox', 'animation', 40),
            # Material category
            ('texture_maps', 'Texture Maps', 'json', 'text', 'material', 10),
            ('texture_resolution', 'Texture Resolution', 'string', 'text', 'material', 20),
            # Mesh extended
            ('vertex_group_count', 'Vertex Groups', 'integer', 'number', 'mesh', 60),
            ('shape_key_count', 'Shape Keys', 'integer', 'number', 'mesh', 70),
            # Light category
            ('light_type', 'Light Type', 'string', 'text', 'light', 10),
            ('light_count', 'Light Count', 'integer', 'number', 'light', 20),
            ('light_power', 'Power', 'real', 'number', 'light', 30),
            ('light_color', 'Color', 'string', 'text', 'light', 40),
            ('light_shadow', 'Shadow', 'boolean', 'checkbox', 'light', 50),
            ('light_spot_size', 'Spot Size', 'real', 'number', 'light', 60),
            ('light_area_shape', 'Area Shape', 'string', 'text', 'light', 70),
            # Camera category
            ('camera_type', 'Camera Type', 'string', 'text', 'camera', 10),
            ('focal_length', 'Focal Length', 'real', 'number', 'camera', 20),
            ('camera_sensor_width', 'Sensor Width', 'real', 'number', 'camera', 30),
            ('camera_clip_start', 'Clip Start', 'real', 'number', 'camera', 40),
            ('camera_clip_end', 'Clip End', 'real', 'number', 'camera', 50),
            ('camera_dof_enabled', 'DOF Enabled', 'boolean', 'checkbox', 'camera', 60),
            ('camera_ortho_scale', 'Ortho Scale', 'real', 'number', 'camera', 70),
            # Collection category
            ('collection_name', 'Collection Name', 'string', 'text', 'collection', 10),
            ('mesh_count', 'Mesh Count', 'integer', 'number', 'collection', 20),
            ('camera_count', 'Camera Count', 'integer', 'number', 'collection', 30),
            ('armature_count', 'Armature Count', 'integer', 'number', 'collection', 40),
            ('has_nested_collections', 'Has Nested Collections', 'boolean', 'checkbox', 'collection', 50),
            ('nested_collection_count', 'Nested Collection Count', 'integer', 'number', 'collection', 60),
            # Grease Pencil category
            ('layer_count', 'Layers', 'integer', 'number', 'grease_pencil', 10),
            ('stroke_count', 'Strokes', 'integer', 'number', 'grease_pencil', 20),
            ('frame_count', 'Frames', 'integer', 'number', 'grease_pencil', 30),
            # Curve category
            ('curve_type', 'Curve Type', 'string', 'text', 'curve', 10),
            ('point_count', 'Points', 'integer', 'number', 'curve', 20),
            ('spline_count', 'Splines', 'integer', 'number', 'curve', 30),
            # Scene category
            ('scene_name', 'Scene Name', 'string', 'text', 'scene', 10),
            ('object_count', 'Objects', 'integer', 'number', 'scene', 20),
            ('collection_count', 'Collections', 'integer', 'number', 'scene', 30),
            ('render_engine', 'Render Engine', 'string', 'text', 'scene', 40),
            ('resolution_x', 'Resolution X', 'integer', 'number', 'scene', 50),
            ('resolution_y', 'Resolution Y', 'integer', 'number', 'scene', 60),
            ('world_name', 'World', 'string', 'text', 'scene', 70),
        ]

        added_count = 0
        for field_name, display_name, field_type, ui_widget, category, sort_order in fields:
            cursor.execute('''
                INSERT OR IGNORE INTO metadata_fields
                (entity_type_id, field_name, display_name, field_type, ui_widget, category, sort_order, show_in_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ''', (entity_type_id, field_name, display_name, field_type, ui_widget, category, sort_order))
            if cursor.rowcount > 0:
                added_count += 1

        self._connection.commit()

        if added_count > 0:
            logger.info(f"Registered {added_count} new metadata fields")
        else:
            logger.debug("All metadata fields already registered")

    def get_current_version(self) -> int:
        """Get current schema version from database."""
        cursor = self._connection.cursor()
        cursor.execute('SELECT MAX(version) FROM schema_version')
        result = cursor.fetchone()
        return result[0] if result and result[0] else 0

    def update_version(self, version: int):
        """Update schema version in database."""
        cursor = self._connection.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO schema_version (version) VALUES (?)',
            (version,)
        )
        self._connection.commit()


__all__ = ['SchemaManager']
