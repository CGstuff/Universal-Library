"""
MainWindow - Main application window

Pattern: QMainWindow with splitter layout
Based on animation_library architecture.
"""

import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QSplitter, QMessageBox, QStackedWidget
)
from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QCloseEvent

from ..config import Config
from ..events.event_bus import get_event_bus
from ..services.database_service import get_database_service
from ..services.control_authority import get_control_authority
from ..services.thumbnail_loader import get_thumbnail_loader
from ..services.screenshot_queue_handler import get_screenshot_queue_handler
from ..services.review_database import get_review_database
from ..services.asset_manager import get_asset_manager
from ..models.asset_list_model import AssetListModel
from ..models.asset_filter_proxy_model import AssetFilterProxyModel
from ..models.asset_tree_model import AssetTreeModel
from ..views.asset_view import AssetView
from ..views.asset_tree_view import AssetTreeView
from .header_toolbar import HeaderToolbar
from .folder_tree import FolderTree
from .metadata_panel import MetadataPanel
from .status_bar import StatusBar
from .bulk_edit_toolbar import BulkEditToolbar
from .controllers import BulkEditController


class MainWindow(QMainWindow):
    """
    Main application window

    Features:
    - 3-panel layout (folder tree, asset grid, metadata panel)
    - Splitter with persistent state
    - Header toolbar with search and controls
    - Status bar
    - Window state persistence
    - Event bus integration

    Layout:
        +------------------------------------------+
        |  HeaderToolbar                           |
        +------------------------------------------+
        | FolderTree | AssetView    | Metadata    |
        |            |              | Panel       |
        |            |              |             |
        +------------------------------------------+
        |  StatusBar                               |
        +------------------------------------------+
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Check for first run and show setup wizard
        if Config.is_first_run():
            from .dialogs.setup_wizard import SetupWizard
            from PyQt6.QtWidgets import QDialog
            wizard = SetupWizard(self)
            if wizard.exec() != QDialog.DialogCode.Accepted:
                # User cancelled setup
                sys.exit(0)

        # Services and event bus
        self._event_bus = get_event_bus()
        self._db_service = get_database_service()
        self._thumbnail_loader = get_thumbnail_loader()
        self._screenshot_queue_handler = get_screenshot_queue_handler()
        
        # Initialize control authority with database service
        self._control_authority = get_control_authority()
        self._control_authority.set_db_service(self._db_service)

        # Models
        self._asset_model = AssetListModel()
        self._proxy_model = AssetFilterProxyModel()
        self._proxy_model.setSourceModel(self._asset_model)

        # Setup window
        self._setup_window()
        self._create_widgets()
        self._create_layout()
        self._init_controllers()
        self._connect_signals()
        self._load_settings()
        self._load_assets()
        self._start_screenshot_queue_timer()

    def _setup_window(self):
        """Configure window properties"""
        self.setWindowTitle(f"{Config.APP_NAME} {Config.APP_VERSION}")
        self.setGeometry(100, 100, Config.DEFAULT_WINDOW_WIDTH, Config.DEFAULT_WINDOW_HEIGHT)

    def _create_widgets(self):
        """Create UI widgets"""

        # Header toolbar
        self._header_toolbar = HeaderToolbar()

        # Bulk edit toolbar (hidden by default)
        self._bulk_edit_toolbar = BulkEditToolbar()
        self._bulk_edit_toolbar.hide()

        # Folder tree (left panel)
        self._folder_tree = FolderTree()

        # Asset view (center panel) - grid/list modes
        self._asset_view = AssetView()
        self._asset_view.setModel(self._proxy_model)

        # Asset tree view - tree mode
        self._tree_model = AssetTreeModel()
        self._tree_view = AssetTreeView()
        self._tree_view.setModel(self._tree_model)

        # Stacked widget to swap between flat view and tree view
        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._asset_view)   # index 0: grid/list
        self._view_stack.addWidget(self._tree_view)     # index 1: tree
        self._view_stack.setCurrentIndex(0)

        # Current view mode
        self._current_view_mode = "grid"

        # Metadata panel (right panel)
        self._metadata_panel = MetadataPanel()

        # Status bar
        self._status_bar = StatusBar()

    def _create_layout(self):
        """Create window layout"""

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main vertical layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Add header toolbar
        main_layout.addWidget(self._header_toolbar)

        # Add bulk edit toolbar (hidden by default)
        main_layout.addWidget(self._bulk_edit_toolbar)

        # Create horizontal splitter for 3-panel layout
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        # Add panels to splitter
        self._splitter.addWidget(self._folder_tree)
        self._splitter.addWidget(self._view_stack)
        self._splitter.addWidget(self._metadata_panel)

        # Set initial splitter sizes
        self._splitter.setSizes(Config.DEFAULT_SPLITTER_SIZES)

        # Set stretch factors (center panel gets most space)
        self._splitter.setStretchFactor(0, 0)  # Folder tree: fixed-ish
        self._splitter.setStretchFactor(1, 1)  # Asset view: stretchy
        self._splitter.setStretchFactor(2, 0)  # Metadata: fixed-ish

        # Add splitter to layout
        main_layout.addWidget(self._splitter, 1)

        # Add status bar
        main_layout.addWidget(self._status_bar)

    def _init_controllers(self):
        """Initialize controllers for delegated functionality"""
        self._bulk_edit_ctrl = BulkEditController(
            parent=self,
            asset_view=self._asset_view,
            asset_model=self._asset_model,
            db_service=self._db_service,
            event_bus=self._event_bus,
            status_bar=self._status_bar,
            reload_assets_callback=self._load_assets
        )

    def _connect_signals(self):
        """Connect signals and slots"""

        # Folder tree selection -> filter assets
        self._folder_tree.folder_selected.connect(self._on_folder_selected)

        # Folder tree system folder (type folder) selection -> filter by asset type
        self._folder_tree.asset_type_selected.connect(self._on_type_filter_changed)

        # Folder tree physical path selection -> filter by subfolder
        self._folder_tree.physical_path_selected.connect(self._on_physical_path_filter_changed)

        # Asset view selection -> update metadata panel
        self._asset_view.selectionModel().selectionChanged.connect(
            self._on_asset_selection_changed
        )

        # Asset view double-click -> import asset
        self._asset_view.asset_double_clicked.connect(self._on_asset_double_clicked)

        # Tree view double-click -> import asset
        self._tree_view.asset_double_clicked.connect(self._on_asset_double_clicked)

        # Tree view selection -> update metadata panel
        self._tree_view.asset_selected.connect(self._on_tree_asset_selected)

        # Auto-rebuild tree when proxy model filter/sort changes
        self._proxy_model.layoutChanged.connect(self._on_proxy_layout_changed)
        self._proxy_model.modelReset.connect(self._on_proxy_layout_changed)

        # Header toolbar search -> filter assets
        self._header_toolbar.search_text_changed.connect(self._on_search_text_changed)

        # Header toolbar type filter -> filter assets
        self._header_toolbar.asset_type_filter_changed.connect(self._on_type_filter_changed)

        # Header toolbar status filter -> filter assets
        self._header_toolbar.status_filter_changed.connect(self._on_status_filter_changed)

        # Header toolbar tag filter -> filter assets
        self._header_toolbar.tag_filter_changed.connect(self._on_tag_filter_changed)

        # Header toolbar sort -> update sort
        self._header_toolbar.sort_changed.connect(self._on_sort_changed)

        # Header toolbar view mode -> update view (grid/list/tree)
        self._header_toolbar.view_mode_changed.connect(self._on_view_mode_changed)

        # Header toolbar card size -> update view
        self._header_toolbar.card_size_changed.connect(self._asset_view.set_card_size)

        # Header toolbar refresh -> reload assets
        self._header_toolbar.refresh_clicked.connect(self._on_refresh_clicked)

        # Header toolbar settings -> show settings
        self._header_toolbar.settings_clicked.connect(self._show_settings)

        # Header toolbar about -> show about dialog
        self._header_toolbar.about_clicked.connect(self._show_about)

        # Header toolbar retired assets -> show retired assets dialog
        self._header_toolbar.retired_assets_clicked.connect(self._show_retired_assets)

        # Header toolbar edit mode -> show/hide bulk edit toolbar
        self._header_toolbar.edit_mode_changed.connect(self._on_edit_mode_changed)

        # Header toolbar group by family -> update sorting
        self._header_toolbar.group_by_family_changed.connect(self._on_group_by_family_changed)

        # Bulk edit toolbar signals
        self._bulk_edit_toolbar.status_change_requested.connect(
            self._bulk_edit_ctrl.change_status
        )
        self._bulk_edit_toolbar.representation_change_requested.connect(
            self._bulk_edit_ctrl.change_representation
        )
        self._bulk_edit_toolbar.archive_selected_clicked.connect(
            self._bulk_edit_ctrl.archive_selected
        )
        self._bulk_edit_toolbar.restore_selected_clicked.connect(
            self._bulk_edit_ctrl.restore_selected
        )
        self._bulk_edit_toolbar.cold_storage_requested.connect(
            self._bulk_edit_ctrl.move_to_cold_storage
        )
        self._bulk_edit_toolbar.restore_from_cold_requested.connect(
            self._bulk_edit_ctrl.restore_from_cold_storage
        )
        self._bulk_edit_toolbar.publish_requested.connect(
            self._bulk_edit_ctrl.publish_selected
        )

        # Metadata panel edit -> edit asset (BLEND + APPEND)
        self._metadata_panel.edit_requested.connect(self._on_edit_requested)

        # Metadata panel import -> import asset
        self._metadata_panel.import_requested.connect(self._on_import_requested)

        # Metadata panel replace -> replace selected in Blender
        self._metadata_panel.replace_requested.connect(self._on_replace_requested)

        # Metadata panel tags changed -> update model and filters
        self._metadata_panel.tags_changed.connect(self._on_asset_tags_changed)

        # Metadata panel folders changed -> update model
        self._metadata_panel.folders_changed.connect(self._on_asset_folders_changed)

        # Event bus signals
        self._event_bus.status_message.connect(self._status_bar.set_status)
        self._event_bus.status_error.connect(self._status_bar.set_error)
        self._event_bus.request_toggle_favorite.connect(self._on_favorite_toggled)
        self._event_bus.request_delete_assets.connect(self._on_delete_assets_requested)
        self._event_bus.request_retire_assets.connect(self._on_retire_assets_requested)
        self._event_bus.assets_moved.connect(self._on_assets_moved)
        self._event_bus.asset_updated.connect(self._on_asset_updated)

        # Thumbnail loaded -> refresh asset data from DB (piggyback on thumbnail cache invalidation)
        self._thumbnail_loader.thumbnail_loaded.connect(self._on_thumbnail_loaded)
        # Thumbnail failed (file missing) -> also refresh, may indicate version change
        self._thumbnail_loader.thumbnail_failed.connect(self._on_thumbnail_failed)

    def _on_thumbnail_failed(self, uuid: str, error_message: str):
        """When thumbnail file is missing, refresh asset from DB (may have new version)"""
        # Use same logic as thumbnail_loaded - check for version changes
        self._on_thumbnail_loaded(uuid, None)

    def _on_thumbnail_loaded(self, uuid: str, pixmap):
        """When thumbnail reloads from disk, also refresh asset data from DB"""
        # Get old is_latest value before refresh
        old_asset = self._asset_model.get_asset_by_uuid(uuid)
        was_latest = old_asset.get('is_latest', 1) if old_asset else 1
        
        # Refresh this asset
        self._asset_model.refresh_asset(uuid)
        
        # If it was latest but now isn't, a new version was added - fetch it
        if was_latest:
            new_asset = self._asset_model.get_asset_by_uuid(uuid)
            is_now_latest = new_asset.get('is_latest', 1) if new_asset else 1
            
            if not is_now_latest and new_asset:
                # Find and add the new latest version
                version_group_id = new_asset.get('version_group_id')
                if version_group_id:
                    latest = self._db_service.get_latest_asset_version(version_group_id)
                    if latest and latest.get('uuid') != uuid:
                        # Enrich and add new version
                        latest['tags_v2'] = self._db_service.get_asset_tags(latest['uuid'])
                        latest['folders_v2'] = self._db_service.get_asset_folders(latest['uuid'])
                        self._asset_model.append_asset(latest)

    def _load_settings(self):
        """Load window and splitter settings"""
        settings = QSettings(Config.APP_AUTHOR, Config.APP_NAME)

        # Window geometry
        if settings.contains("window/geometry"):
            self.restoreGeometry(settings.value("window/geometry"))

        # Window state
        if settings.contains("window/state"):
            self.restoreState(settings.value("window/state"))

        # Splitter sizes
        if settings.contains("splitter/sizes"):
            sizes = settings.value("splitter/sizes")
            if sizes:
                try:
                    sizes = [int(s) for s in sizes]
                    self._splitter.setSizes(sizes)
                except (ValueError, TypeError):
                    self._splitter.setSizes(Config.DEFAULT_SPLITTER_SIZES)

    def _save_settings(self):
        """Save window and splitter settings"""
        settings = QSettings(Config.APP_AUTHOR, Config.APP_NAME)

        # Window geometry
        settings.setValue("window/geometry", self.saveGeometry())

        # Window state
        settings.setValue("window/state", self.saveState())

        # Splitter sizes
        settings.setValue("splitter/sizes", self._splitter.sizes())

    def _load_assets(self):
        """Load assets from database"""
        self._status_bar.set_status("Loading assets...")

        # Get all assets from database
        assets = self._db_service.get_all_assets()

        # Get review database for comment status
        review_db = get_review_database()

        # Enrich assets with tags_v2, folders_v2, and comment status
        for asset in assets:
            uuid = asset.get('uuid')
            if uuid:
                asset['tags_v2'] = self._db_service.get_asset_tags(uuid)
                asset['folders_v2'] = self._db_service.get_asset_folders(uuid)
                # Auto-migrate legacy folder_id if no folders_v2 entries
                if not asset['folders_v2'] and asset.get('folder_id'):
                    self._db_service.migrate_asset_to_multi_folder(uuid, asset['folder_id'])
                    asset['folders_v2'] = self._db_service.get_asset_folders(uuid)

                # Enrich with comment/review status
                version_label = asset.get('version_label', 'v001')
                # Pass version_group_id for cycle lookup (cycles span all versions in group)
                version_group_id = asset.get('version_group_id') or asset.get('asset_id') or uuid
                review_status = review_db.get_review_status(uuid, version_label, version_group_id)
                asset['has_unresolved_comments'] = review_status.get('unresolved_notes', 0) > 0
                asset['unresolved_comment_count'] = review_status.get('unresolved_notes', 0)
                asset['review_state'] = review_status.get('review_state')

        # Load into model
        self._asset_model.set_assets(assets)

        # Load variant counts for badge display
        variant_counts = self._db_service.get_variant_counts()
        self._asset_model.set_variant_counts(variant_counts)

        # Trigger initial sort (required for lessThan to be called)
        self._proxy_model.sort(0, Qt.SortOrder.AscendingOrder)

        # Refresh tag filter with available tags
        tags_with_counts = self._db_service.get_tags_with_counts()
        self._header_toolbar.refresh_tag_filter(tags_with_counts)

        # Update status
        count = len(assets)
        self._status_bar.set_asset_count(count)
        self._status_bar.set_status("Ready")

    def _start_screenshot_queue_timer(self):
        """Start timer to poll for Blender screenshot requests"""
        self._screenshot_queue_timer = QTimer(self)
        self._screenshot_queue_timer.timeout.connect(self._poll_screenshot_queue)
        self._screenshot_queue_timer.start(2000)  # Poll every 2 seconds

    def _poll_screenshot_queue(self):
        """Poll for and process pending screenshot requests from Blender"""
        try:
            count = self._screenshot_queue_handler.process_all_pending()
            if count > 0:
                # Show notification
                self._status_bar.set_status(
                    f"Imported {count} screenshot(s) from Blender"
                )
        except Exception as e:
            pass

    # ==================== SLOT HANDLERS ====================

    def _on_folder_selected(self, folder_id: int):
        """Handle folder selection"""

        # Reset cold storage view mode by default
        self._bulk_edit_toolbar.set_cold_storage_view_mode(False)

        if folder_id == Config.VIRTUAL_FOLDER_ALL:
            self._proxy_model.set_folder_filter(None)
            self._status_bar.set_status("All assets")
        elif folder_id == Config.VIRTUAL_FOLDER_FAVORITES:
            self._proxy_model.set_folder_filter(Config.VIRTUAL_FOLDER_FAVORITES)
            self._status_bar.set_status("Favorites")
        elif folder_id == Config.VIRTUAL_FOLDER_RECENT:
            self._proxy_model.set_folder_filter(Config.VIRTUAL_FOLDER_RECENT)
            self._status_bar.set_status("Recent")
        elif folder_id == Config.VIRTUAL_FOLDER_COLD_STORAGE:
            self._proxy_model.set_folder_filter(Config.VIRTUAL_FOLDER_COLD_STORAGE)
            self._status_bar.set_status("Cold Storage")
            # Enable restore from cold mode in bulk edit toolbar
            self._bulk_edit_toolbar.set_cold_storage_view_mode(True)
        elif folder_id == Config.VIRTUAL_FOLDER_BASE:
            self._proxy_model.set_folder_filter(Config.VIRTUAL_FOLDER_BASE)
            self._status_bar.set_status("Base Assets")
        elif folder_id == Config.VIRTUAL_FOLDER_VARIANTS:
            self._proxy_model.set_folder_filter(Config.VIRTUAL_FOLDER_VARIANTS)
            self._status_bar.set_status("Variant Assets")
        else:
            # User folder - get all child folder IDs for recursive filtering
            child_ids = self._db_service.get_descendant_folder_ids(folder_id)
            self._proxy_model.set_folder_filter(folder_id, child_ids)

            folder = self._db_service.get_folder_by_id(folder_id)
            folder_name = folder.get('name', 'Unknown') if folder else 'Unknown'
            self._status_bar.set_status(f"Folder: {folder_name}")

        # Update count
        count = self._proxy_model.rowCount()
        self._status_bar.set_asset_count(count, filtered=True)

    def _on_asset_selection_changed(self, selected, deselected):
        """Handle asset selection change"""
        selected_indexes = self._asset_view.selectionModel().selectedIndexes()

        if selected_indexes:
            # Get first selected asset
            index = selected_indexes[0]
            source_index = self._proxy_model.mapToSource(index)
            asset = self._asset_model.get_asset_at_index(source_index.row())

            if asset:
                # Update metadata panel via event bus
                self._event_bus.asset_selected.emit(asset.get('uuid', ''))

                # Update status
                name = asset.get('name', 'Unknown')
                self._status_bar.set_status(f"Selected: {name}")
        else:
            # Clear selection
            self._event_bus.asset_selected.emit('')
            self._status_bar.set_status("Ready")

    def _on_asset_double_clicked(self, uuid: str):
        """Handle asset double-click - import to Blender if quick import enabled"""
        if not self._header_toolbar.is_quick_import_enabled():
            return  # Quick import disabled, do nothing

        link_mode = self._metadata_panel.get_link_mode()
        self._import_asset(uuid, "BLEND", link_mode)

    def _on_search_text_changed(self, text: str):
        """Handle search text change"""
        self._proxy_model.set_search_text(text)

        count = self._proxy_model.rowCount()
        if text:
            self._status_bar.set_status(f"Search: '{text}'")
            self._status_bar.set_asset_count(count, filtered=True)
        else:
            self._status_bar.set_status("Ready")
            self._status_bar.set_asset_count(count)

    def _on_type_filter_changed(self, asset_type: str):
        """Handle asset type filter change"""
        if asset_type:
            self._proxy_model.set_asset_type_filter({asset_type})
        else:
            self._proxy_model.clear_asset_type_filter()

        count = self._proxy_model.rowCount()
        self._status_bar.set_asset_count(count, filtered=bool(asset_type))

    def _on_physical_path_filter_changed(self, physical_path: str):
        """Handle physical path filter change (for subfolder filtering)"""
        if physical_path:
            self._proxy_model.set_physical_path_filter(physical_path)
        else:
            self._proxy_model.clear_physical_path_filter()

        count = self._proxy_model.rowCount()
        self._status_bar.set_asset_count(count, filtered=bool(physical_path))

    def _on_status_filter_changed(self, status: str):
        """Handle status filter change"""
        if status:
            self._proxy_model.set_status_filter({status})
            self._status_bar.set_status(f"Filtered by status: {status}")
        else:
            self._proxy_model.clear_status_filter()
            self._status_bar.set_status("Ready")

        count = self._proxy_model.rowCount()
        self._status_bar.set_asset_count(count, filtered=bool(status))

    def _on_tag_filter_changed(self, tag_ids: list):
        """Handle tag filter change"""
        self._proxy_model.set_tag_id_filter(tag_ids)

        # Update status bar
        count = self._proxy_model.rowCount()
        if tag_ids:
            self._status_bar.set_asset_count(count, filtered=True)
            self._status_bar.set_status(f"Filtered by {len(tag_ids)} tag(s)")
        else:
            self._status_bar.set_asset_count(count)
            self._status_bar.set_status("Ready")

    def _on_asset_tags_changed(self, uuid: str, tag_ids: list):
        """Handle asset tags changed in metadata panel"""
        # Update the model with new tags
        tags_v2 = self._db_service.get_asset_tags(uuid)
        self._asset_model.update_asset(uuid, {'tags_v2': tags_v2})

        # Refresh tag filter dropdown (counts may have changed)
        tags_with_counts = self._db_service.get_tags_with_counts()
        self._header_toolbar.refresh_tag_filter(tags_with_counts)

        self._status_bar.set_status("Tags updated")

    def _on_asset_folders_changed(self, uuid: str, folder_ids: list):
        """Handle asset folders changed in metadata panel"""
        # Update the model with new folders
        folders_v2 = self._db_service.get_asset_folders(uuid)
        self._asset_model.update_asset(uuid, {'folders_v2': folders_v2})

        # Re-filter to reflect folder membership changes
        self._proxy_model.invalidateFilter()

        # Refresh folder tree (counts may have changed)
        self._folder_tree.refresh()

        self._status_bar.set_status("Folders updated")

    def _on_sort_changed(self, sort_by: str, sort_order: str):
        """Handle sort option change"""
        self._proxy_model.set_sort_config(sort_by, sort_order)

    def _on_refresh_clicked(self):
        """Handle refresh button click - reload assets from database"""
        self._status_bar.set_status("Refreshing...")

        # Clear thumbnail cache so updated thumbnails are reloaded from disk
        thumbnail_loader = get_thumbnail_loader()
        thumbnail_loader.clear_cache()

        # Reload assets from database
        assets = self._db_service.get_all_assets()

        # Get review database for comment status
        review_db = get_review_database()

        # Enrich assets with tags_v2, folders_v2, and comment status
        for asset in assets:
            uuid = asset.get('uuid')
            if uuid:
                asset['tags_v2'] = self._db_service.get_asset_tags(uuid)
                asset['folders_v2'] = self._db_service.get_asset_folders(uuid)

                # Enrich with comment/review status
                version_label = asset.get('version_label', 'v001')
                # Pass version_group_id for cycle lookup (cycles span all versions in group)
                version_group_id = asset.get('version_group_id') or asset.get('asset_id') or uuid
                review_status = review_db.get_review_status(uuid, version_label, version_group_id)
                asset['has_unresolved_comments'] = review_status.get('unresolved_notes', 0) > 0
                asset['unresolved_comment_count'] = review_status.get('unresolved_notes', 0)
                asset['review_state'] = review_status.get('review_state')

        self._asset_model.set_assets(assets)

        # Refresh tag filter with available tags
        tags_with_counts = self._db_service.get_tags_with_counts()
        self._header_toolbar.refresh_tag_filter(tags_with_counts)

        # Refresh folder tree
        self._folder_tree.refresh()

        # Update status
        count = len(assets)
        self._status_bar.set_asset_count(count)
        self._status_bar.set_status(f"Refreshed: {count} assets")

    def _on_edit_mode_changed(self, enabled: bool):
        """Handle edit mode toggle"""
        if enabled:
            self._bulk_edit_toolbar.show()
        else:
            self._bulk_edit_toolbar.hide()

        # Update asset view to show/hide checkboxes
        self._asset_view.set_edit_mode(enabled)

    def _on_group_by_family_changed(self, group: bool):
        """Handle group by family toggle"""
        self._proxy_model.set_group_by_family(group)

        if group:
            self._status_bar.set_status("Grouped by asset family")
        else:
            self._status_bar.set_status("Ready")

    def _on_view_mode_changed(self, mode: str):
        """Handle view mode switch between grid, list, and tree"""
        # Capture selected UUID before switching
        selected_uuid = None
        if self._current_view_mode == "tree":
            selected_uuid = self._tree_view.get_selected_uuid()
        else:
            uuids = self._asset_view.get_selected_uuids()
            if uuids:
                selected_uuid = uuids[0]

        self._current_view_mode = mode

        if mode in ("grid", "list"):
            # Show flat view
            self._asset_view.set_view_mode(mode)
            self._view_stack.setCurrentIndex(0)

            # Restore selection
            if selected_uuid:
                self._asset_view.select_asset(selected_uuid)
        elif mode == "tree":
            # Build/refresh tree and show tree view
            self._rebuild_tree_model()
            self._view_stack.setCurrentIndex(1)

            # Restore selection
            if selected_uuid:
                self._tree_view.select_asset(selected_uuid)

    def _on_tree_asset_selected(self, uuid: str):
        """Handle selection in tree view"""
        if uuid:
            self._event_bus.asset_selected.emit(uuid)
            asset = self._asset_model.get_asset_by_uuid(uuid)
            if asset:
                name = asset.get('name', 'Unknown')
                self._status_bar.set_status(f"Selected: {name}")
        else:
            self._event_bus.asset_selected.emit('')
            self._status_bar.set_status("Ready")

    def _rebuild_tree_model(self):
        """Rebuild the tree model from currently filtered assets."""
        # Collect visible assets from the proxy model
        filtered_assets = []
        for row in range(self._proxy_model.rowCount()):
            index = self._proxy_model.index(row, 0)
            source_index = self._proxy_model.mapToSource(index)
            asset = self._asset_model.get_asset_at_index(source_index.row())
            if asset:
                filtered_assets.append(asset)

        # Get variant counts
        variant_counts = self._db_service.get_variant_counts()

        # Build tree
        self._tree_model.build_from_assets(filtered_assets, variant_counts)
        self._tree_view.refresh_expansion()

    def _on_proxy_layout_changed(self):
        """Rebuild tree model when proxy model filters/sort change (only if in tree mode)."""
        if self._current_view_mode == "tree":
            self._rebuild_tree_model()

    def _on_edit_requested(self, uuid: str):
        """Handle edit request from metadata panel — always BLEND + APPEND"""
        self._import_asset(uuid, "BLEND", "APPEND")

    def _on_import_requested(self, uuid: str, link_mode: str):
        """Handle import request from metadata panel"""
        self._import_asset(uuid, "BLEND", link_mode)

    def _import_asset(self, uuid: str, import_method: str = None, link_mode: str = None):
        """Import asset to Blender"""
        from ..services.blender_service import get_blender_service

        asset = self._asset_model.get_asset_by_uuid(uuid)
        if not asset:
            self._status_bar.set_error("Asset not found")
            return

        name = asset.get('name', 'Unknown')
        asset_type = asset.get('asset_type', 'model')
        usd_file_path = asset.get('usd_file_path', '')
        blend_file_path = asset.get('blend_backup_path', '')

        if not usd_file_path and not blend_file_path:
            self._status_bar.set_error(f"No file path found for '{name}'")
            return

        blender_service = get_blender_service()

        success = blender_service.queue_import_asset(
            uuid=uuid,
            asset_name=name,
            usd_file_path=usd_file_path,
            blend_file_path=blend_file_path,
            import_method=import_method or Config.DEFAULT_IMPORT_METHOD,
            link_mode=link_mode or Config.DEFAULT_LINK_MODE,
            asset_type=asset_type,
            # Versioning fields
            version_group_id=asset.get('version_group_id'),
            version=asset.get('version', 1),
            version_label=asset.get('version_label', 'v001'),
            representation_type=asset.get('representation_type', 'none'),
            # Variant system fields
            asset_id=asset.get('asset_id'),
            variant_name=asset.get('variant_name', 'Base')
        )

        if success:
            self._status_bar.set_status(f"Ready to import '{name}' in Blender")

            # Update last used timestamp
            self._db_service.update_asset_last_used(uuid)
        else:
            self._status_bar.set_error(f"Failed to queue '{name}' for import")

    def _on_replace_requested(self, uuid: str, link_mode: str):
        """Handle replace request from metadata panel"""
        self._replace_asset(uuid, "BLEND", link_mode)

    def _replace_asset(self, uuid: str, import_method: str = None, link_mode: str = None):
        """Queue a replace-selected request for Blender"""
        from ..services.blender_service import get_blender_service

        asset = self._asset_model.get_asset_by_uuid(uuid)
        if not asset:
            self._status_bar.set_error("Asset not found")
            return

        name = asset.get('name', 'Unknown')
        asset_type = asset.get('asset_type', 'model')
        usd_file_path = asset.get('usd_file_path', '')
        blend_file_path = asset.get('blend_backup_path', '')

        if not usd_file_path and not blend_file_path:
            self._status_bar.set_error(f"No file path found for '{name}'")
            return

        blender_service = get_blender_service()

        success = blender_service.queue_replace_asset(
            uuid=uuid,
            asset_name=name,
            usd_file_path=usd_file_path,
            blend_file_path=blend_file_path,
            import_method=import_method or Config.DEFAULT_IMPORT_METHOD,
            link_mode=link_mode or Config.DEFAULT_LINK_MODE,
            asset_type=asset_type,
            version_group_id=asset.get('version_group_id'),
            version=asset.get('version', 1),
            version_label=asset.get('version_label', 'v001'),
            representation_type=asset.get('representation_type', 'none'),
            asset_id=asset.get('asset_id'),
            variant_name=asset.get('variant_name', 'Base')
        )

        if success:
            self._status_bar.set_status(
                f"Ready to replace selected with '{name}' in Blender"
            )
            self._db_service.update_asset_last_used(uuid)
        else:
            self._status_bar.set_error(f"Failed to queue replace for '{name}'")

    def _on_favorite_toggled(self, uuid: str):
        """Handle favorite toggle"""
        asset = self._asset_model.get_asset_by_uuid(uuid)
        if not asset:
            return

        is_favorite = asset.get('is_favorite', 0)
        new_value = 0 if is_favorite else 1

        if self._db_service.update_asset(uuid, {'is_favorite': new_value}):
            # Update model
            self._asset_model.update_asset(uuid, {'is_favorite': new_value})

            # Update metadata panel
            self._event_bus.asset_selected.emit(uuid)

            status = "Added to favorites" if new_value else "Removed from favorites"
            self._status_bar.set_status(status)

    def _on_delete_assets_requested(self, uuids: list):
        """Handle delete assets request with confirmation dialog"""
        if not uuids:
            return

        manager = get_asset_manager()

        # Build detailed warning message
        info_lines = []
        total_versions = 0
        total_variants = 0

        for uuid in uuids:
            delete_info = manager.get_delete_info(uuid)
            if 'error' in delete_info:
                continue

            name = delete_info.get('name', 'Unknown')
            variant = delete_info.get('variant_name', 'Base')
            is_base = delete_info.get('is_base', False)
            version_count = delete_info.get('version_count', 1)
            variant_count = delete_info.get('variant_count', 1)

            total_versions += version_count
            total_variants += variant_count

            if is_base and variant_count > 1:
                variants_str = ', '.join(delete_info.get('variants', [])[:3])
                if variant_count > 3:
                    variants_str += f" +{variant_count - 3} more"
                info_lines.append(f"  {name} (Base + {variant_count - 1} variants: {variants_str})")
            else:
                info_lines.append(f"  {name}/{variant} ({version_count} version{'s' if version_count != 1 else ''})")

        if not info_lines:
            self._status_bar.set_error("No valid assets to delete")
            return

        # Build confirmation message
        msg = (
            "PERMANENT DELETE\n\n"
            "This will delete:\n" +
            "\n".join(info_lines[:10]) +
            ("\n  ..." if len(info_lines) > 10 else "") +
            f"\n\nTotal: {total_versions} version(s) across {total_variants} variant(s)\n\n"
            "This includes:\n"
            "  - All version history\n"
            "  - All files on disk (USD, .blend, thumbnails)\n"
            "  - All reviews, screenshots, and draw-overs\n\n"
            "This action cannot be undone!"
        )

        reply = QMessageBox.warning(
            self,
            "Confirm Delete",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )

        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            for uuid in uuids:
                success, result_msg = manager.delete_asset_complete(uuid)
                if success:
                    deleted_count += 1

            # Reload assets
            self._load_assets()

            # Refresh folder tree
            self._folder_tree.refresh()

            # Update status
            if deleted_count == len(uuids):
                self._status_bar.set_status(f"Deleted {deleted_count} asset(s)")
            elif deleted_count > 0:
                self._status_bar.set_status(f"Deleted {deleted_count}/{len(uuids)} assets")
            else:
                self._status_bar.set_error("Failed to delete assets")
        else:
            pass

    def _on_retire_assets_requested(self, uuids: list):
        """Handle retire assets request (Studio/Pipeline mode)."""
        if not uuids:
            return

        from ..services.retire_service import get_retire_service
        retire_service = get_retire_service()

        # Build confirmation showing what will be retired
        info_lines = []
        total_versions = 0

        for uuid in uuids:
            retire_info = retire_service.get_retire_info(uuid)
            if 'error' in retire_info:
                continue

            name = retire_info.get('name', 'Unknown')
            variant = retire_info.get('variant_name', 'Base')
            version_count = retire_info.get('version_count', 1)
            total_versions += version_count

            info_lines.append(f"  {name}/{variant} ({version_count} version{'s' if version_count != 1 else ''})")

        if not info_lines:
            self._status_bar.set_error("No valid assets to retire")
            return

        # Build confirmation message
        msg = (
            "RETIRE ASSET\n\n"
            "This will retire:\n" +
            "\n".join(info_lines[:10]) +
            ("\n  ..." if len(info_lines) > 10 else "") +
            f"\n\nTotal: {total_versions} version(s)\n\n"
            "Retired assets:\n"
            "  \u2022 Move to _retired/ folder\n"
            "  \u2022 No longer visible in library\n"
            "  \u2022 Variants can still reference them\n"
            "  \u2022 Can be restored by admin later"
        )

        reply = QMessageBox.question(
            self,
            "Confirm Retire",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )

        if reply == QMessageBox.StandardButton.Yes:
            retired_count = 0
            for uuid in uuids:
                success, result_msg = retire_service.retire_asset(uuid)
                if success:
                    retired_count += 1
                else:
                    pass

            # Reload assets
            self._load_assets()

            # Refresh folder tree
            self._folder_tree.refresh()

            # Update status
            if retired_count == len(uuids):
                self._status_bar.set_status(f"Retired {retired_count} asset(s)")
            elif retired_count > 0:
                self._status_bar.set_status(f"Retired {retired_count}/{len(uuids)} assets")
            else:
                self._status_bar.set_error("Failed to retire assets")

    def _on_assets_moved(self, uuids: list, folder_id: int, count: int):
        """Handle assets moved to folder"""
        # Add assets to the new folder in multi-folder system
        for uuid in uuids:
            self._db_service.add_asset_to_folder(uuid, folder_id)

        # Reload assets to reflect changes
        assets = self._db_service.get_all_assets()

        # Get review database for comment status
        review_db = get_review_database()

        # Enrich assets with tags_v2, folders_v2, and comment status
        for asset in assets:
            uuid = asset.get('uuid')
            if uuid:
                asset['tags_v2'] = self._db_service.get_asset_tags(uuid)
                asset['folders_v2'] = self._db_service.get_asset_folders(uuid)

                # Enrich with comment/review status
                version_label = asset.get('version_label', 'v001')
                # Pass version_group_id for cycle lookup (cycles span all versions in group)
                version_group_id = asset.get('version_group_id') or asset.get('asset_id') or uuid
                review_status = review_db.get_review_status(uuid, version_label, version_group_id)
                asset['has_unresolved_comments'] = review_status.get('unresolved_notes', 0) > 0
                asset['unresolved_comment_count'] = review_status.get('unresolved_notes', 0)
                asset['review_state'] = review_status.get('review_state')

        self._asset_model.set_assets(assets)

    def _on_asset_updated(self, uuid: str):
        """Handle asset updated event - full refresh of asset data from database"""
        if not uuid:
            return

        # Clear thumbnail cache so updated thumbnails reload
        thumbnail_loader = get_thumbnail_loader()
        thumbnail_loader.clear_cache()

        # Full refresh from database (includes is_latest, thumbnail_path, folders_v2, tags_v2)
        self._asset_model.refresh_asset(uuid)

        # Also refresh review status
        review_db = get_review_database()
        asset = self._asset_model.get_asset_by_uuid(uuid)
        if asset:
            version_label = asset.get('version_label', 'v001')
            version_group_id = asset.get('version_group_id') or asset.get('asset_id') or uuid
            review_status = review_db.get_review_status(uuid, version_label, version_group_id)

            updates = {
                'has_unresolved_comments': review_status.get('unresolved_notes', 0) > 0,
                'unresolved_comment_count': review_status.get('unresolved_notes', 0),
                'review_state': review_status.get('review_state')
            }
            self._asset_model.update_asset(uuid, updates)

        # Re-filter in case is_latest changed (affects show_only_latest filter)
        self._proxy_model.invalidateFilter()

    def _show_settings(self):
        """Show settings dialog"""
        from .settings import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.exec()

    def _show_about(self):
        """Show about dialog"""
        from .dialogs import AboutDialog
        dialog = AboutDialog(self)
        dialog.exec()

    def _show_retired_assets(self):
        """Show retired assets dialog for viewing/restoring retired assets."""
        from .dialogs import RetiredAssetsDialog
        dialog = RetiredAssetsDialog(self)
        if dialog.exec():
            # Refresh assets after dialog closes (in case something was restored)
            self._load_assets()

    # ==================== EVENTS ====================

    def closeEvent(self, event: QCloseEvent):
        """Handle window close"""
        # Stop screenshot queue timer
        if hasattr(self, '_screenshot_queue_timer'):
            self._screenshot_queue_timer.stop()

        self._save_settings()
        event.accept()


__all__ = ['MainWindow']
