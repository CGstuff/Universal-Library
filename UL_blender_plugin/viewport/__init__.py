"""
Viewport Module

Provides viewport overlay functionality for the Universal Library.
Displays asset name/version labels on imported library objects.
"""

from .asset_overlay import (
    enable_overlay,
    disable_overlay,
    toggle_overlay,
    is_overlay_enabled,
)

__all__ = [
    'enable_overlay',
    'disable_overlay',
    'toggle_overlay',
    'is_overlay_enabled',
]
