"""
ThemeManager - Centralized theme management

Pattern: Singleton with strategy pattern for theme switching
Based on animation_library architecture.
"""

from typing import Optional, List
from dataclasses import dataclass, asdict
from pathlib import Path
import json

from PyQt6.QtCore import QObject, pyqtSignal, QSettings


@dataclass
class ColorPalette:
    """Color palette for a theme"""

    # Background colors
    background: str
    background_secondary: str

    # Text colors
    text_primary: str
    text_secondary: str
    text_disabled: str

    # Accent colors
    accent: str
    accent_hover: str
    accent_pressed: str

    # Card colors
    card_background: str
    card_border: str
    card_selected: str

    # Button colors
    button_background: str
    button_hover: str
    button_pressed: str
    button_disabled: str

    # Status colors
    error: str
    warning: str
    success: str

    # Border/Divider colors
    border: str
    divider: str

    # Header colors (optional with defaults)
    header_gradient_start: str = "#1a5276"
    header_gradient_end: str = "#2874a6"
    header_icon_color: str = "#ffffff"

    # List item colors (for dropdowns, lists, menus)
    list_item_background: str = "#3A3A3A"
    list_item_hover: str = "#4A4A4A"
    list_item_selected: str = "#3A8FB7"
    selection_border: str = "#D4AF37"


class Theme:
    """Base theme class"""

    def __init__(self, name: str, palette: ColorPalette, is_dark: bool = True):
        self.name = name
        self.palette = palette
        self.is_dark = is_dark

    def get_stylesheet(self) -> str:
        """Generate Qt stylesheet for this theme"""
        raise NotImplementedError("Subclasses must implement get_stylesheet()")

    @classmethod
    def from_json_file(cls, filepath: Path) -> 'Theme':
        """Load theme from JSON file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> 'Theme':
        """Create theme from dictionary"""
        from .dark_theme import DarkTheme

        name = data.get('name', 'Custom Theme')
        is_dark = data.get('is_dark', True)
        colors = data.get('colors', {})

        # Map JSON to ColorPalette
        palette = ColorPalette(
            background=colors.get('background', '#1e1e1e'),
            background_secondary=colors.get('background_secondary', '#2d2d2d'),
            text_primary=colors.get('text_primary', '#e0e0e0'),
            text_secondary=colors.get('text_secondary', '#a0a0a0'),
            text_disabled=colors.get('text_disabled', '#606060'),
            accent=colors.get('accent', '#0078d4'),
            accent_hover=colors.get('accent_hover', '#1084d8'),
            accent_pressed=colors.get('accent_pressed', '#006cc1'),
            card_background=colors.get('card_background', '#2d2d2d'),
            card_border=colors.get('card_border', '#404040'),
            card_selected=colors.get('card_selected', '#0078d4'),
            button_background=colors.get('button_background', '#3d3d3d'),
            button_hover=colors.get('button_hover', '#4d4d4d'),
            button_pressed=colors.get('button_pressed', '#2d2d2d'),
            button_disabled=colors.get('button_disabled', '#252525'),
            error=colors.get('error', '#ff6b6b'),
            warning=colors.get('warning', '#ffa500'),
            success=colors.get('success', '#4CAF50'),
            border=colors.get('border', '#404040'),
            divider=colors.get('divider', '#353535'),
            list_item_background=colors.get('list_item_background', '#3A3A3A'),
            list_item_hover=colors.get('list_item_hover', '#4A4A4A'),
            list_item_selected=colors.get('list_item_selected', '#0078d4'),
            selection_border=colors.get('selection_border', '#0078d4'),
        )

        # Create theme that uses DarkTheme's stylesheet generator
        theme = DarkTheme.__new__(DarkTheme)
        theme.name = name
        theme.palette = palette
        theme.is_dark = is_dark
        return theme


class ThemeManager(QObject):
    """
    Manages application themes and style switching

    Usage:
        theme_manager = get_theme_manager()
        theme_manager.set_theme("Dark")
        stylesheet = theme_manager.get_current_stylesheet()
    """

    # Signals
    theme_changed = pyqtSignal(str)  # Emits theme name when theme changes

    def __init__(self):
        super().__init__()
        self._themes = {}
        self._current_theme: Optional[Theme] = None
        self._load_builtin_themes()
        self._load_custom_themes()

    def register_theme(self, theme: Theme):
        """Register a theme"""
        self._themes[theme.name] = theme

    def set_theme(self, theme_name: str):
        """Set active theme"""
        if theme_name not in self._themes:
            available = list(self._themes.keys())
            raise ValueError(f"Theme '{theme_name}' not found. Available: {available}")

        self._current_theme = self._themes[theme_name]

        # Save preference
        from ..config import Config
        settings = QSettings(Config.APP_AUTHOR, Config.APP_NAME)
        settings.setValue("theme/current", theme_name)

        self.theme_changed.emit(theme_name)

    def get_current_theme(self) -> Optional[Theme]:
        """Get currently active theme"""
        return self._current_theme

    def get_current_stylesheet(self) -> str:
        """Get stylesheet for current theme"""
        if self._current_theme is None:
            return ""
        return self._current_theme.get_stylesheet()

    def get_theme_names(self) -> List[str]:
        """Get list of available theme names"""
        return list(self._themes.keys())

    def get_all_themes(self) -> List[Theme]:
        """Get list of all available themes"""
        return list(self._themes.values())

    def _load_builtin_themes(self):
        """Load built-in themes"""
        from .dark_theme import DarkTheme
        from .light_theme import LightTheme

        self.register_theme(DarkTheme())
        self.register_theme(LightTheme())

    def _load_custom_themes(self):
        """Load user custom themes from JSON files"""
        from ..config import Config

        custom_dir = Config.get_data_directory() / 'themes' / 'custom'
        if not custom_dir.exists():
            return

        for json_file in custom_dir.glob('*.json'):
            try:
                theme = Theme.from_json_file(json_file)
                self.register_theme(theme)
            except Exception as e:
                pass

    def save_custom_theme(self, theme: Theme) -> bool:
        """
        Save custom theme to JSON file

        Args:
            theme: Theme to save

        Returns:
            True if saved successfully
        """
        from ..config import Config

        custom_dir = Config.get_data_directory() / 'themes' / 'custom'
        custom_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize theme name for filename
        filename = theme.name.lower().replace(' ', '_') + '.json'
        filepath = custom_dir / filename

        try:
            theme_data = {
                'name': theme.name,
                'is_dark': theme.is_dark,
                'colors': asdict(theme.palette)
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(theme_data, f, indent=2)

            # Register the theme
            self.register_theme(theme)
            return True

        except Exception as e:
            return False

    def delete_custom_theme(self, theme_name: str) -> bool:
        """
        Delete custom theme

        Args:
            theme_name: Name of theme to delete

        Returns:
            True if deleted successfully
        """
        from ..config import Config

        custom_dir = Config.get_data_directory() / 'themes' / 'custom'
        filename = theme_name.lower().replace(' ', '_') + '.json'
        filepath = custom_dir / filename

        try:
            if filepath.exists():
                filepath.unlink()

            # Remove from registered themes
            if theme_name in self._themes:
                del self._themes[theme_name]

            return True

        except Exception as e:
            return False

    def is_builtin_theme(self, theme_name: str) -> bool:
        """
        Check if a theme is built-in (not custom)

        Args:
            theme_name: Name of theme to check

        Returns:
            True if theme is built-in
        """
        return theme_name in ['Dark', 'Light']

    def import_theme(self, filepath: Path) -> bool:
        """
        Import theme from external JSON file

        Args:
            filepath: Path to JSON theme file

        Returns:
            True if imported successfully
        """
        try:
            theme = Theme.from_json_file(filepath)
            return self.save_custom_theme(theme)
        except Exception as e:
            return False

    def export_theme(self, theme_name: str, filepath: Path) -> bool:
        """
        Export theme to JSON file

        Args:
            theme_name: Name of theme to export
            filepath: Path to save JSON file

        Returns:
            True if exported successfully
        """
        if theme_name not in self._themes:
            return False

        try:
            theme = self._themes[theme_name]
            theme_data = {
                'name': theme.name,
                'is_dark': theme.is_dark,
                'colors': asdict(theme.palette)
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(theme_data, f, indent=2)

            return True

        except Exception as e:
            return False

    def get_custom_themes_dir(self) -> Path:
        """Get the custom themes directory path"""
        from ..config import Config
        return Config.get_data_directory() / 'themes' / 'custom'


# Singleton instance
_theme_manager_instance: Optional[ThemeManager] = None


def get_theme_manager() -> ThemeManager:
    """Get global ThemeManager singleton instance"""
    global _theme_manager_instance

    if _theme_manager_instance is None:
        _theme_manager_instance = ThemeManager()

        # Load saved theme preference
        from ..config import Config
        settings = QSettings(Config.APP_AUTHOR, Config.APP_NAME)
        saved_theme = settings.value("theme/current", "Dark")

        # Set theme
        try:
            _theme_manager_instance.set_theme(saved_theme)
        except ValueError:
            # Fallback to Dark theme
            try:
                _theme_manager_instance.set_theme("Dark")
            except ValueError:
                # Use first available
                themes = _theme_manager_instance.get_theme_names()
                if themes:
                    _theme_manager_instance.set_theme(themes[0])

    return _theme_manager_instance


__all__ = ['Theme', 'ColorPalette', 'ThemeManager', 'get_theme_manager']
