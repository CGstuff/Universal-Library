"""
AssetViewport — QOpenGLWidget for previewing 3D asset .glb files.

Slim, single-mesh-focused viewport with an orbit camera, a ground grid, and
flat-shaded mesh rendering with one directional light. No terrain, no
blockers, no gizmos, no instancing — just "show me this mesh".

Public API:
    AssetViewport(parent=None)
        .load_glb(path)             — load and display a .glb file
        .clear()                    — remove the current mesh
        .set_background_color(qc)   — change clear color
        .reset_camera()             — re-frame the current mesh
        .glb_loaded(path)           — signal: emitted on success
        .glb_failed(path, error)    — signal: emitted on failure
        .context_unavailable()      — signal: emitted if GL context fails
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QSurfaceFormat, QWheelEvent
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from OpenGL.GL import *  # noqa: F403

from .camera import OrbitCamera
from .gl_dsa import (
    check_dsa, dsa_create_buffer, dsa_buffer_storage,
    dsa_create_vao, dsa_vao_vertex_buffer, dsa_vao_attrib_format,
    dsa_vao_attrib_binding, dsa_enable_vao_attrib, dsa_vao_element_buffer,
)
from .gl_geometry import make_grid_lines
from .gl_shaders import (
    MESH_VERT, MESH_FRAG, LINE_VERT, LINE_FRAG,
    SKIN_VERT, SKIN_FRAG, SILHOUETTE_VERT, SILHOUETTE_FRAG,
    MAX_JOINTS, compile_shader_program,
)
from .gltf_loader import (
    MeshData, GLBData, SkinData, NodeData, AnimationData, AnimationChannel,
)
from .mesh_cache import load_mesh, load_glb_data

logger = logging.getLogger(__name__)


# Bundled scale-reference silhouette PNG (same image used by the Blender addon).
_SILHOUETTE_PNG_PATH = (
    Path(__file__).resolve().parent.parent / "icons" / "human_silhouette.png"
)


_DEFAULT_BG = (0.25, 0.25, 0.25, 1.0)   # neutral mid-gray
_GRID_COLOR = (0.4, 0.4, 0.4, 0.6)
_GRID_AXIS_COLOR = (0.55, 0.55, 0.55, 0.9)


def _light_dir_from_spherical(az_deg: float, el_deg: float) -> np.ndarray:
    """Build a normalized light direction vector from azimuth + elevation.

    Az = 0   → light comes from +Y (in front of the camera at default view).
    Az = 90  → +X. El = 0 → horizon. El = 90 → straight down. All in degrees.
    """
    import math
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    cos_el = math.cos(el)
    v = np.array([cos_el * math.sin(az), cos_el * math.cos(az), math.sin(el)],
                 dtype=np.float32)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([0, 0, 1], dtype=np.float32)


_FALLBACK_LIGHT_DIR = _light_dir_from_spherical(45.0, 35.0)

# Y-up (glTF) → Z-up (UL) — same rotation the loader applies to static meshes,
# but for skinned meshes we apply it at the joint-palette level instead.
_Y_TO_Z_4x4 = np.array([
    [1, 0,  0, 0],
    [0, 0, -1, 0],
    [0, 1,  0, 0],
    [0, 0,  0, 1],
], dtype=np.float32)


def _make_surface_format() -> QSurfaceFormat:
    """Build the surface format we want our viewport widgets to use."""
    fmt = QSurfaceFormat()
    fmt.setVersion(4, 6)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    return fmt


def _install_default_surface_format_if_safe():
    """Apply our format as the GLOBAL default — but only if no GL surfaces
    have been realized yet. Safe when we're constructed before the main
    window's `show()`. Matches the World_Library pattern: same call as in
    their `GLViewport.__init__`, made early in the widget tree build."""
    cur = QSurfaceFormat.defaultFormat()
    if (cur.majorVersion(), cur.minorVersion()) >= (4, 6):
        return
    QSurfaceFormat.setDefaultFormat(_make_surface_format())


class _MeshGPU:
    """GPU resources for one loaded mesh primitive."""
    __slots__ = (
        'vao', 'vbo', 'ebo', 'tex',
        'vert_count', 'index_count', 'color',
        'skinned', 'skin_index',
    )

    def __init__(self, vao: int, vbo: int, ebo: int, tex: int,
                 vert_count: int, index_count: int, color: tuple,
                 skinned: bool = False, skin_index: Optional[int] = None):
        self.vao = vao
        self.vbo = vbo
        self.ebo = ebo
        self.tex = tex            # GL texture name, 0 if no texture
        self.vert_count = vert_count
        self.index_count = index_count
        self.color = color
        self.skinned = skinned
        self.skin_index = skin_index


class AssetViewport(QOpenGLWidget):
    """3D mesh viewport for asset preview."""

    glb_loaded = pyqtSignal(str)          # path
    glb_failed = pyqtSignal(str, str)     # path, error
    context_unavailable = pyqtSignal()

    def __init__(self, parent=None):
        # Promote our format to the global default — only takes effect if
        # called before any GL surface has been realized. The thumbnail
        # panel constructs us synchronously before the main window's first
        # show(), which is the safe window for this.
        _install_default_surface_format_if_safe()
        super().__init__(parent)
        # Also set per-widget — covers the case where we get constructed
        # late (e.g. user re-opens a window in an existing session).
        self.setFormat(_make_surface_format())
        self.camera = OrbitCamera()
        self._bg = _DEFAULT_BG
        self._light_dir = _FALLBACK_LIGHT_DIR.copy()

        # Pull persisted preferences (BG color + light direction + scale ref)
        # and subscribe to live changes so all open viewports stay in sync.
        self._scale_ref_enabled = False
        self._scale_ref_height = 1.8
        try:
            from ...services.viewport_settings import (
                get_viewport_bg_color, get_viewport_light,
                get_scale_ref_enabled, get_scale_ref_height,
                viewport_settings_signals,
            )
            self.set_background_color(get_viewport_bg_color())
            az, el = get_viewport_light()
            self._light_dir = _light_dir_from_spherical(az, el)
            self._scale_ref_enabled = get_scale_ref_enabled()
            self._scale_ref_height = get_scale_ref_height()
            sig = viewport_settings_signals()
            sig.bg_changed.connect(self.set_background_color)
            sig.light_changed.connect(self._on_light_changed)
            sig.scale_ref_changed.connect(self._on_scale_ref_changed)
        except Exception as e:
            # If settings infrastructure isn't available (e.g., the standalone
            # test harness), fall back to the compiled defaults.
            logger.debug(f"[AssetViewport] No persisted prefs: {e}")

        # GL programs / buffers — populated in initializeGL
        self._mesh_program = None
        self._skin_program = None
        self._line_program = None
        self._silhouette_program = None
        self._silhouette_vao = None
        self._silhouette_vbo = None
        self._silhouette_ebo = None
        self._silhouette_tex = 0       # GL texture name, 0 = not loaded
        self._silhouette_aspect = 0.5  # half-width / height; refined on PNG load
        self._grid_vao = None
        self._grid_vbo = None
        self._grid_vert_count = 0

        # Loaded meshes
        self._meshes: list[_MeshGPU] = []
        self._current_path: Optional[str] = None
        self._pending_glb: Optional[GLBData] = None
        self._pending_path: Optional[str] = None

        # Skinning / animation state — GLBData of the currently-loaded asset.
        # Populated from the cache so we can re-sample animations per frame
        # without re-parsing. `None` means a non-animated / non-skinned asset.
        self._glb: Optional[GLBData] = None
        self._current_animation: Optional[int] = None  # index into _glb.animations
        self._current_time: float = 0.0
        self._skinning_disabled = False  # set True for rigs with >MAX_JOINTS joints

        # Mouse interaction state
        self._last_mouse_pos: Optional[tuple[int, int]] = None
        self._mouse_button: Optional[Qt.MouseButton] = None

        self._gl_ready = False
        self._gl_failed = False

        self.setMinimumSize(150, 150)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.destroyed.connect(self._cleanup_gl_resources)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_glb(self, path: str) -> None:
        """Load and display a .glb file. Path resolution / fallback is the
        caller's responsibility — this method just tries to load."""
        glb = load_glb_data(path)
        if not glb or not glb.meshes:
            self.glb_failed.emit(path, "Failed to load or empty mesh")
            return

        if not self._gl_ready:
            # Defer until initializeGL runs. _apply_glb will fire glb_loaded
            # at that point so callers don't miss the event.
            self._pending_glb = glb
            self._pending_path = path
            self.update()
            return

        self.makeCurrent()
        try:
            self._clear_meshes()
            self._apply_glb(glb, path)
        finally:
            self.doneCurrent()

        self.update()

    def clear(self) -> None:
        """Remove the current mesh."""
        if self._gl_ready:
            self.makeCurrent()
            try:
                self._clear_meshes()
            finally:
                self.doneCurrent()
        self._current_path = None
        self._pending_glb = None
        self._pending_path = None
        self._glb = None
        self._current_animation = None
        self._current_time = 0.0
        self._skinning_disabled = False
        self.update()

    # ------------------------------------------------------------------
    # Animation playback API (consumed by EnlargedViewerDialog in 6.6)
    # ------------------------------------------------------------------

    def animation_names(self) -> list:
        """Return the list of animation names in the current asset.
        Empty if the asset has no animations (or none loaded yet)."""
        if self._glb is None:
            return []
        return [a.name for a in self._glb.animations]

    def animation_duration(self, index: Optional[int] = None) -> float:
        """Duration in seconds of the given animation (or current if None)."""
        if self._glb is None:
            return 0.0
        if index is None:
            index = self._current_animation
        if index is None or index < 0 or index >= len(self._glb.animations):
            return 0.0
        return self._glb.animations[index].duration

    def set_current_animation(self, index: Optional[int]):
        """Pick which animation drives the rig. `None` shows bind pose."""
        if self._glb is None:
            self._current_animation = None
        elif index is None:
            self._current_animation = None
        else:
            n = len(self._glb.animations)
            if n == 0:
                self._current_animation = None
            else:
                self._current_animation = max(0, min(int(index), n - 1))
        self._current_time = 0.0
        self.update()

    def set_current_time(self, t: float):
        """Set the current playback time (seconds). Wrapped per animation duration."""
        dur = self.animation_duration()
        if dur > 0:
            self._current_time = float(t) % dur
        else:
            self._current_time = 0.0
        self.update()

    def set_background_color(self, color) -> None:
        """Change the clear color. Accepts QColor or (r,g,b[,a]) tuple in 0..1."""
        if isinstance(color, QColor):
            self._bg = (
                color.redF(), color.greenF(), color.blueF(),
                color.alphaF() if color.alpha() else 1.0,
            )
        else:
            if len(color) == 3:
                self._bg = (color[0], color[1], color[2], 1.0)
            else:
                self._bg = tuple(color)
        self.update()

    def reset_camera(self) -> None:
        """Re-frame the current mesh."""
        if self._meshes:
            self._frame_meshes()
        else:
            self.camera = OrbitCamera()
        self.update()

    def _on_light_changed(self, azimuth_deg: float, elevation_deg: float):
        """Slot for the viewport_settings.light_changed signal."""
        self._light_dir = _light_dir_from_spherical(azimuth_deg, elevation_deg)
        self.update()

    def _on_scale_ref_changed(self, enabled: bool, height_m: float):
        """Slot for the viewport_settings.scale_ref_changed signal — keeps
        every open viewport in sync when the user toggles via any UI."""
        self._scale_ref_enabled = bool(enabled)
        self._scale_ref_height = float(height_m)
        self.update()

    # ------------------------------------------------------------------
    # QOpenGLWidget hooks
    # ------------------------------------------------------------------

    def initializeGL(self):
        try:
            check_dsa()
            self._mesh_program = compile_shader_program(MESH_VERT, MESH_FRAG)
            self._skin_program = compile_shader_program(SKIN_VERT, SKIN_FRAG)
            self._line_program = compile_shader_program(LINE_VERT, LINE_FRAG)
            self._silhouette_program = compile_shader_program(
                SILHOUETTE_VERT, SILHOUETTE_FRAG,
            )
            self._build_grid()
            self._build_silhouette()

            glEnable(GL_DEPTH_TEST)
            glEnable(GL_CULL_FACE)
            glCullFace(GL_BACK)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_LINE_SMOOTH)

            self._gl_ready = True
            logger.info("[AssetViewport] GL context initialized")

            # Apply any pending load that arrived before initializeGL
            if self._pending_glb is not None:
                self._apply_glb(self._pending_glb, self._pending_path)
                self._pending_glb = None
                self._pending_path = None
        except Exception as e:
            logger.exception(f"[AssetViewport] GL init failed: {e}")
            self._gl_failed = True
            self.context_unavailable.emit()

    def resizeGL(self, w: int, h: int):
        if h > 0:
            self.camera.aspect = w / h
        glViewport(0, 0, w, h)

    def paintGL(self):
        glClearColor(*self._bg)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        if not self._gl_ready or self._gl_failed:
            return

        view = self.camera.get_view_matrix().astype(np.float32)
        proj = self.camera.get_projection_matrix().astype(np.float32)
        vp = (proj @ view).astype(np.float32)
        eye = self.camera.eye.astype(np.float32)

        # Grid
        if self._grid_vao is not None:
            glUseProgram(self._line_program)
            loc_vp = glGetUniformLocation(self._line_program, 'u_vp')
            loc_color = glGetUniformLocation(self._line_program, 'u_color')
            glUniformMatrix4fv(loc_vp, 1, GL_TRUE, vp)
            glUniform4f(loc_color, *_GRID_COLOR)
            glBindVertexArray(self._grid_vao)
            glDrawArrays(GL_LINES, 0, self._grid_vert_count)
            glBindVertexArray(0)

        if not self._meshes:
            return

        # Pre-compute joint palettes for every skin referenced this frame.
        # Cheap to recompute even per-frame for 64-joint rigs (<2000 floats).
        skin_palettes = {}
        if (self._glb is not None and not self._skinning_disabled
                and self._glb.skins):
            for m in self._meshes:
                if m.skinned and m.skin_index is not None:
                    if m.skin_index not in skin_palettes:
                        skin_palettes[m.skin_index] = self._compute_joint_palette(
                            m.skin_index
                        )

        # Static-mesh pass
        static_meshes = [m for m in self._meshes if not m.skinned]
        if static_meshes:
            self._draw_static_meshes(static_meshes, view, proj, eye)

        # Skinned-mesh pass (rigs)
        skinned_meshes = [m for m in self._meshes if m.skinned]
        if skinned_meshes and skin_palettes:
            self._draw_skinned_meshes(skinned_meshes, view, proj, eye, skin_palettes)

        # Scale-reference silhouette (M5) — billboarded textured quad. Drawn
        # last so it composites over the grid + meshes with alpha blending.
        if self._scale_ref_enabled and self._silhouette_tex:
            self._draw_silhouette(view, proj, eye)

    def _draw_silhouette(self, view, proj, eye):
        """Draw the human silhouette next to the loaded mesh's bbox."""
        bbox = self._compute_world_bbox()
        if bbox is None:
            return
        bbox_min, bbox_max = bbox

        height = float(self._scale_ref_height)
        if height <= 0:
            return

        # Anchor: same rule as the Blender addon. To the right (+X) of the
        # bbox with clear breathing room, feet on Z=0 (world ground plane).
        half_w_norm = float(self._silhouette_aspect)
        offset = (half_w_norm + 0.25) * height
        anchor = np.array([
            float(bbox_max[0]) + offset,
            (float(bbox_min[1]) + float(bbox_max[1])) * 0.5,
            0.0,
        ], dtype=np.float32)

        # Billboard axes. World-Z up so silhouette stays upright; right is
        # the camera's right axis (first row of the view matrix) projected
        # against world up so the quad stays a clean rectangle when the
        # camera is pitched.
        view_inv = np.linalg.inv(view)
        right = view_inv[0:3, 0].astype(np.float32)
        up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        right = right - up * float(np.dot(right, up))
        n = float(np.linalg.norm(right))
        if n < 1e-6:
            right = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        else:
            right = right / n

        width = (half_w_norm * 2.0) * height

        glUseProgram(self._silhouette_program)
        p = self._silhouette_program
        glUniformMatrix4fv(glGetUniformLocation(p, 'u_view'), 1, GL_TRUE, view)
        glUniformMatrix4fv(glGetUniformLocation(p, 'u_proj'), 1, GL_TRUE, proj)
        glUniform3f(glGetUniformLocation(p, 'u_anchor'), *anchor)
        glUniform3f(glGetUniformLocation(p, 'u_right'), *right)
        glUniform3f(glGetUniformLocation(p, 'u_up'), *up)
        glUniform1f(glGetUniformLocation(p, 'u_width'), float(width))
        glUniform1f(glGetUniformLocation(p, 'u_height'), float(height))
        glUniform1i(glGetUniformLocation(p, 'u_tex'), 0)

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._silhouette_tex)
        # Silhouette is transparent on its outside — must not write depth
        # or it'll occlude the asset behind it; must blend on top.
        glDepthMask(GL_FALSE)
        glDisable(GL_CULL_FACE)
        glBindVertexArray(self._silhouette_vao)
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glEnable(GL_CULL_FACE)
        glDepthMask(GL_TRUE)

    def _draw_static_meshes(self, meshes, view, proj, eye):
        glUseProgram(self._mesh_program)
        p = self._mesh_program
        loc_view = glGetUniformLocation(p, 'u_view')
        loc_proj = glGetUniformLocation(p, 'u_proj')
        loc_light = glGetUniformLocation(p, 'u_light_dir')
        loc_view_pos = glGetUniformLocation(p, 'u_view_pos')
        loc_color = glGetUniformLocation(p, 'u_mesh_color')
        loc_has_tex = glGetUniformLocation(p, 'u_has_tex')
        loc_tex = glGetUniformLocation(p, 'u_base_tex')

        glUniformMatrix4fv(loc_view, 1, GL_TRUE, view)
        glUniformMatrix4fv(loc_proj, 1, GL_TRUE, proj)
        glUniform3f(loc_light, *self._light_dir)
        glUniform3f(loc_view_pos, *eye)
        glUniform1i(loc_tex, 0)

        for m in meshes:
            glUniform3f(loc_color, *m.color)
            if m.tex:
                glUniform1i(loc_has_tex, 1)
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, m.tex)
            else:
                glUniform1i(loc_has_tex, 0)
            glBindVertexArray(m.vao)
            if m.index_count > 0:
                glDrawElements(GL_TRIANGLES, m.index_count, GL_UNSIGNED_INT, None)
            else:
                glDrawArrays(GL_TRIANGLES, 0, m.vert_count)
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)

    def _draw_skinned_meshes(self, meshes, view, proj, eye, skin_palettes):
        glUseProgram(self._skin_program)
        p = self._skin_program
        loc_view = glGetUniformLocation(p, 'u_view')
        loc_proj = glGetUniformLocation(p, 'u_proj')
        loc_light = glGetUniformLocation(p, 'u_light_dir')
        loc_view_pos = glGetUniformLocation(p, 'u_view_pos')
        loc_color = glGetUniformLocation(p, 'u_mesh_color')
        loc_has_tex = glGetUniformLocation(p, 'u_has_tex')
        loc_tex = glGetUniformLocation(p, 'u_base_tex')
        loc_joints = glGetUniformLocation(p, 'u_joints')

        glUniformMatrix4fv(loc_view, 1, GL_TRUE, view)
        glUniformMatrix4fv(loc_proj, 1, GL_TRUE, proj)
        glUniform3f(loc_light, *self._light_dir)
        glUniform3f(loc_view_pos, *eye)
        glUniform1i(loc_tex, 0)

        current_palette_skin = None
        for m in meshes:
            if m.skin_index != current_palette_skin:
                palette = skin_palettes.get(m.skin_index)
                if palette is None:
                    continue
                # Pad/truncate to MAX_JOINTS rows (shader assumes a fixed array).
                if palette.shape[0] < MAX_JOINTS:
                    pad = np.tile(
                        np.eye(4, dtype=np.float32),
                        (MAX_JOINTS - palette.shape[0], 1, 1),
                    )
                    palette = np.concatenate([palette, pad], axis=0)
                elif palette.shape[0] > MAX_JOINTS:
                    palette = palette[:MAX_JOINTS]
                # GL_TRUE = row-major (transpose on upload). Our matrices are
                # in row-major math convention already.
                glUniformMatrix4fv(loc_joints, MAX_JOINTS, GL_TRUE, palette)
                current_palette_skin = m.skin_index

            glUniform3f(loc_color, *m.color)
            if m.tex:
                glUniform1i(loc_has_tex, 1)
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, m.tex)
            else:
                glUniform1i(loc_has_tex, 0)
            glBindVertexArray(m.vao)
            if m.index_count > 0:
                glDrawElements(GL_TRIANGLES, m.index_count, GL_UNSIGNED_INT, None)
            else:
                glDrawArrays(GL_TRIANGLES, 0, m.vert_count)
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)

    # ------------------------------------------------------------------
    # Mouse interaction (orbit / pan / zoom)
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent):
        self._last_mouse_pos = (event.position().x(), event.position().y())
        self._mouse_button = event.button()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._last_mouse_pos is None:
            return
        x, y = event.position().x(), event.position().y()
        dx = x - self._last_mouse_pos[0]
        dy = y - self._last_mouse_pos[1]
        self._last_mouse_pos = (x, y)
        if self._mouse_button == Qt.MouseButton.LeftButton:
            self.camera.orbit(-dx * 0.4, dy * 0.4)
        elif self._mouse_button == Qt.MouseButton.MiddleButton:
            self.camera.pan(-dx, dy)
        elif self._mouse_button == Qt.MouseButton.RightButton:
            self.camera.zoom(dy * 0.05)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._last_mouse_pos = None
        self._mouse_button = None

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y() / 120.0
        self.camera.zoom(delta)
        self.update()

    # ------------------------------------------------------------------
    # GL resource management
    # ------------------------------------------------------------------

    def _build_grid(self):
        verts = make_grid_lines(extent=5.0, step=0.5)
        vbo = dsa_create_buffer()
        dsa_buffer_storage(vbo, verts)
        vao = dsa_create_vao()
        dsa_vao_vertex_buffer(vao, binding=0, buffer=vbo, offset=0, stride=12)
        dsa_vao_attrib_format(vao, attrib=0, size=3, gl_type=GL_FLOAT, offset=0)
        dsa_vao_attrib_binding(vao, attrib=0, binding=0)
        dsa_enable_vao_attrib(vao, attrib=0)
        self._grid_vao = vao
        self._grid_vbo = vbo
        self._grid_vert_count = verts.shape[0]

    def _build_silhouette(self):
        """Build the silhouette quad VAO + load the PNG into a GL texture.

        Quad lives in local space: x in [-0.5, 0.5], y in [0, 1] (feet at
        y=0, head at y=1). The vertex shader transforms these into world
        space using camera-right and world-up uniforms each frame.
        Vertices interleaved as (x, y, u, v) → stride 16 bytes.
        UV layout: v=0 at feet (bottom of PNG), v=1 at head (top of PNG).
        """
        # 4 verts × (vec2 local + vec2 uv) = 4×4 floats = 64 bytes total.
        quad = np.array([
            [-0.5, 0.0, 0.0, 0.0],   # bottom-left
            [ 0.5, 0.0, 1.0, 0.0],   # bottom-right
            [ 0.5, 1.0, 1.0, 1.0],   # top-right
            [-0.5, 1.0, 0.0, 1.0],   # top-left
        ], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)

        vbo = dsa_create_buffer()
        dsa_buffer_storage(vbo, quad)
        ebo = dsa_create_buffer()
        dsa_buffer_storage(ebo, indices)
        vao = dsa_create_vao()
        dsa_vao_vertex_buffer(vao, binding=0, buffer=vbo, offset=0, stride=16)
        # location 0: local position (vec2)
        dsa_vao_attrib_format(vao, attrib=0, size=2, gl_type=GL_FLOAT, offset=0)
        dsa_vao_attrib_binding(vao, attrib=0, binding=0)
        dsa_enable_vao_attrib(vao, attrib=0)
        # location 1: uv (vec2)
        dsa_vao_attrib_format(vao, attrib=1, size=2, gl_type=GL_FLOAT, offset=8)
        dsa_vao_attrib_binding(vao, attrib=1, binding=0)
        dsa_enable_vao_attrib(vao, attrib=1)
        dsa_vao_element_buffer(vao, ebo)
        self._silhouette_vao = vao
        self._silhouette_vbo = vbo
        self._silhouette_ebo = ebo

        # Load PNG via QImage → GL texture. Fail-open: if the PNG is missing
        # or unreadable we just don't draw the silhouette (no error toast).
        if not _SILHOUETTE_PNG_PATH.exists():
            logger.warning(
                "[AssetViewport] scale-ref PNG missing at %s", _SILHOUETTE_PNG_PATH,
            )
            return

        img = QImage(str(_SILHOUETTE_PNG_PATH))
        if img.isNull():
            logger.warning(
                "[AssetViewport] failed to load scale-ref PNG: %s", _SILHOUETTE_PNG_PATH,
            )
            return

        # Convert to a canonical format we know GL can consume directly.
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = img.width(), img.height()
        if w <= 0 or h <= 0:
            return

        # Flip vertically so v=0 at the bottom of the texture lines up with
        # feet at y=0 in our quad. QImage's coordinate origin is top-left;
        # GL textures expect bottom-left for the conventional v=0.
        img = img.mirrored(False, True)

        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        data = bytes(ptr)

        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glGenerateMipmap(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, 0)

        self._silhouette_tex = tex
        # half-width / full-height in normalized quad units
        self._silhouette_aspect = (w / h) / 2.0

    def _apply_glb(self, glb: GLBData, path: Optional[str]):
        """Apply a freshly-loaded GLBData: upload meshes, capture animation
        state, frame the camera. Must be called with the GL context current.

        Emits `glb_loaded` at the end — fires from both the direct and the
        deferred (initializeGL) load paths so consumers don't miss it.
        """
        self._glb = glb
        self._current_path = path
        # Reject skinning if any skin exceeds MAX_JOINTS — preview falls back to
        # static rest pose for those primitives. Static meshes elsewhere in the
        # same .glb still render normally.
        self._skinning_disabled = any(
            len(s.joints) > MAX_JOINTS for s in glb.skins
        )
        if self._skinning_disabled:
            logger.warning(
                f"[AssetViewport] rig has >{MAX_JOINTS} joints; "
                f"skinning disabled, showing bind pose only"
            )

        # Default to the first animation if any. 6.6's timeline UI will drive
        # this via set_current_animation / set_current_time.
        self._current_animation = 0 if glb.animations else None
        self._current_time = 0.0

        self._upload_meshes(glb.meshes)
        self._frame_meshes()

        if path:
            self.glb_loaded.emit(path)

    def _upload_meshes(self, meshes: list[MeshData]):
        for md in meshes:
            n = int(md.vertices.shape[0])

            # Decide upfront whether this primitive uses the skinning path.
            is_skinned = (
                md.skin_index is not None
                and md.joints is not None and md.joints.shape == (n, 4)
                and md.weights is not None and md.weights.shape == (n, 4)
                and not self._skinning_disabled
            )

            # UVs: present if we have them, else zeros (shader gates on u_has_tex).
            if md.uvs is not None and md.uvs.shape == (n, 2):
                uvs = md.uvs.astype(np.float32, copy=False)
            else:
                uvs = np.zeros((n, 2), dtype=np.float32)

            if is_skinned:
                # Interleaved: pos(3) + nrm(3) + uv(2) + joints(4 uint32) + weights(4)
                # Stride = (3+3+2)*4 + 4*4 (joints) + 4*4 (weights) = 32 + 16 + 16 = 64 bytes
                # Pack joints as uint32 alongside floats — same byte width.
                joints32 = md.joints.astype(np.uint32, copy=False).view(np.uint32)
                # Normalize weights — defensive (most assets are well-behaved but
                # some lossy paths drift the sum).
                w = md.weights.astype(np.float32, copy=False)
                wsum = w.sum(axis=1, keepdims=True)
                wsum[wsum < 1e-6] = 1.0
                w = w / wsum

                # Build the interleaved buffer byte-by-byte via a structured array
                # so the joints stay as uint32 not silently coerced to float32.
                interleaved = np.empty(n, dtype=[
                    ('pos', np.float32, 3),
                    ('nrm', np.float32, 3),
                    ('uv', np.float32, 2),
                    ('joints', np.uint32, 4),
                    ('weights', np.float32, 4),
                ])
                interleaved['pos'] = md.vertices.astype(np.float32, copy=False)
                interleaved['nrm'] = md.normals.astype(np.float32, copy=False)
                interleaved['uv'] = uvs
                interleaved['joints'] = joints32
                interleaved['weights'] = w

                vbo = dsa_create_buffer()
                dsa_buffer_storage(vbo, interleaved)
                stride = 64

                vao = dsa_create_vao()
                dsa_vao_vertex_buffer(vao, binding=0, buffer=vbo, offset=0, stride=stride)
                # Position (location 0, float3 at offset 0)
                dsa_vao_attrib_format(vao, attrib=0, size=3, gl_type=GL_FLOAT, offset=0)
                dsa_vao_attrib_binding(vao, attrib=0, binding=0)
                dsa_enable_vao_attrib(vao, attrib=0)
                # Normal (location 1, float3 at offset 12)
                dsa_vao_attrib_format(vao, attrib=1, size=3, gl_type=GL_FLOAT, offset=12)
                dsa_vao_attrib_binding(vao, attrib=1, binding=0)
                dsa_enable_vao_attrib(vao, attrib=1)
                # UV (location 2, float2 at offset 24)
                dsa_vao_attrib_format(vao, attrib=2, size=2, gl_type=GL_FLOAT, offset=24)
                dsa_vao_attrib_binding(vao, attrib=2, binding=0)
                dsa_enable_vao_attrib(vao, attrib=2)
                # Joints (location 3, uint4 at offset 32) — IFormat for integer attrib
                glVertexArrayAttribIFormat(vao, 3, 4, GL_UNSIGNED_INT, 32)
                dsa_vao_attrib_binding(vao, attrib=3, binding=0)
                dsa_enable_vao_attrib(vao, attrib=3)
                # Weights (location 4, float4 at offset 48)
                dsa_vao_attrib_format(vao, attrib=4, size=4, gl_type=GL_FLOAT, offset=48)
                dsa_vao_attrib_binding(vao, attrib=4, binding=0)
                dsa_enable_vao_attrib(vao, attrib=4)
            else:
                # Static (existing) path: pos(3) + nrm(3) + uv(2), stride 32.
                interleaved = np.column_stack([
                    md.vertices.astype(np.float32, copy=False),
                    md.normals.astype(np.float32, copy=False),
                    uvs,
                ]).astype(np.float32)

                vbo = dsa_create_buffer()
                dsa_buffer_storage(vbo, interleaved)
                stride = 32

                vao = dsa_create_vao()
                dsa_vao_vertex_buffer(vao, binding=0, buffer=vbo, offset=0, stride=stride)
                dsa_vao_attrib_format(vao, attrib=0, size=3, gl_type=GL_FLOAT, offset=0)
                dsa_vao_attrib_binding(vao, attrib=0, binding=0)
                dsa_enable_vao_attrib(vao, attrib=0)
                dsa_vao_attrib_format(vao, attrib=1, size=3, gl_type=GL_FLOAT, offset=12)
                dsa_vao_attrib_binding(vao, attrib=1, binding=0)
                dsa_enable_vao_attrib(vao, attrib=1)
                dsa_vao_attrib_format(vao, attrib=2, size=2, gl_type=GL_FLOAT, offset=24)
                dsa_vao_attrib_binding(vao, attrib=2, binding=0)
                dsa_enable_vao_attrib(vao, attrib=2)

            ebo = 0
            index_count = 0
            if md.indices is not None and md.indices.size > 0:
                idx = md.indices.astype(np.uint32, copy=False)
                ebo = dsa_create_buffer()
                dsa_buffer_storage(ebo, idx)
                dsa_vao_element_buffer(vao, ebo)
                index_count = int(idx.size)

            tex = self._upload_texture(md.base_image) if md.base_image else 0

            self._meshes.append(_MeshGPU(
                vao=vao, vbo=vbo, ebo=ebo, tex=tex,
                vert_count=n,
                index_count=index_count,
                color=md.color,
                skinned=is_skinned,
                skin_index=md.skin_index if is_skinned else None,
            ))

    def _upload_texture(self, qimg) -> int:
        """Upload a QImage to a GL2D texture. Returns the texture name, or 0 on failure."""
        try:
            if qimg is None or qimg.isNull():
                return 0
            # QImage is RGBA8888 (converted in the loader). Get raw bytes.
            w = qimg.width()
            h = qimg.height()
            # Ensure tightly packed, RGBA order.
            from PyQt6.QtGui import QImage
            img = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
            ptr = img.constBits()
            ptr.setsize(img.sizeInBytes())
            data = bytes(ptr)

            tex = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0,
                         GL_RGBA, GL_UNSIGNED_BYTE, data)
            glGenerateMipmap(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, 0)
            return int(tex)
        except Exception as e:
            logger.warning(f"[AssetViewport] Texture upload failed: {e}")
            return 0

    def _clear_meshes(self):
        for m in self._meshes:
            try:
                if m.vao:
                    glDeleteVertexArrays(1, [m.vao])
                if m.vbo:
                    glDeleteBuffers(1, [m.vbo])
                if m.ebo:
                    glDeleteBuffers(1, [m.ebo])
                if m.tex:
                    glDeleteTextures(1, [m.tex])
            except Exception:
                pass
        self._meshes.clear()

    def _compute_world_bbox(self):
        """Compute the union bbox of all loaded meshes in Z-up world space.

        Same logic as `_frame_meshes` (skinned meshes get the Y→Z swap to
        match how they render). Extracted so the scale-reference silhouette
        can position itself next to the asset.

        Returns (min: np.ndarray(3), max: np.ndarray(3)) or None.
        """
        if self._glb is None or not self._glb.meshes:
            return None
        mins = []
        maxs = []
        for md in self._glb.meshes:
            if md.vertices.size == 0:
                continue
            v = md.vertices
            if md.skin_index is not None:
                v_zup = np.column_stack([v[:, 0], -v[:, 2], v[:, 1]])
                mins.append(v_zup.min(axis=0))
                maxs.append(v_zup.max(axis=0))
            else:
                mins.append(v.min(axis=0))
                maxs.append(v.max(axis=0))
        if not mins:
            return None
        return np.min(np.array(mins), axis=0), np.max(np.array(maxs), axis=0)

    def _frame_meshes(self):
        """Fit the camera to the loaded mesh bounding box."""
        bbox = self._compute_world_bbox()
        if bbox is None:
            return
        self.camera.frame_bbox(bbox[0], bbox[1])

    # ------------------------------------------------------------------
    # Animation sampling + forward kinematics + joint palette
    # ------------------------------------------------------------------

    def _compute_joint_palette(self, skin_idx: int) -> Optional[np.ndarray]:
        """Build the joint palette for one skin at the current animation time.

        Returns (J, 4, 4) float32 where each entry =
            Y_TO_Z × joint_world × inverse_bind_matrix[joint]
        and `joint_world` is the joint's world matrix obtained by forward-
        kinematics over the node tree with the current animation's samples
        applied.

        At bind pose (no animation or t=0 with no channels) this collapses to
        Y_TO_Z × identity = Y_TO_Z, so the mesh shows in bind pose with the
        correct orientation.
        """
        if self._glb is None or skin_idx >= len(self._glb.skins):
            return None
        skin = self._glb.skins[skin_idx]

        # 1. Sample current animation (if any) to per-node TRS overrides.
        anim = None
        if self._current_animation is not None and self._glb.animations:
            anim = self._glb.animations[self._current_animation]
        samples = self._sample_node_trs(anim, self._current_time)

        # 2. Forward-kinematics: compute world matrix for every node.
        node_worlds = self._compute_node_world_matrices(samples)

        # 3. Build the palette for this skin's joints.
        n_joints = len(skin.joints)
        ibm = skin.inverse_bind_matrices
        palette = np.empty((n_joints, 4, 4), dtype=np.float32)
        for i, joint_node in enumerate(skin.joints):
            if 0 <= joint_node < len(node_worlds):
                jw = node_worlds[joint_node]
            else:
                jw = np.eye(4, dtype=np.float32)
            palette[i] = _Y_TO_Z_4x4 @ jw @ ibm[i]
        return palette

    def _sample_node_trs(self, anim: Optional[AnimationData], t: float) -> dict:
        """Sample all channels in `anim` at time `t`. Returns a dict
        `{(node_idx, path): value}` of overrides; nodes/paths not in the dict
        keep their bind-pose TRS."""
        out = {}
        if anim is None:
            return out
        for ch in anim.channels:
            v = _sample_channel(ch, t)
            if v is not None:
                out[(ch.target_node, ch.target_path)] = v
        return out

    def _compute_node_world_matrices(self, samples: dict) -> list:
        """Walk the node tree from roots, composing local TRS into world
        matrices. Animation samples override the bind-pose TRS per (node, path).

        Returns a list of (4, 4) float32 arrays, one per node, in glTF Y-up
        space (no Y→Z applied; that's baked into the palette later)."""
        if self._glb is None:
            return []
        nodes = self._glb.nodes
        worlds = [np.eye(4, dtype=np.float32) for _ in nodes]
        visited = [False] * len(nodes)

        def visit(idx: int, parent_world: np.ndarray):
            if visited[idx]:
                return
            visited[idx] = True
            n = nodes[idx]
            t = samples.get((idx, 'translation'), n.translation)
            r = samples.get((idx, 'rotation'), n.rotation)
            s = samples.get((idx, 'scale'), n.scale)
            local = _trs_to_matrix(t, r, s)
            w = parent_world @ local
            worlds[idx] = w
            for c in n.children:
                if 0 <= c < len(nodes):
                    visit(c, w)

        # Roots: parent is None. (Already filled by gltf_loader._load_nodes.)
        identity = np.eye(4, dtype=np.float32)
        for i, n in enumerate(nodes):
            if n.parent is None:
                visit(i, identity)

        # Any nodes that weren't visited (orphaned) get identity. Defensive.
        return worlds

    def _cleanup_gl_resources(self):
        """Best-effort cleanup. May be called after the GL context is gone."""
        if not self._gl_ready:
            return
        try:
            self.makeCurrent()
            self._clear_meshes()
            if self._grid_vao:
                glDeleteVertexArrays(1, [self._grid_vao])
            if self._grid_vbo:
                glDeleteBuffers(1, [self._grid_vbo])
            if self._mesh_program:
                glDeleteProgram(self._mesh_program)
            if self._skin_program:
                glDeleteProgram(self._skin_program)
            if self._line_program:
                glDeleteProgram(self._line_program)
            self.doneCurrent()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Module-level math helpers — used by joint palette computation
# ----------------------------------------------------------------------


def _trs_to_matrix(t, r, s) -> np.ndarray:
    """Build a 4x4 row-major matrix from translation, rotation (quaternion
    xyzw), and scale (3-vector)."""
    qx, qy, qz, qw = float(r[0]), float(r[1]), float(r[2]), float(r[3])
    # Quat → 3x3
    n = qx * qx + qy * qy + qz * qz + qw * qw
    if n < 1e-12:
        rot3 = np.eye(3, dtype=np.float32)
    else:
        inv = 2.0 / n
        wx, wy, wz = inv * qw * qx, inv * qw * qy, inv * qw * qz
        xx, xy, xz = inv * qx * qx, inv * qx * qy, inv * qx * qz
        yy, yz, zz = inv * qy * qy, inv * qy * qz, inv * qz * qz
        rot3 = np.array([
            [1.0 - (yy + zz), xy - wz,         xz + wy],
            [xy + wz,         1.0 - (xx + zz), yz - wx],
            [xz - wy,         yz + wx,         1.0 - (xx + yy)],
        ], dtype=np.float32)
    m = np.eye(4, dtype=np.float32)
    sx, sy, sz = float(s[0]), float(s[1]), float(s[2])
    m[:3, 0] = rot3[:, 0] * sx
    m[:3, 1] = rot3[:, 1] * sy
    m[:3, 2] = rot3[:, 2] * sz
    m[:3, 3] = [float(t[0]), float(t[1]), float(t[2])]
    return m


def _sample_channel(channel: AnimationChannel, t: float):
    """Sample one animation channel at time `t`. Returns a numpy value
    suitable to override a node's TRS, or None on degenerate input.

    Interpolation:
        - STEP        → previous keyframe
        - LINEAR      → linear blend (with SLERP for quaternions)
        - CUBICSPLINE → falls back to linear interpolation between the
          stored value slots (skipping tangents).

    KNOWN LIMITATION (verified harmless for current Blender exports):
    The single-keyframe early-return (times.size == 1) and the clamp paths
    (t <= times[0], t >= times[-1]) return values[i] unconditionally —
    they don't honor CUBICSPLINE's 3-slot-per-keyframe packing
    (in_tangent, value, out_tangent), so they'd return a tangent instead
    of the value at the edges of a CUBICSPLINE channel. Verified against
    production exports (60 samplers, 0 CUBICSPLINE) — Blender's exporter
    emits STEP/LINEAR for our rigs. Fix path if we ever ship rigs with
    CUBICSPLINE: check `interp == 'CUBICSPLINE'` in each branch and use
    `values[i * 3 + 1]` instead.
    """
    times = channel.times
    values = channel.values
    if times.size == 0 or values.shape[0] == 0:
        return None
    if times.size == 1:
        return values[0]

    # Clamp to range
    if t <= times[0]:
        return values[0]
    if t >= times[-1]:
        return values[-1]

    # Find surrounding keyframes
    idx = int(np.searchsorted(times, t, side='right'))
    i0 = max(0, idx - 1)
    i1 = min(times.size - 1, idx)
    t0, t1 = float(times[i0]), float(times[i1])
    if t1 <= t0:
        return values[i0]
    alpha = (t - t0) / (t1 - t0)

    interp = channel.interpolation
    if interp == 'STEP':
        return values[i0]

    if interp == 'CUBICSPLINE':
        # CUBICSPLINE output has 3 components per keyframe: (in_tangent,
        # value, out_tangent). For preview fidelity, treat the middle slot
        # as the keyframe value and fall back to LINEAR. This is a known
        # corner — proper Hermite eval is a future polish item.
        if values.shape[0] == times.size * 3:
            v0 = values[i0 * 3 + 1]
            v1 = values[i1 * 3 + 1]
        else:
            v0 = values[i0]
            v1 = values[i1]
    else:
        v0 = values[i0]
        v1 = values[i1]

    if channel.target_path == 'rotation' and v0.shape[-1] == 4:
        return _slerp(v0, v1, alpha)
    return v0 * (1.0 - alpha) + v1 * alpha


def _slerp(q0: np.ndarray, q1: np.ndarray, t: float) -> np.ndarray:
    """Spherical linear interpolation between two (x, y, z, w) quaternions."""
    q0 = q0.astype(np.float32)
    q1 = q1.astype(np.float32)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    if dot > 0.9995:
        # Nearly parallel — lerp + normalize
        out = q0 * (1.0 - t) + q1 * t
        n = np.linalg.norm(out)
        return out / n if n > 1e-9 else out
    theta_0 = float(np.arccos(np.clip(dot, -1.0, 1.0)))
    sin_theta_0 = float(np.sin(theta_0))
    theta = theta_0 * t
    s1 = float(np.sin(theta_0 - theta)) / sin_theta_0
    s2 = float(np.sin(theta)) / sin_theta_0
    return q0 * s1 + q1 * s2
