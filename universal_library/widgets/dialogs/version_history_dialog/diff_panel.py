"""
Diff panel — Surface A of the version diff feature.

Lives in the preview panel (right side of the version history dialog) below
"Version Info". Shows full per-field diff vs. a selectable baseline version.
"""

from typing import Any, Dict, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMenu, QFrame
)
from PyQt6.QtCore import Qt

from ....services.version_diff import compute_version_diff, DiffResult, FieldDiff, ColorDiff


# Colors for diff rendering. Kept inline (small, theme-neutral palette).
_COLOR_ADDED = "#4CAF50"      # green
_COLOR_REMOVED = "#F44336"    # red
_COLOR_CHANGED = "#90A4AE"    # gray-blue
_COLOR_LABEL = "#e0e0e0"      # default light
_COLOR_DIM = "#888888"        # muted for prev→curr line
_COLOR_HINT = "#666666"       # placeholder/empty hints


class DiffPanel(QWidget):
    """
    Diff section for the version history preview panel.

    Public API:
        update_display(curr_version, prior_versions)
            curr_version:    the selected version dict (or None to clear).
            prior_versions:  list of version dicts in the same variant that come
                             BEFORE curr_version, sorted ascending by version.
                             May be empty (means initial version, no baseline).
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._curr_version: Optional[Dict[str, Any]] = None
        self._prior_versions: List[Dict[str, Any]] = []
        self._baseline_uuid: Optional[str] = None   # which prior version to compare against

        self._setup_ui()
        self._clear()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 0)
        outer.setSpacing(6)

        # Top divider rule + section header row
        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet("QFrame { color: #333; }")
        outer.addWidget(rule)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(4)

        self._header_label = QLabel("Changes")
        self._header_label.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #e0e0e0;"
        )
        header_row.addWidget(self._header_label)

        # Baseline picker. Button with caret + popup menu of prior versions.
        self._baseline_btn = QPushButton("—")
        self._baseline_btn.setFlat(True)
        self._baseline_btn.setStyleSheet("""
            QPushButton {
                color: #4FC3F7;
                background: transparent;
                border: none;
                padding: 0 4px;
                font-size: 12px;
                font-weight: bold;
                text-align: left;
            }
            QPushButton:hover { color: #81D4FA; }
        """)
        self._baseline_btn.clicked.connect(self._show_baseline_menu)
        self._baseline_btn.setVisible(False)
        header_row.addWidget(self._baseline_btn)
        header_row.addStretch(1)

        outer.addLayout(header_row)

        # Body container — holds field blocks
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(8)
        outer.addLayout(self._body)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_display(
        self,
        curr_version: Optional[Dict[str, Any]],
        prior_versions: List[Dict[str, Any]],
    ):
        """Render the diff for the selected version vs. the chosen baseline."""
        self._curr_version = curr_version
        self._prior_versions = list(prior_versions or [])

        if curr_version is None:
            self._clear()
            return

        # Default baseline = immediate previous version (last entry in
        # prior_versions, since the list is sorted ascending by version).
        if self._prior_versions:
            # Keep current baseline selection if it's still in the prior list,
            # otherwise reset to the immediate previous version.
            existing_uuids = {v.get('uuid') for v in self._prior_versions}
            if self._baseline_uuid not in existing_uuids:
                self._baseline_uuid = self._prior_versions[-1].get('uuid')
        else:
            self._baseline_uuid = None

        self._render()

    def clear(self):
        """Public clear (e.g., when nothing selected)."""
        self._curr_version = None
        self._prior_versions = []
        self._baseline_uuid = None
        self._clear()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _clear(self):
        """Reset to the 'no version selected' state."""
        self._header_label.setText("Changes")
        self._baseline_btn.setVisible(False)
        self._clear_body()
        hint = QLabel("Select a version to see changes.")
        hint.setStyleSheet(f"color: {_COLOR_HINT}; font-size: 11px;")
        hint.setWordWrap(True)
        self._body.addWidget(hint)

    def _clear_body(self):
        """Remove all widgets from the body layout."""
        while self._body.count():
            item = self._body.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _render(self):
        """Compute + display the diff."""
        self._clear_body()

        baseline = self._get_baseline()
        result = compute_version_diff(baseline, self._curr_version)

        # Header text + baseline picker visibility
        if result.is_initial:
            self._header_label.setText("Initial version")
            self._baseline_btn.setVisible(False)
        else:
            self._header_label.setText("Changes from")
            self._baseline_btn.setText(f"{result.prev_label} ▾")
            self._baseline_btn.setVisible(True)

        # Body
        if result.is_initial:
            msg = QLabel("No changes to display — this is the first export.")
            msg.setStyleSheet(f"color: {_COLOR_HINT}; font-size: 11px;")
            msg.setWordWrap(True)
            self._body.addWidget(msg)
            return

        if not result.has_changes():
            msg = QLabel("No metadata changes.")
            msg.setStyleSheet(f"color: {_COLOR_HINT}; font-size: 11px;")
            msg.setWordWrap(True)
            self._body.addWidget(msg)
            return

        for fd in result.fields:
            self._body.addWidget(self._render_field(fd))

    def _render_field(self, fd: FieldDiff) -> QWidget:
        """Render one FieldDiff as a small multi-line block."""
        # Color fields get a dedicated swatch-based renderer — reading
        # `#FF8800 → #00AAFF` as text is way harder than seeing the
        # actual colors next to each other.
        if isinstance(fd.shape, ColorDiff):
            return self._render_color_field(fd)

        block = QWidget()
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(0, 0, 0, 0)
        block_layout.setSpacing(1)

        accent = self._color_for(fd.change_type)
        lines = fd.format_long_block()
        if not lines:
            lines = [fd.label]

        # First line: label (bold, light)
        label_widget = QLabel(lines[0])
        label_widget.setStyleSheet(
            f"color: {_COLOR_LABEL}; font-size: 11px; font-weight: bold;"
        )
        block_layout.addWidget(label_widget)

        # Subsequent lines: dim or colored value lines
        for i, line in enumerate(lines[1:]):
            stripped = line.strip()
            is_added = stripped.startswith('+')
            is_removed = stripped.startswith('−') or stripped.startswith('-')
            if is_added:
                color = _COLOR_ADDED
            elif is_removed:
                color = _COLOR_REMOVED
            else:
                # The first body line gets the accent color (it carries the
                # prev → curr / verb); subsequent lines stay dim.
                color = accent if i == 0 else _COLOR_DIM
            line_widget = QLabel(line)
            line_widget.setStyleSheet(f"color: {color}; font-size: 11px;")
            line_widget.setWordWrap(True)
            block_layout.addWidget(line_widget)

        return block

    def _render_color_field(self, fd: FieldDiff) -> QWidget:
        """Render a ColorDiff as label + [swatch hex → swatch hex] row.

        Each swatch is a small filled rectangle. The hex strings stay
        visible alongside so artists can copy/cross-reference exact
        values, but the dominant signal is the visible color change.
        """
        block = QWidget()
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(0, 0, 0, 0)
        block_layout.setSpacing(2)

        label_widget = QLabel(fd.label)
        label_widget.setStyleSheet(
            f"color: {_COLOR_LABEL}; font-size: 11px; font-weight: bold;"
        )
        block_layout.addWidget(label_widget)

        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        accent = self._color_for(fd.change_type)
        prev_hex = (fd.prev_value or '').strip()
        curr_hex = (fd.curr_value or '').strip()

        # Previous side
        row.addWidget(self._color_swatch(prev_hex))
        prev_label = QLabel(prev_hex or '—')
        prev_label.setStyleSheet(f"color: {_COLOR_DIM}; font-size: 11px;")
        row.addWidget(prev_label)

        # Arrow
        arrow = QLabel('→')
        arrow.setStyleSheet(f"color: {_COLOR_DIM}; font-size: 11px;")
        row.addWidget(arrow)

        # Current side (accent-colored hex to match other diff types'
        # "the new value" emphasis)
        row.addWidget(self._color_swatch(curr_hex))
        curr_label = QLabel(curr_hex or '—')
        curr_label.setStyleSheet(f"color: {accent}; font-size: 11px;")
        row.addWidget(curr_label)

        shift = fd.extra.get('temp_shift', '') if fd.extra else ''
        if shift:
            shift_label = QLabel(f"({shift})")
            shift_label.setStyleSheet(
                f"color: {_COLOR_DIM}; font-size: 10px; font-style: italic;"
            )
            row.addWidget(shift_label)

        row.addStretch()
        block_layout.addWidget(row_widget)

        return block

    @staticmethod
    def _color_swatch(hex_color: str) -> QWidget:
        """Build a small filled rectangle for a hex color.

        Empty/invalid input renders a neutral placeholder swatch so the
        layout doesn't shift between "color present" and "color absent"
        rows.
        """
        swatch = QFrame()
        swatch.setFixedSize(16, 16)
        # Sanity-check the hex — anything weird falls back to a neutral
        # gray placeholder rather than risking a stylesheet parse error.
        clean = hex_color.strip().upper() if hex_color else ''
        if clean.startswith('#') and len(clean) in (4, 7):  # #RGB or #RRGGBB
            fill = clean
        else:
            fill = '#2a2a2a'
        swatch.setStyleSheet(
            f"QFrame {{ "
            f"background-color: {fill}; "
            f"border: 1px solid #555; "
            f"border-radius: 2px; "
            f"}}"
        )
        return swatch

    @staticmethod
    def _color_for(change_type: str) -> str:
        if change_type == 'added':
            return _COLOR_ADDED
        if change_type == 'removed':
            return _COLOR_REMOVED
        return _COLOR_CHANGED

    # ------------------------------------------------------------------
    # Baseline picker
    # ------------------------------------------------------------------

    def _get_baseline(self) -> Optional[Dict[str, Any]]:
        if not self._baseline_uuid:
            return None
        for v in self._prior_versions:
            if v.get('uuid') == self._baseline_uuid:
                return v
        # Fallback: most recent prior
        return self._prior_versions[-1] if self._prior_versions else None

    def _show_baseline_menu(self):
        """Popup menu of prior versions to choose comparison baseline."""
        if not self._prior_versions:
            return
        menu = QMenu(self)
        # Show most-recent prior at top
        for v in reversed(self._prior_versions):
            label = v.get('version_label', '?')
            if v.get('is_retired'):
                label += '  (retired)'
            action = menu.addAction(label)
            action.setData(v.get('uuid'))
            action.triggered.connect(
                lambda _checked=False, uuid=v.get('uuid'): self._on_baseline_picked(uuid)
            )
        menu.exec(self._baseline_btn.mapToGlobal(self._baseline_btn.rect().bottomLeft()))

    def _on_baseline_picked(self, uuid: str):
        self._baseline_uuid = uuid
        self._render()


__all__ = ['DiffPanel']
