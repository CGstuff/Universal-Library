"""
Protocol Loader - Dynamically loads protocol from library/.schema/protocol/

This allows the Blender addon to use the same protocol schema as the desktop app
without needing a bundled copy that could get out of sync.
"""

import sys
import importlib.util
from pathlib import Path
from typing import Optional, Any

from .constants import STATUS_PENDING

# Cache for loaded protocol module
_protocol_module = None
_protocol_load_attempted = False


def get_library_path() -> Optional[Path]:
    """Get the library path from the connection."""
    try:
        from .library_connection import get_library_connection
        conn = get_library_connection()
        return conn.library_path if conn else None
    except Exception:
        return None


def get_protocol_path() -> Optional[Path]:
    """Get the path to the protocol directory in the library."""
    library_path = get_library_path()
    if not library_path:
        return None

    protocol_path = library_path / '.schema' / 'protocol'
    if protocol_path.exists():
        return protocol_path

    return None


def load_protocol() -> Optional[Any]:
    """
    Load the protocol module from library/.schema/protocol/

    Returns:
        The protocol module, or None if not available
    """
    global _protocol_module, _protocol_load_attempted

    # Return cached module if already loaded
    if _protocol_module is not None:
        return _protocol_module

    # Don't retry if we already failed
    if _protocol_load_attempted:
        return None

    _protocol_load_attempted = True

    protocol_path = get_protocol_path()
    if not protocol_path:
        return None

    try:
        # Add protocol path to sys.path temporarily
        protocol_parent = str(protocol_path.parent)
        if protocol_parent not in sys.path:
            sys.path.insert(0, protocol_parent)

        # Load the protocol __init__.py
        init_path = protocol_path / '__init__.py'
        if not init_path.exists():
            return None

        spec = importlib.util.spec_from_file_location("protocol", init_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules['universal_library_protocol'] = module
        spec.loader.exec_module(module)

        _protocol_module = module
        return module

    except Exception as e:
        return None


def get_protocol_function(name: str) -> Optional[Any]:
    """
    Get a specific function/class from the protocol module.

    Args:
        name: Name of the function/class to get (e.g., 'validate_message')

    Returns:
        The function/class, or None if not available
    """
    protocol = load_protocol()
    if protocol is None:
        return None

    return getattr(protocol, name, None)


# Convenience functions that try protocol first, return None if unavailable
def validate_message(message: dict, message_type: str = None):
    """Validate a message using the protocol schema."""
    func = get_protocol_function('validate_message')
    if func:
        return func(message, message_type)
    return True, None  # No validation if protocol unavailable


def build_message(message_type: str, data: dict, extra_fields: dict = None):
    """Build a message using the protocol schema."""
    func = get_protocol_function('build_message')
    if func:
        return func(message_type, data, extra_fields)
    # Fallback: just add type to data with required fields
    # Also map semantic fields that the protocol expects
    from datetime import datetime
    result = {
        'type': message_type,
        'status': STATUS_PENDING,
        'timestamp': datetime.now().isoformat(),
        'source': 'blender',
        # Map semantic identifiers (protocol expects these names)
        'asset_uuid': data.get('version_group_id') or data.get('asset_id') or data.get('uuid'),
        **data
    }
    if extra_fields:
        result.update(extra_fields)
    return result


# Constants - try to get from protocol, fall back to defaults
def get_constant(name: str, default: Any) -> Any:
    """Get a constant from the protocol, with fallback."""
    protocol = load_protocol()
    if protocol:
        return getattr(protocol, name, default)
    return default


def reload_protocol():
    """Force reload of protocol (call when library path changes)."""
    global _protocol_module, _protocol_load_attempted
    _protocol_module = None
    _protocol_load_attempted = False


__all__ = [
    'load_protocol',
    'get_protocol_function',
    'validate_message',
    'build_message',
    'get_constant',
    'reload_protocol',
    'get_protocol_path',
]
