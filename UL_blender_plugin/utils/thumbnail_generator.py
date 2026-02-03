"""
Thumbnail Generator

Consolidated thumbnail generation utilities for the UAL addon.
"""

import tempfile
from pathlib import Path
from typing import Optional, Tuple, List
import bpy

from .blender_helpers import find_3d_viewport
from .context_managers import render_settings, viewport_overlays


class ThumbnailGenerator:
    """
    Generates thumbnails for assets using viewport capture.

    Usage:
        generator = ThumbnailGenerator(context)
        generator.capture_viewport(filepath)
    """

    def __init__(self, context, size: int = 256):
        """
        Initialize thumbnail generator.

        Args:
            context: Blender context
            size: Target thumbnail size in pixels
        """
        self.context = context
        self.size = size

    def capture_viewport(self, filepath: str) -> bool:
        """
        Capture a simple viewport render.

        Args:
            filepath: Output file path

        Returns:
            True if successful
        """
        view3d_area, view3d_region, view3d_space = find_3d_viewport(self.context)

        if not view3d_area:
            return self._create_placeholder(filepath)

        scene = self.context.scene

        try:
            with render_settings(scene, resolution=(self.size, self.size)):
                with viewport_overlays(view3d_space, show_overlays=False):
                    with self.context.temp_override(area=view3d_area, region=view3d_region):
                        bpy.ops.render.opengl()

            # Save render result
            result = bpy.data.images.get('Render Result')
            if result:
                result.save_render(filepath=filepath)
                return True

        except Exception as e:
            pass

        return self._create_placeholder(filepath)

    def capture_with_framing(self, filepath: str, objects: List[bpy.types.Object] = None) -> bool:
        """
        Capture viewport with automatic framing of objects.

        Uses the more complex MACHIN3tools-style approach with bounding box
        calculation and cropping.

        Args:
            filepath: Output file path
            objects: Objects to frame (defaults to selected)

        Returns:
            True if successful
        """
        try:
            import numpy as np
        except ImportError:
            return self.capture_viewport(filepath)

        view3d_area, view3d_region, view3d_space = find_3d_viewport(self.context)

        if not view3d_area:
            return self._create_placeholder(filepath)

        rv3d = view3d_space.region_3d
        region_width = view3d_region.width
        region_height = view3d_region.height

        # Get bounding box
        bbox_3d = self._get_objects_bbox_3d(objects)
        if not bbox_3d:
            return self.capture_viewport(filepath)

        # Convert to screen coordinates with margin
        xmin, ymin, xmax, ymax = self._bbox_to_screen(
            view3d_region, rv3d, bbox_3d, margin=20
        )

        # Make square
        xmin, ymin, xmax, ymax = self._make_square_bbox(
            xmin, ymin, xmax, ymax, region_width, region_height
        )

        crop_width = xmax - xmin
        crop_height = ymax - ymin

        if crop_width <= 0 or crop_height <= 0:
            return self.capture_viewport(filepath)

        scene = self.context.scene
        render_image = None
        cropped_image = None

        try:
            with render_settings(scene, resolution=(region_width, region_height)):
                with viewport_overlays(view3d_space, show_overlays=False):
                    with self.context.temp_override(area=view3d_area, region=view3d_region):
                        bpy.ops.render.opengl()

            result = bpy.data.images.get('Render Result')
            if not result:
                return self._create_placeholder(filepath)

            # Save to temp and reload for numpy processing
            temp_path = Path(tempfile.gettempdir()) / "_ual_temp_render.png"
            result.save_render(filepath=str(temp_path))
            render_image = bpy.data.images.load(str(temp_path))

            # Crop using numpy
            pixels = np.array(render_image.pixels[:])
            pixels = pixels.reshape((region_height, region_width, 4))
            cropped_pixels = pixels[ymin:ymax, xmin:xmax, :]

            # Create cropped image
            cropped_image = bpy.data.images.new(
                "_UAL_cropped_thumbnail",
                width=crop_width,
                height=crop_height
            )
            cropped_image.pixels[:] = cropped_pixels.flatten()

            # Scale to target size
            scale_factor = max(crop_width, crop_height) / self.size
            if scale_factor > 1:
                new_width = int(crop_width / scale_factor)
                new_height = int(crop_height / scale_factor)
                cropped_image.scale(new_width, new_height)

            # Save
            cropped_image.filepath_raw = filepath
            cropped_image.file_format = 'PNG'
            cropped_image.save()

            # Cleanup temp
            if temp_path.exists():
                temp_path.unlink()

            return True

        except Exception as e:
            import traceback
            traceback.print_exc()

        finally:
            if render_image:
                bpy.data.images.remove(render_image, do_unlink=True)
            if cropped_image:
                bpy.data.images.remove(cropped_image, do_unlink=True)

        return self._create_placeholder(filepath)

    def generate_material_preview(self, material: bpy.types.Material, filepath: str) -> bool:
        """
        Generate a material preview using Blender's built-in system.

        Args:
            material: Material to preview
            filepath: Output file path

        Returns:
            True if successful
        """
        try:
            # Use Blender's material preview system
            material.preview_render_type = 'SPHERE'
            material.asset_generate_preview()

            # Wait for preview to generate
            if material.preview:
                preview = material.preview
                if preview.image_size[0] > 0:
                    # Create image from preview
                    img = bpy.data.images.new(
                        "_ual_mat_preview",
                        width=preview.image_size[0],
                        height=preview.image_size[1]
                    )
                    img.pixels[:] = preview.image_pixels_float[:]
                    img.scale(self.size, self.size)
                    img.filepath_raw = filepath
                    img.file_format = 'PNG'
                    img.save()
                    bpy.data.images.remove(img, do_unlink=True)
                    return True

        except Exception as e:
            pass

        return self._create_placeholder(filepath)

    def _create_placeholder(self, filepath: str) -> bool:
        """Create a simple placeholder thumbnail."""
        try:
            img = bpy.data.images.new("_ual_placeholder", width=self.size, height=self.size)
            pixels = [0.2, 0.2, 0.2, 1.0] * (self.size * self.size)
            img.pixels = pixels
            img.filepath_raw = filepath
            img.file_format = 'PNG'
            img.save()
            bpy.data.images.remove(img, do_unlink=True)
            return True
        except Exception as e:
            return False

    def _get_objects_bbox_3d(self, objects=None) -> Optional[Tuple]:
        """Get 3D bounding box of objects."""
        if objects is None:
            objects = self.context.selected_objects

        if not objects:
            return None

        from mathutils import Vector

        min_co = Vector((float('inf'), float('inf'), float('inf')))
        max_co = Vector((float('-inf'), float('-inf'), float('-inf')))

        for obj in objects:
            if not hasattr(obj, 'bound_box'):
                continue

            matrix_world = obj.matrix_world
            for corner in obj.bound_box:
                world_co = matrix_world @ Vector(corner)
                min_co.x = min(min_co.x, world_co.x)
                min_co.y = min(min_co.y, world_co.y)
                min_co.z = min(min_co.z, world_co.z)
                max_co.x = max(max_co.x, world_co.x)
                max_co.y = max(max_co.y, world_co.y)
                max_co.z = max(max_co.z, world_co.z)

        if min_co.x == float('inf'):
            return None

        return (min_co, max_co)

    def _bbox_to_screen(self, region, rv3d, bbox_3d, margin=20) -> Tuple[int, int, int, int]:
        """Convert 3D bounding box to 2D screen coordinates."""
        from bpy_extras.view3d_utils import location_3d_to_region_2d
        from mathutils import Vector

        min_co, max_co = bbox_3d

        # Get all 8 corners
        corners = [
            Vector((min_co.x, min_co.y, min_co.z)),
            Vector((max_co.x, min_co.y, min_co.z)),
            Vector((min_co.x, max_co.y, min_co.z)),
            Vector((max_co.x, max_co.y, min_co.z)),
            Vector((min_co.x, min_co.y, max_co.z)),
            Vector((max_co.x, min_co.y, max_co.z)),
            Vector((min_co.x, max_co.y, max_co.z)),
            Vector((max_co.x, max_co.y, max_co.z)),
        ]

        screen_coords = []
        for corner in corners:
            co_2d = location_3d_to_region_2d(region, rv3d, corner)
            if co_2d:
                screen_coords.append(co_2d)

        if not screen_coords:
            return 0, 0, region.width, region.height

        xs = [co.x for co in screen_coords]
        ys = [co.y for co in screen_coords]

        xmin = max(0, int(min(xs)) - margin)
        ymin = max(0, int(min(ys)) - margin)
        xmax = min(region.width, int(max(xs)) + margin)
        ymax = min(region.height, int(max(ys)) + margin)

        return xmin, ymin, xmax, ymax

    def _make_square_bbox(self, xmin, ymin, xmax, ymax, region_width, region_height) -> Tuple[int, int, int, int]:
        """Make bounding box square by padding shorter dimension."""
        width = xmax - xmin
        height = ymax - ymin
        diff = abs(width - height)

        if width > height:
            pad = diff // 2
            ymin = max(0, ymin - pad)
            ymax = min(region_height, ymax + (diff - pad))
        else:
            pad = diff // 2
            xmin = max(0, xmin - pad)
            xmax = min(region_width, xmax + (diff - pad))

        return xmin, ymin, xmax, ymax


def generate_thumbnail(context, filepath: str, size: int = 256, framed: bool = False) -> bool:
    """
    Convenience function for generating thumbnails.

    Args:
        context: Blender context
        filepath: Output file path
        size: Target size in pixels
        framed: If True, use framed capture with object bounding

    Returns:
        True if successful
    """
    generator = ThumbnailGenerator(context, size=size)
    if framed:
        return generator.capture_with_framing(filepath)
    return generator.capture_viewport(filepath)


__all__ = [
    'ThumbnailGenerator',
    'generate_thumbnail',
]
