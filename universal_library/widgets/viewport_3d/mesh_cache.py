"""
GLB cache.

LRU cache keyed by (absolute_path, mtime). Multiple viewports (e.g. the small
preview panel + the enlarged modal) share a single cache so we don't re-parse
the same file twice.

The cache stores parsed `GLBData` (meshes + skin + nodes + animations).
GPU buffers are owned per-viewport — they can't be shared across
QOpenGLWidget contexts.

Two access shapes:
    load_glb_data(path) -> Optional[GLBData]     # full payload (Phase 6+)
    load_mesh(path)     -> Optional[list[MeshData]]  # bare mesh list (legacy)

Both share the cache — calling either after the other is free.
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from typing import Optional

from .gltf_loader import GLBData, MeshData, load_glb

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 16
_cache: "OrderedDict[tuple[str, float], GLBData]" = OrderedDict()


def load_glb_data(path: str) -> Optional[GLBData]:
    """Load + cache the full GLBData (meshes + skins + nodes + animations).

    Returns None if the path doesn't exist or parsing fails.
    """
    if not path or not os.path.isfile(path):
        return None

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None

    abs_path = os.path.abspath(path)
    key = (abs_path, mtime)

    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]

    try:
        data = load_glb(abs_path)
    except Exception as e:
        logger.error(f"[mesh_cache] Failed to load {abs_path}: {e}")
        return None

    if data is None or not data.meshes:
        return None

    _cache[key] = data
    while len(_cache) > _MAX_ENTRIES:
        _cache.popitem(last=False)
    return data


def load_mesh(path: str) -> Optional[list[MeshData]]:
    """Backward-compatible accessor — returns just the mesh list.

    Existing callers (AssetViewport) use this; new code wanting skins or
    animations should call `load_glb_data` instead.
    """
    data = load_glb_data(path)
    return data.meshes if data else None


def clear_cache():
    """Drop all cached entries."""
    _cache.clear()
