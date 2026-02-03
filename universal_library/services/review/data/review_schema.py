"""
ReviewSchema - Schema creation and migration for reviews database.

Handles:
- Table creation (review_sessions, review_cycles, review_notes, etc.)
- Index creation
- Schema version tracking
- Migrations between versions
"""

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


class ReviewSchema:
    """
    Manages review database schema creation and migrations.
    """

    SCHEMA_VERSION = 5

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    def create_schema(self) -> None:
        """Create database schema if not exists."""
        cursor = self._connection.cursor()

        # Review sessions table - one per asset version
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS review_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_uuid TEXT NOT NULL,
                version_label TEXT NOT NULL,
                cycle_id INTEGER,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP,
                status TEXT DEFAULT 'open',
                review_state TEXT DEFAULT NULL,
                submitted_for_review_date TIMESTAMP,
                submitted_by TEXT,
                approved_date TIMESTAMP,
                finalized_date TIMESTAMP,
                finalized_by TEXT,
                UNIQUE(asset_uuid, version_label),
                FOREIGN KEY (cycle_id) REFERENCES review_cycles(id) ON DELETE SET NULL
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sessions_uuid
            ON review_sessions(asset_uuid)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sessions_review_state
            ON review_sessions(review_state)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sessions_cycle
            ON review_sessions(cycle_id)
        ''')

        # Review cycles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS review_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                variant_name TEXT DEFAULT 'Base',
                cycle_type TEXT NOT NULL,
                start_version TEXT NOT NULL,
                end_version TEXT,
                review_state TEXT DEFAULT 'needs_review',
                submitted_by TEXT,
                submitted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finalized_by TEXT,
                finalized_date TIMESTAMP,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cycles_asset ON review_cycles(asset_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cycles_state ON review_cycles(review_state)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cycles_active ON review_cycles(asset_id, end_version)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cycles_variant ON review_cycles(asset_id, variant_name, end_version)')

        # Review screenshots table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS review_screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                display_name TEXT,
                file_path TEXT NOT NULL,
                display_order INTEGER DEFAULT 0,
                uploaded_by TEXT,
                uploaded_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES review_sessions(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_screenshots_session ON review_screenshots(session_id)')

        # Review notes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS review_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                screenshot_id INTEGER,
                note TEXT NOT NULL,
                author TEXT DEFAULT '',
                author_role TEXT DEFAULT 'artist',
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_date TIMESTAMP,
                resolved INTEGER DEFAULT 0,
                resolved_by TEXT,
                resolved_date TIMESTAMP,
                note_status TEXT DEFAULT 'open',
                addressed_by TEXT,
                addressed_date TIMESTAMP,
                approved_by TEXT,
                approved_date TIMESTAMP,
                deleted INTEGER DEFAULT 0,
                deleted_by TEXT,
                deleted_at TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES review_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (screenshot_id) REFERENCES review_screenshots(id) ON DELETE SET NULL
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_session ON review_notes(session_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_screenshot ON review_notes(screenshot_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_deleted ON review_notes(deleted)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_status ON review_notes(note_status)')

        # Audit log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS review_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                actor_role TEXT DEFAULT '',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                details TEXT,
                FOREIGN KEY (note_id) REFERENCES review_notes(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_note ON review_audit_log(note_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON review_audit_log(timestamp)')

        # Studio users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS studio_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT DEFAULT 'artist',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        ''')

        # App settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Drawover metadata table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS drawover_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_uuid TEXT NOT NULL,
                version_label TEXT NOT NULL,
                screenshot_id INTEGER NOT NULL,
                stroke_count INTEGER DEFAULT 0,
                authors TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_at TIMESTAMP,
                file_path TEXT,
                UNIQUE(asset_uuid, version_label, screenshot_id),
                FOREIGN KEY (screenshot_id) REFERENCES review_screenshots(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_drawover_uuid ON drawover_metadata(asset_uuid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_drawover_version ON drawover_metadata(asset_uuid, version_label)')

        # Drawover audit log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS drawover_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_uuid TEXT NOT NULL,
                version_label TEXT NOT NULL,
                screenshot_id INTEGER NOT NULL,
                stroke_id TEXT,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                actor_role TEXT DEFAULT '',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                details TEXT
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_drawover_audit_uuid ON drawover_audit_log(asset_uuid, version_label)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_drawover_audit_timestamp ON drawover_audit_log(timestamp)')

        # Schema version table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        ''')

        # Initialize defaults
        cursor.execute('SELECT version FROM schema_version')
        if cursor.fetchone() is None:
            cursor.execute('INSERT INTO schema_version (version) VALUES (?)', (self.SCHEMA_VERSION,))

        # Default settings
        cursor.execute('INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)', ('app_mode', 'solo'))
        cursor.execute('INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)', ('current_user', ''))
        cursor.execute('INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)', ('show_deleted_notes', 'false'))

        # Default admin user
        cursor.execute('''
            INSERT OR IGNORE INTO studio_users (username, display_name, role)
            VALUES (?, ?, ?)
        ''', ('admin', 'Administrator', 'admin'))

        self._connection.commit()

    def migrate_if_needed(self) -> None:
        """Run migrations if schema version is outdated."""
        cursor = self._connection.cursor()

        cursor.execute('SELECT version FROM schema_version')
        row = cursor.fetchone()
        current_version = row[0] if row else 1

        if current_version < 2:
            self._migrate_v1_to_v2()
            cursor.execute('UPDATE schema_version SET version = 2')
            self._connection.commit()
            current_version = 2

        if current_version < 3:
            self._migrate_v2_to_v3()
            cursor.execute('UPDATE schema_version SET version = 3')
            self._connection.commit()
            current_version = 3

        if current_version < 4:
            self._migrate_v3_to_v4()
            cursor.execute('UPDATE schema_version SET version = 4')
            self._connection.commit()
            current_version = 4

        if current_version < 5:
            self._migrate_v4_to_v5()
            cursor.execute('UPDATE schema_version SET version = 5')
            self._connection.commit()

    def _migrate_v1_to_v2(self) -> None:
        """Migration v1 -> v2: Add review workflow state columns."""
        cursor = self._connection.cursor()

        cursor.execute('PRAGMA table_info(review_sessions)')
        existing_columns = {row[1] for row in cursor.fetchall()}

        new_columns = [
            ('review_state', 'TEXT DEFAULT NULL'),
            ('submitted_for_review_date', 'TIMESTAMP'),
            ('submitted_by', 'TEXT'),
            ('approved_date', 'TIMESTAMP'),
            ('finalized_date', 'TIMESTAMP'),
            ('finalized_by', 'TEXT'),
        ]

        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                cursor.execute(f'ALTER TABLE review_sessions ADD COLUMN {col_name} {col_type}')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sessions_review_state
            ON review_sessions(review_state)
        ''')

        self._connection.commit()
        logger.info("Review database migrated to v2 (review workflow states)")

    def _migrate_v2_to_v3(self) -> None:
        """Migration v2 -> v3: Add 3-state note status columns."""
        cursor = self._connection.cursor()

        cursor.execute('PRAGMA table_info(review_notes)')
        existing_columns = {row[1] for row in cursor.fetchall()}

        new_columns = [
            ('note_status', "TEXT DEFAULT 'open'"),
            ('addressed_by', 'TEXT'),
            ('addressed_date', 'TIMESTAMP'),
            ('approved_by', 'TEXT'),
            ('approved_date', 'TIMESTAMP'),
        ]

        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                cursor.execute(f'ALTER TABLE review_notes ADD COLUMN {col_name} {col_type}')

        cursor.execute('''
            UPDATE review_notes
            SET note_status = 'approved'
            WHERE resolved = 1 AND (note_status IS NULL OR note_status = 'open')
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_notes_status
            ON review_notes(note_status)
        ''')

        self._connection.commit()
        logger.info("Review database migrated to v3 (3-state note status)")

    def _migrate_v3_to_v4(self) -> None:
        """Migration v3 -> v4: Add review cycles for multi-version review spans."""
        cursor = self._connection.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS review_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                cycle_type TEXT NOT NULL,
                start_version TEXT NOT NULL,
                end_version TEXT,
                review_state TEXT DEFAULT 'needs_review',
                submitted_by TEXT,
                submitted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finalized_by TEXT,
                finalized_date TIMESTAMP,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cycles_asset ON review_cycles(asset_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cycles_state ON review_cycles(review_state)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cycles_active ON review_cycles(asset_id, end_version)')

        cursor.execute('PRAGMA table_info(review_sessions)')
        existing_columns = {row[1] for row in cursor.fetchall()}

        if 'cycle_id' not in existing_columns:
            cursor.execute('ALTER TABLE review_sessions ADD COLUMN cycle_id INTEGER')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_cycle ON review_sessions(cycle_id)')

        # Migrate existing sessions with review_state to individual cycles
        cursor.execute('''
            SELECT id, asset_uuid, version_label, review_state, submitted_by,
                   submitted_for_review_date, finalized_by, finalized_date
            FROM review_sessions
            WHERE review_state IS NOT NULL
        ''')

        sessions_to_migrate = cursor.fetchall()
        for session in sessions_to_migrate:
            session_id = session[0]
            asset_uuid = session[1]
            version_label = session[2]
            review_state = session[3]
            submitted_by = session[4]
            submitted_date = session[5]
            finalized_by = session[6]
            finalized_date = session[7]

            end_version = version_label if review_state == 'final' else None

            cursor.execute('''
                INSERT INTO review_cycles
                (asset_id, cycle_type, start_version, end_version, review_state,
                 submitted_by, submitted_date, finalized_by, finalized_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (asset_uuid, 'general', version_label, end_version, review_state,
                  submitted_by, submitted_date, finalized_by, finalized_date))

            cycle_id = cursor.lastrowid

            cursor.execute('''
                UPDATE review_sessions SET cycle_id = ? WHERE id = ?
            ''', (cycle_id, session_id))

        self._connection.commit()
        migrated_count = len(sessions_to_migrate)
        logger.info(f"Review database migrated to v4 (review cycles) - {migrated_count} sessions migrated")

    def _migrate_v4_to_v5(self) -> None:
        """Migration v4 -> v5: Add variant support to review cycles."""
        cursor = self._connection.cursor()

        cursor.execute('PRAGMA table_info(review_cycles)')
        existing_columns = {row[1] for row in cursor.fetchall()}

        if 'variant_name' not in existing_columns:
            cursor.execute('''
                ALTER TABLE review_cycles ADD COLUMN variant_name TEXT DEFAULT 'Base'
            ''')

            cursor.execute('''
                UPDATE review_cycles SET variant_name = 'Base' WHERE variant_name IS NULL
            ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cycles_variant
            ON review_cycles(asset_id, variant_name, end_version)
        ''')

        self._connection.commit()
        logger.info("Review database migrated to v5 (variant support for cycles)")


__all__ = ['ReviewSchema']
