"""
Addon Preferences for Universal Library

User-configurable settings for the addon.
"""

import os
import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty
from pathlib import Path

from .utils.library_connection import set_library_path, get_library_connection
from .utils.appdata import read_library_path as _read_appdata_path, write_library_path as _write_appdata_path


def get_default_library_path() -> str:
    """Get default library path from shared AppData config or fallback."""
    # Try shared AppData config first
    appdata_path = _read_appdata_path()
    if appdata_path:
        return appdata_path

    # Fallback to Documents
    if os.name == 'nt':
        docs = Path(os.environ.get("USERPROFILE", "")) / "Documents"
    else:
        docs = Path.home() / "Documents"
    return str(docs / "UniversalAssetLibrary")


class UAL_Preferences(AddonPreferences):
    """Addon preferences for Universal Library"""
    bl_idname = __package__

    # Library path
    library_path: StringProperty(
        name="Library Path",
        description="Path to the Universal Library folder",
        default=get_default_library_path(),
        subtype='DIR_PATH',
        update=lambda self, ctx: self._on_library_path_changed()
    )

    # Import settings
    import_materials_default: BoolProperty(
        name="Import Materials by Default",
        description="Include materials when importing assets",
        default=True
    )

    # Export settings
    create_blend_backup_default: BoolProperty(
        name="Create .blend Backup by Default",
        description="Save a .blend backup alongside USD exports",
        default=True
    )

    auto_generate_thumbnail: BoolProperty(
        name="Auto Generate Thumbnail",
        description="Automatically generate thumbnail on export",
        default=True
    )

    thumbnail_size: IntProperty(
        name="Thumbnail Size",
        description="Size of generated thumbnails (pixels)",
        default=256,
        min=64,
        max=1024
    )

    # Naming settings
    use_auto_naming: BoolProperty(
        name="Use Auto-Naming",
        description="Automatically generate asset names with prefixes",
        default=True
    )

    prefix_model: StringProperty(
        name="Model Prefix",
        description="Prefix for model assets",
        default="MDL"
    )

    prefix_rig: StringProperty(
        name="Rig Prefix",
        description="Prefix for rigged assets",
        default="RIG"
    )

    prefix_material: StringProperty(
        name="Material Prefix",
        description="Prefix for material assets",
        default="MAT"
    )

    prefix_prop: StringProperty(
        name="Prop Prefix",
        description="Prefix for prop assets",
        default="PRP"
    )

    prefix_character: StringProperty(
        name="Character Prefix",
        description="Prefix for character assets",
        default="CHR"
    )

    validate_names: BoolProperty(
        name="Validate Names on Export",
        description="Show warning if name doesn't follow naming convention",
        default=True
    )

    # UI settings
    show_polygon_count: BoolProperty(
        name="Show Polygon Count",
        description="Display polygon count in asset list",
        default=True
    )

    list_display_mode: EnumProperty(
        name="List Display Mode",
        description="How to display assets in the panel",
        items=[
            ('COMPACT', "Compact", "Compact list view"),
            ('DETAILED', "Detailed", "Show more details per asset"),
        ],
        default='COMPACT'
    )

    # Desktop App settings
    launch_mode: EnumProperty(
        name="Launch Mode",
        description="How to launch the desktop application",
        items=[
            ('PRODUCTION', "Production", "Launch installed application"),
            ('DEVELOPMENT', "Development", "Run from source with Python"),
        ],
        default='PRODUCTION'
    )

    app_executable_path: StringProperty(
        name="App Executable",
        description="Path to the Universal Library executable (for Production mode)",
        default="",
        subtype='FILE_PATH'
    )

    dev_script_path: StringProperty(
        name="Dev Script Path",
        description="Path to run.py script (for Development mode)",
        default="",
        subtype='FILE_PATH'
    )

    python_executable: StringProperty(
        name="Python Executable",
        description="Python interpreter for development mode",
        default="python",
        subtype='FILE_PATH'
    )

    def _on_library_path_changed(self):
        """Called when library path changes — sync to AppData config"""
        if self.library_path:
            set_library_path(self.library_path)

            # Sync to shared AppData config so desktop app sees the same path
            try:
                _write_appdata_path(self.library_path)
            except Exception as e:
                pass

    def draw(self, context):
        layout = self.layout

        # Library section
        box = layout.box()
        box.label(text="Library Settings", icon='FILE_FOLDER')

        row = box.row()
        row.prop(self, "library_path")

        # Show library status
        library = get_library_connection()
        if library.library_path.exists():
            assets = library.get_all_assets()
            box.label(text=f"Connected: {len(assets)} assets", icon='CHECKMARK')
        else:
            box.label(text="Library not found", icon='ERROR')

        # Import section
        box = layout.box()
        box.label(text="Import Settings", icon='IMPORT')
        box.prop(self, "import_materials_default")
        box.label(text="Placement options available in sidebar panel", icon='INFO')

        # Export section
        box = layout.box()
        box.label(text="Export Settings", icon='EXPORT')
        box.prop(self, "create_blend_backup_default")
        box.prop(self, "auto_generate_thumbnail")
        box.prop(self, "thumbnail_size")

        # Naming section
        box = layout.box()
        box.label(text="Asset Naming", icon='SORTALPHA')
        box.prop(self, "use_auto_naming")
        box.prop(self, "validate_names")

        if self.use_auto_naming:
            col = box.column(align=True)
            col.label(text="Prefixes:")
            row = col.row(align=True)
            row.prop(self, "prefix_model", text="Model")
            row.prop(self, "prefix_rig", text="Rig")
            row = col.row(align=True)
            row.prop(self, "prefix_material", text="Material")
            row.prop(self, "prefix_prop", text="Prop")
            row = col.row(align=True)
            row.prop(self, "prefix_character", text="Character")

        # UI section
        box = layout.box()
        box.label(text="Display Settings", icon='WINDOW')
        box.prop(self, "show_polygon_count")
        box.prop(self, "list_display_mode")

        # Desktop App section
        box = layout.box()
        box.label(text="Desktop Application", icon='WINDOW')
        box.prop(self, "launch_mode")

        if self.launch_mode == 'PRODUCTION':
            box.prop(self, "app_executable_path")
            if not self.app_executable_path:
                box.label(text="Set path to UAL.exe or run.bat", icon='INFO')
        else:
            box.prop(self, "dev_script_path")
            box.prop(self, "python_executable")
            if not self.dev_script_path:
                box.label(text="Set path to run.py", icon='INFO')


def get_preferences() -> UAL_Preferences:
    """Get addon preferences"""
    addon = bpy.context.preferences.addons.get(__package__)
    if addon:
        return addon.preferences
    return None


def get_naming_prefixes() -> dict:
    """
    Get naming prefixes from preferences

    Returns:
        Dict mapping asset_type to prefix
    """
    prefs = get_preferences()
    if prefs:
        return {
            'model': prefs.prefix_model or 'MDL',
            'rig': prefs.prefix_rig or 'RIG',
            'material': prefs.prefix_material or 'MAT',
            'prop': prefs.prefix_prop or 'PRP',
            'character': prefs.prefix_character or 'CHR',
        }
    # Defaults if preferences not available
    return {
        'model': 'MDL',
        'rig': 'RIG',
        'material': 'MAT',
        'prop': 'PRP',
        'character': 'CHR',
    }


# Registration
def register():
    bpy.utils.register_class(UAL_Preferences)


def unregister():
    bpy.utils.unregister_class(UAL_Preferences)


__all__ = ['UAL_Preferences', 'get_preferences', 'get_naming_prefixes', 'register', 'unregister']
