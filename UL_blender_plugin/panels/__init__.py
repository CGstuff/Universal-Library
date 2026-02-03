"""
Blender UI panels for Universal Library

Contains sidebar panels for export and settings.
"""

from .library_panel import (
    UAL_PT_main_panel,
    UAL_PT_export_panel,
    UAL_PT_settings_panel,
)
from .asset_switcher_panel import (
    UAL_PT_asset_switcher_panel,
)

from . import library_panel
from . import asset_switcher_panel


def register():
    library_panel.register()
    asset_switcher_panel.register()


def unregister():
    asset_switcher_panel.unregister()
    library_panel.unregister()


__all__ = [
    'UAL_PT_main_panel',
    'UAL_PT_export_panel',
    'UAL_PT_settings_panel',
    'UAL_PT_asset_switcher_panel',
    'register',
    'unregister',
]
