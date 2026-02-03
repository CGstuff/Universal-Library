"""
BlenderTab - Blender integration settings tab

Pattern: QWidget for settings tab
Based on animation_library architecture.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox
)

from ...config import Config


class BlenderTab(QWidget):
    """
    Blender integration settings tab

    Features:
    - Blender executable path configuration
    - Path verification
    - Addon installation
    - Queue folder configuration
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._blender_path = ""
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        """Initialize UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Blender Executable Group
        blender_group = QGroupBox("Blender Executable")
        blender_layout = QVBoxLayout(blender_group)

        # Path row
        path_layout = QHBoxLayout()
        path_label = QLabel("Path:")
        path_label.setFixedWidth(60)
        path_layout.addWidget(path_label)

        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText("Select blender.exe")
        path_layout.addWidget(self._path_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_blender)
        path_layout.addWidget(browse_btn)

        blender_layout.addLayout(path_layout)

        # Buttons row
        btn_layout = QHBoxLayout()

        verify_btn = QPushButton("Verify Blender")
        verify_btn.clicked.connect(self._verify_blender)
        btn_layout.addWidget(verify_btn)

        btn_layout.addStretch()
        blender_layout.addLayout(btn_layout)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        blender_layout.addWidget(self._status_label)

        layout.addWidget(blender_group)

        # Addon Installation Group
        addon_group = QGroupBox("Addon Installation")
        addon_layout = QVBoxLayout(addon_group)

        info_label = QLabel(
            "Install the Universal Library addon to enable asset import in Blender."
        )
        info_label.setWordWrap(True)
        addon_layout.addWidget(info_label)

        install_btn = QPushButton("Install Addon to Blender")
        install_btn.clicked.connect(self._install_addon)
        addon_layout.addWidget(install_btn)

        self._addon_status_label = QLabel("")
        self._addon_status_label.setWordWrap(True)
        addon_layout.addWidget(self._addon_status_label)

        note_label = QLabel(
            "Note: The addon will be installed, enabled, and configured automatically.\n"
            "Restart Blender after installation to ensure all changes take effect."
        )
        note_label.setWordWrap(True)
        note_label.setStyleSheet("font-style: italic; color: #808080;")
        addon_layout.addWidget(note_label)

        layout.addWidget(addon_group)

        # Queue Folder Group
        queue_group = QGroupBox("Import Queue")
        queue_layout = QVBoxLayout(queue_group)

        queue_info = QLabel(
            "The import queue folder is used to communicate with the Blender addon. "
            "Assets queued for import are placed here."
        )
        queue_info.setWordWrap(True)
        queue_layout.addWidget(queue_info)

        queue_path = Config.get_data_directory() / "queue"
        queue_label = QLabel(f"<b>Queue Folder:</b> {queue_path}")
        queue_label.setWordWrap(True)
        queue_layout.addWidget(queue_label)

        layout.addWidget(queue_group)

        layout.addStretch()

    def _load_settings(self):
        """Load settings from blender_settings.json"""
        settings = Config.load_blender_settings()
        self._blender_path = settings.get("blender_path", "")
        self._path_input.setText(self._blender_path)

    def _browse_blender(self):
        """Browse for Blender executable"""
        file_filter = "Blender Executable (blender.exe);;All Files (*)"
        if not self._is_windows():
            file_filter = "Blender Executable (blender);;All Files (*)"

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Blender Executable",
            "",
            file_filter
        )

        if file_path:
            self._path_input.setText(file_path)
            self._blender_path = file_path

    def _is_windows(self) -> bool:
        """Check if running on Windows"""
        import sys
        return sys.platform == 'win32'

    def _verify_blender(self):
        """Verify Blender executable"""
        blender_path = self._path_input.text().strip()

        if not blender_path:
            self._status_label.setText("Please select a Blender executable first.")
            self._status_label.setStyleSheet("color: orange;")
            return

        path = Path(blender_path)
        if not path.exists():
            self._status_label.setText("File does not exist.")
            self._status_label.setStyleSheet("color: red;")
            return

        if not path.is_file():
            self._status_label.setText("Path is not a file.")
            self._status_label.setStyleSheet("color: red;")
            return

        # Try to get Blender version
        try:
            import subprocess
            result = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                # Extract version from output
                version_line = result.stdout.strip().split('\n')[0]
                self._status_label.setText(f"✓ Valid: {version_line}")
                self._status_label.setStyleSheet("color: #4CAF50;")
                self._blender_path = blender_path
            else:
                self._status_label.setText("✗ Could not verify Blender version.")
                self._status_label.setStyleSheet("color: red;")

        except subprocess.TimeoutExpired:
            self._status_label.setText("✗ Verification timed out.")
            self._status_label.setStyleSheet("color: red;")
        except Exception as e:
            self._status_label.setText(f"✗ Error: {str(e)}")
            self._status_label.setStyleSheet("color: red;")

    def _install_addon(self):
        """Install addon to Blender using zip + script method"""
        blender_path = self._path_input.text().strip()

        if not blender_path:
            QMessageBox.warning(
                self,
                "No Blender Path",
                "Please select and verify Blender executable first."
            )
            return

        # Get storage path to auto-configure in addon
        storage_path = Config.load_library_path()
        storage_path_str = str(storage_path) if storage_path else None

        # Use the addon installer service with zip + script method
        from ...services.addon_installer_service import get_addon_installer

        self._addon_status_label.setText("Installing addon...")
        self._addon_status_label.setStyleSheet("color: #2196F3;")
        # Force UI update
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        installer = get_addon_installer()
        success, message = installer.install_addon_with_config(
            blender_path=blender_path,
            storage_path=storage_path_str,
            auto_configure_exe=True
        )

        if success:
            self._addon_status_label.setText("✓ Addon installed and configured!")
            self._addon_status_label.setStyleSheet("color: #4CAF50;")
            QMessageBox.information(self, "Success", message)
        else:
            self._addon_status_label.setText("✗ Installation failed")
            self._addon_status_label.setStyleSheet("color: red;")
            QMessageBox.critical(self, "Installation Failed", message)

    def save_settings(self):
        """Save settings to blender_settings.json"""
        settings = Config.load_blender_settings()
        settings["blender_path"] = self._path_input.text().strip()
        Config.save_blender_settings(settings)


__all__ = ['BlenderTab']
