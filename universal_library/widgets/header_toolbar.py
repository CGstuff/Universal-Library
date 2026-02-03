"""
HeaderToolbar - Main toolbar with search and controls

Pattern: QWidget with horizontal layout
Based on animation_library architecture.
"""

from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton,
    QSlider, QLabel, QComboBox, QCheckBox, QMenu, QWidgetAction
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QAction

from ..config import Config
from ..events.event_bus import get_event_bus
from ..services.control_authority import get_control_authority

# Path to utility icons
ICONS_DIR = Path(__file__).parent / "icons" / "utility"


class HeaderToolbar(QWidget):
    """
    Header toolbar with search and view controls

    Features:
    - Search box with debounced filtering
    - View mode toggle (grid/list)
    - Card size slider (grid mode)
    - Asset type filter dropdown
    - Sort dropdown
    - Scan and settings buttons

    Layout:
        [Search] [Type Filter] [Sort] | [Grid/List] [Size] | [Scan] [Settings]
    """

    # Signals
    search_text_changed = pyqtSignal(str)
    view_mode_changed = pyqtSignal(str)  # "grid", "list", or "tree"
    card_size_changed = pyqtSignal(int)
    asset_type_filter_changed = pyqtSignal(str)  # "" for all, or specific type
    status_filter_changed = pyqtSignal(str)  # "" for all, or specific status
    tag_filter_changed = pyqtSignal(list)  # list of tag_ids to filter by
    sort_changed = pyqtSignal(str, str)  # (sort_by, sort_order)
    refresh_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    about_clicked = pyqtSignal()
    retired_assets_clicked = pyqtSignal()  # Open retired assets dialog
    edit_mode_changed = pyqtSignal(bool)  # enabled/disabled
    group_by_family_changed = pyqtSignal(bool)  # group variants with their base

    def __init__(self, parent=None):
        super().__init__(parent)

        # Set header property for theme-based styling
        self.setProperty("header", "true")
        # Enable styled background for gradient to work
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Fixed height like animation_library
        self.setFixedHeight(50)

        self._event_bus = get_event_bus()
        self._control_authority = get_control_authority()

        # State
        self._view_mode = "grid"
        self._card_size = Config.DEFAULT_CARD_SIZE
        self._edit_mode = False

        # Debounce timer for search
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._emit_search)

        # Setup UI
        self._create_widgets()
        self._create_layout()
        self._connect_signals()

        # Force Qt to reapply stylesheet for dynamic property
        self.style().unpolish(self)
        self.style().polish(self)

    def _create_widgets(self):
        """Create toolbar widgets"""

        # Search box
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search assets...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setFixedWidth(200)

        # Asset type filter dropdown
        self._type_combo = QComboBox()
        self._type_combo.addItem("All Types", "")
        for asset_type in Config.ASSET_TYPES:
            self._type_combo.addItem(asset_type.capitalize(), asset_type)
        self._type_combo.setFixedWidth(120)
        self._type_combo.setToolTip("Filter by asset type")

        # Status filter dropdown (from Config)
        self._status_combo = QComboBox()
        self._status_combo.addItem("All Status", "")
        for key, info in Config.LIFECYCLE_STATUSES.items():
            if key != 'none':  # Skip 'none' in filter
                self._status_combo.addItem(info['label'], key)
        self._status_combo.setFixedWidth(100)
        self._status_combo.setToolTip("Filter by workflow status")

        # Tag filter button with dropdown menu
        self._tag_filter_btn = QPushButton("Tags")
        self._tag_filter_btn.setFixedWidth(70)
        self._tag_filter_btn.setToolTip("Filter by tags")
        self._tag_filter_menu = QMenu(self._tag_filter_btn)
        self._tag_filter_btn.setMenu(self._tag_filter_menu)
        self._selected_tag_ids = []  # Track selected tags

        # Sort dropdown
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Name A-Z", ("name", "ASC"))
        self._sort_combo.addItem("Name Z-A", ("name", "DESC"))
        self._sort_combo.addItem("Newest", ("created_date", "DESC"))
        self._sort_combo.addItem("Oldest", ("created_date", "ASC"))
        self._sort_combo.addItem("Size ↑", ("file_size", "ASC"))
        self._sort_combo.addItem("Size ↓", ("file_size", "DESC"))
        self._sort_combo.addItem("Polys ↑", ("polygon_count", "ASC"))
        self._sort_combo.addItem("Polys ↓", ("polygon_count", "DESC"))
        self._sort_combo.setFixedWidth(100)
        self._sort_combo.setToolTip("Sort assets")

        # View mode toggle button (cycles: grid -> list -> tree)
        self._view_mode_btn = QPushButton()
        self._view_mode_btn.setCheckable(False)
        self._view_mode_btn.setToolTip("Cycle View: Grid / List / Tree")
        view_icon_path = ICONS_DIR / "view_mode.svg"
        if view_icon_path.exists():
            self._view_mode_btn.setIcon(QIcon(str(view_icon_path)))
            self._view_mode_btn.setIconSize(QSize(20, 20))
            self._view_mode_btn.setFixedSize(32, 32)

        # Card size slider with grid icon (like animation_library)
        self._size_label = QLabel("Size:")
        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setProperty("cardsize", "true")  # Property for CSS selector
        self._size_slider.setMinimum(Config.MIN_CARD_SIZE)
        self._size_slider.setMaximum(Config.MAX_CARD_SIZE)
        self._size_slider.setValue(self._card_size)
        self._size_slider.setSingleStep(Config.CARD_SIZE_STEP)
        self._size_slider.setFixedWidth(100)
        self._size_slider.setToolTip(f"Card size ({Config.MIN_CARD_SIZE}-{Config.MAX_CARD_SIZE}px)")

        # Quick import checkbox
        self._quick_import_cb = QCheckBox("Quick Import")
        self._quick_import_cb.setToolTip("Enable double-click to instantly import assets")
        self._quick_import_cb.setChecked(False)

        # Edit mode toggle button (icon-only)
        self._edit_mode_btn = QPushButton()
        self._edit_mode_btn.setCheckable(True)
        self._edit_mode_btn.setChecked(False)
        self._edit_mode_btn.setToolTip("Toggle Edit Mode for bulk operations")
        edit_icon_path = ICONS_DIR / "edit.svg"
        if edit_icon_path.exists():
            self._edit_mode_btn.setIcon(QIcon(str(edit_icon_path)))
            self._edit_mode_btn.setIconSize(QSize(20, 20))
            self._edit_mode_btn.setFixedSize(32, 32)

        # Group by family checkbox
        self._group_by_family_cb = QCheckBox("Group by Family")
        self._group_by_family_cb.setToolTip("Group variants next to their base asset")
        self._group_by_family_cb.setChecked(False)

        # Refresh button
        self._refresh_btn = QPushButton()
        self._refresh_btn.setToolTip("Refresh assets from database")
        refresh_icon_path = ICONS_DIR / "file_refresh.svg"
        if refresh_icon_path.exists():
            self._refresh_btn.setIcon(QIcon(str(refresh_icon_path)))
            self._refresh_btn.setIconSize(QSize(18, 18))
            self._refresh_btn.setFixedSize(32, 32)
        else:
            self._refresh_btn.setText("Refresh")
            self._refresh_btn.setFixedWidth(60)

        # Settings button
        self._settings_btn = QPushButton()
        self._settings_btn.setToolTip("Open settings")
        settings_icon_path = ICONS_DIR / "settings.svg"
        if settings_icon_path.exists():
            self._settings_btn.setIcon(QIcon(str(settings_icon_path)))
            self._settings_btn.setIconSize(QSize(18, 18))
            self._settings_btn.setFixedSize(32, 32)
        else:
            self._settings_btn.setText("Settings")
            self._settings_btn.setFixedWidth(70)

        # About button
        self._about_btn = QPushButton()
        self._about_btn.setToolTip("About Universal Library")
        about_icon_path = ICONS_DIR / "about.svg"
        if about_icon_path.exists():
            self._about_btn.setIcon(QIcon(str(about_icon_path)))
            self._about_btn.setIconSize(QSize(18, 18))
            self._about_btn.setFixedSize(32, 32)
        else:
            self._about_btn.setText("About")
            self._about_btn.setFixedWidth(60)

        # Retired Assets button (visible only in Studio/Pipeline Mode)
        self._retired_assets_btn = QPushButton("Retired")
        self._retired_assets_btn.setToolTip("View and restore retired assets")
        self._retired_assets_btn.setStyleSheet("""
            QPushButton {
                background-color: #795548;
                color: white;
                padding: 4px 10px;
                border-radius: 0px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #8D6E63; }
        """)
        self._retired_assets_btn.setVisible(False)

        # Pipeline Mode indicator (visible only in Pipeline Mode)
        self._pipeline_mode_label = QLabel("PIPELINE MODE")
        self._pipeline_mode_label.setStyleSheet("""
            QLabel {
                background-color: #3498DB;
                color: white;
                padding: 4px 8px;
                border-radius: 0px;
                font-weight: bold;
                font-size: 10px;
            }
        """)
        self._pipeline_mode_label.setToolTip(
            "Asset status is controlled by Pipeline Control.\n"
            "Status changes are read-only in Universal Library."
        )
        self._pipeline_mode_label.setVisible(False)

    def _create_layout(self):
        """Create toolbar layout"""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)  # Match animation_library: 15px left/right, no top/bottom
        layout.setSpacing(8)

        # Left section: Search and filters
        layout.addWidget(self._search_box)
        layout.addWidget(self._type_combo)
        layout.addWidget(self._status_combo)
        layout.addWidget(self._tag_filter_btn)
        layout.addWidget(self._sort_combo)

        layout.addSpacing(16)

        # Middle section: View controls
        layout.addWidget(self._view_mode_btn)
        layout.addWidget(self._size_label)
        layout.addWidget(self._size_slider)

        layout.addSpacing(16)

        # Quick import toggle
        layout.addWidget(self._quick_import_cb)

        # Edit mode toggle
        layout.addWidget(self._edit_mode_btn)

        # Group by family toggle
        layout.addWidget(self._group_by_family_cb)

        # Refresh button
        layout.addWidget(self._refresh_btn)

        # Stretch to push right section to the end
        layout.addStretch()

        # Retired Assets button (before Pipeline Mode indicator)
        layout.addWidget(self._retired_assets_btn)
        layout.addSpacing(8)

        # Pipeline Mode indicator (before settings)
        layout.addWidget(self._pipeline_mode_label)
        layout.addSpacing(8)

        # Right section: About and Settings
        layout.addWidget(self._about_btn)
        layout.addWidget(self._settings_btn)

    def _connect_signals(self):
        """Connect internal signals"""

        # Search box with debounce
        self._search_box.textChanged.connect(self._on_search_text_changed)

        # Filters
        self._type_combo.currentIndexChanged.connect(self._on_type_filter_changed)
        self._status_combo.currentIndexChanged.connect(self._on_status_filter_changed)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)

        # View controls
        self._view_mode_btn.clicked.connect(self._on_view_mode_clicked)
        self._size_slider.valueChanged.connect(self._on_card_size_changed)

        # Edit mode
        self._edit_mode_btn.clicked.connect(self._on_edit_mode_clicked)

        # Group by family
        self._group_by_family_cb.stateChanged.connect(self._on_group_by_family_changed)

        # Action buttons
        self._refresh_btn.clicked.connect(self.refresh_clicked.emit)
        self._settings_btn.clicked.connect(self.settings_clicked.emit)
        self._about_btn.clicked.connect(self.about_clicked.emit)
        self._retired_assets_btn.clicked.connect(self.retired_assets_clicked.emit)

        # Control authority - mode changes
        self._control_authority.mode_changed.connect(self._update_pipeline_mode_indicator)
        
        # Initial update
        self._update_pipeline_mode_indicator()

    def _on_search_text_changed(self, text: str):
        """Handle search text change with debounce"""
        self._search_timer.stop()
        self._search_timer.start(Config.SEARCH_DEBOUNCE_MS)

    def _emit_search(self):
        """Emit search text after debounce"""
        text = self._search_box.text()
        self.search_text_changed.emit(text)
        self._event_bus.emit_search_text_changed(text)

    def _on_type_filter_changed(self, index: int):
        """Handle asset type filter change"""
        asset_type = self._type_combo.currentData()
        self.asset_type_filter_changed.emit(asset_type)

    def _on_status_filter_changed(self, index: int):
        """Handle status filter change"""
        status = self._status_combo.currentData()
        self.status_filter_changed.emit(status)

    def _on_sort_changed(self, index: int):
        """Handle sort option change"""
        sort_data = self._sort_combo.currentData()
        if sort_data:
            sort_by, sort_order = sort_data
            self.sort_changed.emit(sort_by, sort_order)

    def _on_view_mode_clicked(self):
        """Handle view mode button click - cycles grid -> list -> tree"""
        cycle = {"grid": "list", "list": "tree", "tree": "grid"}
        self._view_mode = cycle.get(self._view_mode, "grid")

        # Slider only enabled in grid mode
        is_grid = self._view_mode == "grid"
        self._size_slider.setEnabled(is_grid)
        self._size_label.setEnabled(is_grid)

        # Group by family is redundant in tree mode (tree IS grouped by family)
        self._group_by_family_cb.setEnabled(self._view_mode != "tree")

        # Update tooltip to show current mode
        mode_label = self._view_mode.capitalize()
        self._view_mode_btn.setToolTip(f"View: {mode_label} (click to cycle)")

        self.view_mode_changed.emit(self._view_mode)
        self._event_bus.emit_view_mode_changed(self._view_mode)

    def _on_card_size_changed(self, size: int):
        """Handle card size slider change"""
        self._card_size = size
        self.card_size_changed.emit(size)
        self._event_bus.emit_card_size_changed(size)

    def _on_edit_mode_clicked(self):
        """Handle edit mode button click"""
        self._edit_mode = self._edit_mode_btn.isChecked()
        self.edit_mode_changed.emit(self._edit_mode)
        self._event_bus.emit_edit_mode_changed(self._edit_mode)

    def _on_group_by_family_changed(self, state: int):
        """Handle group by family checkbox change"""
        group = state == Qt.CheckState.Checked.value
        self.group_by_family_changed.emit(group)

    # ==================== TAG FILTER ====================

    def refresh_tag_filter(self, tags: list):
        """
        Refresh the tag filter menu with available tags

        Args:
            tags: List of tag dicts with id, name, color, count
        """
        self._tag_filter_menu.clear()

        if not tags:
            no_tags_action = self._tag_filter_menu.addAction("No tags available")
            no_tags_action.setEnabled(False)
            return

        # Add "Clear All" action
        clear_action = self._tag_filter_menu.addAction("Clear Filter")
        clear_action.triggered.connect(self._clear_tag_filter)
        self._tag_filter_menu.addSeparator()

        # Add checkable tag items
        for tag in tags:
            tag_id = tag.get('id')
            tag_name = tag.get('name', 'Unknown')
            tag_color = tag.get('color', '#607D8B')
            count = tag.get('count', 0)

            action = QAction(f"{tag_name} ({count})", self._tag_filter_menu)
            action.setCheckable(True)
            action.setChecked(tag_id in self._selected_tag_ids)
            action.setData(tag_id)

            # Use stylesheet for color indicator
            action.triggered.connect(lambda checked, tid=tag_id: self._on_tag_toggled(tid, checked))

            self._tag_filter_menu.addAction(action)

        self._update_tag_button_text()

    def _on_tag_toggled(self, tag_id: int, checked: bool):
        """Handle tag checkbox toggle"""
        if checked:
            if tag_id not in self._selected_tag_ids:
                self._selected_tag_ids.append(tag_id)
        else:
            if tag_id in self._selected_tag_ids:
                self._selected_tag_ids.remove(tag_id)

        self._update_tag_button_text()
        self.tag_filter_changed.emit(self._selected_tag_ids.copy())

    def _clear_tag_filter(self):
        """Clear all tag filters"""
        self._selected_tag_ids = []

        # Uncheck all actions
        for action in self._tag_filter_menu.actions():
            if action.isCheckable():
                action.setChecked(False)

        self._update_tag_button_text()
        self.tag_filter_changed.emit([])

    def _update_tag_button_text(self):
        """Update button text to show selected count"""
        count = len(self._selected_tag_ids)
        if count == 0:
            self._tag_filter_btn.setText("Tags")
        elif count == 1:
            self._tag_filter_btn.setText("1 Tag")
        else:
            self._tag_filter_btn.setText(f"{count} Tags")

    def get_selected_tags(self) -> list:
        """Get list of selected tag IDs"""
        return self._selected_tag_ids.copy()

    # ==================== PUBLIC METHODS ====================

    def get_view_mode(self) -> str:
        """Get current view mode"""
        return self._view_mode

    def get_card_size(self) -> int:
        """Get current card size"""
        return self._card_size

    def get_search_text(self) -> str:
        """Get current search text"""
        return self._search_box.text()

    def set_search_text(self, text: str):
        """Set search text programmatically"""
        self._search_box.setText(text)

    def clear_search(self):
        """Clear search text"""
        self._search_box.clear()

    def is_quick_import_enabled(self) -> bool:
        """Check if quick import (double-click) is enabled"""
        return self._quick_import_cb.isChecked()

    def is_edit_mode(self) -> bool:
        """Check if edit mode is enabled"""
        return self._edit_mode

    def is_group_by_family_enabled(self) -> bool:
        """Check if group by family is enabled"""
        return self._group_by_family_cb.isChecked()

    def _update_pipeline_mode_indicator(self, mode=None):
        """Update Pipeline Mode indicator and Retired Assets button visibility."""
        is_pipeline = self._control_authority.is_pipeline_mode()
        is_studio = self._control_authority.is_studio_mode()

        self._pipeline_mode_label.setVisible(is_pipeline)
        # Show Retired Assets button in Studio or Pipeline mode (where retire is used)
        self._retired_assets_btn.setVisible(is_studio or is_pipeline)


__all__ = ['HeaderToolbar']
