"""
VersionHistoryDialog - Dialog for viewing and managing asset version history.

Orchestrates sub-components for version management.
"""

from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QLabel, QPushButton,
    QDialogButtonBox, QGroupBox, QHeaderView, QMessageBox, QAbstractItemView,
    QStackedWidget, QTreeWidget, QWidget, QButtonGroup, QLineEdit, QTextEdit,
    QSplitter, QApplication
)
from PyQt6.QtCore import Qt, QSize, QTimer

from .config import VersionHistoryConfig, THUMBNAIL_UUID_ROLE
from .preview_panel import PreviewPanel
from .tree_view import VersionTreeView
from .list_view import VersionListView
from .action_handlers import VersionActionHandlers
from .variant_manager import VariantManager

from ....config import Config, REVIEW_CYCLE_TYPES
from ....services.database_service import get_database_service
from ....services.cold_storage_service import get_cold_storage_service
from ....services.thumbnail_loader import get_thumbnail_loader
from ....services.user_service import get_user_service
from ....services.control_authority import get_control_authority, OperationMode
from ..asset_review_dialog import AssetReviewDialog
from ..create_variant_dialog import CreateVariantDialog


class VersionHistoryDialog(QDialog):
    """
    Dialog for viewing and managing asset version history.

    Features:
    - List all versions of an asset (by version_group_id)
    - Show version label, status, date, is_latest, is_cold
    - Support for variants: switch between parallel version chains
    - Actions: Set as Latest, Cold Storage, Lock, Publish, Review
    """

    def __init__(self, version_group_id: str, parent=None):
        super().__init__(parent)

        self._version_group_id = version_group_id
        self._db_service = get_database_service()
        self._cold_storage = get_cold_storage_service()
        self._thumbnail_loader = get_thumbnail_loader()
        self._versions: List[Dict[str, Any]] = []
        self._selected_uuid: Optional[str] = None

        # View mode
        self._view_mode: str = "tree"
        self._notes_modified: bool = False
        self._first_show: bool = True

        # Sub-components
        self._variant_manager = VariantManager(self, self._db_service, version_group_id)

        self.setWindowTitle("Asset Lineage")
        self.setModal(True)

        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        # Size to configured percentage of screen
        self._setup_size()

        self._create_ui()
        self._connect_signals()
        self._initialize_data()
        self._update_review_button_visibility()

    def _setup_size(self):
        """Configure dialog size based on screen."""
        cfg = VersionHistoryConfig
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            width = int(screen_rect.width() * cfg.SCREEN_RATIO)
            height = int(screen_rect.height() * cfg.SCREEN_RATIO)
            self.resize(width, height)
            x = screen_rect.x() + (screen_rect.width() - width) // 2
            y = screen_rect.y() + (screen_rect.height() - height) // 2
            self.move(x, y)
        else:
            self.resize(int(cfg.MIN_WIDTH * 1.4), int(cfg.MIN_HEIGHT * 1.5))
        self.setMinimumSize(cfg.MIN_WIDTH, cfg.MIN_HEIGHT)

    def _create_ui(self):
        """Create UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header
        self._header_label = QLabel("Asset Lineage")
        self._header_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self._header_label.setFixedHeight(24)
        layout.addWidget(self._header_label)

        # Main splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side content
        left_widget = self._create_left_panel()
        main_splitter.addWidget(left_widget)

        # Right side preview
        preview_widget = self._create_preview_panel()
        main_splitter.addWidget(preview_widget)

        main_splitter.setSizes([780, 320])
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 0)
        main_splitter.setCollapsible(1, False)

        layout.addWidget(main_splitter)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

        self._update_action_buttons(None)

    def _create_left_panel(self) -> QWidget:
        """Create left panel with views and actions."""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Controls row
        controls_row = self._create_controls_row()
        left_layout.addLayout(controls_row)

        # View stack
        self._view_stack = QStackedWidget()

        # List view
        self._table = self._create_table()
        self._view_stack.addWidget(self._table)

        # Tree view
        self._tree = self._create_tree()
        self._view_stack.addWidget(self._tree)

        left_layout.addWidget(self._view_stack, 1)

        # Actions group
        actions_group = self._create_actions_group()
        left_layout.addWidget(actions_group)

        # Notes section
        notes_group = self._create_notes_section()
        left_layout.addWidget(notes_group)

        return left_widget

    def _create_controls_row(self) -> QHBoxLayout:
        """Create view controls row."""
        controls_row = QHBoxLayout()

        # View mode toggle
        view_mode_layout = QHBoxLayout()
        view_mode_layout.setSpacing(0)

        self._list_view_btn = QPushButton("List View")
        self._list_view_btn.setCheckable(True)
        self._list_view_btn.setStyleSheet("""
            QPushButton { padding: 4px 12px; border: 1px solid #555; border-right: none;
                          border-radius: 0; border-top-left-radius: 4px; border-bottom-left-radius: 4px; }
            QPushButton:checked { background-color: #0078d4; color: white; }
        """)
        view_mode_layout.addWidget(self._list_view_btn)

        self._tree_view_btn = QPushButton("Tree View")
        self._tree_view_btn.setCheckable(True)
        self._tree_view_btn.setChecked(True)
        self._tree_view_btn.setStyleSheet("""
            QPushButton { padding: 4px 12px; border: 1px solid #555; border-radius: 0;
                          border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
            QPushButton:checked { background-color: #0078d4; color: white; }
        """)
        view_mode_layout.addWidget(self._tree_view_btn)

        self._view_mode_group = QButtonGroup(self)
        self._view_mode_group.addButton(self._list_view_btn, 0)
        self._view_mode_group.addButton(self._tree_view_btn, 1)

        controls_row.addLayout(view_mode_layout)
        controls_row.addSpacing(20)

        # Search filter
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter variants...")
        self._search_edit.setFixedWidth(150)
        self._search_edit.setClearButtonEnabled(True)
        controls_row.addWidget(self._search_edit)
        controls_row.addSpacing(10)

        # Hide intermediate toggle
        self._hide_intermediate_btn = QPushButton("Branch Points Only")
        self._hide_intermediate_btn.setCheckable(True)
        self._hide_intermediate_btn.setToolTip("Hide intermediate versions - show only branch points and latest")
        self._hide_intermediate_btn.setStyleSheet("""
            QPushButton { padding: 4px 10px; border: 1px solid #555; border-radius: 0px; }
            QPushButton:checked { background-color: #7B1FA2; color: white; border-color: #7B1FA2; }
        """)
        controls_row.addWidget(self._hide_intermediate_btn)
        controls_row.addSpacing(10)

        # Show thumbnails toggle
        self._show_thumbnails_btn = QPushButton("Version Thumbs")
        self._show_thumbnails_btn.setCheckable(True)
        self._show_thumbnails_btn.setChecked(True)
        self._show_thumbnails_btn.setToolTip("Show thumbnails for each version")
        self._show_thumbnails_btn.setStyleSheet("""
            QPushButton { padding: 4px 10px; border: 1px solid #555; border-radius: 0px; }
            QPushButton:checked { background-color: #2196F3; color: white; border-color: #2196F3; }
        """)
        controls_row.addWidget(self._show_thumbnails_btn)
        controls_row.addSpacing(10)

        # New variant button
        self._new_variant_btn = QPushButton("+ New Variant")
        self._new_variant_btn.setToolTip("Create a new variant from the selected Base version")
        self._new_variant_btn.setEnabled(False)
        controls_row.addWidget(self._new_variant_btn)

        controls_row.addStretch()
        return controls_row

    def _create_table(self) -> QTableWidget:
        """Create table for list view."""
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "Version", "Name", "Status", "Created", "Latest", "Cold", "Locked"
        ])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i in range(2, 7):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(0, 80)
        table.setColumnWidth(2, 100)
        table.setColumnWidth(3, 140)
        table.setColumnWidth(4, 60)
        table.setColumnWidth(5, 60)
        table.setColumnWidth(6, 60)

        return table

    def _create_tree(self) -> QTreeWidget:
        """Create tree for tree view."""
        tree = QTreeWidget()
        tree.setHeaderLabels(["Asset", "Version", "Status", "Review", "VariantSet"])
        tree.setColumnCount(5)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setAlternatingRowColors(True)
        tree.setIconSize(QSize(VersionHistoryConfig.THUMBNAIL_SIZE, VersionHistoryConfig.THUMBNAIL_SIZE))

        tree.setColumnWidth(0, 250)
        tree.setColumnWidth(1, 80)
        tree.setColumnWidth(2, 100)
        tree.setColumnWidth(3, 100)

        return tree

    def _create_actions_group(self) -> QGroupBox:
        """Create actions group."""
        actions_group = QGroupBox("Actions")
        actions_group.setMaximumHeight(70)
        actions_layout = QHBoxLayout(actions_group)

        self._promote_btn = QPushButton("Set as Latest")
        self._promote_btn.setToolTip("Promote this version to be the latest")
        actions_layout.addWidget(self._promote_btn)

        self._cold_storage_btn = QPushButton("Move to Cold Storage")
        self._cold_storage_btn.setToolTip("Move to cold storage (archive)")
        actions_layout.addWidget(self._cold_storage_btn)

        self._publish_btn = QPushButton("Publish")
        self._publish_btn.setToolTip("Approve and lock this version")
        actions_layout.addWidget(self._publish_btn)

        self._lock_btn = QPushButton("Lock")
        self._lock_btn.setToolTip("Lock version to prevent changes")
        actions_layout.addWidget(self._lock_btn)

        self._review_btn = QPushButton("Review")
        self._review_btn.setToolTip("Open review dialog for this version")
        self._review_btn.setStyleSheet("""
            QPushButton { background-color: #FF5722; color: white; font-weight: bold;
                          padding: 6px 16px; border-radius: 4px; }
            QPushButton:hover { background-color: #E64A19; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        actions_layout.addWidget(self._review_btn)

        self._mark_final_btn = QPushButton("Mark Final")
        self._mark_final_btn.setToolTip("Mark the current review cycle as final")
        self._mark_final_btn.setStyleSheet("""
            QPushButton { background-color: #9C27B0; color: white; font-weight: bold;
                          padding: 6px 16px; border-radius: 4px; }
            QPushButton:hover { background-color: #7B1FA2; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self._mark_final_btn.setEnabled(False)
        actions_layout.addWidget(self._mark_final_btn)

        actions_layout.addStretch()
        return actions_group

    def _create_notes_section(self) -> QGroupBox:
        """Create notes section."""
        notes_group = QGroupBox("Notes")
        notes_group.setFixedHeight(140)
        notes_layout = QHBoxLayout(notes_group)
        notes_layout.setContentsMargins(8, 4, 8, 8)
        notes_layout.setSpacing(8)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Add notes about this version...")
        self._notes_edit.setEnabled(False)
        notes_layout.addWidget(self._notes_edit, 1)

        self._save_notes_btn = QPushButton("Save")
        self._save_notes_btn.setEnabled(False)
        self._save_notes_btn.setFixedWidth(50)
        notes_layout.addWidget(self._save_notes_btn)

        return notes_group

    def _create_preview_panel(self) -> QWidget:
        """Create right-side preview panel."""
        cfg = VersionHistoryConfig
        preview_widget = QWidget()
        preview_widget.setFixedWidth(cfg.PREVIEW_SIZE + 20)
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(10, 0, 0, 0)
        preview_layout.setSpacing(4)

        # Header
        preview_header = QLabel("Version Preview")
        preview_header.setStyleSheet("font-size: 14px; font-weight: bold;")
        preview_layout.addWidget(preview_header)

        # Info label
        self._preview_info_label = QLabel("Select a version to preview")
        self._preview_info_label.setStyleSheet("font-size: 12px; color: #888;")
        preview_layout.addWidget(self._preview_info_label)

        # Image label
        self._preview_image_label = QLabel()
        self._preview_image_label.setFixedSize(cfg.PREVIEW_SIZE, cfg.PREVIEW_SIZE)
        self._preview_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_image_label.setStyleSheet("""
            QLabel { background-color: #1a1a1a; border: 1px solid #404040; border-radius: 4px; }
        """)
        self._preview_image_label.setText("No preview")
        preview_layout.addWidget(self._preview_image_label)

        # Initialize preview panel manager
        self._preview_panel = PreviewPanel(self._preview_info_label, self._preview_image_label)

        preview_layout.addSpacing(12)

        # Version info
        info_header = QLabel("Version Info")
        info_header.setStyleSheet("font-size: 12px; font-weight: bold;")
        preview_layout.addWidget(info_header)

        self._info_label = QLabel("Select a version to see details")
        self._info_label.setWordWrap(True)
        self._info_label.setMaximumWidth(cfg.PREVIEW_SIZE)
        self._info_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        preview_layout.addWidget(self._info_label)

        preview_layout.addStretch()
        return preview_widget

    def _connect_signals(self):
        """Connect widget signals."""
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self._tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self._view_mode_group.idClicked.connect(self._on_view_mode_changed)
        self._search_edit.textChanged.connect(self._on_search_changed)
        self._hide_intermediate_btn.clicked.connect(self._on_hide_intermediate_toggled)
        self._show_thumbnails_btn.clicked.connect(self._on_show_thumbnails_toggled)
        self._new_variant_btn.clicked.connect(self._on_new_variant_clicked)

        self._promote_btn.clicked.connect(self._on_promote_clicked)
        self._cold_storage_btn.clicked.connect(self._on_cold_storage_clicked)
        self._publish_btn.clicked.connect(self._on_publish_clicked)
        self._lock_btn.clicked.connect(self._on_lock_clicked)
        self._review_btn.clicked.connect(self._on_review_clicked)
        self._mark_final_btn.clicked.connect(self._on_mark_final_clicked)

        self._notes_edit.textChanged.connect(self._on_notes_changed)
        self._save_notes_btn.clicked.connect(self._on_save_notes_clicked)
        self._thumbnail_loader.thumbnail_loaded.connect(self._on_thumbnail_loaded)

    def _initialize_data(self):
        """Initialize data and views."""
        # Initialize sub-components
        self._variant_manager.load_asset_info()
        self._variant_manager.load_variants()
        self._variant_manager.load_all_variants_data()

        # Initialize tree view manager
        self._tree_view = VersionTreeView(
            self._tree,
            self._thumbnail_loader,
            self._request_tree_thumbnail
        )
        self._tree_view.set_data(self._variant_manager.all_variants_data)

        # Initialize list view manager
        self._list_view = VersionListView(self._table)

        # Initialize action handlers
        self._action_handlers = VersionActionHandlers(
            self,
            self._db_service,
            self._cold_storage,
            lambda: self._get_version_for_action(check_all_variants=True),
            self._refresh_after_action
        )

        # Set default view
        self._view_stack.setCurrentIndex(1)
        self._populate_tree()

    def showEvent(self, event):
        """Handle dialog show."""
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            QTimer.singleShot(50, self._tree_view._create_deferred_badge_widgets)

    def _request_tree_thumbnail(self, uuid: str, path: str, node):
        """Request thumbnail for tree node."""
        from PyQt6.QtGui import QIcon
        pixmap = self._thumbnail_loader.request_thumbnail(uuid, path, 32)
        if pixmap:
            node.setIcon(0, QIcon(pixmap))

    def _on_thumbnail_loaded(self, uuid: str, pixmap):
        """Handle thumbnail loaded."""
        self._tree_view.on_thumbnail_loaded(uuid, pixmap)

    # ==================== View Mode Handlers ====================

    def _on_view_mode_changed(self, button_id: int):
        """Handle view mode toggle."""
        if button_id == 0:
            self._view_mode = "list"
            self._view_stack.setCurrentIndex(0)
            self._load_versions()
        else:
            self._view_mode = "tree"
            self._view_stack.setCurrentIndex(1)
            self._populate_tree()

    def _on_search_changed(self, text: str):
        """Handle search filter change."""
        self._tree_view.set_search_filter(text)
        self._populate_tree()

    def _on_hide_intermediate_toggled(self):
        """Handle hide intermediate toggle."""
        self._tree_view.set_hide_intermediate(self._hide_intermediate_btn.isChecked())
        self._populate_tree()

    def _on_show_thumbnails_toggled(self):
        """Handle show thumbnails toggle."""
        self._tree_view.set_show_thumbnails(self._show_thumbnails_btn.isChecked())
        self._populate_tree()

    # ==================== Data Loading ====================

    def _load_versions(self):
        """Load version history for list view."""
        self._versions = self._db_service.get_version_history(self._version_group_id)

        if self._versions:
            first_version = self._versions[0]
            asset_name = first_version.get('name', 'Unknown')
            self._header_label.setText(f"Lineage: {asset_name}")

        self._list_view.set_data(self._versions)
        self._list_view.populate()

    def _populate_tree(self):
        """Populate tree view."""
        self._tree_view.set_data(self._variant_manager.all_variants_data)
        self._tree_view.populate()

    def _refresh_after_action(self):
        """Refresh view after action."""
        self._load_versions()
        self._variant_manager.load_variants()
        self._variant_manager.load_all_variants_data()
        if self._view_mode == "tree":
            self._populate_tree()

    # ==================== Selection Handling ====================

    def _on_table_selection_changed(self):
        """Handle table selection change."""
        selected_rows = self._table.selectedIndexes()
        if not selected_rows:
            self._selected_uuid = None
            self._apply_selection_updates(None)
            return

        row = selected_rows[0].row()
        version_item = self._table.item(row, 0)
        if version_item:
            self._selected_uuid = version_item.data(Qt.ItemDataRole.UserRole)
            self._apply_selection_updates(self._get_selected_version())

    def _on_tree_selection_changed(self):
        """Handle tree selection change."""
        selected_items = self._tree.selectedItems()
        if not selected_items:
            self._selected_uuid = None
            self._apply_selection_updates(None)
            return

        item = selected_items[0]
        uuid = item.data(0, Qt.ItemDataRole.UserRole)

        if uuid:
            self._selected_uuid = uuid
            version = self._get_version_for_action(check_all_variants=True)
            self._apply_selection_updates(version)
        else:
            self._selected_uuid = None
            self._update_action_buttons(None)
            self._update_new_variant_button(None)

            thumb_uuid = item.data(0, THUMBNAIL_UUID_ROLE)
            if thumb_uuid:
                for v in self._variant_manager.all_variants_data:
                    if v.get('uuid') == thumb_uuid:
                        header_text = item.text(0)
                        self._preview_info_label.setText(f"{header_text} (Latest)")
                        self._preview_panel.load_preview(thumb_uuid, v.get('thumbnail_path', ''))
                        return
            self._preview_panel.update_display(None)

    def _apply_selection_updates(self, version: Optional[Dict[str, Any]]):
        """Apply UI updates after selection change."""
        if version:
            self._update_action_buttons(version)
            self._update_info_panel(version)
            self._update_new_variant_button(version)
            self._preview_panel.update_display(version)
        else:
            self._update_action_buttons(None)
            self._update_new_variant_button(None)
            self._preview_panel.update_display(None)
            self._info_label.setText("Select a version to see details")

    def _get_selected_version(self) -> Optional[Dict[str, Any]]:
        """Get selected version from list view."""
        if not self._selected_uuid:
            return None
        for version in self._versions:
            if version.get('uuid') == self._selected_uuid:
                return version
        return None

    def _get_version_for_action(self, check_all_variants: bool = False) -> Optional[Dict[str, Any]]:
        """Get selected version for actions."""
        if not self._selected_uuid:
            return None

        if check_all_variants:
            for v in self._variant_manager.all_variants_data:
                if v.get('uuid') == self._selected_uuid:
                    return v

        return self._get_selected_version()

    # ==================== UI Updates ====================

    def _update_review_button_visibility(self):
        """Update review button visibility based on operation mode.
        
        Review features are only available in Studio and Pipeline modes,
        not in Standalone mode.
        """
        control_authority = get_control_authority()
        is_review_mode = control_authority.get_operation_mode() != OperationMode.STANDALONE
        self._review_btn.setVisible(is_review_mode)
        self._mark_final_btn.setVisible(is_review_mode)

    def _update_action_buttons(self, version: Optional[Dict[str, Any]]):
        """Update action button states."""
        if not version:
            self._promote_btn.setEnabled(False)
            self._cold_storage_btn.setEnabled(False)
            self._publish_btn.setEnabled(False)
            self._lock_btn.setEnabled(False)
            self._review_btn.setEnabled(False)
            self._mark_final_btn.setEnabled(False)
            return

        # Check if version is retired - disable ALL actions
        is_retired = version.get('is_retired', 0) == 1
        if is_retired:
            self._promote_btn.setEnabled(False)
            self._promote_btn.setToolTip("Cannot modify retired asset")
            self._cold_storage_btn.setEnabled(False)
            self._cold_storage_btn.setToolTip("Cannot modify retired asset")
            self._publish_btn.setEnabled(False)
            self._publish_btn.setToolTip("Cannot modify retired asset")
            self._lock_btn.setEnabled(False)
            self._lock_btn.setToolTip("Cannot modify retired asset")
            self._review_btn.setEnabled(False)
            self._review_btn.setToolTip("Cannot review retired asset")
            self._mark_final_btn.setEnabled(False)
            self._mark_final_btn.setToolTip("Cannot modify retired asset")
            return

        # Only enable review button in Studio/Pipeline modes (not Standalone)
        control_authority = get_control_authority()
        is_review_mode = control_authority.get_operation_mode() != OperationMode.STANDALONE
        self._review_btn.setEnabled(is_review_mode)

        # Mark Final button (only in Studio/Pipeline modes)
        if is_review_mode:
            from ....services.review_state_manager import get_review_state_manager
            state_manager = get_review_state_manager()
            cycle = state_manager.get_cycle_for_version(version.get('uuid'), version.get('version_label', 'v001'))
            if cycle and cycle.get('review_state') == 'approved':
                self._mark_final_btn.setEnabled(True)
                cycle_type = cycle.get('cycle_type', 'general')
                cycle_label = REVIEW_CYCLE_TYPES.get(cycle_type, {}).get('label', cycle_type.title())
                self._mark_final_btn.setToolTip(f"Mark {cycle_label} cycle as Final")
            else:
                self._mark_final_btn.setEnabled(False)
                self._mark_final_btn.setToolTip("Mark the current review cycle as final (requires approved state)")
        else:
            self._mark_final_btn.setEnabled(False)

        is_latest = version.get('is_latest', 0) == 1
        is_cold = version.get('is_cold', 0) == 1
        is_locked = version.get('is_immutable', 0) == 1
        status = version.get('status', 'wip')

        self._promote_btn.setEnabled(not is_latest)

        if is_cold:
            self._cold_storage_btn.setText("Restore from Cold")
            self._cold_storage_btn.setToolTip("Restore from cold storage to active")
        else:
            self._cold_storage_btn.setText("Move to Cold Storage")
            self._cold_storage_btn.setToolTip("Move to cold storage (archive)")
        self._cold_storage_btn.setEnabled(True)

        self._publish_btn.setEnabled(status != 'approved')

        if is_locked:
            self._lock_btn.setText("Unlock")
            self._lock_btn.setToolTip("Unlock version to allow changes")
        else:
            self._lock_btn.setText("Lock")
            self._lock_btn.setToolTip("Lock version to prevent changes")
        self._lock_btn.setEnabled(True)

    def _update_new_variant_button(self, version: Optional[Dict[str, Any]]):
        """Update new variant button state."""
        if not version:
            self._new_variant_btn.setEnabled(False)
            self._new_variant_btn.setToolTip("Select a version to create a variant")
            return

        # Check if version is retired - cannot create variants from retired assets
        is_retired = version.get('is_retired', 0) == 1
        if is_retired:
            self._new_variant_btn.setEnabled(False)
            self._new_variant_btn.setToolTip("Cannot create variant from retired asset")
            return

        variant_name = version.get('variant_name') or version.get('_variant_name', 'Base')
        version_label = version.get('version_label', 'Unknown')

        if variant_name == 'Base':
            self._new_variant_btn.setEnabled(True)
            self._new_variant_btn.setToolTip(f"Create new variant from {version_label}")
        else:
            self._new_variant_btn.setEnabled(False)
            self._new_variant_btn.setToolTip("Variants can only be created from Base")

    def _update_info_panel(self, version: Optional[Dict[str, Any]]):
        """Update info panel with version details."""
        if not version:
            self._info_label.setText("Select a version to see details")
            self._notes_edit.setEnabled(False)
            self._notes_edit.clear()
            self._save_notes_btn.setEnabled(False)
            return

        # Check if retired
        is_retired = version.get('is_retired', 0) == 1

        # Build info text
        description = version.get('description', '')
        usd_path = version.get('usd_file_path', '')
        blend_path = version.get('blend_backup_path', '')
        cold_path = version.get('cold_storage_path', '')
        rep_type = version.get('representation_type', 'final')
        variant_name = version.get('variant_name') or version.get('_variant_name', 'Base')
        source_name = version.get('source_asset_name', '')
        source_version = version.get('source_version_label', '')

        info_lines = [
            f"<b>Variant:</b> {variant_name}",
            f"<b>Representation:</b> {rep_type.capitalize() if rep_type else 'None'}",
        ]

        if source_name and source_version:
            info_lines.append(f"<b>Branched from:</b> {source_name} {source_version}")

        if description:
            desc_short = description[:80] + "..." if len(description) > 80 else description
            info_lines.append(f"<b>Description:</b> {desc_short}")

        if not cold_path:
            if usd_path:
                info_lines.append(f"<b>USD:</b><br>{self._truncate_path(usd_path, 40)}")
            if blend_path:
                info_lines.append(f"<b>Blend:</b><br>{self._truncate_path(blend_path, 40)}")

        # Add retired warning to info
        if is_retired:
            info_lines.insert(0, "<b style='color: #795548;'>⚠ RETIRED ASSET</b>")

        self._info_label.setText("<br>".join(info_lines))

        # Notes - disabled for retired versions
        notes = version.get('version_notes', '') or ''
        self._notes_edit.blockSignals(True)
        self._notes_edit.setPlainText(notes)
        self._notes_edit.blockSignals(False)
        self._notes_edit.setEnabled(not is_retired)  # Disable for retired
        self._notes_modified = False
        self._save_notes_btn.setEnabled(False)

    def _truncate_path(self, path: str, max_len: int = 35) -> str:
        """Truncate a path for display."""
        if not path or len(path) <= max_len:
            return path
        keep = (max_len - 3) // 2
        return f"{path[:keep]}...{path[-keep:]}"

    # ==================== Notes Handling ====================

    def _on_notes_changed(self):
        """Handle notes text changed."""
        self._notes_modified = True
        self._save_notes_btn.setEnabled(True)

    def _on_save_notes_clicked(self):
        """Save notes for selected version."""
        if not self._selected_uuid:
            return

        notes = self._notes_edit.toPlainText()
        if self._db_service.update_version_notes(self._selected_uuid, notes):
            self._notes_modified = False
            self._save_notes_btn.setEnabled(False)

            for v in self._variant_manager.all_variants_data:
                if v.get('uuid') == self._selected_uuid:
                    v['version_notes'] = notes
                    break
            for v in self._versions:
                if v.get('uuid') == self._selected_uuid:
                    v['version_notes'] = notes
                    break
        else:
            QMessageBox.warning(self, "Error", "Failed to save notes.")

    # ==================== Action Handlers ====================

    def _on_promote_clicked(self):
        """Handle promote action."""
        self._action_handlers.on_promote()

    def _on_cold_storage_clicked(self):
        """Handle cold storage action."""
        self._action_handlers.on_cold_storage()

    def _on_publish_clicked(self):
        """Handle publish action."""
        self._action_handlers.on_publish()

    def _on_lock_clicked(self):
        """Handle lock action."""
        self._action_handlers.on_lock()

    def _on_review_clicked(self):
        """Handle review action."""
        version = self._get_version_for_action(check_all_variants=True)
        if not version:
            return

        # Use version_group_id for review dialog since sessions/cycles are tracked at family level
        version_group_id = version.get('version_group_id') or version.get('asset_id') or version.get('uuid', '')
        variant_name = version.get('variant_name', 'Base')

        user_service = get_user_service()
        control_authority = get_control_authority()
        # Review dialog is available in Studio and Pipeline modes
        is_review_mode = control_authority.get_operation_mode() != OperationMode.STANDALONE
        dialog = AssetReviewDialog(
            asset_uuid=version_group_id,  # Family UUID for session/cycle tracking
            version_label=version.get('version_label', 'v001'),
            asset_name=version.get('name', ''),
            asset_id=version_group_id,  # Same as asset_uuid for storage paths
            variant_name=variant_name,
            is_studio_mode=is_review_mode,
            current_user=user_service.get_current_username(),
            current_user_role=user_service.get_current_role(),
            parent=self
        )
        dialog.exec()
        self._populate_tree()

    def _on_mark_final_clicked(self):
        """Handle mark final action."""
        self._action_handlers.on_mark_final(self._populate_tree)

    def _on_new_variant_clicked(self):
        """Handle new variant action."""
        version = self._get_version_for_action(check_all_variants=True)
        if not version:
            return

        variant_name = version.get('variant_name') or version.get('_variant_name', 'Base')
        if variant_name != 'Base':
            QMessageBox.warning(
                self,
                "Cannot Create Variant",
                "Variants can only be created from Base variants."
            )
            return

        dialog = CreateVariantDialog(
            source_name=version.get('name', 'Unknown'),
            source_version=version.get('version_label', 'Unknown'),
            existing_variants=[v.get('variant_name') for v in self._variant_manager.variants],
            existing_variant_sets=self._db_service.get_variant_sets(self._variant_manager.asset_id),
            parent=self
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name = dialog.get_variant_name()
        variant_set = dialog.get_variant_set()

        if name:
            self._variant_manager.create_new_variant(
                self._selected_uuid,
                version,
                name,
                variant_set,
                self._refresh_after_action
            )


__all__ = ['VersionHistoryDialog']
