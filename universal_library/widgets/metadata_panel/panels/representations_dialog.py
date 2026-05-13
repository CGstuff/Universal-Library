"""
RepresentationsDialog - Popup for managing proxy/render designations.

Shows custom proxies and version-based render selection with a cleaner UI.

Three artist-facing affordances live here:
- Auto-refresh on external proxy changes (event-bus driven)
- Per-proxy delete button with confirmation
- Inline 3D preview of the selected custom proxy via embedded AssetViewport
"""

import logging
import os
from typing import Dict, Any, Optional, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QRadioButton, QButtonGroup,
    QFrame, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt

from ....events.event_bus import get_event_bus

logger = logging.getLogger(__name__)


class RepresentationsDialog(QDialog):
    """
    Dialog for managing proxy/render representation designations.

    Shows:
    - Custom proxies (last 3, expandable to all) with delete + 3D preview
    - Render versions (last 3, expandable to all)
    - Apply/Regenerate/Clear actions
    """

    # Signals
    apply_requested = pyqtSignal(object, object, str)  # proxy_uuid, render_uuid, proxy_source
    regenerate_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    proxy_delete_requested = pyqtSignal(str)               # proxy_uuid
    refresh_requested = pyqtSignal(str, str)               # version_group_id, variant_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Representations")
        self.setMinimumWidth(440)
        self.setModal(False)

        # Data
        self._versions_list: List[Dict[str, Any]] = []
        self._custom_proxies_list: List[Dict[str, Any]] = []
        self._current_proxy_uuid: Optional[str] = None
        self._current_render_uuid: Optional[str] = None
        self._current_proxy_source: str = 'version'
        self._has_proxy_file: bool = False
        self._has_render_file: bool = False
        self._version_group_id: str = ""
        self._variant_name: str = "Base"

        # UI state
        self._show_all_proxies = False
        self._show_all_renders = False
        self._proxy_buttons: List[QRadioButton] = []
        self._render_buttons: List[QRadioButton] = []

        # Proxy preview viewport (created lazily inside _setup_ui)
        self._proxy_viewport = None
        self._proxy_preview_label: Optional[QLabel] = None

        self._setup_ui()

        # Listen for external proxy changes (designation flipped, proxy
        # added/deleted via another path). Re-fetches go through the parent
        # because we don't own a DB handle here.
        self._event_bus = get_event_bus()
        self._event_bus.custom_proxy_changed.connect(self._on_custom_proxy_changed)

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Proxy section
        self._proxy_section = self._create_section("PROXY", is_proxy=True)
        layout.addWidget(self._proxy_section)

        # Inline 3D preview for the selected custom proxy. Lives between
        # the proxy section and the render section so the visual mapping
        # "selected proxy → this preview" is obvious.
        self._preview_frame = self._create_preview_frame()
        layout.addWidget(self._preview_frame)

        # Render section
        self._render_section = self._create_section("RENDER", is_proxy=False)
        layout.addWidget(self._render_section)

        # Action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setFixedHeight(32)
        self._apply_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                font-weight: bold;
                padding: 4px 24px;
                border: none;
                border-radius: 4px;
                background: #0078d4;
                color: white;
            }
            QPushButton:hover { background: #1084d8; }
            QPushButton:pressed { background: #006cbd; }
            QPushButton:disabled { background: #404040; color: #888; }
        """)
        self._apply_btn.clicked.connect(self._on_apply)
        action_row.addWidget(self._apply_btn)

        self._regenerate_btn = QPushButton("Regenerate")
        self._regenerate_btn.setFixedHeight(32)
        self._regenerate_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 4px 16px;
                border: 1px solid #555;
                border-radius: 4px;
                background: transparent;
            }
            QPushButton:hover { background: #404040; }
            QPushButton:pressed { background: #333; }
        """)
        self._regenerate_btn.clicked.connect(self._on_regenerate)
        action_row.addWidget(self._regenerate_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedHeight(32)
        self._clear_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                padding: 4px 16px;
                border: 1px solid #555;
                border-radius: 4px;
                background: transparent;
                color: #f44336;
            }
            QPushButton:hover { background: #402020; }
            QPushButton:pressed { background: #301515; }
        """)
        self._clear_btn.clicked.connect(self._on_clear)
        action_row.addWidget(self._clear_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

    def _create_section(self, title: str, is_proxy: bool) -> QWidget:
        """Create a proxy or render section widget."""
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(8)

        # Header row
        header_row = QHBoxLayout()

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                font-weight: bold;
                color: #888;
                letter-spacing: 1px;
            }
        """)
        header_row.addWidget(title_label)

        header_row.addStretch()

        # File status indicator
        if is_proxy:
            self._proxy_file_label = QLabel("")
            self._proxy_file_label.setStyleSheet("font-size: 11px; color: #666;")
            header_row.addWidget(self._proxy_file_label)
        else:
            self._render_file_label = QLabel("")
            self._render_file_label.setStyleSheet("font-size: 11px; color: #666;")
            header_row.addWidget(self._render_file_label)

        section_layout.addLayout(header_row)

        # Content frame
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
            }
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(4)

        # Items container
        if is_proxy:
            self._proxy_container = QWidget()
            self._proxy_container_layout = QVBoxLayout(self._proxy_container)
            self._proxy_container_layout.setContentsMargins(0, 0, 0, 0)
            self._proxy_container_layout.setSpacing(2)
            self._proxy_button_group = QButtonGroup(self)
            self._proxy_button_group.setExclusive(False)  # Allow deselection
            frame_layout.addWidget(self._proxy_container)

            # Show all toggle
            self._proxy_show_all_btn = QPushButton("▸ Show all")
            self._proxy_show_all_btn.setStyleSheet("""
                QPushButton {
                    font-size: 11px;
                    color: #0078d4;
                    border: none;
                    background: transparent;
                    text-align: left;
                    padding: 4px 0;
                }
                QPushButton:hover { color: #1084d8; }
            """)
            self._proxy_show_all_btn.clicked.connect(self._toggle_show_all_proxies)
            self._proxy_show_all_btn.hide()
            frame_layout.addWidget(self._proxy_show_all_btn)

            # Empty state
            self._proxy_empty_label = QLabel("No proxies yet\nCreate in Blender with 'Save Proxy Version'")
            self._proxy_empty_label.setStyleSheet("""
                QLabel {
                    color: #666;
                    font-size: 11px;
                    padding: 16px;
                }
            """)
            self._proxy_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._proxy_empty_label.hide()
            frame_layout.addWidget(self._proxy_empty_label)
        else:
            self._render_container = QWidget()
            self._render_container_layout = QVBoxLayout(self._render_container)
            self._render_container_layout.setContentsMargins(0, 0, 0, 0)
            self._render_container_layout.setSpacing(2)
            self._render_button_group = QButtonGroup(self)
            frame_layout.addWidget(self._render_container)

            # Show all toggle
            self._render_show_all_btn = QPushButton("▸ Show all")
            self._render_show_all_btn.setStyleSheet("""
                QPushButton {
                    font-size: 11px;
                    color: #0078d4;
                    border: none;
                    background: transparent;
                    text-align: left;
                    padding: 4px 0;
                }
                QPushButton:hover { color: #1084d8; }
            """)
            self._render_show_all_btn.clicked.connect(self._toggle_show_all_renders)
            self._render_show_all_btn.hide()
            frame_layout.addWidget(self._render_show_all_btn)

        section_layout.addWidget(frame)
        return section

    def _create_preview_frame(self) -> QWidget:
        """Build the inline 3D-preview frame shown beneath the proxy list.

        Imports AssetViewport lazily so a missing OpenGL stack doesn't take
        the whole dialog down — we degrade to a "preview unavailable" label.
        """
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background: #1f1f1f;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
            }
        """)
        wrapper = QVBoxLayout(frame)
        wrapper.setContentsMargins(8, 8, 8, 8)
        wrapper.setSpacing(4)

        header = QLabel("PROXY PREVIEW")
        header.setStyleSheet("""
            QLabel {
                font-size: 10px;
                font-weight: bold;
                color: #777;
                letter-spacing: 1px;
                background: transparent;
                border: none;
            }
        """)
        wrapper.addWidget(header)

        try:
            from ...viewport_3d import AssetViewport
            self._proxy_viewport = AssetViewport(frame)
            self._proxy_viewport.setMinimumHeight(180)
            self._proxy_viewport.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            wrapper.addWidget(self._proxy_viewport)
        except Exception:
            logger.exception("Failed to create AssetViewport for proxy preview")
            self._proxy_viewport = None
            unavailable = QLabel("3D preview unavailable")
            unavailable.setStyleSheet(
                "color: #777; font-size: 11px; padding: 16px; border: none; background: transparent;"
            )
            unavailable.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wrapper.addWidget(unavailable)

        # Caption below the viewport — tells the user which proxy's .glb is
        # loaded (or why nothing is showing). Helpful when the .glb is
        # missing from disk for an older proxy that predates the .glb-export
        # change.
        self._proxy_preview_label = QLabel("Select a proxy to preview")
        self._proxy_preview_label.setStyleSheet(
            "color: #888; font-size: 11px; background: transparent; border: none;"
        )
        self._proxy_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wrapper.addWidget(self._proxy_preview_label)

        # Hidden until there's at least one proxy to talk about.
        frame.hide()
        return frame

    def _create_item_radio(
        self,
        label: str,
        sublabel: str,
        data: Any,
        is_designated: bool,
        button_group: QButtonGroup,
        is_proxy: bool = False
    ) -> QRadioButton:
        """Create a styled radio button for an item."""
        # Build display text
        display = label
        if sublabel:
            display += f"   {sublabel}"
        if is_designated:
            display += "   [Designated]"

        radio = QRadioButton(display)
        radio.setProperty("item_data", data)
        radio.setChecked(is_designated)

        radio.setStyleSheet("""
            QRadioButton {
                font-size: 12px;
                padding: 6px 4px;
                spacing: 8px;
            }
            QRadioButton:hover {
                background: #333;
                border-radius: 2px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
            }
        """)

        button_group.addButton(radio)

        # For proxy buttons (non-exclusive group), manually handle mutual exclusivity
        # while still allowing deselection by clicking the checked button
        if is_proxy:
            radio.clicked.connect(lambda checked, r=radio: self._on_proxy_radio_clicked(r, checked))

        return radio

    def _create_proxy_row(self, proxy: Dict[str, Any], is_designated: bool) -> QWidget:
        """Build one proxy row: [ radio ........ × ]

        The × is a small delete button that pops a confirmation and emits
        ``proxy_delete_requested`` on accept. We keep the .glb_path on the
        radio so the selection handler can drive the preview without
        another DB hit.
        """
        uuid = proxy.get('uuid')
        label = proxy.get('proxy_label', 'p???')
        poly_count = proxy.get('polygon_count', 0)
        sublabel = f"{poly_count:,} polys" if poly_count else ""

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        radio = self._create_item_radio(
            label, sublabel, uuid, is_designated, self._proxy_button_group,
            is_proxy=True,
        )
        # Stash .glb path so the preview-update slot doesn't have to
        # re-query the list.
        radio.setProperty("glb_path", proxy.get('glb_path') or "")
        radio.setProperty("proxy_label", label)
        # Update preview whenever this radio is clicked (selected or not —
        # the slot handles both cases).
        radio.clicked.connect(self._update_proxy_preview)
        self._proxy_buttons.append(radio)
        row_layout.addWidget(radio, 1)

        delete_btn = QPushButton("×")
        delete_btn.setFixedSize(20, 20)
        delete_btn.setToolTip(f"Delete proxy {label}")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                color: #888;
                background: transparent;
                border: none;
                border-radius: 2px;
                padding: 0;
            }
            QPushButton:hover {
                color: #f44336;
                background: #3a2020;
            }
            QPushButton:pressed { background: #2a1515; }
        """)
        delete_btn.clicked.connect(
            lambda _checked=False, u=uuid, lbl=label: self._on_delete_proxy_clicked(u, lbl)
        )
        row_layout.addWidget(delete_btn)

        return row

    def _on_proxy_radio_clicked(self, clicked_radio: QRadioButton, checked: bool):
        """Handle proxy radio click - enforce mutual exclusivity while allowing deselection."""
        if checked:
            # Uncheck all other proxy buttons
            for btn in self._proxy_buttons:
                if btn is not clicked_radio and btn.isChecked():
                    btn.setChecked(False)

    def populate(
        self,
        versions: List[Dict[str, Any]],
        custom_proxies: List[Dict[str, Any]],
        designations: Dict[str, Any],
        version_group_id: str = "",
        variant_name: str = "Base",
    ):
        """
        Populate the dialog with data.

        Args:
            versions: List of version dicts
            custom_proxies: List of custom proxy dicts
            designations: Current designations from RepresentationService
            version_group_id: Asset version group id (used for refresh + filtering
                external event-bus signals)
            variant_name: Variant name (same purpose)
        """
        self._versions_list = sorted(versions, key=lambda v: v.get('version', 0), reverse=True)
        self._custom_proxies_list = sorted(
            custom_proxies,
            key=lambda p: p.get('proxy_version', 0),
            reverse=True
        )

        self._current_proxy_uuid = designations.get('proxy_uuid')
        self._current_render_uuid = designations.get('render_uuid')
        self._current_proxy_source = designations.get('proxy_source', 'version')
        self._has_proxy_file = designations.get('has_proxy_file', False)
        self._has_render_file = designations.get('has_render_file', False)

        # Cache the asset context so signal-driven refreshes can target this
        # asset specifically, and so delete confirmations have something to
        # name in their messages.
        if version_group_id:
            self._version_group_id = version_group_id
        if variant_name:
            self._variant_name = variant_name

        # Update file status labels
        if self._has_proxy_file:
            self._proxy_file_label.setText(".proxy.blend ✓")
            self._proxy_file_label.setStyleSheet("font-size: 11px; color: #4CAF50;")
        else:
            self._proxy_file_label.setText(".proxy.blend ✗")
            self._proxy_file_label.setStyleSheet("font-size: 11px; color: #666;")

        if self._has_render_file:
            self._render_file_label.setText(".render.blend ✓")
            self._render_file_label.setStyleSheet("font-size: 11px; color: #4CAF50;")
        else:
            self._render_file_label.setText(".render.blend ✗")
            self._render_file_label.setStyleSheet("font-size: 11px; color: #666;")

        # Populate sections
        self._populate_proxy_section()
        self._populate_render_section()
        # Sync the inline 3D preview with whatever proxy is currently selected.
        self._update_proxy_preview()

    def _populate_proxy_section(self):
        """Populate the proxy section with custom proxies."""
        # Clear existing
        for btn in self._proxy_buttons:
            self._proxy_button_group.removeButton(btn)
        self._proxy_buttons.clear()

        # Clear layout (rows now wrap each radio, so deleteLater the row
        # widgets and everything inside goes with them)
        while self._proxy_container_layout.count():
            item = self._proxy_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._custom_proxies_list:
            self._proxy_empty_label.show()
            self._proxy_show_all_btn.hide()
            self._proxy_container.hide()
            self._preview_frame.hide()
            return

        self._proxy_empty_label.hide()
        self._proxy_container.show()
        self._preview_frame.show()

        # Determine how many to show
        total = len(self._custom_proxies_list)
        show_count = total if self._show_all_proxies else min(3, total)

        # Track UUIDs we've added to avoid duplicates
        added_uuids = set()

        for proxy in self._custom_proxies_list[:show_count]:
            uuid = proxy.get('uuid')
            added_uuids.add(uuid)
            is_designated = (
                self._current_proxy_source == 'custom' and
                uuid == self._current_proxy_uuid
            )

            row = self._create_proxy_row(proxy, is_designated)
            self._proxy_container_layout.addWidget(row)

        # If the designated custom proxy isn't in the visible list, add it
        # This prevents inadvertently changing the designation when user clicks Apply
        if (self._current_proxy_source == 'custom' and
            self._current_proxy_uuid and
            self._current_proxy_uuid not in added_uuids and
            not self._show_all_proxies):
            # Find the designated proxy in the full list
            for proxy in self._custom_proxies_list:
                if proxy.get('uuid') == self._current_proxy_uuid:
                    row = self._create_proxy_row(proxy, True)
                    self._proxy_container_layout.addWidget(row)
                    break

        # Show all toggle
        if total > 3:
            if self._show_all_proxies:
                self._proxy_show_all_btn.setText(f"▾ Show less")
            else:
                self._proxy_show_all_btn.setText(f"▸ Show all ({total})")
            self._proxy_show_all_btn.show()
        else:
            self._proxy_show_all_btn.hide()

    def _populate_render_section(self):
        """Populate the render section with versions."""
        # Clear existing
        for btn in self._render_buttons:
            self._render_button_group.removeButton(btn)
            btn.deleteLater()
        self._render_buttons.clear()

        # Clear layout
        while self._render_container_layout.count():
            item = self._render_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._versions_list:
            return

        # Add "Latest" option first
        is_latest_designated = self._current_render_uuid is None
        latest_version = self._versions_list[0] if self._versions_list else {}
        latest_radio = self._create_item_radio(
            "Latest",
            f"({latest_version.get('version_label', 'v001')})",
            None,  # None means "latest"
            is_latest_designated,
            self._render_button_group
        )
        self._render_buttons.append(latest_radio)
        self._render_container_layout.addWidget(latest_radio)

        # Determine how many versions to show (excluding the one shown as "Latest")
        versions_to_show = self._versions_list[1:] if len(self._versions_list) > 1 else []
        total = len(versions_to_show)
        show_count = total if self._show_all_renders else min(2, total)  # 2 + Latest = 3 total

        # Track UUIDs we've added to avoid duplicates
        added_uuids = set()

        for version in versions_to_show[:show_count]:
            uuid = version.get('uuid')
            added_uuids.add(uuid)
            label = version.get('version_label', 'v???')
            poly_count = version.get('polygon_count', 0)
            is_cold = version.get('is_cold', 0) == 1

            sublabel_parts = []
            if poly_count:
                sublabel_parts.append(f"{poly_count:,} polys")
            if is_cold:
                sublabel_parts.append("[cold]")
            sublabel = "  ".join(sublabel_parts)

            is_designated = uuid == self._current_render_uuid

            radio = self._create_item_radio(
                label, sublabel, uuid, is_designated, self._render_button_group
            )
            self._render_buttons.append(radio)
            self._render_container_layout.addWidget(radio)

        # If the designated render version isn't in the visible list, add it
        # This prevents inadvertently changing the designation when user clicks Apply
        if (self._current_render_uuid and
            self._current_render_uuid not in added_uuids and
            not self._show_all_renders):
            # Find the designated version in the full list
            for version in versions_to_show:
                if version.get('uuid') == self._current_render_uuid:
                    uuid = version.get('uuid')
                    label = version.get('version_label', 'v???')
                    poly_count = version.get('polygon_count', 0)
                    is_cold = version.get('is_cold', 0) == 1

                    sublabel_parts = []
                    if poly_count:
                        sublabel_parts.append(f"{poly_count:,} polys")
                    if is_cold:
                        sublabel_parts.append("[cold]")
                    sublabel = "  ".join(sublabel_parts)

                    radio = self._create_item_radio(
                        label, sublabel, uuid, True, self._render_button_group
                    )
                    self._render_buttons.append(radio)
                    self._render_container_layout.addWidget(radio)
                    break

        # Show all toggle
        if total > 2:
            if self._show_all_renders:
                self._render_show_all_btn.setText(f"▾ Show less")
            else:
                self._render_show_all_btn.setText(f"▸ Show all ({total + 1})")  # +1 for Latest
            self._render_show_all_btn.show()
        else:
            self._render_show_all_btn.hide()

    def _toggle_show_all_proxies(self):
        """Toggle showing all proxies."""
        self._show_all_proxies = not self._show_all_proxies
        self._populate_proxy_section()
        self._update_proxy_preview()

    def _toggle_show_all_renders(self):
        """Toggle showing all render versions."""
        self._show_all_renders = not self._show_all_renders
        self._populate_render_section()

    def _get_selected_proxy(self) -> tuple:
        """Get selected proxy UUID and source."""
        checked = self._get_checked_proxy_button()
        if checked:
            uuid = checked.property("item_data")
            return uuid, 'custom'
        return None, 'version'

    def _get_checked_proxy_button(self) -> Optional[QRadioButton]:
        """Return the currently-checked proxy radio (group is non-exclusive)."""
        for btn in self._proxy_buttons:
            if btn.isChecked():
                return btn
        return None

    def _get_selected_render(self) -> Optional[str]:
        """Get selected render UUID (None = latest)."""
        checked = self._render_button_group.checkedButton()
        if checked:
            return checked.property("item_data")
        return None

    def _on_apply(self):
        """Handle apply button click."""
        proxy_uuid, proxy_source = self._get_selected_proxy()
        render_uuid = self._get_selected_render()
        self.apply_requested.emit(proxy_uuid, render_uuid, proxy_source)

    def _on_regenerate(self):
        """Handle regenerate button click."""
        self.regenerate_requested.emit()

    def _on_clear(self):
        """Handle clear button click."""
        self.clear_requested.emit()

    # ------------------------------------------------------------------
    # Delete + auto-refresh + preview
    # ------------------------------------------------------------------

    def _on_delete_proxy_clicked(self, proxy_uuid: str, proxy_label: str):
        """Confirm and request deletion of a single custom proxy.

        The destructive action (DB row + files on disk) is irreversible, so
        we gate it behind a QMessageBox.question. We surface the
        high-water-mark behavior in the prompt so the artist isn't surprised
        when the number doesn't get reused.
        """
        if not proxy_uuid:
            return
        result = QMessageBox.question(
            self,
            "Delete custom proxy",
            (
                f"Delete custom proxy <b>{proxy_label}</b>?\n\n"
                "This removes the proxy from the library — the .blend, .glb, "
                "thumbnail and JSON sidecar are deleted from disk.\n\n"
                "The proxy number will not be reused for future proxies."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        # Hand off to the panel which owns the RepresentationService handle.
        self.proxy_delete_requested.emit(proxy_uuid)

    def _on_custom_proxy_changed(self, version_group_id: str, variant_name: str):
        """React to external proxy changes (designation flip, add, delete).

        Only fires a refresh when (a) the dialog is visible and (b) the
        signal matches the asset we're currently showing. Otherwise we'd
        thrash the UI on every proxy event app-wide.
        """
        if not self.isVisible():
            return
        if (version_group_id != self._version_group_id
                or variant_name != self._variant_name):
            return
        # Re-fetch is the parent's job — we don't own the DB handle. The
        # parent listens to refresh_requested and calls populate() again.
        self.refresh_requested.emit(version_group_id, variant_name)

    def _update_proxy_preview(self, _checked: bool = False):
        """Load the .glb of the currently-checked proxy into the viewport.

        Called both from the radio-click slot (which passes a bool) and
        directly (no args) after a re-populate. The ``_checked`` arg is
        ignored — we re-derive selection from the group state because a
        click can also be a deselect.
        """
        if self._proxy_viewport is None or self._proxy_preview_label is None:
            return

        checked = self._get_checked_proxy_button()
        if checked is None:
            self._proxy_viewport.clear()
            self._proxy_preview_label.setText("Select a proxy to preview")
            return

        glb_path = checked.property("glb_path") or ""
        label = checked.property("proxy_label") or "?"

        if not glb_path:
            # Older proxy authored before the .glb-on-save change. We can't
            # render it — point the user at re-saving.
            self._proxy_viewport.clear()
            self._proxy_preview_label.setText(
                f"{label}: no .glb on disk (re-save proxy in Blender to enable preview)"
            )
            return

        if not os.path.isfile(glb_path):
            self._proxy_viewport.clear()
            self._proxy_preview_label.setText(
                f"{label}: .glb file missing on disk"
            )
            return

        try:
            self._proxy_viewport.load_glb(glb_path)
            self._proxy_preview_label.setText(f"{label}")
        except Exception:
            logger.exception("Failed to load proxy .glb: %s", glb_path)
            self._proxy_preview_label.setText(f"{label}: failed to load preview")

    def closeEvent(self, event):
        """Drop preview GL state on close.

        We deliberately do NOT disconnect from the event bus here — the
        dialog is created once and reused (just hidden between asset
        selections), and re-establishing the connection lazily on every
        show would be easy to forget. ``_on_custom_proxy_changed`` filters
        on ``isVisible()`` so stray fires while hidden are cheap.
        """
        if self._proxy_viewport is not None:
            try:
                self._proxy_viewport.clear()
            except Exception:
                logger.debug("AssetViewport.clear() raised on close", exc_info=True)
        super().closeEvent(event)


__all__ = ['RepresentationsDialog']
