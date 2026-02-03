"""
Constants for UL Blender plugin.

These constants mirror universal_library/protocol/constants.py and
universal_library/config.py to ensure consistency between the
Blender plugin and desktop app.

IMPORTANT: Keep these in sync with the desktop app constants!
"""

# =============================================================================
# QUEUE CONSTANTS (from protocol/constants.py)
# =============================================================================

# Queue directory name (in system temp folder)
QUEUE_DIR_NAME = "usd_library_queue"

# Message status values
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Message directions
DIRECTION_DESKTOP_TO_BLENDER = "desktop_to_blender"
DIRECTION_BLENDER_TO_DESKTOP = "blender_to_desktop"

# File patterns for each message type
FILE_PATTERNS = {
    "import_asset": "import_*.json",
    "review_screenshot": "screenshot_*.json",
    "regenerate_thumbnail": "thumbnail_*.json",
}


# =============================================================================
# DEFAULT VALUES (from protocol/constants.py)
# =============================================================================

DEFAULT_VARIANT_NAME = "Base"
DEFAULT_VERSION_LABEL = "v001"


# =============================================================================
# FOLDER STRUCTURE (from config.py)
# =============================================================================

# Storage folder names
META_FOLDER = ".meta"
LIBRARY_FOLDER = "library"
ARCHIVE_FOLDER = "_archive"
REVIEWS_FOLDER = "reviews"
CACHE_FOLDER = "cache"

# Database name
DATABASE_NAME = "database.db"


# =============================================================================
# ASSET TYPE FOLDERS (from config.py)
# =============================================================================

ASSET_TYPE_FOLDERS = {
    # Current types
    'mesh': 'meshes',
    'material': 'materials',
    'rig': 'rigs',
    'light': 'lights',
    'camera': 'cameras',
    'collection': 'collections',
    'grease_pencil': 'grease_pencils',
    'curve': 'curves',
    'scene': 'scenes',
    # Future types (add as needed)
    'texture': 'textures',
    'geonode': 'geonodes',
    'shader': 'shaders',
    'hdri': 'hdris',
    'preset': 'presets',
    # Fallback
    'other': 'other',
}


def get_type_folder(asset_type: str) -> str:
    """
    Get folder name for asset type.

    Args:
        asset_type: Asset type string (mesh, material, rig, etc.)

    Returns:
        Folder name string. Returns 'other' for unknown types.
    """
    return ASSET_TYPE_FOLDERS.get(asset_type, 'other')


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Queue
    'QUEUE_DIR_NAME',
    'STATUS_PENDING',
    'STATUS_PROCESSING',
    'STATUS_COMPLETED',
    'STATUS_FAILED',
    'DIRECTION_DESKTOP_TO_BLENDER',
    'DIRECTION_BLENDER_TO_DESKTOP',
    'FILE_PATTERNS',
    # Defaults
    'DEFAULT_VARIANT_NAME',
    'DEFAULT_VERSION_LABEL',
    # Folders
    'META_FOLDER',
    'LIBRARY_FOLDER',
    'ARCHIVE_FOLDER',
    'REVIEWS_FOLDER',
    'CACHE_FOLDER',
    'DATABASE_NAME',
    # Asset types
    'ASSET_TYPE_FOLDERS',
    'get_type_folder',
]
