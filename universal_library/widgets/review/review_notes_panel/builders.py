"""
List builders for review notes panel.
"""

from typing import List, Dict, Callable, Optional

from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt

from .note_item import NoteItemWidget


def build_flat_notes_list(
    notes_layout: QVBoxLayout,
    visible_notes: List[Dict],
    marker_indices: Dict[int, int],
    is_studio_mode: bool,
    current_user: str,
    current_user_role: str,
    connect_fn: Callable[[NoteItemWidget], None]
) -> List[NoteItemWidget]:
    """
    Build a flat list of notes (non-grouped).

    Args:
        notes_layout: Layout to add widgets to
        visible_notes: List of note dicts to display
        marker_indices: Map of note_id to marker index
        is_studio_mode: Whether studio mode is enabled
        current_user: Current username
        current_user_role: Current user role
        connect_fn: Function to connect widget signals

    Returns:
        List of created NoteItemWidget instances
    """
    note_widgets = []

    for note_data in visible_notes:
        is_deleted = note_data.get('deleted', 0) == 1
        marker_index = 0 if is_deleted else marker_indices.get(note_data.get('id'), 0)

        widget = NoteItemWidget(
            note_data,
            is_studio_mode=is_studio_mode,
            current_user=current_user,
            current_user_role=current_user_role,
            marker_index=marker_index
        )
        connect_fn(widget)
        notes_layout.addWidget(widget)
        note_widgets.append(widget)

    return note_widgets


def build_version_grouped_notes(
    notes_layout: QVBoxLayout,
    visible_notes: List[Dict],
    marker_indices: Dict[int, int],
    current_version: Optional[str],
    is_studio_mode: bool,
    current_user: str,
    current_user_role: str,
    connect_fn: Callable[[NoteItemWidget], None]
) -> List[NoteItemWidget]:
    """
    Build notes grouped by version with collapsible headers.

    Args:
        notes_layout: Layout to add widgets to
        visible_notes: List of note dicts to display
        marker_indices: Map of note_id to marker index
        current_version: Version label to highlight as current
        is_studio_mode: Whether studio mode is enabled
        current_user: Current username
        current_user_role: Current user role
        connect_fn: Function to connect widget signals

    Returns:
        List of created NoteItemWidget instances
    """
    from collections import OrderedDict

    note_widgets = []

    # Group by version_label
    version_groups: Dict[str, List[Dict]] = OrderedDict()
    for note in visible_notes:
        version = note.get('version_label', 'Unknown')
        if version not in version_groups:
            version_groups[version] = []
        version_groups[version].append(note)

    # Sort versions (newest first)
    sorted_versions = sorted(version_groups.keys(), reverse=True)

    for version_label in sorted_versions:
        notes_in_version = version_groups[version_label]

        # Count stats
        open_count = sum(1 for n in notes_in_version if n.get('note_status') == 'open' and n.get('deleted', 0) != 1)
        addressed_count = sum(1 for n in notes_in_version if n.get('note_status') == 'addressed' and n.get('deleted', 0) != 1)
        approved_count = sum(1 for n in notes_in_version if n.get('note_status') == 'approved' and n.get('deleted', 0) != 1)
        total_active = open_count + addressed_count + approved_count

        # Create header
        is_current = version_label == current_version
        header = create_version_header(
            version_label, total_active,
            open_count, addressed_count, approved_count,
            is_current
        )
        notes_layout.addWidget(header)

        # Add notes
        for note_data in notes_in_version:
            is_deleted = note_data.get('deleted', 0) == 1
            marker_index = 0 if is_deleted else marker_indices.get(note_data.get('id'), 0)

            widget = NoteItemWidget(
                note_data,
                is_studio_mode=is_studio_mode,
                current_user=current_user,
                current_user_role=current_user_role,
                marker_index=marker_index
            )
            connect_fn(widget)
            notes_layout.addWidget(widget)
            note_widgets.append(widget)

    return note_widgets


def create_version_header(
    version_label: str,
    total_count: int,
    open_count: int,
    addressed_count: int,
    approved_count: int,
    is_current: bool
) -> QFrame:
    """
    Create a version group header with note status counts.

    Args:
        version_label: Version label (e.g., "v001")
        total_count: Total active notes in this version
        open_count: Open note count
        addressed_count: Addressed note count
        approved_count: Approved note count
        is_current: Whether this is the current version

    Returns:
        QFrame widget for the header
    """
    header = QFrame()
    header.setStyleSheet(f"""
        QFrame {{
            background: {'#2a3a3a' if is_current else '#252525'};
            border: 1px solid {'#4a6a6a' if is_current else '#333'};
            border-radius: 0px;
            margin-top: 8px;
        }}
    """)

    layout = QHBoxLayout(header)
    layout.setContentsMargins(10, 6, 10, 6)
    layout.setSpacing(8)

    # Version label
    version_text = f"\u25bc {version_label}"
    if is_current:
        version_text += " (current)"
    label = QLabel(version_text)
    label.setStyleSheet(f"""
        color: {'#8BC34A' if is_current else '#aaa'};
        font-size: 12px;
        font-weight: bold;
    """)
    layout.addWidget(label)

    layout.addStretch()

    # Status count badges
    if open_count > 0:
        open_badge = QLabel(f"\u25cf {open_count}")
        open_badge.setStyleSheet("color: #FF9800; font-size: 11px;")
        open_badge.setToolTip(f"{open_count} open")
        layout.addWidget(open_badge)

    if addressed_count > 0:
        addr_badge = QLabel(f"\u25cf {addressed_count}")
        addr_badge.setStyleSheet("color: #00BCD4; font-size: 11px;")
        addr_badge.setToolTip(f"{addressed_count} addressed")
        layout.addWidget(addr_badge)

    if approved_count > 0:
        appr_badge = QLabel(f"\u25cf {approved_count}")
        appr_badge.setStyleSheet("color: #4CAF50; font-size: 11px;")
        appr_badge.setToolTip(f"{approved_count} approved")
        layout.addWidget(appr_badge)

    return header


__all__ = [
    'build_flat_notes_list',
    'build_version_grouped_notes',
    'create_version_header',
]
