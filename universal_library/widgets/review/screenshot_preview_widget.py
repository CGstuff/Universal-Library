"""
ScreenshotPreviewWidget - Large screenshot display with drawover overlay

Features:
- Scaled image display
- DrawoverCanvas overlay for annotations
- DrawingToolbar integration
- Annotation toggle button
"""

from pathlib import Path
from typing import Optional, List, Dict, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF
from PyQt6.QtGui import QPixmap, QResizeEvent

from .drawover_canvas import DrawoverCanvas, DrawingTool
from .drawing_toolbar import DrawingToolbar


class ScreenshotPreviewWidget(QWidget):
    """
    Large screenshot preview with annotation support.

    Signals:
        annotation_changed(): When annotations are modified
        annotation_mode_changed(bool): When annotation mode is toggled
    """

    annotation_changed = pyqtSignal()
    annotation_mode_changed = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._screenshot_path: Optional[str] = None
        self._screenshot_name: Optional[str] = None
        self._pixmap: Optional[QPixmap] = None
        self._annotation_mode = False
        self._current_author = ''

        # Pending strokes to apply after canvas is positioned
        self._pending_strokes: Optional[List[Dict]] = None
        self._pending_canvas_size: Optional[Tuple[int, int]] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Build the preview UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with annotate toggle and toolbar (like AL)
        header = QFrame()
        header.setStyleSheet("background: #252525; border-bottom: 1px solid #333;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(8)

        # Annotate toggle button
        self._annotate_btn = QPushButton("Annotate")
        self._annotate_btn.setCheckable(True)
        self._annotate_btn.setFixedHeight(28)
        self._annotate_btn.setStyleSheet("""
            QPushButton {
                background: #2d2d2d;
                color: #aaa;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 4px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #3a3a3a;
            }
            QPushButton:checked {
                background: #FF5722;
                color: white;
                border-color: #FF5722;
            }
        """)
        self._annotate_btn.clicked.connect(self._on_annotate_toggled)
        header_layout.addWidget(self._annotate_btn)

        # Drawing toolbar (hidden by default, inline with header)
        self._toolbar = DrawingToolbar()
        self._toolbar.hide()
        header_layout.addWidget(self._toolbar)

        header_layout.addStretch()

        # Screenshot name in header
        self._name_label = QLabel("No screenshot selected")
        self._name_label.setStyleSheet("color: #888; font-size: 11px;")
        header_layout.addWidget(self._name_label)

        layout.addWidget(header)

        # Image container with canvas overlay
        self._image_container = QFrame()
        self._image_container.setStyleSheet("background: #1a1a1a;")
        container_layout = QVBoxLayout(self._image_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Image label
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background: transparent;")
        self._image_label.setMinimumSize(400, 300)
        container_layout.addWidget(self._image_label, 1)

        layout.addWidget(self._image_container, 1)

        # Drawover canvas (overlay - will be positioned over image)
        self._canvas = DrawoverCanvas()
        self._canvas.hide()
        self._canvas.set_tool(DrawingTool.NONE)

    def _connect_signals(self):
        """Connect internal signals."""
        # Toolbar signals
        self._toolbar.tool_changed.connect(self._on_tool_changed)
        self._toolbar.color_changed.connect(self._on_color_changed)
        self._toolbar.brush_size_changed.connect(self._on_brush_size_changed)
        self._toolbar.undo_clicked.connect(self._on_undo)
        self._toolbar.redo_clicked.connect(self._on_redo)
        self._toolbar.clear_clicked.connect(self._on_clear)

        # Canvas signals
        self._canvas.drawing_modified.connect(self._on_drawing_modified)

    def load_screenshot(self, file_path: str, display_name: str = ''):
        """Load a screenshot for preview."""
        self._screenshot_path = file_path
        self._screenshot_name = display_name or Path(file_path).stem

        # Update name label
        self._name_label.setText(self._screenshot_name)

        # Load pixmap
        if file_path and Path(file_path).exists():
            self._pixmap = QPixmap(file_path)
            self._update_image_display()
        else:
            self._pixmap = None
            self._image_label.setText("Image not found")

        # Clear canvas and pending strokes
        self._canvas.clear()
        self._pending_strokes = None
        self._pending_canvas_size = None

        # Position canvas after image loads
        QTimer.singleShot(50, self._position_canvas)

    def _update_image_display(self):
        """Scale and display the image."""
        if not self._pixmap or self._pixmap.isNull():
            return

        # Get available size
        available_size = self._image_label.size()

        # Scale pixmap to fit
        scaled = self._pixmap.scaled(
            available_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        self._image_label.setPixmap(scaled)

    def _position_canvas(self):
        """Position the drawover canvas over the image."""
        if not self._pixmap or self._pixmap.isNull():
            return

        # Calculate the actual image display rect
        image_rect = self._get_image_display_rect()
        if not image_rect:
            return

        # Parent canvas to image label and position
        self._canvas.setParent(self._image_label)
        self._canvas.setGeometry(
            int(image_rect.x()),
            int(image_rect.y()),
            int(image_rect.width()),
            int(image_rect.height())
        )

        # Set canvas image rect for coordinate conversion
        local_rect = QRectF(0, 0, image_rect.width(), image_rect.height())
        self._canvas.set_image_rect(local_rect)

        self._canvas.raise_()

        # Apply any pending strokes now that the canvas is properly positioned
        if self._pending_strokes is not None:
            self._canvas.import_strokes(self._pending_strokes, self._pending_canvas_size)
            if self._pending_strokes:
                self._canvas.show()
            self._pending_strokes = None
            self._pending_canvas_size = None

    def _get_image_display_rect(self) -> Optional[QRectF]:
        """Get the rect where the image is actually displayed within the label."""
        if not self._pixmap or self._pixmap.isNull():
            return None

        label_w = self._image_label.width()
        label_h = self._image_label.height()
        pixmap_w = self._pixmap.width()
        pixmap_h = self._pixmap.height()

        if pixmap_w <= 0 or pixmap_h <= 0:
            return None

        # Calculate scale to fit
        scale = min(label_w / pixmap_w, label_h / pixmap_h)

        # Scaled dimensions
        scaled_w = pixmap_w * scale
        scaled_h = pixmap_h * scale

        # Centered position
        x = (label_w - scaled_w) / 2
        y = (label_h - scaled_h) / 2

        return QRectF(x, y, scaled_w, scaled_h)

    def _on_annotate_toggled(self, checked: bool):
        """Handle annotation mode toggle."""
        self._annotation_mode = checked
        self._toolbar.setVisible(checked)

        if checked:
            self._canvas.show()
            self._canvas.set_tool(DrawingTool.PEN)
            self._toolbar.set_tool(DrawingTool.PEN)
            self._position_canvas()
        else:
            self._canvas.set_tool(DrawingTool.NONE)

        self.annotation_mode_changed.emit(checked)

    def _on_tool_changed(self, tool: DrawingTool):
        """Handle tool change from toolbar."""
        self._canvas.set_tool(tool)

    def _on_color_changed(self, color):
        """Handle color change from toolbar."""
        self._canvas.color = color

    def _on_brush_size_changed(self, size: int):
        """Handle brush size change from toolbar."""
        self._canvas.brush_size = size

    def _on_undo(self):
        """Handle undo action."""
        self._canvas.undo_stack.undo()
        self._update_undo_redo_state()

    def _on_redo(self):
        """Handle redo action."""
        self._canvas.undo_stack.redo()
        self._update_undo_redo_state()

    def _on_clear(self):
        """Handle clear action."""
        self._canvas.clear()
        self.annotation_changed.emit()

    def _on_drawing_modified(self):
        """Handle drawing modification."""
        self._update_undo_redo_state()
        self.annotation_changed.emit()

    def _update_undo_redo_state(self):
        """Update undo/redo button states."""
        self._toolbar.set_undo_enabled(self._canvas.undo_stack.canUndo())
        self._toolbar.set_redo_enabled(self._canvas.undo_stack.canRedo())

    def set_author(self, author: str):
        """Set current author for annotations."""
        self._current_author = author
        self._canvas.set_author(author)

    def get_strokes(self) -> List[Dict]:
        """Get current annotation strokes."""
        return self._canvas.export_strokes()

    def set_strokes(self, strokes: List[Dict], canvas_size: Tuple[int, int] = None):
        """Load annotation strokes.

        Strokes are stored as pending until the canvas is properly positioned,
        ensuring correct UV-to-screen coordinate conversion.
        """
        # Store as pending - will be applied when canvas is positioned
        # This ensures image_rect is set before UV coordinate conversion
        self._pending_strokes = strokes
        self._pending_canvas_size = canvas_size

        # If canvas is already positioned, apply immediately
        if self._canvas.get_image_rect() is not None:
            self._canvas.import_strokes(strokes, canvas_size)
            if strokes:
                self._canvas.show()
            self._pending_strokes = None
            self._pending_canvas_size = None

    def clear_annotations(self):
        """Clear all annotations."""
        self._canvas.clear()
        self._pending_strokes = None
        self._pending_canvas_size = None

    def clear(self):
        """Clear the preview."""
        self._pixmap = None
        self._screenshot_path = None
        self._screenshot_name = None
        self._pending_strokes = None
        self._pending_canvas_size = None
        self._image_label.clear()
        self._image_label.setText("No screenshot selected")
        self._name_label.setText("No screenshot selected")
        self._canvas.clear()
        self._canvas.hide()

        if self._annotation_mode:
            self._annotate_btn.setChecked(False)
            self._on_annotate_toggled(False)

    def get_screenshot_name(self) -> Optional[str]:
        """Get the current screenshot name (for drawover storage)."""
        return self._screenshot_name

    def get_screenshot_path(self) -> Optional[str]:
        """Get the current screenshot file path."""
        return self._screenshot_path

    def get_canvas_size(self) -> Tuple[int, int]:
        """Get current canvas size for storage."""
        rect = self._get_image_display_rect()
        if rect:
            return (int(rect.width()), int(rect.height()))
        return (self._canvas.width(), self._canvas.height())

    def resizeEvent(self, event: QResizeEvent):
        """Handle resize - update image and canvas."""
        super().resizeEvent(event)
        self._update_image_display()
        QTimer.singleShot(50, self._position_canvas)


__all__ = ['ScreenshotPreviewWidget']
