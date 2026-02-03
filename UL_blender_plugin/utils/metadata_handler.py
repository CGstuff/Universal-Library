"""
UAL Metadata Handler

Manages UAL custom properties on Blender objects for version tracking.
"""

from typing import Dict, Any, Optional, List
import bpy


# Property key constants
UAL_UUID = "ual_uuid"
UAL_VERSION_GROUP_ID = "ual_version_group_id"
UAL_VERSION = "ual_version"
UAL_VERSION_LABEL = "ual_version_label"
UAL_ASSET_NAME = "ual_asset_name"
UAL_ASSET_TYPE = "ual_asset_type"
UAL_REPRESENTATION_TYPE = "ual_representation_type"
UAL_IMPORTED = "ual_imported"
# Variant system properties
UAL_ASSET_ID = "ual_asset_id"  # Shared identity across all variants
UAL_VARIANT_NAME = "ual_variant_name"  # Variant identifier (e.g., 'Base', 'Heavy_Armor')
# Import mode tracking
UAL_LINK_MODE = "ual_link_mode"  # How the object was imported (APPEND, LINK, INSTANCE)


def store_ual_metadata(
    obj: bpy.types.Object,
    uuid: str,
    version_group_id: str,
    version: int,
    version_label: str,
    asset_name: str,
    asset_type: str = "model",
    representation_type: str = "none",
    imported: bool = True,
    asset_id: str = "",
    variant_name: str = "Base",
    link_mode: str = "APPEND"
) -> None:
    """
    Store UAL tracking properties on a Blender object.

    Args:
        obj: Blender object to store metadata on
        uuid: Asset UUID
        version_group_id: Version group identifier
        version: Version number
        version_label: Version label (e.g., "v001")
        asset_name: Name of the asset
        asset_type: Type of asset (model, rig, material, etc.)
        representation_type: Pipeline representation (none, model, lookdev, rig, final)
        imported: Whether this object was imported from library
        asset_id: Shared identity UUID across all variants
        variant_name: Variant identifier (e.g., 'Base', 'Heavy_Armor')
        link_mode: How the object was imported (APPEND, LINK, INSTANCE)
    """
    obj[UAL_UUID] = uuid
    obj[UAL_VERSION_GROUP_ID] = version_group_id
    obj[UAL_VERSION] = version
    obj[UAL_VERSION_LABEL] = version_label
    obj[UAL_ASSET_NAME] = asset_name
    obj[UAL_ASSET_TYPE] = asset_type
    obj[UAL_REPRESENTATION_TYPE] = representation_type
    obj[UAL_IMPORTED] = imported
    # Variant system - use version_group_id as asset_id if not provided
    obj[UAL_ASSET_ID] = asset_id or version_group_id
    obj[UAL_VARIANT_NAME] = variant_name
    obj[UAL_LINK_MODE] = link_mode


def store_ual_metadata_from_dict(obj: bpy.types.Object, asset_data: Dict[str, Any]) -> None:
    """
    Store UAL tracking properties from a dictionary.

    Args:
        obj: Blender object to store metadata on
        asset_data: Dictionary containing asset metadata
    """
    version_group_id = asset_data.get('version_group_id', asset_data.get('uuid', ''))
    store_ual_metadata(
        obj,
        uuid=asset_data.get('uuid', asset_data.get('asset_uuid', '')),
        version_group_id=version_group_id,
        version=asset_data.get('version', 1),
        version_label=asset_data.get('version_label', 'v001'),
        asset_name=asset_data.get('name', asset_data.get('asset_name', '')),
        asset_type=asset_data.get('asset_type', 'model'),
        representation_type=asset_data.get('representation_type', 'none'),
        imported=True,
        asset_id=asset_data.get('asset_id', version_group_id),
        variant_name=asset_data.get('variant_name', 'Base'),
        link_mode=asset_data.get('link_mode', 'APPEND')
    )


def read_ual_metadata(obj: bpy.types.Object) -> Optional[Dict[str, Any]]:
    """
    Read UAL tracking properties from a Blender object.

    Args:
        obj: Blender object to read metadata from

    Returns:
        Dictionary of metadata or None if object has no UAL metadata
    """
    if UAL_UUID not in obj:
        return None

    version_group_id = obj.get(UAL_VERSION_GROUP_ID, '')
    return {
        'uuid': obj.get(UAL_UUID, ''),
        'version_group_id': version_group_id,
        'version': obj.get(UAL_VERSION, 1),
        'version_label': obj.get(UAL_VERSION_LABEL, 'v001'),
        'asset_name': obj.get(UAL_ASSET_NAME, ''),
        'asset_type': obj.get(UAL_ASSET_TYPE, 'model'),
        'representation_type': obj.get(UAL_REPRESENTATION_TYPE, 'none'),
        'imported': obj.get(UAL_IMPORTED, False),
        # Variant system - fallback to version_group_id for legacy objects
        'asset_id': obj.get(UAL_ASSET_ID, version_group_id),
        'variant_name': obj.get(UAL_VARIANT_NAME, 'Base'),
        'link_mode': obj.get(UAL_LINK_MODE, ''),
    }


def has_ual_metadata(obj: bpy.types.Object) -> bool:
    """
    Check if an object has UAL metadata.

    Args:
        obj: Blender object to check

    Returns:
        True if object has UAL metadata
    """
    return UAL_UUID in obj


def clear_ual_metadata(obj: bpy.types.Object) -> None:
    """
    Remove all UAL metadata from an object.

    Args:
        obj: Blender object to clear metadata from
    """
    keys_to_remove = [
        UAL_UUID, UAL_VERSION_GROUP_ID, UAL_VERSION, UAL_VERSION_LABEL,
        UAL_ASSET_NAME, UAL_ASSET_TYPE, UAL_REPRESENTATION_TYPE, UAL_IMPORTED,
        UAL_ASSET_ID, UAL_VARIANT_NAME, UAL_LINK_MODE
    ]
    for key in keys_to_remove:
        if key in obj:
            del obj[key]


def store_metadata_on_objects(objects: List[bpy.types.Object], asset_data: Dict[str, Any]) -> None:
    """
    Store UAL metadata on multiple objects.

    Args:
        objects: List of Blender objects
        asset_data: Dictionary containing asset metadata
    """
    for obj in objects:
        try:
            store_ual_metadata_from_dict(obj, asset_data)
        except (ReferenceError, RuntimeError):
            pass


def get_ual_objects_in_scene(context) -> List[bpy.types.Object]:
    """
    Get all objects in the scene that have UAL metadata.

    Args:
        context: Blender context

    Returns:
        List of objects with UAL metadata
    """
    return [obj for obj in context.scene.objects if has_ual_metadata(obj)]


# ==================== MATERIAL METADATA ====================

def store_material_metadata(material: bpy.types.Material, metadata: Dict[str, Any]) -> None:
    """
    Store UAL metadata on a material data block.

    Materials support custom properties just like objects, so we store
    versioning metadata directly on the material for version tracking.

    Args:
        material: Blender material to store metadata on
        metadata: Dictionary containing asset metadata
    """
    version_group_id = metadata.get('version_group_id', metadata.get('uuid', ''))

    material[UAL_UUID] = metadata.get('uuid', '')
    material[UAL_VERSION_GROUP_ID] = version_group_id
    material[UAL_VERSION] = metadata.get('version', 1)
    material[UAL_VERSION_LABEL] = metadata.get('version_label', 'v001')
    material[UAL_ASSET_NAME] = metadata.get('name', metadata.get('asset_name', ''))
    material[UAL_ASSET_TYPE] = 'material'
    material[UAL_IMPORTED] = True
    material[UAL_ASSET_ID] = metadata.get('asset_id', version_group_id)
    material[UAL_VARIANT_NAME] = metadata.get('variant_name', 'Base')


def read_material_metadata(material: bpy.types.Material) -> Optional[Dict[str, Any]]:
    """
    Read UAL metadata from a material.

    Args:
        material: Blender material to read metadata from

    Returns:
        Dictionary of metadata or None if material has no UAL metadata
    """
    if not material.get(UAL_IMPORTED):
        return None

    version_group_id = material.get(UAL_VERSION_GROUP_ID, '')
    return {
        'uuid': material.get(UAL_UUID, ''),
        'version_group_id': version_group_id,
        'version': material.get(UAL_VERSION, 0),
        'version_label': material.get(UAL_VERSION_LABEL, ''),
        'asset_name': material.get(UAL_ASSET_NAME, ''),
        'asset_type': 'material',
        'asset_id': material.get(UAL_ASSET_ID, version_group_id),
        'variant_name': material.get(UAL_VARIANT_NAME, 'Base'),
    }


def has_material_metadata(material: bpy.types.Material) -> bool:
    """
    Check if a material has UAL versioning metadata.

    Args:
        material: Blender material to check

    Returns:
        True if material has UAL metadata
    """
    return material.get(UAL_IMPORTED, False)


def detect_link_mode(obj: bpy.types.Object) -> str:
    """
    Detect import mode from stored property or Blender data inspection.

    For objects imported before link_mode tracking was added, inspects
    the object's data to determine how it was brought into the scene.

    Args:
        obj: Blender object to inspect

    Returns:
        Link mode string: 'INSTANCE', 'LINK', or 'APPEND'
    """
    stored = obj.get(UAL_LINK_MODE, '')
    if stored:
        return stored
    if obj.instance_type == 'COLLECTION' and obj.instance_collection:
        return 'INSTANCE'
    if obj.library or (obj.data and hasattr(obj.data, 'library') and obj.data.library):
        return 'LINK'
    return 'APPEND'


__all__ = [
    # Object metadata functions
    'store_ual_metadata',
    'store_ual_metadata_from_dict',
    'read_ual_metadata',
    'has_ual_metadata',
    'clear_ual_metadata',
    'store_metadata_on_objects',
    'get_ual_objects_in_scene',
    'detect_link_mode',
    # Material metadata functions
    'store_material_metadata',
    'read_material_metadata',
    'has_material_metadata',
    # Constants
    'UAL_UUID',
    'UAL_VERSION_GROUP_ID',
    'UAL_VERSION',
    'UAL_VERSION_LABEL',
    'UAL_ASSET_NAME',
    'UAL_ASSET_TYPE',
    'UAL_REPRESENTATION_TYPE',
    'UAL_IMPORTED',
    # Variant system constants
    'UAL_ASSET_ID',
    'UAL_VARIANT_NAME',
    # Import mode tracking
    'UAL_LINK_MODE',
]
