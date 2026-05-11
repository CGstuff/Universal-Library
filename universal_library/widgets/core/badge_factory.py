"""
Badge factory for creating consistent UI badges.

Centralizes badge creation to ensure consistent styling across:
- Version badges (v001, v002, etc.)
- Variant badges (Base, Damaged, etc.)

Usage:
    from universal_library.widgets.core import BadgeFactory

    # Create version badge
    badge = BadgeFactory.create_version_badge('v003')

    # Create variant badge
    badge = BadgeFactory.create_variant_badge('Base', is_base=True)
"""

from typing import Optional
from PyQt6.QtWidgets import QLabel, QWidget
from PyQt6.QtCore import Qt

from .styles import Colors, BadgeStyles


class BadgeFactory:
    """Factory for creating consistent badge widgets."""

    @classmethod
    def create_version_badge(
        cls,
        version_label: str,
        parent: Optional[QWidget] = None
    ) -> QLabel:
        """
        Create a version badge.

        Args:
            version_label: Version string (e.g., 'v001', 'v003')
            parent: Optional parent widget

        Returns:
            QLabel styled as a version badge
        """
        badge = QLabel(version_label, parent)
        badge.setStyleSheet(BadgeStyles.VERSION)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        return badge

    @classmethod
    def create_variant_badge(
        cls,
        variant_name: str,
        is_base: bool = False,
        parent: Optional[QWidget] = None
    ) -> QLabel:
        """
        Create a variant badge.

        Args:
            variant_name: Variant name (e.g., 'Base', 'Damaged')
            is_base: Whether this is the base variant
            parent: Optional parent widget

        Returns:
            QLabel styled as a variant badge
        """
        color = Colors.VARIANT_BASE if is_base else Colors.VARIANT_OTHER
        style = BadgeStyles.colored(color)

        badge = QLabel(variant_name, parent)
        badge.setStyleSheet(style)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        return badge


__all__ = ['BadgeFactory']
