"""
Thumbnail Helper Gizmo

Interactive 2D cage gizmo for fine-tuning thumbnail framing.
Based on MACHIN3tools' asset thumbnail helper pattern.
"""

import bpy
from bpy.types import GizmoGroup
from mathutils import Matrix, Vector, Quaternion

from ..utils.metadata_handler import has_ual_metadata


class UAL_GGT_thumbnail_helper(GizmoGroup):
    """Gizmo group for thumbnail helper - 2D cage for framing adjustment"""
    
    bl_idname = "UAL_GGT_thumbnail_helper"
    bl_label = "UAL Thumbnail Helper"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        """Show when active object has UAL metadata and helper is enabled"""
        if context.mode != 'OBJECT':
            return False
        
        active = context.active_object
        if not active or not active.select_get():
            return False
        
        # Check if helper is enabled on this object
        if not getattr(active, 'ual_thumbnail_helper_enabled', False):
            return False
        
        # Only show for UAL assets
        return has_ual_metadata(active)

    def setup(self, context):
        """Initialize the gizmo"""
        self.obj = context.active_object if context.active_object and context.active_object.select_get() else None
        self.gzm = None
        
        if self.obj and getattr(self.obj, 'ual_thumbnail_helper_enabled', False):
            self.gzm = self._create_cage_gizmo()

    def refresh(self, context):
        """Update gizmo when context changes"""
        active = context.active_object if context.active_object and context.active_object.select_get() else None
        
        # Track if object changed
        if self.obj != active:
            self.obj = active
            self.gzm = None
        
        # Recreate gizmo if needed (object changed OR gizmo was cleared by poll returning False)
        if self.obj and getattr(self.obj, 'ual_thumbnail_helper_enabled', False):
            if self.gzm is None or len(self.gizmos) == 0:
                self.gizmos.clear()
                self.gzm = self._create_cage_gizmo()
        
        # Always update gizmo transform - this handles property changes
        if self.gzm and self.obj:
            self._update_gizmo_transform()

    def _create_cage_gizmo(self):
        """Create the 2D cage gizmo"""
        self.gizmos.clear()
        
        gzm = self.gizmos.new("GIZMO_GT_cage_2d")
        
        # Visual style
        gzm.draw_style = 'BOX'
        gzm.transform = {'TRANSLATE', 'SCALE'}
        
        gzm.use_draw_modal = True   # Draw when dragging
        gzm.use_draw_hover = False  # Always visible, not just on hover
        
        # Colors
        gzm.color = (0.4, 0.7, 1.0)          # Light blue
        gzm.color_highlight = (0.6, 0.9, 1.0)  # Brighter on hover
        gzm.alpha = 0.3
        gzm.alpha_highlight = 0.6
        
        # Set up transform
        self._update_gizmo_transform()
        
        # Bind the matrix property so dragging updates the object property
        gzm.target_set_prop("matrix", self.obj, "ual_thumbnail_helper_matrix")
        
        return gzm

    def _update_gizmo_transform(self):
        """Update gizmo position/rotation from object properties"""
        if not self.obj or not hasattr(self, 'gzm') or not self.gzm:
            return
        
        # Get object transform
        loc, rot, sca = self.obj.matrix_world.decompose()
        
        # Get stored offset and rotation
        offset = Vector(self.obj.ual_thumbnail_helper_offset)
        
        # Get rotation as quaternion
        rot_data = self.obj.ual_thumbnail_helper_rotation
        helper_rot = Quaternion((rot_data[0], rot_data[1], rot_data[2], rot_data[3]))
        
        # Build gizmo transform matrix
        # Position: object location + offset
        # Rotation: stored helper rotation (view-aligned)
        # Scale: from object scale
        self.gzm.matrix_basis = Matrix.LocRotScale(
            loc + offset,
            helper_rot,
            sca
        )


# Registration
classes = (
    UAL_GGT_thumbnail_helper,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
