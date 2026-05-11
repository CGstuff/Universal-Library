"""3D asset preview viewport.

A trimmed QOpenGLWidget for rendering .glb meshes with an orbit camera.
Ported from World_Library_private_new/viewer with terrain, blockers, voxels,
gizmos, and instance rendering removed — only what's needed for asset preview.

Public API:
    AssetViewport — QOpenGLWidget subclass, the main viewport widget.
    load_mesh(path) → list[MeshData]  — load + cache .glb meshes.
"""

from .asset_viewport import AssetViewport
from .enlarged_viewer_dialog import EnlargedViewerDialog
from .gltf_loader import (
    MeshData, SkinData, NodeData,
    AnimationChannel, AnimationData, GLBData,
)
from .mesh_cache import load_mesh, load_glb_data, clear_cache

__all__ = [
    'AssetViewport', 'EnlargedViewerDialog',
    'MeshData', 'SkinData', 'NodeData',
    'AnimationChannel', 'AnimationData', 'GLBData',
    'load_mesh', 'load_glb_data', 'clear_cache',
]
