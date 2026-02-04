"""
BaseRepository - Base class for repository pattern

Pattern: Repository base with shared database access
Provides thread-local connections and transaction support.
"""

import sqlite3
import threading
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from ..config import Config


class BaseRepository:
    """
    Base repository with shared database infrastructure

    Features:
    - Thread-local connections for thread safety
    - WAL mode for better concurrency
    - Transaction support via context manager
    - Shared across all repositories
    """

    # Class-level shared state
    _db_path: Path = None
    _local = threading.local()
    _initialized = False

    @classmethod
    def initialize(cls, db_path: Optional[Path] = None):
        """Initialize the shared database path"""
        cls._db_path = db_path or Config.get_database_path()
        cls._initialized = True

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not BaseRepository._initialized:
            BaseRepository.initialize()

        if not hasattr(BaseRepository._local, 'connection') or BaseRepository._local.connection is None:
            # Thread-local connections ensure thread safety without needing check_same_thread=False
            # isolation_level=None enables autocommit so readers always see latest committed data
            # (critical for seeing changes made by external processes like Blender addon)
            BaseRepository._local.connection = sqlite3.connect(
                str(BaseRepository._db_path),
                timeout=30.0,
                isolation_level=None
            )
            BaseRepository._local.connection.execute("PRAGMA foreign_keys = ON")
            BaseRepository._local.connection.execute("PRAGMA journal_mode = WAL")
            BaseRepository._local.connection.row_factory = sqlite3.Row

        return BaseRepository._local.connection

    @contextmanager
    def _transaction(self):
        """Context manager for database transactions"""
        conn = self._get_connection()
        conn.execute("BEGIN")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e

    def close(self):
        """Close database connection for current thread"""
        if hasattr(BaseRepository._local, 'connection') and BaseRepository._local.connection:
            BaseRepository._local.connection.close()
            BaseRepository._local.connection = None


__all__ = ['BaseRepository']
