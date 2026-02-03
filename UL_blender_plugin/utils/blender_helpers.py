"""
Blender Helper Utilities

Common Blender operations used across the addon.
"""

from typing import Optional, Tuple, List, Any
import bpy


def find_3d_viewport(context) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
    """
    Find the 3D viewport area, region, and space.

    Args:
        context: Blender context

    Returns:
        Tuple of (area, region, space) or (None, None, None) if not found
    """
    view3d_area = None
    view3d_region = None
    view3d_space = None

    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            view3d_area = area
            for region in area.regions:
                if region.type == 'WINDOW':
                    view3d_region = region
                    break
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    view3d_space = space
                    break
            break

    return view3d_area, view3d_region, view3d_space


def get_root_objects(objects) -> List[bpy.types.Object]:
    """
    Filter to get only root objects (objects without parents).

    Args:
        objects: Iterable of Blender objects

    Returns:
        List of objects that have no parent
    """
    return [obj for obj in objects if obj.parent is None]


def apply_location_to_roots(objects, location) -> None:
    """
    Apply a location to all root objects in the given collection.

    Args:
        objects: Iterable of Blender objects
        location: Location vector to apply
    """
    root_objects = get_root_objects(objects)
    for obj in root_objects:
        obj.location = location


def apply_scale_to_roots(objects, scale: float) -> None:
    """
    Apply a scale factor to all root objects in the given collection.

    Args:
        objects: Iterable of Blender objects
        scale: Scale factor to apply
    """
    for obj in objects:
        if obj.parent is None:
            obj.scale *= scale


def select_objects(context, objects, set_active: bool = True) -> None:
    """
    Select objects and optionally set the first as active.

    Args:
        context: Blender context
        objects: List of objects to select
        set_active: Whether to set the first object as active
    """
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        try:
            obj.select_set(True)
        except (ReferenceError, RuntimeError):
            pass

    if set_active and objects:
        try:
            context.view_layer.objects.active = objects[0]
        except (ReferenceError, RuntimeError):
            pass


def get_cursor_location(context):
    """
    Get the 3D cursor location.

    Args:
        context: Blender context

    Returns:
        Copy of cursor location vector
    """
    return context.scene.cursor.location.copy()


__all__ = [
    'find_3d_viewport',
    'get_root_objects',
    'apply_location_to_roots',
    'apply_scale_to_roots',
    'select_objects',
    'get_cursor_location',
]
