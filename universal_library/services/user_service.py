"""
User Service - Manages current user and role for review workflow

Provides:
- Current user tracking (username, display_name, role)
- Solo mode vs Studio mode support
- User settings persistence
- Integration with review_database for user management
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from .review_database import get_review_database


# Singleton instance
_user_service_instance = None


def get_user_service() -> 'UserService':
    """Get the singleton UserService instance."""
    global _user_service_instance
    if _user_service_instance is None:
        _user_service_instance = UserService()
    return _user_service_instance


class UserService(QObject):
    """
    Service for managing current user and authentication mode.

    In Solo Mode:
    - Single default user with all permissions
    - No login required

    In Studio Mode:
    - Multiple users with different roles
    - Role-based permissions enforced

    Signals:
        user_changed(str, str, str): username, display_name, role
        mode_changed(bool): is_studio_mode
    """

    user_changed = pyqtSignal(str, str, str)  # username, display_name, role
    mode_changed = pyqtSignal(bool)  # is_studio_mode

    # Settings file location
    SETTINGS_FILE = Path.home() / ".universal_library" / "user_settings.json"

    # Default user for solo mode
    DEFAULT_USER = {
        'username': 'solo_user',
        'display_name': 'Artist',
        'role': 'admin'  # Full permissions in solo mode
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._review_db = get_review_database()

        # Current state
        self._is_studio_mode = False
        self._current_user: Optional[Dict] = None

        # Load saved settings
        self._load_settings()

    def _load_settings(self):
        """Load user settings from file."""
        try:
            if self.SETTINGS_FILE.exists():
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                self._is_studio_mode = settings.get('is_studio_mode', False)

                if self._is_studio_mode:
                    # Try to load saved user
                    saved_username = settings.get('current_username')
                    if saved_username:
                        user = self._review_db.get_user(saved_username)
                        if user:
                            self._current_user = user
                        else:
                            # User no longer exists, fall back to solo
                            self._is_studio_mode = False
                            self._current_user = self.DEFAULT_USER.copy()
                    else:
                        self._current_user = None
                else:
                    self._current_user = self.DEFAULT_USER.copy()
            else:
                # No settings, use defaults
                self._current_user = self.DEFAULT_USER.copy()
        except Exception as e:
            self._current_user = self.DEFAULT_USER.copy()

    def _save_settings(self):
        """Save user settings to file."""
        try:
            self.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

            settings = {
                'is_studio_mode': self._is_studio_mode,
                'current_username': self._current_user.get('username') if self._current_user else None
            }

            with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            pass

    # ==================== Public API ====================

    def is_studio_mode(self) -> bool:
        """Check if studio mode is enabled."""
        return self._is_studio_mode

    def set_studio_mode(self, enabled: bool):
        """Enable or disable studio mode."""
        if enabled != self._is_studio_mode:
            self._is_studio_mode = enabled

            if not enabled:
                # Switch to solo mode - use default user
                self._current_user = self.DEFAULT_USER.copy()
            else:
                # Switch to studio mode - clear current user until login
                self._current_user = None

            self._save_settings()
            self.mode_changed.emit(enabled)

            if self._current_user:
                self.user_changed.emit(
                    self._current_user.get('username', ''),
                    self._current_user.get('display_name', ''),
                    self._current_user.get('role', 'artist')
                )

    def get_current_user(self) -> Optional[Dict]:
        """Get the current user info."""
        return self._current_user

    def get_current_username(self) -> str:
        """Get the current username."""
        if self._current_user:
            return self._current_user.get('username', '')
        return ''

    def get_current_display_name(self) -> str:
        """Get the current user's display name."""
        if self._current_user:
            return self._current_user.get('display_name', '')
        return ''

    def get_current_role(self) -> str:
        """Get the current user's role."""
        if self._current_user:
            return self._current_user.get('role', 'artist')
        return 'artist'

    def set_current_user(self, username: str) -> Tuple[bool, str]:
        """
        Set the current user by username.

        Args:
            username: The username to switch to

        Returns:
            Tuple of (success, message)
        """
        if not self._is_studio_mode:
            return False, "Cannot change user in solo mode"

        user = self._review_db.get_user(username)
        if not user:
            return False, f"User '{username}' not found"

        if not user.get('is_active', True):
            return False, f"User '{username}' is inactive"

        self._current_user = user
        self._save_settings()

        self.user_changed.emit(
            user.get('username', ''),
            user.get('display_name', ''),
            user.get('role', 'artist')
        )

        return True, f"Switched to user: {user.get('display_name', username)}"

    def logout(self):
        """Log out the current user (studio mode only)."""
        if self._is_studio_mode:
            self._current_user = None
            self._save_settings()
            self.user_changed.emit('', '', 'artist')

    def is_logged_in(self) -> bool:
        """Check if a user is currently logged in."""
        return self._current_user is not None

    def has_permission(self, required_role: str) -> bool:
        """
        Check if current user has permission for a role-restricted action.

        In solo mode, always returns True (full permissions).
        In studio mode, checks against role hierarchy.
        """
        if not self._is_studio_mode:
            return True  # Solo mode has all permissions

        if not self._current_user:
            return False  # Not logged in

        current_role = self._current_user.get('role', 'artist')
        return self._check_role_permission(current_role, required_role)

    def _check_role_permission(self, user_role: str, required_role: str) -> bool:
        """Check if user_role has permission for required_role."""
        # Role hierarchy (higher can do everything lower can)
        role_hierarchy = {
            'admin': 4,
            'director': 4,
            'supervisor': 3,
            'lead': 2,
            'artist': 1
        }

        user_level = role_hierarchy.get(user_role, 1)
        required_level = role_hierarchy.get(required_role, 1)

        return user_level >= required_level

    # ==================== User Management ====================

    def get_all_users(self, include_inactive: bool = False) -> List[Dict]:
        """Get all studio users."""
        return self._review_db.get_all_users(include_inactive=include_inactive)

    def create_user(self, username: str, display_name: str, role: str = 'artist') -> Tuple[bool, str]:
        """Create a new studio user."""
        if not self._is_studio_mode:
            return False, "Cannot create users in solo mode"

        # Check if current user has admin permission
        if not self.has_permission('admin'):
            return False, "Only administrators can create users"

        success = self._review_db.add_user(username, display_name, role)
        if success:
            return True, f"User '{display_name}' created successfully"
        return False, f"Failed to create user (username may already exist)"

    def update_user(self, username: str, display_name: str = None, role: str = None, is_active: bool = None) -> Tuple[bool, str]:
        """Update a studio user."""
        if not self._is_studio_mode:
            return False, "Cannot update users in solo mode"

        if not self.has_permission('admin'):
            return False, "Only administrators can update users"

        # Handle is_active separately since review_db.update_user doesn't support it
        if is_active is not None:
            if is_active:
                self._review_db.reactivate_user(username)
            else:
                self._review_db.deactivate_user(username)

        # Update other fields if provided
        success = True
        if display_name is not None or role is not None:
            success = self._review_db.update_user(username, display_name, role)

        if success:
            # If updating current user, refresh
            if self._current_user and self._current_user.get('username') == username:
                user = self._review_db.get_user(username)
                if user:
                    self._current_user = user
                    self.user_changed.emit(
                        user.get('username', ''),
                        user.get('display_name', ''),
                        user.get('role', 'artist')
                    )
            return True, "User updated successfully"
        return False, "Failed to update user"

    def delete_user(self, username: str) -> Tuple[bool, str]:
        """Delete (deactivate) a studio user."""
        if not self._is_studio_mode:
            return False, "Cannot delete users in solo mode"

        if not self.has_permission('admin'):
            return False, "Only administrators can delete users"

        # Prevent deleting self
        if self._current_user and self._current_user.get('username') == username:
            return False, "Cannot delete your own account"

        success = self._review_db.deactivate_user(username)
        if success:
            return True, "User deactivated successfully"
        return False, "Failed to deactivate user"


__all__ = ['UserService', 'get_user_service']
