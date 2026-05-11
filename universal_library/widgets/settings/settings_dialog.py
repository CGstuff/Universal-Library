"""
SettingsDialog - Application settings dialog

Pattern: QDialog with sidebar list + stacked pages (Photoshop/Blender style)
Based on animation_library architecture.
"""

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QStackedWidget, QDialogButtonBox, QFrame
)

from ...config import Config
from .storage_tab import StorageTab
from .blender_tab import BlenderTab
from .appearance_tab import AppearanceTab
from .tags_tab import TagsTab
from .maintenance_tab import MaintenanceTab
from .backup_tab import BackupTab
from .operation_mode_tab import OperationModeTab


class SettingsDialog(QDialog):
    """
    Main settings dialog with sidebar navigation

    Features:
    - Sidebar list of categories (Photoshop/Blender prefs style)
    - Stacked page area on the right
    - OK/Cancel/Apply buttons

    Usage:
        dialog = SettingsDialog(parent=main_window)
        if dialog.exec():
            # Settings were saved
            pass
    """

    # Width of the left-hand category list
    SIDEBAR_WIDTH = 170

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(f"Settings - {Config.APP_NAME}")
        self.setModal(True)
        self.resize(780, 520)

        self._tabs = []  # list of (label, widget) for save_settings dispatch
        self._create_ui()

    def _create_ui(self):
        """Create UI layout"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Body: sidebar + stacked pages ----
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Sidebar list
        self._sidebar = QListWidget()
        self._sidebar.setObjectName("settingsSidebar")
        self._sidebar.setFixedWidth(self.SIDEBAR_WIDTH)
        self._sidebar.setFrameShape(QFrame.Shape.NoFrame)
        self._sidebar.setUniformItemSizes(True)
        self._sidebar.setIconSize(QSize(16, 16))
        self._sidebar.setSpacing(0)
        self._sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Stacked pages
        self._stack = QStackedWidget()
        self._stack.setObjectName("settingsStack")

        body.addWidget(self._sidebar)
        body.addWidget(self._stack, 1)

        # Instantiate and register tabs
        self._storage_tab = StorageTab(self)
        self._blender_tab = BlenderTab(self)
        self._appearance_tab = AppearanceTab(self)
        self._tags_tab = TagsTab(self)
        self._maintenance_tab = MaintenanceTab(self)
        self._backup_tab = BackupTab(self)
        self._operation_mode_tab = OperationModeTab(self)

        for label, widget in [
            ("Storage",        self._storage_tab),
            ("Blender",        self._blender_tab),
            ("Appearance",     self._appearance_tab),
            ("Tags",           self._tags_tab),
            ("Maintenance",    self._maintenance_tab),
            ("Backup",         self._backup_tab),
            ("Operation Mode", self._operation_mode_tab),
        ]:
            self._add_page(label, widget)

        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._sidebar.setCurrentRow(0)

        # Apply sidebar styling
        self._sidebar.setStyleSheet(self._sidebar_qss())

        # Restyle live if the user changes the theme inside this dialog
        try:
            from ...themes import get_theme_manager
            get_theme_manager().theme_changed.connect(self._refresh_sidebar_style)
        except Exception:
            pass

        # Wrap body in a frame for layout
        body_widget = QFrame()
        body_widget.setLayout(body)
        outer.addWidget(body_widget, 1)

        # ---- Button box ----
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._on_apply
        )

        button_row = QHBoxLayout()
        button_row.setContentsMargins(12, 8, 12, 12)
        button_row.addStretch(1)
        button_row.addWidget(button_box)
        outer.addLayout(button_row)

    def _add_page(self, label: str, widget):
        """Add one (label, widget) pair to the sidebar + stack."""
        item = QListWidgetItem(label)
        item.setSizeHint(QSize(self.SIDEBAR_WIDTH, 32))
        self._sidebar.addItem(item)
        self._stack.addWidget(widget)
        self._tabs.append((label, widget))

    def _sidebar_qss(self) -> str:
        """Sidebar styling — pulls colors from the active theme palette."""
        from ...themes import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        if theme is None:
            # Fallback colors (dark)
            sidebar_bg = "#1a1a1a"
            border = "#404040"
            text = "#e0e0e0"
            hover_bg = "#2d2d2d"
            sel_bg = "#0078d4"
            sel_text = "#ffffff"
        else:
            p = theme.palette
            sidebar_bg = p.background_secondary
            border = p.border
            text = p.text_primary
            hover_bg = p.list_item_hover
            sel_bg = p.list_item_selected
            sel_text = "#ffffff"

        return f"""
        QListWidget#settingsSidebar {{
            background: {sidebar_bg};
            border: none;
            border-right: 1px solid {border};
            outline: 0;
            padding-top: 6px;
            color: {text};
        }}
        QListWidget#settingsSidebar::item {{
            padding: 6px 14px;
            border: none;
            color: {text};
        }}
        QListWidget#settingsSidebar::item:hover {{
            background: {hover_bg};
        }}
        QListWidget#settingsSidebar::item:selected {{
            background: {sel_bg};
            color: {sel_text};
        }}
        """

    def _refresh_sidebar_style(self, *_):
        """Re-apply the sidebar QSS when the active theme changes."""
        self._sidebar.setStyleSheet(self._sidebar_qss())

    def _on_apply(self):
        """Handle Apply button - save settings without closing dialog"""
        self._storage_tab.save_settings()
        self._blender_tab.save_settings()
        self._appearance_tab.save_settings()
        self._tags_tab.save_settings()
        self._maintenance_tab.save_settings()
        self._operation_mode_tab.save_settings()

    def accept(self):
        """Handle OK button - save and close"""
        self._on_apply()
        super().accept()


__all__ = ['SettingsDialog']
