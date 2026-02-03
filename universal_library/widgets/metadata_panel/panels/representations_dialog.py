"""
RepresentationsDialog - Popup for managing proxy/render designations.

Shows custom proxies and version-based render selection with a cleaner UI.
"""

from typing import Dict, Any, Optional, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QRadioButton, QButtonGroup,
    QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt


class RepresentationsDialog(QDialog):
    """
    Dialog for managing proxy/render representation designations.
    
    Shows:
    - Custom proxies (last 3, expandable to all)
    - Render versions (last 3, expandable to all)
    - Apply/Regenerate/Clear actions
    """
    
    # Signals
    apply_requested = pyqtSignal(object, object, str)  # proxy_uuid, render_uuid, proxy_source
    regenerate_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Representations")
        self.setMinimumWidth(400)
        self.setModal(False)
        
        # Data
        self._versions_list: List[Dict[str, Any]] = []
        self._custom_proxies_list: List[Dict[str, Any]] = []
        self._current_proxy_uuid: Optional[str] = None
        self._current_render_uuid: Optional[str] = None
        self._current_proxy_source: str = 'version'
        self._has_proxy_file: bool = False
        self._has_render_file: bool = False
        
        # UI state
        self._show_all_proxies = False
        self._show_all_renders = False
        self._proxy_buttons: List[QRadioButton] = []
        self._render_buttons: List[QRadioButton] = []
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Proxy section
        self._proxy_section = self._create_section("PROXY", is_proxy=True)
        layout.addWidget(self._proxy_section)
        
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
        designations: Dict[str, Any]
    ):
        """
        Populate the dialog with data.
        
        Args:
            versions: List of version dicts
            custom_proxies: List of custom proxy dicts
            designations: Current designations from RepresentationService
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
    
    def _populate_proxy_section(self):
        """Populate the proxy section with custom proxies."""
        # Clear existing
        for btn in self._proxy_buttons:
            self._proxy_button_group.removeButton(btn)
            btn.deleteLater()
        self._proxy_buttons.clear()
        
        # Clear layout
        while self._proxy_container_layout.count():
            item = self._proxy_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self._custom_proxies_list:
            self._proxy_empty_label.show()
            self._proxy_show_all_btn.hide()
            self._proxy_container.hide()
            return
        
        self._proxy_empty_label.hide()
        self._proxy_container.show()
        
        # Determine how many to show
        total = len(self._custom_proxies_list)
        show_count = total if self._show_all_proxies else min(3, total)
        
        # Track UUIDs we've added to avoid duplicates
        added_uuids = set()
        
        for proxy in self._custom_proxies_list[:show_count]:
            uuid = proxy.get('uuid')
            added_uuids.add(uuid)
            label = proxy.get('proxy_label', 'p???')
            poly_count = proxy.get('polygon_count', 0)
            
            sublabel = f"{poly_count:,} polys" if poly_count else ""
            is_designated = (
                self._current_proxy_source == 'custom' and 
                uuid == self._current_proxy_uuid
            )
            
            radio = self._create_item_radio(
                label, sublabel, uuid, is_designated, self._proxy_button_group,
                is_proxy=True
            )
            self._proxy_buttons.append(radio)
            self._proxy_container_layout.addWidget(radio)
        
        # If the designated custom proxy isn't in the visible list, add it
        # This prevents inadvertently changing the designation when user clicks Apply
        if (self._current_proxy_source == 'custom' and 
            self._current_proxy_uuid and 
            self._current_proxy_uuid not in added_uuids and
            not self._show_all_proxies):
            # Find the designated proxy in the full list
            for proxy in self._custom_proxies_list:
                if proxy.get('uuid') == self._current_proxy_uuid:
                    uuid = proxy.get('uuid')
                    label = proxy.get('proxy_label', 'p???')
                    poly_count = proxy.get('polygon_count', 0)
                    
                    sublabel = f"{poly_count:,} polys" if poly_count else ""
                    
                    radio = self._create_item_radio(
                        label, sublabel, uuid, True, self._proxy_button_group,
                        is_proxy=True
                    )
                    self._proxy_buttons.append(radio)
                    self._proxy_container_layout.addWidget(radio)
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
    
    def _toggle_show_all_renders(self):
        """Toggle showing all render versions."""
        self._show_all_renders = not self._show_all_renders
        self._populate_render_section()
    
    def _get_selected_proxy(self) -> tuple:
        """Get selected proxy UUID and source."""
        checked = self._proxy_button_group.checkedButton()
        if checked:
            uuid = checked.property("item_data")
            return uuid, 'custom'
        return None, 'version'
    
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


__all__ = ['RepresentationsDialog']
