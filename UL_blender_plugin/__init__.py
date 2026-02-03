"""
Universal Library (UL) - Blender Addon

Provides integration between Universal Library and Blender.
Handles asset import/export and asset management within Blender.

Features:
- Export selected objects to USD library
- Import assets from library via USD or .blend (triggered from desktop app)
- Material conversion (Principled BSDF <-> UsdPreviewSurface)
- Sidebar panel for exporting and settings
- Queue-based import from desktop app
- Preferences for library path and defaults

Usage:
1. Set library path in addon preferences
2. Use sidebar panel (View3D > Sidebar > Asset Library)
3. Export: Select objects, click "Export to Library"
4. Import: Use the desktop app, select asset, click "Apply to Blender"
"""

bl_info = {
    "name": "Universal Library",
    "author": "CGstuff",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Asset Library",
    "description": "Asset management for Blender",
    "warning": "",
    "doc_url": "https://github.com/cgstuff/universal-library",
    "category": "Import-Export",
}

import bpy
from bpy.app.handlers import persistent

# Import submodules
from . import preferences
from . import operators
from . import panels
from . import properties
from . import gizmos
from .utils.library_connection import get_library_connection, set_library_path
from .utils import icon_loader


# Queue listener state
_queue_timer = None


@persistent
def load_handler(dummy):
    """Handler called when a .blend file is loaded"""
    # Restart queue listener after file load
    start_queue_listener()


def start_queue_listener():
    """Start the queue listener timer"""
    global _queue_timer

    # Already running
    if _queue_timer is not None:
        return

    def queue_timer_callback():
        """Timer callback to check import queue"""
        try:
            bpy.ops.ual.check_import_queue()
        except Exception:
            pass
        return 0.5  # Run again in 0.5 seconds

    _queue_timer = bpy.app.timers.register(queue_timer_callback, first_interval=1.0)


def stop_queue_listener():
    """Stop the queue listener timer"""
    global _queue_timer

    if _queue_timer is not None:
        try:
            bpy.app.timers.unregister(_queue_timer)
        except Exception:
            pass
        _queue_timer = None


def menu_func_export(self, context):
    """Add to File > Export menu"""
    self.layout.operator(
        operators.UAL_OT_export_to_library.bl_idname,
        text="Universal Library (.usd)"
    )
    self.layout.operator(
        operators.UAL_OT_export_collection.bl_idname,
        text="UAL Collection (Active Collection)"
    )


def menu_func_import(self, context):
    """Add to File > Import menu"""
    self.layout.operator(
        operators.UAL_OT_browse_library.bl_idname,
        text="Universal Library"
    )


def register():
    """Register addon classes and handlers"""
    # Register icons first (needed by panels)
    icon_loader.register()

    # Register preferences (needed by other modules)
    preferences.register()

    # Register operators
    operators.register()

    # Register panels
    panels.register()

    # Register object properties (for thumbnail helper)
    properties.register()

    # Register gizmos
    gizmos.register()

    # Add to menus
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

    # Add load handler
    bpy.app.handlers.load_post.append(load_handler)


    # Initialize library connection with user's preferred path
    try:
        prefs = preferences.get_preferences()
        if prefs:
            if prefs.library_path:
                # Use set_library_path to ensure the correct path is used
                # (get_library_connection ignores path if connection already exists)
                set_library_path(prefs.library_path)
        else:
            pass
    except Exception as e:
        pass

    # Start queue listener
    start_queue_listener()



def unregister():
    """Unregister addon classes and handlers"""
    # Stop queue listener
    stop_queue_listener()


    # Remove load handler
    if load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_handler)

    # Remove from menus
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    # Disconnect library
    try:
        library = get_library_connection()
        library.disconnect()
    except Exception:
        pass

    # Unregister in reverse order
    gizmos.unregister()
    properties.unregister()
    panels.unregister()
    operators.unregister()
    preferences.unregister()
    icon_loader.unregister()



if __name__ == "__main__":
    register()
