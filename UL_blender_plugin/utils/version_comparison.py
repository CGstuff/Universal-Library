"""
Version Comparison Utilities

Collects and compares metadata between asset versions.
Used in export dialog to show changes from previous version.
"""

from typing import Dict, Any, Optional, List, Tuple
import bpy

from .library_connection import get_library_connection


def collect_scene_stats(context, objects: List[bpy.types.Object] = None) -> Dict[str, Any]:
    """
    Collect statistics from current scene/selection.

    Args:
        context: Blender context
        objects: Objects to analyze (defaults to selected)

    Returns:
        Dictionary of statistics
    """
    if objects is None:
        objects = context.selected_objects

    stats = {
        'object_count': len(objects),
        'polygon_count': 0,
        'vertex_count': 0,
        'material_count': 0,
        'materials': set(),
        'has_armature': False,
        'has_animations': False,
        'modifier_types': [],
    }

    for obj in objects:
        if obj.type == 'MESH' and obj.data:
            # Get evaluated mesh for accurate polygon count
            depsgraph = context.evaluated_depsgraph_get()
            eval_obj = obj.evaluated_get(depsgraph)
            mesh = eval_obj.to_mesh()

            if mesh:
                stats['polygon_count'] += len(mesh.polygons)
                stats['vertex_count'] += len(mesh.vertices)
                eval_obj.to_mesh_clear()

            # Count materials
            for slot in obj.material_slots:
                if slot.material:
                    stats['materials'].add(slot.material.name)

        elif obj.type == 'ARMATURE':
            stats['has_armature'] = True
            if obj.animation_data and obj.animation_data.action:
                stats['has_animations'] = True

        # Check for animations on any object
        if obj.animation_data and obj.animation_data.action:
            stats['has_animations'] = True

        # Collect modifier types
        for mod in obj.modifiers:
            if mod.type not in stats['modifier_types']:
                stats['modifier_types'].append(mod.type)

    stats['material_count'] = len(stats['materials'])
    stats['materials'] = list(stats['materials'])

    return stats


def get_version_stats(version_uuid: str) -> Optional[Dict[str, Any]]:
    """
    Get statistics for a stored version from database.

    Args:
        version_uuid: UUID of the version

    Returns:
        Dictionary of statistics or None
    """
    library = get_library_connection()
    asset = library.get_asset_by_uuid(version_uuid)

    if not asset:
        return None

    return {
        'name': asset.get('name', 'Unknown'),
        'version_label': asset.get('version_label', 'v001'),
        'polygon_count': asset.get('polygon_count', 0) or 0,
        'material_count': asset.get('material_count', 0) or 0,
        'has_armature': asset.get('has_skeleton', 0) == 1,
        'has_animations': asset.get('has_animations', 0) == 1,
        'representation_type': asset.get('representation_type', 'none'),
        'thumbnail_path': asset.get('thumbnail_path', ''),
    }


def compare_versions(
    current_stats: Dict[str, Any],
    previous_stats: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """
    Compare two versions and generate diff report.

    Args:
        current_stats: Stats from current scene
        previous_stats: Stats from previous version

    Returns:
        Dictionary with comparison results for each metric
        Each entry has: current, previous, diff_text, change_type
        change_type: 'added', 'removed', 'unchanged'
    """
    diff = {}

    # Polygon count comparison
    curr_poly = current_stats.get('polygon_count', 0)
    prev_poly = previous_stats.get('polygon_count', 0)
    poly_diff = curr_poly - prev_poly

    if poly_diff > 0:
        diff['polygon_count'] = {
            'current': curr_poly,
            'previous': prev_poly,
            'diff_text': f"+{poly_diff:,}",
            'change_type': 'added',
            'percent': (poly_diff / prev_poly * 100) if prev_poly > 0 else 100
        }
    elif poly_diff < 0:
        diff['polygon_count'] = {
            'current': curr_poly,
            'previous': prev_poly,
            'diff_text': f"{poly_diff:,}",
            'change_type': 'removed',
            'percent': (abs(poly_diff) / prev_poly * 100) if prev_poly > 0 else 100
        }
    else:
        diff['polygon_count'] = {
            'current': curr_poly,
            'previous': prev_poly,
            'diff_text': "No change",
            'change_type': 'unchanged',
            'percent': 0
        }

    # Material count comparison
    curr_mat = current_stats.get('material_count', 0)
    prev_mat = previous_stats.get('material_count', 0)
    mat_diff = curr_mat - prev_mat

    if mat_diff > 0:
        diff['material_count'] = {
            'current': curr_mat,
            'previous': prev_mat,
            'diff_text': f"+{mat_diff}",
            'change_type': 'added'
        }
    elif mat_diff < 0:
        diff['material_count'] = {
            'current': curr_mat,
            'previous': prev_mat,
            'diff_text': f"{mat_diff}",
            'change_type': 'removed'
        }
    else:
        diff['material_count'] = {
            'current': curr_mat,
            'previous': prev_mat,
            'diff_text': "No change",
            'change_type': 'unchanged'
        }

    # Skeleton comparison
    curr_skel = current_stats.get('has_armature', False)
    prev_skel = previous_stats.get('has_armature', False) or previous_stats.get('has_skeleton', False)

    if curr_skel and not prev_skel:
        diff['has_armature'] = {
            'current': True,
            'previous': False,
            'diff_text': "Added",
            'change_type': 'added'
        }
    elif not curr_skel and prev_skel:
        diff['has_armature'] = {
            'current': False,
            'previous': True,
            'diff_text': "Removed",
            'change_type': 'removed'
        }
    # Don't include if unchanged

    # Animation comparison
    curr_anim = current_stats.get('has_animations', False)
    prev_anim = previous_stats.get('has_animations', False)

    if curr_anim and not prev_anim:
        diff['has_animations'] = {
            'current': True,
            'previous': False,
            'diff_text': "Added",
            'change_type': 'added'
        }
    elif not curr_anim and prev_anim:
        diff['has_animations'] = {
            'current': False,
            'previous': True,
            'diff_text': "Removed",
            'change_type': 'removed'
        }
    # Don't include if unchanged

    return diff


def format_comparison_summary(diff: Dict[str, Dict[str, Any]]) -> str:
    """
    Format comparison diff as human-readable summary.

    Args:
        diff: Comparison dictionary from compare_versions()

    Returns:
        Formatted string summary
    """
    lines = []

    # Polygons
    if 'polygon_count' in diff:
        poly = diff['polygon_count']
        if poly['change_type'] != 'unchanged':
            lines.append(
                f"Polygons: {poly['previous']:,} -> {poly['current']:,} ({poly['diff_text']})"
            )

    # Materials
    if 'material_count' in diff:
        mat = diff['material_count']
        if mat['change_type'] != 'unchanged':
            lines.append(
                f"Materials: {mat['previous']} -> {mat['current']} ({mat['diff_text']})"
            )

    # Skeleton
    if 'has_armature' in diff:
        skel = diff['has_armature']
        lines.append(f"Skeleton: {skel['diff_text']}")

    # Animations
    if 'has_animations' in diff:
        anim = diff['has_animations']
        lines.append(f"Animations: {anim['diff_text']}")

    if not lines:
        return "No significant changes detected"

    return "\n".join(lines)


__all__ = [
    'collect_scene_stats',
    'get_version_stats',
    'compare_versions',
    'format_comparison_summary',
]
