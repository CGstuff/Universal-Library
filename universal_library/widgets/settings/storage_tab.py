"""
StorageTab - Storage location settings tab

Pattern: QWidget for settings tab
Based on animation_library architecture.
"""

import subprocess
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QFileDialog, QMessageBox
)

from ...config import Config


class StorageTab(QWidget):
    """
    Storage location settings tab

    Features:
    - Single configurable storage location
    - Database/cache stored in hidden .assetlibrary folder inside storage
    - Folder browsing functionality
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """Initialize UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Storage Location Group (Primary)
        storage_group = QGroupBox("Storage Location")
        storage_layout = QVBoxLayout(storage_group)

        storage_info = QLabel(
            "Set the root folder for your USD asset library. "
            "This folder contains your assets and the application database."
        )
        storage_info.setWordWrap(True)
        storage_layout.addWidget(storage_info)

        self._storage_path_label = QLabel("<b>Not configured</b>")
        self._storage_path_label.setWordWrap(True)
        storage_layout.addWidget(self._storage_path_label)

        storage_buttons = QHBoxLayout()
        set_storage_btn = QPushButton("Set Storage Location...")
        set_storage_btn.clicked.connect(self._set_storage_location)
        storage_buttons.addWidget(set_storage_btn)

        open_storage_btn = QPushButton("Open")
        open_storage_btn.clicked.connect(self._open_storage_folder)
        storage_buttons.addWidget(open_storage_btn)

        storage_buttons.addStretch()
        storage_layout.addLayout(storage_buttons)

        layout.addWidget(storage_group)

        # Database Info Group (Read-only)
        db_group = QGroupBox("Database Information")
        db_layout = QVBoxLayout(db_group)

        self._db_path_label = QLabel("")
        self._db_path_label.setWordWrap(True)
        db_layout.addWidget(self._db_path_label)

        db_info = QLabel(
            "The database and cache are stored in a hidden .assetlibrary folder "
            "inside your storage location."
        )
        db_info.setWordWrap(True)
        db_info.setStyleSheet("font-style: italic; color: #808080;")
        db_layout.addWidget(db_info)

        layout.addWidget(db_group)

        # Cache Management Group
        cache_group = QGroupBox("Cache Management")
        cache_layout = QVBoxLayout(cache_group)

        self._cache_path_label = QLabel("")
        self._cache_path_label.setWordWrap(True)
        cache_layout.addWidget(self._cache_path_label)

        cache_buttons = QHBoxLayout()
        clear_cache_btn = QPushButton("Clear Cache")
        clear_cache_btn.clicked.connect(self._clear_cache)
        cache_buttons.addWidget(clear_cache_btn)
        cache_buttons.addStretch()
        cache_layout.addLayout(cache_buttons)

        layout.addWidget(cache_group)

        layout.addStretch()

        # Load current settings
        self._load_settings()

    def _load_settings(self):
        """Load and display current settings"""
        # Load storage path
        storage_path = Config.load_library_path()
        if storage_path:
            self._storage_path_label.setText(f"<b>{storage_path}</b>")
        else:
            self._storage_path_label.setText("<b>Not configured</b>")

        # Show database path
        db_path = Config.get_database_path()
        self._db_path_label.setText(f"<b>Database:</b> {db_path}")

        # Show cache path
        cache_path = Config.get_cache_directory()
        self._cache_path_label.setText(f"<b>Cache:</b> {cache_path}")

    def _open_folder(self, folder_path):
        """Open folder in system file explorer"""
        folder_path = Path(folder_path)

        if not folder_path.exists():
            QMessageBox.warning(
                self,
                "Folder Not Found",
                f"The folder does not exist:\n{folder_path}"
            )
            return

        try:
            if sys.platform == 'win32':
                subprocess.Popen(['explorer', str(folder_path)])
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(folder_path)])
            else:  # Linux
                subprocess.Popen(['xdg-open', str(folder_path)])
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Could not open folder:\n{folder_path}\n\nError: {str(e)}"
            )

    def _set_storage_location(self):
        """Set storage location"""
        # Start from current location if set
        current_path = Config.load_library_path()
        start_dir = str(current_path) if current_path else ""

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Storage Location",
            start_dir,
            QFileDialog.Option.ShowDirsOnly
        )

        if folder:
            if Config.save_library_path(folder):
                self._storage_path_label.setText(f"<b>{folder}</b>")
                # Refresh database/cache paths display
                self._load_settings()
                QMessageBox.information(
                    self,
                    "Storage Location Set",
                    f"Storage location has been set to:\n{folder}\n\n"
                    "Please restart the application for changes to take full effect."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Error",
                    "Failed to save storage location."
                )

    def _open_storage_folder(self):
        """Open storage folder in system file explorer"""
        storage_path = Config.load_library_path()
        if storage_path:
            self._open_folder(storage_path)
        else:
            QMessageBox.information(
                self,
                "No Storage Set",
                "No storage location has been configured yet."
            )

    def _clear_cache(self):
        """Clear the cache folder"""
        cache_dir = Config.get_cache_directory()

        reply = QMessageBox.question(
            self,
            "Clear Cache",
            f"This will delete all cached thumbnails and temporary files.\n\n"
            f"Cache location: {cache_dir}\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                import shutil
                if cache_dir.exists():
                    shutil.rmtree(cache_dir)
                    cache_dir.mkdir(parents=True, exist_ok=True)

                QMessageBox.information(
                    self,
                    "Cache Cleared",
                    "Cache has been cleared successfully."
                )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Failed to clear cache:\n{str(e)}"
                )

    def save_settings(self):
        """Save settings - storage is saved on change"""
        pass


__all__ = ['StorageTab']
