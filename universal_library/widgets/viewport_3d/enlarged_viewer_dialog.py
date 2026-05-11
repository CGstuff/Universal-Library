"""
EnlargedViewerDialog — pops the 3D asset preview into a larger window.

Non-modal QDialog hosting its own AssetViewport. The mesh data is shared via
the module-level LRU cache (mesh_cache.py), so opening this dialog does not
re-parse the .glb that's already loaded in the metadata panel — only the
GL upload runs again (per-context, unavoidable).

For rig assets, the dialog also surfaces an animation timeline (action picker,
play/pause, scrubber, loop). The timeline auto-hides for non-animated assets.

Public API:
    EnlargedViewerDialog(glb_path, asset_name=None, parent=None)
        .exec() / .show()           — open the dialog
        .load_glb(path)             — swap the displayed asset
"""

from __future__ import annotations

from typing import Optional

from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QTimer, QElapsedTimer
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QColorDialog, QWidget, QComboBox, QSlider, QCheckBox, QSizePolicy,
)

from .asset_viewport import AssetViewport
from .light_direction_dialog import LightDirectionDialog
from ...services.viewport_settings import (
    get_viewport_bg_color, set_viewport_bg_color,
    get_viewport_fps, set_viewport_fps,
)

# Icons live under universal_library/widgets/icons/. We're at
# universal_library/widgets/viewport_3d/. One parent up to reach widgets.
_ICONS_DIR = Path(__file__).resolve().parent.parent / 'icons'


class EnlargedViewerDialog(QDialog):
    """Larger 3D preview window. Non-modal — the user can keep browsing the
    library while it stays open."""

    _DEFAULT_SIZE = QSize(900, 700)
    _MIN_SIZE = QSize(400, 300)
    _TIMER_INTERVAL_MS = 16  # ~60Hz; playback is wall-clock-driven anyway

    # The animation's authored framerate. glTF stores keyframes in seconds —
    # not frames — so we can't recover the source FPS from the file alone.
    # 24 is the most common authoring rate for animation work and matches
    # Blender's default scene FPS. The frame counter is computed against
    # THIS rate (so a 200-frame anim always shows 200, regardless of the
    # picker FPS). The picker FPS only controls playback SPEED.
    _SOURCE_FPS = 24

    def __init__(self, glb_path: str, asset_name: Optional[str] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(self._title_for(asset_name))
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint
        )
        # Non-modal so the user can keep clicking around the library
        self.setModal(False)
        self.resize(self._DEFAULT_SIZE)
        self.setMinimumSize(self._MIN_SIZE)

        self._asset_name = asset_name
        self._current_glb_path: Optional[str] = None
        self._viewport: Optional[AssetViewport] = None

        # Playback state
        self._timer = QTimer(self)
        self._timer.setInterval(self._TIMER_INTERVAL_MS)
        self._timer.timeout.connect(self._on_timer_tick)
        self._elapsed = QElapsedTimer()  # wall-clock since last tick

        self._setup_ui()

        if glb_path:
            self.load_glb(glb_path)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._reset_btn = QPushButton("Reset View")
        self._reset_btn.clicked.connect(self._on_reset)
        toolbar.addWidget(self._reset_btn)

        self._bg_btn = QPushButton("Background…")
        self._bg_btn.setToolTip("Change 3D preview background color (applies globally)")
        self._bg_btn.clicked.connect(self._on_pick_bg)
        toolbar.addWidget(self._bg_btn)

        self._light_btn = QPushButton("Light…")
        self._light_btn.setToolTip("Adjust the directional light's angle (applies globally)")
        self._light_btn.clicked.connect(self._on_light_clicked)
        toolbar.addWidget(self._light_btn)

        toolbar.addStretch(1)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(self._status)

        layout.addLayout(toolbar)

        # Viewport
        self._viewport = AssetViewport(self)
        self._viewport.glb_loaded.connect(self._on_loaded)
        self._viewport.glb_failed.connect(self._on_failed)
        self._viewport.context_unavailable.connect(self._on_no_context)
        layout.addWidget(self._viewport, 1)

        # Animation timeline (hidden until the loaded asset has animations)
        self._timeline_row = self._build_timeline_row()
        layout.addWidget(self._timeline_row)
        self._timeline_row.hide()

        # Footer with close button
        footer = QHBoxLayout()
        footer.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

    def _build_timeline_row(self) -> QWidget:
        """Build the animation timeline strip: play / picker / scrubber /
        frame counter / FPS / speed / loop. Lives between viewport and footer."""
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(30, 26)
        self._play_btn.setCheckable(True)
        self._play_btn.setToolTip("Play / Pause")
        self._play_btn.toggled.connect(self._on_play_toggled)
        lay.addWidget(self._play_btn)

        self._anim_combo = QComboBox()
        self._anim_combo.setMinimumWidth(160)
        self._anim_combo.setToolTip("Animation")
        self._anim_combo.currentIndexChanged.connect(self._on_anim_changed)
        lay.addWidget(self._anim_combo)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(1000)
        self._slider.setValue(0)
        self._slider.valueChanged.connect(self._on_slider_changed)
        lay.addWidget(self._slider, 1)

        self._frame_label = QLabel("0 / 0")
        self._frame_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        self._frame_label.setFixedWidth(110)
        self._frame_label.setToolTip("Current / total")
        self._frame_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        lay.addWidget(self._frame_label)

        # Display-mode toggle for the counter — frames or seconds.
        # Default: frames (animator convention). Session-local; not persisted.
        # PLACEHOLDER icons: keyframe icon for frames, clock for seconds.
        # Swap when final assets are provided.
        self._show_as_frames = True
        self._icon_frames = self._load_icon('next_keyframe.svg')
        self._icon_seconds = self._load_icon('mod_time.svg')
        self._mode_btn = QPushButton()
        self._mode_btn.setFixedSize(24, 22)
        self._mode_btn.setCheckable(True)
        self._mode_btn.setChecked(True)
        self._mode_btn.setToolTip("Click to switch between frames and seconds")
        self._mode_btn.setIconSize(QSize(14, 14))
        if self._icon_frames is not None:
            self._mode_btn.setIcon(self._icon_frames)
        else:
            self._mode_btn.setText("f")  # text fallback if icon missing
        self._mode_btn.toggled.connect(self._on_display_mode_toggled)
        lay.addWidget(self._mode_btn)

        # FPS picker — persisted in QSettings so it sticks across sessions.
        # Frame count is fixed (computed at _SOURCE_FPS); this picker controls
        # PLAYBACK SPEED — higher FPS = animation plays faster, same frames.
        self._fps_combo = QComboBox()
        self._fps_combo.setToolTip(
            "Playback rate. Higher FPS plays the animation faster — "
            "the frame count stays the same."
        )
        for fps in (24, 25, 30, 48, 50, 60, 120):
            self._fps_combo.addItem(f"{fps} fps", fps)
        saved_fps = get_viewport_fps()
        idx = self._fps_combo.findData(saved_fps)
        if idx < 0:
            self._fps_combo.addItem(f"{saved_fps} fps", saved_fps)
            idx = self._fps_combo.count() - 1
        self._fps_combo.setCurrentIndex(idx)
        self._fps_combo.currentIndexChanged.connect(self._on_fps_changed)
        lay.addWidget(self._fps_combo)

        # Playback speed — session-local, defaults to 1.0×.
        self._speed_combo = QComboBox()
        self._speed_combo.setToolTip("Playback speed")
        for speed in (0.25, 0.5, 1.0, 1.5, 2.0, 4.0):
            self._speed_combo.addItem(self._format_speed(speed), speed)
        # Default 1.0×
        idx_one = self._speed_combo.findData(1.0)
        if idx_one >= 0:
            self._speed_combo.setCurrentIndex(idx_one)
        lay.addWidget(self._speed_combo)

        self._loop_check = QCheckBox("Loop")
        self._loop_check.setChecked(True)
        self._loop_check.setToolTip("Loop the animation when it reaches the end")
        lay.addWidget(self._loop_check)

        return row

    @staticmethod
    def _format_speed(speed: float) -> str:
        if speed == int(speed):
            return f"{int(speed)}×"
        return f"{speed}×"

    @staticmethod
    def _title_for(asset_name: Optional[str]) -> str:
        if asset_name:
            return f"3D Preview — {asset_name}"
        return "3D Preview"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_glb(self, path: str):
        """Load and display a .glb file. Path resolution is the caller's job."""
        # Stop playback while the new asset loads. _on_loaded will re-enable
        # the timeline if the new asset has animations.
        self._stop_playback()
        self._current_glb_path = path
        if self._viewport is not None:
            self._viewport.load_glb(path)

    # ------------------------------------------------------------------
    # Toolbar handlers
    # ------------------------------------------------------------------

    def _on_reset(self):
        if self._viewport is not None:
            self._viewport.reset_camera()

    def _on_pick_bg(self):
        current = get_viewport_bg_color()
        color = QColorDialog.getColor(
            current, self, "3D Preview Background",
            QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if color.isValid():
            # Persist + broadcast — every open viewport (panel + this dialog)
            # picks up the change live via viewport_settings signals.
            set_viewport_bg_color(color)

    def _on_light_clicked(self):
        """Open the directional-light direction dialog. Non-modal so the
        user can drag sliders and see live preview behind it."""
        dlg = LightDirectionDialog(self)
        dlg.show()
        dlg.raise_()

    # ------------------------------------------------------------------
    # Viewport signals
    # ------------------------------------------------------------------

    def _on_loaded(self, path: str):
        self._status.setText("")
        self._refresh_timeline_for_loaded_asset()

    def _on_failed(self, path: str, error: str):
        self._status.setText(f"Failed: {error}")
        self._timeline_row.hide()
        self._stop_playback()

    def _on_no_context(self):
        self._status.setText("3D preview unavailable on this system")
        self._reset_btn.setEnabled(False)
        self._bg_btn.setEnabled(False)
        self._timeline_row.hide()
        self._stop_playback()

    # ------------------------------------------------------------------
    # Animation timeline logic
    # ------------------------------------------------------------------

    def _refresh_timeline_for_loaded_asset(self):
        """Called after a successful load. Populates the animation picker
        and shows / hides the timeline based on whether the asset has any
        animations."""
        if self._viewport is None:
            return
        names = self._viewport.animation_names()
        # Diagnostic so we can immediately see whether the .glb itself lacks
        # animations vs the UI failing to surface them.
        if self._current_glb_path:
            import logging
            logging.getLogger(__name__).info(
                f"[EnlargedViewerDialog] loaded {self._current_glb_path}: "
                f"{len(names)} animation(s) — {names if names else 'none'}"
            )
        if not names:
            self._timeline_row.hide()
            self._stop_playback()
            return

        self._timeline_row.show()

        # Populate combo without firing change handlers
        self._anim_combo.blockSignals(True)
        self._anim_combo.clear()
        for n in names:
            self._anim_combo.addItem(n)
        self._anim_combo.setCurrentIndex(0)
        self._anim_combo.blockSignals(False)

        self._reset_to_animation(0)

    def _reset_to_animation(self, idx: int):
        """Switch the viewport to animation `idx`, rewind to t=0, pause."""
        if self._viewport is None:
            return
        self._viewport.set_current_animation(idx)
        dur = self._viewport.animation_duration(idx)

        self._slider.blockSignals(True)
        self._slider.setMaximum(max(1, int(dur * 1000)))
        self._slider.setValue(0)
        self._slider.blockSignals(False)

        self._update_frame_label(0.0, dur)
        self._stop_playback()

    def _on_anim_changed(self, idx: int):
        if idx < 0:
            return
        self._reset_to_animation(idx)

    def _on_slider_changed(self, value_ms: int):
        """User dragged the scrubber — seek the viewport."""
        if self._viewport is None:
            return
        t = value_ms / 1000.0
        self._viewport.set_current_time(t)
        dur = self._viewport.animation_duration()
        self._update_frame_label(t, dur)
        # If we were mid-playback, the next tick mustn't gobble pre-seek time.
        self._elapsed.restart()

    def _on_fps_changed(self, idx: int):
        """Persist the new playback rate. Frame count stays the same, but
        if the counter is in seconds mode the displayed seconds change
        (240 frames at 60 fps = 4 s, at 24 fps = 10 s)."""
        fps = self._fps_combo.currentData()
        if isinstance(fps, int):
            set_viewport_fps(fps)
        # Reset the wall-clock baseline so the speed change kicks in cleanly
        # mid-playback instead of "catching up" via the next tick.
        self._elapsed.restart()
        # Refresh the counter — seconds mode depends on the playback FPS.
        if self._viewport is not None:
            cur = self._slider.value() / 1000.0
            dur = self._viewport.animation_duration()
            self._update_frame_label(cur, dur)

    def _current_fps(self) -> int:
        v = self._fps_combo.currentData()
        return int(v) if isinstance(v, (int, float)) else 30

    def _current_speed(self) -> float:
        v = self._speed_combo.currentData()
        return float(v) if isinstance(v, (int, float)) else 1.0

    def _on_play_toggled(self, playing: bool):
        if self._viewport is None:
            return
        if playing:
            if self._viewport.animation_duration() <= 0:
                # Nothing to play — undo the toggle
                self._play_btn.blockSignals(True)
                self._play_btn.setChecked(False)
                self._play_btn.blockSignals(False)
                return
            self._play_btn.setText("⏸")
            self._elapsed.restart()
            self._timer.start()
        else:
            self._play_btn.setText("▶")
            self._timer.stop()

    def _on_timer_tick(self):
        """Advance current time by wall-clock elapsed since last tick,
        scaled by FPS-vs-source-FPS rate and the playback-speed combo.

        At picker_fps = _SOURCE_FPS and speed = 1×, this plays at native
        speed. At picker_fps = 60 with _SOURCE_FPS = 24, the animation plays
        60/24 = 2.5× faster (same frame count, less wall-clock time)."""
        if self._viewport is None:
            return
        elapsed_s = self._elapsed.restart() / 1000.0
        rate_scale = self._current_fps() / self._SOURCE_FPS
        elapsed_s *= rate_scale * self._current_speed()
        dur = self._viewport.animation_duration()
        if dur <= 0:
            self._stop_playback()
            return

        cur = self._slider.value() / 1000.0
        next_t = cur + elapsed_s

        if next_t >= dur:
            if self._loop_check.isChecked():
                next_t = next_t % dur
            else:
                # Stop at the end, leave slider at duration
                next_t = dur
                self._stop_playback()

        self._viewport.set_current_time(next_t)
        self._slider.blockSignals(True)
        self._slider.setValue(int(next_t * 1000))
        self._slider.blockSignals(False)
        self._update_frame_label(next_t, dur)

    def _stop_playback(self):
        """Halt the timer and unpress the play button (without re-entering)."""
        self._timer.stop()
        if hasattr(self, '_play_btn'):
            if self._play_btn.isChecked():
                self._play_btn.blockSignals(True)
                self._play_btn.setChecked(False)
                self._play_btn.blockSignals(False)
            self._play_btn.setText("▶")

    def _update_frame_label(self, cur_seconds: float, dur_seconds: float):
        """Refresh the counter — frames or seconds, based on the toggle.

        Frame count is computed against _SOURCE_FPS (constant) — a 240-frame
        anim always shows 240.

        Seconds display = frames / picker_fps. At picker = 60 fps, a 240-frame
        anim shows 4.0 seconds (not 10), reflecting wall-clock playback time
        at the chosen rate."""
        cur_f = cur_seconds * self._SOURCE_FPS
        total_f = dur_seconds * self._SOURCE_FPS

        if self._show_as_frames:
            self._frame_label.setText(
                f"{int(round(cur_f))} / {int(round(total_f))}"
            )
        else:
            playback_fps = self._current_fps()
            if playback_fps <= 0:
                playback_fps = self._SOURCE_FPS
            cur_s = cur_f / playback_fps
            total_s = total_f / playback_fps
            self._frame_label.setText(
                f"{self._format_seconds(cur_s)} / "
                f"{self._format_seconds(total_s)}"
            )

    @staticmethod
    def _format_seconds(t: float) -> str:
        m = int(t // 60)
        s = t - m * 60
        return f"{m}:{s:04.1f}"

    def _on_display_mode_toggled(self, checked: bool):
        """User clicked the frames/seconds toggle."""
        self._show_as_frames = checked
        # Update icon (icons preferred; fall back to text if icons absent)
        icon = self._icon_frames if checked else self._icon_seconds
        if icon is not None:
            self._mode_btn.setIcon(icon)
            self._mode_btn.setText("")
        else:
            self._mode_btn.setText("f" if checked else "s")
        # Refresh the label with the new format right now (don't wait for
        # the next playback tick or slider event).
        if self._viewport is not None:
            cur = self._slider.value() / 1000.0
            dur = self._viewport.animation_duration()
            self._update_frame_label(cur, dur)

    @staticmethod
    def _load_icon(filename: str):
        """Return a QIcon from the project's icons dir, or None if missing."""
        path = _ICONS_DIR / filename
        if path.is_file():
            return QIcon(str(path))
        return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """Ensure the playback timer stops when the dialog closes."""
        self._timer.stop()
        super().closeEvent(event)


__all__ = ['EnlargedViewerDialog']
