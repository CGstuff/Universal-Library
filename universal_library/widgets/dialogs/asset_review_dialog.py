"""
AssetReviewDialog - Main dialog for asset review system

Orchestrates:
- Screenshot list panel (left)
- Screenshot preview with annotations (center)
- Review notes panel (right)

Features:
- Upload screenshots for review
- Draw annotations on screenshots
- Add/manage review notes
- Save/load review data
"""

from pathlib import Path
from typing import Optional, List, Dict, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QSplitter,
    QPushButton, QLabel, QMessageBox, QFrame, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QScreen

from ..review.screenshot_list_panel import ScreenshotListPanel
from ..review.screenshot_preview_widget import ScreenshotPreviewWidget
from ..review.review_notes_panel import ReviewNotesPanel
from ...config import Config, REVIEW_CYCLE_TYPES
from ...services.review_database import get_review_database
from ...services.review_storage import get_review_storage
from ...services.review_state_manager import get_review_state_manager
from ...services.drawover_storage import get_drawover_storage


class AssetReviewDialog(QDialog):
    """
    Main asset review dialog.

    Shows:
    - Left: Screenshot thumbnails list
    - Center: Large screenshot preview with annotation canvas
    - Right: Review notes panel

    Signals:
        review_updated(): When review data changes (notes added, annotations saved)
    """

    review_updated = pyqtSignal()

    def __init__(
        self,
        asset_uuid: str,
        version_label: str,
        asset_name: str = '',
        asset_id: str = '',
        variant_name: str = 'Base',
        is_studio_mode: bool = False,
        current_user: str = '',
        current_user_role: str = 'artist',
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self._asset_uuid = asset_uuid
        self._version_label = version_label
        self._asset_name = asset_name or f"{version_label}"
        # New params for storage path generation
        self._asset_id = asset_id or asset_uuid  # Family ID (fallback to uuid for compatibility)
        self._variant_name = variant_name
        self._is_studio_mode = is_studio_mode
        self._current_user = current_user
        self._current_user_role = current_user_role

        # Services
        self._review_db = get_review_database()
        self._review_storage = get_review_storage()
        self._drawover_storage = get_drawover_storage()
        self._review_state_manager = get_review_state_manager()

        # State
        self._current_screenshot_id: Optional[int] = None
        self._has_unsaved_changes = False
        self._current_cycle: Optional[Dict] = None  # Active cycle for this asset

        self._setup_ui()
        self._connect_signals()
        self._load_data()
        self._load_cycle_info()

    def _setup_ui(self):
        """Build the dialog UI."""
        self.setWindowTitle(f"Asset Review: {self._asset_name}")

        # Fullscreen window with proper flags
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        # Size to 90% of screen
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            width = int(screen_rect.width() * 0.9)
            height = int(screen_rect.height() * 0.9)
            self.resize(width, height)
            # Center on screen
            x = screen_rect.x() + (screen_rect.width() - width) // 2
            y = screen_rect.y() + (screen_rect.height() - height) // 2
            self.move(x, y)
        else:
            self.resize(1400, 900)

        self.setMinimumSize(1200, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Cycle info header (shown when version belongs to a cycle)
        self._cycle_header = QFrame()
        self._cycle_header.setVisible(False)  # Hidden until we know we're in a cycle
        self._cycle_header.setStyleSheet("""
            QFrame {
                background: #1e2530;
                border-bottom: 1px solid #333;
            }
        """)
        cycle_header_layout = QHBoxLayout(self._cycle_header)
        cycle_header_layout.setContentsMargins(16, 10, 16, 10)

        # Cycle type badge
        self._cycle_type_badge = QLabel("Cycle")
        self._cycle_type_badge.setStyleSheet("""
            background: #2196F3;
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
        """)
        cycle_header_layout.addWidget(self._cycle_type_badge)

        # Version range label
        self._cycle_version_label = QLabel("v001 → v003")
        self._cycle_version_label.setStyleSheet("color: #aaa; font-size: 12px; margin-left: 8px;")
        cycle_header_layout.addWidget(self._cycle_version_label)

        # Current version indicator
        self._current_version_label = QLabel("(viewing v002)")
        self._current_version_label.setStyleSheet("color: #666; font-size: 11px; margin-left: 4px;")
        cycle_header_layout.addWidget(self._current_version_label)

        cycle_header_layout.addStretch()

        # Cycle state badge
        self._cycle_state_badge = QLabel("In Review")
        self._cycle_state_badge.setStyleSheet("""
            background: #333;
            color: #FF9800;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 11px;
        """)
        cycle_header_layout.addWidget(self._cycle_state_badge)

        layout.addWidget(self._cycle_header)

        # Main splitter
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)
        self._splitter.setStyleSheet("""
            QSplitter::handle {
                background: #333;
            }
            QSplitter::handle:hover {
                background: #444;
            }
        """)

        # Left panel: Screenshot list
        self._screenshot_list = ScreenshotListPanel()
        self._screenshot_list.setMinimumWidth(150)
        self._screenshot_list.setMaximumWidth(200)
        self._splitter.addWidget(self._screenshot_list)

        # Center panel: Screenshot preview
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self._preview = ScreenshotPreviewWidget()
        center_layout.addWidget(self._preview, 1)

        self._splitter.addWidget(center_widget)

        # Right panel: Notes
        self._notes_panel = ReviewNotesPanel(
            is_studio_mode=self._is_studio_mode,
            current_user=self._current_user,
            current_user_role=self._current_user_role
        )
        self._notes_panel.setMinimumWidth(250)
        self._notes_panel.setMaximumWidth(400)
        self._splitter.addWidget(self._notes_panel)

        # Set splitter sizes
        self._splitter.setSizes([180, 700, 300])

        layout.addWidget(self._splitter, 1)

        # Bottom bar
        bottom_bar = QFrame()
        bottom_bar.setStyleSheet("background: #252525; border-top: 1px solid #333;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(12, 8, 12, 8)

        # Status label
        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        bottom_layout.addWidget(self._status_label)

        bottom_layout.addStretch()

        # Resolve all button
        self._resolve_all_btn = QPushButton("Resolve All Notes")
        self._resolve_all_btn.setStyleSheet("""
            QPushButton {
                background: #2d2d2d;
                color: #8BC34A;
                border: 1px solid #4a6a4a;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #3a4a3a;
            }
        """)
        self._resolve_all_btn.clicked.connect(self._on_resolve_all)
        bottom_layout.addWidget(self._resolve_all_btn)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: #ccc;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background: #4a4a4a;
            }
        """)
        close_btn.clicked.connect(self._on_close)
        bottom_layout.addWidget(close_btn)

        layout.addWidget(bottom_bar)

    def _connect_signals(self):
        """Connect widget signals."""
        # Screenshot list signals
        self._screenshot_list.screenshot_selected.connect(self._on_screenshot_selected)
        self._screenshot_list.screenshot_added.connect(self._on_screenshot_added)
        self._screenshot_list.screenshot_renamed.connect(self._on_screenshot_renamed)
        self._screenshot_list.screenshot_deleted.connect(self._on_screenshot_deleted)

        # Preview signals
        self._preview.annotation_changed.connect(self._on_annotation_changed)

        # Notes panel signals
        self._notes_panel.note_clicked.connect(self._on_note_clicked)
        self._notes_panel.note_added.connect(self._on_note_added)
        self._notes_panel.note_deleted.connect(self._on_note_deleted)
        self._notes_panel.note_restored.connect(self._on_note_restored)
        self._notes_panel.note_edited.connect(self._on_note_edited)

        # New 3-state signals
        self._notes_panel.note_addressed.connect(self._on_note_addressed)
        self._notes_panel.note_approved.connect(self._on_note_approved)
        self._notes_panel.note_reopened.connect(self._on_note_reopened)

    def _load_data(self):
        """Load existing review data."""
        # Load screenshots
        screenshots = self._review_db.get_screenshots(self._asset_uuid, self._version_label)
        self._screenshot_list.set_screenshots(screenshots)

        # Load notes
        self._load_notes()

        # Update status
        self._update_status()
        self._update_notes_can_add()

    def _load_notes(self):
        """
        Load and display notes.

        If the version belongs to a cycle, load ALL notes from the cycle
        (grouped by version). Otherwise, load only notes for this version.
        """
        include_deleted = self._is_studio_mode and self._current_user_role in ['admin', 'supervisor', 'lead']

        # Check if we're in a cycle - if so, load ALL cycle notes
        if self._current_cycle:
            cycle_id = self._current_cycle.get('id')
            notes = self._review_db.get_cycle_notes(
                cycle_id,
                include_deleted=include_deleted
            )
            # Pass notes with version grouping info to the panel
            self._notes_panel.set_notes(
                notes,
                current_version=self._version_label,
                show_version_groups=True
            )
        else:
            # No cycle - just load notes for this version
            notes = self._review_db.get_notes_for_version(
                self._asset_uuid,
                self._version_label,
                include_deleted=include_deleted
            )
            self._notes_panel.set_notes(notes)

    def _update_status(self):
        """Update status bar."""
        screenshots = self._review_db.get_screenshots(self._asset_uuid, self._version_label)
        note_count = self._notes_panel.get_note_count()

        status = f"{len(screenshots)} screenshots, {note_count} notes"
        if self._has_unsaved_changes:
            status += " (unsaved changes)"
        self._status_label.setText(status)

    def _load_cycle_info(self):
        """Load and display cycle information if version belongs to a cycle."""
        # Check if version belongs to a cycle
        cycle = self._review_state_manager.get_cycle_for_version(
            self._asset_uuid, self._version_label
        )

        if not cycle:
            # No cycle - hide the header
            self._cycle_header.setVisible(False)
            self._current_cycle = None
            return

        self._current_cycle = cycle
        self._cycle_header.setVisible(True)

        # Update cycle type badge
        cycle_type = cycle.get('cycle_type', 'general')
        cycle_info = REVIEW_CYCLE_TYPES.get(cycle_type, {})
        cycle_label = cycle_info.get('label', cycle_type.title())
        cycle_color = cycle_info.get('color', '#607D8B')

        self._cycle_type_badge.setText(cycle_label)
        self._cycle_type_badge.setStyleSheet(f"""
            background: {cycle_color};
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
        """)

        # Update version range label
        start_version = cycle.get('start_version', '?')
        end_version = cycle.get('end_version')
        if end_version:
            version_text = f"{start_version} → {end_version}"
        else:
            version_text = f"{start_version} → ongoing"
        self._cycle_version_label.setText(version_text)

        # Update current version indicator
        self._current_version_label.setText(f"(viewing {self._version_label})")

        # Update cycle state badge
        review_state = cycle.get('review_state', 'needs_review')
        state_colors = {
            'needs_review': '#FF9800',
            'in_review': '#FF9800',
            'in_progress': '#2196F3',
            'approved': '#4CAF50',
            'final': '#9C27B0'
        }
        state_labels = {
            'needs_review': 'Needs Review',
            'in_review': 'In Review',
            'in_progress': 'In Progress',
            'approved': 'Approved',
            'final': 'Final'
        }
        state_color = state_colors.get(review_state, '#666')
        state_label = state_labels.get(review_state, review_state)

        self._cycle_state_badge.setText(state_label)
        self._cycle_state_badge.setStyleSheet(f"""
            background: #333;
            color: {state_color};
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        """)

    # ==================== Screenshot Handlers ====================

    def _on_screenshot_selected(self, index: int, data: Dict):
        """Handle screenshot selection."""
        # Save current annotations before switching
        self._save_current_annotations()

        self._current_screenshot_id = data.get('id')
        display_name = data.get('display_name', '')

        # Load screenshot
        file_path = data.get('file_path', '')
        self._preview.load_screenshot(file_path, display_name)

        # Load annotations for this screenshot
        self._load_annotations_for_screenshot()

        # Update notes panel context with screenshot name
        self._notes_panel.set_current_screenshot(self._current_screenshot_id, display_name)

    def _on_screenshot_added(self, file_path: str):
        """Handle new screenshot upload."""
        # Copy to storage
        result = self._review_storage.save_screenshot(
            self._asset_id,
            self._asset_name,
            self._variant_name,
            self._version_label,
            Path(file_path),
            display_name=Path(file_path).stem,
            order=len(self._screenshot_list._screenshots)
        )

        if result:
            # Add to database
            screenshot_id = self._review_db.add_screenshot(
                self._asset_uuid,
                self._version_label,
                result['filename'],
                result['file_path'],
                result['display_name'],
                self._current_user
            )

            if screenshot_id:
                result['id'] = screenshot_id
                self._screenshot_list.add_screenshot(result)
                self._update_status()
                self.review_updated.emit()

    def _on_screenshot_renamed(self, index: int, new_name: str):
        """Handle screenshot rename."""
        data = self._screenshot_list._screenshots[index]
        screenshot_id = data.get('id')

        if screenshot_id:
            # Update in database
            self._review_db.update_screenshot(screenshot_id, display_name=new_name)

            # Update in storage (rename file)
            old_filename = data.get('filename', '')
            new_filename = self._review_storage.rename_screenshot(
                self._asset_id,
                self._asset_name,
                self._variant_name,
                self._version_label,
                old_filename,
                new_name
            )

            if new_filename:
                # Update local data
                data['display_name'] = new_name
                data['filename'] = new_filename
                data['file_path'] = str(
                    self._review_storage.get_screenshot_path(
                        self._asset_id, self._asset_name, self._variant_name,
                        self._version_label, new_filename
                    )
                )
                self._screenshot_list.update_screenshot(index, data)
                self.review_updated.emit()

    def _on_screenshot_deleted(self, index: int):
        """Handle screenshot deletion."""
        data = self._screenshot_list._screenshots[index]
        screenshot_id = data.get('id')
        filename = data.get('filename', '')

        if screenshot_id:
            # Delete from database
            self._review_db.delete_screenshot(screenshot_id)

            # Delete from storage
            self._review_storage.delete_screenshot(
                self._asset_id,
                self._asset_name,
                self._variant_name,
                self._version_label,
                filename
            )

            # Update UI
            self._screenshot_list.remove_screenshot(index)
            self._update_status()
            self._load_notes()  # Reload notes (some may have been orphaned)
            self.review_updated.emit()

    # ==================== Annotation Handlers ====================

    def _on_annotation_changed(self):
        """Handle annotation modification."""
        self._has_unsaved_changes = True
        self._update_status()

    def _save_current_annotations(self):
        """Save annotations for current screenshot."""
        if not self._current_screenshot_id:
            return

        strokes = self._preview.get_strokes()
        canvas_size = self._preview.get_canvas_size()

        if strokes:
            self._drawover_storage.save_drawover(
                self._asset_id,
                self._asset_name,
                self._variant_name,
                self._version_label,
                self._current_screenshot_id,
                strokes,
                self._current_user,
                canvas_size
            )

            # Update metadata in DB
            authors = set(s.get('author', '') for s in strokes if s.get('author'))
            self._review_db.update_drawover_metadata(
                self._asset_uuid,
                self._version_label,
                self._current_screenshot_id,
                len(strokes),
                ', '.join(authors)
            )
        else:
            # Clear any existing drawover
            self._drawover_storage.delete_drawover(
                self._asset_id,
                self._asset_name,
                self._variant_name,
                self._version_label,
                self._current_screenshot_id
            )
            self._review_db.delete_drawover_metadata(
                self._asset_uuid,
                self._version_label,
                self._current_screenshot_id
            )

        self._has_unsaved_changes = False
        self._update_status()

    def _load_annotations_for_screenshot(self):
        """Load annotations for the current screenshot."""
        if not self._current_screenshot_id:
            return

        data = self._drawover_storage.load_drawover(
            self._asset_id,
            self._asset_name,
            self._variant_name,
            self._version_label,
            self._current_screenshot_id
        )

        if data and data.get('strokes'):
            canvas_size = tuple(data.get('canvas_size', [1920, 1080]))
            self._preview.set_strokes(data['strokes'], canvas_size)
        else:
            self._preview.clear_annotations()

    # ==================== Notes Handlers ====================

    def _on_note_clicked(self, screenshot_id):
        """Handle note click - navigate to screenshot."""
        if screenshot_id:
            # Find screenshot index
            for i, data in enumerate(self._screenshot_list._screenshots):
                if data.get('id') == screenshot_id:
                    self._screenshot_list.select_screenshot(i)
                    break

    def _on_note_added(self, screenshot_id, text: str):
        """Handle new note creation."""
        note_id = self._review_db.add_note(
            self._asset_uuid,
            self._version_label,
            text,
            screenshot_id=screenshot_id,
            author=self._current_user,
            author_role=self._current_user_role
        )

        if note_id:
            # Trigger state transition (needs_review -> in_review if elevated role)
            new_state, message = self._review_state_manager.on_comment_added(
                self._asset_uuid,
                self._version_label,
                self._current_user_role
            )

            self._load_notes()
            self._update_status()
            self.review_updated.emit()

    def _on_note_deleted(self, note_id: int):
        """Handle note deletion."""
        self._review_db.soft_delete_note(
            note_id,
            self._current_user,
            self._current_user_role
        )

        # Deleting a note may approve all remaining -> check for state transition
        # (if all remaining notes are now approved, asset moves to approved state)
        new_state, message = self._review_state_manager.on_note_approved(
            self._asset_uuid,
            self._version_label
        )

        self._load_notes()
        self._update_status()
        self.review_updated.emit()

    def _on_note_restored(self, note_id: int):
        """Handle note restoration."""
        self._review_db.restore_note(
            note_id,
            self._current_user,
            self._current_user_role
        )

        # Restoring a note reopens it - check for state transition
        # If restoring on an approved asset, it should go back to in_review
        new_state, message = self._review_state_manager.on_note_reopened(
            self._asset_uuid,
            self._version_label,
            self._current_user_role
        )

        self._load_notes()
        self._update_status()
        self.review_updated.emit()

    def _on_note_edited(self, note_id: int, new_text: str):
        """Handle note edit."""
        self._review_db.update_note(
            note_id,
            new_text,
            self._current_user,
            self._current_user_role
        )
        self._load_notes()
        self.review_updated.emit()

    def _on_resolve_all(self):
        """
        Bulk action for notes based on user role.

        - Artists: Mark all 'open' notes as 'addressed' (I fixed these)
        - Leads: Approve all 'addressed' notes
        """
        notes = self._review_db.get_notes_for_version(
            self._asset_uuid,
            self._version_label,
            include_deleted=False
        )

        is_elevated = self._current_user_role in Config.ELEVATED_ROLES
        action_count = 0

        if is_elevated:
            # Lead: approve all addressed notes
            for note in notes:
                if note.get('note_status') == 'addressed':
                    self._review_db.approve_note(
                        note['id'],
                        self._current_user,
                        self._current_user_role
                    )
                    action_count += 1
            action_text = "approved"
        else:
            # Artist: address all open notes
            for note in notes:
                if note.get('note_status') == 'open':
                    self._review_db.mark_note_addressed(
                        note['id'],
                        self._current_user,
                        self._current_user_role
                    )
                    action_count += 1
            action_text = "addressed"

        if action_count > 0:
            # Check for state transitions
            if is_elevated:
                self._review_state_manager.on_note_approved(
                    self._asset_uuid,
                    self._version_label
                )
            else:
                self._review_state_manager.on_note_addressed(
                    self._asset_uuid,
                    self._version_label
                )

            self._load_notes()
            self.review_updated.emit()
            QMessageBox.information(
                self,
                "Notes Updated",
                f"{action_count} note(s) {action_text}."
            )

    def _update_notes_can_add(self):
        """Update whether notes can be added based on review state."""
        # Notes can only be added if asset is in review workflow
        can_add = self._review_state_manager.can_add_comments(
            self._asset_uuid,
            self._version_label
        )
        self._notes_panel.set_can_add_notes(can_add)

    # ==================== 3-State Note Handlers ====================

    def _on_note_addressed(self, note_id: int):
        """Handle artist marking note as addressed ('I fixed it')."""
        self._review_db.mark_note_addressed(
            note_id,
            self._current_user,
            self._current_user_role
        )

        # Trigger state transition (in_review -> in_progress)
        new_state, message = self._review_state_manager.on_note_addressed(
            self._asset_uuid,
            self._version_label
        )

        self._load_notes()
        self._update_status()
        self.review_updated.emit()

    def _on_note_approved(self, note_id: int):
        """Handle lead approving a note."""
        self._review_db.approve_note(
            note_id,
            self._current_user,
            self._current_user_role
        )

        # Trigger state transition (in_progress -> approved if all notes approved)
        new_state, message = self._review_state_manager.on_note_approved(
            self._asset_uuid,
            self._version_label
        )

        self._load_notes()
        self._update_status()
        self.review_updated.emit()

    def _on_note_reopened(self, note_id: int):
        """Handle note being reopened to 'open' state."""
        self._review_db.reopen_note(
            note_id,
            self._current_user,
            self._current_user_role
        )

        # Trigger state transition (approved -> in_review if lead reopens)
        new_state, message = self._review_state_manager.on_note_reopened(
            self._asset_uuid,
            self._version_label,
            self._current_user_role
        )

        self._load_notes()
        self._update_status()
        self.review_updated.emit()

    # ==================== Dialog Handlers ====================

    def _on_close(self):
        """Handle close button click."""
        self._save_current_annotations()
        self.accept()

    def closeEvent(self, event):
        """Handle window close."""
        self._save_current_annotations()
        super().closeEvent(event)


__all__ = ['AssetReviewDialog']
