"""
ThumbnailPanel - Thumbnail display widget.
"""

from typing import Optional
from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap


class ThumbnailPanel(QLabel):
    """
    Thumbnail display widget.

    Displays asset thumbnail with proper scaling.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI."""
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 200)
        self.setMaximumSize(300, 300)
        self.setStyleSheet("background-color: #2d2d2d; border-radius: 4px;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setText("No Preview")

    def set_thumbnail(self, pixmap: QPixmap):
        """Set thumbnail with proper scaling."""
        scaled = pixmap.scaled(
            280, 280,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(scaled)

    def set_loading(self):
        """Show loading state."""
        self.clear()
        self.setText("Loading...")

    def set_no_preview(self):
        """Show no preview state."""
        self.clear()
        self.setText("No Preview")


__all__ = ['ThumbnailPanel']
