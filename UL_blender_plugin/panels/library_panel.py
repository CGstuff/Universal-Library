"""
Library Panel - Sidebar UI for Universal Library

Provides a 3D View sidebar panel for exporting assets and settings.
Import is handled directly from the desktop app via queue system.
"""

import bpy
from bpy.types import Panel, PropertyGroup
from bpy.props import EnumProperty

from ..utils.library_connection import get_library_connection
from ..utils.metadata_handler import has_ual_metadata, read_ual_metadata
from ..utils.icon_loader import get_icon_id, Icons
from ..operators.material_preview import PREVIEW_SCENE_NAME


class UAL_SceneProperties(PropertyGroup):
    """Scene-level properties for Universal Library"""
    import_placement: EnumProperty(
        name="Placement",
        description="Where to place imported assets",
        items=[
            ('CURSOR', "3D Cursor", "Place at 3D cursor location"),
            ('ORIGIN', "World Origin", "Place at world origin (0, 0, 0)"),
        ],
        default='CURSOR'
    )


class UAL_PT_main_panel(Panel):
    """Main sidebar panel for Universal Library"""
    bl_label = "Asset Library"
    bl_idname = "UAL_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Library"

    def draw(self, context):
        layout = self.layout

        # Library status
        library = get_library_connection()
        status_box = layout.box()
        if library.library_path.exists():
            assets = library.get_all_assets()
            status_box.label(text=f"Library: {len(assets)} assets", icon='CHECKMARK')
            # Show path (truncated if long)
            path_str = str(library.library_path)
            if len(path_str) > 35:
                path_str = "..." + path_str[-32:]
            status_box.label(text=path_str, icon='FILE_FOLDER')
        else:
            status_box.label(text="Library not connected", icon='ERROR')
            op = status_box.operator("preferences.addon_show", text="Open Preferences")
            op.module = __package__.split('.')[0]

        layout.separator()

        # Launch Desktop App - Prominent button with icon
        launch_box = layout.box()
        launch_row = launch_box.row()
        launch_row.scale_y = 2.0

        # Use custom icon if available
        icon_id = get_icon_id(Icons.LAUNCH_APP)
        if icon_id:
            launch_row.operator("ual.browse_library", text="  Open Desktop App", icon_value=icon_id)
        else:
            launch_row.operator("ual.browse_library", text="Open Desktop App", icon='WINDOW')

        # Import placement option
        layout.separator()
        placement_box = layout.box()
        placement_box.label(text="Import Settings", icon='IMPORT')
        placement_box.prop(context.scene.ual_props, "import_placement", text="Place at")


class UAL_PT_export_panel(Panel):
    """Panel for exporting to library"""
    bl_label = "Export"
    bl_idname = "UAL_PT_export_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Library"
    bl_parent_id = "UAL_PT_main_panel"

    def draw(self, context):
        layout = self.layout

        # Selection info
        selected = context.selected_objects
        if selected:
            layout.label(text=f"{len(selected)} object(s) selected")

            # Large prominent export button - hard to miss
            col = layout.column()
            col.scale_y = 2.0  # Double height for prominence
            col.operator(
                "ual.export_to_library",
                text=f"EXPORT {len(selected)} OBJECT(S)",
                icon='EXPORT'
            )

            # Check if active object has materials - show material export option
            obj = context.active_object
            if obj and hasattr(obj, 'material_slots') and obj.material_slots:
                mat_count = sum(1 for slot in obj.material_slots if slot.material)
                if mat_count > 0:
                    layout.separator()
                    layout.label(text=f"{mat_count} material(s) on object")
                    row = layout.row(align=True)
                    row.operator("ual.export_material", text="Export Material", icon='MATERIAL')
                    row.operator("ual.open_material_preview", text="", icon='RESTRICT_RENDER_OFF')
        else:
            layout.label(text="Select objects to export", icon='INFO')

        # Collection export - shown when active collection is not scene root
        layout.separator()
        collection = context.collection
        if collection and collection != context.scene.collection:
            box = layout.box()
            box.label(text=f"Collection: {collection.name}", icon='OUTLINER_COLLECTION')
            obj_count = len(collection.objects)
            child_count = len(collection.children)
            info_text = f"{obj_count} objects"
            if child_count > 0:
                info_text += f", {child_count} nested"
            box.label(text=info_text)
            box.operator("ual.export_collection", text="Export Collection", icon='EXPORT')
        else:
            layout.label(text="Active collection: Scene Root", icon='OUTLINER_COLLECTION')

        # Scene export - always visible
        layout.separator()
        scene_box = layout.box()
        scene_box.label(text=f"Scene: {context.scene.name}", icon='SCENE_DATA')
        scene_box.operator("ual.export_scene", text="Export Scene", icon='EXPORT')


class UAL_PT_material_preview_panel(Panel):
    """Panel for material preview controls - shows when in preview scene"""
    bl_label = "Material Preview"
    bl_idname = "UAL_PT_material_preview_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Library"
    bl_parent_id = "UAL_PT_main_panel"

    @classmethod
    def poll(cls, context):
        """Only show when in material preview scene"""
        return context.scene.name.startswith(PREVIEW_SCENE_NAME)

    def draw(self, context):
        layout = self.layout

        # Preview scene indicator
        box = layout.box()
        box.label(text="Preview Mode Active", icon='RESTRICT_RENDER_OFF')

        # Show material being previewed (if we can find it on the preview ball)
        for obj in context.scene.objects:
            if obj.name.startswith("UAL_PreviewBall"):
                if obj.data.materials:
                    mat = obj.data.materials[0]
                    if mat:
                        box.label(text=f"Material: {mat.name}")
                break

        layout.separator()

        # Close preview button
        col = layout.column()
        col.scale_y = 1.5
        col.alert = False
        col.operator("ual.close_material_preview", text="Close Preview", icon='PANEL_CLOSE')


class UAL_PT_review_panel(Panel):
    """Panel for asset review - capture screenshots for review"""
    bl_label = "Review"
    bl_idname = "UAL_PT_review_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Library"
    bl_parent_id = "UAL_PT_main_panel"

    @classmethod
    def poll(cls, context):
        """Only show when a UAL asset is selected and NOT in preview scene"""
        if context.scene.name.startswith(PREVIEW_SCENE_NAME):
            return False
        obj = context.active_object
        return obj and has_ual_metadata(obj)

    def draw(self, context):
        layout = self.layout

        obj = context.active_object
        metadata = read_ual_metadata(obj)

        if metadata:
            # Asset info header
            box = layout.box()
            asset_name = metadata.get('asset_name', 'Unknown')
            version_label = metadata.get('version_label', 'v001')
            variant_name = metadata.get('variant_name', 'Base')

            box.label(text=asset_name, icon='OBJECT_DATA')
            row = box.row()
            row.label(text=f"Version: {version_label}")
            if variant_name != 'Base':
                row.label(text=f"Variant: {variant_name}")

            layout.separator()

            # Thumbnail section
            thumb_box = layout.box()
            thumb_box.label(text="Thumbnail", icon='IMAGE_DATA')
            
            # Check if helper is enabled
            helper_enabled = getattr(obj, 'ual_thumbnail_helper_enabled', False)
            
            # Toggle helper button
            row = thumb_box.row(align=True)
            toggle_op = row.operator(
                "ual.toggle_thumbnail_helper",
                text="Frame Helper" if not helper_enabled else "Helper Active",
                icon='CON_CAMERASOLVER' if not helper_enabled else 'CHECKMARK',
                depress=helper_enabled
            )
            
            if helper_enabled:
                # Show hint
                thumb_box.label(text="Adjust the frame, then capture", icon='INFO')
            
            # Capture button
            col = thumb_box.column()
            col.scale_y = 1.5
            col.operator(
                "ual.update_thumbnail",
                text="Capture Thumbnail",
                icon='RESTRICT_RENDER_OFF'
            )

            layout.separator()

            # Screenshot capture button
            col = layout.column()
            col.scale_y = 1.5
            col.operator(
                "ual.capture_review_screenshot",
                text="Capture Screenshot",
                icon='RESTRICT_RENDER_OFF'
            )

            layout.label(text="Captures viewport for review", icon='INFO')


class UAL_PT_linked_assets_panel(Panel):
    """Panel for managing linked library assets"""
    bl_label = "Linked Assets"
    bl_idname = "UAL_PT_linked_assets_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Library"
    bl_parent_id = "UAL_PT_main_panel"

    @classmethod
    def poll(cls, context):
        """Show when there are linked libraries"""
        import bpy
        return len(bpy.data.libraries) > 0

    def draw(self, context):
        layout = self.layout
        import bpy

        # Count UAL current-reference libraries vs other libraries
        ual_libs = []
        other_libs = []
        for lib in bpy.data.libraries:
            if lib.filepath:
                if '.current.blend' in lib.filepath:
                    ual_libs.append(lib)
                else:
                    other_libs.append(lib)

        # Show counts
        box = layout.box()
        if ual_libs:
            box.label(text=f"UAL Auto-Update Links: {len(ual_libs)}", icon='FILE_REFRESH')
        if other_libs:
            box.label(text=f"Other Libraries: {len(other_libs)}", icon='LIBRARY_DATA_DIRECT')

        layout.separator()

        # Reload buttons
        col = layout.column(align=True)

        # Main reload button - reload UAL assets
        if ual_libs:
            row = col.row()
            row.scale_y = 1.5
            row.operator(
                "ual.reload_current_assets",
                text=f"Reload UAL Assets ({len(ual_libs)})",
                icon='FILE_REFRESH'
            )
            col.label(text="Updates to latest versions", icon='INFO')

        col.separator()

        # Secondary actions
        row = col.row(align=True)
        row.operator("ual.reload_all_libraries", text="Reload All", icon='FILE_REFRESH')
        row.operator("ual.list_linked_libraries", text="List", icon='CONSOLE')


class UAL_PT_settings_panel(Panel):
    """Panel for addon settings"""
    bl_label = "Settings"
    bl_idname = "UAL_PT_settings_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Library"
    bl_parent_id = "UAL_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons.get(__package__.split('.')[0])

        if prefs:
            layout.prop(prefs.preferences, "library_path")

        # Library info
        library = get_library_connection()
        layout.label(text=f"Path: {library.library_path}")

        # Queue status
        try:
            from ..utils.queue_client import get_queue_client
            client = get_queue_client()
            pending = client.get_pending_count()
            if pending > 0:
                layout.label(text=f"Pending imports: {pending}", icon='TIME')
        except Exception:
            pass

        layout.separator()

        # Viewport overlay toggle
        overlay_box = layout.box()
        overlay_box.label(text="Viewport Display:", icon='VIEW3D')

        # Check overlay state from scene property
        overlay_enabled = context.scene.get('ual_overlay_enabled', False)

        row = overlay_box.row()
        row.operator(
            "ual.toggle_asset_overlay",
            text="Hide Asset Labels" if overlay_enabled else "Show Asset Labels",
            icon='HIDE_ON' if overlay_enabled else 'HIDE_OFF',
            depress=overlay_enabled
        )

        if overlay_enabled:
            overlay_box.operator("ual.refresh_overlay", text="Refresh", icon='FILE_REFRESH')


# Registration
classes = [
    UAL_SceneProperties,
    UAL_PT_main_panel,
    UAL_PT_export_panel,
    UAL_PT_material_preview_panel,
    UAL_PT_review_panel,
    UAL_PT_linked_assets_panel,
    UAL_PT_settings_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Register scene properties
    bpy.types.Scene.ual_props = bpy.props.PointerProperty(type=UAL_SceneProperties)


def unregister():
    # Unregister scene properties
    if hasattr(bpy.types.Scene, 'ual_props'):
        del bpy.types.Scene.ual_props

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_SceneProperties',
    'UAL_PT_main_panel',
    'UAL_PT_export_panel',
    'UAL_PT_material_preview_panel',
    'UAL_PT_review_panel',
    'UAL_PT_linked_assets_panel',
    'UAL_PT_settings_panel',
    'register',
    'unregister',
]
