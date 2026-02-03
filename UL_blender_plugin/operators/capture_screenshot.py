"""
Capture Review Screenshot - Captures viewport for asset review

Captures a clean viewport screenshot and sends it to the UL desktop app
via a queue file, tied to the currently selected UAL asset version.

Now uses the protocol module for schema-driven message building.
"""

import bpy
import json
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from bpy.types import Operator
from bpy.props import StringProperty

from ..utils.metadata_handler import has_ual_metadata, read_ual_metadata
from ..utils.protocol_loader import build_message, get_constant

# Get protocol constants with fallbacks
# IMPORTANT: fallback must match universal_library/protocol/constants.py
QUEUE_DIR_NAME = get_constant('QUEUE_DIR_NAME', 'usd_library_queue')


class UL_OT_capture_review_screenshot(Operator):
    """Capture viewport screenshot for asset review"""

    bl_idname = "ual.capture_review_screenshot"
    bl_label = "Capture Review Screenshot"
    bl_description = "Capture viewport screenshot for review (requires UAL asset selected)"
    bl_options = {'REGISTER', 'UNDO'}

    display_name: StringProperty(
        name="Display Name",
        default="Screenshot",
        description="Name for this screenshot in the review system"
    )

    @classmethod
    def poll(cls, context):
        """Only enable when a UAL asset object is selected"""
        obj = context.active_object
        if not obj:
            return False
        return has_ual_metadata(obj)

    def invoke(self, context, event):
        """Show dialog to enter display name before capture"""
        # Set default name based on view direction
        self.display_name = self._get_view_name(context)
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        """Draw the dialog UI"""
        layout = self.layout
        layout.use_property_split = True

        # Get asset info for display
        obj = context.active_object
        metadata = read_ual_metadata(obj)
        if metadata:
            asset_name = metadata.get('asset_name', 'Unknown')
            version_label = metadata.get('version_label', 'v001')
            layout.label(text=f"Asset: {asset_name} ({version_label})")
            layout.separator()

        layout.prop(self, "display_name")

    def execute(self, context):
        """Execute the screenshot capture"""
        try:
            # Get metadata from active object
            obj = context.active_object
            metadata = read_ual_metadata(obj)

            if not metadata:
                self.report({'ERROR'}, "Selected object has no UAL metadata")
                return {'CANCELLED'}

            # Capture viewport to temp file
            temp_path = self._capture_viewport(context)

            if not temp_path or not temp_path.exists():
                self.report({'ERROR'}, "Failed to capture viewport")
                return {'CANCELLED'}

            # Write queue file for UL app
            if self._write_queue_file(metadata, temp_path):
                asset_name = metadata.get('asset_name', 'Unknown')
                version_label = metadata.get('version_label', 'v001')
                self.report(
                    {'INFO'},
                    f"Screenshot captured for {asset_name} ({version_label})"
                )
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Failed to write queue file")
                return {'CANCELLED'}

        except Exception as e:
            self.report({'ERROR'}, f"Screenshot capture failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def _get_view_name(self, context) -> str:
        """Generate a default name based on current view direction"""
        try:
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            rv3d = space.region_3d
                            if rv3d:
                                # Get view rotation
                                view_rot = rv3d.view_rotation
                                # Convert to euler for easier interpretation
                                euler = view_rot.to_euler()

                                # Determine view name based on rotation
                                # These are approximate checks
                                import math
                                x, y, z = euler.x, euler.y, euler.z

                                # Check for standard views
                                if abs(x - math.radians(90)) < 0.1 and abs(z) < 0.1:
                                    return "Front"
                                elif abs(x - math.radians(90)) < 0.1 and abs(z - math.radians(180)) < 0.1:
                                    return "Back"
                                elif abs(x - math.radians(90)) < 0.1 and abs(z - math.radians(90)) < 0.1:
                                    return "Right"
                                elif abs(x - math.radians(90)) < 0.1 and abs(z - math.radians(-90)) < 0.1:
                                    return "Left"
                                elif abs(x) < 0.1:
                                    return "Top"
                                elif abs(x - math.radians(180)) < 0.1:
                                    return "Bottom"
                                else:
                                    return "Perspective"
        except Exception:
            pass

        return "Screenshot"

    def _capture_viewport(self, context) -> Optional[Path]:
        """Capture viewport to a temp PNG file with clean settings"""
        # Generate temp file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path(tempfile.gettempdir()) / QUEUE_DIR_NAME
        temp_dir.mkdir(parents=True, exist_ok=True)

        temp_filename = f"ul_screenshot_{timestamp}.png"
        temp_path = temp_dir / temp_filename

        # Store original settings
        original_settings = self._store_viewport_settings(context)

        try:
            # Configure viewport for clean capture
            self._setup_clean_viewport(context)

            # Configure render settings for screenshot
            scene = context.scene
            original_filepath = scene.render.filepath
            original_format = scene.render.image_settings.file_format
            original_color_mode = scene.render.image_settings.color_mode

            # Store media_type if available (Blender 4.5+/5.0)
            original_media_type = None
            if hasattr(scene.render.image_settings, 'media_type'):
                original_media_type = scene.render.image_settings.media_type

            scene.render.filepath = str(temp_path)

            # IMPORTANT: In Blender 4.5+/5.0, must set media_type to 'IMAGE' first
            if hasattr(scene.render.image_settings, 'media_type'):
                scene.render.image_settings.media_type = 'IMAGE'
            scene.render.image_settings.file_format = 'PNG'
            scene.render.image_settings.color_mode = 'RGBA'

            # Capture viewport
            bpy.ops.render.opengl(write_still=True)

            # Restore render settings
            # Restore media_type first (Blender 4.5+/5.0), then file_format
            if original_media_type is not None and hasattr(scene.render.image_settings, 'media_type'):
                scene.render.image_settings.media_type = original_media_type
            scene.render.filepath = original_filepath
            scene.render.image_settings.file_format = original_format
            scene.render.image_settings.color_mode = original_color_mode

            return temp_path

        finally:
            # Always restore viewport settings
            self._restore_viewport_settings(context, original_settings)

    def _store_viewport_settings(self, context) -> Dict[str, Any]:
        """Store current viewport settings for restoration"""
        settings = {}

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        # Store overlay settings
                        settings['show_overlays'] = space.overlay.show_overlays
                        settings['show_floor'] = space.overlay.show_floor
                        settings['show_axis_x'] = space.overlay.show_axis_x
                        settings['show_axis_y'] = space.overlay.show_axis_y
                        settings['show_axis_z'] = space.overlay.show_axis_z
                        settings['show_cursor'] = space.overlay.show_cursor
                        settings['show_object_origins'] = space.overlay.show_object_origins
                        settings['show_relationship_lines'] = space.overlay.show_relationship_lines
                        settings['show_outline_selected'] = space.overlay.show_outline_selected

                        # Store gizmo settings
                        settings['show_gizmo'] = space.show_gizmo

                        # Store region visibility
                        settings['show_region_toolbar'] = space.show_region_toolbar
                        settings['show_region_ui'] = space.show_region_ui
                        settings['show_region_header'] = space.show_region_header

                        return settings

        return settings

    def _setup_clean_viewport(self, context):
        """Configure viewport for clean screenshot capture"""
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        # Hide overlays for clean capture
                        space.overlay.show_overlays = False

                        # Hide gizmos
                        space.show_gizmo = False

                        # Force redraw
                        area.tag_redraw()
                        return

    def _restore_viewport_settings(self, context, settings: Dict[str, Any]):
        """Restore viewport settings after capture"""
        if not settings:
            return

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        # Restore overlay settings
                        if 'show_overlays' in settings:
                            space.overlay.show_overlays = settings['show_overlays']
                        if 'show_floor' in settings:
                            space.overlay.show_floor = settings['show_floor']
                        if 'show_axis_x' in settings:
                            space.overlay.show_axis_x = settings['show_axis_x']
                        if 'show_axis_y' in settings:
                            space.overlay.show_axis_y = settings['show_axis_y']
                        if 'show_axis_z' in settings:
                            space.overlay.show_axis_z = settings['show_axis_z']
                        if 'show_cursor' in settings:
                            space.overlay.show_cursor = settings['show_cursor']
                        if 'show_object_origins' in settings:
                            space.overlay.show_object_origins = settings['show_object_origins']
                        if 'show_relationship_lines' in settings:
                            space.overlay.show_relationship_lines = settings['show_relationship_lines']
                        if 'show_outline_selected' in settings:
                            space.overlay.show_outline_selected = settings['show_outline_selected']

                        # Restore gizmo settings
                        if 'show_gizmo' in settings:
                            space.show_gizmo = settings['show_gizmo']

                        # Force redraw
                        area.tag_redraw()
                        return

    def _write_queue_file(self, metadata: Dict[str, Any], screenshot_path: Path) -> bool:
        """Write queue file for UL app to pick up using protocol schema"""
        try:
            queue_dir = Path(tempfile.gettempdir()) / QUEUE_DIR_NAME
            queue_dir.mkdir(parents=True, exist_ok=True)

            # Generate unique filename
            uuid_short = metadata.get('uuid', 'unknown')[:8]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            queue_filename = f"screenshot_{uuid_short}_{timestamp}.json"
            queue_path = queue_dir / queue_filename

            # Build message using protocol schema
            # The schema defines which fields to use and their sources
            extra_fields = {
                "display_name": self.display_name,
                "screenshot_path": str(screenshot_path),
                "blender_version": bpy.app.version_string,
            }
            queue_data = build_message("review_screenshot", metadata, extra_fields)

            # Write queue file
            with open(queue_path, 'w', encoding='utf-8') as f:
                json.dump(queue_data, f, indent=2)

            return True

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False


# Registration
classes = (
    UL_OT_capture_review_screenshot,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = ['UL_OT_capture_review_screenshot', 'register', 'unregister']
