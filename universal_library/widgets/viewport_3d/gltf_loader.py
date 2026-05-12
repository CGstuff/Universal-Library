"""
glTF/GLB mesh loader for asset preview.

Walks the glTF scene graph, composing node transforms so multi-mesh assets
display in their authored layout. Decodes diffuse (baseColor) textures via
QImage when present so meshes show their albedo.

Pure Python — no trimesh / pygltflib / assimp. QImage handles PNG/JPEG.
"""

from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np

from PyQt6.QtGui import QImage


# Y-up (glTF) → Z-up (Blender / UL) — rotate -90° around X
_Y_TO_Z = np.array([
    [1, 0,  0, 0],
    [0, 0, -1, 0],
    [0, 1,  0, 0],
    [0, 0,  0, 1],
], dtype=np.float64)


@dataclass
class MeshData:
    """Loaded mesh data ready for OpenGL rendering."""
    vertices: np.ndarray                   # (N, 3) float32 positions
    normals: np.ndarray                    # (N, 3) float32 normals
    uvs: Optional[np.ndarray] = None       # (N, 2) float32 or None
    indices: Optional[np.ndarray] = None   # (M,) uint32 or None
    color: tuple = (0.7, 0.7, 0.7)         # baseColorFactor
    base_image: Optional[QImage] = None    # baseColorTexture decoded, or None
    # Skinning attributes — populated only for primitives on skinned nodes
    joints: Optional[np.ndarray] = None    # (N, 4) uint32 joint indices per vertex
    weights: Optional[np.ndarray] = None   # (N, 4) float32 weights (sum=1)
    skin_index: Optional[int] = None       # index into GLBData.skins, or None


@dataclass
class SkinData:
    """A glTF skin — list of joint node indices + their inverse-bind matrices."""
    joints: List[int]                       # node indices that are joints
    inverse_bind_matrices: np.ndarray       # (J, 4, 4) float32 — IBM per joint
    skeleton_root: Optional[int] = None     # joint tree root node index, optional
    name: str = ""


@dataclass
class NodeData:
    """One glTF node. Used by animations to target joints and by 6.5's
    forward-kinematics pass to compute joint world matrices.

    Transforms are stored in glTF (Y-up) space. The Y_TO_Z conversion is
    applied as a root model matrix at render time so skinning and node TRS
    stay consistent."""
    name: str
    translation: np.ndarray  # (3,) float32 — initial T
    rotation: np.ndarray     # (4,) float32 — initial R as (qx, qy, qz, qw)
    scale: np.ndarray        # (3,) float32 — initial S
    children: List[int] = field(default_factory=list)
    parent: Optional[int] = None
    mesh: Optional[int] = None   # mesh index if this node has a mesh
    skin: Optional[int] = None   # skin index if this node is skinned


@dataclass
class AnimationChannel:
    """One animation channel — drives a node's T/R/S over time."""
    target_node: int            # node index this channel animates
    target_path: str            # 'translation' | 'rotation' | 'scale'
    times: np.ndarray           # (K,) float32 time values in seconds
    values: np.ndarray          # (K, 3) for T/S, (K, 4) for R
    interpolation: str = 'LINEAR'   # 'LINEAR' | 'STEP' | 'CUBICSPLINE'


@dataclass
class AnimationData:
    """One named glTF animation."""
    name: str
    duration: float             # max time across all channels (seconds)
    channels: List[AnimationChannel] = field(default_factory=list)


@dataclass
class GLBData:
    """Full result of a glTF/GLB load — meshes + scene graph + skins + animations."""
    meshes: List[MeshData] = field(default_factory=list)
    skins: List[SkinData] = field(default_factory=list)
    nodes: List[NodeData] = field(default_factory=list)
    animations: List[AnimationData] = field(default_factory=list)

    @property
    def has_animations(self) -> bool:
        return len(self.animations) > 0


def load_glb(path: str) -> GLBData:
    """Parse a binary .glb file. Returns a GLBData with meshes + scene graph +
    skins + animations. For backwards compatibility, callers wanting just the
    mesh list can read `.meshes`."""
    with open(path, 'rb') as f:
        magic = f.read(4)
        if magic != b'glTF':
            raise ValueError("Not a valid GLB file")
        version = struct.unpack('<I', f.read(4))[0]
        if version != 2:
            raise ValueError(f"Unsupported glTF version: {version}")
        total_length = struct.unpack('<I', f.read(4))[0]

        json_chunk = None
        bin_chunk = None
        while f.tell() < total_length:
            chunk_length = struct.unpack('<I', f.read(4))[0]
            chunk_type = f.read(4)
            chunk_data = f.read(chunk_length)
            if chunk_type == b'JSON':
                json_chunk = json.loads(chunk_data.decode('utf-8'))
            elif chunk_type == b'BIN\x00':
                bin_chunk = chunk_data

        if not json_chunk or not bin_chunk:
            return GLBData()

        ctx = _ParseContext(
            gltf=json_chunk,
            bin_data=bin_chunk,
            base_dir=os.path.dirname(os.path.abspath(path)),
        )

        glb = GLBData()
        glb.nodes = _load_nodes(ctx)
        glb.skins = _load_skins(ctx)
        glb.meshes = _build_meshes(ctx)
        glb.animations = _load_animations(ctx)
        return glb


# ----------------------------------------------------------------------
# Context + scene-graph walk
# ----------------------------------------------------------------------


@dataclass
class _ParseContext:
    gltf: dict
    bin_data: bytes
    base_dir: str
    # Lazy caches keyed by index, populated on demand
    image_cache: dict = field(default_factory=dict)   # image_idx -> QImage


def _build_meshes(ctx: _ParseContext) -> list[MeshData]:
    """Walk the scene graph, collect (mesh_idx, world_matrix) pairs,
    and parse each primitive with its world transform applied."""
    scenes = ctx.gltf.get('scenes', [])
    nodes = ctx.gltf.get('nodes', [])
    if not scenes or not nodes:
        # Fallback: no scene graph → render meshes at origin
        return _build_flat(ctx)

    scene_idx = ctx.gltf.get('scene', 0)
    if scene_idx >= len(scenes):
        scene_idx = 0
    root_nodes = scenes[scene_idx].get('nodes', [])

    meshes: list[MeshData] = []
    identity = np.eye(4, dtype=np.float64)
    for n_idx in root_nodes:
        _walk_node(ctx, n_idx, identity, meshes)
    return meshes


def _build_flat(ctx: _ParseContext) -> list[MeshData]:
    """Fallback when no scene graph is present — flatten mesh list at origin."""
    meshes_out = []
    # Apply the Y→Z conversion at root only
    root = _Y_TO_Z.copy()
    for mesh_idx in range(len(ctx.gltf.get('meshes', []))):
        for md in _parse_mesh(ctx, mesh_idx, root, skin_idx=None):
            meshes_out.append(md)
    return meshes_out


def _walk_node(ctx: _ParseContext, node_idx: int, parent_world: np.ndarray,
               out: list[MeshData]):
    nodes = ctx.gltf['nodes']
    if node_idx >= len(nodes):
        return
    node = nodes[node_idx]
    local = _node_local_matrix(node)
    world = parent_world @ local

    mesh_idx = node.get('mesh')
    if mesh_idx is not None:
        skin_idx = node.get('skin')  # None for un-skinned meshes
        if skin_idx is not None:
            # Skinned: vertices stay in skin-local glTF (Y-up) space.
            # 6.5 will apply Y→Z + joint matrices in the vertex shader.
            for md in _parse_mesh(ctx, mesh_idx, np.eye(4), skin_idx=skin_idx):
                out.append(md)
        else:
            # Un-skinned: bake world × Y→Z into vertices at load time
            # (current static-mesh behavior).
            final = _Y_TO_Z @ world
            for md in _parse_mesh(ctx, mesh_idx, final, skin_idx=None):
                out.append(md)

    for child_idx in node.get('children', []):
        _walk_node(ctx, child_idx, world, out)


def _node_local_matrix(node: dict) -> np.ndarray:
    """Read a node's local transform — `matrix` if present, else T*R*S."""
    if 'matrix' in node:
        # glTF stores matrices column-major; numpy is row-major
        m = np.array(node['matrix'], dtype=np.float64).reshape(4, 4).T
        return m

    t = np.array(node.get('translation', [0, 0, 0]), dtype=np.float64)
    r = np.array(node.get('rotation', [0, 0, 0, 1]), dtype=np.float64)  # qx,qy,qz,qw
    s = np.array(node.get('scale', [1, 1, 1]), dtype=np.float64)

    # Translation
    T = np.eye(4)
    T[:3, 3] = t

    # Rotation from quaternion
    R = _quat_to_mat4(r)

    # Scale
    S = np.diag([s[0], s[1], s[2], 1.0])

    return T @ R @ S


def _quat_to_mat4(q: np.ndarray) -> np.ndarray:
    """Convert a (qx, qy, qz, qw) quaternion to a 4x4 rotation matrix."""
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    if n < 1e-12:
        return np.eye(4)
    s = 2.0 / n
    wx, wy, wz = s * w * x, s * w * y, s * w * z
    xx, xy, xz = s * x * x, s * x * y, s * x * z
    yy, yz, zz = s * y * y, s * y * z, s * z * z
    return np.array([
        [1.0 - (yy + zz), xy - wz,         xz + wy,         0.0],
        [xy + wz,         1.0 - (xx + zz), yz - wx,         0.0],
        [xz - wy,         yz + wx,         1.0 - (xx + yy), 0.0],
        [0.0,             0.0,             0.0,             1.0],
    ], dtype=np.float64)


# ----------------------------------------------------------------------
# Draco mesh decompression
# ----------------------------------------------------------------------


_DRACO_MODULE = None         # Lazily-loaded DracoPy module
_DRACO_IMPORT_WARNED = False  # Print the missing-dep message at most once


def _get_dracopy():
    """Return the DracoPy module if available, else None. Cached after first call."""
    global _DRACO_MODULE, _DRACO_IMPORT_WARNED
    if _DRACO_MODULE is not None:
        return _DRACO_MODULE
    try:
        import DracoPy  # type: ignore
        _DRACO_MODULE = DracoPy
        return DracoPy
    except ImportError:
        if not _DRACO_IMPORT_WARNED:
            print("[gltf_loader] DracoPy not installed — Draco-compressed meshes "
                  "will fail to load. Install with: pip install DracoPy")
            _DRACO_IMPORT_WARNED = True
        return None


def _decode_draco_primitive(draco_ext: dict, buffer_views: list,
                            bin_data: bytes) -> Optional[tuple]:
    """Decode a Draco-compressed primitive's geometry + optional skinning attrs.

    Returns (vertices, normals, uvs, indices, joints, weights) or None on failure.
    `joints` / `weights` are populated when the Draco extension's `attributes`
    map names JOINTS_0 / WEIGHTS_0 — i.e. the primitive belongs to a skinned mesh.
    """
    DracoPy = _get_dracopy()
    if DracoPy is None:
        return None

    bv_idx = draco_ext.get('bufferView')
    if bv_idx is None or bv_idx >= len(buffer_views):
        print("[gltf_loader] Draco primitive missing bufferView reference")
        return None

    bv = buffer_views[bv_idx]
    offset = bv.get('byteOffset', 0)
    length = bv.get('byteLength', 0)
    blob = bytes(bin_data[offset:offset + length])

    try:
        mesh = DracoPy.decode_buffer_to_mesh(blob)
    except Exception as e:
        print(f"[gltf_loader] DracoPy.decode_buffer_to_mesh failed: {e}")
        return None

    # DracoMesh in DracoPy 2.x exposes attributes as numpy ndarrays — either
    # flat 1D or shape (N, k). Some attributes are None when absent. Use
    # `.size` (total elements) for length checks since `len()` on a 2D array
    # returns the row count, not the total element count.
    try:
        if mesh.points is None or np.asarray(mesh.points).size == 0:
            print("[gltf_loader] Draco mesh has no points")
            return None
        verts_flat = np.asarray(mesh.points, dtype=np.float32)
        if verts_flat.size % 3 != 0:
            print("[gltf_loader] Draco mesh vertex buffer wrong size")
            return None
        vertices = verts_flat.reshape(-1, 3)
        n_verts = vertices.shape[0]

        normals = _reshape_or_none(mesh.normals, np.float32, n_verts, 3)
        if normals is None:
            normals = np.zeros_like(vertices)
            normals[:, 2] = 1.0

        uvs = _reshape_or_none(mesh.tex_coord, np.float32, n_verts, 2)

        indices = None
        if mesh.faces is not None:
            faces = np.asarray(mesh.faces, dtype=np.uint32)
            if faces.size > 0 and faces.size % 3 == 0:
                indices = faces.reshape(-1)

        # Skinning attributes live in Draco's generic-attribute slots. The
        # glTF Draco extension's `attributes` map gives us the unique_id
        # for each glTF attribute name.
        joints = None
        weights = None
        attr_map = draco_ext.get('attributes', {})
        joints_uid = attr_map.get('JOINTS_0')
        if joints_uid is not None:
            joints = _draco_attribute_data(mesh, joints_uid, n_verts, 4, np.uint32)
        weights_uid = attr_map.get('WEIGHTS_0')
        if weights_uid is not None:
            weights = _draco_attribute_data(mesh, weights_uid, n_verts, 4, np.float32)

        return vertices, normals, uvs, indices, joints, weights
    except Exception as e:
        print(f"[gltf_loader] Draco mesh attribute extraction failed: {e}")
        return None


def _draco_attribute_data(mesh, unique_id: int, expected_rows: int, cols: int,
                          dtype) -> Optional[np.ndarray]:
    """Pull a generic attribute (joints/weights) out of a DracoMesh.

    DracoPy returns each attribute as a dict with a `data` ndarray. We coerce
    to (expected_rows, cols) of the requested dtype. Returns None if missing
    or wrong size — caller falls back to "no skinning" gracefully.
    """
    try:
        attr = mesh.get_attribute_by_unique_id(int(unique_id))
    except Exception as e:
        print(f"[gltf_loader] Draco get_attribute_by_unique_id({unique_id}) failed: {e}")
        return None
    if attr is None:
        return None
    data = attr.get('data') if isinstance(attr, dict) else getattr(attr, 'data', None)
    if data is None:
        return None
    return _reshape_or_none(data, dtype, expected_rows, cols)


def _reshape_or_none(arr, dtype, expected_rows: int, cols: int) -> Optional[np.ndarray]:
    """Coerce a Draco attribute (flat or 2D) to shape (expected_rows, cols)
    of the given dtype. Returns None if the array is missing or wrong size."""
    if arr is None:
        return None
    a = np.asarray(arr, dtype=dtype)
    if a.size != expected_rows * cols:
        return None
    return a.reshape(expected_rows, cols)


# ----------------------------------------------------------------------
# Primitive parsing
# ----------------------------------------------------------------------


def _parse_mesh(ctx: _ParseContext, mesh_idx: int, world: np.ndarray,
                skin_idx: Optional[int]) -> list[MeshData]:
    meshes = ctx.gltf.get('meshes', [])
    if mesh_idx >= len(meshes):
        return []
    out = []
    for primitive in meshes[mesh_idx].get('primitives', []):
        try:
            md = _parse_primitive(ctx, primitive, world, skin_idx)
            if md:
                out.append(md)
        except Exception as e:
            print(f"[gltf_loader] Failed to parse primitive: {e}")
    return out


def _parse_primitive(ctx: _ParseContext, primitive: dict,
                     world: np.ndarray,
                     skin_idx: Optional[int]) -> Optional[MeshData]:
    gltf = ctx.gltf
    accessors = gltf.get('accessors', [])
    buffer_views = gltf.get('bufferViews', [])
    bin_data = ctx.bin_data

    joints: Optional[np.ndarray] = None
    weights: Optional[np.ndarray] = None

    # Fast path: if KHR_draco_mesh_compression is present on this primitive,
    # decode the compressed blob via DracoPy and skip the accessor reads —
    # Blender no longer writes valid raw buffer data when Draco is enabled.
    draco_ext = primitive.get('extensions', {}).get('KHR_draco_mesh_compression')
    if draco_ext is not None:
        decoded = _decode_draco_primitive(draco_ext, buffer_views, bin_data)
        if decoded is None:
            return None
        vertices, normals, uvs, indices, joints, weights = decoded
    else:
        attributes = primitive.get('attributes', {})
        pos_idx = attributes.get('POSITION')
        if pos_idx is None:
            return None

        vertices = _read_accessor(accessors[pos_idx], buffer_views, bin_data)
        if vertices is None:
            return None

        norm_idx = attributes.get('NORMAL')
        if norm_idx is not None:
            normals = _read_accessor(accessors[norm_idx], buffer_views, bin_data)
        else:
            normals = np.zeros_like(vertices)
            normals[:, 2] = 1.0

        uvs = None
        uv_idx = attributes.get('TEXCOORD_0')
        if uv_idx is not None:
            uvs = _read_accessor(accessors[uv_idx], buffer_views, bin_data)
            if uvs is not None:
                # glTF and QImage both store with V going down from top; uploading a
                # QImage to glTexImage2D with V going down means sampling at the same
                # UV the artist authored returns the same pixel. NO flip needed —
                # flipping here would mirror every texture vertically.
                uvs = uvs.astype(np.float32, copy=False)

        # Skinning attributes (JOINTS_0 / WEIGHTS_0). May be uint8/uint16 indices
        # and float/uint8/uint16 weights. We promote to uint32 / float32.
        j_idx = attributes.get('JOINTS_0')
        if j_idx is not None:
            raw = _read_accessor(accessors[j_idx], buffer_views, bin_data)
            if raw is not None:
                joints = raw.astype(np.uint32, copy=False)
        w_idx = attributes.get('WEIGHTS_0')
        if w_idx is not None:
            raw = _read_accessor(accessors[w_idx], buffer_views, bin_data)
            if raw is not None:
                weights = raw.astype(np.float32, copy=False)

        indices = None
        idx_accessor = primitive.get('indices')
        if idx_accessor is not None:
            indices = _read_accessor(
                accessors[idx_accessor], buffer_views, bin_data, as_indices=True
            )

    # Skinned primitives: vertices stay in skin-local glTF (Y-up) space.
    # The skinning shader (Phase 6.5) will apply joint matrices + Y→Z at draw time.
    # Un-skinned primitives: bake world transform now (existing static behavior).
    if skin_idx is None:
        vertices = _transform_points(vertices, world)
        normal_mat = _normal_matrix(world)
        normals = _transform_normals(normals, normal_mat)

    # Material: base color factor + optional baseColorTexture
    materials = gltf.get('materials', [])
    color = (0.7, 0.7, 0.7)
    base_image: Optional[QImage] = None
    mat_idx = primitive.get('material')
    if mat_idx is not None and mat_idx < len(materials):
        material = materials[mat_idx]
        pbr = material.get('pbrMetallicRoughness', {})
        bcf = pbr.get('baseColorFactor')
        if bcf and len(bcf) >= 3:
            color = (bcf[0], bcf[1], bcf[2])
        tex_info = pbr.get('baseColorTexture')
        if tex_info:
            tex_idx = tex_info.get('index')
            if tex_idx is not None:
                base_image = _load_texture_image(ctx, tex_idx)

    return MeshData(
        vertices=vertices.astype(np.float32, copy=False),
        normals=normals.astype(np.float32, copy=False),
        uvs=uvs,
        indices=indices,
        color=color,
        base_image=base_image,
        joints=joints,
        weights=weights,
        skin_index=skin_idx,
    )


# ----------------------------------------------------------------------
# Texture decoding
# ----------------------------------------------------------------------


def _load_texture_image(ctx: _ParseContext, texture_idx: int) -> Optional[QImage]:
    gltf = ctx.gltf
    textures = gltf.get('textures', [])
    if texture_idx >= len(textures):
        return None
    texture = textures[texture_idx]

    # Texture source can be at texture.source (standard) OR inside one of the
    # texture-format extensions. Check both — Blender writes WEBP textures into
    # the EXT_texture_webp extension with no top-level fallback.
    image_idx = texture.get('source')
    if image_idx is None:
        extensions = texture.get('extensions', {})
        for ext_name in ('EXT_texture_webp', 'KHR_texture_basisu', 'EXT_texture_avif'):
            ext = extensions.get(ext_name)
            if ext and 'source' in ext:
                image_idx = ext['source']
                break
    if image_idx is None:
        return None

    if image_idx in ctx.image_cache:
        return ctx.image_cache[image_idx]

    images = gltf.get('images', [])
    if image_idx >= len(images):
        return None
    image = images[image_idx]

    qimg: Optional[QImage] = None

    # Embedded via bufferView (most common for .glb)
    bv_idx = image.get('bufferView')
    if bv_idx is not None:
        bvs = gltf.get('bufferViews', [])
        if bv_idx < len(bvs):
            bv = bvs[bv_idx]
            offset = bv.get('byteOffset', 0)
            length = bv.get('byteLength', 0)
            data = bytes(ctx.bin_data[offset:offset + length])
            qimg = QImage()
            if not qimg.loadFromData(data):
                qimg = None
    elif image.get('uri'):
        uri = image['uri']
        if uri.startswith('data:'):
            # data: URI — base64 inline
            import base64
            try:
                comma = uri.index(',')
                data = base64.b64decode(uri[comma + 1:])
                qimg = QImage()
                if not qimg.loadFromData(data):
                    qimg = None
            except Exception:
                qimg = None
        else:
            # Relative file path
            full_path = os.path.join(ctx.base_dir, uri)
            qimg = QImage(full_path)
            if qimg.isNull():
                qimg = None

    if qimg is not None and not qimg.isNull():
        # Normalize to a known format for predictable GL upload (RGBA8888)
        qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)

    ctx.image_cache[image_idx] = qimg
    return qimg


# ----------------------------------------------------------------------
# Scene graph / skins / animations
# ----------------------------------------------------------------------


def _load_nodes(ctx: _ParseContext) -> List[NodeData]:
    """Build a NodeData list from the glTF JSON's `nodes[]` array.

    Stores each node's local TRS (or decomposed `matrix` if that form was used).
    Fills in `parent` links by walking the children references afterwards.
    """
    raw_nodes = ctx.gltf.get('nodes', [])
    nodes: List[NodeData] = []

    for i, node in enumerate(raw_nodes):
        if 'matrix' in node:
            # glTF matrix is column-major; we decompose to T/R/S for animation
            # blending. Skip decomposition complexity — use identity TRS and
            # store the matrix only if needed. For now, decompose roughly:
            m = np.array(node['matrix'], dtype=np.float64).reshape(4, 4).T
            t = m[:3, 3].astype(np.float32)
            # Crude scale: column lengths of the 3x3 part
            sx = float(np.linalg.norm(m[:3, 0]))
            sy = float(np.linalg.norm(m[:3, 1]))
            sz = float(np.linalg.norm(m[:3, 2]))
            s = np.array([sx, sy, sz], dtype=np.float32)
            # Rotation = normalize columns, then matrix→quaternion
            R3 = np.eye(3, dtype=np.float64)
            if sx > 1e-9 and sy > 1e-9 and sz > 1e-9:
                R3[:, 0] = m[:3, 0] / sx
                R3[:, 1] = m[:3, 1] / sy
                R3[:, 2] = m[:3, 2] / sz
            r = _mat3_to_quat(R3).astype(np.float32)
        else:
            t = np.array(node.get('translation', [0.0, 0.0, 0.0]), dtype=np.float32)
            r = np.array(node.get('rotation', [0.0, 0.0, 0.0, 1.0]), dtype=np.float32)
            s = np.array(node.get('scale', [1.0, 1.0, 1.0]), dtype=np.float32)

        nodes.append(NodeData(
            name=node.get('name', f'node_{i}'),
            translation=t,
            rotation=r,
            scale=s,
            children=list(node.get('children', [])),
            mesh=node.get('mesh'),
            skin=node.get('skin'),
        ))

    # Fill parent links
    for i, n in enumerate(nodes):
        for c in n.children:
            if 0 <= c < len(nodes):
                nodes[c].parent = i

    return nodes


def _mat3_to_quat(m: np.ndarray) -> np.ndarray:
    """Convert a 3x3 rotation matrix to a (qx, qy, qz, qw) quaternion."""
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0:
        s = 0.5 / np.sqrt(t + 1.0)
        return np.array([
            (m[2, 1] - m[1, 2]) * s,
            (m[0, 2] - m[2, 0]) * s,
            (m[1, 0] - m[0, 1]) * s,
            0.25 / s,
        ], dtype=np.float64)
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
        return np.array([
            0.25 * s,
            (m[0, 1] + m[1, 0]) / s,
            (m[0, 2] + m[2, 0]) / s,
            (m[2, 1] - m[1, 2]) / s,
        ], dtype=np.float64)
    if m[1, 1] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
        return np.array([
            (m[0, 1] + m[1, 0]) / s,
            0.25 * s,
            (m[1, 2] + m[2, 1]) / s,
            (m[0, 2] - m[2, 0]) / s,
        ], dtype=np.float64)
    s = 2.0 * np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
    return np.array([
        (m[0, 2] + m[2, 0]) / s,
        (m[1, 2] + m[2, 1]) / s,
        0.25 * s,
        (m[1, 0] - m[0, 1]) / s,
    ], dtype=np.float64)


def _load_skins(ctx: _ParseContext) -> List[SkinData]:
    """Build a SkinData list from the glTF JSON's `skins[]` array.

    Each skin has joint node indices and an `inverseBindMatrices` accessor
    referencing a MAT4 array (one IBM per joint).
    """
    gltf = ctx.gltf
    raw_skins = gltf.get('skins', [])
    accessors = gltf.get('accessors', [])
    buffer_views = gltf.get('bufferViews', [])
    bin_data = ctx.bin_data
    skins: List[SkinData] = []

    for skin in raw_skins:
        joints = list(skin.get('joints', []))
        ibm_idx = skin.get('inverseBindMatrices')
        if ibm_idx is not None and ibm_idx < len(accessors):
            raw = _read_accessor(accessors[ibm_idx], buffer_views, bin_data)
            if raw is not None and raw.size == len(joints) * 16:
                # glTF stores each MAT4 as 16 floats column-major.
                # Reshape to (J, 4, 4) and transpose each to row-major for numpy.
                ibm = raw.astype(np.float32, copy=False).reshape(-1, 4, 4)
                ibm = np.transpose(ibm, (0, 2, 1)).copy()
            else:
                ibm = np.tile(np.eye(4, dtype=np.float32), (len(joints), 1, 1))
        else:
            ibm = np.tile(np.eye(4, dtype=np.float32), (len(joints), 1, 1))

        skins.append(SkinData(
            joints=joints,
            inverse_bind_matrices=ibm,
            skeleton_root=skin.get('skeleton'),
            name=skin.get('name', ''),
        ))

    return skins


def _load_animations(ctx: _ParseContext) -> List[AnimationData]:
    """Build an AnimationData list from the glTF JSON's `animations[]` array.

    Each animation = list of channels. Each channel binds a sampler (time +
    value arrays) to a target node's TRS property.
    """
    gltf = ctx.gltf
    raw_animations = gltf.get('animations', [])
    accessors = gltf.get('accessors', [])
    buffer_views = gltf.get('bufferViews', [])
    bin_data = ctx.bin_data
    out: List[AnimationData] = []

    for ai, anim in enumerate(raw_animations):
        samplers = anim.get('samplers', [])
        channels_out: List[AnimationChannel] = []
        duration = 0.0

        for channel in anim.get('channels', []):
            target = channel.get('target', {})
            target_node = target.get('node')
            target_path = target.get('path')
            sampler_idx = channel.get('sampler')

            if target_node is None or sampler_idx is None:
                continue
            if target_path not in ('translation', 'rotation', 'scale'):
                continue  # skip 'weights' (shape-key) for now — Phase 6 non-goal
            if sampler_idx >= len(samplers):
                continue

            sampler = samplers[sampler_idx]
            time_idx = sampler.get('input')
            val_idx = sampler.get('output')
            if time_idx is None or val_idx is None:
                continue
            if time_idx >= len(accessors) or val_idx >= len(accessors):
                continue

            times = _read_accessor(accessors[time_idx], buffer_views, bin_data)
            values = _read_accessor(accessors[val_idx], buffer_views, bin_data)
            if times is None or values is None or times.size == 0:
                continue

            times = times.astype(np.float32, copy=False)
            values = values.astype(np.float32, copy=False)
            duration = max(duration, float(times[-1]) if times.size else 0.0)

            channels_out.append(AnimationChannel(
                target_node=target_node,
                target_path=target_path,
                times=times,
                values=values,
                interpolation=sampler.get('interpolation', 'LINEAR'),
            ))

        out.append(AnimationData(
            name=anim.get('name', f'Animation_{ai}'),
            duration=duration,
            channels=channels_out,
        ))

    return out


# ----------------------------------------------------------------------
# Vector / matrix helpers
# ----------------------------------------------------------------------


def _transform_points(verts: np.ndarray, m: np.ndarray) -> np.ndarray:
    """Apply a 4x4 matrix to (N, 3) points."""
    if verts.size == 0:
        return verts
    ones = np.ones((verts.shape[0], 1), dtype=np.float64)
    homog = np.concatenate([verts.astype(np.float64), ones], axis=1)
    out = homog @ m.T
    return out[:, :3]


def _transform_normals(normals: np.ndarray, normal_mat: np.ndarray) -> np.ndarray:
    """Apply a 3x3 normal matrix and renormalize."""
    if normals.size == 0:
        return normals
    out = normals.astype(np.float64) @ normal_mat.T
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms[norms < 1e-12] = 1.0
    return out / norms


def _normal_matrix(world: np.ndarray) -> np.ndarray:
    """Return the inverse-transpose 3x3 of the world matrix's upper-left."""
    m3 = world[:3, :3]
    try:
        inv = np.linalg.inv(m3)
    except np.linalg.LinAlgError:
        return np.eye(3)
    return inv.T


def _read_accessor(accessor: dict, buffer_views: list, bin_data: bytes,
                   as_indices: bool = False) -> Optional[np.ndarray]:
    # KNOWN LIMITATIONS — all verified safe against Blender's gltf exporter
    # (production exports inspected, none trigger any of these):
    #
    # 1. `bufferView.byteStride` is not honored. glTF allows interleaved
    #    attributes in one bufferView with stride > element_size; we read
    #    them as if tightly packed. External glTFs (three.js, game engines,
    #    Khronos samples) may interleave and would load with corrupted
    #    vertex data. Fix path: `np.lib.stride_tricks.as_strided`.
    #
    # 2. `accessor.normalized` is not honored. glTF allows int8/uint8/
    #    int16/uint16 attributes with `normalized: true`, meaning values
    #    should be divided by max_int and used as floats (compact normals,
    #    quantized weights, etc.). We return raw integers. Fix path: when
    #    `normalized=True` and dtype is integer, return `arr / dtype_max`
    #    as float32.
    #
    # 3. `accessor.sparse` is not honored. Sparse accessors override base
    #    data at specific indices. Used mainly for shape-key animations,
    #    which we explicitly skip elsewhere (Phase 6 non-goal).
    bv_idx = accessor.get('bufferView')
    if bv_idx is None:
        return None
    buffer_view = buffer_views[bv_idx]
    byte_offset = buffer_view.get('byteOffset', 0) + accessor.get('byteOffset', 0)

    component_type = accessor['componentType']
    count = accessor['count']
    accessor_type = accessor['type']

    dtype_map = {
        5120: np.int8, 5121: np.uint8, 5122: np.int16,
        5123: np.uint16, 5125: np.uint32, 5126: np.float32,
    }
    dtype = dtype_map.get(component_type, np.float32)
    type_components = {
        'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4,
        'MAT2': 4, 'MAT3': 9, 'MAT4': 16,
    }
    components = type_components.get(accessor_type, 1)

    element_size = np.dtype(dtype).itemsize * components
    data_slice = bin_data[byte_offset:byte_offset + count * element_size]
    arr = np.frombuffer(data_slice, dtype=dtype)
    if components > 1:
        arr = arr.reshape(-1, components)
    if as_indices:
        return arr.astype(np.uint32)
    return arr
