"""
Update Thumbnail Operator

Allows updating the thumbnail for an asset that's already in the library.
Works by reading UAL metadata from the selected object to find the asset.

Also includes the thumbnail helper toggle operator for interactive framing.
"""

import bpy
from bpy.types import Operator
from bpy.props import BoolProperty
from pathlib import Path
from mathutils import Matrix, Vector, Quaternion

from ..utils.library_connection import get_library_connection
from ..utils.metadata_handler import has_ual_metadata, read_ual_metadata
from ..utils.viewport_capture import capture_viewport_thumbnail, get_objects_bbox_3d


class UAL_OT_update_thumbnail(Operator):
    """Update thumbnail for an existing library asset"""

    bl_idname = "ual.update_thumbnail"
    bl_label = "Update Asset Thumbnail"
    bl_description = "Capture a new thumbnail for the selected library asset"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Only enable when a UAL asset object is selected"""
        if context.mode != 'OBJECT':
            return False
        obj = context.active_object
        if not obj:
            return False
        return has_ual_metadata(obj)

    def execute(self, context):
        """Execute the thumbnail update"""
        try:
            # Get active object and its metadata
            obj = context.active_object
            metadata = read_ual_metadata(obj)

            if not metadata:
                self.report({'ERROR'}, "Selected object has no UAL metadata")
                return {'CANCELLED'}

            asset_uuid = metadata.get('uuid')
            if not asset_uuid:
                self.report({'ERROR'}, "Object metadata missing UUID")
                return {'CANCELLED'}

            # Get library connection and find asset
            library = get_library_connection()
            if not library:
                self.report({'ERROR'}, "Could not connect to library")
                return {'CANCELLED'}

            asset = library.get_asset_by_uuid(asset_uuid)
            if not asset:
                self.report({'ERROR'}, f"Asset not found in library (UUID: {asset_uuid[:8]}...)")
                return {'CANCELLED'}

            # Get asset info for folder paths
            asset_name = asset.get('name', metadata.get('asset_name', 'Unknown'))
            asset_type = asset.get('asset_type', metadata.get('asset_type', 'mesh'))
            asset_id = asset.get('asset_id', metadata.get('asset_id', asset_uuid))
            variant_name = asset.get('variant_name', metadata.get('variant_name', 'Base'))
            version_label = asset.get('version_label', metadata.get('version_label', 'v001'))
            is_latest = asset.get('is_latest', 1)

            # Determine thumbnail folder based on whether this is latest or archived
            if is_latest:
                # Latest version: thumbnail in library folder
                thumbnail_folder = library.get_library_folder_path(
                    asset_id, asset_name, variant_name, asset_type
                )
            else:
                # Archived version: thumbnail in archive folder
                thumbnail_folder = library.get_archive_folder_path(
                    asset_id, asset_name, variant_name, version_label, asset_type
                )

            # Versioned thumbnail filename
            thumbnail_versioned = thumbnail_folder / f"thumbnail.{version_label}.png"

            # Collect objects to capture
            # Include active object and its hierarchy (children, armature targets, etc.)
            objects = self._collect_capture_objects(context, obj)

            if not objects:
                self.report({'ERROR'}, "No visible objects to capture")
                return {'CANCELLED'}

            # Capture the thumbnail (versioned)
            success = capture_viewport_thumbnail(
                context,
                objects,
                str(thumbnail_versioned),
                size=256,
                asset_type=asset_type
            )

            if not success:
                self.report({'ERROR'}, "Failed to capture thumbnail")
                return {'CANCELLED'}

            # For latest version, also update thumbnail.current.png (cache watching)
            import shutil
            if is_latest:
                thumbnail_current = thumbnail_folder / "thumbnail.current.png"
                shutil.copy2(str(thumbnail_versioned), str(thumbnail_current))
                thumbnail_path = thumbnail_current  # DB stores .current for latest
            else:
                thumbnail_path = thumbnail_versioned  # DB stores versioned for archived

            # Update database if path changed
            current_db_path = asset.get('thumbnail_path', '')
            if current_db_path != str(thumbnail_path):
                library.update_asset(asset_uuid, {'thumbnail_path': str(thumbnail_path)})

            # Report success
            version_info = f"{version_label}" + (" (latest)" if is_latest else " (archived)")
            self.report({'INFO'}, f"Updated thumbnail for '{asset_name}' {version_info}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Thumbnail update failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def _collect_capture_objects(self, context, root_obj):
        """Collect all objects that should be included in the thumbnail capture.
        
        Includes:
        - The root object
        - All children (recursive)
        - Parent hierarchy
        - Armature modifier targets
        - Bone custom shapes (for armatures)
        """
        objects = set()
        
        # Add root object
        objects.add(root_obj)
        
        # Add children recursively
        for child in root_obj.children_recursive:
            if child.visible_get():
                objects.add(child)
        
        # Add parent hierarchy
        parent = root_obj.parent
        while parent:
            if parent.visible_get():
                objects.add(parent)
            parent = parent.parent
        
        # Add armature modifier targets
        if hasattr(root_obj, 'modifiers'):
            for mod in root_obj.modifiers:
                if mod.type == 'ARMATURE' and mod.object:
                    if mod.object.visible_get():
                        objects.add(mod.object)
        
        # For armatures: add bone custom shapes
        if root_obj.type == 'ARMATURE' and root_obj.pose:
            for pose_bone in root_obj.pose.bones:
                if pose_bone.custom_shape and pose_bone.custom_shape.visible_get():
                    objects.add(pose_bone.custom_shape)
        
        # Also check selected objects - user might have selected relevant objects
        for obj in context.selected_objects:
            if obj.visible_get():
                objects.add(obj)
        
        return list(objects)


class UAL_OT_toggle_thumbnail_helper(Operator):
    """Toggle the interactive thumbnail helper gizmo"""

    bl_idname = "ual.toggle_thumbnail_helper"
    bl_label = "Toggle Thumbnail Helper"
    bl_description = "Toggle interactive thumbnail framing helper"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Only enable when a UAL asset object is selected"""
        if context.mode != 'OBJECT':
            return False
        obj = context.active_object
        if not obj:
            return False
        return has_ual_metadata(obj)

    def execute(self, context):
        """Toggle the thumbnail helper"""
        obj = context.active_object
        
        if not obj:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}

        # Simple toggle
        current_state = getattr(obj, 'ual_thumbnail_helper_enabled', False)
        
        if current_state:
            # Turn off
            obj.ual_thumbnail_helper_enabled = False
            self.report({'INFO'}, "Thumbnail helper disabled")
        else:
            # Turn on - set up view-aligned to current view
            obj.ual_thumbnail_helper_enabled = True
            self._setup_view_aligned(context, obj)
            self.report({'INFO'}, "Thumbnail helper enabled")
        
        # Force UI update by toggling selection (triggers gizmo refresh)
        obj.select_set(obj.select_get())
        
        # Force viewport redraw
        context.area.tag_redraw()
        
        return {'FINISHED'}

    def _setup_view_aligned(self, context, obj):
        """Set up the helper aligned to the current view (screen-space sizing)"""
        from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d
        
        region = context.region
        rv3d = context.region_data
        
        if not rv3d:
            self.report({'WARNING'}, "No 3D view region data")
            return
        
        # Get object bounding box
        objects = [obj]
        for child in obj.children_recursive:
            if child.visible_get():
                objects.append(child)
        
        bbox_3d = get_objects_bbox_3d(objects)
        
        if not bbox_3d:
            bbox_center = obj.matrix_world.translation.copy()
        else:
            # Calculate bbox center
            min_co = Vector((min(c.x for c in bbox_3d), min(c.y for c in bbox_3d), min(c.z for c in bbox_3d)))
            max_co = Vector((max(c.x for c in bbox_3d), max(c.y for c in bbox_3d), max(c.z for c in bbox_3d)))
            bbox_center = (min_co + max_co) / 2
        
        # Calculate offset from object origin to bbox center
        offset = bbox_center - obj.matrix_world.translation
        obj.ual_thumbnail_helper_offset = offset
        
        # Get view-aligned rotation using view_matrix.transposed()
        # This is the standard way to align an object to face the current view
        view_aligned_matrix = rv3d.view_matrix.transposed().to_3x3().to_4x4()
        helper_rot = view_aligned_matrix.to_quaternion()
        
        obj.ual_thumbnail_helper_rotation = helper_rot
        
        # Now calculate screen-space bounding box for size
        if bbox_3d:
            # Project all bbox points to 2D
            coords_2d = []
            default_2d = Vector((region.width / 2, region.height / 2))
            for co in bbox_3d:
                co2d = location_3d_to_region_2d(region, rv3d, co, default=default_2d)
                if co2d:
                    coords_2d.append(co2d)
            
            if coords_2d:
                # Get 2D bounding box with margin
                margin = 20
                xmin = max(0, min(c.x for c in coords_2d) - margin)
                xmax = min(region.width, max(c.x for c in coords_2d) + margin)
                ymin = max(0, min(c.y for c in coords_2d) - margin)
                ymax = min(region.height, max(c.y for c in coords_2d) + margin)
                
                # Make it square by padding shorter dimension
                width_2d = xmax - xmin
                height_2d = ymax - ymin
                
                if width_2d > height_2d:
                    delta = (width_2d - height_2d) / 2
                    ymin -= delta
                    ymax += delta
                elif height_2d > width_2d:
                    delta = (height_2d - width_2d) / 2
                    xmin -= delta
                    xmax += delta
                
                # Convert 2D corners back to 3D at bbox_center depth
                corner_bl = region_2d_to_location_3d(region, rv3d, Vector((xmin, ymin)), bbox_center)
                corner_br = region_2d_to_location_3d(region, rv3d, Vector((xmax, ymin)), bbox_center)
                corner_tl = region_2d_to_location_3d(region, rv3d, Vector((xmin, ymax)), bbox_center)
                
                # Calculate width and height in 3D
                width_3d = (corner_br - corner_bl).length
                height_3d = (corner_tl - corner_bl).length
                
                # Build scale matrix (cage_2d uses -0.5 to 0.5 range)
                scale_matrix = Matrix.Scale(width_3d, 4, Vector((1, 0, 0))) @ Matrix.Scale(height_3d, 4, Vector((0, 1, 0)))
            else:
                scale_matrix = Matrix.Scale(2.0, 4)
        else:
            scale_matrix = Matrix.Scale(2.0, 4)
        
        # Flatten matrix to 16 floats for storage
        flat_matrix = [scale_matrix[row][col] for row in range(4) for col in range(4)]
        obj.ual_thumbnail_helper_matrix = flat_matrix


# Registration
classes = (
    UAL_OT_update_thumbnail,
    UAL_OT_toggle_thumbnail_helper,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
