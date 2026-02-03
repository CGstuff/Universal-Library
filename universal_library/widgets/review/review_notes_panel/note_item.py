"""
NoteItemWidget - Single note item in the notes panel.
"""

import os
from datetime import datetime
from typing import Dict, Optional

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QSizePolicy, QWidget
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QIcon

from ....config import Config
from .styling import (
    get_icon_path, apply_frame_style, create_icon_button, get_role_color
)
from .permissions import is_elevated_role, can_edit, can_delete, can_restore


class NoteItemWidget(QFrame):
    """
    Single note item in the notes panel with 3-state workflow.

    States:
    - open: Awaiting artist (orange)
    - addressed: Artist fixed, awaiting lead (cyan)
    - approved: Lead approved (green)

    Signals:
        clicked: screenshot_id
        addressed_clicked: note_id - artist marks "I fixed it"
        approved_clicked: note_id - lead approves
        reopened_clicked: note_id - reopen to 'open' state
        delete_requested: note_id
        restore_requested: note_id
        edit_saved: note_id, new_text
        resolve_toggled: note_id, new_resolved (legacy)
    """

    clicked = pyqtSignal(int)
    addressed_clicked = pyqtSignal(int)
    approved_clicked = pyqtSignal(int)
    reopened_clicked = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    restore_requested = pyqtSignal(int)
    edit_saved = pyqtSignal(int, str)
    resolve_toggled = pyqtSignal(int, bool)  # Legacy

    def __init__(
        self,
        note_data: Dict,
        is_studio_mode: bool = False,
        current_user: str = '',
        current_user_role: str = 'artist',
        marker_index: int = 0,
        parent=None
    ):
        super().__init__(parent)
        self._note_data = note_data
        self._is_studio_mode = is_studio_mode
        self._current_user = current_user
        self._current_user_role = current_user_role
        self._marker_index = marker_index
        self._editing = False
        self._is_deleted = note_data.get('deleted', 0) == 1

        # Get note status
        self._note_status = note_data.get('note_status', 'open')
        if self._note_status is None or self._note_status == '':
            if note_data.get('resolved', 0) == 1:
                self._note_status = 'approved'
            else:
                self._note_status = 'open'

        self._setup_ui()

    def _setup_ui(self):
        """Build the note item UI."""
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Header row
        header = QHBoxLayout()
        header.setSpacing(8)

        author = self._note_data.get('author', '')
        author_role = self._note_data.get('author_role', 'artist')

        # Timestamp
        self._add_timestamp(header)

        # Marker badge
        self._add_marker_badge(header)

        # Status badge
        if not self._is_deleted:
            self._add_status_badge(header)

        # Role badge (Studio Mode only)
        if self._is_studio_mode and author_role and is_elevated_role(author_role):
            self._add_role_badge(header, author_role)

        # Author name (Studio Mode only)
        if self._is_studio_mode and author:
            author_label = QLabel(author)
            author_label.setStyleSheet("color: #888; font-size: 11px;")
            header.addWidget(author_label)

        header.addStretch()

        # Action buttons
        self._add_action_buttons(header, author)

        layout.addLayout(header)

        # Note text
        self._add_note_text(layout)

        # Status change info
        self._add_status_info(layout)

        # Deleted info
        self._add_deleted_info(layout)

        # Edit container
        self._add_edit_container(layout, author)

        # Apply frame styling
        apply_frame_style(self, self._note_status, self._is_deleted)

    def _add_timestamp(self, header: QHBoxLayout):
        """Add timestamp to header."""
        created_date = self._note_data.get('created_date', '')
        if created_date:
            try:
                dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                time_str = dt.strftime('%b %d, %H:%M')
            except Exception:
                time_str = ""
        else:
            time_str = ""

        if time_str:
            time_label = QLabel(time_str)
            time_label.setStyleSheet("color: #666; font-size: 10px;")
            header.addWidget(time_label)

    def _add_marker_badge(self, header: QHBoxLayout):
        """Add marker index badge to header."""
        if self._marker_index > 0:
            marker_badge = QLabel(str(self._marker_index))
            marker_badge.setFixedSize(20, 20)
            marker_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            marker_badge.setStyleSheet("""
                QLabel {
                    background-color: #FF9800;
                    color: white;
                    font-size: 11px;
                    font-weight: bold;
                    border-radius: 10px;
                }
            """)
            marker_badge.setToolTip(f"Note {self._marker_index}")
            header.addWidget(marker_badge)

    def _add_status_badge(self, header: QHBoxLayout):
        """Add note status badge to header."""
        status_config = Config.NOTE_STATUSES.get(self._note_status, {})
        status_label = status_config.get('label', self._note_status)
        status_color = status_config.get('color', '#888')

        status_badge = QLabel(status_label.upper())
        status_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {status_color};
                color: white;
                font-size: 9px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 0px;
            }}
        """)
        status_badge.setToolTip(f"Status: {status_label}")
        header.addWidget(status_badge)

    def _add_role_badge(self, header: QHBoxLayout, author_role: str):
        """Add author role badge to header."""
        role_label = author_role.title()
        role_color = get_role_color(author_role)
        role_badge = QLabel(role_label.upper())
        role_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {role_color};
                color: white;
                font-size: 9px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 0px;
            }}
        """)
        header.addWidget(role_badge)

    def _add_note_text(self, layout: QVBoxLayout):
        """Add note text label."""
        note_text = self._note_data.get('note', '')
        self._note_label = QLabel(note_text)
        self._note_label.setWordWrap(True)
        self._note_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._note_label.setMinimumWidth(50)

        if self._is_deleted:
            self._note_label.setStyleSheet("""
                QLabel { color: #555; font-size: 12px; padding: 4px 0; text-decoration: line-through; }
            """)
        else:
            self._note_label.setStyleSheet("""
                QLabel { color: #e0e0e0; font-size: 12px; padding: 4px 0; }
            """)
        layout.addWidget(self._note_label)

    def _add_status_info(self, layout: QVBoxLayout):
        """Add status change info (addressed by, approved by)."""
        if self._is_deleted:
            return
        if self._note_status not in ('addressed', 'approved'):
            return

        info_parts = []
        if self._note_status == 'addressed':
            addressed_by = self._note_data.get('addressed_by', '')
            if addressed_by:
                info_parts.append(f"Addressed by {addressed_by}")
        elif self._note_status == 'approved':
            approved_by = self._note_data.get('approved_by', '')
            if approved_by:
                info_parts.append(f"Approved by {approved_by}")

        if info_parts:
            status_info = QLabel(" | ".join(info_parts))
            status_info.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
            layout.addWidget(status_info)

    def _add_deleted_info(self, layout: QVBoxLayout):
        """Add deleted note info."""
        if not self._is_deleted:
            return

        deleted_by = self._note_data.get('deleted_by', 'Unknown')
        deleted_at = self._note_data.get('deleted_at', '')
        if deleted_at:
            try:
                dt = datetime.fromisoformat(deleted_at.replace('Z', '+00:00'))
                deleted_at = dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                pass

        deleted_info = QLabel(f"Deleted by {deleted_by}" + (f" on {deleted_at}" if deleted_at else ""))
        deleted_info.setStyleSheet("color: #555; font-size: 10px; font-style: italic;")
        layout.addWidget(deleted_info)

    def _add_edit_container(self, layout: QVBoxLayout, author: str):
        """Add edit container (hidden by default)."""
        if self._is_deleted:
            self._edit_container = None
            self._edit_input = None
            return

        self._edit_container = QWidget()
        edit_layout = QVBoxLayout(self._edit_container)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.setSpacing(4)

        self._edit_input = QTextEdit()
        self._edit_input.setFixedHeight(60)
        self._edit_input.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                border: 1px solid #3A8FB7;
                border-radius: 0px;
                padding: 6px 8px;
                color: #e0e0e0;
                font-size: 12px;
            }
        """)
        edit_layout.addWidget(self._edit_input)

        # Edit buttons row
        edit_btn_row = QHBoxLayout()
        edit_btn_row.setSpacing(4)
        edit_btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(24)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 0px;
                color: #aaa;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
        """)
        cancel_btn.clicked.connect(self._on_cancel_edit)
        edit_btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(24)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3A8FB7;
                border: none;
                border-radius: 0px;
                color: white;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #4A9FC7; }
        """)
        save_btn.clicked.connect(self._on_save_edit)
        edit_btn_row.addWidget(save_btn)

        edit_layout.addLayout(edit_btn_row)
        self._edit_container.hide()
        layout.addWidget(self._edit_container)

        # Double-click to edit
        if can_edit(self._note_data, self._is_studio_mode, self._current_user, self._current_user_role):
            self._note_label.mouseDoubleClickEvent = self._start_edit

    def _add_action_buttons(self, header: QHBoxLayout, author: str):
        """Add action buttons based on permissions and current state."""
        role = self._current_user_role.lower() if self._current_user_role else 'artist'
        is_admin = role == 'admin'
        is_lead = role in ('lead', 'supervisor', 'director')
        is_artist = role == 'artist'

        show_artist_buttons = is_admin or is_artist
        show_lead_buttons = is_admin or is_lead

        if not self._is_deleted:
            # OPEN notes
            if self._note_status == 'open':
                if show_artist_buttons:
                    fixed_btn = create_icon_button(
                        "checkmark", "utility", "I fixed this",
                        "#00BCD4", "#26C6DA", self._on_addressed
                    )
                    header.addWidget(fixed_btn)

                if show_lead_buttons:
                    approve_btn = create_icon_button(
                        "checkmark", "utility", "Approve",
                        "#4CAF50", "#66BB6A", self._on_approved
                    )
                    header.addWidget(approve_btn)

            # ADDRESSED notes
            if self._note_status == 'addressed':
                if show_artist_buttons:
                    undo_btn = create_icon_button(
                        "undo", "drawing", "Undo - mark as not fixed",
                        "#3a3a3a", "#4a4a4a", self._on_reopen
                    )
                    header.addWidget(undo_btn)

                if show_lead_buttons:
                    approve_btn = create_icon_button(
                        "checkmark", "utility", "Approve this fix",
                        "#4CAF50", "#66BB6A", self._on_approved
                    )
                    header.addWidget(approve_btn)

                    reject_btn = create_icon_button(
                        "cancel", "utility", "Reject - needs more work",
                        "#F44336", "#EF5350", self._on_reopen
                    )
                    header.addWidget(reject_btn)

            # APPROVED notes
            if self._note_status == 'approved':
                if show_lead_buttons:
                    reopen_btn = create_icon_button(
                        "undo", "drawing", "Reopen this note",
                        "#3a3a3a", "#4a4a4a", self._on_reopen
                    )
                    header.addWidget(reopen_btn)

            # Delete button
            if can_delete(self._note_data, self._is_studio_mode, self._current_user, self._current_user_role):
                self._add_delete_button(header)

        # Restore button (deleted notes only)
        if self._is_deleted:
            if can_restore(self._is_studio_mode, self._current_user_role):
                self._add_restore_button(header)

    def _add_delete_button(self, header: QHBoxLayout):
        """Add delete button."""
        delete_btn = QPushButton()
        delete_btn.setFixedSize(26, 26)
        delete_btn.setToolTip("Delete note")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(self._on_delete)

        delete_icon_path = get_icon_path("delete")
        if os.path.exists(delete_icon_path):
            delete_btn.setIcon(QIcon(delete_icon_path))
            delete_btn.setIconSize(QSize(16, 16))
        else:
            delete_btn.setText("\u00d7")

        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a; border: 1px solid #555;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #4a3535; border-color: #aa5555; }
        """)
        header.addWidget(delete_btn)

    def _add_restore_button(self, header: QHBoxLayout):
        """Add restore button for deleted notes."""
        restore_btn = QPushButton("Restore")
        restore_btn.setFixedHeight(24)
        restore_btn.setToolTip("Restore this deleted note")
        restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restore_btn.clicked.connect(self._on_restore)
        restore_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a4a3a; border: 1px solid #4a6a4a;
                border-radius: 3px; color: #8BC34A; font-size: 11px; padding: 2px 12px;
            }
            QPushButton:hover { background-color: #4a5a4a; }
        """)
        header.addWidget(restore_btn)

    # ==================== Event Handlers ====================

    def _on_addressed(self):
        """Artist marks note as addressed."""
        self.addressed_clicked.emit(self._note_data.get('id', -1))

    def _on_approved(self):
        """Lead approves the note."""
        self.approved_clicked.emit(self._note_data.get('id', -1))

    def _on_reopen(self):
        """Reopen note to 'open' state."""
        self.reopened_clicked.emit(self._note_data.get('id', -1))

    def _on_delete(self):
        self.delete_requested.emit(self._note_data.get('id', -1))

    def _on_restore(self):
        self.restore_requested.emit(self._note_data.get('id', -1))

    def _start_edit(self, event):
        if self._edit_container is None:
            return
        self._editing = True
        self._edit_input.setPlainText(self._note_data.get('note', ''))
        self._note_label.hide()
        self._edit_container.show()
        self._edit_input.setFocus()
        cursor = self._edit_input.textCursor()
        cursor.select(cursor.SelectionType.Document)
        self._edit_input.setTextCursor(cursor)

    def _on_save_edit(self):
        if self._edit_container is None:
            return
        new_text = self._edit_input.toPlainText().strip()
        if new_text and new_text != self._note_data.get('note', ''):
            self.edit_saved.emit(self._note_data.get('id', -1), new_text)

        self._editing = False
        self._edit_container.hide()
        self._note_label.show()

    def _on_cancel_edit(self):
        if self._edit_container is None:
            return
        self._editing = False
        self._edit_container.hide()
        self._note_label.show()

    # ==================== Public API ====================

    def get_note_id(self) -> int:
        return self._note_data.get('id', -1)

    def get_screenshot_id(self) -> Optional[int]:
        return self._note_data.get('screenshot_id')

    def is_deleted(self) -> bool:
        return self._is_deleted

    def get_note_status(self) -> str:
        return self._note_status


__all__ = ['NoteItemWidget']
