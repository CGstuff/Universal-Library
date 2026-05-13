"""
Import Helper Functions

Standalone functions for importing assets from various file formats.
Extracted from queue_handler.py for reusability.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple
import bpy

from .blender_helpers import get_root_objects, apply_location_to_roots, select_objects, get_cursor_location

logger = logging.getLogger(__name__)


def _walk_image_nodes(tree):
    """Yield every ShaderNodeTexImage in a node tree, recursing into groups."""
    if tree is None:
        return
    for node in tree.nodes:
        if node.bl_idname == 'ShaderNodeTexImage':
            yield node
        elif node.type == 'GROUP' and getattr(node, 'node_tree', None):
            yield from _walk_image_nodes(node.node_tree)


def _pack_imported_textures(imported_objects):
    """After import, pack any image referenced by imported objects' materials.

    Solves Blender's name-dedup behavior on append: if the user's working
    file already has `wood.png` as external, the appended packed copy is
    silently discarded and the imported material ends up pointing at the
    local external image — making the work-PC path different from a fresh
    laptop. Packing now (from disk if needed) makes the imported asset
    self-contained either way.

    Skips images that are already packed, library-linked (read-only), or
    have no resolvable source. Per-image try/except so one bad texture
    doesn't abort the whole pass.
    """
    seen = set()
    packed_count = 0
    failed = []

    for obj in imported_objects:
        if obj.type != 'MESH':
            continue
        for slot in getattr(obj, 'material_slots', []):
            mat = slot.material
            if not mat or not getattr(mat, 'use_nodes', False):
                continue
            for node in _walk_image_nodes(mat.node_tree):
                img = node.image
                if img is None or img.name in seen:
                    continue
                seen.add(img.name)

                # Already packed — leave alone.
                if img.packed_file is not None:
                    continue
                # Library-linked images are read-only.
                if getattr(img, 'library', None) is not None:
                    continue
                # No source we can pack from.
                if not img.filepath and img.source != 'GENERATED':
                    continue

                try:
                    img.pack()
                    packed_count += 1
                except Exception as e:
                    failed.append((img.name, str(e)))

    if packed_count > 0:
        print(f"[UL import] packed {packed_count} texture(s) into "
              f"working file for portability")
    if failed:
        for name, err in failed:
            print(f"[UL import] failed to pack '{name}': {err}")


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
        existing_actions = set(bpy.data.actions.keys())

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
            # Pull in ALL actions stored in the library .blend.
            # `libraries.load` only follows explicit requests — actions saved
            # via fake_user but not currently referenced (the picker's
            # un-attached selections) would otherwise be silently dropped.
            data_to.actions = data_from.actions[:]

        # Set fake_user on every action we just brought in. The library
        # author intentionally shipped these (picked in the export dialog),
        # so we want them to survive subsequent saves of the user's working
        # file even if they don't immediately get assigned to anything.
        for name in set(bpy.data.actions.keys()) - existing_actions:
            action = bpy.data.actions.get(name)
            if action is not None:
                action.use_fake_user = True

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

        # Pack textures referenced by imported materials. Blender's append
        # silently dedups images by name — if the user's working file already
        # has `wood.png` external, the appended packed version is discarded
        # and the imported material points at the local external one. That
        # makes the work-PC path different from the laptop path. Packing now
        # ensures the imported asset is self-contained either way.
        _pack_imported_textures(imported_objects)

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
        logger.exception("import_blend_as_objects failed for %s", filepath)
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
        logger.exception("import_blend_as_instance failed for %s", filepath)
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
        logger.exception("import_usd_file failed for %s", filepath)
        return False, []


def import_material_from_blend(
    context,
    filepath: str,
    apply_to_selection: bool = True,
    asset_metadata: Optional[dict] = None,
) -> Tuple[bool, Optional[bpy.types.Material]]:
    """
    Import material from a .blend file.

    Args:
        context: Blender context
        filepath: Path to .blend file containing material
        apply_to_selection: If True, apply to selected meshes
        asset_metadata: Optional dict of UAL asset fields (uuid,
            version_group_id, version, version_label, name, asset_id,
            variant_name, ...). When provided, the imported material is
            stamped via store_material_metadata so the export operator
            can later offer "new version" on it. Without this, materials
            dragged in via the queue handler would land in fresh Blender
            files with no library lineage and the user would be unable
            to version them.

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
                # Always append. On a mesh with zero materials this still
                # creates slot 0; on a mesh that already has materials it
                # appends a new slot at the end instead of overwriting the
                # one the artist already set up. Imports are additive,
                # never destructive.
                obj.data.materials.append(imported_material)

        # Stamp UAL metadata so future exports can recognize this material
        # as a library asset and offer the "new version" path.
        if asset_metadata:
            try:
                from .metadata_handler import store_material_metadata
                store_material_metadata(imported_material, asset_metadata)
            except Exception:
                logger.exception(
                    "Failed to stamp UAL metadata on imported material %s",
                    imported_material.name,
                )

        return True, imported_material

    except Exception:
        logger.exception("import_material_from_blend failed for %s", filepath)
        return False, None


def import_material_from_usd(
    context,
    filepath: str,
    apply_to_selection: bool = True,
    asset_metadata: Optional[dict] = None,
) -> Tuple[bool, Optional[bpy.types.Material]]:
    """
    Import material from a USD file (extracts from geometry).

    Args:
        context: Blender context
        filepath: Path to USD file
        apply_to_selection: If True, apply to originally selected meshes
        asset_metadata: See import_material_from_blend.

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
                    # Always append (see note in import_material_from_blend).
                    obj.data.materials.append(imported_material)

        if asset_metadata:
            try:
                from .metadata_handler import store_material_metadata
                store_material_metadata(imported_material, asset_metadata)
            except Exception:
                logger.exception(
                    "Failed to stamp UAL metadata on imported material %s",
                    imported_material.name,
                )

        return True, imported_material

    except Exception:
        logger.exception("import_material_from_usd failed for %s", filepath)
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
