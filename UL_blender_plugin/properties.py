"""
Object Properties for Universal Library

Defines custom properties added to Blender objects for thumbnail helper gizmo.
"""

import bpy
from bpy.props import (
    BoolProperty,
    FloatVectorProperty,
)
from mathutils import Matrix


def register():
    """Register object properties for thumbnail helper"""
    
    # Enable/disable thumbnail helper gizmo
    bpy.types.Object.ual_thumbnail_helper_enabled = BoolProperty(
        name="Thumbnail Helper",
        description="Enable interactive thumbnail framing helper",
        default=False
    )
    
    # Location offset from object origin (in world space)
    bpy.types.Object.ual_thumbnail_helper_offset = FloatVectorProperty(
        name="Thumbnail Helper Offset",
        description="Location offset for thumbnail helper",
        subtype='TRANSLATION',
        size=3,
        default=(0.0, 0.0, 0.0)
    )
    
    # Rotation as quaternion (view-aligned when set up)
    bpy.types.Object.ual_thumbnail_helper_rotation = FloatVectorProperty(
        name="Thumbnail Helper Rotation",
        description="Rotation for thumbnail helper (quaternion)",
        subtype='QUATERNION',
        size=4,
        default=(1.0, 0.0, 0.0, 0.0)
    )
    
    # Scale/size matrix for the helper box
    bpy.types.Object.ual_thumbnail_helper_matrix = FloatVectorProperty(
        name="Thumbnail Helper Matrix",
        description="Transform matrix for thumbnail helper size",
        subtype='MATRIX',
        size=16,
        default=(
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0
        )
    )


def unregister():
    """Unregister object properties"""
    del bpy.types.Object.ual_thumbnail_helper_matrix
    del bpy.types.Object.ual_thumbnail_helper_rotation
    del bpy.types.Object.ual_thumbnail_helper_offset
    del bpy.types.Object.ual_thumbnail_helper_enabled
