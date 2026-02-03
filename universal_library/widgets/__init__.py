"""
UI widgets for Universal Library

Contains all UI components.
"""

from .header_toolbar import HeaderToolbar
from .folder_tree import FolderTree
from .metadata_panel import MetadataPanel
from .status_bar import StatusBar
from .bulk_edit_toolbar import BulkEditToolbar
from .main_window import MainWindow

# Controllers
from .controllers import BulkEditController

# Settings
from .settings import SettingsDialog, StorageTab, BlenderTab, AppearanceTab

# Dialogs
from .dialogs import ScanProgressDialog, AboutDialog, VersionHistoryDialog, AssetHistoryDialog, show_asset_history_dialog

__all__ = [
    # Core widgets
    'HeaderToolbar',
    'FolderTree',
    'MetadataPanel',
    'StatusBar',
    'BulkEditToolbar',
    'MainWindow',
    # Controllers
    'BulkEditController',
    # Settings
    'SettingsDialog',
    'StorageTab',
    'BlenderTab',
    'AppearanceTab',
    # Dialogs
    'ScanProgressDialog',
    'AboutDialog',
    'VersionHistoryDialog',
    'AssetHistoryDialog',
    'show_asset_history_dialog',
]
