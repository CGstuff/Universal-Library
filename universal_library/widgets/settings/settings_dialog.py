"""
SettingsDialog - Application settings dialog

Pattern: QDialog with QTabWidget
Based on animation_library architecture.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QDialogButtonBox
)

from ...config import Config
from .storage_tab import StorageTab
from .blender_tab import BlenderTab
from .appearance_tab import AppearanceTab
from .tags_tab import TagsTab
from .maintenance_tab import MaintenanceTab
from .backup_tab import BackupTab
from .user_tab import UserTab
from .operation_mode_tab import OperationModeTab


class SettingsDialog(QDialog):
    """
    Main settings dialog with tabbed interface

    Features:
    - Storage locations (database, cache paths)
    - Blender integration settings
    - Appearance settings
    - OK/Cancel/Apply buttons

    Usage:
        dialog = SettingsDialog(parent=main_window)
        if dialog.exec():
            # Settings were saved
            pass
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(f"Settings - {Config.APP_NAME}")
        self.setModal(True)
        self.resize(600, 450)

        self._create_ui()

    def _create_ui(self):
        """Create UI layout"""
        layout = QVBoxLayout(self)

        # Tab widget
        self._tab_widget = QTabWidget()

        # Storage tab
        self._storage_tab = StorageTab(self)
        self._tab_widget.addTab(self._storage_tab, "Storage")

        # Blender Integration tab
        self._blender_tab = BlenderTab(self)
        self._tab_widget.addTab(self._blender_tab, "Blender")

        # Appearance tab
        self._appearance_tab = AppearanceTab(self)
        self._tab_widget.addTab(self._appearance_tab, "Appearance")

        # Tags tab
        self._tags_tab = TagsTab(self)
        self._tab_widget.addTab(self._tags_tab, "Tags")

        # Maintenance tab (database status and upgrades)
        self._maintenance_tab = MaintenanceTab(self)
        self._tab_widget.addTab(self._maintenance_tab, "Maintenance")

        # Backup tab (export/import library)
        self._backup_tab = BackupTab(self)
        self._tab_widget.addTab(self._backup_tab, "Backup")

        # User tab (solo/studio mode, user management)
        self._user_tab = UserTab(self)
        self._tab_widget.addTab(self._user_tab, "Users")

        # Operation Mode tab (standalone/studio/pipeline mode for Pipeline Control integration)
        self._operation_mode_tab = OperationModeTab(self)
        self._tab_widget.addTab(self._operation_mode_tab, "Operation Mode")

        layout.addWidget(self._tab_widget)

        # Button box
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

        layout.addWidget(button_box)

    def _on_apply(self):
        """Handle Apply button - save settings without closing dialog"""
        self._storage_tab.save_settings()
        self._blender_tab.save_settings()
        self._appearance_tab.save_settings()
        self._tags_tab.save_settings()
        self._maintenance_tab.save_settings()
        self._user_tab.save_settings()
        self._operation_mode_tab.save_settings()

    def accept(self):
        """Handle OK button - save and close"""
        self._on_apply()
        super().accept()


__all__ = ['SettingsDialog']
