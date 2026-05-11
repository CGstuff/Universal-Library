"""
LightDirectionDialog — small non-modal popup for adjusting the 3D viewport's
directional-light angle.

Two sliders (azimuth + elevation). Changes are saved to QSettings live via
viewport_settings, which broadcasts to every open AssetViewport so they
all update without re-opening anything.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSizePolicy,
)

from ...services.viewport_settings import (
    get_viewport_light, set_viewport_light, default_light,
)


class LightDirectionDialog(QDialog):
    """Compact popover with two sliders: azimuth (0–360°) and elevation
    (−89–89°). Updates global preferences live."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Viewport Light")
        self.setModal(False)
        self.setSizeGripEnabled(False)
        self.setFixedSize(360, 170)

        az, el = get_viewport_light()
        self._setup_ui(az, el)

    def _setup_ui(self, az: float, el: float):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        title = QLabel("Adjust where the light shines from. Applies globally.")
        title.setStyleSheet("color: #888; font-size: 11px;")
        title.setWordWrap(True)
        outer.addWidget(title)

        # Azimuth row
        outer.addLayout(self._slider_row(
            "Azimuth",
            int(round(az)),
            0, 360, '°',
            self._on_azimuth_changed,
        ))
        # Elevation row
        outer.addLayout(self._slider_row(
            "Elevation",
            int(round(el)),
            -89, 89, '°',
            self._on_elevation_changed,
        ))

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        reset = QPushButton("Reset")
        reset.clicked.connect(self._on_reset)
        btn_row.addWidget(reset)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        btn_row.addWidget(close)
        outer.addLayout(btn_row)

    def _slider_row(self, label_text: str, value: int, lo: int, hi: int,
                    suffix: str, on_change) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        label = QLabel(label_text)
        label.setFixedWidth(70)
        row.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(lo)
        slider.setMaximum(hi)
        slider.setValue(value)
        slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(slider, 1)

        value_label = QLabel(f"{value}{suffix}")
        value_label.setFixedWidth(40)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(value_label)

        slider.valueChanged.connect(
            lambda v: (value_label.setText(f"{v}{suffix}"), on_change(v))
        )

        # Stash references so reset can update them later
        if label_text == "Azimuth":
            self._az_slider = slider
            self._az_label = value_label
        else:
            self._el_slider = slider
            self._el_label = value_label

        return row

    def _on_azimuth_changed(self, v: int):
        _, el = get_viewport_light()
        set_viewport_light(float(v), el)

    def _on_elevation_changed(self, v: int):
        az, _ = get_viewport_light()
        set_viewport_light(az, float(v))

    def _on_reset(self):
        az, el = default_light()
        # Block signals so the two slider sets don't fire two settings writes
        self._az_slider.blockSignals(True)
        self._az_slider.setValue(int(round(az)))
        self._az_slider.blockSignals(False)
        self._az_label.setText(f"{int(round(az))}°")

        self._el_slider.blockSignals(True)
        self._el_slider.setValue(int(round(el)))
        self._el_slider.blockSignals(False)
        self._el_label.setText(f"{int(round(el))}°")

        set_viewport_light(az, el)


__all__ = ['LightDirectionDialog']
