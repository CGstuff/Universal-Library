"""
Asset Switcher Operators - Switch version or variant in-place.

Provides instant in-place switching without a full replace. Each operator
captures transforms, deletes originals, imports the new version, and
restores position/rotation/scale. Fully undoable via Ctrl+Z.
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty
from pathlib import Path
from typing import List, Dict, Any, Tuple

from ..utils.metadata_handler import (
    has_ual_metadata,
    read_ual_metadata,
    store_ual_metadata,
    detect_link_mode,
)
from ..utils.import_helpers import import_asset
from ..utils.blender_helpers import select_objects
from ..utils.asset_switcher_db import get_switcher_db
from ..operators.representation_swap import restore_to_original


# ---------------------------------------------------------------------------
# Shared swap helper
# ---------------------------------------------------------------------------

def perform_in_place_swap(
    context,
    targets: List[bpy.types.Object],
    new_blend_path: str,
    new_metadata: Dict[str, Any],
    link_mode: str,
) -> Tuple[bool, List[bpy.types.Object]]:
    """
    Replace *targets* with an asset from *new_blend_path*, preserving transforms.

    Steps:
        1. Push undo snapshot
        2. Auto-restore ALL libraries if in proxy/render/nothing mode
        3. Capture matrix_world + collection membership for each target
        4. Delete originals
        5. Import asset via import_asset()
        6. Place first imported object at first transform
        7. Duplicate for remaining transforms
        8. Store ual_* metadata on all new objects
        9. Select new objects
        10. Push undo snapshot

    Args:
        context: Blender context
        targets: Objects to replace (must all be valid)
        new_blend_path: Path to the .blend file to import
        new_metadata: Dict of UAL metadata keys to store on new objects
        link_mode: Import method -- APPEND, LINK, or INSTANCE

    Returns:
        Tuple of (success, list of new objects)
    """
    if not targets:
        return False, []

    # 1. Pre-swap undo
    bpy.ops.ed.undo_push(message="Before Switch")

    # 2. Auto-restore ALL libraries if any are in proxy/render/nothing mode
    #    This ensures clean state before switching
    restored, _, _ = restore_to_original()
    if restored > 0:
        context.view_layer.update()

    # 3. Capture transforms and collection membership
    transforms = []
    for obj in targets:
        collections = list(obj.users_collection)
        target_col = collections[0] if collections else context.scene.collection
        transforms.append({
            'matrix_world': obj.matrix_world.copy(),
            'collection': target_col,
        })

    # 4. Delete originals
    for obj in targets:
        bpy.data.objects.remove(obj, do_unlink=True)

    # 5. Import replacement asset
    try:
        success, imported_objects = import_asset(
            context,
            new_blend_path,
            import_method='BLEND',
            link_mode=link_mode,
            keep_location=True,
        )
    except Exception as e:
        return False, []

    if not success or not imported_objects:
        return False, []

    # 6. Place first imported object at first transform
    first_obj = imported_objects[0]
    first_transform = transforms[0]
    first_obj.matrix_world = first_transform['matrix_world']

    # Move to correct collection if needed
    target_col = first_transform['collection']
    if first_obj.name not in target_col.objects:
        try:
            target_col.objects.link(first_obj)
        except RuntimeError:
            pass
    for col in list(first_obj.users_collection):
        if col != target_col:
            try:
                col.objects.unlink(first_obj)
            except RuntimeError:
                pass

    new_objects = [first_obj]

    # 7. Duplicate for remaining transforms
    for transform in transforms[1:]:
        dup = first_obj.copy()
        target_col = transform['collection']
        target_col.objects.link(dup)
        dup.matrix_world = transform['matrix_world']
        new_objects.append(dup)

    # 8. Store UAL metadata on all new objects
    for obj in new_objects:
        store_ual_metadata(
            obj,
            uuid=new_metadata.get('uuid', ''),
            version_group_id=new_metadata.get('version_group_id', ''),
            version=new_metadata.get('version', 1),
            version_label=new_metadata.get('version_label', 'v001'),
            asset_name=new_metadata.get('asset_name', ''),
            asset_type=new_metadata.get('asset_type', 'model'),
            representation_type=new_metadata.get('representation_type', 'none'),
            imported=True,
            asset_id=new_metadata.get('asset_id', ''),
            variant_name=new_metadata.get('variant_name', 'Base'),
            link_mode=link_mode,
        )

    # 9. Select new objects
    select_objects(context, new_objects)
    context.view_layer.update()

    # 10. Post-swap undo
    bpy.ops.ed.undo_push(message="Asset Switch")

    return True, new_objects


# ---------------------------------------------------------------------------
# Helper: gather batch targets
# ---------------------------------------------------------------------------

def _gather_batch_targets(context) -> List[bpy.types.Object]:
    """
    Gather all selected objects sharing the active object's version_group_id.

    Returns empty list if active object has no UAL metadata.
    """
    obj = context.active_object
    if not obj or not has_ual_metadata(obj):
        return []

    metadata = read_ual_metadata(obj)
    vg_id = metadata.get('version_group_id', '')
    if not vg_id:
        return [obj]

    targets = []
    for o in context.selected_objects:
        if has_ual_metadata(o) and o.get('ual_version_group_id') == vg_id:
            targets.append(o)

    return targets if targets else [obj]


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class UAL_OT_switch_version(Operator):
    """Switch the selected asset to a different version"""
    bl_idname = "ual.switch_version"
    bl_label = "Switch Version"
    bl_description = "Switch to a different version of this asset in-place"
    bl_options = {'REGISTER', 'UNDO'}

    target_uuid: StringProperty(
        name="Target UUID",
        description="UUID of the version to switch to",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and has_ual_metadata(obj)

    def execute(self, context):
        db = get_switcher_db()
        if not db:
            self.report({'ERROR'}, "Cannot connect to library database")
            return {'CANCELLED'}

        # Get blend path for the target version
        blend_path = db.get_asset_blend_path(self.target_uuid)
        if not blend_path:
            self.report({'ERROR'}, "No blend file path found for target version")
            return {'CANCELLED'}

        if not Path(blend_path).exists():
            self.report({'ERROR'},
                f"File not found (may be in cold storage): {Path(blend_path).name}")
            return {'CANCELLED'}

        # Get full asset info for metadata
        versions = db.get_version_siblings(
            read_ual_metadata(context.active_object)['version_group_id']
        )
        target_info = None
        for v in versions:
            if v['uuid'] == self.target_uuid:
                target_info = v
                break

        if not target_info:
            self.report({'ERROR'}, "Target version not found in database")
            return {'CANCELLED'}

        # Gather batch targets
        targets = _gather_batch_targets(context)
        current_metadata = read_ual_metadata(context.active_object)
        link_mode = detect_link_mode(context.active_object)

        new_metadata = {
            'uuid': target_info['uuid'],
            'version_group_id': current_metadata['version_group_id'],
            'version': target_info['version'],
            'version_label': target_info['version_label'],
            'asset_name': target_info.get('name', current_metadata['asset_name']),
            'asset_type': current_metadata['asset_type'],
            'representation_type': target_info.get('representation_type', 'none') or 'none',
            'asset_id': target_info.get('asset_id', current_metadata.get('asset_id', '')),
            'variant_name': target_info.get('variant_name', current_metadata['variant_name']),
        }

        success, new_objects = perform_in_place_swap(
            context, targets, blend_path, new_metadata, link_mode
        )

        if success:
            db.invalidate_cache()
            self.report({'INFO'},
                f"Switched {len(targets)} object(s) to {target_info['version_label']}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Version switch failed")
            return {'CANCELLED'}


class UAL_OT_switch_variant(Operator):
    """Switch the selected asset to a different variant"""
    bl_idname = "ual.switch_variant"
    bl_label = "Switch Variant"
    bl_description = "Switch to a different variant of this asset in-place"
    bl_options = {'REGISTER', 'UNDO'}

    target_uuid: StringProperty(
        name="Target UUID",
        description="UUID of the variant's latest version to switch to",
    )
    target_variant_name: StringProperty(
        name="Target Variant",
        description="Name of the variant to switch to",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and has_ual_metadata(obj)

    def execute(self, context):
        db = get_switcher_db()
        if not db:
            self.report({'ERROR'}, "Cannot connect to library database")
            return {'CANCELLED'}

        blend_path = db.get_asset_blend_path(self.target_uuid)
        if not blend_path:
            self.report({'ERROR'}, "No blend file path found for target variant")
            return {'CANCELLED'}

        if not Path(blend_path).exists():
            self.report({'ERROR'},
                f"File not found: {Path(blend_path).name}")
            return {'CANCELLED'}

        # Get variant info from database
        current_metadata = read_ual_metadata(context.active_object)
        variants = db.get_variant_siblings(current_metadata['asset_id'])
        target_info = None
        for v in variants:
            if v['uuid'] == self.target_uuid:
                target_info = v
                break

        if not target_info:
            self.report({'ERROR'}, "Target variant not found in database")
            return {'CANCELLED'}

        targets = _gather_batch_targets(context)
        link_mode = detect_link_mode(context.active_object)

        new_metadata = {
            'uuid': target_info['uuid'],
            'version_group_id': target_info.get('version_group_id', ''),
            'version': target_info.get('version', 1),
            'version_label': target_info.get('version_label', 'v001'),
            'asset_name': target_info.get('name', current_metadata['asset_name']),
            'asset_type': current_metadata['asset_type'],
            'representation_type': current_metadata.get('representation_type', 'none'),
            'asset_id': current_metadata['asset_id'],
            'variant_name': self.target_variant_name,
        }

        success, new_objects = perform_in_place_swap(
            context, targets, blend_path, new_metadata, link_mode
        )

        if success:
            db.invalidate_cache()
            self.report({'INFO'},
                f"Switched {len(targets)} object(s) to variant '{self.target_variant_name}'")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Variant switch failed")
            return {'CANCELLED'}


class UAL_OT_refresh_switcher(Operator):
    """Refresh the asset switcher panel data"""
    bl_idname = "ual.refresh_switcher"
    bl_label = "Refresh Switcher"
    bl_description = "Refresh asset switcher data from database"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and has_ual_metadata(obj)

    def execute(self, context):
        db = get_switcher_db()
        if db:
            db.invalidate_cache()
        # Force panel redraw
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        self.report({'INFO'}, "Switcher data refreshed")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = [
    UAL_OT_switch_version,
    UAL_OT_switch_variant,
    UAL_OT_refresh_switcher,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_OT_switch_version',
    'UAL_OT_switch_variant',
    'UAL_OT_refresh_switcher',
    'perform_in_place_swap',
    'register',
    'unregister',
]
