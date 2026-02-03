"""
ReviewNotesPanel - Panel for displaying and managing review notes.

Features:
- Note list with NoteItemWidget items (3-state: open/addressed/approved)
- Add note input (blocked until asset submitted for review)
- Show/hide deleted notes toggle
- Note count display
- Permission-based features
"""

from typing import Optional, List, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QCheckBox, QTextEdit
)
from PyQt6.QtCore import pyqtSignal, Qt

from .note_item import NoteItemWidget
from .builders import build_flat_notes_list, build_version_grouped_notes


class ReviewNotesPanel(QWidget):
    """
    Panel for displaying and managing review notes with 3-state workflow.

    Signals:
        note_clicked(int): screenshot_id
        note_added(int, str): screenshot_id (or None for general), text
        note_addressed(int): note_id - artist marked as fixed
        note_approved(int): note_id - lead approved
        note_reopened(int): note_id - reopened to 'open'
        note_deleted(int): note_id
        note_restored(int): note_id
        note_edited(int, str): note_id, new_text
    """

    note_clicked = pyqtSignal(object)
    note_added = pyqtSignal(object, str)
    note_addressed = pyqtSignal(int)
    note_approved = pyqtSignal(int)
    note_reopened = pyqtSignal(int)
    note_deleted = pyqtSignal(int)
    note_restored = pyqtSignal(int)
    note_edited = pyqtSignal(int, str)
    note_resolved = pyqtSignal(int, bool)  # Legacy

    def __init__(
        self,
        is_studio_mode: bool = False,
        current_user: str = '',
        current_user_role: str = 'artist',
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self._is_studio_mode = is_studio_mode
        self._current_user = current_user
        self._current_user_role = current_user_role
        self._current_screenshot_id: Optional[int] = None
        self._current_screenshot_name: str = ""
        self._notes: List[Dict] = []
        self._note_widgets: List[NoteItemWidget] = []
        self._can_add_notes = False
        self._current_version: Optional[str] = None
        self._show_version_groups: bool = False

        self._setup_ui()

    def _setup_ui(self):
        """Build the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = self._create_header()
        layout.addWidget(header)

        # Notes scroll area
        scroll = self._create_scroll_area()
        layout.addWidget(scroll, 1)

        # Add note section
        self._add_section = self._create_add_section()
        layout.addWidget(self._add_section)

        self._update_add_section_state()

    def _create_header(self) -> QWidget:
        """Create header widget."""
        header = QWidget()
        header.setStyleSheet("background: #252525;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(4)

        # Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title = QLabel("Notes")
        title.setStyleSheet("color: #e0e0e0; font-size: 13px; font-weight: bold;")
        title_row.addWidget(title)

        self._count_label = QLabel("(0)")
        self._count_label.setStyleSheet("color: #888; font-size: 12px;")
        title_row.addWidget(self._count_label)

        title_row.addStretch()

        # Show deleted checkbox
        if self._is_studio_mode and self._current_user_role in ['admin', 'supervisor', 'lead']:
            self._show_deleted_cb = QCheckBox("Show deleted")
            self._show_deleted_cb.setStyleSheet("color: #888; font-size: 11px;")
            self._show_deleted_cb.toggled.connect(self._on_show_deleted_toggled)
            title_row.addWidget(self._show_deleted_cb)
        else:
            self._show_deleted_cb = None

        header_layout.addLayout(title_row)

        # Screenshot name label
        self._screenshot_label = QLabel("Select a screenshot")
        self._screenshot_label.setStyleSheet("color: #FF9800; font-size: 11px;")
        header_layout.addWidget(self._screenshot_label)

        return header

    def _create_scroll_area(self) -> QScrollArea:
        """Create scroll area for notes."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: #1e1e1e; }
            QScrollBar:vertical { background: #252525; width: 8px; margin: 0; }
            QScrollBar::handle:vertical { background: #3a3a3a; min-height: 20px; border-radius: 4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._notes_container = QWidget()
        self._notes_layout = QVBoxLayout(self._notes_container)
        self._notes_layout.setContentsMargins(8, 8, 8, 8)
        self._notes_layout.setSpacing(8)
        self._notes_layout.addStretch()

        scroll.setWidget(self._notes_container)
        return scroll

    def _create_add_section(self) -> QWidget:
        """Create add note section."""
        add_section = QWidget()
        add_section.setStyleSheet("background: #252525;")
        add_layout = QHBoxLayout(add_section)
        add_layout.setContentsMargins(8, 8, 8, 8)
        add_layout.setSpacing(8)

        self._note_input = QTextEdit()
        self._note_input.setPlaceholderText("Add note for current screenshot...")
        self._note_input.setFixedHeight(60)
        self._note_input.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 0px;
                padding: 8px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QTextEdit:focus { border-color: #FF5722; }
            QTextEdit:disabled { background-color: #1e1e1e; color: #555; }
        """)
        add_layout.addWidget(self._note_input)

        self._add_btn = QPushButton("+")
        self._add_btn.setFixedSize(36, 60)
        self._add_btn.setToolTip("Add note")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF5722;
                border: none;
                border-radius: 0px;
                color: white;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #FF7043; }
            QPushButton:disabled { background-color: #3a3a3a; color: #555; }
        """)
        self._add_btn.clicked.connect(self._on_add_note)
        add_layout.addWidget(self._add_btn)

        return add_section

    def _update_add_section_state(self):
        """Update the add note section based on whether notes can be added."""
        enabled = self._can_add_notes and self._current_screenshot_id is not None
        self._note_input.setEnabled(enabled)
        self._add_btn.setEnabled(enabled)

        if not self._can_add_notes:
            self._note_input.setPlaceholderText("Submit asset for review to add notes")
        elif self._current_screenshot_id is None:
            self._note_input.setPlaceholderText("Select a screenshot first...")
        else:
            self._note_input.setPlaceholderText(f"Add note for '{self._current_screenshot_name}'...")

    def _on_add_note(self):
        """Handle add note button."""
        if not self._can_add_notes:
            return

        text = self._note_input.toPlainText().strip()
        if text:
            self.note_added.emit(self._current_screenshot_id, text)
            self._note_input.clear()

    def _on_show_deleted_toggled(self, checked: bool):
        """Handle show deleted checkbox toggle."""
        self._rebuild_notes_list()

    def _rebuild_notes_list(self):
        """Rebuild the notes list UI."""
        # Clear existing widgets
        for widget in self._note_widgets:
            widget.deleteLater()
        self._note_widgets.clear()

        while self._notes_layout.count() > 0:
            item = self._notes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Filter notes
        show_deleted = self._show_deleted_cb and self._show_deleted_cb.isChecked()

        if self._show_version_groups:
            visible_notes = [
                n for n in self._notes
                if (show_deleted or n.get('deleted', 0) != 1)
            ]
        else:
            visible_notes = [
                n for n in self._notes
                if (show_deleted or n.get('deleted', 0) != 1)
                and n.get('screenshot_id') == self._current_screenshot_id
            ]

        visible_notes.sort(key=lambda n: n.get('created_date', ''))

        # Show empty state
        if not self._show_version_groups and self._current_screenshot_id is None:
            empty_label = QLabel("Select a screenshot to view notes")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #555; font-size: 12px; padding: 40px;")
            self._notes_layout.addWidget(empty_label)
            self._notes_layout.addStretch()
            self._count_label.setText("(0)")
            return

        if not visible_notes:
            if self._can_add_notes:
                empty_label = QLabel("No notes yet\nAdd one below!")
            else:
                empty_label = QLabel("No notes yet\nSubmit for review to add notes")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #666; font-size: 12px; padding: 30px;")
            self._notes_layout.addWidget(empty_label)
            self._notes_layout.addStretch()
            self._count_label.setText("(0)")
            return

        # Build marker indices
        active_notes = [n for n in visible_notes if n.get('deleted', 0) != 1]
        marker_indices = {n.get('id'): idx + 1 for idx, n in enumerate(active_notes)}

        if self._show_version_groups:
            self._note_widgets = build_version_grouped_notes(
                self._notes_layout,
                visible_notes,
                marker_indices,
                self._current_version,
                self._is_studio_mode,
                self._current_user,
                self._current_user_role,
                self._connect_note_widget
            )
        else:
            self._note_widgets = build_flat_notes_list(
                self._notes_layout,
                visible_notes,
                marker_indices,
                self._is_studio_mode,
                self._current_user,
                self._current_user_role,
                self._connect_note_widget
            )

        self._notes_layout.addStretch()

        # Update count
        active_count = len([n for n in self._notes if n.get('deleted', 0) != 1])
        self._count_label.setText(f"({active_count})")

    def _connect_note_widget(self, widget: NoteItemWidget):
        """Connect signals for a note widget."""
        widget.clicked.connect(self.note_clicked.emit)
        widget.addressed_clicked.connect(self.note_addressed.emit)
        widget.approved_clicked.connect(self.note_approved.emit)
        widget.reopened_clicked.connect(self.note_reopened.emit)
        widget.delete_requested.connect(self.note_deleted.emit)
        widget.restore_requested.connect(self.note_restored.emit)
        widget.edit_saved.connect(self.note_edited.emit)

    # ==================== PUBLIC API ====================

    def set_notes(
        self,
        notes: List[Dict],
        current_version: Optional[str] = None,
        show_version_groups: bool = False
    ):
        """Set the list of notes to display."""
        self._notes = notes
        self._current_version = current_version
        self._show_version_groups = show_version_groups
        self._rebuild_notes_list()

    def clear(self):
        """Clear all notes."""
        self._notes = []
        self._rebuild_notes_list()

    def set_current_screenshot(self, screenshot_id: Optional[int], screenshot_name: str = ""):
        """Set the current screenshot context and rebuild notes list."""
        self._current_screenshot_id = screenshot_id
        self._current_screenshot_name = screenshot_name

        if screenshot_id is not None and screenshot_name:
            self._screenshot_label.setText(f"\U0001F4F7 {screenshot_name}")
        else:
            self._screenshot_label.setText("Select a screenshot")

        self._rebuild_notes_list()
        self._update_add_section_state()

    def set_can_add_notes(self, can_add: bool):
        """Set whether notes can be added."""
        self._can_add_notes = can_add
        self._update_add_section_state()

    def set_studio_mode(self, enabled: bool, user: str = '', role: str = 'artist'):
        """Update studio mode settings."""
        self._is_studio_mode = enabled
        self._current_user = user
        self._current_user_role = role
        self._rebuild_notes_list()

    def get_note_count(self) -> int:
        """Get count of active (non-deleted) notes."""
        return len([n for n in self._notes if n.get('deleted', 0) != 1])


__all__ = ['ReviewNotesPanel']
