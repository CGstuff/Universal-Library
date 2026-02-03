"""
Input validation utilities for Universal Library

Provides validation functions for asset data and other inputs
before database operations.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Valid asset types in the system
VALID_ASSET_TYPES = frozenset([
    'mesh', 'material', 'rig', 'light', 'camera', 'collection',
    'grease_pencil', 'curve', 'scene', 'other'
])

# Valid asset statuses
VALID_STATUSES = frozenset([
    'none', 'wip', 'review', 'approved', 'deprecated', 'archived'
])

# Required fields for asset creation
REQUIRED_ASSET_FIELDS = frozenset(['name', 'asset_type', 'folder_id'])

# Maximum field lengths
MAX_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 10000
MAX_PATH_LENGTH = 4096


def validate_asset_data(data: Dict[str, Any], is_update: bool = False) -> Dict[str, Any]:
    """
    Validate asset data before database insert/update.

    Args:
        data: Asset data dictionary
        is_update: If True, required fields are optional (for partial updates)

    Returns:
        Validated and sanitized data dictionary

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(data, dict):
        raise ValidationError("Asset data must be a dictionary")

    validated = {}
    errors = []

    # Check required fields (only for inserts)
    if not is_update:
        for field in REQUIRED_ASSET_FIELDS:
            if field not in data or data[field] is None:
                errors.append(f"Required field '{field}' is missing")

    # Validate name
    if 'name' in data:
        name = data['name']
        if name is not None:
            name = validate_asset_name(name)
            validated['name'] = name

    # Validate asset_type
    if 'asset_type' in data:
        asset_type = data['asset_type']
        if asset_type is not None:
            if asset_type not in VALID_ASSET_TYPES:
                errors.append(
                    f"Invalid asset_type '{asset_type}'. "
                    f"Must be one of: {', '.join(sorted(VALID_ASSET_TYPES))}"
                )
            else:
                validated['asset_type'] = asset_type

    # Validate folder_id
    if 'folder_id' in data:
        folder_id = data['folder_id']
        if folder_id is not None:
            if not isinstance(folder_id, int) or folder_id < 1:
                errors.append(f"folder_id must be a positive integer, got: {folder_id}")
            else:
                validated['folder_id'] = folder_id

    # Validate status
    if 'status' in data:
        status = data['status']
        if status is not None:
            if status not in VALID_STATUSES:
                errors.append(
                    f"Invalid status '{status}'. "
                    f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
                )
            else:
                validated['status'] = status

    # Validate description
    if 'description' in data:
        desc = data['description']
        if desc is not None:
            if len(str(desc)) > MAX_DESCRIPTION_LENGTH:
                errors.append(
                    f"Description exceeds maximum length of {MAX_DESCRIPTION_LENGTH}"
                )
            else:
                validated['description'] = str(desc)

    # Validate UUID format
    if 'uuid' in data:
        uuid_val = data['uuid']
        if uuid_val is not None:
            if not validate_uuid_format(uuid_val):
                errors.append(f"Invalid UUID format: {uuid_val}")
            else:
                validated['uuid'] = uuid_val

    # Validate version_group_id format
    if 'version_group_id' in data:
        vg_id = data['version_group_id']
        if vg_id is not None:
            if not validate_uuid_format(vg_id):
                errors.append(f"Invalid version_group_id format: {vg_id}")
            else:
                validated['version_group_id'] = vg_id

    # Validate file paths
    for path_field in ['usd_file_path', 'blend_backup_path', 'thumbnail_path']:
        if path_field in data:
            path_val = data[path_field]
            if path_val is not None:
                path_val = str(path_val)
                if len(path_val) > MAX_PATH_LENGTH:
                    errors.append(f"{path_field} exceeds maximum length")
                else:
                    validated[path_field] = path_val

    # Validate numeric fields
    numeric_fields = [
        'version', 'polygon_count', 'material_count', 'bone_count',
        'control_count', 'frame_start', 'frame_end', 'mesh_count',
        'camera_count', 'armature_count', 'custom_order'
    ]
    for field in numeric_fields:
        if field in data:
            val = data[field]
            if val is not None:
                try:
                    validated[field] = int(val)
                except (TypeError, ValueError):
                    errors.append(f"{field} must be an integer, got: {val}")

    # Validate float fields
    float_fields = ['file_size_mb', 'frame_rate', 'focal_length']
    for field in float_fields:
        if field in data:
            val = data[field]
            if val is not None:
                try:
                    validated[field] = float(val)
                except (TypeError, ValueError):
                    errors.append(f"{field} must be a number, got: {val}")

    # Validate boolean fields
    bool_fields = [
        'is_favorite', 'is_locked', 'is_latest', 'is_cold', 'is_immutable',
        'has_materials', 'has_skeleton', 'has_animations', 'has_facial_rig',
        'is_loop', 'has_nested_collections'
    ]
    for field in bool_fields:
        if field in data:
            val = data[field]
            if val is not None:
                # Accept int (0/1) or bool
                validated[field] = 1 if val else 0

    # Copy through any other fields that weren't validated
    for key, value in data.items():
        if key not in validated:
            validated[key] = value

    # Raise combined error if any validation failed
    if errors:
        raise ValidationError(
            f"Asset validation failed: {'; '.join(errors)}",
            field='multiple' if len(errors) > 1 else None
        )

    return validated


def validate_asset_name(name: str) -> str:
    """
    Validate and sanitize an asset name.

    Args:
        name: Asset name to validate

    Returns:
        Sanitized name

    Raises:
        ValidationError: If name is invalid
    """
    if not name:
        raise ValidationError("Asset name cannot be empty", field='name')

    name = str(name).strip()

    if not name:
        raise ValidationError("Asset name cannot be blank", field='name')

    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(
            f"Asset name exceeds maximum length of {MAX_NAME_LENGTH}",
            field='name',
            value=name[:50] + '...'
        )

    # Sanitize: remove invalid filesystem characters
    # These characters are invalid on Windows: < > : " / \ | ? *
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    sanitized = sanitized.strip(' .')  # Remove leading/trailing spaces and dots
    sanitized = re.sub(r'_+', '_', sanitized)  # Collapse multiple underscores

    if not sanitized:
        raise ValidationError(
            "Asset name contains only invalid characters",
            field='name',
            value=name
        )

    return sanitized


def validate_uuid_format(uuid_str: str) -> bool:
    """
    Validate UUID format (accepts both standard and simple formats).

    Args:
        uuid_str: String to validate as UUID

    Returns:
        True if valid UUID format, False otherwise
    """
    if not uuid_str or not isinstance(uuid_str, str):
        return False

    # Standard UUID format: 8-4-4-4-12 hex digits
    standard_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    # Simple format: 32 hex digits
    simple_pattern = r'^[0-9a-fA-F]{32}$'

    return bool(re.match(standard_pattern, uuid_str) or re.match(simple_pattern, uuid_str))


def validate_folder_path(path: str) -> str:
    """
    Validate a folder path string.

    Args:
        path: Folder path to validate

    Returns:
        Validated path

    Raises:
        ValidationError: If path is invalid
    """
    if path is None:
        return ""

    path = str(path).strip()

    # Check for path traversal attempts
    if '..' in path:
        raise ValidationError(
            "Path cannot contain '..'",
            field='path',
            value=path
        )

    # Normalize separators
    path = path.replace('\\', '/')

    # Remove leading/trailing slashes for consistency
    path = path.strip('/')

    return path


def validate_tag_name(name: str) -> str:
    """
    Validate and sanitize a tag name.

    Args:
        name: Tag name to validate

    Returns:
        Sanitized tag name

    Raises:
        ValidationError: If name is invalid
    """
    if not name:
        raise ValidationError("Tag name cannot be empty", field='name')

    name = str(name).strip()

    if not name:
        raise ValidationError("Tag name cannot be blank", field='name')

    if len(name) > 100:
        raise ValidationError(
            "Tag name exceeds maximum length of 100",
            field='name'
        )

    # Tags can contain letters, numbers, spaces, hyphens, underscores
    if not re.match(r'^[\w\s\-]+$', name, re.UNICODE):
        raise ValidationError(
            "Tag name contains invalid characters",
            field='name',
            value=name
        )

    return name


def validate_color_hex(color: str) -> str:
    """
    Validate a hex color string.

    Args:
        color: Color string to validate (e.g., '#FF0000' or 'FF0000')

    Returns:
        Normalized color string with # prefix

    Raises:
        ValidationError: If color is invalid
    """
    if not color:
        raise ValidationError("Color cannot be empty", field='color')

    color = str(color).strip()

    # Add # prefix if missing
    if not color.startswith('#'):
        color = '#' + color

    # Validate format
    if not re.match(r'^#[0-9a-fA-F]{6}$', color):
        raise ValidationError(
            "Color must be a valid 6-digit hex color (e.g., #FF0000)",
            field='color',
            value=color
        )

    return color.upper()


__all__ = [
    'validate_asset_data',
    'validate_asset_name',
    'validate_uuid_format',
    'validate_folder_path',
    'validate_tag_name',
    'validate_color_hex',
    'VALID_ASSET_TYPES',
    'VALID_STATUSES',
    'REQUIRED_ASSET_FIELDS',
]
