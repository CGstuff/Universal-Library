"""
Save Proxy Version Operator - Save geometry as a proxy version.

Workflow:
1. Import an asset from the library
2. Create or edit proxy geometry (simplify, decimate, etc.)
3. Select the objects (must include at least one with UAL metadata)
4. Click "Save Proxy Version" to save as a new proxy version (p001, p002, etc.)

The proxy is automatically designated as the active proxy representation.
Proxy files can be selected in the desktop app for runtime swapping. A
companion .glb is exported alongside each .blend so the app can render a
3D preview of the proxy.
"""

import bpy
import json
import logging
import uuid as uuid_module
from bpy.types import Operator
from bpy.props import BoolProperty, StringProperty
from pathlib import Path
from datetime import datetime

from ..utils.metadata_handler import has_ual_metadata, read_ual_metadata
from ..utils.library_connection import get_library_connection

logger = logging.getLogger(__name__)


def _export_proxy_glb(objects, filepath: str) -> bool:
    """Export proxy objects to a .glb for app-side 3D preview.

    Minimal compared to the main-asset glTF export: no animations, no rig
    filtering, just meshes + materials + WEBP textures + Draco. Selection
    state is saved and restored so this never disturbs the user's selection.

    Returns:
        True on success, False on failure (caller treats glb as best-effort —
        the proxy is usable without it; the user just won't see a preview).
    """
    if not objects:
        return False

    ctx = bpy.context
    original_selection = list(ctx.selected_objects)
    original_active = ctx.view_layer.objects.active
    hidden_to_restore = []

    try:
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            try:
                if obj.hide_get():
                    obj.hide_set(False)
                    hidden_to_restore.append(obj)
                obj.select_set(True)
            except (RuntimeError, ReferenceError):
                continue
        if objects:
            try:
                ctx.view_layer.objects.active = objects[0]
            except (RuntimeError, ReferenceError):
                pass

        bpy.ops.export_scene.gltf(
            filepath=filepath,
            use_selection=True,
            export_format='GLB',
            export_texcoords=True,
            export_normals=True,
            export_materials='EXPORT',
            export_image_format='WEBP',
            export_image_quality=75,
            export_draco_mesh_compression_enable=True,
            export_draco_mesh_compression_level=6,
            export_animations=False,
            export_apply=True,
            export_cameras=False,
            export_lights=False,
        )
        return Path(filepath).exists()
    except Exception:
        logger.exception("_export_proxy_glb failed for %s", filepath)
        return False
    finally:
        # Restore selection + visibility, ignoring any objects that got
        # destroyed since (defensive against undo / scene churn).
        try:
            bpy.ops.object.select_all(action='DESELECT')
        except Exception:
            pass
        for obj in original_selection:
            try:
                obj.select_set(True)
            except (RuntimeError, ReferenceError):
                continue
        try:
            ctx.view_layer.objects.active = original_active
        except (RuntimeError, ReferenceError):
            pass
        for obj in hidden_to_restore:
            try:
                obj.hide_set(True)
            except (RuntimeError, ReferenceError):
                continue


class UAL_OT_update_proxy(Operator):
    """Save selected geometry as a new proxy version for this asset"""
    bl_idname = "ual.update_proxy"
    bl_label = "Save Proxy"
    bl_description = (
        "Save selected geometry as a proxy version. "
        "Selection must include a library asset (e.g., decimate the imported asset, then save)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    include_materials: BoolProperty(
        name="Include Materials",
        description="Include materials in the proxy file",
        default=False,
    )

    proxy_notes: StringProperty(
        name="Notes",
        description="Optional notes for this proxy",
        default="",
    )

    @classmethod
    def poll(cls, context):
        """Need at least one selected object with UAL metadata."""
        if not context.selected_objects:
            return False
        for obj in context.selected_objects:
            if has_ual_metadata(obj):
                return True
        return False

    @classmethod
    def description(cls, context, properties):
        """Dynamic tooltip based on selection state."""
        if not context.selected_objects:
            return "Select a library asset to save as proxy"
        for obj in context.selected_objects:
            if has_ual_metadata(obj):
                return "Save selected geometry as a new proxy version (p001, p002, etc.)"
        return (
            "No library asset in selection. "
            "Select the imported asset (with decimate modifier, etc.) to save as proxy"
        )

    def invoke(self, context, event):
        """Show properties dialog."""
        return context.window_manager.invoke_props_dialog(self, width=350)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Save as new proxy version (p001, p002...)")
        layout.prop(self, "include_materials")
        layout.prop(self, "proxy_notes")

    def execute(self, context):
        # Find the UAL asset metadata
        metadata = None
        for obj in context.selected_objects:
            if has_ual_metadata(obj):
                metadata = read_ual_metadata(obj)
                break

        if not metadata:
            self.report({'ERROR'}, "No UAL asset found in selection")
            return {'CANCELLED'}

        asset_name = metadata.get('asset_name', '')
        asset_type = metadata.get('asset_type', 'mesh')
        version_group_id = metadata.get('version_group_id', '')
        asset_id = metadata.get('asset_id', '') or version_group_id
        variant_name = metadata.get('variant_name', 'Base')

        if not version_group_id:
            self.report({'ERROR'}, "Asset has no version_group_id")
            return {'CANCELLED'}

        if asset_type not in ('mesh', 'rig'):
            self.report({'ERROR'}, f"Proxy not supported for {asset_type} assets")
            return {'CANCELLED'}

        # Collect all selected objects as proxy geometry
        proxy_objects = []
        for obj in context.selected_objects:
            if obj.type == 'EMPTY' and obj.instance_collection:
                continue
            proxy_objects.append(obj)

        if not proxy_objects:
            self.report({'ERROR'}, "No geometry objects found in selection")
            return {'CANCELLED'}

        # Get library connection
        library = get_library_connection()
        if not library:
            self.report({'ERROR'}, "Library connection not available")
            return {'CANCELLED'}

        # Get next proxy version number
        next_version = library.get_next_custom_proxy_version(version_group_id, variant_name)
        proxy_label = f"p{next_version:03d}"

        # Get proxy folder path
        proxy_folder = library.get_custom_proxy_folder_path(
            asset_id, asset_name, variant_name, proxy_label, asset_type
        )

        # Save proxy .blend file
        blend_filename = f"{asset_name}.{proxy_label}.blend"
        blend_path = proxy_folder / blend_filename

        try:
            self._save_proxy_blend(proxy_objects, str(blend_path), asset_name)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to save proxy: {e}")
            return {'CANCELLED'}

        # Also export a .glb companion for app-side 3D preview. Best-effort —
        # a failure here doesn't fail the proxy save.
        glb_path = blend_path.with_suffix('.glb')
        glb_ok = _export_proxy_glb(proxy_objects, str(glb_path))
        glb_path_value = str(glb_path) if glb_ok else None

        # Calculate polygon count
        polygon_count = 0
        for obj in proxy_objects:
            if obj.type == 'MESH' and obj.data:
                polygon_count += len(obj.data.polygons)

        # Write JSON sidecar
        sidecar_path = proxy_folder / f"{asset_name}.{proxy_label}.json"
        sidecar_data = {
            'proxy_label': proxy_label,
            'proxy_version': next_version,
            'asset_name': asset_name,
            'asset_type': asset_type,
            'variant_name': variant_name,
            'version_group_id': version_group_id,
            'asset_id': asset_id,
            'polygon_count': polygon_count,
            'object_count': len(proxy_objects),
            'object_names': [o.name for o in proxy_objects],
            'notes': self.proxy_notes,
            'created_date': datetime.now().isoformat(),
        }
        try:
            with open(str(sidecar_path), 'w') as f:
                json.dump(sidecar_data, f, indent=2)
        except Exception as e:
            pass

        # Add to database
        proxy_uuid = str(uuid_module.uuid4())
        proxy_data = {
            'uuid': proxy_uuid,
            'version_group_id': version_group_id,
            'variant_name': variant_name,
            'asset_id': asset_id,
            'asset_name': asset_name,
            'asset_type': asset_type,
            'proxy_version': next_version,
            'proxy_label': proxy_label,
            'blend_path': str(blend_path),
            'glb_path': glb_path_value,
            'thumbnail_path': None,
            'polygon_count': polygon_count,
            'notes': self.proxy_notes,
            'created_date': datetime.now().isoformat(),
        }

        success = library.add_custom_proxy(proxy_data)
        if not success:
            self.report({'WARNING'}, f"Saved {proxy_label} but failed to register in database")
            return {'FINISHED'}

        # Auto-designate as active proxy and copy to .proxy.blend
        library.designate_custom_proxy(
            version_group_id=version_group_id,
            variant_name=variant_name,
            proxy_uuid=proxy_uuid,
            proxy_label=proxy_label,
            proxy_blend_path=str(blend_path),
            asset_name=asset_name,
            asset_id=asset_id,
            asset_type=asset_type,
        )

        self.report({'INFO'}, f"Saved {proxy_label} for {asset_name} ({polygon_count:,} polys)")
        return {'FINISHED'}

    def _save_proxy_blend(self, objects, filepath: str, asset_name: str):
        """Thin wrapper that forwards to the module-level helper so the
        sibling `UAL_OT_save_proxy_from_source` operator can reuse it."""
        _save_proxy_blend_file(objects, filepath, asset_name, self.include_materials)


def _save_proxy_blend_file(objects, filepath: str, asset_name: str,
                           include_materials: bool):
    """Write `objects` to a `.blend` wrapped in a collection named `asset_name`.

    Why the collection wrapper: the file is loaded later via `lib.reload()`
    in INSTANCE-mode swap workflows. Blender matches datablocks by name on
    reload, so the saved structure has to mirror what the source asset
    looked like. The collection name being identical to the asset_name is
    one of the matching keys.

    Args:
        objects:           Blender objects to save. Names must already match
                           whatever the source asset expects (callers may
                           rename around this call — see
                           `UAL_OT_save_proxy_from_source`).
        filepath:          Absolute path to write to.
        asset_name:        Name for the wrapping collection.
        include_materials: If True, include each object's materials and
                           texture image nodes in the save set.
    """
    data_blocks = set()

    # Create collection with asset name (critical for lib.reload matching)
    temp_collection = bpy.data.collections.new(asset_name)
    data_blocks.add(temp_collection)

    for obj in objects:
        # Link to temp collection
        if obj.name not in temp_collection.objects:
            temp_collection.objects.link(obj)

        data_blocks.add(obj)

        # Add object data
        if obj.data:
            data_blocks.add(obj.data)

        # Add materials
        if include_materials and hasattr(obj, 'material_slots'):
            for slot in obj.material_slots:
                if slot.material:
                    data_blocks.add(slot.material)
                    # Add textures
                    if slot.material.use_nodes:
                        for node in slot.material.node_tree.nodes:
                            if node.type == 'TEX_IMAGE' and node.image:
                                data_blocks.add(node.image)

        # Add armature if rigged
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE' and mod.object:
                data_blocks.add(mod.object)
                if mod.object.data:
                    data_blocks.add(mod.object.data)

        # Add parent chain
        parent = obj.parent
        while parent:
            data_blocks.add(parent)
            if parent.data:
                data_blocks.add(parent.data)
            parent = parent.parent

    try:
        bpy.data.libraries.write(
            filepath,
            data_blocks,
            path_remap='RELATIVE_ALL',
            compress=True,
        )
    finally:
        # Cleanup: unlink and remove temp collection
        for obj in list(temp_collection.objects):
            temp_collection.objects.unlink(obj)
        bpy.data.collections.remove(temp_collection)


# ---------------------------------------------------------------------------
# Save Proxy from Source — single proxy mesh replaces ONE chosen source mesh.
# ---------------------------------------------------------------------------
# Selection convention (matches Blender's join/parent idioms):
#     Active object       = source mesh to replace (provides the name)
#     Other selected obj  = proxy mesh (gets renamed to source's name on save)
# After save, the proxy object's original name is restored on the user's side.
# In the saved .blend, the proxy carries the source's name so `lib.reload()`
# can swap it in by name during representation swap.

class UAL_OT_save_proxy_from_source(Operator):
    """Save the non-active selected object as a proxy of the active source mesh.

    Workflow:
        1. Build your proxy mesh (cube, custom geo, whatever).
        2. Select it, then shift-click the source mesh you want to replace so
           the source becomes active.
        3. Click 'Save Proxy from Source'.
        4. The proxy gets renamed to the source's name for the .blend write,
           saved, and renamed back. Restore-original works as usual.

    Why this is needed: representation swap uses `lib.reload()` which matches
    datablocks by name. A custom proxy mesh has the wrong name; this operator
    renames it temporarily so the swap lines up.
    """
    bl_idname = "ual.save_proxy_from_source"
    bl_label = "Save Proxy from Source"
    bl_description = (
        "Save the non-active selected object as a proxy that replaces the active "
        "source mesh. Select the proxy + the source mesh (source active = last clicked)."
    )
    bl_options = {'REGISTER', 'UNDO'}

    include_materials: BoolProperty(
        name="Include Materials",
        description="Include materials in the proxy file",
        default=False,
    )

    proxy_notes: StringProperty(
        name="Notes",
        description="Optional notes for this proxy",
        default="",
    )

    @classmethod
    def poll(cls, context):
        sel = context.selected_objects
        active = context.active_object
        if active is None or len(sel) != 2 or active not in sel:
            return False
        # Source mesh must carry UAL metadata so we know which asset this is.
        return has_ual_metadata(active)

    @classmethod
    def description(cls, context, properties):
        try:
            sel = context.selected_objects
            active = context.active_object
            if active and len(sel) == 2 and has_ual_metadata(active):
                other = next((o for o in sel if o is not active), None)
                if other is not None:
                    return (
                        f"Save '{other.name}' as a proxy for source mesh "
                        f"'{active.name}'"
                    )
        except Exception:
            pass
        return cls.bl_description

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        active = context.active_object
        other = next(
            (o for o in context.selected_objects if o is not active), None,
        )
        if active and other:
            box = layout.box()
            box.label(text=f"Source mesh: {active.name}", icon='OBJECT_DATA')
            box.label(
                text=f"Proxy: {other.name}  ->  saved as '{active.name}'",
                icon='MESH_CUBE',
            )
        layout.prop(self, 'include_materials')
        layout.prop(self, 'proxy_notes')

    def execute(self, context):
        active = context.active_object
        if active is None or not has_ual_metadata(active):
            self.report({'ERROR'}, "Active object must be a source mesh with UAL metadata.")
            return {'CANCELLED'}

        proxy_obj = next(
            (o for o in context.selected_objects if o is not active), None,
        )
        if proxy_obj is None:
            self.report({'ERROR'}, "Select the proxy mesh + the source mesh (source active).")
            return {'CANCELLED'}

        metadata = read_ual_metadata(active)
        if not metadata:
            self.report({'ERROR'}, "Failed to read UAL metadata from active object.")
            return {'CANCELLED'}

        asset_name = metadata.get('asset_name', '')
        asset_type = metadata.get('asset_type', 'mesh')
        version_group_id = metadata.get('version_group_id', '')
        asset_id = metadata.get('asset_id', '') or version_group_id
        variant_name = metadata.get('variant_name', 'Base')

        if not version_group_id:
            self.report({'ERROR'}, "Asset has no version_group_id")
            return {'CANCELLED'}
        if asset_type not in ('mesh', 'rig'):
            self.report({'ERROR'}, f"Proxy not supported for {asset_type} assets")
            return {'CANCELLED'}

        library = get_library_connection()
        if not library:
            self.report({'ERROR'}, "Library connection not available")
            return {'CANCELLED'}

        next_version = library.get_next_custom_proxy_version(version_group_id, variant_name)
        proxy_label = f"p{next_version:03d}"
        proxy_folder = library.get_custom_proxy_folder_path(
            asset_id, asset_name, variant_name, proxy_label, asset_type,
        )
        blend_filename = f"{asset_name}.{proxy_label}.blend"
        blend_path = proxy_folder / blend_filename

        # The rename dance:
        #   1. Active (source) needs to keep occupying source_name in the scene,
        #      so we move it aside under a temporary name to free up the name.
        #   2. Rename proxy to source_name (now free).
        #   3. Save — the .blend captures proxy_obj WITH the source's name.
        #   4. Restore both names in finally so the user's scene is unchanged.
        source_name = active.name
        original_proxy_name = proxy_obj.name
        # Suffix unlikely to collide with anything Blender or the user has.
        active_temp_name = f"__UL_SRC__{source_name}"

        # Check for name collisions BEFORE we start moving things around —
        # if some other object in the scene already owns source_name (besides
        # the active), Blender will append .001 on rename and the proxy file
        # won't match on reload. Better to fail loud than write a broken proxy.
        existing = bpy.data.objects.get(source_name)
        if existing is not None and existing is not active:
            self.report(
                {'ERROR'},
                f"Cannot rename proxy to '{source_name}': another object with "
                f"that name exists in the scene. Rename or remove it first.",
            )
            return {'CANCELLED'}

        try:
            active.name = active_temp_name
            proxy_obj.name = source_name
            _save_proxy_blend_file(
                [proxy_obj], str(blend_path), asset_name, self.include_materials,
            )
        except Exception as e:
            self.report({'ERROR'}, f"Failed to save proxy: {e}")
            return {'CANCELLED'}
        finally:
            # Restore both names in the user's scene. The .blend on disk
            # already has the renamed proxy frozen in.
            try:
                proxy_obj.name = original_proxy_name
            except Exception:
                pass
            try:
                active.name = source_name
            except Exception:
                pass

        # Companion .glb for app-side 3D preview (best-effort; runs AFTER
        # name restoration — only the .blend needs the renamed-for-swap
        # name; the .glb is a separate preview artifact).
        glb_path = blend_path.with_suffix('.glb')
        glb_ok = _export_proxy_glb([proxy_obj], str(glb_path))
        glb_path_value = str(glb_path) if glb_ok else None

        # Polycount for the proxy (single-object proxy)
        polygon_count = 0
        if proxy_obj.type == 'MESH' and proxy_obj.data:
            polygon_count = len(proxy_obj.data.polygons)

        # Sidecar
        sidecar_path = proxy_folder / f"{asset_name}.{proxy_label}.json"
        sidecar_data = {
            'proxy_label': proxy_label,
            'proxy_version': next_version,
            'asset_name': asset_name,
            'asset_type': asset_type,
            'variant_name': variant_name,
            'version_group_id': version_group_id,
            'asset_id': asset_id,
            'polygon_count': polygon_count,
            'object_count': 1,
            'object_names': [source_name],
            'source_replaced': source_name,
            'proxy_source_object': original_proxy_name,
            'notes': self.proxy_notes,
            'created_date': datetime.now().isoformat(),
        }
        try:
            with open(str(sidecar_path), 'w') as f:
                json.dump(sidecar_data, f, indent=2)
        except Exception:
            pass

        # Register in DB
        proxy_uuid = str(uuid_module.uuid4())
        proxy_data = {
            'uuid': proxy_uuid,
            'version_group_id': version_group_id,
            'variant_name': variant_name,
            'asset_id': asset_id,
            'asset_name': asset_name,
            'asset_type': asset_type,
            'proxy_version': next_version,
            'proxy_label': proxy_label,
            'blend_path': str(blend_path),
            'glb_path': glb_path_value,
            'thumbnail_path': None,
            'polygon_count': polygon_count,
            'notes': self.proxy_notes,
            'created_date': datetime.now().isoformat(),
        }
        success = library.add_custom_proxy(proxy_data)
        if not success:
            self.report(
                {'WARNING'},
                f"Saved {proxy_label} but failed to register in database",
            )
            return {'FINISHED'}

        library.designate_custom_proxy(
            version_group_id=version_group_id,
            variant_name=variant_name,
            proxy_uuid=proxy_uuid,
            proxy_label=proxy_label,
            proxy_blend_path=str(blend_path),
            asset_name=asset_name,
            asset_id=asset_id,
            asset_type=asset_type,
        )

        self.report(
            {'INFO'},
            f"Saved {proxy_label}: '{original_proxy_name}' as proxy for "
            f"'{source_name}' ({polygon_count:,} polys)",
        )
        return {'FINISHED'}


# Registration
classes = [
    UAL_OT_update_proxy,
    UAL_OT_save_proxy_from_source,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_OT_update_proxy',
    'UAL_OT_save_proxy_from_source',
    'register',
    'unregister',
]
