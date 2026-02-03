"""
Asset Overlay - Viewport overlay showing UAL asset info

Uses Blender's GPU and BLF modules to draw asset name/version
on imported library assets in the 3D viewport.
"""

import bpy
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from ..utils.metadata_handler import has_ual_metadata, read_ual_metadata


# Global state
_draw_handler = None
_is_enabled = False


def get_asset_label(obj) -> str:
    """Get display label for an asset object"""
    metadata = read_ual_metadata(obj)
    if not metadata:
        return ""

    name = metadata.get('asset_name', obj.name)
    version = metadata.get('version', 1)
    version_label = metadata.get('version_label', f'v{version:03d}')
    rep_type = metadata.get('representation_type', '')

    if rep_type and rep_type != 'none':
        return f"{name} ({version_label}) - {rep_type.capitalize()}"
    return f"{name} ({version_label})"


def draw_rounded_rect(x, y, width, height, color=(0.1, 0.1, 0.1, 0.8)):
    """Draw a rectangle using GPU shader"""
    vertices = [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
    ]

    indices = [(0, 1, 2), (0, 2, 3)]

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)

    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set('NONE')


def draw_asset_overlays():
    """Main draw callback for viewport overlays"""
    global _is_enabled

    if not _is_enabled:
        return

    context = bpy.context

    # Only draw in 3D viewport
    if not context.area or context.area.type != 'VIEW_3D':
        return

    if not context.region or not context.space_data:
        return

    region = context.region
    rv3d = context.space_data.region_3d

    if not rv3d:
        return

    # Get font settings
    font_size = 14
    bg_alpha = 0.7

    # Try to get from addon preferences
    try:
        prefs = context.preferences.addons.get('UL_blender_plugin')
        if prefs and hasattr(prefs.preferences, 'overlay_font_size'):
            font_size = prefs.preferences.overlay_font_size
            bg_alpha = prefs.preferences.overlay_bg_alpha
    except Exception:
        pass

    # Configure font
    font_id = 0
    blf.size(font_id, font_size)

    # Iterate through scene objects with UAL metadata
    for obj in context.scene.objects:
        if not has_ual_metadata(obj):
            continue

        if not obj.visible_get():
            continue

        # Get object's world position (use bounding box center)
        try:
            if hasattr(obj, 'bound_box') and obj.bound_box:
                # Calculate bounding box center in world space
                bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
                center = sum(bbox_corners, Vector()) / len(bbox_corners)
                # Offset slightly above the object
                z_offset = max(obj.dimensions.z / 2, 0.5) + 0.3
                pos_3d = center + Vector((0, 0, z_offset))
            else:
                pos_3d = obj.matrix_world.translation + Vector((0, 0, 1))
        except Exception:
            pos_3d = obj.location + Vector((0, 0, 1))

        # Convert to 2D screen coordinates
        pos_2d = location_3d_to_region_2d(region, rv3d, pos_3d)

        if pos_2d is None:
            continue

        # Get label text
        label = get_asset_label(obj)
        if not label:
            continue

        # Calculate text dimensions for background
        text_width, text_height = blf.dimensions(font_id, label)
        padding = 6

        # Draw background rectangle
        bg_x = pos_2d.x - text_width / 2 - padding
        bg_y = pos_2d.y - padding
        bg_width = text_width + padding * 2
        bg_height = text_height + padding * 2

        draw_rounded_rect(
            bg_x, bg_y,
            bg_width, bg_height,
            color=(0.1, 0.1, 0.1, bg_alpha)
        )

        # Draw text
        blf.position(font_id, pos_2d.x - text_width / 2, pos_2d.y, 0)
        blf.color(font_id, 1.0, 1.0, 1.0, 1.0)  # White text
        blf.draw(font_id, label)


def enable_overlay():
    """Enable viewport overlay drawing"""
    global _draw_handler, _is_enabled

    if _draw_handler is not None:
        return  # Already enabled

    _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_asset_overlays,
        (),
        'WINDOW',
        'POST_PIXEL'
    )
    _is_enabled = True

    # Force viewport redraw
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def disable_overlay():
    """Disable viewport overlay drawing"""
    global _draw_handler, _is_enabled

    if _draw_handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, 'WINDOW')
        except Exception:
            pass
        _draw_handler = None

    _is_enabled = False

    # Force viewport redraw
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass


def toggle_overlay() -> bool:
    """Toggle overlay on/off, returns new state"""
    global _is_enabled

    if _is_enabled:
        disable_overlay()
        return False
    else:
        enable_overlay()
        return True


def is_overlay_enabled() -> bool:
    """Check if overlay is currently enabled"""
    return _is_enabled


__all__ = [
    'enable_overlay',
    'disable_overlay',
    'toggle_overlay',
    'is_overlay_enabled',
]
