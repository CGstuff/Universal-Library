"""
OperationModeTab - Settings tab for Standalone/Pipeline mode switching

This tab controls:
1. Operation Mode: Who controls asset status (Standalone vs Pipeline)

In Pipeline Mode, asset status changes are controlled by Pipeline Control,
and the status editing UI in Universal Library becomes read-only.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QRadioButton, QButtonGroup, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal

from ...services.control_authority import get_control_authority, OperationMode


class OperationModeTab(QWidget):
    """Settings tab for Operation Mode (Standalone/Pipeline)."""

    mode_changed = pyqtSignal(object)  # OperationMode

    def __init__(self, parent=None):
        super().__init__(parent)
        self._control_authority = get_control_authority()
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        # Sharp styling for the tab
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #3a3a3a;
                border-radius: 0px;
                margin-top: 12px;
                padding: 12px;
                padding-top: 24px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px;
                color: #e0e0e0;
            }
            QRadioButton {
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 0px;
            }
            QRadioButton::indicator:unchecked {
                background-color: #2a2a2a;
                border: 1px solid #555;
            }
            QRadioButton::indicator:checked {
                background-color: #3A8FB7;
                border: 1px solid #3A8FB7;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Operation Mode selection group
        mode_group = QGroupBox("Operation Mode")
        mode_layout = QVBoxLayout(mode_group)

        self._mode_btn_group = QButtonGroup(self)

        # Standalone mode option
        self._standalone_radio = QRadioButton("Standalone Mode")
        self._standalone_radio.setStyleSheet("font-weight: bold; font-size: 12px;")
        mode_layout.addWidget(self._standalone_radio)

        standalone_desc = QLabel(
            "Universal Library controls asset status internally. "
            "Full control over workflow. Permanent delete allowed."
        )
        standalone_desc.setWordWrap(True)
        standalone_desc.setStyleSheet("color: #888; margin-left: 22px; margin-bottom: 12px; font-size: 11px;")
        mode_layout.addWidget(standalone_desc)

        # Studio mode option (NEW)
        self._studio_radio = QRadioButton("Studio Mode")
        self._studio_radio.setStyleSheet("font-weight: bold; font-size: 12px;")
        mode_layout.addWidget(self._studio_radio)

        studio_desc = QLabel(
            "Multi-user environment. Assets are retired instead of deleted. "
            "Audit trail and role-based permissions."
        )
        studio_desc.setWordWrap(True)
        studio_desc.setStyleSheet("color: #888; margin-left: 22px; margin-bottom: 12px; font-size: 11px;")
        mode_layout.addWidget(studio_desc)

        # Studio mode info box
        self._studio_info = QFrame()
        self._studio_info.setStyleSheet("""
            QFrame {
                background-color: rgba(156, 39, 176, 0.1);
                border: 1px solid rgba(156, 39, 176, 0.3);
                border-radius: 0px;
                padding: 8px;
                margin-left: 22px;
                margin-top: 4px;
            }
        """)
        studio_info_layout = QVBoxLayout(self._studio_info)
        studio_info_layout.setContentsMargins(8, 8, 8, 8)

        studio_info_label = QLabel(
            "In Studio Mode:\n"
            "- Delete button becomes 'Retire Asset'\n"
            "- Retired assets move to .retired folder\n"
            "- Variants can still reference retired bases\n"
            "- Admins can restore retired assets"
        )
        studio_info_label.setStyleSheet("color: #9C27B0; font-size: 11px;")
        studio_info_layout.addWidget(studio_info_label)

        mode_layout.addWidget(self._studio_info)
        self._studio_info.setVisible(False)

        # Pipeline mode option
        self._pipeline_radio = QRadioButton("Pipeline Mode")
        self._pipeline_radio.setStyleSheet("font-weight: bold; font-size: 12px;")
        mode_layout.addWidget(self._pipeline_radio)

        pipeline_desc = QLabel(
            "Asset status is controlled externally by Pipeline Control. "
            "Status changes in Universal Library are read-only."
        )
        pipeline_desc.setWordWrap(True)
        pipeline_desc.setStyleSheet("color: #888; margin-left: 22px; font-size: 11px;")
        mode_layout.addWidget(pipeline_desc)

        # Pipeline mode info box
        self._pipeline_info = QFrame()
        self._pipeline_info.setStyleSheet("""
            QFrame {
                background-color: rgba(52, 152, 219, 0.1);
                border: 1px solid rgba(52, 152, 219, 0.3);
                border-radius: 0px;
                padding: 8px;
                margin-left: 22px;
                margin-top: 4px;
            }
        """)
        pipeline_info_layout = QVBoxLayout(self._pipeline_info)
        pipeline_info_layout.setContentsMargins(8, 8, 8, 8)
        
        pipeline_info_label = QLabel(
            "In Pipeline Mode:\n"
            "- Asset status badges are read-only\n"
            "- Use Pipeline Control to change asset status\n"
            "- Reviews and notes still work normally"
        )
        pipeline_info_label.setStyleSheet("color: #3498DB; font-size: 11px;")
        pipeline_info_layout.addWidget(pipeline_info_label)
        
        mode_layout.addWidget(self._pipeline_info)
        self._pipeline_info.setVisible(False)

        self._mode_btn_group.addButton(self._standalone_radio, 0)
        self._mode_btn_group.addButton(self._studio_radio, 1)
        self._mode_btn_group.addButton(self._pipeline_radio, 2)
        self._mode_btn_group.idToggled.connect(self._on_mode_changed)

        layout.addWidget(mode_group)

        # Current mode indicator
        self._mode_indicator = QFrame()
        self._mode_indicator.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 0px;
                padding: 12px;
            }
        """)
        indicator_layout = QHBoxLayout(self._mode_indicator)
        
        indicator_label = QLabel("Current Mode:")
        indicator_label.setStyleSheet("font-weight: bold;")
        indicator_layout.addWidget(indicator_label)
        
        self._current_mode_label = QLabel("")
        self._current_mode_label.setStyleSheet("font-size: 12px;")
        indicator_layout.addWidget(self._current_mode_label)
        indicator_layout.addStretch()
        
        layout.addWidget(self._mode_indicator)

        layout.addStretch()

    def _load_settings(self):
        """Load current settings from database."""
        operation_mode = self._control_authority.get_operation_mode()

        if operation_mode == OperationMode.PIPELINE:
            self._pipeline_radio.setChecked(True)
        elif operation_mode == OperationMode.STUDIO:
            self._studio_radio.setChecked(True)
        else:
            self._standalone_radio.setChecked(True)

        self._update_ui_visibility()

    def _update_ui_visibility(self):
        """Update visibility based on mode."""
        is_pipeline = self._pipeline_radio.isChecked()
        is_studio = self._studio_radio.isChecked()

        # Show info boxes only when respective mode is selected
        self._pipeline_info.setVisible(is_pipeline)
        self._studio_info.setVisible(is_studio)

        # Update current mode label
        if is_pipeline:
            self._current_mode_label.setText("Pipeline - Status controlled by Pipeline Control")
            self._current_mode_label.setStyleSheet("color: #3498DB; font-size: 12px;")
        elif is_studio:
            self._current_mode_label.setText("Studio - Multi-user mode with retire instead of delete")
            self._current_mode_label.setStyleSheet("color: #9C27B0; font-size: 12px;")
        else:
            self._current_mode_label.setText("Standalone - Universal Library controls asset status")
            self._current_mode_label.setStyleSheet("color: #4CAF50; font-size: 12px;")

    def _on_mode_changed(self, button_id: int, checked: bool):
        """Handle mode radio button change."""
        if checked:
            self._update_ui_visibility()

    def save_settings(self):
        """Save settings to database."""
        if self._pipeline_radio.isChecked():
            new_mode = OperationMode.PIPELINE
        elif self._studio_radio.isChecked():
            new_mode = OperationMode.STUDIO
        else:
            new_mode = OperationMode.STANDALONE

        self._control_authority.set_operation_mode(new_mode)

        # Emit signal for other components to update
        self.mode_changed.emit(new_mode)


__all__ = ['OperationModeTab']
