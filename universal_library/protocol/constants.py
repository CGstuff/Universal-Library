"""
Protocol constants - shared between Blender and Desktop.

These constants ensure both sides use the same values for
queue directory names, status values, and other shared config.
"""

# Queue directory (in system temp folder)
QUEUE_DIR_NAME = "usd_library_queue"

# Message status values
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Message directions
DIRECTION_DESKTOP_TO_BLENDER = "desktop_to_blender"
DIRECTION_BLENDER_TO_DESKTOP = "blender_to_desktop"

# Default values
DEFAULT_VARIANT_NAME = "Base"
DEFAULT_VERSION_LABEL = "v001"

# File patterns for each message type
FILE_PATTERNS = {
    "import_asset": "import_*.json",
    "review_screenshot": "screenshot_*.json",
    "regenerate_thumbnail": "thumbnail_*.json",
}
