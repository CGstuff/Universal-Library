"""
Configuration constants for version history dialog.
"""

from PyQt6.QtCore import Qt


# Custom data role for thumbnail UUID (separate from selection UUID)
THUMBNAIL_UUID_ROLE = Qt.ItemDataRole.UserRole + 1


class VersionHistoryConfig:
    """Configuration constants for version history dialog."""

    # Sizes
    PREVIEW_SIZE = 280
    THUMBNAIL_SIZE = 32
    MIN_WIDTH = 1000
    MIN_HEIGHT = 600
    SCREEN_RATIO = 0.9

    # Column widths
    COL_VERSION = 80
    COL_VARIANT = 100
    COL_STATUS = 80
    COL_DATE = 120

    # Status colors
    STATUS_COLORS = {
        'approved': '#4CAF50',
        'pending': '#FFC107',
        'rejected': '#F44336',
        'wip': '#2196F3',
    }


__all__ = ['VersionHistoryConfig', 'THUMBNAIL_UUID_ROLE']
