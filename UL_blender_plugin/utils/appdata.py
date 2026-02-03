"""Shared AppData path for Universal Library config.

Both the desktop app and Blender addon use the same AppData location
to store config files (library_path.txt, blender_settings.json).
This module provides helpers so the addon can read/write the shared config.
"""

import os
import sys
from pathlib import Path

APP_NAME = "UniversalLibrary"


def get_appdata_dir() -> Path:
    """Get the OS-specific AppData directory for Universal Library config."""
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base / APP_NAME


def read_library_path() -> str:
    """Read library path from the shared AppData config file.

    Returns:
        The library path string if found and valid, empty string otherwise.
    """
    config = get_appdata_dir() / 'library_path.txt'
    if config.exists():
        try:
            path_str = config.read_text(encoding='utf-8').strip()
            if path_str and Path(path_str).exists():
                return path_str
        except Exception:
            pass
    return ""


def write_library_path(path: str):
    """Write library path to the shared AppData config file."""
    config_dir = get_appdata_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / 'library_path.txt').write_text(str(path), encoding='utf-8')
