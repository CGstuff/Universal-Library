"""
Widget Helpers for Rig Imports

Detects and hides bone custom shape (widget) objects when linking rigs
from the library. Widget objects (WGT-*, etc.) clutter the scene and
cannot be deleted when linked; this module moves them into a hidden
collection excluded from the view layer.

Also handles widget objects that appear after creating Library Overrides
(e.g., AutoRig Pro rigs where widgets are part of the armature hierarchy).
A lightweight depsgraph handler monitors for newly added override objects
and hides them automatically.
"""

import bpy
from bpy.app.handlers import persistent
from typing import Set, Optional

# Common naming prefixes used by rig tools for widget objects
WIDGET_NAME_PREFIXES = ("WGT-", "WGT_", "wgt-", "wgt_")

# Common collection names used by rig tools for widget collections
WIDGET_COLLECTION_PREFIXES = ("WGT", "WGTS", "Widgets", "widgets")

# Name of the hidden collection we create to hold linked widgets
_WGT_COLLECTION_NAME = "_WGT_Linked"


def find_widget_objects(armature_obj) -> Set:
    """
    Find all widget objects referenced by an armature's pose bones.

    This is the most reliable detection method - it works for any rig tool
    (Rigify, AutoRig Pro, custom rigs) regardless of naming convention,
    because it inspects the actual custom_shape references.

    Args:
        armature_obj: A Blender object of type 'ARMATURE'

    Returns:
        Set of objects used as bone custom shapes
    """
    widgets = set()
    if armature_obj.type != 'ARMATURE' or not armature_obj.pose:
        return widgets

    for pose_bone in armature_obj.pose.bones:
        if pose_bone.custom_shape is not None:
            widgets.add(pose_bone.custom_shape)

    return widgets


def find_widget_objects_by_name(objects) -> Set:
    """
    Fallback detection: find widget objects by name prefix.

    Catches widgets that may not be directly referenced by any bone
    (e.g., orphaned widgets from deleted bones).

    Args:
        objects: Iterable of Blender objects to check

    Returns:
        Set of objects whose names match widget prefixes
    """
    widgets = set()
    for obj in objects:
        if obj and obj.name.startswith(WIDGET_NAME_PREFIXES):
            widgets.add(obj)
    return widgets


def hide_linked_widgets(context, imported_objects) -> int:
    """
    Hide widget objects after linking a rig from the library.

    Moves widget objects into a hidden, excluded collection so they don't
    clutter the scene. Custom bone shapes continue to display correctly
    because Blender evaluates custom_shape references independently of
    object visibility.

    Args:
        context: Blender context
        imported_objects: List/set of newly imported objects

    Returns:
        Number of widget objects hidden
    """
    if not imported_objects:
        return 0

    imported_set = set(imported_objects)

    # Find all widget objects among the imported objects
    all_widgets = set()

    # Primary: detect via pose bone custom_shape references
    for obj in imported_objects:
        if obj and obj.type == 'ARMATURE':
            all_widgets |= find_widget_objects(obj)

    # Secondary: detect by name prefix
    all_widgets |= find_widget_objects_by_name(imported_objects)

    # Only touch widgets that are part of this import
    widgets_to_hide = all_widgets & imported_set

    if not widgets_to_hide:
        return 0

    # Get or create the hidden widget collection
    wgt_collection = bpy.data.collections.get(_WGT_COLLECTION_NAME)
    if not wgt_collection:
        wgt_collection = bpy.data.collections.new(_WGT_COLLECTION_NAME)
        context.scene.collection.children.link(wgt_collection)

    # Ensure collection is linked to scene (may have been unlinked)
    scene_child_names = [c.name for c in context.scene.collection.children]
    if wgt_collection.name not in scene_child_names:
        context.scene.collection.children.link(wgt_collection)

    # Move widget objects into the hidden collection
    hidden_count = 0
    for widget in widgets_to_hide:
        # Link to our hidden collection
        if widget.name not in wgt_collection.objects:
            wgt_collection.objects.link(widget)

        # Unlink from all other collections in the scene
        for col in list(bpy.data.collections):
            if col.name == _WGT_COLLECTION_NAME:
                continue
            if widget.name in col.objects:
                col.objects.unlink(widget)

        # Also unlink from scene root collection if present
        if widget.name in context.scene.collection.objects:
            context.scene.collection.objects.unlink(widget)

        hidden_count += 1

    # Hide the collection itself
    wgt_collection.hide_viewport = True
    wgt_collection.hide_render = True

    # Exclude from view layer
    _exclude_collection_from_view_layer(context, _WGT_COLLECTION_NAME)

    return hidden_count


def hide_widget_collections(context) -> int:
    """
    Hide widget collections that came through as linked sub-collections.

    For collection-instance imports, individual objects are already hidden
    by instancing, but linked sub-collections named WGT/WGTS/Widgets may
    appear in the outliner.

    Args:
        context: Blender context

    Returns:
        Number of collections hidden
    """
    hidden_count = 0

    for col in bpy.data.collections:
        # Check if collection name starts with any widget prefix
        is_widget_col = False
        for prefix in WIDGET_COLLECTION_PREFIXES:
            if col.name == prefix or col.name.startswith(prefix + "."):
                is_widget_col = True
                break

        if is_widget_col:
            layer_col = _find_layer_collection(
                context.view_layer.layer_collection, col.name
            )
            if layer_col:
                layer_col.exclude = True
                hidden_count += 1

    return hidden_count


def _exclude_collection_from_view_layer(context, collection_name: str):
    """Exclude a collection from the view layer."""
    layer_col = _find_layer_collection(
        context.view_layer.layer_collection, collection_name
    )
    if layer_col:
        layer_col.exclude = True


def _find_layer_collection(
    layer_col, name: str
) -> Optional[bpy.types.LayerCollection]:
    """
    Recursively find a LayerCollection by name in the view layer tree.

    Args:
        layer_col: Root LayerCollection to search from
        name: Collection name to find

    Returns:
        The matching LayerCollection, or None if not found
    """
    if layer_col.name == name:
        return layer_col

    for child in layer_col.children:
        found = _find_layer_collection(child, name)
        if found:
            return found

    return None


def hide_override_widgets(scene) -> int:
    """
    Hide widget objects created by Library Override.

    When Blender creates a library override of an armature (e.g., AutoRig Pro),
    it may also create override copies of widget objects. These appear as new
    local objects in the scene. This function finds them and moves them into
    the hidden _WGT_Linked collection.

    Args:
        scene: The Blender scene

    Returns:
        Number of widget objects hidden
    """
    wgt_collection = bpy.data.collections.get(_WGT_COLLECTION_NAME)
    wgt_object_names = set(wgt_collection.objects.keys()) if wgt_collection else set()

    # Find override armatures and collect their widget objects
    widgets_to_hide = set()
    for obj in bpy.data.objects:
        if obj.type != 'ARMATURE' or not obj.override_library or not obj.pose:
            continue
        for pose_bone in obj.pose.bones:
            if pose_bone.custom_shape is not None:
                widget = pose_bone.custom_shape
                if widget.override_library and widget.name not in wgt_object_names:
                    widgets_to_hide.add(widget)

    # Also catch by name prefix (orphaned override widgets)
    for obj in bpy.data.objects:
        if (obj.override_library
                and obj.name not in wgt_object_names
                and obj.name.startswith(WIDGET_NAME_PREFIXES)):
            widgets_to_hide.add(obj)

    if not widgets_to_hide:
        return 0

    # Get or create hidden collection
    if not wgt_collection:
        wgt_collection = bpy.data.collections.new(_WGT_COLLECTION_NAME)
        scene.collection.children.link(wgt_collection)

    # Ensure linked to scene
    scene_child_names = [c.name for c in scene.collection.children]
    if wgt_collection.name not in scene_child_names:
        scene.collection.children.link(wgt_collection)

    # Move widget objects into the hidden collection
    hidden_count = 0
    for widget in widgets_to_hide:
        if widget.name not in wgt_collection.objects:
            wgt_collection.objects.link(widget)

        # Unlink from all other collections
        for col in list(bpy.data.collections):
            if col.name == _WGT_COLLECTION_NAME:
                continue
            if widget.name in col.objects:
                col.objects.unlink(widget)

        # Unlink from scene root collection
        if widget.name in scene.collection.objects:
            scene.collection.objects.unlink(widget)

        hidden_count += 1

    # Hide the collection
    wgt_collection.hide_viewport = True
    wgt_collection.hide_render = True

    # Exclude from all view layers
    for view_layer in scene.view_layers:
        layer_col = _find_layer_collection(
            view_layer.layer_collection, _WGT_COLLECTION_NAME
        )
        if layer_col:
            layer_col.exclude = True

    return hidden_count


# ---------------------------------------------------------------------------
# Depsgraph handler for automatic override widget hiding
# ---------------------------------------------------------------------------

_prev_object_count = -1
_handler_active = False


@persistent
def _on_depsgraph_update(scene, depsgraph):
    """
    Lightweight depsgraph handler that detects newly added override widget
    objects and hides them automatically.

    Fast path: compares object count (O(1)). Only scans for widgets when
    objects have been added to the scene.
    """
    global _prev_object_count, _handler_active

    if _handler_active:
        return

    current_count = len(bpy.data.objects)

    # Fast path: no change in object count
    if current_count == _prev_object_count:
        return

    prev = _prev_object_count
    _prev_object_count = current_count

    # Only process when objects were added (not removed or on init)
    if current_count <= prev or prev < 0:
        return

    _handler_active = True
    try:
        hidden = hide_override_widgets(scene)
        if hidden:
            # Update count after our changes (we may have moved objects
            # between collections but count stays the same)
            _prev_object_count = len(bpy.data.objects)
    except Exception:
        pass
    finally:
        _handler_active = False


@persistent
def _on_file_loaded(dummy):
    """Reset object count tracking when a new file is loaded."""
    global _prev_object_count
    _prev_object_count = len(bpy.data.objects)


def register_handlers():
    """Register depsgraph and file-load handlers for override widget hiding."""
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    bpy.app.handlers.load_post.append(_on_file_loaded)

    # Initialize count for current file
    global _prev_object_count
    _prev_object_count = len(bpy.data.objects)


def unregister_handlers():
    """Unregister depsgraph and file-load handlers."""
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if _on_file_loaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_file_loaded)


__all__ = [
    'WIDGET_NAME_PREFIXES',
    'WIDGET_COLLECTION_PREFIXES',
    'find_widget_objects',
    'find_widget_objects_by_name',
    'hide_linked_widgets',
    'hide_widget_collections',
    'hide_override_widgets',
    'register_handlers',
    'unregister_handlers',
]
