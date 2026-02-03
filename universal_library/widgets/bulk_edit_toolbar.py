"""
BulkEditToolbar - Toolbar for bulk operations on assets

Pattern: QWidget with centered horizontal layout
Features: Change status, archive/restore selected assets
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QComboBox
)
from PyQt6.QtCore import pyqtSignal, Qt

from ..config import Config
from ..events.event_bus import get_event_bus
from ..services.control_authority import get_control_authority


class BulkEditToolbar(QWidget):
    """
    Toolbar for bulk editing selected assets

    Features:
    - Selection count display
    - Status change dropdown
    - Archive/Restore buttons
    - Centered, minimalistic layout

    Layout:
        [stretch] [Selection Label] [stretch]
        [stretch] [Status v] [Archive] [Restore*] [stretch]
    """

    # Signals
    status_change_requested = pyqtSignal(str)  # new status value
    representation_change_requested = pyqtSignal(str)  # new representation type
    archive_selected_clicked = pyqtSignal()
    restore_selected_clicked = pyqtSignal()
    cold_storage_requested = pyqtSignal()  # move to cold storage
    restore_from_cold_requested = pyqtSignal()  # restore from cold storage
    publish_requested = pyqtSignal()  # publish/approve selected

    def __init__(self, parent=None):
        super().__init__(parent)

        self._event_bus = get_event_bus()
        self._control_authority = get_control_authority()
        self._in_archived_view = False

        self._create_widgets()
        self._create_layout()
        self._connect_signals()
        self._apply_styling()

        # Set initial state
        self._update_selection_count(0)

    def _create_widgets(self):
        """Create toolbar widgets"""

        # Selection count label
        self._selection_label = QLabel("No assets selected")
        self._selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Status dropdown
        self._status_combo = QComboBox()
        self._status_combo.setToolTip("Change status of selected assets")
        self._status_combo.setMinimumWidth(140)

        # Populate status dropdown from Config
        self._status_combo.addItem("Change Status...")  # Placeholder
        self._status_combo.model().item(0).setEnabled(False)
        for key, info in Config.LIFECYCLE_STATUSES.items():
            if key != 'none':  # Skip 'none' in bulk edit
                self._status_combo.addItem(info['label'], key)

        # Representation dropdown
        self._rep_combo = QComboBox()
        self._rep_combo.setToolTip("Change representation type of selected assets")
        self._rep_combo.setMinimumWidth(140)

        # Populate representation dropdown
        self._rep_combo.addItem("Set Representation...")  # Placeholder
        self._rep_combo.model().item(0).setEnabled(False)
        for rep_type, rep_info in Config.REPRESENTATION_TYPES.items():
            self._rep_combo.addItem(rep_info['label'], rep_type)

        # Archive button (status)
        self._archive_btn = QPushButton("Archive")
        self._archive_btn.setToolTip("Move selected assets to Archived status")

        # Restore button (status - hidden by default)
        self._restore_btn = QPushButton("Restore")
        self._restore_btn.setToolTip("Restore selected assets from archived")
        self._restore_btn.hide()

        # Cold Storage button
        self._cold_storage_btn = QPushButton("To Cold Storage")
        self._cold_storage_btn.setToolTip("Move selected assets to cold storage (file migration)")
        self._cold_storage_btn.setStyleSheet("""
            QPushButton {
                background-color: #1565C0;
                border-color: #1565C0;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)

        # Restore from Cold button (hidden by default)
        self._restore_cold_btn = QPushButton("From Cold")
        self._restore_cold_btn.setToolTip("Restore selected assets from cold storage")
        self._restore_cold_btn.hide()

        # Publish button
        self._publish_btn = QPushButton("Publish")
        self._publish_btn.setToolTip("Publish selected assets (approve + lock)")
        self._publish_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32;
                border-color: #2E7D32;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
        """)

    def _create_layout(self):
        """Create centered toolbar layout"""

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(8)

        # Row 1: Selection label (centered)
        label_row = QHBoxLayout()
        label_row.addStretch()
        label_row.addWidget(self._selection_label)
        label_row.addStretch()
        main_layout.addLayout(label_row)

        # Row 2: Action buttons (centered)
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(12)
        buttons_row.addStretch()
        buttons_row.addWidget(self._status_combo)
        buttons_row.addWidget(self._rep_combo)
        buttons_row.addWidget(self._archive_btn)
        buttons_row.addWidget(self._restore_btn)
        buttons_row.addWidget(self._cold_storage_btn)
        buttons_row.addWidget(self._restore_cold_btn)
        buttons_row.addWidget(self._publish_btn)
        buttons_row.addStretch()
        main_layout.addLayout(buttons_row)

    def _connect_signals(self):
        """Connect internal signals"""

        # Buttons
        self._archive_btn.clicked.connect(self.archive_selected_clicked.emit)
        self._restore_btn.clicked.connect(self.restore_selected_clicked.emit)
        self._cold_storage_btn.clicked.connect(self.cold_storage_requested.emit)
        self._restore_cold_btn.clicked.connect(self.restore_from_cold_requested.emit)
        self._publish_btn.clicked.connect(self.publish_requested.emit)

        # Status dropdown
        self._status_combo.currentIndexChanged.connect(self._on_status_selected)

        # Representation dropdown
        self._rep_combo.currentIndexChanged.connect(self._on_rep_selected)

        # Event bus - selection changes
        self._event_bus.assets_selected.connect(self._on_selection_changed)

        # Control authority - mode changes
        self._control_authority.mode_changed.connect(self._on_mode_changed)

    def _apply_styling(self):
        """Apply dark theme styling"""

        self.setStyleSheet("""
            BulkEditToolbar {
                background-color: #2a2a2a;
                border-bottom: 1px solid #444;
            }

            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: #e0e0e0;
            }

            QPushButton {
                border: 1px solid #555;
                border-radius: 0px;
                padding: 6px 16px;
                background-color: #3a3a3a;
                color: #e0e0e0;
                min-width: 80px;
            }

            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #666;
            }

            QPushButton:pressed {
                background-color: #2a2a2a;
            }

            QPushButton:disabled {
                background-color: #2a2a2a;
                border-color: #444;
                color: #666;
            }

            QComboBox {
                border: 1px solid #555;
                border-radius: 0px;
                padding: 6px 12px;
                background-color: #3a3a3a;
                color: #e0e0e0;
                min-width: 130px;
            }

            QComboBox:hover {
                background-color: #4a4a4a;
                border-color: #666;
            }

            QComboBox:disabled {
                background-color: #2a2a2a;
                border-color: #444;
                color: #666;
            }

            QComboBox::drop-down {
                border: none;
                width: 20px;
            }

            QComboBox QAbstractItemView {
                border: 1px solid #555;
                background-color: #2e2e2e;
                color: #e0e0e0;
                selection-background-color: #569eff;
            }
        """)

    def _on_status_selected(self, index: int):
        """Handle status selection from dropdown"""
        if index <= 0:  # Placeholder or invalid
            return

        status = self._status_combo.currentData()
        if status:
            self.status_change_requested.emit(status)

        # Reset dropdown to placeholder
        self._status_combo.blockSignals(True)
        self._status_combo.setCurrentIndex(0)
        self._status_combo.blockSignals(False)

    def _on_rep_selected(self, index: int):
        """Handle representation selection from dropdown"""
        if index <= 0:  # Placeholder or invalid
            return

        rep_type = self._rep_combo.currentData()
        if rep_type:
            self.representation_change_requested.emit(rep_type)

        # Reset dropdown to placeholder
        self._rep_combo.blockSignals(True)
        self._rep_combo.setCurrentIndex(0)
        self._rep_combo.blockSignals(False)

    def _on_selection_changed(self, selected_uuids: list):
        """Handle selection change from event bus"""
        self._update_selection_count(len(selected_uuids))

    def _update_selection_count(self, count: int):
        """Update selection count display and button states"""

        if count == 0:
            self._selection_label.setText("No assets selected")
        elif count == 1:
            self._selection_label.setText("1 asset selected")
        else:
            self._selection_label.setText(f"{count} assets selected")

        # Enable/disable controls based on selection AND pipeline mode
        has_selection = count > 0
        can_edit_status = self._control_authority.can_edit_status()
        
        # Status-related controls - disabled in Pipeline Mode
        status_enabled = has_selection and can_edit_status
        self._status_combo.setEnabled(status_enabled)
        self._archive_btn.setEnabled(status_enabled)
        self._restore_btn.setEnabled(status_enabled)
        self._publish_btn.setEnabled(status_enabled)
        
        # Update tooltips for disabled status controls
        if not can_edit_status:
            pipeline_tooltip = "Disabled in Pipeline Mode - use Pipeline Control to change status"
            self._status_combo.setToolTip(pipeline_tooltip)
            self._archive_btn.setToolTip(pipeline_tooltip)
            self._restore_btn.setToolTip(pipeline_tooltip)
            self._publish_btn.setToolTip(pipeline_tooltip)
        else:
            self._status_combo.setToolTip("Change status of selected assets")
            self._archive_btn.setToolTip("Move selected assets to Archived status")
            self._restore_btn.setToolTip("Restore selected assets from archived")
            self._publish_btn.setToolTip("Publish selected assets (approve + lock)")
        
        # Non-status controls - always enabled with selection
        self._rep_combo.setEnabled(has_selection)
        self._cold_storage_btn.setEnabled(has_selection)
        self._restore_cold_btn.setEnabled(has_selection)

    def _on_mode_changed(self, mode):
        """Handle operation mode change - refresh UI state."""
        # Re-apply current selection count to update enabled states
        selected_uuids = []
        try:
            # Try to get current selection count
            selected_uuids = self._event_bus.get_selected_uuids() if hasattr(self._event_bus, 'get_selected_uuids') else []
        except Exception:
            pass
        self._update_selection_count(len(selected_uuids))

    def set_archived_view_mode(self, in_archived: bool = False):
        """
        Configure toolbar for archived view.

        Args:
            in_archived: True if viewing archived assets
        """
        self._in_archived_view = in_archived

        if in_archived:
            self._restore_btn.show()
            self._archive_btn.hide()
        else:
            self._restore_btn.hide()
            self._archive_btn.show()

    def set_cold_storage_view_mode(self, in_cold_storage: bool = False):
        """
        Configure toolbar for cold storage view.

        Args:
            in_cold_storage: True if viewing cold storage assets
        """
        if in_cold_storage:
            self._restore_cold_btn.show()
            self._cold_storage_btn.hide()
        else:
            self._restore_cold_btn.hide()
            self._cold_storage_btn.show()


__all__ = ['BulkEditToolbar']
