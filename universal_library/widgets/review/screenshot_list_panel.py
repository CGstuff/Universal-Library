"""
ScreenshotListPanel - Vertical list of screenshot thumbnails for review

Features:
- Thumbnail grid/list display
- Click to select and view
- Drag to reorder
- Right-click context menu (rename, delete)
- Add screenshot button
"""

from pathlib import Path
from typing import Optional, List, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMenu, QInputDialog, QMessageBox,
    QFileDialog, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QMimeData
from PyQt6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QDrag, QCursor


class ScreenshotThumbnail(QFrame):
    """Individual screenshot thumbnail widget."""

    clicked = pyqtSignal(int)  # index
    double_clicked = pyqtSignal(int)
    context_menu_requested = pyqtSignal(int, object)  # index, QPoint

    THUMB_SIZE = 120

    def __init__(self, index: int, data: Dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._index = index
        self._data = data
        self._selected = False

        self._setup_ui()
        self._load_thumbnail()

    def _setup_ui(self):
        """Build the thumbnail UI."""
        self.setFixedSize(self.THUMB_SIZE + 10, self.THUMB_SIZE + 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        # Thumbnail image
        self._image_label = QLabel()
        self._image_label.setFixedSize(self.THUMB_SIZE, self.THUMB_SIZE)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("""
            background: #1a1a1a;
            border: 1px solid #333;
        """)
        layout.addWidget(self._image_label)

        # Name label
        display_name = self._data.get('display_name', 'Screenshot')
        if len(display_name) > 15:
            display_name = display_name[:12] + '...'
        self._name_label = QLabel(display_name)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setStyleSheet("color: #aaa; font-size: 10px;")
        layout.addWidget(self._name_label)

        self._update_style()

    def _load_thumbnail(self):
        """Load and display the thumbnail image."""
        file_path = self._data.get('file_path', '')
        if file_path and Path(file_path).exists():
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.THUMB_SIZE, self.THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._image_label.setPixmap(scaled)
            else:
                self._image_label.setText("?")
        else:
            self._image_label.setText("?")

    def _update_style(self):
        """Update frame style based on selection state."""
        if self._selected:
            self.setStyleSheet("""
                ScreenshotThumbnail {
                    background: #3A8FB7;
                    border: 2px solid #3A8FB7;
                    border-radius: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                ScreenshotThumbnail {
                    background: #2d2d2d;
                    border: 1px solid #444;
                    border-radius: 4px;
                }
                ScreenshotThumbnail:hover {
                    background: #353535;
                    border-color: #555;
                }
            """)

    @property
    def index(self) -> int:
        return self._index

    @index.setter
    def index(self, value: int):
        self._index = value

    @property
    def data(self) -> Dict:
        return self._data

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool):
        self._selected = value
        self._update_style()

    def update_data(self, data: Dict):
        """Update screenshot data."""
        self._data = data
        display_name = data.get('display_name', 'Screenshot')
        if len(display_name) > 15:
            display_name = display_name[:12] + '...'
        self._name_label.setText(display_name)
        self._load_thumbnail()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._index)
        super().mouseDoubleClickEvent(event)

    def _on_context_menu(self, pos):
        self.context_menu_requested.emit(self._index, self.mapToGlobal(pos))


class ScreenshotListPanel(QWidget):
    """
    Panel displaying list of screenshots for review.

    Signals:
        screenshot_selected(int, dict): When a screenshot is selected (index, data)
        screenshot_added(str): When a new screenshot is added (file_path)
        screenshot_renamed(int, str): When a screenshot is renamed (index, new_name)
        screenshot_deleted(int): When a screenshot is deleted (index)
        screenshots_reordered(list): When screenshots are reordered (new order of indices)
    """

    screenshot_selected = pyqtSignal(int, dict)
    screenshot_added = pyqtSignal(str)
    screenshot_renamed = pyqtSignal(int, str)
    screenshot_deleted = pyqtSignal(int)
    screenshots_reordered = pyqtSignal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._screenshots: List[Dict] = []
        self._thumbnails: List[ScreenshotThumbnail] = []
        self._selected_index: int = -1

        self._setup_ui()

    def _setup_ui(self):
        """Build the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QLabel("Screenshots")
        header.setStyleSheet("""
            color: #fff;
            font-weight: bold;
            font-size: 12px;
            padding: 4px;
        """)
        layout.addWidget(header)

        # Scroll area for thumbnails
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet("""
            QScrollArea {
                background: #1e1e1e;
                border: none;
            }
        """)

        # Container for thumbnails
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(4, 4, 4, 4)
        self._container_layout.setSpacing(8)
        self._container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, 1)

        # Add screenshot button
        self._add_btn = QPushButton("+ Add Screenshot")
        self._add_btn.setStyleSheet("""
            QPushButton {
                background: #2d2d2d;
                color: #4CAF50;
                border: 1px dashed #4CAF50;
                border-radius: 4px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #353535;
                border-style: solid;
            }
        """)
        self._add_btn.clicked.connect(self._on_add_clicked)
        layout.addWidget(self._add_btn)

        # Enable drop
        self.setAcceptDrops(True)

    def set_screenshots(self, screenshots: List[Dict]):
        """Set the list of screenshots to display."""
        self._screenshots = screenshots
        self._selected_index = -1
        self._rebuild_thumbnails()

        # Auto-select first if available
        if screenshots:
            self.select_screenshot(0)

    def _rebuild_thumbnails(self):
        """Rebuild all thumbnail widgets."""
        # Clear existing
        for thumb in self._thumbnails:
            thumb.deleteLater()
        self._thumbnails.clear()

        # Create new thumbnails
        for i, data in enumerate(self._screenshots):
            thumb = ScreenshotThumbnail(i, data)
            thumb.clicked.connect(self._on_thumbnail_clicked)
            thumb.double_clicked.connect(self._on_thumbnail_double_clicked)
            thumb.context_menu_requested.connect(self._on_context_menu)
            self._thumbnails.append(thumb)
            self._container_layout.addWidget(thumb)

    def select_screenshot(self, index: int):
        """Select a screenshot by index."""
        if index < 0 or index >= len(self._screenshots):
            return

        # Deselect previous
        if 0 <= self._selected_index < len(self._thumbnails):
            self._thumbnails[self._selected_index].selected = False

        # Select new
        self._selected_index = index
        self._thumbnails[index].selected = True
        self.screenshot_selected.emit(index, self._screenshots[index])

    def get_selected_index(self) -> int:
        """Get currently selected screenshot index."""
        return self._selected_index

    def get_selected_data(self) -> Optional[Dict]:
        """Get currently selected screenshot data."""
        if 0 <= self._selected_index < len(self._screenshots):
            return self._screenshots[self._selected_index]
        return None

    def _on_thumbnail_clicked(self, index: int):
        """Handle thumbnail click."""
        self.select_screenshot(index)

    def _on_thumbnail_double_clicked(self, index: int):
        """Handle thumbnail double-click (rename)."""
        self._rename_screenshot(index)

    def _on_context_menu(self, index: int, global_pos):
        """Show context menu for a screenshot."""
        menu = QMenu(self)

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._rename_screenshot(index))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_screenshot(index))

        menu.exec(global_pos)

    def _rename_screenshot(self, index: int):
        """Rename a screenshot."""
        if index < 0 or index >= len(self._screenshots):
            return

        current_name = self._screenshots[index].get('display_name', '')
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Screenshot",
            "Enter new name:",
            text=current_name
        )

        if ok and new_name and new_name != current_name:
            self.screenshot_renamed.emit(index, new_name)

    def _delete_screenshot(self, index: int):
        """Delete a screenshot with confirmation."""
        if index < 0 or index >= len(self._screenshots):
            return

        name = self._screenshots[index].get('display_name', 'this screenshot')
        reply = QMessageBox.question(
            self,
            "Delete Screenshot",
            f"Are you sure you want to delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.screenshot_deleted.emit(index)

    def _on_add_clicked(self):
        """Handle add screenshot button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Screenshot",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp);;All Files (*.*)"
        )

        if file_path:
            self.screenshot_added.emit(file_path)

    def update_screenshot(self, index: int, data: Dict):
        """Update a specific screenshot's data."""
        if 0 <= index < len(self._screenshots):
            self._screenshots[index] = data
            if index < len(self._thumbnails):
                self._thumbnails[index].update_data(data)

    def add_screenshot(self, data: Dict):
        """Add a new screenshot to the list."""
        self._screenshots.append(data)
        index = len(self._screenshots) - 1

        thumb = ScreenshotThumbnail(index, data)
        thumb.clicked.connect(self._on_thumbnail_clicked)
        thumb.double_clicked.connect(self._on_thumbnail_double_clicked)
        thumb.context_menu_requested.connect(self._on_context_menu)
        self._thumbnails.append(thumb)
        self._container_layout.addWidget(thumb)

        # Auto-select new screenshot
        self.select_screenshot(index)

    def remove_screenshot(self, index: int):
        """Remove a screenshot from the list."""
        if index < 0 or index >= len(self._screenshots):
            return

        # Remove from list
        self._screenshots.pop(index)

        # Remove thumbnail
        thumb = self._thumbnails.pop(index)
        self._container_layout.removeWidget(thumb)
        thumb.deleteLater()

        # Update indices
        for i, t in enumerate(self._thumbnails):
            t.index = i

        # Update selection
        if self._selected_index >= len(self._screenshots):
            self._selected_index = len(self._screenshots) - 1

        if self._selected_index >= 0:
            self.select_screenshot(self._selected_index)
        else:
            self._selected_index = -1

    def clear(self):
        """Clear all screenshots."""
        for thumb in self._thumbnails:
            thumb.deleteLater()
        self._thumbnails.clear()
        self._screenshots.clear()
        self._selected_index = -1

    # ==================== Drag and Drop ====================

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if Path(file_path).suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp']:
                    self.screenshot_added.emit(file_path)


__all__ = ['ScreenshotListPanel', 'ScreenshotThumbnail']
