"""
Blender operators for Universal Library

Contains operators for importing/exporting USD assets and queue handling.
"""

from .export_to_library import (
    UAL_OT_export_to_library,
    UAL_OT_export_material,
)
from .export_collection import (
    UAL_OT_export_collection,
)
from .export_scene import (
    UAL_OT_export_scene,
)
from .import_from_library import (
    UAL_OT_import_from_library,
    UAL_OT_browse_library,
    UAL_OT_refresh_library,
)
from .queue_handler import (
    UAL_OT_check_import_queue,
    UAL_OT_start_queue_listener,
    UAL_OT_stop_queue_listener,
)
from .export_presets import (
    UAL_OT_save_export_preset,
    UAL_OT_load_export_preset,
    UAL_OT_delete_export_preset,
    UAL_MT_export_presets,
)
from .version_history import (
    UAL_VersionItem,
    UAL_UL_version_list,
    UAL_OT_show_version_history,
    UAL_OT_import_version,
)
from .viewport_overlay import (
    UAL_OT_toggle_asset_overlay,
    UAL_OT_refresh_overlay,
)
from .capture_screenshot import (
    UL_OT_capture_review_screenshot,
)
from .material_preview import (
    UAL_OT_open_material_preview,
    UAL_OT_close_material_preview,
    UAL_OT_render_material_preview,
)
from .reload_libraries import (
    UAL_OT_reload_current_assets,
    UAL_OT_reload_all_libraries,
    UAL_OT_list_linked_libraries,
)
from .asset_switcher import (
    UAL_OT_switch_version,
    UAL_OT_switch_variant,
    UAL_OT_refresh_switcher,
)
from .representation_swap import (
    UAL_OT_swap_representation,
    UAL_OT_swap_representation_selected,
    UAL_OT_restore_representation,
    UAL_OT_restore_representation_selected,
)
from .update_proxy import (
    UAL_OT_update_proxy,
)
from .update_thumbnail import (
    UAL_OT_update_thumbnail,
    UAL_OT_toggle_thumbnail_helper,
)

# For registration
from . import export_to_library
from . import export_collection
from . import export_scene
from . import import_from_library
from . import queue_handler
from . import export_presets
from . import version_history
from . import viewport_overlay
from . import capture_screenshot
from . import material_preview
from . import reload_libraries
from . import asset_switcher
from . import representation_swap
from . import update_proxy
from . import update_thumbnail


def register():
    export_to_library.register()
    export_collection.register()
    export_scene.register()
    import_from_library.register()
    queue_handler.register()
    export_presets.register()
    version_history.register()
    viewport_overlay.register()
    capture_screenshot.register()
    material_preview.register()
    reload_libraries.register()
    asset_switcher.register()
    representation_swap.register()
    update_proxy.register()
    update_thumbnail.register()


def unregister():
    update_thumbnail.unregister()
    update_proxy.unregister()
    representation_swap.unregister()
    asset_switcher.unregister()
    reload_libraries.unregister()
    material_preview.unregister()
    capture_screenshot.unregister()
    viewport_overlay.unregister()
    version_history.unregister()
    export_presets.unregister()
    queue_handler.unregister()
    import_from_library.unregister()
    export_scene.unregister()
    export_collection.unregister()
    export_to_library.unregister()


__all__ = [
    'UAL_OT_export_to_library',
    'UAL_OT_export_material',
    'UAL_OT_export_collection',
    'UAL_OT_export_scene',
    'UAL_OT_import_from_library',
    'UAL_OT_browse_library',
    'UAL_OT_refresh_library',
    'UAL_OT_check_import_queue',
    'UAL_OT_start_queue_listener',
    'UAL_OT_stop_queue_listener',
    'UAL_OT_save_export_preset',
    'UAL_OT_load_export_preset',
    'UAL_OT_delete_export_preset',
    'UAL_MT_export_presets',
    'UAL_VersionItem',
    'UAL_UL_version_list',
    'UAL_OT_show_version_history',
    'UAL_OT_import_version',
    'UAL_OT_toggle_asset_overlay',
    'UAL_OT_refresh_overlay',
    'UL_OT_capture_review_screenshot',
    'UAL_OT_open_material_preview',
    'UAL_OT_close_material_preview',
    'UAL_OT_render_material_preview',
    'UAL_OT_reload_current_assets',
    'UAL_OT_reload_all_libraries',
    'UAL_OT_list_linked_libraries',
    'UAL_OT_switch_version',
    'UAL_OT_switch_variant',
    'UAL_OT_refresh_switcher',
    'UAL_OT_swap_representation',
    'UAL_OT_swap_representation_selected',
    'UAL_OT_restore_representation',
    'UAL_OT_restore_representation_selected',
    'UAL_OT_update_proxy',
    'UAL_OT_update_thumbnail',
    'UAL_OT_toggle_thumbnail_helper',
    'register',
    'unregister',
]
