"""
FoldersWidget - Folder membership management for assets.
"""

from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QComboBox, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal


class FoldersWidget(QWidget):
    """
    Widget for managing asset folder membership.

    Features:
    - Display current folders as clickable pills
    - Dropdown to add to new folders
    - Remove from folders by clicking X (except last folder)

    Signals:
        folder_added: Emitted when added to folder (uuid, folder_id)
        folder_removed: Emitted when removed from folder (uuid, folder_id)
        folders_changed: Emitted when folders change (uuid, [folder_ids])
    """

    folder_added = pyqtSignal(str, int)  # uuid, folder_id
    folder_removed = pyqtSignal(str, int)  # uuid, folder_id
    folders_changed = pyqtSignal(str, list)  # uuid, [folder_ids]

    def __init__(self, db_service, parent=None):
        super().__init__(parent)
        self._db_service = db_service
        self._current_uuid: Optional[str] = None
        self._current_folder_ids: List[int] = []
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._group = QGroupBox("Folders")
        group_layout = QVBoxLayout(self._group)
        group_layout.setSpacing(4)

        # Folder pills container
        self._folders_container = QWidget()
        self._folders_flow = QHBoxLayout(self._folders_container)
        self._folders_flow.setContentsMargins(0, 0, 0, 0)
        self._folders_flow.setSpacing(4)
        group_layout.addWidget(self._folders_container)

        # Add folder dropdown
        add_folder_row = QHBoxLayout()
        self._folder_dropdown = QComboBox()
        self._folder_dropdown.setFixedHeight(24)
        self._folder_dropdown.setPlaceholderText("Add to folder...")
        self._folder_dropdown.activated.connect(self._on_folder_selected)
        add_folder_row.addWidget(self._folder_dropdown, 1)
        group_layout.addLayout(add_folder_row)

        layout.addWidget(self._group)

    def set_asset(self, uuid: str):
        """Set current asset and refresh display."""
        self._current_uuid = uuid

        # Get folders for this asset
        folders_v2 = self._db_service.get_asset_folders(uuid)
        self._update_display(folders_v2)
        self._refresh_dropdown()

    def _update_display(self, folders_v2: list):
        """Update the folders display."""
        # Clear existing folder pills
        while self._folders_flow.count():
            item = self._folders_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if folders_v2:
            self._current_folder_ids = [f.get('id') for f in folders_v2 if f.get('id')]

            for folder in folders_v2:
                folder_id = folder.get('id')
                folder_name = folder.get('name', 'Unknown')
                folder_path = folder.get('path', folder_name)

                # Only show X if more than one folder (can't remove last)
                if len(folders_v2) > 1:
                    folder_btn = QPushButton(f"{folder_name} \u00d7")
                    folder_btn.setToolTip(f"Click to remove from '{folder_path}'")
                    folder_btn.clicked.connect(lambda checked, fid=folder_id: self._on_remove_folder(fid))
                else:
                    folder_btn = QPushButton(folder_name)
                    folder_btn.setToolTip(f"In folder: {folder_path}")

                folder_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                folder_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #4a6785;
                        color: white;
                        padding: 2px 6px;
                        border-radius: 0px;
                        border: none;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: #5a7795;
                    }
                """)
                self._folders_flow.addWidget(folder_btn)

            self._folders_flow.addStretch()
        else:
            self._current_folder_ids = []
            no_folders = QLabel("Not in any folder")
            no_folders.setStyleSheet("color: #606060;")
            self._folders_flow.addWidget(no_folders)

    def _on_folder_selected(self, index: int):
        """Handle folder selection from dropdown."""
        if not self._current_uuid or index < 0:
            return

        folder_id = self._folder_dropdown.itemData(index)
        if not folder_id:
            return

        if folder_id not in self._current_folder_ids:
            if self._db_service.add_asset_to_folder(self._current_uuid, folder_id):
                self._current_folder_ids.append(folder_id)

                # Refresh display
                folders_v2 = self._db_service.get_asset_folders(self._current_uuid)
                self._update_display(folders_v2)
                self._refresh_dropdown()

                # Emit signals
                self.folder_added.emit(self._current_uuid, folder_id)
                self.folders_changed.emit(self._current_uuid, self._current_folder_ids.copy())

        # Reset dropdown
        self._folder_dropdown.setCurrentIndex(-1)

    def _on_remove_folder(self, folder_id: int):
        """Handle removing asset from a folder."""
        if not self._current_uuid:
            return

        # Don't allow removing the last folder
        if len(self._current_folder_ids) <= 1:
            return

        if self._db_service.remove_asset_from_folder(self._current_uuid, folder_id):
            if folder_id in self._current_folder_ids:
                self._current_folder_ids.remove(folder_id)

            # Refresh display
            folders_v2 = self._db_service.get_asset_folders(self._current_uuid)
            self._update_display(folders_v2)
            self._refresh_dropdown()

            # Emit signals
            self.folder_removed.emit(self._current_uuid, folder_id)
            self.folders_changed.emit(self._current_uuid, self._current_folder_ids.copy())

    def _refresh_dropdown(self):
        """Refresh folder dropdown with available folders."""
        self._folder_dropdown.clear()

        # Get all user folders (not root)
        all_folders = self._db_service.get_all_folders()
        root_id = self._db_service.get_root_folder_id()

        # Filter out root and already-assigned folders
        available_folders = [
            f for f in all_folders
            if f.get('id') != root_id and f.get('id') not in self._current_folder_ids
        ]

        if not available_folders:
            self._folder_dropdown.setEnabled(False)
            self._folder_dropdown.setPlaceholderText("No more folders available")
        else:
            self._folder_dropdown.setEnabled(True)
            self._folder_dropdown.setPlaceholderText("Add to folder...")
            for folder in available_folders:
                display_name = folder.get('path') or folder.get('name', 'Unknown')
                self._folder_dropdown.addItem(display_name, folder.get('id'))

        self._folder_dropdown.setCurrentIndex(-1)

    def clear(self):
        """Clear display."""
        self._current_uuid = None
        self._current_folder_ids = []
        self._update_display([])

    @property
    def current_folder_ids(self) -> List[int]:
        """Get current folder IDs."""
        return self._current_folder_ids.copy()


__all__ = ['FoldersWidget']
