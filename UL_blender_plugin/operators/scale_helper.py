"""
M5 — Scale Reference (Blender side).

Draws a 1.8 m human silhouette in the 3D viewport, placed next to the
active object's world bbox, so users can eye-check asset scale BEFORE
exporting. Rig-aware: when an armature is selected, the bbox includes
all bound meshes (same resolver `_collect_rig_export_meshes` uses for
exports, so the reference reflects what the user is actually shipping).

Implementation choice (Option B from spec): pure GPU draw handler.
No scene datablocks are created — the silhouette is rendered every
viewport draw via `SpaceView3D.draw_handler_add()` so it doesn't pollute
the outliner, isn't selectable, doesn't survive a .blend save, and
doesn't tangle with undo. Cost: more code than the Empty-image approach,
but cleaner UX.

State lives on `context.scene.ual_props` (see `panels/library_panel.py`):
    scale_ref_enabled         bool — handler installs when this flips True
    scale_ref_height          float — silhouette height in metres
    scale_ref_locked          bool — when True, ignore selection changes
    scale_ref_locked_position vec3 — anchor used while locked

Toggling on/off:
    The enabled-prop has an `update=` callback that just retriggers
    viewport redraw. Actual handler install/remove is managed here in
    `_sync_handler_state` which is called from the update callback AND
    on addon register so the state is consistent regardless of how the
    enabled flag got flipped (UI click, scene load, programmatic set).
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import bpy
import gpu
from bpy.types import Operator
from gpu_extras.batch import batch_for_shader
from mathutils import Vector


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Silhouette texture
# ---------------------------------------------------------------------------
# Path to the bundled silhouette PNG (front-facing, transparent BG). The image
# gets loaded into bpy.data.images on first draw and uploaded to a GPU texture
# that we billboard every frame as a textured quad.

_RESOURCES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources",
)
_SILHOUETTE_PNG = os.path.join(_RESOURCES_DIR, "human_silhouette.png")
_SILHOUETTE_IMAGE_NAME = "_UL_SCALE_REF_SILHOUETTE"

# The half-width of the silhouette quad relative to its height, used to
# compute the breathing-room offset so the silhouette's left edge clears
# the bbox cleanly. PNG is roughly 256×512 (1:2), so the quad's half-width
# in normalized height units is 0.25. Tweak if your PNG aspect changes.
_SILHOUETTE_HALF_WIDTH_NORM = 0.25


# ---------------------------------------------------------------------------
# Bbox computation (rig-aware)
# ---------------------------------------------------------------------------

def _resolve_target_objects(context) -> List[bpy.types.Object]:
    """Pick the objects whose union bbox the silhouette stands next to.

    Behaviour:
    - Single selected ARMATURE → that armature + every mesh bound to it
      via Armature modifier or parenting. Matches the rig-export resolver
      so the on-screen scale check reflects what'll actually be saved.
    - Anything else → the user's selection, minus objects with no bbox.
    """
    selected = context.selected_objects
    if not selected:
        active = context.active_object
        return [active] if active is not None else []

    if len(selected) == 1 and selected[0].type == 'ARMATURE':
        try:
            # Reuse the canonical rig export resolver.
            from .export_to_library import UAL_OT_export_to_library
            # The resolver is a method but doesn't use any instance state
            # beyond _add helpers — safe to call via the unbound function
            # using a throwaway dict-like or by constructing a temp instance.
            armature = selected[0]
            bound = _collect_rig_bound_meshes(armature)
            return [armature] + bound
        except Exception:
            logger.exception("scale_ref: rig bbox resolver failed, falling back")
            return list(selected)

    return [o for o in selected if o.type in {'MESH', 'CURVE', 'SURFACE', 'META',
                                                'FONT', 'CURVES', 'GPENCIL',
                                                'GREASEPENCIL', 'POINTCLOUD',
                                                'VOLUME', 'ARMATURE', 'EMPTY'}]


def _collect_rig_bound_meshes(armature) -> List[bpy.types.Object]:
    """Inline copy of the rig-export bound-mesh resolver, intentionally
    independent of UAL_OT_export_to_library so the draw handler doesn't
    instantiate the operator class just to read a list of meshes.
    """
    out: List[bpy.types.Object] = []
    seen = set()
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH' or obj.name in seen:
            continue
        # Bound via Armature modifier?
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE' and mod.object is armature:
                out.append(obj)
                seen.add(obj.name)
                break
        if obj.name in seen:
            continue
        # Or parented?
        if obj.parent is armature:
            out.append(obj)
            seen.add(obj.name)
    return out


def _compute_world_bbox(objects) -> Optional[Tuple[Vector, Vector]]:
    """Union world-space bbox of `objects`. Returns (min, max) or None."""
    corners: List[Vector] = []
    for obj in objects:
        if obj is None:
            continue
        try:
            bb = obj.bound_box
        except (AttributeError, ReferenceError):
            continue
        if not bb:
            continue
        mat = obj.matrix_world
        for c in bb:
            corners.append(mat @ Vector(c))
    if not corners:
        return None
    xs = [v.x for v in corners]
    ys = [v.y for v in corners]
    zs = [v.z for v in corners]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def _compute_anchor(bbox_min: Vector, bbox_max: Vector, height: float,
                    half_width_norm: float = _SILHOUETTE_HALF_WIDTH_NORM) -> Vector:
    """Pick the world position where the silhouette's feet should land.

    Default rule: stand to the right (+X) of the bbox with a clear gap,
    feet on the world ground plane (Z = 0). X and Y track the bbox so the
    silhouette stays "next to" the asset; Z stays grounded so a flying or
    raised asset (chair on a table, hovering ship) doesn't make the
    reference human float in mid-air — which would defeat the scale check.

    The X offset has two parts:
        1. `silhouette_half_width` — pushes the anchor past where the
           silhouette quad's left edge actually sits (otherwise it ends up
           INSIDE the bbox).
        2. `breathing_room` — visible empty space between the bbox and
           the silhouette, scaled to silhouette height so a tall ref
           also gets proportionally more space.

    `half_width_norm` is the quad's half-width relative to its height; the
    caller passes the value derived from the loaded PNG's aspect ratio.
    """
    silhouette_half_width = half_width_norm * height
    breathing_room = 0.25 * height
    offset = silhouette_half_width + breathing_room
    return Vector((
        bbox_max.x + offset,
        (bbox_min.y + bbox_max.y) * 0.5,
        0.0,
    ))


# ---------------------------------------------------------------------------
# GPU draw state
# ---------------------------------------------------------------------------

# Built lazily on first draw — depends on the GPU module + bpy.data being
# fully initialized, which only happens once Blender is running with a
# viewport. Image + texture references are held module-level so they
# persist across draws.
_shader = None
_image = None
_gpu_texture = None
_quad_aspect = 0.5    # half-width / height; refined once the image loads
_draw_handler = None
_msgbus_owner = object()


def _ensure_texture():
    """Load the silhouette PNG into `bpy.data.images` and build a GPU
    texture from it. Cached for the rest of the session.

    Returns the (shader, texture, half_width_norm) tuple, or None if
    the image couldn't be loaded — caller bails on that.
    """
    global _shader, _image, _gpu_texture, _quad_aspect

    if _gpu_texture is not None and _shader is not None:
        return _shader, _gpu_texture, _quad_aspect

    if not os.path.exists(_SILHOUETTE_PNG):
        logger.warning("scale_ref: silhouette PNG missing at %s", _SILHOUETTE_PNG)
        return None

    # Re-use an existing data-block if we already loaded once (e.g. across
    # an addon reload) so we don't accumulate duplicates in bpy.data.images.
    if _image is None or _image.name not in bpy.data.images:
        try:
            _image = bpy.data.images.load(_SILHOUETTE_PNG, check_existing=True)
            # Stable internal name so we can find it again after a reload.
            _image.name = _SILHOUETTE_IMAGE_NAME
        except (RuntimeError, OSError):
            logger.exception("scale_ref: failed to load silhouette PNG")
            return None

    try:
        _gpu_texture = gpu.texture.from_image(_image)
    except (RuntimeError, ValueError):
        logger.exception("scale_ref: failed to create GPU texture")
        return None

    # Real PNG aspect overrides the conservative default of 0.5.
    w, h = _image.size
    if w > 0 and h > 0:
        _quad_aspect = (w / h) / 2.0   # half-width / full-height

    # IMAGE_COLOR shader: samples a texture, multiplies by an optional tint.
    # Built-in shader name: 'IMAGE' (Blender 3.5+). It expects 'pos' + 'texCoord'.
    _shader = gpu.shader.from_builtin('IMAGE')

    return _shader, _gpu_texture, _quad_aspect


def _draw_callback():
    """POST_VIEW draw fn. Cheap: a few bbox vectors + 1 textured quad."""
    context = bpy.context
    try:
        props = context.scene.ual_props
    except (AttributeError, ReferenceError):
        return
    if not props.scale_ref_enabled:
        return

    height = float(props.scale_ref_height)
    if height <= 0:
        return

    tex_info = _ensure_texture()
    if tex_info is None:
        return
    shader, texture, half_width_norm = tex_info

    # Resolve anchor: locked uses stored vector, unlocked recomputes from bbox.
    if props.scale_ref_locked:
        anchor = Vector(props.scale_ref_locked_position)
    else:
        objs = _resolve_target_objects(context)
        bbox = _compute_world_bbox(objs)
        if bbox is None:
            return
        anchor = _compute_anchor(bbox[0], bbox[1], height, half_width_norm)
        # Stash the live anchor so the user can click Lock without the
        # silhouette jumping (the lock-button operator just copies this).
        try:
            props.scale_ref_locked_position = anchor
        except Exception:
            pass

    # Billboard axes: camera's right (projected against world Z), and world Z.
    # This keeps the silhouette upright like a real person standing.
    region_3d = context.region_data
    if region_3d is None:
        return
    view_mat = region_3d.view_matrix
    inv = view_mat.inverted_safe()
    right = Vector((inv[0][0], inv[1][0], inv[2][0]))
    up = Vector((0.0, 0.0, 1.0))
    # Re-orthogonalize right against up so the silhouette stays a clean
    # rectangle even when the camera is pitched.
    right = right - up * right.dot(up)
    if right.length < 1e-6:
        right = Vector((1.0, 0.0, 0.0))
    else:
        right = right.normalized()

    # Quad corners — feet on ground, head on top, billboard-flat against camera.
    half_w = half_width_norm * height
    bl = anchor + right * (-half_w)
    br = anchor + right * (half_w)
    tl = bl + up * height
    tr = br + up * height

    positions = [tuple(bl), tuple(br), tuple(tr), tuple(tl)]
    # UV layout: PNG has feet at the BOTTOM, head at the TOP, so v=0 is feet.
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    indices = [(0, 1, 2), (0, 2, 3)]

    batch = batch_for_shader(
        shader, 'TRIS',
        {"pos": [positions[i] for tri in indices for i in tri],
         "texCoord": [uvs[i] for tri in indices for i in tri]},
    )

    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    shader.bind()
    shader.uniform_sampler("image", texture)
    batch.draw(shader)
    gpu.state.depth_mask_set(True)
    gpu.state.blend_set('NONE')


# ---------------------------------------------------------------------------
# Handler lifecycle
# ---------------------------------------------------------------------------

def _on_active_object_changed():
    """msgbus callback: tag viewports to redraw when the active object
    changes so the silhouette repositions live. Cheap — the draw handler
    is what reads the bbox; this just triggers a redraw."""
    try:
        if not bpy.context.scene.ual_props.scale_ref_enabled:
            return
    except (AttributeError, ReferenceError):
        return
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _install_handler():
    global _draw_handler
    if _draw_handler is not None:
        return
    _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        _draw_callback, (), 'WINDOW', 'POST_VIEW',
    )
    # Auto-reposition on active object change.
    try:
        bpy.msgbus.subscribe_rna(
            key=(bpy.types.LayerObjects, "active"),
            owner=_msgbus_owner,
            args=(),
            notify=_on_active_object_changed,
        )
    except Exception:
        logger.exception("scale_ref: msgbus subscribe failed (non-fatal)")


def _remove_handler():
    global _draw_handler
    if _draw_handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, 'WINDOW')
        except (ValueError, RuntimeError):
            pass
        _draw_handler = None
    try:
        bpy.msgbus.clear_by_owner(_msgbus_owner)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class UAL_OT_lock_scale_reference(Operator):
    """Toggle the lock state of the scale-reference silhouette.

    Locked = silhouette stays where it is, even if the user selects something
    else. Unlocked = silhouette repositions to follow the active object.
    """
    bl_idname = "ual.lock_scale_reference"
    bl_label = "Lock Scale Reference"
    bl_description = "Pin the silhouette in place (unlock to follow selection)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, 'ual_props')

    def execute(self, context):
        props = context.scene.ual_props
        if not props.scale_ref_locked:
            # Snapshot the live anchor before locking so the silhouette
            # doesn't visually jump on the next redraw. Use the module's
            # current `_quad_aspect` (set by _ensure_texture once the PNG
            # is loaded) so the offset matches what's actually rendered.
            objs = _resolve_target_objects(context)
            bbox = _compute_world_bbox(objs)
            if bbox is not None:
                props.scale_ref_locked_position = _compute_anchor(
                    bbox[0], bbox[1], float(props.scale_ref_height),
                    _quad_aspect,
                )
            props.scale_ref_locked = True
        else:
            props.scale_ref_locked = False
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (UAL_OT_lock_scale_reference,)


def _scene_load_post_handler(_dummy):
    """When a .blend loads, re-honor whatever the scene says scale-ref should be."""
    try:
        enabled = bpy.context.scene.ual_props.scale_ref_enabled
    except (AttributeError, ReferenceError):
        enabled = False
    if enabled:
        _install_handler()
    else:
        _remove_handler()


def _scale_ref_state_sync():
    """Called from the property's update= callback (via library_panel) to
    install/remove the handler when scale_ref_enabled flips."""
    try:
        enabled = bpy.context.scene.ual_props.scale_ref_enabled
    except (AttributeError, ReferenceError):
        return
    if enabled:
        _install_handler()
    else:
        _remove_handler()


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_post.append(_scene_load_post_handler)


def unregister():
    _remove_handler()
    try:
        bpy.app.handlers.load_post.remove(_scene_load_post_handler)
    except ValueError:
        pass
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except (RuntimeError, ValueError):
            pass


__all__ = [
    'UAL_OT_lock_scale_reference',
    '_scale_ref_state_sync',
    'register',
    'unregister',
]
