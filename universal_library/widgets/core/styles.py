"""
Centralized styles for Universal Library UI.

All color constants and stylesheet templates in one place.
Never hardcode colors in widgets - import from here.

Usage:
    from universal_library.widgets.core import Colors, ButtonStyles

    button.setStyleSheet(ButtonStyles.PRIMARY)
    label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
"""


class Colors:
    """
    Centralized color palette.

    Naming convention:
    - Semantic names (PRIMARY, SUCCESS) for UI meaning
    - Role names (TEXT_*, BG_*) for specific uses
    """

    # Primary palette
    PRIMARY = "#0078d4"          # Main action color (blue)
    PRIMARY_HOVER = "#1976D2"
    PRIMARY_DARK = "#005a9e"

    # Status colors
    SUCCESS = "#4CAF50"          # Approved, success states
    SUCCESS_HOVER = "#66BB6A"
    SUCCESS_DARK = "#388E3C"

    WARNING = "#FF9800"          # Needs attention, pending
    WARNING_HOVER = "#FFB74D"
    WARNING_DARK = "#F57C00"

    ERROR = "#F44336"            # Error, rejected states
    ERROR_HOVER = "#EF5350"
    ERROR_DARK = "#D32F2F"

    FINAL = "#9C27B0"            # Final/published state (purple)
    FINAL_HOVER = "#AB47BC"
    FINAL_DARK = "#7B1FA2"

    INFO = "#2196F3"             # Informational
    INFO_HOVER = "#42A5F5"

    # Review states (specific meanings)
    NEEDS_REVIEW = WARNING
    IN_REVIEW = WARNING
    IN_PROGRESS = PRIMARY
    APPROVED = SUCCESS
    REVIEW_FINAL = FINAL

    # Note states
    NOTE_OPEN = ERROR
    NOTE_ADDRESSED = WARNING
    NOTE_APPROVED = SUCCESS

    # Text colors
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#aaaaaa"
    TEXT_MUTED = "#888888"
    TEXT_DISABLED = "#666666"

    # Background colors
    BG_DARK = "#1a1a1a"
    BG_MEDIUM = "#252525"
    BG_LIGHT = "#2d2d2d"
    BG_LIGHTER = "#3a3a3a"
    BG_HOVER = "#4a4a4a"
    BG_SELECTED = "#0078d4"

    # Border colors
    BORDER_DARK = "#333333"
    BORDER_LIGHT = "#555555"

    # Badge backgrounds
    BADGE_BG = "#333333"

    # Variant colors
    VARIANT_BASE = "#607D8B"     # Gray-blue for base variant
    VARIANT_OTHER = "#8BC34A"    # Light green for other variants

    # Asset type colors
    TYPE_MESH = "#4FC3F7"        # Light blue
    TYPE_MATERIAL = "#FF8A65"    # Orange
    TYPE_RIG = "#BA68C8"         # Purple
    TYPE_ANIMATION = "#81C784"   # Green
    TYPE_LIGHT = "#FFF176"       # Yellow
    TYPE_CAMERA = "#90A4AE"      # Gray
    TYPE_COLLECTION = "#A1887F"  # Brown


class ButtonStyles:
    """Pre-built button stylesheets."""

    PRIMARY = f"""
        QPushButton {{
            background-color: {Colors.PRIMARY};
            color: {Colors.TEXT_PRIMARY};
            font-weight: bold;
            padding: 8px 16px;
            border-radius: 4px;
            border: none;
        }}
        QPushButton:hover {{
            background-color: {Colors.PRIMARY_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {Colors.PRIMARY_DARK};
        }}
        QPushButton:disabled {{
            background-color: {Colors.BG_LIGHTER};
            color: {Colors.TEXT_DISABLED};
        }}
    """

    SUCCESS = f"""
        QPushButton {{
            background-color: {Colors.SUCCESS};
            color: {Colors.TEXT_PRIMARY};
            font-weight: bold;
            padding: 8px 16px;
            border-radius: 4px;
            border: none;
        }}
        QPushButton:hover {{
            background-color: {Colors.SUCCESS_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {Colors.SUCCESS_DARK};
        }}
        QPushButton:disabled {{
            background-color: {Colors.BG_LIGHTER};
            color: {Colors.TEXT_DISABLED};
        }}
    """

    WARNING = f"""
        QPushButton {{
            background-color: {Colors.WARNING};
            color: {Colors.TEXT_PRIMARY};
            font-weight: bold;
            padding: 8px 16px;
            border-radius: 4px;
            border: none;
        }}
        QPushButton:hover {{
            background-color: {Colors.WARNING_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {Colors.WARNING_DARK};
        }}
        QPushButton:disabled {{
            background-color: {Colors.BG_LIGHTER};
            color: {Colors.TEXT_DISABLED};
        }}
    """

    FINAL = f"""
        QPushButton {{
            background-color: {Colors.FINAL};
            color: {Colors.TEXT_PRIMARY};
            font-weight: bold;
            padding: 8px 16px;
            border-radius: 4px;
            border: none;
        }}
        QPushButton:hover {{
            background-color: {Colors.FINAL_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {Colors.FINAL_DARK};
        }}
        QPushButton:disabled {{
            background-color: {Colors.BG_LIGHTER};
            color: {Colors.TEXT_DISABLED};
        }}
    """

    SECONDARY = f"""
        QPushButton {{
            background-color: {Colors.BG_LIGHTER};
            color: {Colors.TEXT_SECONDARY};
            padding: 8px 16px;
            border-radius: 4px;
            border: 1px solid {Colors.BORDER_LIGHT};
        }}
        QPushButton:hover {{
            background-color: {Colors.BG_HOVER};
            color: {Colors.TEXT_PRIMARY};
        }}
        QPushButton:disabled {{
            background-color: {Colors.BG_MEDIUM};
            color: {Colors.TEXT_DISABLED};
            border-color: {Colors.BORDER_DARK};
        }}
    """

    OUTLINE = f"""
        QPushButton {{
            background-color: transparent;
            color: {Colors.PRIMARY};
            padding: 8px 16px;
            border-radius: 4px;
            border: 1px solid {Colors.PRIMARY};
        }}
        QPushButton:hover {{
            background-color: {Colors.PRIMARY};
            color: {Colors.TEXT_PRIMARY};
        }}
        QPushButton:disabled {{
            color: {Colors.TEXT_DISABLED};
            border-color: {Colors.BORDER_DARK};
        }}
    """

    SMALL = f"""
        QPushButton {{
            background-color: {Colors.BG_LIGHTER};
            color: {Colors.TEXT_SECONDARY};
            padding: 4px 8px;
            border-radius: 3px;
            border: 1px solid {Colors.BORDER_DARK};
            font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: {Colors.BG_HOVER};
            color: {Colors.TEXT_PRIMARY};
        }}
        QPushButton:disabled {{
            color: {Colors.TEXT_DISABLED};
        }}
    """


class BadgeStyles:
    """Pre-built badge/label stylesheets."""

    @staticmethod
    def colored(bg_color: str, text_color: str = Colors.TEXT_PRIMARY) -> str:
        """Generate a colored badge style."""
        return f"""
            background-color: {bg_color};
            color: {text_color};
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
        """

    # Status badges
    NEEDS_REVIEW = colored.__func__(Colors.NEEDS_REVIEW)
    IN_REVIEW = colored.__func__(Colors.IN_REVIEW)
    IN_PROGRESS = colored.__func__(Colors.IN_PROGRESS)
    APPROVED = colored.__func__(Colors.APPROVED)
    FINAL = colored.__func__(Colors.FINAL)

    # Note status badges
    NOTE_OPEN = colored.__func__(Colors.NOTE_OPEN)
    NOTE_ADDRESSED = colored.__func__(Colors.NOTE_ADDRESSED)
    NOTE_APPROVED = colored.__func__(Colors.NOTE_APPROVED)

    # Version badge
    VERSION = f"""
        background-color: {Colors.BADGE_BG};
        color: {Colors.TEXT_SECONDARY};
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 10px;
    """

    # Variant badges
    VARIANT_BASE = colored.__func__(Colors.VARIANT_BASE)
    VARIANT_OTHER = colored.__func__(Colors.VARIANT_OTHER)

    # Cycle type badges (use REVIEW_CYCLE_TYPES colors from config)
    @staticmethod
    def cycle_type(color: str) -> str:
        """Generate a cycle type badge style."""
        return f"""
            background-color: {color};
            color: {Colors.TEXT_PRIMARY};
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
        """


class LabelStyles:
    """Pre-built label stylesheets."""

    HEADING = f"""
        color: {Colors.TEXT_PRIMARY};
        font-size: 14px;
        font-weight: bold;
    """

    SUBHEADING = f"""
        color: {Colors.TEXT_SECONDARY};
        font-size: 12px;
        font-weight: bold;
    """

    BODY = f"""
        color: {Colors.TEXT_SECONDARY};
        font-size: 11px;
    """

    MUTED = f"""
        color: {Colors.TEXT_MUTED};
        font-size: 11px;
    """

    ERROR = f"""
        color: {Colors.ERROR};
        font-size: 11px;
    """

    SUCCESS = f"""
        color: {Colors.SUCCESS};
        font-size: 11px;
    """


__all__ = ['Colors', 'ButtonStyles', 'BadgeStyles', 'LabelStyles']
