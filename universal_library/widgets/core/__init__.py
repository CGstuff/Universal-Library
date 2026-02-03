"""
Core UI infrastructure for Universal Library widgets.

Provides:
- Colors: Centralized color constants
- ButtonStyles, BadgeStyles: Reusable stylesheet templates
- BasePanel, BaseDialog: Base widget classes
- BadgeFactory: Create consistent status/version/variant badges
"""

from .styles import Colors, ButtonStyles, BadgeStyles, LabelStyles
from .base_widget import BasePanel, BaseDialog, BaseSection
from .badge_factory import BadgeFactory

__all__ = [
    # Styles
    'Colors',
    'ButtonStyles',
    'BadgeStyles',
    'LabelStyles',
    # Base classes
    'BasePanel',
    'BaseDialog',
    'BaseSection',
    # Factories
    'BadgeFactory',
]
