"""
Styling utilities for review notes.
"""

import os
from pathlib import Path
from PyQt6.QtWidgets import QPushButton, QFrame
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon


def get_icon_path(name: str, folder: str = "drawing") -> str:
    """Get path to icon by name and folder."""
    icons_dir = Path(__file__).parent.parent.parent / "icons" / folder
    return str(icons_dir / f"{name}.svg")


def apply_frame_style(frame: QFrame, note_status: str, is_deleted: bool):
    """Apply frame styling based on note status."""
    if is_deleted:
        frame.setStyleSheet("""
            NoteItemWidget { background-color: #1e1e1e; border: 1px dashed #333; border-radius: 0px; }
        """)
    elif note_status == 'approved':
        frame.setStyleSheet("""
            NoteItemWidget { background-color: #252d25; border: 1px solid #3a4a3a; border-radius: 0px; }
            NoteItemWidget:hover { background-color: #2a352a; border-color: #4a5a4a; }
        """)
    elif note_status == 'addressed':
        frame.setStyleSheet("""
            NoteItemWidget { background-color: #252d2d; border: 1px solid #3a4a4a; border-radius: 0px; }
            NoteItemWidget:hover { background-color: #2a3535; border-color: #4a5a5a; }
        """)
    else:
        frame.setStyleSheet("""
            NoteItemWidget { background-color: #2d2a25; border: 1px solid #4a3a3a; border-radius: 0px; }
            NoteItemWidget:hover { background-color: #352a2a; border-color: #5a4a4a; }
        """)


def create_icon_button(
    icon_name: str,
    icon_folder: str,
    tooltip: str,
    color: str,
    hover_color: str,
    callback
) -> QPushButton:
    """Create a small icon button for note actions."""
    btn = QPushButton()
    btn.setFixedSize(24, 24)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(callback)

    icon_path = get_icon_path(icon_name, icon_folder)
    if os.path.exists(icon_path):
        btn.setIcon(QIcon(icon_path))
        btn.setIconSize(QSize(14, 14))

    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            border: none;
            border-radius: 4px;
            padding: 4px;
        }}
        QPushButton:hover {{ background-color: {hover_color}; }}
    """)
    return btn


ROLE_COLORS = {
    'supervisor': '#E91E63',
    'lead': '#9C27B0',
    'admin': '#FF5722',
    'director': '#F44336'
}


def get_role_color(role: str) -> str:
    """Get color for a user role."""
    return ROLE_COLORS.get(role, '#666')


__all__ = [
    'get_icon_path',
    'apply_frame_style',
    'create_icon_button',
    'get_role_color',
    'ROLE_COLORS',
]
