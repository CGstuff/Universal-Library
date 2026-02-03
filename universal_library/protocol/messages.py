"""
Protocol Messages - Build and validate messages using the schema.

This module provides:
- build_message(): Create a message from metadata using schema definitions
- validate_message(): Validate a received message against schema
- get_field(): Get a field value using semantic identifier names
"""

from datetime import datetime
from typing import Dict, Any, Optional

from .schema import MESSAGE_TYPES, IDENTIFIER_FIELDS, get_message_def
from .constants import STATUS_PENDING


class ValidationError(Exception):
    """Raised when a message fails validation."""
    pass


def build_message(
    message_type: str,
    metadata: Dict[str, Any],
    extra_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build a message from metadata using schema definitions.

    This function reads from the correct source fields as defined
    in the schema, applies fallbacks, and validates required fields.

    Args:
        message_type: Type of message (e.g., "review_screenshot")
        metadata: Source metadata dict (e.g., from Blender object properties)
        extra_fields: Additional fields to include (e.g., screenshot_path)

    Returns:
        Complete message dict ready to be written as JSON

    Raises:
        ValidationError: If message_type is unknown or required fields are missing

    Example:
        >>> metadata = {"version_group_id": "abc", "version_label": "v001", "asset_name": "Cube"}
        >>> msg = build_message("review_screenshot", metadata)
        >>> msg["asset_uuid"]  # Pulled from version_group_id per schema
        'abc'
    """
    msg_def = get_message_def(message_type)
    if not msg_def:
        raise ValidationError(f"Unknown message type: {message_type}")

    message = {
        "type": message_type,
        "status": STATUS_PENDING,
        "timestamp": datetime.now().isoformat(),
    }

    # Build fields from schema
    missing_required = []
    for field_def in msg_def.fields:
        value = _get_value_with_fallbacks(
            metadata,
            field_def.source,
            field_def.fallbacks
        )

        # Check extra_fields for override
        if extra_fields and field_def.name in extra_fields:
            value = extra_fields[field_def.name]

        # Apply default if no value
        if value is None or value == '':
            if field_def.default is not None:
                value = field_def.default
            elif field_def.required:
                missing_required.append(field_def.name)
                continue

        if value is not None:
            message[field_def.name] = value

    if missing_required:
        raise ValidationError(
            f"Missing required fields for {message_type}: {', '.join(missing_required)}"
        )

    return message


def validate_message(
    data: Dict[str, Any],
    message_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validate a received message against its schema.

    Args:
        data: Raw message dict (e.g., from JSON file)
        message_type: Expected message type (if None, reads from data['type'])

    Returns:
        The validated message dict (same as input if valid)

    Raises:
        ValidationError: If message is invalid

    Example:
        >>> msg = validate_message({"type": "review_screenshot", "asset_uuid": "abc", ...})
    """
    # Determine message type
    msg_type = message_type or data.get("type")
    if not msg_type:
        raise ValidationError("Message missing 'type' field")

    msg_def = get_message_def(msg_type)
    if not msg_def:
        raise ValidationError(f"Unknown message type: {msg_type}")

    # Check required fields
    missing = []
    for field_def in msg_def.fields:
        if field_def.required:
            value = data.get(field_def.name)
            if value is None or value == '':
                # Check if there's a default
                if field_def.default is None:
                    missing.append(field_def.name)

    if missing:
        raise ValidationError(
            f"Message {msg_type} missing required fields: {', '.join(missing)}"
        )

    return data


def get_field(
    message: Dict[str, Any],
    semantic_name: str,
    default: Any = None
) -> Any:
    """
    Get a field value using its semantic identifier name.

    This provides a consistent way to access fields regardless of
    the actual field name in the message. The schema defines the
    mapping from semantic names to actual field names.

    Args:
        message: The message dict
        semantic_name: Semantic identifier name (e.g., "session_identifier")
        default: Default value if not found

    Returns:
        The field value or default

    Semantic names:
        - "session_identifier": UUID for review sessions (asset_uuid from version_group_id)
        - "storage_identifier": UUID for file paths (asset_id)
        - "version_identifier": UUID of specific version (uuid)
        - "version_chain": Version group UUID (version_group_id)

    Example:
        >>> asset_id = get_field(msg, "storage_identifier")  # Gets msg["asset_id"]
    """
    identifier = IDENTIFIER_FIELDS.get(semantic_name)
    if not identifier:
        # Not a semantic name, try as direct field name
        return message.get(semantic_name, default)

    # Get value from the field name defined in the identifier
    value = message.get(identifier.name)
    if value is not None and value != '':
        return value

    # Try fallbacks
    for fallback in identifier.fallbacks:
        value = message.get(fallback)
        if value is not None and value != '':
            return value

    return default


def _get_value_with_fallbacks(
    data: Dict[str, Any],
    source: str,
    fallbacks: list
) -> Any:
    """
    Get a value from data, trying fallbacks if primary is empty.

    Args:
        data: Source dict
        source: Primary key to try
        fallbacks: List of fallback keys

    Returns:
        Value from data or None
    """
    # Try primary source
    value = data.get(source)
    if value is not None and value != '':
        return value

    # Try fallbacks
    for fallback in fallbacks:
        value = data.get(fallback)
        if value is not None and value != '':
            return value

    return None


def get_file_pattern(message_type: str) -> Optional[str]:
    """Get the file pattern for a message type."""
    msg_def = get_message_def(message_type)
    return msg_def.file_pattern if msg_def else None


def get_message_direction(message_type: str) -> Optional[str]:
    """Get the direction for a message type."""
    msg_def = get_message_def(message_type)
    return msg_def.direction if msg_def else None
