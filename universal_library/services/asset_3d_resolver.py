"""
Asset 3D file resolver.

Returns the path to the `.glb` preview file for an asset version, if one
exists on disk. Used by the metadata panel's 3D viewport toggle to decide
whether 3D preview is available.

Conventions (written by the Blender exporter):
    Latest version:  {library_folder}/preview.current.glb
    Archived:        {archive_folder}/preview.{vNNN}.glb

Both files live next to the version's .blend file, so we resolve via the
parent directory of `blend_backup_path` rather than reconstructing the
library/_archive layout independently.
"""

from __future__ import annotations

import json
import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Asset types where 3D preview makes sense. Per Phase 2 spec, mesh + rig.
# (Collection also gets a .glb today, but we may revisit — for now we accept
# it too since the file is there.)
_TYPES_WITH_3D = {'mesh', 'rig', 'collection'}


def asset_supports_3d(asset: Optional[Dict[str, Any]]) -> bool:
    """Cheap check: does this asset type qualify for 3D preview at all?"""
    if not asset:
        return False
    return asset.get('asset_type') in _TYPES_WITH_3D


def resolve_glb_path(asset: Optional[Dict[str, Any]]) -> Optional[Path]:
    """Return the .glb file for this asset version, or None if not available.

    Looks first for `preview.current.glb` in the same folder as the asset's
    .blend file (latest version). If not present, falls back to the versioned
    name `preview.{version_label}.glb` (older/archived versions).

    Returns None when:
        - The asset is missing or unsupported type
        - No `blend_backup_path` is set
        - The folder doesn't exist
        - No matching `.glb` file is found
    """
    if not asset_supports_3d(asset):
        return None

    blend_path_str = asset.get('blend_backup_path') if asset else None
    if not blend_path_str:
        return None

    blend_path = Path(blend_path_str)
    folder = blend_path.parent
    if not folder.exists():
        return None

    # Prefer the stable `current` symlink-style file (latest version)
    current = folder / "preview.current.glb"
    if current.is_file():
        return current

    # Fall back to versioned name (archived versions)
    version_label = asset.get('version_label')
    if version_label:
        versioned = folder / f"preview.{version_label}.glb"
        if versioned.is_file():
            return versioned

    # Last resort: any preview*.glb in this folder
    for candidate in folder.glob("preview*.glb"):
        if candidate.is_file():
            return candidate

    return None


@dataclass
class Glb3DInfo:
    """What the metadata panel needs to know about an asset's 3D preview."""
    path: Path
    has_animations: bool


def resolve_glb_info(asset: Optional[Dict[str, Any]]) -> Optional[Glb3DInfo]:
    """Like `resolve_glb_path` but also peeks at the file to decide whether
    the asset has any animations. Returns None when no .glb resolves.

    The animation check parses ONLY the glTF JSON chunk — does not decode
    Draco mesh data, textures, or animation buffers. Cheap enough to call
    on every asset selection.
    """
    path = resolve_glb_path(asset)
    if path is None:
        return None
    return Glb3DInfo(
        path=path,
        has_animations=_glb_has_animations(path),
    )


def _glb_has_animations(path: Path) -> bool:
    """Read the glTF JSON chunk of a .glb file and return True iff the
    `animations` array is non-empty. Robust against malformed files —
    any parse error returns False rather than raising."""
    try:
        with open(path, 'rb') as f:
            # GLB header: magic(4) + version(4) + total_length(4)
            magic = f.read(4)
            if magic != b'glTF':
                return False
            f.read(8)  # skip version + total_length

            # First chunk MUST be JSON per spec
            chunk_length_bytes = f.read(4)
            chunk_type_bytes = f.read(4)
            if len(chunk_length_bytes) < 4 or chunk_type_bytes != b'JSON':
                return False
            chunk_length = struct.unpack('<I', chunk_length_bytes)[0]
            chunk_data = f.read(chunk_length)
            if len(chunk_data) < chunk_length:
                return False

            doc = json.loads(chunk_data.decode('utf-8'))
            return bool(doc.get('animations'))
    except Exception as e:
        logger.debug(f"[asset_3d_resolver] _glb_has_animations failed on {path}: {e}")
        return False
