"""
Preview panel for version history dialog.

Handles async preview image loading.
"""

from pathlib import Path
from typing import Dict, Optional, Any

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

from .config import VersionHistoryConfig
from ....config import Config


class PreviewSignals(QObject):
    """Signals for async preview loading."""
    loaded = pyqtSignal(str, QPixmap)  # uuid, pixmap
    failed = pyqtSignal(str)  # uuid


class PreviewLoadTask(QRunnable):
    """Background task for loading a large preview image."""

    def __init__(self, uuid: str, image_path: str, size: int):
        super().__init__()
        self.uuid = uuid
        self.image_path = image_path
        self.size = size
        self.signals = PreviewSignals()

    def run(self):
        """Load and scale image in background."""
        try:
            path = Path(self.image_path)
            if not path.exists():
                self.signals.failed.emit(self.uuid)
                return

            image = QImage(str(path))
            if image.isNull():
                self.signals.failed.emit(self.uuid)
                return

            scaled = image.scaled(
                self.size, self.size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            pixmap = QPixmap.fromImage(scaled)
            self.signals.loaded.emit(self.uuid, pixmap)

        except Exception:
            self.signals.failed.emit(self.uuid)


class PreviewPanel:
    """
    Manages preview panel for version history dialog.

    Handles async loading and caching of preview images.
    """

    def __init__(
        self,
        info_label: QLabel,
        image_label: QLabel,
        thread_pool: QThreadPool = None
    ):
        """
        Initialize preview panel.

        Args:
            info_label: Label for version info text
            image_label: Label for preview image
            thread_pool: Thread pool for async loading
        """
        self._info_label = info_label
        self._image_label = image_label
        self._thread_pool = thread_pool or QThreadPool.globalInstance()

        self._cache: Dict[str, QPixmap] = {}
        self._pending_uuid: Optional[str] = None

    def load_preview(self, uuid: str, thumbnail_path: str):
        """Start async preview loading for a version."""
        if not thumbnail_path:
            self._image_label.clear()
            self._image_label.setText("No preview available")
            return

        # Check cache first
        if uuid in self._cache:
            self._image_label.setPixmap(self._cache[uuid])
            return

        # Show loading state
        self._image_label.clear()
        self._image_label.setText("Loading...")
        self._pending_uuid = uuid

        # Create and start task
        task = PreviewLoadTask(uuid, thumbnail_path, VersionHistoryConfig.PREVIEW_SIZE)
        task.signals.loaded.connect(self._on_loaded)
        task.signals.failed.connect(self._on_failed)
        self._thread_pool.start(task)

    def _on_loaded(self, uuid: str, pixmap: QPixmap):
        """Handle async preview load complete."""
        self._cache[uuid] = pixmap

        if uuid == self._pending_uuid:
            self._image_label.setPixmap(pixmap)

    def _on_failed(self, uuid: str):
        """Handle async preview load failure."""
        if uuid == self._pending_uuid:
            self._image_label.clear()
            self._image_label.setText("Preview not found")

    def update_display(self, version: Optional[Dict[str, Any]]):
        """Update the preview panel with version info and image."""
        if not version:
            self._info_label.setText("Select a version to preview")
            self._image_label.clear()
            self._image_label.setText("No preview")
            return

        # Update info label
        version_label = version.get('version_label', f"v{version.get('version', 1):03d}")
        variant_name = version.get('variant_name') or version.get('_variant_name', 'Base')
        status = version.get('status', 'wip')
        status_info = Config.LIFECYCLE_STATUSES.get(status, {'label': status.upper()})

        info_parts = [version_label]
        if variant_name != 'Base':
            info_parts.append(variant_name)
        if version.get('is_latest', 0):
            info_parts.append("Latest")
        info_parts.append(status_info.get('label', status))

        self._info_label.setText(" | ".join(info_parts))

        # Load preview image
        thumbnail_path = version.get('thumbnail_path', '')
        self.load_preview(version.get('uuid', ''), thumbnail_path)

    def clear(self):
        """Clear preview panel."""
        self._info_label.setText("Select a version to preview")
        self._image_label.clear()
        self._image_label.setText("No preview")


__all__ = ['PreviewSignals', 'PreviewLoadTask', 'PreviewPanel']
