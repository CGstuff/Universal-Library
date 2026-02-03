"""
Material Preview Operators

Provides fast material preview rendering using a bundled preview scene
with pre-configured camera, lighting, and material ball.
"""

import bpy
from pathlib import Path
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty


# Constants
PREVIEW_COLLECTION_NAME = "UAL_MaterialPreview"
PREVIEW_BALL_NAME = "UAL_PreviewBall"
PREVIEW_CAMERA_NAME = "UAL_PreviewCamera"
PREVIEW_SCENE_NAME = "UAL_MaterialPreview"


def get_preview_blend_path() -> Path:
    """Get path to bundled material preview .blend file."""
    # Path relative to this file: ../resources/material_preview.blend
    operators_dir = Path(__file__).parent
    plugin_dir = operators_dir.parent
    return plugin_dir / "resources" / "material_preview.blend"


def get_material_items(self, context):
    """Get list of materials for enum property."""
    items = []

    # First add materials from active object
    if context.active_object and hasattr(context.active_object, 'material_slots'):
        for slot in context.active_object.material_slots:
            if slot.material and slot.material.name not in [i[0] for i in items]:
                items.append((slot.material.name, slot.material.name,
                             f"Material from {context.active_object.name}"))

    # Then add all other materials in the scene
    for mat in bpy.data.materials:
        if mat.name not in [i[0] for i in items] and not mat.name.startswith('_'):
            items.append((mat.name, mat.name, "Scene material"))

    if not items:
        items.append(('NONE', "No Materials", "No materials found"))

    return items


class UAL_OT_open_material_preview(Operator):
    """Open material preview scene for fast rendering"""
    bl_idname = "ual.open_material_preview"
    bl_label = "Open Material Preview"
    bl_description = "Open a preview scene with the selected material on a preview ball"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: EnumProperty(
        name="Material",
        description="Select material to preview",
        items=get_material_items
    )

    # Store original state for returning later
    _original_scene_name: str = ""
    _original_view_perspective: str = "PERSP"
    _original_shading_type: str = "SOLID"
    _original_show_overlays: bool = True

    @classmethod
    def poll(cls, context):
        """Check if any materials exist."""
        return len(bpy.data.materials) > 0

    def invoke(self, context, event):
        """Show material selection dialog."""
        # Set default to active object's material if available
        if context.active_object and hasattr(context.active_object, 'material_slots'):
            if context.active_object.material_slots:
                first_mat = context.active_object.material_slots[0].material
                if first_mat:
                    self.material_name = first_mat.name

        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        """Draw dialog UI."""
        layout = self.layout
        layout.prop(self, "material_name")

    def execute(self, context):
        """Execute the preview scene setup."""
        if not self.material_name or self.material_name == 'NONE':
            self.report({'ERROR'}, "No material selected")
            return {'CANCELLED'}

        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'ERROR'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}

        # Get preview blend path
        preview_blend = get_preview_blend_path()
        if not preview_blend.exists():
            self.report({'ERROR'}, f"Preview template not found: {preview_blend}")
            return {'CANCELLED'}

        # Store original scene
        original_scene = context.window.scene
        UAL_OT_open_material_preview._original_scene_name = original_scene.name

        # Check if preview scene already exists
        existing_preview = bpy.data.scenes.get(PREVIEW_SCENE_NAME)
        if existing_preview:
            # Reuse existing preview scene
            preview_scene = existing_preview
        else:
            # Create new preview scene
            preview_scene = bpy.data.scenes.new(PREVIEW_SCENE_NAME)

            # Append the preview collection from bundled file
            if not self._append_preview_collection(str(preview_blend), preview_scene):
                bpy.data.scenes.remove(preview_scene)
                self.report({'ERROR'}, "Failed to append preview collection")
                return {'CANCELLED'}

        # Find the preview ball
        ball = None
        for obj in preview_scene.objects:
            if obj.name.startswith(PREVIEW_BALL_NAME):
                ball = obj
                break

        if not ball:
            self.report({'ERROR'}, f"Preview ball '{PREVIEW_BALL_NAME}' not found in scene")
            return {'CANCELLED'}

        # Assign material to preview ball
        if ball.data.materials:
            ball.data.materials[0] = material
        else:
            ball.data.materials.append(material)

        # Set scene camera
        camera = None
        for obj in preview_scene.objects:
            if obj.name.startswith(PREVIEW_CAMERA_NAME):
                camera = obj
                break

        if camera:
            preview_scene.camera = camera

        # Copy render settings from original scene
        preview_scene.render.resolution_x = 512
        preview_scene.render.resolution_y = 512
        preview_scene.render.resolution_percentage = 100

        # Switch to preview scene
        context.window.scene = preview_scene

        # Set viewport to camera view and material/rendered mode
        self._setup_viewport(context)

        self.report({'INFO'}, f"Opened preview for material '{material.name}'")
        return {'FINISHED'}

    def _append_preview_collection(self, blend_path: str, target_scene) -> bool:
        """Append preview collection from bundled .blend file."""
        try:
            blend_path_normalized = blend_path.replace('\\', '/')

            # Find available collections in the file
            with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
                available_collections = list(data_from.collections)

            if PREVIEW_COLLECTION_NAME not in available_collections:
                if not available_collections:
                    return False
                collection_to_append = available_collections[0]
            else:
                collection_to_append = PREVIEW_COLLECTION_NAME

            # Append the collection
            directory = f"{blend_path_normalized}/Collection/"
            bpy.ops.wm.append(
                directory=directory,
                files=[{"name": collection_to_append}],
                link=False,
                autoselect=False,
                active_collection=False,
                instance_collections=False,
            )

            # Find the appended collection
            appended_collection = bpy.data.collections.get(collection_to_append)
            if not appended_collection:
                # Try with suffix
                for col in bpy.data.collections:
                    if col.name.startswith(collection_to_append):
                        appended_collection = col
                        break

            if appended_collection:
                # Link collection to target scene
                target_scene.collection.children.link(appended_collection)
                return True

            return False

        except Exception:
            import traceback
            traceback.print_exc()
            return False

    def _setup_viewport(self, context):
        """Set up viewport for preview rendering."""
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        # Store original viewport state before changing
                        UAL_OT_open_material_preview._original_view_perspective = space.region_3d.view_perspective
                        UAL_OT_open_material_preview._original_shading_type = space.shading.type
                        UAL_OT_open_material_preview._original_show_overlays = space.overlay.show_overlays

                        # Set to camera view (only if not already in camera view)
                        if space.region_3d.view_perspective != 'CAMERA':
                            for region in area.regions:
                                if region.type == 'WINDOW':
                                    with context.temp_override(area=area, region=region):
                                        bpy.ops.view3d.view_camera()
                                    break

                        # Keep current shading if already MATERIAL or RENDERED, otherwise use MATERIAL
                        if space.shading.type not in ('MATERIAL', 'RENDERED'):
                            space.shading.type = 'MATERIAL'

                        space.overlay.show_overlays = False
                        break
                break


class UAL_OT_close_material_preview(Operator):
    """Close material preview and return to original scene"""
    bl_idname = "ual.close_material_preview"
    bl_label = "Close Material Preview"
    bl_description = "Close the material preview scene and return to original scene"
    bl_options = {'REGISTER', 'UNDO'}

    cleanup_scene: bpy.props.BoolProperty(
        name="Delete Preview Scene",
        description="Delete the preview scene (uncheck to keep for later)",
        default=True
    )

    @classmethod
    def poll(cls, context):
        """Check if we're in a preview scene."""
        return context.scene.name == PREVIEW_SCENE_NAME or context.scene.name.startswith(PREVIEW_SCENE_NAME)

    def execute(self, context):
        """Close preview and cleanup."""
        preview_scene = context.scene

        # Return to original scene
        original_scene_name = UAL_OT_open_material_preview._original_scene_name
        original_scene = bpy.data.scenes.get(original_scene_name)

        if original_scene:
            context.window.scene = original_scene
        else:
            # Fallback to first non-preview scene
            for scene in bpy.data.scenes:
                if not scene.name.startswith(PREVIEW_SCENE_NAME):
                    context.window.scene = scene
                    break

        # Restore viewport state
        self._restore_viewport(context)

        # Cleanup preview scene if requested
        if self.cleanup_scene and preview_scene.name.startswith(PREVIEW_SCENE_NAME):
            # Gather all collections from the preview scene BEFORE any removal
            collections_to_remove = []
            for col in preview_scene.collection.children:
                collections_to_remove.append(col)
                # Also gather nested collections recursively
                self._gather_nested_collections(col, collections_to_remove)

            # Step 1: Remove all objects from collections first (clear references)
            for col in collections_to_remove:
                # Clear all objects from this collection
                for obj in list(col.objects):
                    # Clear material references first
                    if obj.data and hasattr(obj.data, 'materials'):
                        obj.data.materials.clear()
                    # Unlink from collection
                    col.objects.unlink(obj)

            # Step 2: Remove objects from scene
            for obj in list(preview_scene.objects):
                if obj.data and hasattr(obj.data, 'materials'):
                    obj.data.materials.clear()
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except ReferenceError:
                    pass

            # Step 3: Unlink collections from scene (break parent reference)
            for col in list(preview_scene.collection.children):
                try:
                    preview_scene.collection.children.unlink(col)
                except Exception:
                    pass

            # Step 4: Remove the scene
            bpy.data.scenes.remove(preview_scene)

            # Step 5: Remove collections (in reverse order - children first)
            for col in reversed(collections_to_remove):
                try:
                    # Clear fake_user if set
                    if col.use_fake_user:
                        col.use_fake_user = False
                    # Force zero users by clearing all child links
                    for child in list(col.children):
                        col.children.unlink(child)
                    # Now remove
                    bpy.data.collections.remove(col)
                except ReferenceError:
                    pass
                except Exception:
                    pass

            # Step 6: Final cleanup - purge orphan data
            # This forces Blender to actually release the data blocks
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

        # Clean up "Appended Data" collection if empty (after all cleanup)
        appended_col = bpy.data.collections.get("Appended Data")
        if appended_col and len(appended_col.objects) == 0 and len(appended_col.children) == 0:
            bpy.data.collections.remove(appended_col)

        self.report({'INFO'}, "Closed material preview")
        return {'FINISHED'}

    def _gather_nested_collections(self, collection, result_list):
        """Recursively gather all nested collections."""
        for child in collection.children:
            if child not in result_list:
                result_list.append(child)
                self._gather_nested_collections(child, result_list)

    def _restore_viewport(self, context):
        """Restore viewport to original state."""
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        # Restore original viewport state
                        space.region_3d.view_perspective = UAL_OT_open_material_preview._original_view_perspective
                        space.shading.type = UAL_OT_open_material_preview._original_shading_type
                        space.overlay.show_overlays = UAL_OT_open_material_preview._original_show_overlays
                        break
                break


class UAL_OT_render_material_preview(Operator):
    """Render material preview thumbnail"""
    bl_idname = "ual.render_material_preview"
    bl_label = "Render Material Preview"
    bl_description = "Render the current material preview to a thumbnail file"
    bl_options = {'REGISTER'}

    filepath: StringProperty(
        name="Output Path",
        description="Path to save the rendered thumbnail",
        default="",
        subtype='FILE_PATH'
    )

    @classmethod
    def poll(cls, context):
        """Check if we're in a preview scene with camera."""
        return (context.scene.name.startswith(PREVIEW_SCENE_NAME) and
                context.scene.camera is not None)

    def invoke(self, context, event):
        """Show file browser for output path."""
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        """Render the preview thumbnail."""
        if not self.filepath:
            self.report({'ERROR'}, "No output path specified")
            return {'CANCELLED'}

        scene = context.scene
        render = scene.render

        # Store original settings
        original = {
            'filepath': render.filepath,
            'file_format': render.image_settings.file_format,
            'color_mode': render.image_settings.color_mode,
        }

        # Store media_type if available (Blender 4.5+/5.0)
        if hasattr(render.image_settings, 'media_type'):
            original['media_type'] = render.image_settings.media_type

        try:
            # Configure for PNG output
            render.filepath = self.filepath
            if hasattr(render.image_settings, 'media_type'):
                render.image_settings.media_type = 'IMAGE'
            render.image_settings.file_format = 'PNG'
            render.image_settings.color_mode = 'RGBA'

            # Find 3D viewport for OpenGL render
            view3d_area = None
            view3d_region = None
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    view3d_area = area
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            view3d_region = region
                            break
                    break

            if view3d_area and view3d_region:
                # Use fast OpenGL viewport render
                with context.temp_override(area=view3d_area, region=view3d_region):
                    bpy.ops.render.opengl(write_still=True)
                self.report({'INFO'}, f"Saved preview to: {self.filepath}")
            else:
                self.report({'ERROR'}, "No 3D viewport found")
                return {'CANCELLED'}

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Render failed: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        finally:
            # Restore original settings
            if 'media_type' in original and hasattr(render.image_settings, 'media_type'):
                render.image_settings.media_type = original['media_type']
            render.filepath = original['filepath']
            render.image_settings.file_format = original['file_format']
            render.image_settings.color_mode = original['color_mode']


# Registration
classes = [
    UAL_OT_open_material_preview,
    UAL_OT_close_material_preview,
    UAL_OT_render_material_preview,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_OT_open_material_preview',
    'UAL_OT_close_material_preview',
    'UAL_OT_render_material_preview',
    'get_preview_blend_path',
    'PREVIEW_COLLECTION_NAME',
    'PREVIEW_BALL_NAME',
    'PREVIEW_CAMERA_NAME',
    'PREVIEW_SCENE_NAME',
    'register',
    'unregister',
]
