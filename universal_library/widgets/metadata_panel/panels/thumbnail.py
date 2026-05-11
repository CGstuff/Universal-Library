"""
ThumbnailPanel — Asset preview widget with 2D thumbnail + optional 3D view.

Layout:
    ┌──────────────────────────────┐
    │ [2D] [3D]            [⤢]    │   toggle row
    │ ┌──────────────────────────┐ │
    │ │   stacked widget:        │ │
    │ │     index 0 = 2D thumb   │ │
    │ │     index 1 = 3D view    │ │
    │ └──────────────────────────┘ │
    └──────────────────────────────┘

The 3D toggle is enabled only when the current asset is mesh/rig/collection
AND a .glb file resolves on disk. Otherwise the panel behaves like the
original 2D-only thumbnail.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget, QSizePolicy,
)

# Icons live under universal_library/widgets/icons/. We're at
# universal_library/widgets/metadata_panel/panels/thumbnail.py, so go up
# two parents to reach `widgets`, then into `icons`.
_ICONS_DIR = Path(__file__).resolve().parent.parent.parent / 'icons'

from ....services.asset_3d_resolver import (
    resolve_glb_info, asset_supports_3d,
)

logger = logging.getLogger(__name__)


class _ThumbnailLabel(QLabel):
    """Inner 2D image label. Same behavior as the previous flat ThumbnailPanel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #2d2d2d; border-radius: 4px;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setText("No Preview")

    def set_thumbnail(self, pixmap: QPixmap):
        scaled = pixmap.scaled(
            280, 280,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def set_loading(self):
        self.clear()
        self.setText("Loading...")

    def set_no_preview(self):
        self.clear()
        self.setText("No Preview")


class ThumbnailPanel(QWidget):
    """
    Asset preview panel with 2D/3D toggle.

    Public API (kept compatible with the original flat QLabel-based panel):
        set_thumbnail(pixmap)   — set the 2D image
        set_loading()           — show loading state
        set_no_preview()        — show no-preview state
        set_asset(asset_dict)   — NEW: pass the full asset row so the panel
                                  can decide whether 3D is available
        clear_asset()           — NEW: reset (no asset selected)

    Signals:
        enlarge_requested(str)  — emitted when user clicks ⤢ (the str is the
                                  current .glb path, or empty if none)
    """

    enlarge_requested = pyqtSignal(str)

    _IDX_2D = 0
    _IDX_3D = 1

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_asset: Optional[Dict[str, Any]] = None
        self._current_glb_path: Optional[str] = None
        self._gl_context_failed = False
        self._viewport = None  # AssetViewport, lazy-created on first 3D toggle

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toggle row
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(4)

        self._btn_2d = QPushButton("2D")
        self._btn_2d.setCheckable(True)
        self._btn_2d.setChecked(True)
        self._btn_2d.setFixedHeight(22)
        self._btn_2d.setStyleSheet(self._toggle_style())
        self._btn_2d.clicked.connect(lambda: self._switch_to(self._IDX_2D))

        self._btn_3d = QPushButton("3D")
        self._btn_3d.setCheckable(True)
        self._btn_3d.setChecked(False)
        self._btn_3d.setEnabled(False)
        self._btn_3d.setFixedHeight(22)
        self._btn_3d.setStyleSheet(self._toggle_style())
        self._btn_3d.clicked.connect(lambda: self._switch_to(self._IDX_3D))

        self._btn_enlarge = QPushButton()
        # PLACEHOLDER icon: Blender's fullscreen-enter glyph. Swap when a
        # final asset is provided.
        _enlarge_icon = _ICONS_DIR / 'fullscreen_enter.svg'
        if _enlarge_icon.is_file():
            self._btn_enlarge.setIcon(QIcon(str(_enlarge_icon)))
            self._btn_enlarge.setIconSize(QSize(14, 14))
        else:
            # Fallback to a unicode glyph if the asset is missing
            self._btn_enlarge.setText("⤢")
        self._btn_enlarge.setToolTip("Open enlarged 3D viewer")
        self._btn_enlarge.setFixedSize(22, 22)
        self._btn_enlarge.setEnabled(False)
        self._btn_enlarge.clicked.connect(self._on_enlarge)

        toggle_row.addWidget(self._btn_2d)
        toggle_row.addWidget(self._btn_3d)
        toggle_row.addStretch(1)
        toggle_row.addWidget(self._btn_enlarge)
        layout.addLayout(toggle_row)

        # Stacked preview area
        self._stack = QStackedWidget()
        self._stack.setMinimumHeight(220)
        self._stack.setMaximumHeight(320)
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._label = _ThumbnailLabel()
        self._stack.addWidget(self._label)        # index 0

        # 3D viewport: created synchronously NOW — before the main window
        # is shown. Same pattern as World_Library (GLViewport in its
        # MainWindow.__init__). When `window.show()` runs, Qt realizes the
        # entire widget tree including our GL surface in one pass, so the
        # GL context comes up as part of initial paint instead of mid-
        # session. No flicker on first 3D click.
        #
        # Cost: app startup is ~300-500ms longer (PyOpenGL/numpy/DracoPy
        # imports + widget construction). That cost is unavoidable and is
        # the explicit trade we accept for click-time responsiveness.
        self._stack.addWidget(QWidget())          # index 1 — placeholder
        self._eager_init_viewport()

        layout.addWidget(self._stack)

        self._stack.setCurrentIndex(self._IDX_2D)

    @staticmethod
    def _toggle_style() -> str:
        return """
            QPushButton {
                background-color: #3a3a3a;
                color: #cccccc;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 10px;
                font-size: 11px;
            }
            QPushButton:checked {
                background-color: #0078d4;
                color: white;
                border: 1px solid #0078d4;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #555;
                border: 1px solid #333;
            }
            QPushButton:hover:!checked:!disabled {
                background-color: #454545;
            }
        """

    # ------------------------------------------------------------------
    # Public API — 2D image (compatibility with old flat panel)
    # ------------------------------------------------------------------

    def set_thumbnail(self, pixmap: QPixmap):
        self._label.set_thumbnail(pixmap)

    def set_loading(self):
        self._label.set_loading()

    def set_no_preview(self):
        self._label.set_no_preview()

    # ------------------------------------------------------------------
    # Public API — asset context (NEW)
    # ------------------------------------------------------------------

    def set_asset(self, asset: Optional[Dict[str, Any]]):
        """Pass the currently-selected asset so the panel can decide whether
        3D preview is available. Call AFTER set_thumbnail/set_loading/etc.

        Always resets the view to 2D when the asset changes — the user opts
        back in to 3D explicitly. This avoids reloading a possibly large .glb
        every time they click through the library.
        """
        self._current_asset = asset
        self._current_glb_path = None

        # Always start in 2D when switching assets
        if self._stack.currentIndex() != self._IDX_2D:
            self._switch_to(self._IDX_2D)

        # Decide whether 3D is offered
        if self._gl_context_failed:
            self._set_3d_button_off("3D preview unavailable on this system")
            return

        if not asset_supports_3d(asset):
            self._set_3d_button_off("3D preview not available for this asset type")
            return

        info = resolve_glb_info(asset)
        if info is None:
            self._set_3d_button_off("No 3D preview file for this version")
            return

        self._current_glb_path = str(info.path)
        self._btn_3d.setEnabled(True)
        if info.has_animations:
            self._btn_3d.setText("3D ▶")
            self._btn_3d.setToolTip(
                f"Show 3D preview (animated — open the enlarged viewer for the timeline)\n"
                f"{self._current_glb_path}"
            )
        else:
            self._btn_3d.setText("3D")
            self._btn_3d.setToolTip(f"Show 3D preview\n{self._current_glb_path}")
        # Enlarge only makes sense when 3D is the active view; tied to switch.
        self._btn_enlarge.setEnabled(False)

    def _set_3d_button_off(self, tooltip: str):
        """Disable the 3D toggle with a reason. Resets the label too."""
        self._btn_3d.setEnabled(False)
        self._btn_3d.setText("3D")
        self._btn_3d.setToolTip(tooltip)
        self._btn_enlarge.setEnabled(False)

    def clear_asset(self):
        self._current_asset = None
        self._current_glb_path = None
        if self._stack.currentIndex() != self._IDX_2D:
            self._switch_to(self._IDX_2D)
        self._btn_3d.setEnabled(False)
        self._btn_3d.setText("3D")
        self._btn_3d.setToolTip("")
        self._btn_enlarge.setEnabled(False)

    # ------------------------------------------------------------------
    # Internal — view switching
    # ------------------------------------------------------------------

    def _switch_to(self, index: int):
        """Switch the stacked widget. Updates toggle button checked-states."""
        if index == self._IDX_3D and not self._btn_3d.isEnabled():
            # Should not happen (button is disabled), defensive
            return

        if index == self._IDX_3D:
            self._ensure_viewport()
            if self._viewport is None:
                # GL init failed during creation — bail out
                self._switch_to(self._IDX_2D)
                return
            if self._current_glb_path:
                self._viewport.load_glb(self._current_glb_path)

        self._stack.setCurrentIndex(index)
        self._btn_2d.setChecked(index == self._IDX_2D)
        self._btn_3d.setChecked(index == self._IDX_3D)
        self._btn_enlarge.setEnabled(index == self._IDX_3D and bool(self._current_glb_path))

    def _eager_init_viewport(self):
        """Create the AssetViewport synchronously, before the parent main
        window is shown. This matches the World_Library pattern: build the
        GL widget as part of the initial widget tree so its GL context
        comes up during the main window's first paint pass — no mid-session
        pipeline change."""
        if self._viewport is not None:
            return
        try:
            from ...viewport_3d import AssetViewport
        except ImportError as e:
            logger.error(f"[ThumbnailPanel] Failed to import AssetViewport: {e}")
            self._gl_context_failed = True
            self._btn_3d.setEnabled(False)
            self._btn_3d.setToolTip("3D preview unavailable: import failed")
            return

        try:
            self._viewport = AssetViewport()
            self._viewport.context_unavailable.connect(self._on_gl_context_failed)
            self._viewport.glb_failed.connect(self._on_glb_failed)
            placeholder = self._stack.widget(self._IDX_3D)
            self._stack.removeWidget(placeholder)
            placeholder.deleteLater()
            self._stack.insertWidget(self._IDX_3D, self._viewport)
        except Exception as e:
            logger.exception(f"[ThumbnailPanel] AssetViewport construction failed: {e}")
            self._gl_context_failed = True
            self._viewport = None
            self._btn_3d.setEnabled(False)
            self._btn_3d.setToolTip("3D preview unavailable on this system")

    def _ensure_viewport(self):
        """Compatibility shim. Viewport is created eagerly via
        `_eager_init_viewport`; this is a no-op."""
        return

    def _on_gl_context_failed(self):
        logger.warning("[ThumbnailPanel] GL context unavailable; disabling 3D toggle")
        self._gl_context_failed = True
        self._btn_3d.setEnabled(False)
        self._btn_3d.setToolTip("3D preview unavailable on this system")
        self._btn_enlarge.setEnabled(False)
        # Fall back to 2D
        if self._stack.currentIndex() == self._IDX_3D:
            self._switch_to(self._IDX_2D)

    def _on_glb_failed(self, path: str, error: str):
        logger.warning(f"[ThumbnailPanel] glb load failed for {path}: {error}")
        # Stay on 3D — viewport will be blank with just the grid. The toggle
        # back to 2D is right there for the user.

    def _on_enlarge(self):
        """Emit a signal asking the parent to open the enlarged viewer.

        The actual enlarged dialog is wired in Phase 3.
        """
        self.enlarge_requested.emit(self._current_glb_path or "")


__all__ = ['ThumbnailPanel']
