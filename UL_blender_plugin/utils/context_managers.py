"""
Context Managers for Blender Operations

Provides safe, auto-restoring context managers for common Blender state changes.
"""

from contextlib import contextmanager
from typing import Set, List, Tuple, Optional
import bpy


@contextmanager
def render_settings(
    scene,
    resolution: Tuple[int, int] = (256, 256),
    file_format: str = 'PNG',
    color_depth: str = '8',
    filepath: Optional[str] = None
):
    """
    Context manager for temporarily changing render settings.

    Automatically restores original settings on exit.

    Args:
        scene: Blender scene
        resolution: Tuple of (width, height)
        file_format: Image format (PNG, JPEG, etc.)
        color_depth: Color depth (8, 16, etc.)
        filepath: Optional render filepath

    Usage:
        with render_settings(scene, resolution=(512, 512)):
            bpy.ops.render.render()
    """
    render = scene.render

    # Save original settings
    original = {
        'resolution_x': render.resolution_x,
        'resolution_y': render.resolution_y,
        'resolution_percentage': render.resolution_percentage,
        'file_format': render.image_settings.file_format,
        'color_depth': render.image_settings.color_depth,
        'filepath': render.filepath,
    }

    # Store media_type if available (Blender 4.5+/5.0)
    if hasattr(render.image_settings, 'media_type'):
        original['media_type'] = render.image_settings.media_type

    try:
        # Apply new settings
        render.resolution_x = resolution[0]
        render.resolution_y = resolution[1]
        render.resolution_percentage = 100

        # IMPORTANT: In Blender 4.5+/5.0, must set media_type to 'IMAGE' first
        if hasattr(render.image_settings, 'media_type'):
            render.image_settings.media_type = 'IMAGE'
        render.image_settings.file_format = file_format
        render.image_settings.color_depth = color_depth
        if filepath:
            render.filepath = filepath

        yield render

    finally:
        # Restore original settings
        render.resolution_x = original['resolution_x']
        render.resolution_y = original['resolution_y']
        render.resolution_percentage = original['resolution_percentage']

        # Restore media_type first (Blender 4.5+/5.0), then file_format
        if 'media_type' in original and hasattr(render.image_settings, 'media_type'):
            render.image_settings.media_type = original['media_type']
        render.image_settings.file_format = original['file_format']
        render.image_settings.color_depth = original['color_depth']
        render.filepath = original['filepath']


@contextmanager
def viewport_overlays(view3d_space, show_overlays: bool = False):
    """
    Context manager for temporarily changing viewport overlay visibility.

    Args:
        view3d_space: View3D space data
        show_overlays: Whether to show overlays

    Usage:
        with viewport_overlays(space, show_overlays=False):
            # Render without overlays
    """
    if view3d_space is None:
        yield
        return

    original = view3d_space.overlay.show_overlays

    try:
        view3d_space.overlay.show_overlays = show_overlays
        yield

    finally:
        view3d_space.overlay.show_overlays = original


@contextmanager
def preserve_selection(context):
    """
    Context manager that preserves and restores object selection state.

    Args:
        context: Blender context

    Usage:
        with preserve_selection(context):
            bpy.ops.object.select_all(action='DESELECT')
            # Do something
        # Original selection restored
    """
    # Save current state
    original_selected = [obj for obj in context.selected_objects]
    original_active = context.view_layer.objects.active

    try:
        yield

    finally:
        # Restore selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in original_selected:
            try:
                obj.select_set(True)
            except (ReferenceError, RuntimeError):
                pass

        # Restore active
        if original_active:
            try:
                context.view_layer.objects.active = original_active
            except (ReferenceError, RuntimeError):
                pass


class ObjectImportTracker:
    """
    Context manager that tracks new objects created during import.

    Attributes:
        new_objects: List of objects created during the context

    Usage:
        with ObjectImportTracker(context) as tracker:
            bpy.ops.wm.append(...)
        new_objs = tracker.new_objects
    """

    def __init__(self, context):
        self.context = context
        self.objects_before: Set[bpy.types.Object] = set()
        self.new_objects: List[bpy.types.Object] = []

    def __enter__(self):
        self.objects_before = set(self.context.scene.objects)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        objects_after = set(self.context.scene.objects)
        self.new_objects = list(objects_after - self.objects_before)
        return False


@contextmanager
def object_import_tracker(context):
    """
    Functional version of ObjectImportTracker.

    Yields a list that will be populated with new objects after the context exits.

    Usage:
        with object_import_tracker(context) as new_objects:
            bpy.ops.wm.append(...)
        # new_objects now contains imported objects
    """
    objects_before = set(context.scene.objects)
    new_objects = []

    yield new_objects

    objects_after = set(context.scene.objects)
    new_objects.extend(objects_after - objects_before)


@contextmanager
def cycles_settings(scene, samples: int = 32, use_denoising: bool = False):
    """
    Context manager for temporarily changing Cycles render settings.

    Args:
        scene: Blender scene
        samples: Number of render samples
        use_denoising: Whether to use denoising

    Usage:
        with cycles_settings(scene, samples=64):
            bpy.ops.render.render()
    """
    cycles = scene.cycles if hasattr(scene, 'cycles') else None

    if cycles is None:
        yield
        return

    # Save original settings
    original = {
        'samples': cycles.samples,
        'use_denoising': cycles.use_denoising,
        'use_adaptive_sampling': cycles.use_adaptive_sampling,
    }

    try:
        cycles.samples = samples
        cycles.use_denoising = use_denoising
        cycles.use_adaptive_sampling = False

        yield cycles

    finally:
        for key, value in original.items():
            setattr(cycles, key, value)


@contextmanager
def preserve_viewport_state(view3d_space):
    """
    Context manager that preserves and restores the 3D viewport navigation state.

    Saves and restores view_location, view_rotation, view_distance,
    view_perspective, view_camera_zoom, view_camera_offset, and lock_camera.

    Args:
        view3d_space: View3D space data

    Usage:
        with preserve_viewport_state(space):
            # Manipulate viewport (view_selected, camera switch, etc.)
        # Original viewport state restored
    """
    if view3d_space is None:
        yield
        return

    rv3d = view3d_space.region_3d

    # Save current viewport navigation state
    original = {
        'view_location': rv3d.view_location.copy(),
        'view_rotation': rv3d.view_rotation.copy(),
        'view_distance': rv3d.view_distance,
        'view_perspective': rv3d.view_perspective,
        'view_camera_zoom': rv3d.view_camera_zoom,
        'view_camera_offset': (rv3d.view_camera_offset[0], rv3d.view_camera_offset[1]),
        'lock_camera': rv3d.lock_rotation,
    }

    try:
        yield rv3d

    finally:
        rv3d.view_location = original['view_location']
        rv3d.view_rotation = original['view_rotation']
        rv3d.view_distance = original['view_distance']
        rv3d.view_perspective = original['view_perspective']
        rv3d.view_camera_zoom = original['view_camera_zoom']
        rv3d.view_camera_offset[0] = original['view_camera_offset'][0]
        rv3d.view_camera_offset[1] = original['view_camera_offset'][1]
        rv3d.lock_rotation = original['lock_camera']


__all__ = [
    'render_settings',
    'viewport_overlays',
    'preserve_selection',
    'ObjectImportTracker',
    'object_import_tracker',
    'cycles_settings',
    'preserve_viewport_state',
]
