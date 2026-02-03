"""
Viewport Capture Utilities

Shared functions for viewport thumbnail generation used by export operators.
Extracts and crops viewport renders to create asset thumbnails.
"""

import bpy
import math
import tempfile
import numpy as np
from pathlib import Path
from mathutils import Vector, Matrix, Quaternion
from bpy_extras.view3d_utils import location_3d_to_region_2d
from .context_managers import preserve_viewport_state


def _get_helper_bbox_3d(obj):
    """Get 3D bounding box from thumbnail helper gizmo properties.
    
    The helper stores a view-aligned 2D box as:
    - offset: translation from object origin
    - rotation: quaternion for view alignment
    - matrix: scale matrix for box size
    
    Returns:
        list: List of 4 Vector coordinates representing the helper box corners,
              or None if helper data is invalid
    """
    try:
        # Get object world transform
        loc, rot, sca = obj.matrix_world.decompose()
        
        # Get helper properties
        offset = Vector(obj.ual_thumbnail_helper_offset)
        
        rot_data = obj.ual_thumbnail_helper_rotation
        helper_rot = Quaternion((rot_data[0], rot_data[1], rot_data[2], rot_data[3]))
        
        # Reconstruct scale matrix from flat array
        matrix_data = obj.ual_thumbnail_helper_matrix
        helper_matrix = Matrix((
            (matrix_data[0], matrix_data[1], matrix_data[2], matrix_data[3]),
            (matrix_data[4], matrix_data[5], matrix_data[6], matrix_data[7]),
            (matrix_data[8], matrix_data[9], matrix_data[10], matrix_data[11]),
            (matrix_data[12], matrix_data[13], matrix_data[14], matrix_data[15])
        ))
        
        # Build full transform matrix
        gzm_matrix = Matrix.LocRotScale(loc + offset, helper_rot, sca) @ helper_matrix
        
        # Generate 4 corner points for the 2D box (in 3D space)
        # The cage_2d gizmo uses -0.5 to 0.5 range
        corners = [
            gzm_matrix @ Vector((-0.5, -0.5, 0)),
            gzm_matrix @ Vector((0.5, -0.5, 0)),
            gzm_matrix @ Vector((0.5, 0.5, 0)),
            gzm_matrix @ Vector((-0.5, 0.5, 0))
        ]
        
        return corners
        
    except Exception as e:
        return None


def get_3d_viewport(context):
    """Find the 3D viewport area, region, and space.

    Returns:
        tuple: (view3d_area, view3d_region, view3d_space) or (None, None, None) if not found
    """
    view3d_area = None
    view3d_region = None
    view3d_space = None

    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            view3d_area = area
            for region in area.regions:
                if region.type == 'WINDOW':
                    view3d_region = region
                    break
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    view3d_space = space
                    break
            break

    return view3d_area, view3d_region, view3d_space


def get_objects_bbox_3d(objects) -> list:
    """Get combined 3D bounding box of objects in world space.

    Args:
        objects: List of Blender objects

    Returns:
        list: List of Vector coordinates representing bounding box corners
    """
    all_coords = []

    for obj in objects:
        if obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'ARMATURE', 'GPENCIL', 'GREASEPENCIL'}:
            # Get object's bounding box corners in world space
            bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            all_coords.extend(bbox_corners)

    if not all_coords:
        # Fallback: use object locations
        for obj in objects:
            all_coords.append(obj.matrix_world.translation)

    return all_coords


def bbox_to_screen(region, rv3d, bbox_3d, margin=20) -> tuple:
    """Convert 3D bounding box to 2D screen coordinates with margin.

    Args:
        region: Blender region
        rv3d: Region 3D data
        bbox_3d: List of 3D coordinates
        margin: Pixel margin around bounding box

    Returns:
        tuple: (xmin, ymin, xmax, ymax) screen coordinates
    """
    region_width = region.width
    region_height = region.height

    coords_2d = []
    default_2d = Vector((region_width / 2, region_height / 2))

    for co in bbox_3d:
        co2d = location_3d_to_region_2d(region, rv3d, co, default=default_2d)
        if co2d:
            coords_2d.append(Vector((round(co2d.x), round(co2d.y))))
        else:
            coords_2d.append(default_2d.copy())

    if not coords_2d:
        # Fallback to center of region
        return (margin, margin, region_width - margin, region_height - margin)

    # Get min/max with margin, clamped to region bounds
    xmin = max(0, min(c.x for c in coords_2d) - margin)
    xmax = min(region_width, max(c.x for c in coords_2d) + margin)
    ymin = max(0, min(c.y for c in coords_2d) - margin)
    ymax = min(region_height, max(c.y for c in coords_2d) + margin)

    return (int(xmin), int(ymin), int(xmax), int(ymax))


def make_square_bbox(xmin, ymin, xmax, ymax, region_width, region_height) -> tuple:
    """Make bounding box square by padding the shorter dimension.

    Args:
        xmin, ymin, xmax, ymax: Current bounding box
        region_width, region_height: Region dimensions for clamping

    Returns:
        tuple: (xmin, ymin, xmax, ymax) squared bounding box
    """
    width = xmax - xmin
    height = ymax - ymin

    if width > height:
        # Pad height
        delta = (width - height) // 2
        ymin = max(0, ymin - delta)
        ymax = min(region_height, ymax + delta)
    elif height > width:
        # Pad width
        delta = (height - width) // 2
        xmin = max(0, xmin - delta)
        xmax = min(region_width, xmax + delta)

    return (int(xmin), int(ymin), int(xmax), int(ymax))


def is_cycles_rendered_view(context, view3d_space) -> bool:
    """Check if viewport is in Cycles rendered mode.

    Args:
        context: Blender context
        view3d_space: 3D viewport space

    Returns:
        bool: True if in Cycles rendered mode
    """
    return (
        view3d_space.shading.type == 'RENDERED' and
        context.scene.render.engine == 'CYCLES'
    )


def create_placeholder_thumbnail(filepath: str, size: int = 256):
    """Create a simple placeholder thumbnail image.

    Args:
        filepath: Output file path
        size: Image size in pixels (square)
    """
    img = bpy.data.images.new("_ual_thumbnail_temp", width=size, height=size)

    # Fill with dark gray background
    pixels = [0.2, 0.2, 0.2, 1.0] * (size * size)
    img.pixels = pixels

    # Save to file
    img.filepath_raw = filepath
    img.file_format = 'PNG'
    img.save()

    # Clean up
    bpy.data.images.remove(img)


def capture_viewport_thumbnail(
    context,
    objects,
    filepath: str,
    size: int = 256,
    asset_type: str = None
) -> bool:
    """Generate thumbnail by capturing and cropping viewport render.

    This is the main function for thumbnail generation. It:
    1. Gets 3D bounding box of objects
    2. Converts to 2D screen coordinates with margin
    3. Makes bounding box square by padding
    4. Renders viewport at full resolution (OpenGL or Cycles)
    5. Crops using numpy to the square bounding box
    6. Scales to target size
    7. Saves to file

    Args:
        context: Blender context
        objects: List of objects to capture (determines crop region)
        filepath: Output file path
        size: Target thumbnail size in pixels
        asset_type: Asset type ('rig', 'mesh', etc.) for type-specific overlay settings

    Returns:
        bool: True if successful, False otherwise
    """
    success = False

    # Find 3D viewport
    view3d_area, view3d_region, view3d_space = get_3d_viewport(context)
    if not view3d_area:
        create_placeholder_thumbnail(filepath, size)
        return False

    # Get region_3d for coordinate conversion
    rv3d = view3d_space.region_3d

    # Get region dimensions
    region_width = view3d_region.width
    region_height = view3d_region.height

    # 1. Get 3D bounding box - check for thumbnail helper first
    bbox_3d = None
    active_obj = context.active_object
    
    if active_obj and getattr(active_obj, 'ual_thumbnail_helper_enabled', False):
        # Use thumbnail helper bounds
        bbox_3d = _get_helper_bbox_3d(active_obj)
    
    if not bbox_3d:
        # Fall back to object-based bbox
        bbox_3d = get_objects_bbox_3d(objects)
    
    if not bbox_3d:
        create_placeholder_thumbnail(filepath, size)
        return False

    # 2. Convert to 2D screen coordinates
    xmin, ymin, xmax, ymax = bbox_to_screen(view3d_region, rv3d, bbox_3d, margin=20)

    # 3. Make square by padding shorter dimension
    xmin, ymin, xmax, ymax = make_square_bbox(
        xmin, ymin, xmax, ymax, region_width, region_height
    )

    crop_width = xmax - xmin
    crop_height = ymax - ymin

    # Safety check: ensure we have valid crop dimensions
    if crop_width <= 0 or crop_height <= 0:
        create_placeholder_thumbnail(filepath, size)
        return False

    scene = context.scene
    render = scene.render

    # Check if in Cycles RENDERED mode
    is_cycles = is_cycles_rendered_view(context, view3d_space)

    # Auto-detect asset type from objects if not provided
    if asset_type is None:
        has_armature = any(obj.type == 'ARMATURE' for obj in objects)
        asset_type = 'rig' if has_armature else 'mesh'

    # Store original settings
    overlay = view3d_space.overlay
    original = {
        'resolution_x': render.resolution_x,
        'resolution_y': render.resolution_y,
        'resolution_percentage': render.resolution_percentage,
        'file_format': render.image_settings.file_format,
        'color_depth': render.image_settings.color_depth,
        'show_overlays': overlay.show_overlays,
        # Overlay settings for restoration
        'show_bones': overlay.show_bones,
        'show_floor': overlay.show_floor,
        'show_axis_x': overlay.show_axis_x,
        'show_axis_y': overlay.show_axis_y,
        'show_axis_z': overlay.show_axis_z,
        'show_cursor': overlay.show_cursor,
        'show_object_origins': overlay.show_object_origins,
        'show_relationship_lines': overlay.show_relationship_lines,
        'show_outline_selected': overlay.show_outline_selected,
        'show_extras': overlay.show_extras,
        'show_motion_paths': overlay.show_motion_paths,
    }

    # Store media_type if available (Blender 4.5+/5.0)
    if hasattr(render.image_settings, 'media_type'):
        original['media_type'] = render.image_settings.media_type

    # Store Cycles settings if needed
    cycles = None
    if is_cycles:
        cycles = scene.cycles
        original['cycles'] = {
            'samples': cycles.samples,
            'use_adaptive_sampling': cycles.use_adaptive_sampling,
            'adaptive_threshold': cycles.adaptive_threshold,
            'use_denoising': cycles.use_denoising,
            'denoising_input_passes': cycles.denoising_input_passes,
            'denoising_prefilter': cycles.denoising_prefilter,
            'denoising_quality': cycles.denoising_quality,
            'denoising_use_gpu': cycles.denoising_use_gpu,
        }

    render_image = None
    cropped_image = None

    try:
        # 4. Render viewport at full resolution
        render.resolution_x = region_width
        render.resolution_y = region_height
        render.resolution_percentage = 100

        # IMPORTANT: In Blender 4.5+/5.0, must set media_type to 'IMAGE' first
        if hasattr(render.image_settings, 'media_type'):
            render.image_settings.media_type = 'IMAGE'
        render.image_settings.file_format = 'PNG'
        render.image_settings.color_depth = '8'

        # Configure overlays based on asset type
        if asset_type == 'rig':
            # For rigs: show bones only, hide everything else
            overlay.show_overlays = True
            overlay.show_bones = True
            overlay.show_floor = False
            overlay.show_axis_x = False
            overlay.show_axis_y = False
            overlay.show_axis_z = False
            overlay.show_cursor = False
            overlay.show_object_origins = False
            overlay.show_relationship_lines = False
            overlay.show_outline_selected = False
            overlay.show_extras = False
            overlay.show_motion_paths = False
        else:
            # For other types: hide all overlays for clean render
            overlay.show_overlays = False

        # Optimize Cycles for speed
        if is_cycles and cycles:
            cycles.samples = 4
            cycles.use_adaptive_sampling = True
            cycles.adaptive_threshold = 0.1
            cycles.use_denoising = True
            cycles.denoising_input_passes = 'RGB'
            cycles.denoising_prefilter = 'FAST'
            cycles.denoising_quality = 'FAST'
            cycles.denoising_use_gpu = True

        # Render based on shading mode
        with context.temp_override(area=view3d_area, region=view3d_region):
            if is_cycles:
                bpy.ops.render.render(write_still=False)
            else:
                bpy.ops.render.opengl()

        # Get render result
        result = bpy.data.images.get('Render Result')
        if not result:
            create_placeholder_thumbnail(filepath, size)
            return False

        # Save render result to temporary file (needed for loading into numpy)
        temp_render_path = Path(tempfile.gettempdir()) / "_ual_temp_render.png"
        result.save_render(filepath=str(temp_render_path))

        # Load the saved image for numpy processing
        render_image = bpy.data.images.load(str(temp_render_path))

        # 5. Crop using numpy
        pixels = np.array(render_image.pixels[:])
        pixels = pixels.reshape((region_height, region_width, 4))

        # Crop to bounding box (note: numpy uses [row, col] = [y, x])
        cropped_pixels = pixels[ymin:ymax, xmin:xmax, :]

        # Create cropped image
        cropped_image = bpy.data.images.new(
            "_UAL_cropped_thumbnail",
            width=crop_width,
            height=crop_height
        )
        cropped_image.pixels[:] = cropped_pixels.flatten()

        # 6. Scale to target size
        scale_factor = max(crop_width, crop_height) / size
        if scale_factor > 1:
            new_width = int(crop_width / scale_factor)
            new_height = int(crop_height / scale_factor)
            cropped_image.scale(new_width, new_height)

        # 7. Save to file
        cropped_image.filepath_raw = filepath
        cropped_image.file_format = 'PNG'
        cropped_image.save()

        if Path(filepath).exists():
            success = True

        # Cleanup temp file
        if temp_render_path.exists():
            temp_render_path.unlink()

    except Exception:
        pass

    finally:
        # Restore all settings
        render.resolution_x = original['resolution_x']
        render.resolution_y = original['resolution_y']
        render.resolution_percentage = original['resolution_percentage']

        # Restore media_type first (Blender 4.5+/5.0), then file_format
        if 'media_type' in original and hasattr(render.image_settings, 'media_type'):
            render.image_settings.media_type = original['media_type']
        render.image_settings.file_format = original['file_format']
        render.image_settings.color_depth = original['color_depth']

        # Restore all overlay settings
        overlay.show_overlays = original['show_overlays']
        overlay.show_bones = original['show_bones']
        overlay.show_floor = original['show_floor']
        overlay.show_axis_x = original['show_axis_x']
        overlay.show_axis_y = original['show_axis_y']
        overlay.show_axis_z = original['show_axis_z']
        overlay.show_cursor = original['show_cursor']
        overlay.show_object_origins = original['show_object_origins']
        overlay.show_relationship_lines = original['show_relationship_lines']
        overlay.show_outline_selected = original['show_outline_selected']
        overlay.show_extras = original['show_extras']
        overlay.show_motion_paths = original['show_motion_paths']

        # Restore Cycles settings
        if is_cycles and cycles and 'cycles' in original:
            for key, value in original['cycles'].items():
                setattr(cycles, key, value)

        # Cleanup temp images
        if render_image:
            bpy.data.images.remove(render_image, do_unlink=True)
        if cropped_image:
            bpy.data.images.remove(cropped_image, do_unlink=True)

    # Fallback to placeholder if failed
    if not success:
        try:
            create_placeholder_thumbnail(filepath, size)
        except Exception:
            pass

    return success


def _capture_viewport_full(context, filepath: str, size: int = 256) -> bool:
    """Render the full viewport and scale to thumbnail size. No cropping.

    Used when the viewport has already been framed to show the desired content
    (e.g. after _frame_viewport_to_bbox). Renders the viewport as-is
    and scales the result to a square thumbnail.

    Args:
        context: Blender context
        filepath: Output file path
        size: Target thumbnail size in pixels (square)

    Returns:
        bool: True if successful
    """
    view3d_area, view3d_region, view3d_space = get_3d_viewport(context)
    if not view3d_area:
        create_placeholder_thumbnail(filepath, size)
        return False

    region_width = view3d_region.width
    region_height = view3d_region.height

    scene = context.scene
    render = scene.render

    is_cycles = is_cycles_rendered_view(context, view3d_space)

    # Store original settings
    original = {
        'resolution_x': render.resolution_x,
        'resolution_y': render.resolution_y,
        'resolution_percentage': render.resolution_percentage,
        'file_format': render.image_settings.file_format,
        'color_depth': render.image_settings.color_depth,
        'show_overlays': view3d_space.overlay.show_overlays,
    }

    if hasattr(render.image_settings, 'media_type'):
        original['media_type'] = render.image_settings.media_type

    cycles = None
    if is_cycles:
        cycles = scene.cycles
        original['cycles'] = {
            'samples': cycles.samples,
            'use_adaptive_sampling': cycles.use_adaptive_sampling,
            'adaptive_threshold': cycles.adaptive_threshold,
            'use_denoising': cycles.use_denoising,
            'denoising_input_passes': cycles.denoising_input_passes,
            'denoising_prefilter': cycles.denoising_prefilter,
            'denoising_quality': cycles.denoising_quality,
            'denoising_use_gpu': cycles.denoising_use_gpu,
        }

    render_image = None
    scaled_image = None
    success = False

    try:
        render.resolution_x = region_width
        render.resolution_y = region_height
        render.resolution_percentage = 100

        if hasattr(render.image_settings, 'media_type'):
            render.image_settings.media_type = 'IMAGE'
        render.image_settings.file_format = 'PNG'
        render.image_settings.color_depth = '8'
        view3d_space.overlay.show_overlays = False

        if is_cycles and cycles:
            cycles.samples = 4
            cycles.use_adaptive_sampling = True
            cycles.adaptive_threshold = 0.1
            cycles.use_denoising = True
            cycles.denoising_input_passes = 'RGB'
            cycles.denoising_prefilter = 'FAST'
            cycles.denoising_quality = 'FAST'
            cycles.denoising_use_gpu = True

        with context.temp_override(area=view3d_area, region=view3d_region):
            if is_cycles:
                bpy.ops.render.render(write_still=False)
            else:
                bpy.ops.render.opengl()

        result = bpy.data.images.get('Render Result')
        if not result:
            create_placeholder_thumbnail(filepath, size)
            return False

        temp_render_path = Path(tempfile.gettempdir()) / "_ual_temp_full_render.png"
        result.save_render(filepath=str(temp_render_path))

        render_image = bpy.data.images.load(str(temp_render_path))

        # Square-crop the center of the image (no bbox projection needed)
        pixels = np.array(render_image.pixels[:])
        pixels = pixels.reshape((region_height, region_width, 4))

        # Crop to center square
        if region_width > region_height:
            offset = (region_width - region_height) // 2
            pixels = pixels[:, offset:offset + region_height, :]
            sq = region_height
        elif region_height > region_width:
            offset = (region_height - region_width) // 2
            pixels = pixels[offset:offset + region_width, :, :]
            sq = region_width
        else:
            sq = region_width

        scaled_image = bpy.data.images.new("_UAL_full_thumbnail", width=sq, height=sq)
        scaled_image.pixels[:] = pixels.flatten()

        # Scale to target size
        if sq != size:
            scaled_image.scale(size, size)

        scaled_image.filepath_raw = filepath
        scaled_image.file_format = 'PNG'
        scaled_image.save()

        if Path(filepath).exists():
            success = True

        if temp_render_path.exists():
            temp_render_path.unlink()

    except Exception:
        pass

    finally:
        render.resolution_x = original['resolution_x']
        render.resolution_y = original['resolution_y']
        render.resolution_percentage = original['resolution_percentage']

        if 'media_type' in original and hasattr(render.image_settings, 'media_type'):
            render.image_settings.media_type = original['media_type']
        render.image_settings.file_format = original['file_format']
        render.image_settings.color_depth = original['color_depth']
        view3d_space.overlay.show_overlays = original['show_overlays']

        if is_cycles and cycles and 'cycles' in original:
            for key, value in original['cycles'].items():
                setattr(cycles, key, value)

        if render_image:
            bpy.data.images.remove(render_image, do_unlink=True)
        if scaled_image:
            bpy.data.images.remove(scaled_image, do_unlink=True)

    if not success:
        try:
            create_placeholder_thumbnail(filepath, size)
        except Exception:
            pass

    return success


def _get_collection_objects_recursive(collection) -> list:
    """Recursively gather all objects from a collection and its children.

    Args:
        collection: Blender collection

    Returns:
        list: All objects in the collection hierarchy
    """
    objects = list(collection.objects)
    for child_col in collection.children:
        objects.extend(_get_collection_objects_recursive(child_col))
    return objects


def _frame_viewport_to_bbox(view3d_space, bbox_3d):
    """Position the viewport to frame a 3D bounding box.

    Calculates the center and bounding sphere of the bbox, then sets
    view_location and view_distance so all objects are visible.

    Args:
        view3d_space: View3D space data
        bbox_3d: List of 3D Vector coordinates (world-space bounding box corners)
    """
    rv3d = view3d_space.region_3d

    # Calculate bbox center
    xs = [co.x for co in bbox_3d]
    ys = [co.y for co in bbox_3d]
    zs = [co.z for co in bbox_3d]

    center = Vector((
        (min(xs) + max(xs)) / 2,
        (min(ys) + max(ys)) / 2,
        (min(zs) + max(zs)) / 2,
    ))

    # Bounding sphere radius (half the diagonal)
    size_vec = Vector((
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs),
    ))
    half_diagonal = size_vec.length / 2

    # Ensure minimum size for tiny/flat objects
    half_diagonal = max(half_diagonal, 0.5)

    # Calculate distance to fit the bounding sphere
    if rv3d.view_perspective == 'ORTHO':
        # Ortho: view_distance directly controls visible size
        distance = half_diagonal * 2.0
    else:
        # Perspective: distance from FOV
        # Blender default sensor width = 36mm
        lens = view3d_space.lens  # focal length in mm
        fov = 2.0 * math.atan(36.0 / (2.0 * lens))
        distance = half_diagonal / math.tan(fov / 2.0)

    # 20% padding so objects aren't right at the edges
    distance *= 1.2

    rv3d.view_location = center
    rv3d.view_distance = distance


def _capture_from_camera(context, scene, filepath: str, size: int = 256) -> bool:
    """Capture thumbnail by rendering from the scene's active camera.

    Uses OpenGL viewport render from the camera's perspective for speed.
    No cropping needed since the camera defines the framing.

    Args:
        context: Blender context
        scene: Blender scene with an active camera
        filepath: Output file path
        size: Target thumbnail size in pixels (square)

    Returns:
        bool: True if successful
    """
    view3d_area, view3d_region, view3d_space = get_3d_viewport(context)
    if not view3d_area:
        create_placeholder_thumbnail(filepath, size)
        return False

    render = scene.render
    rv3d = view3d_space.region_3d

    # Save original state
    original = {
        'resolution_x': render.resolution_x,
        'resolution_y': render.resolution_y,
        'resolution_percentage': render.resolution_percentage,
        'file_format': render.image_settings.file_format,
        'color_depth': render.image_settings.color_depth,
        'show_overlays': view3d_space.overlay.show_overlays,
        'view_perspective': rv3d.view_perspective,
        'view_camera_zoom': rv3d.view_camera_zoom,
        'view_camera_offset': (rv3d.view_camera_offset[0], rv3d.view_camera_offset[1]),
    }

    if hasattr(render.image_settings, 'media_type'):
        original['media_type'] = render.image_settings.media_type

    render_image = None
    success = False

    try:
        # Switch to camera view
        rv3d.view_perspective = 'CAMERA'
        rv3d.view_camera_zoom = 0
        rv3d.view_camera_offset[0] = 0.0
        rv3d.view_camera_offset[1] = 0.0

        # Set square render resolution for thumbnail
        render.resolution_x = size
        render.resolution_y = size
        render.resolution_percentage = 100

        if hasattr(render.image_settings, 'media_type'):
            render.image_settings.media_type = 'IMAGE'
        render.image_settings.file_format = 'PNG'
        render.image_settings.color_depth = '8'
        view3d_space.overlay.show_overlays = False

        # OpenGL render from camera
        with context.temp_override(area=view3d_area, region=view3d_region):
            bpy.ops.render.opengl()

        # Get and save result
        result = bpy.data.images.get('Render Result')
        if not result:
            create_placeholder_thumbnail(filepath, size)
            return False

        # Save render result to temp then load for processing
        temp_render_path = Path(tempfile.gettempdir()) / "_ual_temp_camera_render.png"
        result.save_render(filepath=str(temp_render_path))

        render_image = bpy.data.images.load(str(temp_render_path))

        # Scale to target size if render resolution doesn't match
        if render_image.size[0] != size or render_image.size[1] != size:
            render_image.scale(size, size)

        render_image.filepath_raw = filepath
        render_image.file_format = 'PNG'
        render_image.save()

        if Path(filepath).exists():
            success = True

        if temp_render_path.exists():
            temp_render_path.unlink()

    except Exception:
        pass

    finally:
        # Restore settings
        render.resolution_x = original['resolution_x']
        render.resolution_y = original['resolution_y']
        render.resolution_percentage = original['resolution_percentage']

        if 'media_type' in original and hasattr(render.image_settings, 'media_type'):
            render.image_settings.media_type = original['media_type']
        render.image_settings.file_format = original['file_format']
        render.image_settings.color_depth = original['color_depth']
        view3d_space.overlay.show_overlays = original['show_overlays']

        # Restore viewport
        rv3d.view_perspective = original['view_perspective']
        rv3d.view_camera_zoom = original['view_camera_zoom']
        rv3d.view_camera_offset[0] = original['view_camera_offset'][0]
        rv3d.view_camera_offset[1] = original['view_camera_offset'][1]

        if render_image:
            bpy.data.images.remove(render_image, do_unlink=True)

    if not success:
        try:
            create_placeholder_thumbnail(filepath, size)
        except Exception:
            pass

    return success


def capture_collection_thumbnail(context, collection, filepath: str, size: int = 256) -> bool:
    """Generate thumbnail for a collection by framing all its objects.

    Computes the 3D bounding box of all collection objects, positions the
    viewport to frame it, then captures. Restores viewport state afterward.

    Args:
        context: Blender context
        collection: Blender collection to capture
        filepath: Output file path
        size: Target thumbnail size in pixels

    Returns:
        bool: True if successful
    """
    # Gather all objects from collection hierarchy
    all_objects = _get_collection_objects_recursive(collection)
    if not all_objects:
        create_placeholder_thumbnail(filepath, size)
        return False

    # Get 3D bounding box
    bbox_3d = get_objects_bbox_3d(all_objects)
    if not bbox_3d:
        create_placeholder_thumbnail(filepath, size)
        return False

    view3d_area, view3d_region, view3d_space = get_3d_viewport(context)
    if not view3d_area:
        create_placeholder_thumbnail(filepath, size)
        return False

    with preserve_viewport_state(view3d_space):
        rv3d = view3d_space.region_3d

        # Exit camera view — need perspective/ortho for bbox framing
        if rv3d.view_perspective == 'CAMERA':
            rv3d.view_perspective = 'PERSP'

        # Frame the bounding box
        _frame_viewport_to_bbox(view3d_space, bbox_3d)

        # Capture the full viewport — already framed, no crop needed
        return _capture_viewport_full(context, filepath, size)


def capture_scene_thumbnail(context, scene, filepath: str, size: int = 256) -> bool:
    """Generate thumbnail for a scene.

    If the scene has an active camera, renders from the camera's perspective.
    Otherwise, computes the 3D bounding box of all scene objects, positions the
    viewport to frame it, then captures.

    Args:
        context: Blender context
        scene: Blender scene to capture
        filepath: Output file path
        size: Target thumbnail size in pixels

    Returns:
        bool: True if successful
    """
    # If scene has a camera, render from it
    if scene.camera:
        return _capture_from_camera(context, scene, filepath, size)

    # No camera — frame all scene objects via bounding box
    all_objects = list(scene.objects)
    if not all_objects:
        create_placeholder_thumbnail(filepath, size)
        return False

    bbox_3d = get_objects_bbox_3d(all_objects)
    if not bbox_3d:
        create_placeholder_thumbnail(filepath, size)
        return False

    view3d_area, view3d_region, view3d_space = get_3d_viewport(context)
    if not view3d_area:
        create_placeholder_thumbnail(filepath, size)
        return False

    with preserve_viewport_state(view3d_space):
        rv3d = view3d_space.region_3d

        # Exit camera view if active
        if rv3d.view_perspective == 'CAMERA':
            rv3d.view_perspective = 'PERSP'

        # Frame the bounding box
        _frame_viewport_to_bbox(view3d_space, bbox_3d)

        # Capture the full viewport — already framed, no crop needed
        return _capture_viewport_full(context, filepath, size)


__all__ = [
    'get_3d_viewport',
    'get_objects_bbox_3d',
    'bbox_to_screen',
    'make_square_bbox',
    'is_cycles_rendered_view',
    'create_placeholder_thumbnail',
    'capture_viewport_thumbnail',
    'capture_collection_thumbnail',
    'capture_scene_thumbnail',
]
