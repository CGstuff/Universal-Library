"""
Utility functions for Blender addon

Contains helpers for USD conversion, library connection, material handling,
queue management, naming, and common Blender operations.
"""

# Core utilities
from .library_connection import (
    LibraryConnection,
    get_library_connection,
    set_library_path
)
from .material_converter import (
    MaterialConverter,
    get_material_converter
)
from .queue_client import (
    QueueClient,
    get_queue_client
)
from .naming_utils import (
    AssetNamer,
    get_asset_namer,
    set_custom_prefixes,
    DEFAULT_PREFIXES,
    DEFAULT_PATTERNS
)

# Blender helpers
from .blender_helpers import (
    find_3d_viewport,
    get_root_objects,
    apply_location_to_roots,
    apply_scale_to_roots,
    select_objects,
    get_cursor_location,
)

# Metadata handling
from .metadata_handler import (
    store_ual_metadata,
    store_ual_metadata_from_dict,
    read_ual_metadata,
    has_ual_metadata,
    clear_ual_metadata,
    store_metadata_on_objects,
    get_ual_objects_in_scene,
    detect_link_mode,
    UAL_LINK_MODE,
)

# Context managers
from .context_managers import (
    render_settings,
    viewport_overlays,
    preserve_selection,
    ObjectImportTracker,
    object_import_tracker,
    cycles_settings,
    preserve_viewport_state,
)

# Decorators
from .decorators import (
    require_library_connection,
    handle_errors,
    require_selection,
    log_execution,
    with_library,
)

# Import helpers
from .import_helpers import (
    import_blend_file,
    import_blend_as_instance,
    import_usd_file,
    import_material_from_blend,
    import_material_from_usd,
    import_asset,
)

# Widget helpers (rig import cleanup)
from .widget_helpers import (
    find_widget_objects,
    find_widget_objects_by_name,
    hide_linked_widgets,
    hide_widget_collections,
    hide_override_widgets,
    register_handlers as register_widget_handlers,
    unregister_handlers as unregister_widget_handlers,
)

# Thumbnail generation
from .thumbnail_generator import (
    ThumbnailGenerator,
    generate_thumbnail,
)

# Viewport capture (shared thumbnail utilities)
from .viewport_capture import (
    get_3d_viewport,
    get_objects_bbox_3d,
    bbox_to_screen,
    make_square_bbox,
    is_cycles_rendered_view,
    create_placeholder_thumbnail,
    capture_viewport_thumbnail,
    capture_collection_thumbnail,
    capture_scene_thumbnail,
)

# Metadata collection (extended metadata by asset type)
from .metadata_collector import (
    collect_mesh_metadata,
    collect_rig_metadata,
    collect_animation_metadata,
    collect_material_metadata,
    collect_light_metadata,
    collect_camera_metadata,
    collect_collection_metadata,
    collect_all_metadata,
)

# Constants (mirrors desktop app protocol/constants.py and config.py)
from .constants import (
    QUEUE_DIR_NAME,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    DEFAULT_VARIANT_NAME,
    DEFAULT_VERSION_LABEL,
    META_FOLDER,
    LIBRARY_FOLDER,
    ARCHIVE_FOLDER,
    REVIEWS_FOLDER,
    CACHE_FOLDER,
    DATABASE_NAME,
    ASSET_TYPE_FOLDERS,
    get_type_folder,
)

__all__ = [
    # Core
    'LibraryConnection',
    'get_library_connection',
    'set_library_path',
    'MaterialConverter',
    'get_material_converter',
    'QueueClient',
    'get_queue_client',
    'AssetNamer',
    'get_asset_namer',
    'set_custom_prefixes',
    'DEFAULT_PREFIXES',
    'DEFAULT_PATTERNS',
    # Blender helpers
    'find_3d_viewport',
    'get_root_objects',
    'apply_location_to_roots',
    'apply_scale_to_roots',
    'select_objects',
    'get_cursor_location',
    # Metadata
    'store_ual_metadata',
    'store_ual_metadata_from_dict',
    'read_ual_metadata',
    'has_ual_metadata',
    'clear_ual_metadata',
    'store_metadata_on_objects',
    'get_ual_objects_in_scene',
    'detect_link_mode',
    'UAL_LINK_MODE',
    # Context managers
    'render_settings',
    'viewport_overlays',
    'preserve_selection',
    'ObjectImportTracker',
    'object_import_tracker',
    'cycles_settings',
    'preserve_viewport_state',
    # Decorators
    'require_library_connection',
    'handle_errors',
    'require_selection',
    'log_execution',
    'with_library',
    # Import helpers
    'import_blend_file',
    'import_blend_as_instance',
    'import_usd_file',
    'import_material_from_blend',
    'import_material_from_usd',
    'import_asset',
    # Widget helpers
    'find_widget_objects',
    'find_widget_objects_by_name',
    'hide_linked_widgets',
    'hide_widget_collections',
    'hide_override_widgets',
    'register_widget_handlers',
    'unregister_widget_handlers',
    # Thumbnail
    'ThumbnailGenerator',
    'generate_thumbnail',
    # Viewport capture
    'get_3d_viewport',
    'get_objects_bbox_3d',
    'bbox_to_screen',
    'make_square_bbox',
    'is_cycles_rendered_view',
    'create_placeholder_thumbnail',
    'capture_viewport_thumbnail',
    'capture_collection_thumbnail',
    'capture_scene_thumbnail',
    # Metadata collection
    'collect_mesh_metadata',
    'collect_rig_metadata',
    'collect_animation_metadata',
    'collect_material_metadata',
    'collect_light_metadata',
    'collect_camera_metadata',
    'collect_collection_metadata',
    'collect_all_metadata',
    # Constants
    'QUEUE_DIR_NAME',
    'STATUS_PENDING',
    'STATUS_PROCESSING',
    'STATUS_COMPLETED',
    'STATUS_FAILED',
    'DEFAULT_VARIANT_NAME',
    'DEFAULT_VERSION_LABEL',
    'META_FOLDER',
    'LIBRARY_FOLDER',
    'ARCHIVE_FOLDER',
    'REVIEWS_FOLDER',
    'CACHE_FOLDER',
    'DATABASE_NAME',
    'ASSET_TYPE_FOLDERS',
    'get_type_folder',
]
