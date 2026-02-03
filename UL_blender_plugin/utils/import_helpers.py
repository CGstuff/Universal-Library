"""
Import Helper Functions

Standalone functions for importing assets from various file formats.
Extracted from queue_handler.py for reusability.
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple
import bpy

from .blender_helpers import get_root_objects, apply_location_to_roots, select_objects, get_cursor_location


def _get_current_blend_path(blend_path: str) -> str:
    """
    Convert a versioned .blend path to its .current.blend equivalent.
    
    Args:
        blend_path: Path like AST_Cube.v003.blend
        
    Returns:
        Path like AST_Cube.current.blend if it exists, otherwise original path
    """
    if not blend_path:
        return blend_path
    
    path = Path(blend_path)
    
    # Strip version suffix (e.g., .v003) to get base name
    stem = path.stem
    base_name = re.sub(r'\.(v\d{3,})$', '', stem)
    
    current_path = path.parent / f"{base_name}.current.blend"
    
    if current_path.exists():
        return str(current_path)
    
    return blend_path


def import_blend_file(
    context,
    filepath: str,
    link: bool = False,
    keep_location: bool = True
) -> Tuple[bool, List[bpy.types.Object]]:
    """
    Import objects and collections from a .blend file.

    Args:
        context: Blender context
        filepath: Path to .blend file
        link: If True, link objects; if False, append
        keep_location: If True, preserve original location; if False, move to cursor

    Returns:
        Tuple of (success, list of imported objects)
    """
    try:
        # Use .current.blend for stable linking (auto-updates when library refreshed)
        if link:
            filepath = _get_current_blend_path(filepath)
        
        # Track existing data to identify what's new
        existing_collections = set(bpy.data.collections.keys())
        existing_objects = set(bpy.data.objects.keys())

        # Import collections AND objects to preserve hierarchy
        with bpy.data.libraries.load(filepath, link=link) as (data_from, data_to):
            # Import all collections (this preserves hierarchy)
            data_to.collections = data_from.collections[:]
            # Import all objects
            data_to.objects = data_from.objects[:]
            # Also import meshes, armatures, etc. for proper linking
            data_to.meshes = data_from.meshes[:]
            data_to.armatures = data_from.armatures[:]
            data_to.materials = data_from.materials[:]
            data_to.cameras = data_from.cameras[:]
            data_to.lights = data_from.lights[:]

        # Find newly imported collections and objects
        new_collection_names = set(bpy.data.collections.keys()) - existing_collections
        new_object_names = set(bpy.data.objects.keys()) - existing_objects

        # Find root collections (not children of other imported collections)
        imported_collections = [bpy.data.collections[name] for name in new_collection_names]
        nested_names = set()
        for col in imported_collections:
            for child in col.children:
                nested_names.add(child.name)

        root_collections = [col for col in imported_collections if col.name not in nested_names]

        # Link root collections to the scene
        for col in root_collections:
            if col.name not in [c.name for c in context.scene.collection.children]:
                context.scene.collection.children.link(col)

        # Get imported objects
        imported_objects = [bpy.data.objects[name] for name in new_object_names if name in bpy.data.objects]

        # If no collections were imported, link objects directly to active collection
        if not root_collections:
            for obj in imported_objects:
                # Check if object is already in a scene collection
                in_scene = any(obj.name in col.objects for col in context.scene.collection.children_recursive)
                if not in_scene and obj.name not in context.collection.objects:
                    context.collection.objects.link(obj)

        # Update view layer and select objects
        context.view_layer.update()

        select_objects(context, imported_objects)

        if not keep_location and imported_objects:
            cursor_loc = get_cursor_location(context)
            apply_location_to_roots(imported_objects, cursor_loc)

        return True, imported_objects

    except Exception:
        return False, []


def import_blend_as_instance(
    context,
    filepath: str,
    keep_location: bool = True
) -> Tuple[bool, Optional[bpy.types.Object]]:
    """
    Import a .blend file as an instanced collection.

    Args:
        context: Blender context
        filepath: Path to .blend file
        keep_location: If True, preserve original location; if False, move to cursor

    Returns:
        Tuple of (success, instance empty object or None)
    """
    try:
        # Use .current.blend for stable linking (auto-updates when library refreshed)
        filepath = _get_current_blend_path(filepath)
        
        # First, try to link collections
        with bpy.data.libraries.load(filepath, link=True) as (data_from, data_to):
            if data_from.collections:
                data_to.collections = data_from.collections

        linked_collection = None

        if data_to.collections:
            linked_collection = data_to.collections[0]
        else:
            # Fall back to linking objects and putting them in a collection
            with bpy.data.libraries.load(filepath, link=True) as (data_from, data_to):
                data_to.objects = data_from.objects

            if not data_to.objects:
                return False, None

            # Create a new collection for the linked objects
            asset_name = Path(filepath).stem
            new_collection = bpy.data.collections.new(asset_name)

            for obj in data_to.objects:
                if obj is not None:
                    new_collection.objects.link(obj)

            linked_collection = new_collection

        if not linked_collection:
            return False, None

        # Create an empty object to instance the collection
        instance_empty = bpy.data.objects.new(
            name=linked_collection.name + "_instance",
            object_data=None
        )
        instance_empty.instance_type = 'COLLECTION'
        instance_empty.instance_collection = linked_collection

        context.collection.objects.link(instance_empty)

        select_objects(context, [instance_empty])

        # Hide any WGT collections that came through the link
        from .widget_helpers import hide_widget_collections
        hide_widget_collections(context)

        if not keep_location:
            instance_empty.location = get_cursor_location(context)

        return True, instance_empty

    except Exception:
        return False, None


def import_usd_file(
    context,
    filepath: str,
    keep_location: bool = True
) -> Tuple[bool, List[bpy.types.Object]]:
    """
    Import from a USD file.

    Args:
        context: Blender context
        filepath: Path to USD file
        keep_location: If True, preserve original location; if False, move to cursor

    Returns:
        Tuple of (success, list of imported objects)
    """
    try:
        result = bpy.ops.wm.usd_import(filepath=filepath)

        if result != {'FINISHED'}:
            return False, []

        imported_objects = list(context.selected_objects)

        if not keep_location and imported_objects:
            cursor_loc = get_cursor_location(context)
            apply_location_to_roots(imported_objects, cursor_loc)

        return True, imported_objects

    except Exception:
        return False, []


def import_material_from_blend(
    context,
    filepath: str,
    apply_to_selection: bool = True
) -> Tuple[bool, Optional[bpy.types.Material]]:
    """
    Import material from a .blend file.

    Args:
        context: Blender context
        filepath: Path to .blend file containing material
        apply_to_selection: If True, apply to selected meshes

    Returns:
        Tuple of (success, imported material or None)
    """
    try:
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']

        with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
            data_to.materials = data_from.materials

        imported_material = None
        for mat in data_to.materials:
            if mat is not None:
                imported_material = mat
                break

        if not imported_material:
            return False, None

        if apply_to_selection and selected_meshes:
            for obj in selected_meshes:
                if obj.data.materials:
                    obj.data.materials[0] = imported_material
                else:
                    obj.data.materials.append(imported_material)

        return True, imported_material

    except Exception:
        return False, None


def import_material_from_usd(
    context,
    filepath: str,
    apply_to_selection: bool = True
) -> Tuple[bool, Optional[bpy.types.Material]]:
    """
    Import material from a USD file (extracts from geometry).

    Args:
        context: Blender context
        filepath: Path to USD file
        apply_to_selection: If True, apply to originally selected meshes

    Returns:
        Tuple of (success, imported material or None)
    """
    try:
        # Remember original selection
        original_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']

        # Import USD
        result = bpy.ops.wm.usd_import(filepath=filepath)
        if result != {'FINISHED'}:
            return False, None

        # Find material from imported objects
        imported_material = None
        imported_objects = list(context.selected_objects)

        for obj in imported_objects:
            if obj.type == 'MESH' and obj.data.materials:
                imported_material = obj.data.materials[0]
                break

        # Delete imported geometry (we only want the material)
        bpy.ops.object.delete()

        if not imported_material:
            return False, None

        # Apply to original selection
        if apply_to_selection and original_meshes:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_meshes:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
                    if obj.data.materials:
                        obj.data.materials[0] = imported_material
                    else:
                        obj.data.materials.append(imported_material)

        return True, imported_material

    except Exception:
        return False, None


def import_asset(
    context,
    filepath: str,
    import_method: str = 'BLEND',
    link_mode: str = 'APPEND',
    keep_location: bool = True
) -> Tuple[bool, List[bpy.types.Object]]:
    """
    High-level asset import function.

    Args:
        context: Blender context
        filepath: Path to asset file
        import_method: 'BLEND' or 'USD'
        link_mode: 'APPEND', 'LINK', or 'INSTANCE'
        keep_location: Whether to preserve original location

    Returns:
        Tuple of (success, list of imported objects)
    """
    if import_method == 'BLEND':
        if link_mode == 'INSTANCE':
            success, instance = import_blend_as_instance(context, filepath, keep_location)
            return success, [instance] if instance else []
        else:
            link = link_mode == 'LINK'
            return import_blend_file(context, filepath, link=link, keep_location=keep_location)
    else:
        return import_usd_file(context, filepath, keep_location=keep_location)


__all__ = [
    'import_blend_file',
    'import_blend_as_instance',
    'import_usd_file',
    'import_material_from_blend',
    'import_material_from_usd',
    'import_asset',
]
