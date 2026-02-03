"""
Protocol Schema - The single source of truth for Blender↔Desktop communication.

This module defines:
- FieldDef: Individual field definitions with source mapping and fallbacks
- MessageDef: Message type definitions with their required/optional fields
- IDENTIFIER_FIELDS: Semantic identifier mappings (which UUID to use where)
- MESSAGE_TYPES: All supported message types and their schemas

To add a new message type:
1. Define its fields in MESSAGE_TYPES
2. Both Blender and Desktop will automatically support it

To add a new field to an existing message:
1. Add a Field() entry to the message's fields list
2. Both sides will automatically read/validate it
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict

from .constants import (
    DIRECTION_DESKTOP_TO_BLENDER,
    DIRECTION_BLENDER_TO_DESKTOP,
    DEFAULT_VARIANT_NAME,
    DEFAULT_VERSION_LABEL,
)


@dataclass
class FieldDef:
    """
    Definition of a semantic identifier field.

    Used to document the meaning of different UUIDs and provide
    consistent access across the codebase.
    """
    name: str                           # Field name in JSON message
    source: str                         # Which metadata field to read from
    description: str                    # Human-readable explanation
    fallbacks: List[str] = field(default_factory=list)  # Fallback sources if primary is empty


@dataclass
class Field:
    """
    Definition of a message field.

    Attributes:
        name: Field name in the JSON message
        source: Which metadata key to read from (for build_message)
        required: Whether this field must be present
        default: Default value if not provided and not required
        description: Human-readable explanation
        fallbacks: Alternative source keys to try if primary is empty
    """
    name: str
    source: str
    required: bool = False
    default: Any = None
    description: str = ""
    fallbacks: List[str] = field(default_factory=list)


@dataclass
class MessageDef:
    """
    Definition of a message type.

    Attributes:
        direction: Which way the message flows (desktop_to_blender or blender_to_desktop)
        file_pattern: Glob pattern for queue files (e.g., "screenshot_*.json")
        fields: List of Field definitions for this message type
        description: Human-readable explanation of the message purpose
    """
    direction: str
    file_pattern: str
    fields: List[Field]
    description: str = ""


# =============================================================================
# IDENTIFIER FIELDS - Semantic meanings of different UUIDs
# =============================================================================

IDENTIFIER_FIELDS: Dict[str, FieldDef] = {
    "session_identifier": FieldDef(
        name="asset_uuid",
        source="version_group_id",
        fallbacks=["asset_id", "uuid"],
        description="UUID for review sessions/cycles - uses version_group_id so all versions share review context"
    ),
    "storage_identifier": FieldDef(
        name="asset_id",
        source="asset_id",
        fallbacks=["version_group_id", "uuid"],
        description="UUID for file storage paths - the family UUID shared across variants"
    ),
    "version_identifier": FieldDef(
        name="uuid",
        source="uuid",
        fallbacks=[],
        description="UUID of this specific version - unique per version record"
    ),
    "version_chain": FieldDef(
        name="version_group_id",
        source="version_group_id",
        fallbacks=["asset_id", "uuid"],
        description="UUID linking all versions of the same asset together"
    ),
}


# =============================================================================
# MESSAGE TYPES - All supported Blender↔Desktop messages
# =============================================================================

MESSAGE_TYPES: Dict[str, MessageDef] = {

    # -------------------------------------------------------------------------
    # IMPORT ASSET (Desktop → Blender)
    # -------------------------------------------------------------------------
    "import_asset": MessageDef(
        direction=DIRECTION_DESKTOP_TO_BLENDER,
        file_pattern="import_*.json",
        description="Request to import an asset into Blender scene",
        fields=[
            # Core identifiers
            Field("asset_uuid", source="uuid", required=True,
                  description="UUID of this specific version"),
            Field("version_group_id", source="version_group_id", required=True,
                  fallbacks=["asset_id", "uuid"],
                  description="Version chain UUID"),
            Field("asset_id", source="asset_id", required=True,
                  fallbacks=["version_group_id", "uuid"],
                  description="Family UUID for storage"),

            # Version info
            Field("version", source="version", required=True,
                  description="Version number (integer)"),
            Field("version_label", source="version_label", required=True,
                  default=DEFAULT_VERSION_LABEL,
                  description="Version label string (e.g., 'v001')"),

            # Asset info
            Field("asset_name", source="name", required=True,
                  fallbacks=["asset_name"],
                  description="Human-readable asset name"),
            Field("asset_type", source="asset_type", required=True,
                  description="Asset type (model, material, rig, etc.)"),

            # Variant system
            Field("variant_name", source="variant_name", required=False,
                  default=DEFAULT_VARIANT_NAME,
                  description="Variant identifier"),

            # File paths
            Field("usd_file_path", source="usd_file_path", required=False,
                  description="Path to USD file"),
            Field("blend_file_path", source="blend_file_path", required=False,
                  description="Path to .blend file"),

            # Import options
            Field("import_method", source="import_method", required=False,
                  default="BLEND",
                  description="Import method: BLEND or USD"),
            Field("link_mode", source="link_mode", required=False,
                  default="APPEND",
                  description="Link mode: APPEND or LINK"),
            Field("keep_location", source="keep_location", required=False,
                  default=True,
                  description="Whether to preserve object location"),

            # Pipeline
            Field("representation_type", source="representation_type", required=False,
                  default="none",
                  description="Pipeline representation: none, model, lookdev, rig, final"),
        ]
    ),

    # -------------------------------------------------------------------------
    # REVIEW SCREENSHOT (Blender → Desktop)
    # -------------------------------------------------------------------------
    "review_screenshot": MessageDef(
        direction=DIRECTION_BLENDER_TO_DESKTOP,
        file_pattern="screenshot_*.json",
        description="Screenshot captured in Blender for asset review",
        fields=[
            # Session tracking - uses version_group_id so all versions share review
            Field("asset_uuid", source="version_group_id", required=True,
                  fallbacks=["asset_id", "uuid"],
                  description="UUID for review session (version_group_id)"),

            # Storage path identifiers
            Field("asset_id", source="asset_id", required=True,
                  fallbacks=["version_group_id", "uuid"],
                  description="Family UUID for storage path"),
            Field("variant_name", source="variant_name", required=False,
                  default=DEFAULT_VARIANT_NAME,
                  description="Variant for storage path"),

            # Version info
            Field("version_label", source="version_label", required=True,
                  default=DEFAULT_VERSION_LABEL,
                  description="Version label"),

            # Asset info
            Field("asset_name", source="asset_name", required=True,
                  fallbacks=["name"],
                  description="Asset name for display"),

            # Screenshot details
            Field("display_name", source="display_name", required=False,
                  default="Screenshot",
                  description="Display name for the screenshot"),
            Field("screenshot_path", source="screenshot_path", required=True,
                  description="Path to the captured PNG file"),

            # Source info
            Field("source", source="source", required=False,
                  default="blender",
                  description="Source application"),
            Field("blender_version", source="blender_version", required=False,
                  description="Blender version string"),
        ]
    ),

    # -------------------------------------------------------------------------
    # REGENERATE THUMBNAIL (Desktop → Blender)
    # -------------------------------------------------------------------------
    "regenerate_thumbnail": MessageDef(
        direction=DIRECTION_DESKTOP_TO_BLENDER,
        file_pattern="thumbnail_*.json",
        description="Request to regenerate asset thumbnail in Blender",
        fields=[
            # Core identifiers
            Field("asset_uuid", source="uuid", required=True,
                  description="UUID of the asset"),
            Field("version_group_id", source="version_group_id", required=False,
                  fallbacks=["asset_id", "uuid"],
                  description="Version chain UUID"),
            Field("asset_id", source="asset_id", required=False,
                  fallbacks=["version_group_id", "uuid"],
                  description="Family UUID"),

            # Asset info
            Field("asset_name", source="name", required=True,
                  fallbacks=["asset_name"],
                  description="Asset name"),

            # File paths
            Field("usd_file_path", source="usd_file_path", required=True,
                  description="Path to USD file to render"),
            Field("thumbnail_path", source="thumbnail_path", required=True,
                  description="Path where thumbnail should be saved"),
        ]
    ),
}


def get_message_def(message_type: str) -> Optional[MessageDef]:
    """Get the message definition for a type."""
    return MESSAGE_TYPES.get(message_type)


def get_identifier_field(semantic_name: str) -> Optional[FieldDef]:
    """Get an identifier field definition by semantic name."""
    return IDENTIFIER_FIELDS.get(semantic_name)
