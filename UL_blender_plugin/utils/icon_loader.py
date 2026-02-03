"""
Icon loader for Universal Library Blender addon.

Loads PNG icons from the icons/ directory for use in Blender UI.
Uses Blender's preview system for custom icons.
"""

import os
import bpy
import bpy.utils.previews

# Global preview collection
_preview_collections = {}


class Icons:
    """Icon name constants"""
    LAUNCH_APP = "UL"


def get_icon_id(icon_name: str) -> int:
    """
    Get the icon ID for a given icon name.

    Args:
        icon_name: Name of the icon file without extension (e.g., "UL" for "UL.png")

    Returns:
        Icon ID for use with icon_value parameter, or 0 if not found
    """
    pcoll = _preview_collections.get("main")
    if pcoll and icon_name in pcoll:
        return pcoll[icon_name].icon_id
    return 0


def register():
    """Register and load icons. Called when addon is enabled."""
    pcoll = bpy.utils.previews.new()

    # Get the icons directory (next to utils folder)
    icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons")

    if not os.path.exists(icons_dir):
        _preview_collections["main"] = pcoll
        return

    # Load all PNG files
    icon_count = 0
    for filename in os.listdir(icons_dir):
        if filename.lower().endswith(".png"):
            icon_name = os.path.splitext(filename)[0]
            icon_path = os.path.join(icons_dir, filename)

            try:
                pcoll.load(icon_name, icon_path, 'IMAGE')
                icon_count += 1
            except Exception as e:
                pass

    _preview_collections["main"] = pcoll


def unregister():
    """Unregister icons. Called when addon is disabled."""
    for pcoll in _preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    _preview_collections.clear()


__all__ = ['Icons', 'get_icon_id', 'register', 'unregister']
