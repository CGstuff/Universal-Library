"""
Version History Operators

Provides version history viewing in Blender UI.
Shows all versions of an asset with thumbnails and metadata.
"""

import bpy
from bpy.types import Operator, UIList, PropertyGroup
from bpy.props import (
    StringProperty, IntProperty, CollectionProperty,
    BoolProperty, EnumProperty
)

from ..utils.library_connection import get_library_connection


class UAL_VersionItem(PropertyGroup):
    """Property group representing a version in the timeline"""
    uuid: StringProperty(name="UUID")
    name: StringProperty(name="Name")
    version_label: StringProperty(name="Version Label")
    version: IntProperty(name="Version Number")
    thumbnail_path: StringProperty(name="Thumbnail Path")
    polygon_count: IntProperty(name="Polygon Count")
    material_count: IntProperty(name="Material Count")
    is_latest: BoolProperty(name="Is Latest")
    is_cold: BoolProperty(name="In Cold Storage")
    representation_type: StringProperty(name="Representation")
    created_date: StringProperty(name="Created")
    status: StringProperty(name="Status")
    has_skeleton: BoolProperty(name="Has Skeleton")
    has_animations: BoolProperty(name="Has Animations")
    # Variant system
    variant_name: StringProperty(name="Variant Name", default="Base")


class UAL_UL_version_list(UIList):
    """UIList for displaying version history"""
    bl_idname = "UAL_UL_version_list"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            # Version label with status indicator
            if item.is_latest:
                row.label(text=f"{item.version_label}", icon='CHECKMARK')
            elif item.is_cold:
                row.label(text=f"{item.version_label}", icon='FREEZE')
            else:
                row.label(text=item.version_label, icon='FILE')

            # Representation type badge
            rep_icons = {
                'model': 'MESH_DATA',
                'lookdev': 'MATERIAL',
                'rig': 'ARMATURE_DATA',
                'final': 'CHECKMARK',
                'none': 'BLANK1',
            }
            rep_type = item.representation_type.lower() if item.representation_type else 'none'
            rep_icon = rep_icons.get(rep_type, 'BLANK1')
            row.label(text=rep_type.capitalize() if rep_type != 'none' else '', icon=rep_icon)

            # Polygon count
            sub = row.row()
            sub.scale_x = 0.8
            if item.polygon_count > 0:
                sub.label(text=f"{item.polygon_count:,}")
            else:
                sub.label(text="-")

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.version_label, icon='FILE')


class UAL_OT_show_version_history(Operator):
    """Show version history for the selected asset"""
    bl_idname = "ual.show_version_history"
    bl_label = "Version History"
    bl_description = "View all versions of this asset"
    bl_options = {'REGISTER'}

    version_group_id: StringProperty(
        name="Version Group ID",
        description="UUID of the version group to display",
        default=""
    )

    asset_name: StringProperty(
        name="Asset Name",
        description="Name of the asset",
        default=""
    )

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        # Get version_group_id from selected object if not provided
        if not self.version_group_id and context.active_object:
            obj = context.active_object
            self.version_group_id = obj.get("ual_version_group_id", "")
            self.asset_name = obj.get("ual_asset_name", "")

        if not self.version_group_id:
            self.report({'ERROR'}, "No version history available for this asset")
            return {'CANCELLED'}

        # Load versions into scene property
        self._load_versions(context)

        return context.window_manager.invoke_popup(self, width=450)

    def _load_versions(self, context):
        """Load version history into scene collection property"""
        library = get_library_connection()
        versions = library.get_version_history(self.version_group_id)

        # Clear existing items
        context.scene.ual_version_items.clear()

        for v in versions:
            item = context.scene.ual_version_items.add()
            item.uuid = v.get('uuid', '')
            item.name = v.get('name', '')
            item.version_label = v.get('version_label', f"v{v.get('version', 1):03d}")
            item.version = v.get('version', 1)
            item.thumbnail_path = v.get('thumbnail_path', '')
            item.polygon_count = v.get('polygon_count', 0) or 0
            item.material_count = v.get('material_count', 0) or 0
            item.is_latest = v.get('is_latest', 0) == 1
            item.is_cold = v.get('is_cold', 0) == 1
            item.representation_type = v.get('representation_type', 'none') or 'none'
            item.status = v.get('status', '') or ''
            item.has_skeleton = v.get('has_skeleton', 0) == 1
            item.has_animations = v.get('has_animations', 0) == 1
            item.variant_name = v.get('variant_name', 'Base') or 'Base'

            # Format created date
            created = v.get('created_date', '')
            if created:
                item.created_date = str(created)[:19]
            else:
                item.created_date = ''

        # Set first item as selected
        if context.scene.ual_version_items:
            context.scene.ual_version_index = 0

    def draw(self, context):
        layout = self.layout

        # Header with asset name
        header_row = layout.row()
        header_row.label(text=f"Version History: {self.asset_name or 'Asset'}", icon='TIME')

        version_count = len(context.scene.ual_version_items)
        header_row.label(text=f"({version_count} version{'s' if version_count != 1 else ''})")

        # Show variant name if not Base (get from first item)
        if context.scene.ual_version_items:
            first_item = context.scene.ual_version_items[0]
            if first_item.variant_name and first_item.variant_name != 'Base':
                variant_row = layout.row()
                variant_row.label(text=f"Variant: {first_item.variant_name}", icon='DUPLICATE')

        layout.separator()

        # Version list with headers
        header = layout.row()
        header.label(text="Version")
        header.label(text="Type")
        header.label(text="Polygons")

        # Version list
        row = layout.row()
        row.template_list(
            "UAL_UL_version_list",
            "versions",
            context.scene, "ual_version_items",
            context.scene, "ual_version_index",
            rows=5
        )

        # Selected version details
        if context.scene.ual_version_items:
            idx = context.scene.ual_version_index
            if 0 <= idx < len(context.scene.ual_version_items):
                item = context.scene.ual_version_items[idx]

                layout.separator()

                box = layout.box()
                # Show variant in selected label if not Base
                if item.variant_name and item.variant_name != 'Base':
                    box.label(text=f"Selected: {item.variant_name} {item.version_label}", icon='INFO')
                else:
                    box.label(text=f"Selected: {item.version_label}", icon='INFO')

                col = box.column(align=True)

                # Stats row
                row = col.row()
                row.label(text=f"Polygons: {item.polygon_count:,}")
                row.label(text=f"Materials: {item.material_count}")

                # Features row
                row = col.row()
                if item.has_skeleton:
                    row.label(text="Skeleton", icon='ARMATURE_DATA')
                if item.has_animations:
                    row.label(text="Animated", icon='ACTION')

                # Status
                if item.created_date:
                    col.label(text=f"Created: {item.created_date}")

                if item.is_cold:
                    col.label(text="Status: Cold Storage", icon='FREEZE')
                elif item.is_latest:
                    col.label(text="Status: Latest", icon='CHECKMARK')

                # Action buttons
                layout.separator()
                row = layout.row(align=True)
                op = row.operator("ual.import_from_library", text="Import This Version", icon='IMPORT')
                op.asset_uuid = item.uuid

    def execute(self, context):
        return {'FINISHED'}


class UAL_OT_import_version(Operator):
    """Import a specific version from history"""
    bl_idname = "ual.import_version"
    bl_label = "Import Version"
    bl_description = "Import this specific version of the asset"
    bl_options = {'REGISTER', 'UNDO'}

    asset_uuid: StringProperty(
        name="Asset UUID",
        description="UUID of the version to import",
        default=""
    )

    def execute(self, context):
        if not self.asset_uuid:
            self.report({'ERROR'}, "No asset UUID provided")
            return {'CANCELLED'}

        # Call the main import operator
        bpy.ops.ual.import_from_library(asset_uuid=self.asset_uuid)
        return {'FINISHED'}


# Registration
classes = [
    UAL_VersionItem,
    UAL_UL_version_list,
    UAL_OT_show_version_history,
    UAL_OT_import_version,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Register scene properties for version list
    bpy.types.Scene.ual_version_items = CollectionProperty(type=UAL_VersionItem)
    bpy.types.Scene.ual_version_index = IntProperty(name="Version Index", default=0)


def unregister():
    # Unregister scene properties
    del bpy.types.Scene.ual_version_items
    del bpy.types.Scene.ual_version_index

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_VersionItem',
    'UAL_UL_version_list',
    'UAL_OT_show_version_history',
    'UAL_OT_import_version',
    'register',
    'unregister',
]
