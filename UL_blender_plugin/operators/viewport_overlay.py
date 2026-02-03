"""
Viewport Overlay Operators

Toggle and configure asset overlay display in viewport.
"""

import bpy
from bpy.types import Operator


class UAL_OT_toggle_asset_overlay(Operator):
    """Toggle asset name/version overlay in viewport"""
    bl_idname = "ual.toggle_asset_overlay"
    bl_label = "Toggle Asset Overlay"
    bl_description = "Show/hide asset name and version labels on imported library objects"

    def execute(self, context):
        from ..viewport.asset_overlay import toggle_overlay, is_overlay_enabled

        new_state = toggle_overlay()

        # Store state in scene for persistence
        context.scene['ual_overlay_enabled'] = new_state

        if new_state:
            self.report({'INFO'}, "Asset overlay enabled")
        else:
            self.report({'INFO'}, "Asset overlay disabled")

        return {'FINISHED'}


class UAL_OT_refresh_overlay(Operator):
    """Refresh viewport overlay"""
    bl_idname = "ual.refresh_overlay"
    bl_label = "Refresh Overlay"
    bl_description = "Refresh the viewport asset overlay display"

    def execute(self, context):
        from ..viewport.asset_overlay import is_overlay_enabled, disable_overlay, enable_overlay

        if is_overlay_enabled():
            disable_overlay()
            enable_overlay()

        # Force viewport redraw
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}


# Registration
classes = [
    UAL_OT_toggle_asset_overlay,
    UAL_OT_refresh_overlay,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    # Ensure overlay is disabled on unregister
    try:
        from ..viewport.asset_overlay import disable_overlay
        disable_overlay()
    except Exception:
        pass

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_OT_toggle_asset_overlay',
    'UAL_OT_refresh_overlay',
    'register',
    'unregister',
]
