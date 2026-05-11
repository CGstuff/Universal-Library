"""
Geometry generators for the asset viewport.

Stripped from World_Library/viewer/gl_geometry.py to just the grid generator —
the only geometry the asset viewport needs apart from loaded meshes.
"""

import numpy as np

__all__ = ['make_grid_lines']


def make_grid_lines(extent: float, step: float) -> np.ndarray:
    """Grid lines on the XY plane at z=0. Returns (N, 3) float32 vertex array.

    extent: half-width of the grid (a 10.0 extent → 20×20 area).
    step:   spacing between grid lines.
    """
    verts = []
    n = int(extent / step)
    for i in range(-n, n + 1):
        v = i * step
        verts.append((-extent, v, 0))
        verts.append((extent, v, 0))
        verts.append((v, -extent, 0))
        verts.append((v, extent, 0))
    return np.array(verts, dtype=np.float32)
