"""
Permission checks for review notes.
"""

from typing import Dict

from ....config import Config


def is_elevated_role(role: str) -> bool:
    """Check if role is elevated (lead/supervisor/admin)."""
    return role in Config.ELEVATED_ROLES


def can_edit(
    note_data: Dict,
    is_studio_mode: bool,
    current_user: str,
    current_user_role: str
) -> bool:
    """
    Check if current user can edit a note.

    Args:
        note_data: Note dictionary with 'author' field
        is_studio_mode: Whether studio mode is enabled
        current_user: Current user's username
        current_user_role: Current user's role

    Returns:
        True if user can edit the note
    """
    if not is_studio_mode:
        return True
    if current_user_role in ['admin', 'supervisor', 'lead']:
        return True
    return note_data.get('author', '') == current_user


def can_delete(
    note_data: Dict,
    is_studio_mode: bool,
    current_user: str,
    current_user_role: str
) -> bool:
    """
    Check if current user can delete a note.

    Args:
        note_data: Note dictionary with 'author' field
        is_studio_mode: Whether studio mode is enabled
        current_user: Current user's username
        current_user_role: Current user's role

    Returns:
        True if user can delete the note
    """
    if not is_studio_mode:
        return True
    if current_user_role in ['admin', 'supervisor', 'lead']:
        return True
    return note_data.get('author', '') == current_user


def can_restore(is_studio_mode: bool, current_user_role: str) -> bool:
    """
    Check if current user can restore deleted notes.

    Args:
        is_studio_mode: Whether studio mode is enabled
        current_user_role: Current user's role

    Returns:
        True if user can restore deleted notes
    """
    if not is_studio_mode:
        return True
    return current_user_role in ['admin', 'supervisor', 'lead']


__all__ = [
    'is_elevated_role',
    'can_edit',
    'can_delete',
    'can_restore',
]
