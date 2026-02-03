"""
Badge factory for creating consistent UI badges.

Centralizes badge creation to ensure consistent styling across:
- Review status badges (needs_review, in_progress, approved, final)
- Note status badges (open, addressed, approved)
- Version badges (v001, v002, etc.)
- Variant badges (Base, Damaged, etc.)
- Cycle type badges (Modeling, Texturing, etc.)

Usage:
    from universal_library.widgets.core import BadgeFactory

    # Create status badge
    badge = BadgeFactory.create_status_badge('approved')

    # Create version badge
    badge = BadgeFactory.create_version_badge('v003')

    # Create with cycle type from config
    badge = BadgeFactory.create_cycle_badge('modeling', REVIEW_CYCLE_TYPES)
"""

from typing import Optional, Dict, Any
from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt

from .styles import Colors, BadgeStyles


class BadgeFactory:
    """Factory for creating consistent badge widgets."""

    # Status display names and colors
    STATUS_CONFIG = {
        'needs_review': {
            'label': 'Needs Review',
            'color': Colors.NEEDS_REVIEW,
        },
        'in_review': {
            'label': 'In Review',
            'color': Colors.IN_REVIEW,
        },
        'in_progress': {
            'label': 'In Progress',
            'color': Colors.IN_PROGRESS,
        },
        'approved': {
            'label': 'Approved',
            'color': Colors.APPROVED,
        },
        'final': {
            'label': 'Final',
            'color': Colors.FINAL,
        },
    }

    # Note status config
    NOTE_STATUS_CONFIG = {
        'open': {
            'label': 'Open',
            'color': Colors.NOTE_OPEN,
            'symbol': '●',
        },
        'addressed': {
            'label': 'Addressed',
            'color': Colors.NOTE_ADDRESSED,
            'symbol': '●',
        },
        'approved': {
            'label': 'Approved',
            'color': Colors.NOTE_APPROVED,
            'symbol': '✓',
        },
    }

    @classmethod
    def create_status_badge(
        cls,
        status: str,
        parent: Optional[QWidget] = None
    ) -> QLabel:
        """
        Create a review status badge.

        Args:
            status: Status key (needs_review, in_progress, approved, final)
            parent: Optional parent widget

        Returns:
            QLabel styled as a status badge
        """
        config = cls.STATUS_CONFIG.get(status, {})
        label_text = config.get('label', status.replace('_', ' ').title())
        color = config.get('color', Colors.BADGE_BG)

        badge = QLabel(label_text, parent)
        badge.setStyleSheet(BadgeStyles.colored(color))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        return badge

    @classmethod
    def create_note_status_badge(
        cls,
        status: str,
        parent: Optional[QWidget] = None
    ) -> QLabel:
        """
        Create a note status badge with symbol.

        Args:
            status: Note status (open, addressed, approved)
            parent: Optional parent widget

        Returns:
            QLabel styled as a note status badge
        """
        config = cls.NOTE_STATUS_CONFIG.get(status, {})
        symbol = config.get('symbol', '●')
        color = config.get('color', Colors.TEXT_MUTED)

        badge = QLabel(symbol, parent)
        badge.setStyleSheet(f"""
            color: {color};
            font-size: 12px;
            font-weight: bold;
        """)
        badge.setToolTip(config.get('label', status.title()))

        return badge

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

    @classmethod
    def create_cycle_badge(
        cls,
        cycle_type: str,
        cycle_types_config: Dict[str, Dict[str, Any]],
        parent: Optional[QWidget] = None
    ) -> QLabel:
        """
        Create a review cycle type badge.

        Args:
            cycle_type: Cycle type key (modeling, texturing, etc.)
            cycle_types_config: REVIEW_CYCLE_TYPES dict from config
            parent: Optional parent widget

        Returns:
            QLabel styled as a cycle type badge
        """
        config = cycle_types_config.get(cycle_type, {})
        label_text = config.get('label', cycle_type.title())
        color = config.get('color', Colors.BADGE_BG)

        badge = QLabel(label_text, parent)
        badge.setStyleSheet(BadgeStyles.cycle_type(color))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        return badge

    @classmethod
    def create_composite_badge(
        cls,
        status: str,
        version_label: str,
        variant_name: Optional[str] = None,
        parent: Optional[QWidget] = None
    ) -> QFrame:
        """
        Create a composite badge with status, version, and optional variant.

        Useful for displaying full context in a single widget.

        Args:
            status: Review status
            version_label: Version string
            variant_name: Optional variant name
            parent: Optional parent widget

        Returns:
            QFrame containing multiple badges
        """
        frame = QFrame(parent)
        frame.setStyleSheet(f"""
            QFrame {{
                background: transparent;
            }}
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Add status badge
        status_badge = cls.create_status_badge(status)
        layout.addWidget(status_badge)

        # Add version badge
        version_badge = cls.create_version_badge(version_label)
        layout.addWidget(version_badge)

        # Add variant badge if provided
        if variant_name:
            variant_badge = cls.create_variant_badge(
                variant_name,
                is_base=(variant_name.lower() == 'base')
            )
            layout.addWidget(variant_badge)

        return frame


__all__ = ['BadgeFactory']
