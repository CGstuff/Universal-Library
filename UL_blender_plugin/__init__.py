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
    "version": (1, 2, 1),
    "blender": (5, 0, 0),
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

# Re-export the gltf user extension class so Blender's io_scene_gltf2 addon
# discovers it. The addon looks for `glTF2ExportUserExtension` on each
# enabled addon's top-level module (see io_scene_gltf2/__init__.py).
from .gltf_action_filter import glTF2ExportUserExtension  # noqa: F401


# Queue listener state
_queue_timer = None


def _sweep_orphan_preview_images():
    """Remove `_UL_PREVIEW_*` temp images left behind by a crashed/aborted
    export. These are temporary downscaled texture copies our export operator
    creates and normally cleans up in a finally block — but if Blender
    crashed mid-export (or the operator was killed), they survive in
    bpy.data.images. Cumulative bloat across crashed sessions. Run on
    addon load and after any .blend load to keep things clean."""
    try:
        orphans = [img for img in bpy.data.images
                   if img.name.startswith('_UL_PREVIEW_')]
        for img in orphans:
            try:
                bpy.data.images.remove(img)
            except Exception:
                pass
        if orphans:
            print(f"[UL] swept {len(orphans)} orphaned _UL_PREVIEW_ image(s)")
    except Exception:
        pass  # bpy.data may not be ready in some early init contexts


@persistent
def load_handler(dummy):
    """Handler called when a .blend file is loaded"""
    # Restart queue listener after file load
    start_queue_listener()
    # Sweep any orphan preview-temp images from the loaded file
    _sweep_orphan_preview_images()


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

    # Sweep any orphan _UL_PREVIEW_ images from a previously-crashed session
    _sweep_orphan_preview_images()



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
