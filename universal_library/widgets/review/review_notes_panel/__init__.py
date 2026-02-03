"""
Review Notes Panel - Note management for asset review.

Modular structure:
- note_item.py: NoteItemWidget - single note display
- builders.py: List building logic
- styling.py: Frame/button styling
- permissions.py: Permission checks
"""

from .review_notes_panel import ReviewNotesPanel
from .note_item import NoteItemWidget

__all__ = ['ReviewNotesPanel', 'NoteItemWidget']
