"""
ReviewSettings - App settings and user management.

Handles:
- App settings (studio mode, current user, etc.)
- User management (add, update, deactivate)
- User queries
"""

import sqlite3
from typing import Optional, List, Dict, Any


class ReviewSettings:
    """
    Manages application settings and studio users.

    Supports both "solo" mode (single user) and "studio" mode
    (multiple users with roles).
    """

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to reviews database
        """
        self._connection = connection

    # ==================== APP SETTINGS ====================

    def get_setting(self, key: str, default: str = '') -> str:
        """
        Get an app setting value.

        Args:
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value or default
        """
        cursor = self._connection.cursor()
        cursor.execute('SELECT value FROM app_settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> bool:
        """
        Set an app setting value.

        Args:
            key: Setting key
            value: Setting value

        Returns:
            True if successful
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO app_settings (key, value)
                VALUES (?, ?)
            ''', (key, value))
            self._connection.commit()
            return True
        except Exception as e:
            return False

    def is_studio_mode(self) -> bool:
        """Check if app is in studio mode (multi-user)."""
        return self.get_setting('app_mode', 'solo') == 'studio'

    def set_studio_mode(self, enabled: bool) -> bool:
        """Enable or disable studio mode."""
        return self.set_setting('app_mode', 'studio' if enabled else 'solo')

    def get_current_user(self) -> str:
        """Get current user username."""
        return self.get_setting('current_user', '')

    def set_current_user(self, username: str) -> bool:
        """Set current user."""
        return self.set_setting('current_user', username)

    def get_show_deleted(self) -> bool:
        """Check if deleted notes should be shown."""
        return self.get_setting('show_deleted_notes', 'false') == 'true'

    def set_show_deleted(self, show: bool) -> bool:
        """Set whether to show deleted notes."""
        return self.set_setting('show_deleted_notes', 'true' if show else 'false')

    # ==================== USER MANAGEMENT ====================

    def get_all_users(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Get all studio users.

        Args:
            include_inactive: Include inactive users

        Returns:
            List of user dicts
        """
        cursor = self._connection.cursor()

        if include_inactive:
            cursor.execute('''
                SELECT * FROM studio_users
                ORDER BY display_name ASC
            ''')
        else:
            cursor.execute('''
                SELECT * FROM studio_users
                WHERE is_active = 1
                ORDER BY display_name ASC
            ''')

        return [dict(row) for row in cursor.fetchall()]

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get a user by username.

        Args:
            username: Username to look up

        Returns:
            User dict or None
        """
        cursor = self._connection.cursor()
        cursor.execute('SELECT * FROM studio_users WHERE username = ?', (username,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a user by ID."""
        cursor = self._connection.cursor()
        cursor.execute('SELECT * FROM studio_users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def add_user(
        self,
        username: str,
        display_name: str,
        role: str = 'artist'
    ) -> Optional[int]:
        """
        Add a new studio user.

        Args:
            username: Unique username
            display_name: Display name
            role: User role (artist, lead, admin)

        Returns:
            User ID or None if failed
        """
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                INSERT INTO studio_users (username, display_name, role)
                VALUES (?, ?, ?)
            ''', (username, display_name, role))
            self._connection.commit()
            return cursor.lastrowid
        except Exception as e:
            return None

    def update_user(
        self,
        username: str,
        display_name: Optional[str] = None,
        role: Optional[str] = None
    ) -> bool:
        """
        Update a user's information.

        Args:
            username: Username to update
            display_name: New display name (optional)
            role: New role (optional)

        Returns:
            True if successful
        """
        try:
            cursor = self._connection.cursor()
            updates = []
            params = []

            if display_name is not None:
                updates.append('display_name = ?')
                params.append(display_name)

            if role is not None:
                updates.append('role = ?')
                params.append(role)

            if not updates:
                return True

            params.append(username)
            cursor.execute(f'''
                UPDATE studio_users
                SET {', '.join(updates)}
                WHERE username = ?
            ''', params)
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def deactivate_user(self, username: str) -> bool:
        """Deactivate a user (soft delete)."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                UPDATE studio_users SET is_active = 0
                WHERE username = ?
            ''', (username,))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def reactivate_user(self, username: str) -> bool:
        """Reactivate a deactivated user."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                UPDATE studio_users SET is_active = 1
                WHERE username = ?
            ''', (username,))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False

    def delete_user(self, username: str) -> bool:
        """Permanently delete a user."""
        try:
            cursor = self._connection.cursor()
            cursor.execute('DELETE FROM studio_users WHERE username = ?', (username,))
            self._connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            return False


__all__ = ['ReviewSettings']
