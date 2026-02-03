"""
Protocol - Schema-driven Blender↔Desktop communication.

This module provides a single source of truth for all message types
exchanged between the Blender plugin and Desktop app.

Usage:
    # Building messages (Blender or Desktop)
    from universal_library.protocol import build_message
    msg = build_message("review_screenshot", metadata)

    # Validating received messages
    from universal_library.protocol import validate_message, get_field
    validated = validate_message(raw_data)
    asset_id = get_field(validated, "storage_identifier")
"""

from .schema import (
    MESSAGE_TYPES,
    IDENTIFIER_FIELDS,
    FieldDef,
    MessageDef,
    Field,
)
from .messages import (
    build_message,
    validate_message,
    get_field,
    ValidationError,
)
from .constants import (
    QUEUE_DIR_NAME,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_COMPLETED,
    STATUS_FAILED,
)

__all__ = [
    # Schema
    'MESSAGE_TYPES',
    'IDENTIFIER_FIELDS',
    'FieldDef',
    'MessageDef',
    'Field',
    # Messages
    'build_message',
    'validate_message',
    'get_field',
    'ValidationError',
    # Constants
    'QUEUE_DIR_NAME',
    'STATUS_PENDING',
    'STATUS_PROCESSING',
    'STATUS_COMPLETED',
    'STATUS_FAILED',
]
