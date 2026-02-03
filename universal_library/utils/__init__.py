"""
Utility functions for Universal Library

Helper utilities for image processing, logging, decorators, path handling.
"""

from .image_utils import (
    load_image_as_pixmap,
    load_image_as_qimage,
    get_image_size,
    scale_image,
    scale_and_crop_image,
)
from .logging_config import LoggingConfig
from .decorators import timed, timed_info, safe_db_operation, transactional, validate_not_none
from .path_utils import (
    normalize_path,
    safe_relative_path,
    ensure_parent_exists,
    is_valid_filename,
)
from .validators import (
    validate_asset_data,
    validate_asset_name,
    validate_uuid_format,
    validate_folder_path,
    validate_tag_name,
    validate_color_hex,
    VALID_ASSET_TYPES,
    VALID_STATUSES,
)

__all__ = [
    # Image utilities
    'load_image_as_pixmap',
    'load_image_as_qimage',
    'get_image_size',
    'scale_image',
    'scale_and_crop_image',
    # Logging
    'LoggingConfig',
    # Decorators
    'timed',
    'timed_info',
    'safe_db_operation',
    'transactional',
    'validate_not_none',
    # Path utilities
    'normalize_path',
    'safe_relative_path',
    'ensure_parent_exists',
    'is_valid_filename',
    # Validators
    'validate_asset_data',
    'validate_asset_name',
    'validate_uuid_format',
    'validate_folder_path',
    'validate_tag_name',
    'validate_color_hex',
    'VALID_ASSET_TYPES',
    'VALID_STATUSES',
]
