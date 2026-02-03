"""
ReviewStateRenderer - Review cycle state display.
"""

from typing import Dict, Any, Optional
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QMenu
from PyQt6.QtCore import pyqtSignal, QObject

from ....config import Config, REVIEW_CYCLE_TYPES


class ReviewStateRenderer(QObject):
    """
    Renders review state UI elements.

    Handles:
    - Review state badge display
    - Submit for review button with cycle type menu
    - State transitions and updates

    Signals:
        cycle_type_selected: Emitted when user selects a cycle type (cycle_type)
    """

    cycle_type_selected = pyqtSignal(str)

    def __init__(
        self,
        state_widget: QWidget,
        state_label: QLabel,
        submit_btn: QPushButton,
        cycle_menu: QMenu,
        parent=None
    ):
        """
        Initialize with widget references.

        Args:
            state_widget: Container widget for state display
            state_label: Label showing current state
            submit_btn: Button to submit for review
            cycle_menu: Menu for selecting cycle type
        """
        super().__init__(parent)
        self._state_widget = state_widget
        self._state_label = state_label
        self._submit_btn = submit_btn
        self._cycle_menu = cycle_menu

        # Connect menu
        self._cycle_menu.triggered.connect(self._on_menu_triggered)

    def _on_menu_triggered(self, action):
        """Handle cycle type selection."""
        cycle_type = action.data()
        if cycle_type:
            self.cycle_type_selected.emit(cycle_type)

    def render(
        self,
        review_state: Optional[str],
        cycle_type: Optional[str] = None,
        can_start_review: bool = True,
        active_cycle: Optional[Dict[str, Any]] = None
    ):
        """
        Update review state display.

        Args:
            review_state: Current review state (needs_review, in_review, etc.)
            cycle_type: Optional cycle type to display
            can_start_review: Whether user can start a new review cycle
            active_cycle: Active cycle data if any
        """
        # Handle 'final' state specially - show state AND allow new cycle
        if review_state == 'final':
            self._render_final_state(cycle_type)
            return

        if review_state:
            self._render_active_state(review_state, cycle_type, active_cycle)
        else:
            self._render_no_state(can_start_review, active_cycle)

    def _render_final_state(self, cycle_type: Optional[str]):
        """Render final state (completed cycle)."""
        state_config = Config.REVIEW_STATES.get('final', {})
        state_label = state_config.get('label', 'Final')

        if cycle_type:
            cycle_info = REVIEW_CYCLE_TYPES.get(cycle_type, {})
            cycle_label = cycle_info.get('label', cycle_type.title())
            label_text = f"{cycle_label}: {state_label}"
        else:
            label_text = state_label

        bg_color = '#9C27B0'  # Purple for final

        self._state_label.setText(label_text)
        self._state_label.setStyleSheet(f"""
            QLabel {{
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                background-color: {bg_color};
                color: white;
            }}
        """)
        self._state_widget.show()

        # Also show button for new cycle
        self._submit_btn.setEnabled(True)
        self._submit_btn.setText("Start New Cycle \u25bc")
        self._submit_btn.setToolTip("Start a new review cycle (previous cycle is final)")
        self._submit_btn.show()

    def _render_active_state(
        self,
        review_state: str,
        cycle_type: Optional[str],
        active_cycle: Optional[Dict[str, Any]]
    ):
        """Render active review state."""
        # Hide submit button
        self._submit_btn.hide()

        # Get state config
        state_config = Config.REVIEW_STATES.get(review_state, {})
        state_label = state_config.get('label', review_state)
        state_color = state_config.get('color', '#888888')

        # Determine label text and color
        if cycle_type:
            cycle_info = REVIEW_CYCLE_TYPES.get(cycle_type, {})
            cycle_label = cycle_info.get('label', cycle_type.title())
            bg_color = cycle_info.get('color', state_color)
            label_text = f"{cycle_label}: {state_label}"
        elif active_cycle:
            active_type = active_cycle.get('cycle_type', '')
            cycle_info = REVIEW_CYCLE_TYPES.get(active_type, {})
            cycle_label = cycle_info.get('label', active_type.title())
            bg_color = cycle_info.get('color', state_color)
            label_text = f"{cycle_label}: {state_label}"
        else:
            label_text = state_label
            bg_color = state_color

        self._state_label.setText(label_text)
        self._state_label.setStyleSheet(f"""
            QLabel {{
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                background-color: {bg_color};
                color: white;
            }}
        """)
        self._state_widget.show()

    def _render_no_state(
        self,
        can_start_review: bool,
        active_cycle: Optional[Dict[str, Any]]
    ):
        """Render no review state (can start new cycle)."""
        if can_start_review:
            # Show submit button
            self._submit_btn.setEnabled(True)
            self._submit_btn.setText("Start Review \u25bc")
            self._submit_btn.show()
            self._state_widget.hide()
        elif active_cycle:
            # Has active cycle, show its state
            cycle_type = active_cycle.get('cycle_type', '')
            review_state = active_cycle.get('review_state', 'needs_review')
            self._render_active_state(review_state, cycle_type, None)
        else:
            self._state_widget.hide()
            self._submit_btn.hide()

    def clear(self):
        """Clear/hide all review state UI."""
        self._state_widget.hide()
        self._submit_btn.hide()
        self._submit_btn.setEnabled(False)

    def show_menu_at_button(self):
        """Show cycle type menu below the submit button."""
        button_pos = self._submit_btn.mapToGlobal(
            self._submit_btn.rect().bottomLeft()
        )
        self._cycle_menu.exec(button_pos)


__all__ = ['ReviewStateRenderer']
