"""Create .current.blend copy for library swap support."""
import re
import shutil
from pathlib import Path


def _get_base_name(stem: str) -> str:
    """
    Extract base asset name from stem, removing version and representation suffixes.

    Examples:
        'Sword.v002' -> 'Sword'
        'Sword.v002.current' -> 'Sword'
        'Sword' -> 'Sword'
    """
    # Remove version (and everything after) if present
    result = re.sub(r'\.(v\d{3,}).*$', '', stem)
    # Also remove any representation suffix from legacy files
    for suffix in ('.current', '.proxy', '.render', '.nothing'):
        if result.endswith(suffix):
            result = result[:-len(suffix)]
    return result


def create_current_reference(blend_path):
    """
    Copy e.g. Sword.v002.blend -> Sword.current.blend alongside the original.

    The .current.blend uses the BASE name (no version) because it's a stable
    link target that always points to the latest version.
    """
    blend_path = Path(blend_path)
    if not blend_path.exists():
        return

    # Get base name (strip version for stable .current.blend naming)
    stem = blend_path.stem
    base_name = _get_base_name(stem)

    current_path = blend_path.parent / f"{base_name}.current.blend"
    try:
        shutil.copy2(str(blend_path), str(current_path))
    except Exception as e:
        pass
