"""Shared AppData path for Universal Library config.

Both the desktop app and Blender addon use the same AppData location
to store config files (library_path.txt, blender_settings.json,
attribution_defaults.json). This module provides helpers so the addon
can read/write the shared config.
"""

import json
import os
import sys
from pathlib import Path

APP_NAME = "UniversalLibrary"
ATTRIBUTION_FILE = "attribution_defaults.json"


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


# ----------------------------------------------------------------------
# M6: Attribution defaults (license / copyright / author)
# ----------------------------------------------------------------------
# The desktop app's Settings → Attribution page is the source of truth.
# The app writes these defaults to attribution_defaults.json on every
# change; the Blender addon reads them at register time + on every
# export-dialog open so they stay in sync without explicit polling.

def read_attribution_defaults() -> dict:
    """Read attribution defaults from the shared AppData JSON file.

    Returns:
        Dict with keys 'license', 'copyright', 'author' (all strings).
        Missing keys default to empty string. Returns all-empty dict if
        the file doesn't exist or is unreadable.
    """
    defaults = {'license': '', 'copyright': '', 'author': ''}
    config = get_appdata_dir() / ATTRIBUTION_FILE
    if not config.exists():
        return defaults
    try:
        with config.open('r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults
        for key in defaults:
            value = data.get(key, '')
            if isinstance(value, str):
                defaults[key] = value
    except (OSError, json.JSONDecodeError):
        pass
    return defaults


def write_attribution_defaults(license_: str, copyright_: str, author: str) -> bool:
    """Write attribution defaults to the shared AppData JSON file.

    Args:
        license_: License code (e.g. 'MIT', 'CC0') or empty string.
        copyright_: Copyright string (e.g. '© 2026 CGstuff') or empty.
        author: Author name or empty.

    Returns:
        True on successful write, False otherwise (caller should not
        treat as fatal — the app keeps its own copy regardless).
    """
    payload = {
        'license': str(license_ or ''),
        'copyright': str(copyright_ or ''),
        'author': str(author or ''),
    }
    config_dir = get_appdata_dir()
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        with (config_dir / ATTRIBUTION_FILE).open('w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        return True
    except OSError:
        return False
