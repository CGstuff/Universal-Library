"""
Theme system for Universal Library

Provides theme management and built-in themes.
"""

from .theme_manager import Theme, ColorPalette, ThemeManager, get_theme_manager
from .dark_theme import DarkTheme
from .light_theme import LightTheme

__all__ = [
    'Theme',
    'ColorPalette',
    'ThemeManager',
    'get_theme_manager',
    'DarkTheme',
    'LightTheme',
]
