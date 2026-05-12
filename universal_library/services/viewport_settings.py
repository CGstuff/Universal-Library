"""
Settings for the 3D asset preview viewport.

Wraps QSettings for the small set of preferences specific to the 3D viewport
(currently: background color). Exposes a Qt signal so any open viewport can
react live when the user changes the color in Preferences.

Public API:
    get_viewport_bg_color() -> QColor          read current value
    set_viewport_bg_color(QColor)              write + broadcast change
    viewport_settings_signals() -> ViewportSettingsSignals
                                                singleton with `bg_changed` signal
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtGui import QColor

from ..config import Config


_KEY_BG = "3d_preview/background_color"
_KEY_LIGHT_AZ = "3d_preview/light_azimuth"
_KEY_LIGHT_EL = "3d_preview/light_elevation"
_KEY_FPS = "3d_preview/fps"
_KEY_SCALE_REF_ENABLED = "3d_preview/scale_ref_enabled"
_KEY_SCALE_REF_HEIGHT = "3d_preview/scale_ref_height"

_DEFAULT_BG_HEX = "#404040"           # neutral mid-gray
_DEFAULT_LIGHT_AZ = 45.0              # degrees, horizontal (0 = +Y, 90 = +X)
_DEFAULT_LIGHT_EL = 35.0              # degrees above horizon
_DEFAULT_FPS = 30
_DEFAULT_SCALE_REF_ENABLED = False
_DEFAULT_SCALE_REF_HEIGHT = 1.8       # metres


class ViewportSettingsSignals(QObject):
    """Lives for the app lifetime. Emits when 3D preview settings change."""
    bg_changed = pyqtSignal(QColor)
    light_changed = pyqtSignal(float, float)   # azimuth, elevation (degrees)
    scale_ref_changed = pyqtSignal(bool, float)  # enabled, height_m


_signals: Optional[ViewportSettingsSignals] = None


def viewport_settings_signals() -> ViewportSettingsSignals:
    global _signals
    if _signals is None:
        _signals = ViewportSettingsSignals()
    return _signals


def _settings() -> QSettings:
    return QSettings(Config.APP_AUTHOR, Config.APP_NAME)


def get_viewport_bg_color() -> QColor:
    raw = _settings().value(_KEY_BG, _DEFAULT_BG_HEX, type=str)
    color = QColor(raw)
    if not color.isValid():
        color = QColor(_DEFAULT_BG_HEX)
    return color


def set_viewport_bg_color(color: QColor) -> None:
    if not color.isValid():
        return
    _settings().setValue(_KEY_BG, color.name())
    viewport_settings_signals().bg_changed.emit(color)


def default_bg_hex() -> str:
    return _DEFAULT_BG_HEX


def get_viewport_light() -> tuple:
    """Return (azimuth_deg, elevation_deg) of the directional light."""
    s = _settings()
    az = s.value(_KEY_LIGHT_AZ, _DEFAULT_LIGHT_AZ, type=float)
    el = s.value(_KEY_LIGHT_EL, _DEFAULT_LIGHT_EL, type=float)
    return float(az), float(el)


def set_viewport_light(azimuth_deg: float, elevation_deg: float) -> None:
    az = max(0.0, min(360.0, float(azimuth_deg)))
    el = max(-89.0, min(89.0, float(elevation_deg)))
    s = _settings()
    s.setValue(_KEY_LIGHT_AZ, az)
    s.setValue(_KEY_LIGHT_EL, el)
    viewport_settings_signals().light_changed.emit(az, el)


def default_light() -> tuple:
    """The compiled-in default light direction (for the picker's Reset button)."""
    return _DEFAULT_LIGHT_AZ, _DEFAULT_LIGHT_EL


def get_viewport_fps() -> int:
    """Default framerate for the timeline frame counter."""
    return int(_settings().value(_KEY_FPS, _DEFAULT_FPS, type=int))


def set_viewport_fps(fps: int) -> None:
    fps = max(1, min(240, int(fps)))
    _settings().setValue(_KEY_FPS, fps)


def get_scale_ref_enabled() -> bool:
    """Whether the scale-reference silhouette is rendered in 3D previews."""
    raw = _settings().value(_KEY_SCALE_REF_ENABLED, _DEFAULT_SCALE_REF_ENABLED, type=bool)
    return bool(raw)


def get_scale_ref_height() -> float:
    """Reference height in metres."""
    return float(_settings().value(_KEY_SCALE_REF_HEIGHT, _DEFAULT_SCALE_REF_HEIGHT, type=float))


def set_scale_ref(enabled: bool, height_m: float) -> None:
    """Update both scale-ref settings and broadcast."""
    height_m = max(0.1, min(10.0, float(height_m)))
    s = _settings()
    s.setValue(_KEY_SCALE_REF_ENABLED, bool(enabled))
    s.setValue(_KEY_SCALE_REF_HEIGHT, height_m)
    viewport_settings_signals().scale_ref_changed.emit(bool(enabled), height_m)


def default_scale_ref() -> tuple:
    """Compiled-in defaults (enabled, height_m). Used by Reset buttons."""
    return _DEFAULT_SCALE_REF_ENABLED, _DEFAULT_SCALE_REF_HEIGHT
