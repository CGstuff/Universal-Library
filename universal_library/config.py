"""
Configuration for Universal Library (UL)

Centralized app configuration with sensible defaults.
Pattern: Single source of truth for all settings.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Union


class Config:
    """
    Application configuration

    Features:
    - App metadata
    - Path configuration (single storage location with hidden .assetlibrary folder)
    - Performance settings
    - UI defaults
    """

    # ==================== APP METADATA ====================
    APP_NAME = "Universal Library"

    # Version: read from version.txt (injected by build system) or use fallback
    _version_file = Path(__file__).parent / "version.txt"
    if _version_file.exists():
        APP_VERSION = _version_file.read_text().strip().lstrip('v')
    else:
        APP_VERSION = "1.0.0"  # Dev/fallback version

    APP_AUTHOR = "CGstuff"

    # ==================== PATHS ====================
    APP_ROOT: Path = Path(__file__).parent
    LIBRARY_CONFIG_FILE = "library_path.txt"
    BLENDER_SETTINGS_FILE = "blender_settings.json"

    # New storage structure folder names
    LIBRARY_FOLDER = "library"      # Active/latest versions
    ARCHIVE_FOLDER = "_archive"     # All previous versions (cold storage)
    REVIEWS_FOLDER = "reviews"      # Review screenshots and drawovers
    CACHE_FOLDER = "cache"          # Generated thumbnails, previews
    META_FOLDER = ".meta"           # Databases and config (hidden)

    # Current reference proxy files (for auto-updating links)
    CURRENT_REFERENCE_SUFFIX = ".current"  # e.g., Sword.current.blend

    # Asset type to folder mapping - easy to extend
    ASSET_TYPE_FOLDERS = {
        # Current types
        'mesh': 'meshes',
        'material': 'materials',
        'rig': 'rigs',
        'light': 'lights',
        'camera': 'cameras',
        'collection': 'collections',
        'grease_pencil': 'grease_pencils',
        'curve': 'curves',
        'scene': 'scenes',
        # Future types (add as needed)
        'texture': 'textures',
        'geonode': 'geonodes',
        'shader': 'shaders',
        'hdri': 'hdris',
        'preset': 'presets',
        # Fallback
        'other': 'other',
    }

    # Active asset types (excludes future/fallback types)
    ASSET_TYPES = ['mesh', 'material', 'rig', 'light', 'camera', 'collection', 'grease_pencil', 'curve', 'scene']

    @classmethod
    def get_type_folder(cls, asset_type: str) -> str:
        """
        Get folder name for asset type.

        Args:
            asset_type: Asset type string (mesh, material, rig, etc.)

        Returns:
            Folder name string. Returns 'other' for unknown types.
        """
        return cls.ASSET_TYPE_FOLDERS.get(asset_type, 'other')

    # Database names (inside META_FOLDER)
    DEFAULT_DB_NAME = "database.db"
    REVIEWS_DB_NAME = "reviews.db"

    # Legacy - keep for migration
    DB_FOLDER_NAME = ".assetlibrary"  # Old hidden folder name

    @classmethod
    def get_user_data_dir(cls) -> Path:
        """Get user config directory in OS AppData.

        Portable mode: if portable.txt exists next to the app root,
        falls back to a local data/ folder for USB-stick deployments.
        """
        import sys

        # Portable mode: if portable.txt exists next to exe, use local data/
        portable_marker = cls.APP_ROOT.parent / 'portable.txt'
        if portable_marker.exists():
            user_dir = cls.APP_ROOT.parent / 'data'
            user_dir.mkdir(parents=True, exist_ok=True)
            return user_dir

        # OS-specific AppData
        if sys.platform == 'win32':
            base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
        elif sys.platform == 'darwin':
            base = Path.home() / 'Library' / 'Application Support'
        else:
            base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))

        user_dir = base / 'UniversalLibrary'
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    @classmethod
    def get_library_config_path(cls) -> Path:
        """Get library path configuration file"""
        return cls.get_user_data_dir() / cls.LIBRARY_CONFIG_FILE

    @classmethod
    def load_library_path(cls) -> Optional[Path]:
        """
        Load saved library/storage path from config file

        Returns:
            Path: Storage path if configured and exists, None otherwise
        """
        config_file = cls.get_library_config_path()

        # Migrate from legacy data/ folder if AppData config doesn't exist yet
        if not config_file.exists():
            cls._migrate_from_legacy_data_dir()

        if config_file.exists():
            try:
                path_str = config_file.read_text(encoding='utf-8').strip()
                if path_str and Path(path_str).exists():
                    return Path(path_str)
            except Exception:
                pass

        # Default: check if 'storage' folder exists in app directory
        default_storage = cls.APP_ROOT.parent / 'storage'
        if default_storage.exists():
            cls.save_library_path(default_storage)
            return default_storage

        return None

    @classmethod
    def save_library_path(cls, path: Union[str, Path]) -> bool:
        """
        Save library/storage path to config file

        Args:
            path: Path to asset storage folder

        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            config_file = cls.get_library_config_path()
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(str(path), encoding='utf-8')
            return True
        except Exception:
            return False

    @classmethod
    def clear_library_path(cls) -> bool:
        """Clear the saved library path"""
        try:
            config_file = cls.get_library_config_path()
            if config_file.exists():
                config_file.unlink()
            return True
        except Exception:
            return False

    @classmethod
    def _migrate_from_legacy_data_dir(cls):
        """One-time migration from repo-relative data/ to AppData."""
        legacy_dir = cls.APP_ROOT.parent / 'data'
        if not legacy_dir.exists():
            return

        appdata_dir = cls.get_user_data_dir()

        # Migrate library_path.txt
        legacy_config = legacy_dir / cls.LIBRARY_CONFIG_FILE
        new_config = appdata_dir / cls.LIBRARY_CONFIG_FILE
        if legacy_config.exists() and not new_config.exists():
            shutil.copy2(legacy_config, new_config)

        # Migrate blender_settings.json
        legacy_blender = legacy_dir / cls.BLENDER_SETTINGS_FILE
        new_blender = appdata_dir / cls.BLENDER_SETTINGS_FILE
        if legacy_blender.exists() and not new_blender.exists():
            shutil.copy2(legacy_blender, new_blender)

    @classmethod
    def get_blender_settings_file(cls) -> Path:
        """Get path to blender settings config file."""
        return cls.get_user_data_dir() / cls.BLENDER_SETTINGS_FILE

    @classmethod
    def load_blender_settings(cls) -> dict:
        """Load Blender integration settings from config file."""
        settings_file = cls.get_blender_settings_file()
        if settings_file.exists():
            try:
                import json
                return json.loads(settings_file.read_text(encoding='utf-8'))
            except Exception:
                pass
        return {}

    @classmethod
    def save_blender_settings(cls, settings: dict) -> bool:
        """Save Blender integration settings to config file."""
        try:
            import json
            settings_file = cls.get_blender_settings_file()
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            settings_file.write_text(
                json.dumps(settings, indent=2),
                encoding='utf-8'
            )
            return True
        except Exception:
            return False

    @classmethod
    def get_meta_folder(cls) -> Path:
        """Get the .meta folder path (inside storage root)"""
        library_path = cls.load_library_path()
        if library_path and library_path.exists():
            meta_folder = library_path / cls.META_FOLDER
            meta_folder.mkdir(parents=True, exist_ok=True)
            return meta_folder
        else:
            # Fallback to user data dir if no storage configured
            meta_folder = cls.get_user_data_dir() / cls.META_FOLDER
            meta_folder.mkdir(parents=True, exist_ok=True)
            return meta_folder

    @classmethod
    def get_database_folder(cls) -> Path:
        """Alias for get_meta_folder (compatibility)"""
        return cls.get_meta_folder()

    @classmethod
    def get_database_path(cls) -> Path:
        """Get full path to database file (in .meta folder)"""
        return cls.get_meta_folder() / cls.DEFAULT_DB_NAME

    @classmethod
    def get_reviews_database_path(cls) -> Path:
        """Get full path to reviews database file (in .meta folder)"""
        return cls.get_meta_folder() / cls.REVIEWS_DB_NAME

    @classmethod
    def get_cache_directory(cls) -> Path:
        """Get cache directory path (inside storage root)"""
        library_path = cls.load_library_path()
        if library_path and library_path.exists():
            cache_dir = library_path / cls.CACHE_FOLDER
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir
        else:
            cache_dir = cls.get_user_data_dir() / cls.CACHE_FOLDER
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir

    @classmethod
    def get_thumbnails_cache_directory(cls) -> Path:
        """Get thumbnails cache directory"""
        cache_dir = cls.get_cache_directory() / 'thumbnails'
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    @classmethod
    def get_logs_directory(cls) -> Path:
        """Get logs directory path (inside .meta folder)"""
        logs_dir = cls.get_meta_folder() / 'logs'
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    # ==================== LIBRARY PATHS (NEW STRUCTURE) ====================

    @classmethod
    def get_library_folder(cls) -> Path:
        """Get the library folder path (active/latest versions)"""
        library_path = cls.load_library_path()
        if library_path and library_path.exists():
            lib_dir = library_path / cls.LIBRARY_FOLDER
            lib_dir.mkdir(parents=True, exist_ok=True)
            return lib_dir
        raise ValueError("Library path not configured")

    @classmethod
    def get_archive_folder(cls) -> Path:
        """Get the archive folder path (all versions/cold storage)"""
        library_path = cls.load_library_path()
        if library_path and library_path.exists():
            archive_dir = library_path / cls.ARCHIVE_FOLDER
            archive_dir.mkdir(parents=True, exist_ok=True)
            return archive_dir
        raise ValueError("Library path not configured")

    @classmethod
    def get_reviews_folder(cls) -> Path:
        """Get the reviews folder path (screenshots, drawovers)"""
        library_path = cls.load_library_path()
        if library_path and library_path.exists():
            reviews_dir = library_path / cls.REVIEWS_FOLDER
            reviews_dir.mkdir(parents=True, exist_ok=True)
            return reviews_dir
        raise ValueError("Library path not configured")

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Sanitize asset name for use in folder/file names"""
        import re
        # Replace invalid characters with underscore
        safe = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Remove leading/trailing spaces and dots
        safe = safe.strip(' .')
        # Collapse multiple underscores
        safe = re.sub(r'_+', '_', safe)
        return safe or 'unnamed'

    @classmethod
    def get_family_folder_name(cls, asset_id: str, asset_name: str) -> str:
        """
        Generate family folder name - human readable, no UUID.

        Industry standard: UUIDs live in database, folders are human-readable.

        Args:
            asset_id: The asset family UUID (unused in folder name, kept for API compatibility)
            asset_name: Human-readable asset name

        Returns:
            Folder name string (just the sanitized asset name)
        """
        return cls.sanitize_filename(asset_name)

    @classmethod
    def get_asset_library_path(cls, asset_id: str, asset_name: str, variant_name: str,
                               asset_type: str = 'other') -> Path:
        """
        Get path to active/latest version of an asset variant

        Args:
            asset_id: Asset family UUID
            asset_name: Asset name
            variant_name: Variant name (e.g., 'Base', 'monkey_blue')
            asset_type: Asset type for folder organization

        Returns:
            Path to library/{type}/{name}/{variant}/
        """
        type_folder = cls.get_type_folder(asset_type)
        family_folder = cls.get_family_folder_name(asset_id, asset_name)
        return cls.get_library_folder() / type_folder / family_folder / variant_name

    @classmethod
    def get_asset_archive_path(cls, asset_id: str, asset_name: str, variant_name: str,
                               version_label: str, asset_type: str = 'other') -> Path:
        """
        Get path to archived version of an asset

        Args:
            asset_id: Asset family UUID
            asset_name: Asset name
            variant_name: Variant name
            version_label: Version like 'v001'
            asset_type: Asset type for folder organization

        Returns:
            Path to _archive/{type}/{name}/{variant}/{version}/
        """
        type_folder = cls.get_type_folder(asset_type)
        family_folder = cls.get_family_folder_name(asset_id, asset_name)
        return cls.get_archive_folder() / type_folder / family_folder / variant_name / version_label

    @classmethod
    def get_asset_reviews_path(cls, asset_id: str, asset_name: str, variant_name: str,
                               version_label: str, asset_type: str = 'other') -> Path:
        """
        Get path to review data for an asset version

        Args:
            asset_id: Asset family UUID
            asset_name: Asset name
            variant_name: Variant name
            version_label: Version like 'v001'
            asset_type: Asset type for folder organization

        Returns:
            Path to reviews/{type}/{name}/{variant}/{version}/
        """
        type_folder = cls.get_type_folder(asset_type)
        family_folder = cls.get_family_folder_name(asset_id, asset_name)
        return cls.get_reviews_folder() / type_folder / family_folder / variant_name / version_label

    # ==================== RETIRED ASSETS ====================
    RETIRED_FOLDER = "_retired"  # Folder for retired assets

    @classmethod
    def get_retired_folder(cls) -> Path:
        """Get the _retired folder path in storage root."""
        library_path = cls.load_library_path()
        if library_path and library_path.exists():
            retired_dir = library_path / cls.RETIRED_FOLDER
            retired_dir.mkdir(parents=True, exist_ok=True)
            return retired_dir
        raise ValueError("Library path not configured")

    @classmethod
    def get_retired_asset_path(cls, asset_type: str, asset_name: str,
                                variant_name: str) -> Path:
        """
        Get path for a retired asset's folder.

        Args:
            asset_type: Asset type (mesh, material, etc.)
            asset_name: Asset name
            variant_name: Variant name (e.g., 'Base')

        Returns:
            Path to _retired/{type}/{name}/{variant}/
        """
        type_folder = cls.get_type_folder(asset_type)
        family_folder = cls.sanitize_filename(asset_name)
        return cls.get_retired_folder() / type_folder / family_folder / variant_name

    # ==================== LEGACY COLD STORAGE (for migration) ====================
    COLD_STORAGE_FOLDER = '_cold_storage'

    @classmethod
    def get_cold_storage_path(cls) -> Path:
        """Legacy: Get cold storage directory (use get_archive_folder instead)"""
        library_path = cls.load_library_path()
        if library_path and library_path.exists():
            cold_dir = library_path / cls.COLD_STORAGE_FOLDER
            return cold_dir
        return cls.get_user_data_dir() / cls.COLD_STORAGE_FOLDER

    @classmethod
    def get_cold_storage_asset_path(cls, version_group_id: str, version_label: str) -> Path:
        """Legacy: Get cold storage path for asset version"""
        cold_dir = cls.get_cold_storage_path() / version_group_id / version_label
        cold_dir.mkdir(parents=True, exist_ok=True)
        return cold_dir

    # Aliases for compatibility
    @classmethod
    def get_data_directory(cls) -> Path:
        """Alias for get_meta_folder (compatibility)"""
        return cls.get_meta_folder()

    @classmethod
    def get_cache_dir(cls) -> Path:
        """Alias for get_cache_directory"""
        return cls.get_cache_directory()

    @classmethod
    def is_first_run(cls) -> bool:
        """Check if this is the first time the application is running"""
        return cls.load_library_path() is None

    # ==================== PERFORMANCE ====================
    # Thumbnail loading
    THUMBNAIL_THREAD_COUNT = 4
    THUMBNAIL_CACHE_SIZE_MB = 100
    DEFAULT_THUMBNAIL_SIZE = 300

    # Pixmap cache (in KB for Qt)
    PIXMAP_CACHE_SIZE_KB = 512 * 1024  # 512 MB

    # Model updates
    BATCH_UPDATE_SIZE = 50
    SEARCH_DEBOUNCE_MS = 300

    # ==================== UI DEFAULTS ====================
    # Window
    DEFAULT_WINDOW_WIDTH = 1400
    DEFAULT_WINDOW_HEIGHT = 900
    MIN_WINDOW_WIDTH = 800
    MIN_WINDOW_HEIGHT = 600

    # Card sizes
    DEFAULT_CARD_SIZE = 200
    MIN_CARD_SIZE = 100
    MAX_CARD_SIZE = 400
    CARD_SIZE_STEP = 20

    # List mode
    LIST_ROW_HEIGHT = 56

    # Tree mode
    TREE_ROW_HEIGHT = 72        # Parent (base) row height
    TREE_CHILD_ROW_HEIGHT = 60  # Variant child row height
    TREE_INDENT = 30            # Indentation for children

    # Splitter ratios
    DEFAULT_LEFT_PANEL_WIDTH = 250
    DEFAULT_RIGHT_PANEL_WIDTH = 300
    MIN_PANEL_WIDTH = 150
    DEFAULT_SPLITTER_SIZES = [250, 800, 300]  # left, center, right

    # ==================== ASSET TYPES ====================
    # Data types only - semantic categories (prop, character, vehicle, etc.)
    # should be handled via tags or description
    # Note: Animation/actions are handled by Action Library, not here
    ASSET_TYPES = [
        'mesh',
        'material',
        'rig',
        'light',
        'camera',
        'collection',
        'grease_pencil',
        'curve',
        'scene',
        'other'
    ]

    # Asset type to category mapping for context-sensitive metadata display
    # Categories: mesh, material, rig, light, camera, collection
    ASSET_TYPE_CATEGORY = {
        'mesh': 'mesh',
        'material': 'material',
        'rig': 'rig',
        'light': 'light',
        'camera': 'camera',
        'collection': 'collection',
        'grease_pencil': 'grease_pencil',
        'curve': 'curve',
        'scene': 'scene',
        'other': 'mesh',  # Default to mesh category for 'other'
    }

    # Asset type colors (for badges)
    ASSET_TYPE_COLORS = {
        'mesh': '#4CAF50',
        'material': '#9C27B0',
        'rig': '#FF9800',
        'light': '#FFD700',
        'camera': '#87CEEB',
        'collection': '#00ACC1',
        'grease_pencil': '#66BB6A',
        'curve': '#26C6DA',
        'scene': '#AB47BC',
        'other': '#9E9E9E',
    }

    # ==================== IMPORT OPTIONS ====================
    # Currently Blender-centric - USD support commented out for future
    # IMPORT_METHODS = ['USD', 'BLEND']  # USD temporarily disabled
    IMPORT_METHODS = ['BLEND']  # Blender-native workflow
    DEFAULT_IMPORT_METHOD = 'BLEND'

    LINK_MODES = ['LINK', 'INSTANCE']
    DEFAULT_LINK_MODE = 'INSTANCE'

    # ==================== VIRTUAL FOLDERS ====================
    VIRTUAL_FOLDER_ALL = -1
    VIRTUAL_FOLDER_FAVORITES = -2
    VIRTUAL_FOLDER_RECENT = -3
    VIRTUAL_FOLDER_COLD_STORAGE = -4
    VIRTUAL_FOLDER_BASE = -5
    VIRTUAL_FOLDER_VARIANTS = -6
    VIRTUAL_FOLDER_NEEDS_REVIEW = -7
    VIRTUAL_FOLDER_IN_REVIEW = -8
    VIRTUAL_FOLDER_IN_PROGRESS = -9
    VIRTUAL_FOLDER_APPROVED = -10
    VIRTUAL_FOLDER_FINAL = -11

    VIRTUAL_FOLDERS = {
        VIRTUAL_FOLDER_ALL: "All Assets",
        VIRTUAL_FOLDER_BASE: "Base",
        VIRTUAL_FOLDER_VARIANTS: "Variants",
        VIRTUAL_FOLDER_FAVORITES: "Favorites",
        VIRTUAL_FOLDER_RECENT: "Recent",
        VIRTUAL_FOLDER_COLD_STORAGE: "Cold Storage",
        VIRTUAL_FOLDER_NEEDS_REVIEW: "Needs Review",
        VIRTUAL_FOLDER_IN_REVIEW: "In Review",
        VIRTUAL_FOLDER_IN_PROGRESS: "In Progress",
        VIRTUAL_FOLDER_APPROVED: "Approved",
        VIRTUAL_FOLDER_FINAL: "Final",
    }

    # Review workflow virtual folder IDs (for grouping in folder tree)
    REVIEW_VIRTUAL_FOLDERS = [
        VIRTUAL_FOLDER_NEEDS_REVIEW,
        VIRTUAL_FOLDER_IN_REVIEW,
        VIRTUAL_FOLDER_IN_PROGRESS,
        VIRTUAL_FOLDER_APPROVED,
        VIRTUAL_FOLDER_FINAL,
    ]

    # ==================== REPRESENTATION TYPES ====================
    REPRESENTATION_TYPES = {
        'none': {'order': 0, 'color': None, 'label': 'None'},  # No badge shown
        'model': {'order': 1, 'color': '#4CAF50', 'label': 'Model'},
        'lookdev': {'order': 2, 'color': '#9C27B0', 'label': 'Lookdev'},
        'rig': {'order': 3, 'color': '#FF9800', 'label': 'Rig'},
        'final': {'order': 4, 'color': '#2196F3', 'label': 'Final'},
    }

    # ==================== VARIANT SYSTEM ====================
    DEFAULT_VARIANT_NAME = 'Base'  # Default variant name for new assets

    # ==================== LIFECYCLE STATUS ====================
    # 'none' = no status (for solo artists using as simple asset browser)
    # Other statuses = pipeline workflow (for studios)
    LIFECYCLE_STATUSES = {
        'none': {'color': None, 'label': 'None'},  # No badge displayed
        'wip': {'color': '#FF9800', 'label': 'WIP'},
        'review': {'color': '#2196F3', 'label': 'In Review'},
        'approved': {'color': '#4CAF50', 'label': 'Approved'},
        'deprecated': {'color': '#F44336', 'label': 'Deprecated'},
        'archived': {'color': '#9E9E9E', 'label': 'Archived'},
    }

    # ==================== REVIEW WORKFLOW STATES ====================
    # Review state is separate from lifecycle status
    # - Lifecycle status = content maturity (WIP, Review, Approved)
    # - Review state = review workflow stage (Needs Review, In Review, Approved, Final)
    REVIEW_STATES = {
        None: {'color': None, 'label': None, 'badge': None},  # Not in review workflow
        'needs_review': {'color': '#2196F3', 'label': 'Needs Review', 'badge': 'REV'},  # Blue - awaiting lead
        'in_review': {'color': '#FF9800', 'label': 'In Review', 'badge': 'REV'},  # Orange - lead commented
        'in_progress': {'color': '#00BCD4', 'label': 'In Progress', 'badge': 'WIP'},  # Cyan - artist working on fixes
        'approved': {'color': '#4CAF50', 'label': 'Approved', 'badge': 'OK'},  # Green - all approved by lead
        'final': {'color': '#9C27B0', 'label': 'Final', 'badge': 'FNL'},  # Purple - review complete
    }

    # Note status constants (3-state workflow)
    NOTE_STATUSES = {
        'open': {'color': '#FF9800', 'label': 'Open', 'icon': 'comment'},  # Lead added, awaiting artist
        'addressed': {'color': '#00BCD4', 'label': 'Addressed', 'icon': 'check'},  # Artist fixed, awaiting lead
        'approved': {'color': '#4CAF50', 'label': 'Approved', 'icon': 'approve'},  # Lead approved
    }

    # User roles for review workflow
    # Elevated roles can trigger state transitions and mark as final
    ELEVATED_ROLES = ['lead', 'supervisor', 'admin', 'director']


# Review cycle types (presets only - no free-form to prevent inconsistency)
# Each review cycle spans multiple versions for a specific phase
# Moved outside Config class for easy module-level import
REVIEW_CYCLE_TYPES = {
    'modeling': {'label': 'Modeling', 'color': '#2196F3'},      # Blue
    'texturing': {'label': 'Texturing', 'color': '#FF9800'},    # Orange
    'rigging': {'label': 'Rigging', 'color': '#9C27B0'},        # Purple
    'lighting': {'label': 'Lighting', 'color': '#FFEB3B'},      # Yellow
    'animation': {'label': 'Animation', 'color': '#4CAF50'},    # Green
    'fx': {'label': 'FX', 'color': '#F44336'},                  # Red
    'lookdev': {'label': 'Look Dev', 'color': '#00BCD4'},       # Cyan
    'general': {'label': 'General', 'color': '#607D8B'},        # Gray - default/catch-all
}


__all__ = ['Config', 'REVIEW_CYCLE_TYPES']
