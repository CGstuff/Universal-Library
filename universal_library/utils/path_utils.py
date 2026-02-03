"""
Path utilities for Universal Library

Consistent path handling across OS.
"""

import os
from pathlib import Path
from typing import Union, Optional


def normalize_path(path: Union[str, Path]) -> Path:
    """
    Normalize a path for consistent handling across OS.

    - Resolves to absolute path
    - Handles both forward and backslashes
    - Expands user (~) and env vars

    Args:
        path: Path string or Path object

    Returns:
        Normalized Path object
    """
    if isinstance(path, str):
        path = os.path.expanduser(path)
        path = os.path.expandvars(path)
    return Path(path).resolve()


def safe_relative_path(path: Union[str, Path], base: Union[str, Path]) -> Optional[Path]:
    """
    Get relative path safely, returns None if not relative to base.

    Args:
        path: Path to make relative
        base: Base path to be relative to

    Returns:
        Relative Path or None if not under base
    """
    try:
        path = normalize_path(path)
        base = normalize_path(base)
        return path.relative_to(base)
    except ValueError:
        return None


def ensure_parent_exists(path: Union[str, Path]) -> Path:
    """
    Ensure parent directory exists, create if needed.

    Args:
        path: File path whose parent should exist

    Returns:
        The original path as Path object
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def is_valid_filename(name: str) -> bool:
    """
    Check if a string is a valid filename (no path separators or illegal chars).

    Args:
        name: Filename to validate

    Returns:
        True if valid filename
    """
    if not name or name in ('.', '..'):
        return False

    # Windows illegal characters
    illegal_chars = '<>:"/\\|?*'
    for char in illegal_chars:
        if char in name:
            return False

    # Control characters
    if any(ord(c) < 32 for c in name):
        return False

    return True


__all__ = [
    'normalize_path',
    'safe_relative_path',
    'ensure_parent_exists',
    'is_valid_filename',
]
