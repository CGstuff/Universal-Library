"""
Save Proxy Version Operator - Save geometry as a proxy version.

Workflow:
1. Import an asset from the library
2. Create or edit proxy geometry (simplify, decimate, etc.)
3. Select the objects (must include at least one with UAL metadata)
4. Click "Save Proxy Version" to save as a new proxy version (p001, p002, etc.)

The proxy is automatically designated as the active proxy representation.
Proxy files can be selected in the desktop app for runtime swapping.
"""

import bpy
import json
import uuid as uuid_module
from bpy.types import Operator
from bpy.props import BoolProperty, StringProperty
from pathlib import Path
from datetime import datetime

from ..utils.metadata_handler import has_ual_metadata, read_ual_metadata
from ..utils.library_connection import get_library_connection


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
        """
        Save objects to a .blend file.

        Creates a collection with the asset name containing the objects.
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
            if self.include_materials and hasattr(obj, 'material_slots'):
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


# Registration
classes = [
    UAL_OT_update_proxy,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_OT_update_proxy',
    'register',
    'unregister',
]
