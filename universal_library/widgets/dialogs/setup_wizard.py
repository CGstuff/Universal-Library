"""
SetupWizard - First-run setup wizard for Universal Library (UL)

Guides users through initial configuration:
1. Welcome page with requirements
2. Library path selection
3. Finish/summary page
"""

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QWidget, QFileDialog, QLineEdit, QFrame,
    QSizePolicy, QGroupBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap, QPalette, QColor

from ...config import Config


class WelcomePage(QWidget):
    """Welcome page with introduction and requirements"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(50, 30, 50, 20)

        layout.addStretch(1)

        # Logo image
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Get icon path - handle both dev and compiled modes
        if getattr(sys, 'frozen', False):
            # Running as compiled exe
            icon_path = Path(sys._MEIPASS) / "Icon.png"
        else:
            # Running from source - Config.APP_ROOT is universal_library/
            icon_path = Config.APP_ROOT.parent / "Icon.png"

        # Load and display icon
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                logo_label.setPixmap(scaled)
            else:
                # Fallback to text
                logo_label.setText("UL")
                logo_label.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
                logo_label.setStyleSheet("color: #0078d4;")
        else:
            # Fallback to text if icon not found
            logo_label.setText("UL")
            logo_label.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
            logo_label.setStyleSheet("color: #0078d4;")

        layout.addWidget(logo_label)

        layout.addSpacing(10)

        # Title
        title = QLabel("Welcome to Universal Library!")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #0078d4;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(15)

        # Description
        desc = QLabel(
            "Universal Library is a tool for organizing, versioning,\n"
            "and managing assets across your Blender projects."
        )
        desc.setFont(QFont("Segoe UI", 10))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        layout.addSpacing(5)

        # Setup line
        setup_line = QLabel("This wizard will help you set up your asset storage location.")
        setup_line.setFont(QFont("Segoe UI", 10))
        setup_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(setup_line)

        layout.addSpacing(20)

        # Requirements group box
        req_frame = QGroupBox("What you'll need:")
        req_frame.setFont(QFont("Segoe UI", 10))
        req_layout = QVBoxLayout(req_frame)
        req_layout.setSpacing(5)
        req_layout.setContentsMargins(15, 15, 15, 15)

        requirements = [
            "A folder to store your asset library",
            "About 1 GB of disk space per 100 assets",
            "Blender 4.2 or later",
        ]

        for req in requirements:
            req_label = QLabel(f"• {req}")
            req_label.setFont(QFont("Segoe UI", 10))
            req_layout.addWidget(req_label)

        layout.addWidget(req_frame)

        layout.addStretch(2)


class LibraryPathPage(QWidget):
    """Page for selecting the library storage path"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(50, 30, 50, 20)

        layout.addStretch(1)

        # Title
        title = QLabel("Choose Storage Location")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #0078d4;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(10)

        # Description
        desc = QLabel(
            "Select a folder where your assets will be stored.\n"
            "This folder will contain all asset files, thumbnails, and metadata."
        )
        desc.setFont(QFont("Segoe UI", 10))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        layout.addSpacing(20)

        # Path selection
        path_layout = QHBoxLayout()

        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("Select a folder...")
        self._path_edit.setMinimumHeight(30)
        path_layout.addWidget(self._path_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.setMinimumHeight(30)
        browse_btn.clicked.connect(self._browse_folder)
        path_layout.addWidget(browse_btn)

        layout.addLayout(path_layout)

        # Default path option (link style)
        default_btn = QPushButton("Use Default Location (storage/ folder)")
        default_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        default_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #0078d4;
                border: none;
                border-radius: 0px;
                text-align: center;
            }
            QPushButton:hover {
                color: #1084d8;
                text-decoration: underline;
            }
        """)
        default_btn.clicked.connect(self._use_default)
        layout.addWidget(default_btn)

        layout.addSpacing(15)

        # Tips group box
        tips_frame = QGroupBox("Tips:")
        tips_frame.setFont(QFont("Segoe UI", 10))
        tips_layout = QVBoxLayout(tips_frame)
        tips_layout.setSpacing(5)
        tips_layout.setContentsMargins(15, 15, 15, 15)

        tips = [
            "Choose a location with fast storage (SSD recommended)",
            "Use a local drive for best performance",
            "Make sure you have write permissions",
        ]

        for tip in tips:
            tip_label = QLabel(f"• {tip}")
            tip_label.setFont(QFont("Segoe UI", 10))
            tips_layout.addWidget(tip_label)

        layout.addWidget(tips_frame)

        layout.addStretch(2)

        # Set default path initially
        self._use_default()

    def _browse_folder(self):
        """Open folder browser dialog"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Library Folder",
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self._path_edit.setText(folder)

    def _use_default(self):
        """Use default storage path"""
        # Default to storage/ folder next to executable or project root
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            base_path = Path(sys.executable).parent
        else:
            # Running as script
            base_path = Path(__file__).parent.parent.parent.parent

        default_path = base_path / "storage"
        self._path_edit.setText(str(default_path))

    def get_path(self) -> Optional[Path]:
        """Get the selected path"""
        text = self._path_edit.text().strip()
        if text:
            return Path(text)
        return None


class FinishPage(QWidget):
    """Final page with summary and next steps"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._library_path = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(50, 30, 50, 20)

        layout.addStretch(1)

        # Title
        title = QLabel("Setup Complete!")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #4CAF50;")
        layout.addWidget(title)

        layout.addSpacing(10)

        # Summary
        self._summary_label = QLabel()
        self._summary_label.setFont(QFont("Segoe UI", 10))
        self._summary_label.setWordWrap(True)
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._summary_label)

        layout.addSpacing(20)

        # Next steps group box
        steps_frame = QGroupBox("Next steps:")
        steps_frame.setFont(QFont("Segoe UI", 10))
        steps_layout = QVBoxLayout(steps_frame)
        steps_layout.setSpacing(5)
        steps_layout.setContentsMargins(15, 15, 15, 15)

        steps = [
            "Install the Blender addon from UL_blender_plugin folder",
            "Configure the addon with the same library path",
            "Export assets from Blender to your library",
            "Use this application to browse and manage assets",
        ]

        for i, step in enumerate(steps, 1):
            step_label = QLabel(f"{i}. {step}")
            step_label.setFont(QFont("Segoe UI", 10))
            steps_layout.addWidget(step_label)

        layout.addWidget(steps_frame)

        layout.addStretch(2)

    def set_library_path(self, path: str):
        """Set the library path for summary display"""
        self._library_path = path
        self._summary_label.setText(
            f"Your asset library has been configured!\n\n"
            f"Library location:\n{path}"
        )


class SetupWizard(QDialog):
    """
    First-run setup wizard for Universal Library (UL)

    Usage:
        wizard = SetupWizard(parent)
        if wizard.exec() == QDialog.DialogCode.Accepted:
            # Setup completed
            pass
        else:
            # User cancelled
            sys.exit(0)
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Universal Library Setup")
        self.setModal(True)
        self.setFixedSize(500, 450)

        # Ensure proper rendering
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Set background color explicitly for consistent rendering
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Global stylesheet for sharp buttons
        self.setStyleSheet("""
            QPushButton {
                padding: 5px 12px;
                border: 1px solid #555;
                border-radius: 0px;
                background-color: #3c3c3c;
                color: white;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            QPushButton:disabled {
                color: #666;
                background-color: #2d2d2d;
                border-color: #444;
            }
            QLineEdit {
                padding: 5px;
                border: 1px solid #555;
                border-radius: 0px;
                background-color: #2d2d2d;
                color: white;
            }
            QGroupBox {
                border: 1px solid #444;
                border-radius: 0px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Page stack
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Create pages
        self._welcome_page = WelcomePage()
        self._path_page = LibraryPathPage()
        self._finish_page = FinishPage()

        # Set size policies for pages
        for page in [self._welcome_page, self._path_page, self._finish_page]:
            page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._stack.addWidget(self._welcome_page)
        self._stack.addWidget(self._path_page)
        self._stack.addWidget(self._finish_page)

        layout.addWidget(self._stack, 1)  # Give stretch factor

        # Navigation buttons
        nav_frame = QFrame()
        nav_frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-top: 1px solid #333;
            }
        """)
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(15, 10, 15, 10)

        self._back_btn = QPushButton("Back")
        self._back_btn.setEnabled(False)
        self._back_btn.clicked.connect(self._go_back)
        nav_layout.addWidget(self._back_btn)

        nav_layout.addStretch()

        self._next_btn = QPushButton("Next")
        self._next_btn.setDefault(True)
        self._next_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                border: 1px solid #0078d4;
                border-radius: 0px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #1084d8;
                border-color: #1084d8;
            }
        """)
        self._next_btn.clicked.connect(self._go_next)
        nav_layout.addWidget(self._next_btn)

        layout.addWidget(nav_frame)

    def _go_back(self):
        """Go to previous page"""
        current = self._stack.currentIndex()
        if current > 0:
            self._stack.setCurrentIndex(current - 1)
            self._update_buttons()

    def _go_next(self):
        """Go to next page or finish"""
        current = self._stack.currentIndex()

        if current == 0:
            # Welcome -> Path
            self._stack.setCurrentIndex(1)
            self._update_buttons()

        elif current == 1:
            # Path -> Finish
            path = self._path_page.get_path()
            if not path:
                return

            self._finish_page.set_library_path(str(path))
            self._stack.setCurrentIndex(2)
            self._update_buttons()

        elif current == 2:
            # Finish -> Complete setup
            self._finish_setup()

    def _update_buttons(self):
        """Update button states based on current page"""
        current = self._stack.currentIndex()

        self._back_btn.setEnabled(current > 0)

        if current == 2:
            self._next_btn.setText("Finish")
        else:
            self._next_btn.setText("Next")

    def _finish_setup(self):
        """Complete the setup process"""
        path = self._path_page.get_path()
        if not path:
            return

        # Create directory if it doesn't exist
        path.mkdir(parents=True, exist_ok=True)

        # Save library path to config
        Config.save_library_path(path)

        # Accept dialog
        self.accept()


__all__ = ['SetupWizard']
