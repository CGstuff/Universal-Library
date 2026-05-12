"""
Always-visible UL launcher button (D0 from FEATURE_SPEC_REVIEW.md).

Adds a compact split-button to a chosen Blender header region (3D Viewport
header by default). Main click launches the desktop app via the existing
`ual.browse_library` operator; the adjacent dropdown arrow opens a menu with
the most-used quick actions (Open / Export Selected / Export Collection /
Browse Library / Settings).

Location is user-configurable via `header_button_location` in addon prefs —
switching it triggers `refresh_location()` to re-attach the draw fn to the
new region without an addon reload.
"""

import bpy

from ..utils.icon_loader import get_icon_id, Icons


# Maps preference enum → (bpy.types attr name, attach mode).
# attach mode:
#   "menus"   = append to VIEW3D_MT_editor_menus, renders inline with
#               View/Select/Add/Object (the "AnimToolBox" position)
#   "prepend" = far-left of the region (before built-in header draws)
#   "append"  = far-right of the region (after built-in header draws)
_HEADER_TARGETS = {
    'VIEW3D_HEADER': ("VIEW3D_MT_editor_menus", "menus"),
    'TOPBAR':        ("TOPBAR_HT_upper_bar",    "append"),
    'STATUSBAR':     ("STATUSBAR_HT_header",    "append"),
}

_attached_to: tuple = ()  # (attr, mode) of current attachment, empty when detached


class UAL_MT_header_menu(bpy.types.Menu):
    """Dropdown for the UL header launcher — main UL actions live here."""
    bl_idname = "UAL_MT_header_menu"
    bl_label = "Universal Library"

    def draw(self, context):
        layout = self.layout

        icon_id = get_icon_id(Icons.LAUNCH_APP)
        if icon_id:
            layout.operator("ual.browse_library", text="Open Desktop App", icon_value=icon_id)
        else:
            layout.operator("ual.browse_library", text="Open Desktop App", icon='WINDOW')

        layout.separator()

        layout.operator("ual.export_to_library", text="Export Selected", icon='EXPORT')
        layout.operator("ual.export_collection", text="Export Collection", icon='OUTLINER_COLLECTION')

        layout.separator()

        # Addon's top-level package matches UAL_Preferences.bl_idname (set via __package__).
        # Here __package__ is 'UL_blender_plugin.panels'; we want the root 'UL_blender_plugin'.
        layout.operator(
            "preferences.addon_show", text="Settings", icon='PREFERENCES',
        ).module = __package__.split('.', 1)[0]


def _draw_header_button(self, context):
    """Append-drawn fn registered on a Blender header type.

    Uses a contained `row(align=True)` so we don't bleed scale_x onto adjacent
    addons' buttons. Main button is icon-only for compactness; tooltip carries
    the label. Dropdown arrow opens UAL_MT_header_menu.
    """
    row = self.layout.row(align=True)

    icon_id = get_icon_id(Icons.LAUNCH_APP)
    if icon_id:
        row.operator("ual.browse_library", text="", icon_value=icon_id)
    else:
        row.operator("ual.browse_library", text="", icon='WINDOW')

    row.menu("UAL_MT_header_menu", text="", icon='DOWNARROW_HLT')


def _detach():
    """Remove the draw fn from whichever region it's currently attached to."""
    global _attached_to
    if not _attached_to:
        return
    attr, _mode = _attached_to
    region = getattr(bpy.types, attr, None)
    if region is not None:
        try:
            region.remove(_draw_header_button)
        except (ValueError, RuntimeError):
            pass
    _attached_to = ()


def _attach(target_attr: str, mode: str):
    """Attach the draw fn to a Blender extension point.

    The "menus" mode targets VIEW3D_MT_editor_menus and renders inline
    with View/Select/Add/Object (the AnimToolBox-style middle position).
    "prepend"/"append" target a header region and land at far-left or
    far-right respectively.
    """
    global _attached_to
    region = getattr(bpy.types, target_attr, None)
    if region is None:
        return
    if mode == "prepend":
        region.prepend(_draw_header_button)
    else:  # "append" or "menus"
        region.append(_draw_header_button)
    _attached_to = (target_attr, mode)


def refresh_location():
    """Re-attach the button to whatever region the prefs currently say.

    Called by the prefs `update` callback so the user sees the move
    immediately without disabling/re-enabling the addon.
    """
    from ..preferences import get_preferences
    prefs = get_preferences()
    if prefs is None:
        return

    _detach()
    target_key = prefs.header_button_location
    if target_key == 'HIDDEN':
        return
    target = _HEADER_TARGETS.get(target_key)
    if target:
        target_attr, mode = target
        _attach(target_attr, mode)


def register():
    bpy.utils.register_class(UAL_MT_header_menu)
    refresh_location()


def unregister():
    _detach()
    try:
        bpy.utils.unregister_class(UAL_MT_header_menu)
    except RuntimeError:
        pass


__all__ = ['UAL_MT_header_menu', 'refresh_location', 'register', 'unregister']
