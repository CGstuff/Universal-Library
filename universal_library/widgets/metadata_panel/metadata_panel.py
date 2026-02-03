"""
MetadataPanel - Right panel showing asset details.

Orchestrates sub-panels for display of asset metadata.
"""

from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QScrollArea, QFrame, QSizePolicy, QMenu
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPixmap

from ...config import Config, REVIEW_CYCLE_TYPES
from ...events.event_bus import get_event_bus
from ...events.entity_events import get_entity_event_bus
from ...services.database_service import get_database_service
from ...services.review_database import get_review_database
from ...services.review_state_manager import get_review_state_manager
from ...services.thumbnail_loader import get_thumbnail_loader
from ...services.user_service import get_user_service
from ...services.control_authority import get_control_authority

from .panels import (
    IdentificationPanel, LineagePanel, ThumbnailPanel,
    TagsWidget, FoldersWidget
)
from .renderers import TechnicalInfoRenderer, ReviewStateRenderer, DynamicMetadataRenderer
from ..dialogs.version_history_dialog import VersionHistoryDialog


class MetadataPanel(QWidget):
    """
    Right panel showing selected asset details with context-sensitive metadata.

    Features:
    - Large thumbnail preview
    - Asset name, type badge, and UUID (copyable)
    - Context-sensitive technical info based on asset category
    - Identification section (author, dates)
    - Version and status information
    - Import settings and action buttons
    """

    # Signals
    edit_requested = pyqtSignal(str)              # uuid (always BLEND+APPEND)
    import_requested = pyqtSignal(str, str)       # uuid, link_mode
    replace_requested = pyqtSignal(str, str)      # uuid, link_mode
    tags_changed = pyqtSignal(str, list)  # uuid, list of tag_ids
    folders_changed = pyqtSignal(str, list)  # uuid, list of folder_ids

    def __init__(self, parent=None):
        super().__init__(parent)

        self._event_bus = get_event_bus()
        self._entity_event_bus = get_entity_event_bus()
        self._db_service = get_database_service()
        self._review_db = get_review_database()
        self._thumbnail_loader = get_thumbnail_loader()
        self._user_service = get_user_service()
        self._control_authority = get_control_authority()

        # Current asset
        self._current_uuid: Optional[str] = None
        self._current_asset: Optional[Dict[str, Any]] = None

        self._setup_ui()
        self._connect_signals()
        self._connect_entity_signals()
        self._clear_display()
        self._update_review_visibility()

    def _get_category_for_type(self, asset_type: str) -> str:
        """Get the metadata category for an asset type."""
        return Config.ASSET_TYPE_CATEGORY.get(asset_type, 'mesh')

    def _setup_ui(self):
        """Setup panel UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(12)

        # Thumbnail
        self._thumbnail = ThumbnailPanel()
        self._layout.addWidget(self._thumbnail)

        # Name label
        self._name_label = QLabel("No asset selected")
        self._name_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self._name_label.setWordWrap(True)
        self._layout.addWidget(self._name_label)

        # Type badge
        self._type_label = QLabel("")
        self._type_label.setStyleSheet("""
            QLabel {
                background-color: #4CAF50;
                color: white;
                padding: 2px 8px;
                border-radius: 0px;
                font-size: 11px;
            }
        """)
        self._type_label.setFixedHeight(20)
        self._layout.addWidget(self._type_label)

        # Identification panel
        self._id_panel = IdentificationPanel()
        self._layout.addWidget(self._id_panel)

        # Lineage panel
        self._lineage_panel = LineagePanel()
        self._lineage_panel.history_requested.connect(self._on_history_clicked)
        self._lineage_panel.representation_apply_requested.connect(self._on_representation_apply)
        self._lineage_panel.representation_regenerate_requested.connect(self._on_representation_regenerate)
        self._lineage_panel.representation_clear_requested.connect(self._on_representation_clear)
        self._layout.addWidget(self._lineage_panel)

        # Technical info section
        self._setup_technical_info()

        # Dynamic metadata section (for custom/extended fields)
        self._setup_dynamic_metadata()

        # Description section
        self._desc_group = QGroupBox("Description")
        desc_layout = QVBoxLayout(self._desc_group)
        self._description_label = QLabel("-")
        self._description_label.setWordWrap(True)
        self._description_label.setStyleSheet("color: #a0a0a0;")
        desc_layout.addWidget(self._description_label)
        self._layout.addWidget(self._desc_group)

        # Tags widget
        self._tags_widget = TagsWidget(self._db_service)
        self._tags_widget.tags_changed.connect(
            lambda uuid, tags: self.tags_changed.emit(uuid, tags)
        )
        self._layout.addWidget(self._tags_widget)

        # Folders widget
        self._folders_widget = FoldersWidget(self._db_service)
        self._folders_widget.folders_changed.connect(
            lambda uuid, folders: self.folders_changed.emit(uuid, folders)
        )
        self._layout.addWidget(self._folders_widget)

        # Import settings
        self._setup_import_section()

        # Review state renderer
        self._setup_review_state()

        # Spacer before danger zone
        spacer = QWidget()
        spacer.setFixedHeight(20)
        self._layout.addWidget(spacer)

        # Danger zone (delete)
        self._setup_danger_zone()

        self._layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll)
        self.setMinimumWidth(280)

    def _setup_technical_info(self):
        """Setup technical info section with all labels."""
        self._tech_group = QGroupBox("Technical Info")
        tech_layout = QVBoxLayout(self._tech_group)
        tech_layout.setSpacing(4)

        # Create all labels
        self._tech_labels = {
            'polygons': QLabel("Polygons: -"),
            'materials': QLabel("Materials: -"),
            'vertex_groups': QLabel("Vertex Groups: -"),
            'shape_keys': QLabel("Shape Keys: -"),
            'bone_count': QLabel("Bones: -"),
            'skeleton': QLabel("Skeleton: -"),
            'animations': QLabel("Animations: -"),
            'facial_rig': QLabel("Facial Rig: -"),
            'texture_maps': QLabel("Texture Maps: -"),
            'texture_res': QLabel("Resolution: -"),
            'control_count': QLabel("Controls: -"),
            'frame_range': QLabel("Frame Range: -"),
            'fps': QLabel("Frame Rate: -"),
            'duration': QLabel("Duration: -"),
            'loop': QLabel("Loop: -"),
            'light_type': QLabel("Light Type: -"),
            'light_count': QLabel("Light Count: -"),
            'light_power': QLabel("Power: -"),
            'light_color': QLabel("Color: -"),
            'light_shadow': QLabel("Shadow: -"),
            'light_spot_size': QLabel("Spot Size: -"),
            'light_area_shape': QLabel("Area Shape: -"),
            'camera_type': QLabel("Camera Type: -"),
            'focal_length': QLabel("Focal Length: -"),
            'camera_sensor': QLabel("Sensor: -"),
            'camera_dof': QLabel("DOF: -"),
            'camera_ortho_scale': QLabel("Ortho Scale: -"),
            'collection_name': QLabel("Collection: -"),
            'contents': QLabel("Contents: -"),
            'nested_collections': QLabel("Nested Collections: -"),
            # Grease Pencil
            'gp_layers': QLabel("Layers: -"),
            'gp_strokes': QLabel("Strokes: -"),
            'gp_frames': QLabel("Frames: -"),
            # Curve
            'curve_type': QLabel("Curve Type: -"),
            'curve_points': QLabel("Points: -"),
            'curve_splines': QLabel("Splines: -"),
            # Scene
            'scene_name': QLabel("Scene: -"),
            'scene_objects': QLabel("Objects: -"),
            'scene_collections': QLabel("Collections: -"),
            'scene_render_engine': QLabel("Render Engine: -"),
            'scene_resolution': QLabel("Resolution: -"),
            'scene_world': QLabel("World: -"),
            'filesize': QLabel("File Size: -"),
        }

        for label in self._tech_labels.values():
            tech_layout.addWidget(label)

        self._layout.addWidget(self._tech_group)

        # Create renderer
        self._tech_renderer = TechnicalInfoRenderer(self._tech_labels)

    def _setup_dynamic_metadata(self):
        """Setup dynamic metadata section for custom/extended fields."""
        # Container for dynamic metadata (will auto-generate category groups)
        self._dynamic_container = QWidget()
        self._dynamic_layout = QVBoxLayout(self._dynamic_container)
        self._dynamic_layout.setContentsMargins(0, 0, 0, 0)
        self._dynamic_layout.setSpacing(8)

        # Create dynamic renderer
        self._dynamic_renderer = DynamicMetadataRenderer(
            entity_type='asset',
            read_only=True,
            show_empty=False
        )
        self._dynamic_layout.addWidget(self._dynamic_renderer)

        # Add to main layout (initially hidden)
        self._dynamic_container.hide()
        self._layout.addWidget(self._dynamic_container)

    def _setup_import_section(self):
        """Setup import settings section."""
        self._import_group = QGroupBox("Import Settings")
        import_layout = QVBoxLayout(self._import_group)

        # Mode row (LINK / INSTANCE only)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode:"))
        self._mode_combo = QComboBox()
        for mode in Config.LINK_MODES:
            self._mode_combo.addItem(mode, mode)
        self._mode_combo.setCurrentText(Config.DEFAULT_LINK_MODE)
        mode_row.addWidget(self._mode_combo)
        import_layout.addLayout(mode_row)

        # Horizontal button row: Edit | Import | Replace
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setEnabled(False)
        self._edit_btn.setToolTip(
            "Append asset locally for editing (breaks library reference)"
        )
        self._edit_btn.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold; padding: 8px;"
        )
        btn_row.addWidget(self._edit_btn)

        self._import_btn = QPushButton("Import")
        self._import_btn.setEnabled(False)
        self._import_btn.setToolTip(
            "Import asset using the selected link mode"
        )
        self._import_btn.setStyleSheet(
            "background-color: #0078d4; color: white; font-weight: bold; padding: 8px;"
        )
        btn_row.addWidget(self._import_btn)

        self._replace_btn = QPushButton("Replace")
        self._replace_btn.setEnabled(False)
        self._replace_btn.setToolTip(
            "Replace selected objects in Blender with this asset"
        )
        self._replace_btn.setStyleSheet(
            "background-color: #e67e22; color: white; font-weight: bold; padding: 8px;"
        )
        btn_row.addWidget(self._replace_btn)

        import_layout.addLayout(btn_row)
        self._layout.addWidget(self._import_group)

    def _setup_review_state(self):
        """Setup review state UI elements."""
        # Submit review button
        self._submit_review_btn = QPushButton("Start Review \u25bc")
        self._submit_review_btn.setEnabled(False)
        self._submit_review_btn.setToolTip("Start a review cycle for this asset")
        self._submit_review_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled { background-color: #555555; color: #888888; }
        """)
        self._submit_review_btn.hide()

        # Cycle type menu
        self._cycle_type_menu = QMenu(self)
        self._cycle_type_menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                border: 1px solid #555;
            }
            QMenu::item { padding: 8px 24px; color: #e0e0e0; }
            QMenu::item:selected { background-color: #404040; }
        """)

        for cycle_type, info in REVIEW_CYCLE_TYPES.items():
            action = self._cycle_type_menu.addAction(info.get('label', cycle_type.title()))
            action.setData(cycle_type)

        self._layout.addWidget(self._submit_review_btn)

        # Review state widget
        self._review_state_widget = QWidget()
        review_state_layout = QHBoxLayout(self._review_state_widget)
        review_state_layout.setContentsMargins(0, 4, 0, 4)
        review_state_layout.setSpacing(8)

        self._review_state_label = QLabel()
        self._review_state_label.setStyleSheet("""
            QLabel { font-weight: bold; padding: 4px 8px; border-radius: 4px; }
        """)
        review_state_layout.addWidget(self._review_state_label)
        review_state_layout.addStretch()

        self._review_state_widget.hide()
        self._layout.addWidget(self._review_state_widget)

        # Create renderer
        self._review_renderer = ReviewStateRenderer(
            self._review_state_widget,
            self._review_state_label,
            self._submit_review_btn,
            self._cycle_type_menu
        )
        self._review_renderer.cycle_type_selected.connect(self._on_cycle_type_selected)

    def _setup_danger_zone(self):
        """Setup danger zone section with delete/retire button."""
        self._danger_group = QGroupBox()
        danger_layout = QVBoxLayout(self._danger_group)
        danger_layout.setSpacing(8)

        # Warning label
        self._danger_warning_label = QLabel("\u26A0  Danger Zone")
        self._danger_warning_label.setStyleSheet("""
            QLabel {
                color: #FF6B6B;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        danger_layout.addWidget(self._danger_warning_label)

        # Delete/Retire button - created here, styled by _update_danger_zone_style
        self._delete_btn = QPushButton()
        self._delete_btn.setEnabled(False)
        danger_layout.addWidget(self._delete_btn)

        self._layout.addWidget(self._danger_group)

        # Apply initial styling based on current mode
        self._update_danger_zone_style()

    def _update_danger_zone_style(self):
        """Update danger zone styling based on operation mode."""
        can_delete = self._control_authority.can_delete()

        if can_delete:
            # Standalone mode - permanent delete (red danger zone)
            self._danger_group.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #8B0000;
                    border-radius: 4px;
                    margin-top: 12px;
                    padding-top: 8px;
                    background-color: rgba(139, 0, 0, 0.1);
                }
            """)
            self._danger_warning_label.setText("\u26A0  Danger Zone")
            self._danger_warning_label.setStyleSheet("""
                QLabel {
                    color: #FF6B6B;
                    font-weight: bold;
                    font-size: 12px;
                }
            """)
            self._delete_btn.setText("\u26A0  Delete Asset")
            self._delete_btn.setToolTip(
                "PERMANENTLY delete this asset including:\n"
                "\u2022 All versions and variants\n"
                "\u2022 All files (USD, .blend, thumbnails)\n"
                "\u2022 All archived versions\n"
                "\u2022 All reviews, screenshots, and draw-overs\n\n"
                "This action cannot be undone!"
            )
            self._delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #8B0000;
                    color: white;
                    font-weight: bold;
                    padding: 10px;
                    border: 1px solid #FF0000;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #B22222;
                    border: 1px solid #FF4444;
                }
                QPushButton:disabled {
                    background-color: #3a3a3a;
                    color: #666666;
                    border: 1px solid #555555;
                }
            """)
        else:
            # Studio/Pipeline mode - retire (amber styling)
            self._danger_group.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #795548;
                    border-radius: 4px;
                    margin-top: 12px;
                    padding-top: 8px;
                    background-color: rgba(121, 85, 72, 0.1);
                }
            """)
            self._danger_warning_label.setText("Archive")
            self._danger_warning_label.setStyleSheet("""
                QLabel {
                    color: #BCAAA4;
                    font-weight: bold;
                    font-size: 12px;
                }
            """)
            self._delete_btn.setText("Retire Asset")
            self._delete_btn.setToolTip(
                "Move this asset to Retired:\n"
                "\u2022 All versions move together\n"
                "\u2022 Variants stay active\n"
                "\u2022 Can be restored by admin\n\n"
                "Asset will no longer appear in library."
            )
            self._delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #795548;
                    color: white;
                    font-weight: bold;
                    padding: 10px;
                    border: 1px solid #8D6E63;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #8D6E63;
                    border: 1px solid #A1887F;
                }
                QPushButton:disabled {
                    background-color: #3a3a3a;
                    color: #666666;
                    border: 1px solid #555555;
                }
            """)

    def _connect_signals(self):
        """Connect signals."""
        self._edit_btn.clicked.connect(self._on_edit_clicked)
        self._import_btn.clicked.connect(self._on_import_clicked)
        self._replace_btn.clicked.connect(self._on_replace_clicked)
        self._submit_review_btn.clicked.connect(self._on_submit_review_clicked)
        self._delete_btn.clicked.connect(self._on_delete_clicked)

        self._event_bus.asset_selected.connect(self._on_asset_selected)
        self._thumbnail_loader.thumbnail_loaded.connect(self._on_thumbnail_loaded)

        # Studio mode changes
        self._user_service.mode_changed.connect(self._on_studio_mode_changed)

        # Operation mode changes (for delete/retire button)
        self._control_authority.mode_changed.connect(self._on_operation_mode_changed)

    def _connect_entity_signals(self):
        """Connect entity event bus signals for auto-refresh."""
        # Refresh display when current entity is updated
        self._entity_event_bus.entity_updated.connect(self._on_entity_updated)
        self._entity_event_bus.metadata_values_changed.connect(self._on_metadata_changed)

        # Refresh field definitions when schema changes
        self._entity_event_bus.metadata_field_added.connect(self._on_field_schema_changed)
        self._entity_event_bus.metadata_field_removed.connect(self._on_field_schema_changed)

    def _on_entity_updated(self, entity_type: str, uuid: str):
        """Handle entity updated event - refresh if it's the current asset."""
        if entity_type == 'asset' and uuid == self._current_uuid:
            self.display_asset(uuid)

    def _on_metadata_changed(self, entity_type: str, uuid: str, changes: dict):
        """Handle metadata value changes - refresh if it's the current asset."""
        if entity_type == 'asset' and uuid == self._current_uuid:
            self.display_asset(uuid)

    def _on_field_schema_changed(self, entity_type: str, field_name: str, *args):
        """Handle field schema changes - refresh dynamic renderer."""
        if entity_type == 'asset':
            # Refresh field definitions in dynamic renderer
            self._dynamic_renderer.refresh_fields()
            # Re-render if we have a current asset
            if self._current_uuid:
                self.display_asset(self._current_uuid)

    def _on_asset_selected(self, uuid: str):
        """Handle asset selection from event bus."""
        if uuid:
            self.display_asset(uuid)
        else:
            self._clear_display()

    def display_asset(self, uuid: str):
        """Display asset details."""
        self._current_uuid = uuid
        self._current_asset = self._db_service.get_asset_by_uuid(uuid)

        if not self._current_asset:
            self._clear_display()
            return

        asset = self._current_asset

        # Name and type
        self._name_label.setText(asset.get('name', 'Unknown'))

        asset_type = asset.get('asset_type', 'unknown')
        type_color = Config.ASSET_TYPE_COLORS.get(asset_type, '#9E9E9E')
        self._type_label.setText(asset_type.capitalize())
        self._type_label.setStyleSheet(f"""
            QLabel {{
                background-color: {type_color};
                color: white;
                padding: 2px 8px;
                border-radius: 0px;
                font-size: 11px;
            }}
        """)

        # Panels
        self._id_panel.display(asset)

        # Get review status for comment count
        version_label = asset.get('version_label', 'v001')
        version_group_id = asset.get('version_group_id') or asset.get('asset_id')
        review_status = self._review_db.get_review_status(uuid, version_label, version_group_id)
        unresolved_count = review_status.get('unresolved_notes', 0)

        self._lineage_panel.display(asset, unresolved_count)

        # Representation designations (mesh and rig)
        if asset_type in ('mesh', 'rig'):
            self._update_representation_display(asset)

        # Technical info
        category = self._get_category_for_type(asset_type)
        self._tech_renderer.render(asset, category)

        # Dynamic metadata (for extended/custom fields from EAV)
        self._render_dynamic_metadata(asset, category)

        # Description
        description = asset.get('description', '')
        self._description_label.setText(description if description else '-')

        # Tags and folders
        self._tags_widget.set_asset(uuid)
        self._folders_widget.set_asset(uuid)

        self._edit_btn.setEnabled(True)
        self._import_btn.setEnabled(True)
        self._replace_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)

        # Review state (only in studio mode)
        if self._user_service.is_studio_mode():
            review_state = review_status.get('review_state')
            cycle_type = None
            state_manager = get_review_state_manager()
            cycle = state_manager.get_cycle_for_version(uuid, version_label)
            if cycle:
                cycle_type = cycle.get('cycle_type')

            asset_id_for_cycle = (
                asset.get('version_group_id') or asset.get('asset_id') or uuid
            )
            can_start = state_manager.can_start_new_cycle(asset_id_for_cycle)
            active_cycle = state_manager.get_active_cycle(asset_id_for_cycle)

            self._review_renderer.render(review_state, cycle_type, can_start, active_cycle)
        else:
            # Clear review UI in solo mode
            self._review_renderer.clear()

        # Thumbnail
        thumbnail_path = asset.get('thumbnail_path')
        if thumbnail_path:
            pixmap = self._thumbnail_loader.request_thumbnail(uuid, thumbnail_path, 280)
            if pixmap:
                self._thumbnail.set_thumbnail(pixmap)
            else:
                self._thumbnail.set_loading()
        else:
            self._thumbnail.set_no_preview()

    def _render_dynamic_metadata(self, asset: Dict[str, Any], category: str):
        """
        Render dynamic metadata fields from EAV storage.

        Shows any custom fields registered in metadata_fields that have values.
        This allows new fields to appear without code changes.

        Args:
            asset: Asset data dict (with EAV data merged)
            category: Asset category for filtering
        """
        # Render dynamic fields for this category
        # The renderer will auto-show/hide based on field values
        self._dynamic_renderer.render(
            asset,
            category=category,
            entity_uuid=asset.get('uuid')
        )

        # Show container if any fields are visible
        # Check if any category groups are visible
        has_visible = any(
            group.isVisible()
            for group in self._dynamic_renderer._category_groups.values()
        )
        self._dynamic_container.setVisible(has_visible)

    def _on_thumbnail_loaded(self, uuid: str, pixmap: QPixmap):
        """Handle thumbnail loaded."""
        if uuid == self._current_uuid:
            self._thumbnail.set_thumbnail(pixmap)

    def _clear_display(self):
        """Clear panel display."""
        self._current_uuid = None
        self._current_asset = None

        self._name_label.setText("No asset selected")
        self._type_label.setText("")
        self._type_label.setStyleSheet("")
        self._thumbnail.set_no_preview()

        self._id_panel.clear()
        self._lineage_panel.clear()
        self._tech_renderer.clear()
        self._dynamic_renderer.clear()
        self._dynamic_container.hide()
        self._description_label.setText("-")
        self._tags_widget.clear()
        self._folders_widget.clear()

        self._edit_btn.setEnabled(False)
        self._import_btn.setEnabled(False)
        self._replace_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)

        self._review_renderer.clear()

    def _on_history_clicked(self):
        """Handle version history button click."""
        if not self._current_asset:
            return

        version_group_id = self._current_asset.get('version_group_id')
        if not version_group_id:
            version_group_id = self._current_uuid

        dialog = VersionHistoryDialog(version_group_id, self)
        dialog.exec()

        if self._current_uuid:
            self.display_asset(self._current_uuid)
            self._event_bus.asset_updated.emit(self._current_uuid)

    def _on_edit_clicked(self):
        """Handle edit button click — always BLEND + APPEND."""
        if self._current_uuid:
            self.edit_requested.emit(self._current_uuid)

    def _on_import_clicked(self):
        """Handle import button click."""
        if self._current_uuid:
            link_mode = self._mode_combo.currentData()
            self.import_requested.emit(self._current_uuid, link_mode)
            self._event_bus.request_import_asset.emit(self._current_uuid)

    def _on_replace_clicked(self):
        """Handle replace selected button click."""
        if self._current_uuid:
            link_mode = self._mode_combo.currentData()
            self.replace_requested.emit(self._current_uuid, link_mode)

    def _on_delete_clicked(self):
        """Handle delete/retire button click - emit appropriate request via event bus."""
        if self._current_uuid:
            if self._control_authority.can_delete():
                # Standalone mode - permanent delete
                self._event_bus.request_delete_assets.emit([self._current_uuid])
            else:
                # Studio/Pipeline mode - retire instead
                self._event_bus.request_retire_assets.emit([self._current_uuid])

    def _on_submit_review_clicked(self):
        """Handle submit for review button click."""
        if not self._current_uuid or not self._current_asset:
            return
        self._review_renderer.show_menu_at_button()

    def _on_cycle_type_selected(self, cycle_type: str):
        """Handle cycle type selection from menu."""
        if not self._current_uuid or not self._current_asset:
            return

        user_service = get_user_service()
        current_user = user_service.get_current_username()

        # Get version_group_id to find the latest version
        version_group_id = (
            self._current_asset.get('version_group_id') or
            self._current_asset.get('asset_id') or
            self._current_uuid
        )

        # IMPORTANT: Fetch latest version from DB to avoid starting review on stale data
        # This ensures the review cycle starts on the actual latest version, not
        # whatever version was cached when the panel was loaded
        latest_version = self._db_service.get_latest_asset_version(version_group_id)
        if latest_version:
            version_label = latest_version.get('version_label', 'v001')
            asset_id_for_cycle = latest_version.get('version_group_id') or version_group_id
        else:
            # Fallback to cached data if latest not found
            version_label = self._current_asset.get('version_label', 'v001')
            asset_id_for_cycle = version_group_id

        state_manager = get_review_state_manager()
        success, message = state_manager.submit_for_review(
            asset_id_for_cycle,
            version_label,
            cycle_type=cycle_type,
            submitted_by=current_user
        )

        if success:
            self._review_renderer.render('needs_review', cycle_type, False, None)
            self._event_bus.asset_updated.emit(self._current_uuid)

            cycle_label = REVIEW_CYCLE_TYPES.get(cycle_type, {}).get('label', cycle_type.title())
            asset_name = self._current_asset.get('name', 'Unknown')
        else:
            pass

    def _on_studio_mode_changed(self, is_studio: bool):
        """Handle studio mode toggle (legacy - user management changes)."""
        # Refresh display if we have an asset selected
        if self._current_uuid:
            self.display_asset(self._current_uuid)

    def _update_review_visibility(self):
        """Update review UI visibility based on operation mode.
        
        Review features are visible in Studio and Pipeline modes only,
        hidden in Standalone mode.
        """
        from ...services.control_authority import OperationMode
        show_review = self._control_authority.get_operation_mode() != OperationMode.STANDALONE
        # Hide review button and state widget in standalone mode
        self._submit_review_btn.setVisible(show_review)
        self._review_state_widget.setVisible(show_review)

    def _on_operation_mode_changed(self, mode):
        """Handle operation mode change - update delete/retire button and review visibility."""
        self._update_danger_zone_style()
        self._update_review_visibility()
        # Refresh display if we have an asset selected
        if self._current_uuid:
            self.display_asset(self._current_uuid)

    # ==================== REPRESENTATION HANDLERS ====================

    def _update_representation_display(self, asset):
        """Fetch and display representation designations for the current asset."""
        try:
            from ...services.representation_service import get_representation_service
            rep_service = get_representation_service()
            version_group_id = asset.get('version_group_id') or asset.get('asset_id') or self._current_uuid
            variant_name = asset.get('variant_name', 'Base')

            # Get versions for dropdown population
            versions = self._db_service.get_asset_versions(version_group_id)

            # Get custom proxies for dropdown
            custom_proxies = self._db_service.get_custom_proxies(version_group_id, variant_name)

            if versions:
                self._lineage_panel.populate_version_dropdowns(versions, custom_proxies)

            # Get and display current designations
            designations = rep_service.get_effective_designations(version_group_id, variant_name)
            self._lineage_panel.display_representations(designations)
        except Exception as e:
            pass

    def _on_representation_apply(self, proxy_uuid, render_uuid, proxy_source='version'):
        """Handle representation apply - set proxy and render versions from dropdowns."""
        if not self._current_asset:
            return

        asset = self._current_asset
        asset_type = asset.get('asset_type', '')
        if asset_type not in ('mesh', 'rig'):
            return

        version_group_id = asset.get('version_group_id') or asset.get('asset_id') or self._current_uuid
        variant_name = asset.get('variant_name', 'Base')

        try:
            if proxy_source == 'custom' and proxy_uuid:
                # Use representation service for custom proxy designation
                from ...services.representation_service import get_representation_service
                rep_service = get_representation_service()
                success, msg = rep_service.designate_custom_proxy(
                    version_group_id, variant_name, proxy_uuid
                )
            else:
                # Use representation service for version-based proxy
                from ...services.representation_service import get_representation_service
                rep_service = get_representation_service()
                success, msg = rep_service.designate_representations(
                    version_group_id, variant_name,
                    proxy_uuid=proxy_uuid,
                    render_uuid=render_uuid,
                )

            if success:
                pass
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Representation Error", f"Failed to set representations:\n{msg}")
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Representation Error", f"Error updating representations:\n{e}")

        # Refresh display
        if self._current_uuid:
            self.display_asset(self._current_uuid)

    def _on_representation_regenerate(self):
        """Handle regenerate representation files request."""
        if not self._current_asset:
            return

        asset = self._current_asset
        version_group_id = asset.get('version_group_id') or asset.get('asset_id') or self._current_uuid
        variant_name = asset.get('variant_name', 'Base')

        # Get current designation to know which UUIDs to use
        designation = self._db_service.get_representation_designation(version_group_id, variant_name)
        proxy_uuid = designation.get('proxy_version_uuid') if designation else None
        render_uuid = designation.get('render_version_uuid') if designation else None
        proxy_source = designation.get('proxy_source', 'version') if designation else 'version'

        try:
            from ...services.representation_service import get_representation_service
            rep_service = get_representation_service()

            if proxy_source == 'custom' and proxy_uuid:
                # Custom proxy designation
                success, msg = rep_service.designate_custom_proxy(
                    version_group_id, variant_name, proxy_uuid
                )
            else:
                # Version-based proxy designation
                success, msg = rep_service.designate_representations(
                    version_group_id, variant_name,
                    proxy_uuid=proxy_uuid,
                    render_uuid=render_uuid,
                )

            if success:
                pass
            else:
                pass
        except Exception as e:
            pass

        if self._current_uuid:
            self.display_asset(self._current_uuid)

    def _on_representation_clear(self):
        """Handle clear representation designations request."""
        if not self._current_asset:
            return

        asset = self._current_asset
        version_group_id = asset.get('version_group_id') or asset.get('asset_id') or self._current_uuid
        variant_name = asset.get('variant_name', 'Base')

        try:
            from ...services.representation_service import get_representation_service
            rep_service = get_representation_service()
            success, msg = rep_service.clear_designations(version_group_id, variant_name)
            if success:
                pass
            else:
                pass
        except Exception as e:
            pass

        if self._current_uuid:
            self.display_asset(self._current_uuid)

    def get_import_method(self) -> str:
        """Get import method — always BLEND."""
        return "BLEND"

    def get_link_mode(self) -> str:
        """Get currently selected link mode."""
        return self._mode_combo.currentData() or Config.DEFAULT_LINK_MODE


__all__ = ['MetadataPanel']
