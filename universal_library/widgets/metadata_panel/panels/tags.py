"""
TagsWidget - Tag management for assets.
"""

import json
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QComboBox, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal


class TagsWidget(QWidget):
    """
    Widget for managing asset tags.

    Features:
    - Display current tags as clickable pills
    - Dropdown to add new tags
    - Remove tags by clicking X

    Signals:
        tag_added: Emitted when tag added (uuid, tag_id)
        tag_removed: Emitted when tag removed (uuid, tag_id)
        tags_changed: Emitted when tags change (uuid, [tag_ids])
    """

    tag_added = pyqtSignal(str, int)  # uuid, tag_id
    tag_removed = pyqtSignal(str, int)  # uuid, tag_id
    tags_changed = pyqtSignal(str, list)  # uuid, [tag_ids]

    def __init__(self, db_service, parent=None):
        super().__init__(parent)
        self._db_service = db_service
        self._current_uuid: Optional[str] = None
        self._current_tag_ids: List[int] = []
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._group = QGroupBox("Tags")
        group_layout = QVBoxLayout(self._group)
        group_layout.setSpacing(4)

        # Tag pills container
        self._tags_container = QWidget()
        self._tags_flow = QHBoxLayout(self._tags_container)
        self._tags_flow.setContentsMargins(0, 0, 0, 0)
        self._tags_flow.setSpacing(4)
        group_layout.addWidget(self._tags_container)

        # Add tag dropdown
        add_tag_row = QHBoxLayout()
        self._tag_dropdown = QComboBox()
        self._tag_dropdown.setFixedHeight(24)
        self._tag_dropdown.setPlaceholderText("Select tag to add...")
        self._tag_dropdown.activated.connect(self._on_tag_selected)
        add_tag_row.addWidget(self._tag_dropdown, 1)
        group_layout.addLayout(add_tag_row)

        layout.addWidget(self._group)

    def set_asset(self, uuid: str):
        """Set current asset and refresh display."""
        self._current_uuid = uuid

        # Get tags for this asset
        tags_v2 = self._db_service.get_asset_tags(uuid)
        self._update_display(tags_v2)
        self._refresh_dropdown()

    def _update_display(self, tags_data):
        """Update tags display with clickable tag pills."""
        # Clear existing tags
        while self._tags_flow.count():
            item = self._tags_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._current_tag_ids = []

        # Handle new tags_v2 format (list of dicts)
        if isinstance(tags_data, list) and tags_data and isinstance(tags_data[0], dict):
            for tag in tags_data[:10]:
                tag_id = tag.get('id')
                tag_name = tag.get('name', 'Unknown')
                tag_color = tag.get('color', '#607D8B')

                self._current_tag_ids.append(tag_id)

                # Create clickable tag button with X
                tag_btn = QPushButton(f"{tag_name} \u00d7")
                tag_btn.setToolTip(f"Click to remove '{tag_name}'")
                tag_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                tag_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {tag_color};
                        color: white;
                        padding: 2px 6px;
                        border-radius: 0px;
                        border: none;
                        font-size: 11px;
                    }}
                    QPushButton:hover {{
                        background-color: #c0392b;
                    }}
                """)
                tag_btn.clicked.connect(lambda checked, tid=tag_id: self._on_remove_tag(tid))
                self._tags_flow.addWidget(tag_btn)

            self._tags_flow.addStretch()
            return

        # Handle legacy string/JSON format
        if not tags_data:
            no_tags = QLabel("No tags")
            no_tags.setStyleSheet("color: #606060;")
            self._tags_flow.addWidget(no_tags)
            return

        try:
            tags = json.loads(tags_data) if isinstance(tags_data, str) else tags_data
            if not tags:
                no_tags = QLabel("No tags")
                no_tags.setStyleSheet("color: #606060;")
                self._tags_flow.addWidget(no_tags)
                return

            for tag in tags[:10]:
                tag_label = QLabel(tag)
                tag_label.setStyleSheet("""
                    QLabel {
                        background-color: #404040;
                        color: #e0e0e0;
                        padding: 2px 6px;
                        border-radius: 0px;
                        font-size: 11px;
                    }
                """)
                self._tags_flow.addWidget(tag_label)
        except (json.JSONDecodeError, TypeError):
            no_tags = QLabel("No tags")
            no_tags.setStyleSheet("color: #606060;")
            self._tags_flow.addWidget(no_tags)

    def _on_tag_selected(self, index: int):
        """Handle tag selection from dropdown."""
        if not self._current_uuid or index < 0:
            return

        tag_id = self._tag_dropdown.itemData(index)
        if not tag_id:
            return

        if tag_id not in self._current_tag_ids:
            if self._db_service.add_tag_to_asset(self._current_uuid, tag_id):
                self._current_tag_ids.append(tag_id)

                # Refresh display
                tags_v2 = self._db_service.get_asset_tags(self._current_uuid)
                self._update_display(tags_v2)
                self._refresh_dropdown()

                # Emit signals
                self.tag_added.emit(self._current_uuid, tag_id)
                self.tags_changed.emit(self._current_uuid, self._current_tag_ids.copy())

        # Reset dropdown
        self._tag_dropdown.setCurrentIndex(-1)

    def _on_remove_tag(self, tag_id: int):
        """Handle removing a tag from the asset."""
        if not self._current_uuid:
            return

        if self._db_service.remove_tag_from_asset(self._current_uuid, tag_id):
            if tag_id in self._current_tag_ids:
                self._current_tag_ids.remove(tag_id)

            # Refresh display
            tags_v2 = self._db_service.get_asset_tags(self._current_uuid)
            self._update_display(tags_v2)
            self._refresh_dropdown()

            # Emit signals
            self.tag_removed.emit(self._current_uuid, tag_id)
            self.tags_changed.emit(self._current_uuid, self._current_tag_ids.copy())

    def _refresh_dropdown(self):
        """Refresh tag dropdown with available tags."""
        self._tag_dropdown.clear()

        all_tags = self._db_service.get_all_tags_v2()

        # Filter out tags already on this asset
        available_tags = [
            tag for tag in all_tags
            if tag.get('id') not in self._current_tag_ids
        ]

        if not available_tags:
            self._tag_dropdown.setEnabled(False)
            self._tag_dropdown.setPlaceholderText("No more tags available")
        else:
            self._tag_dropdown.setEnabled(True)
            self._tag_dropdown.setPlaceholderText("Select tag to add...")
            for tag in available_tags:
                self._tag_dropdown.addItem(tag.get('name', 'Unknown'), tag.get('id'))

        self._tag_dropdown.setCurrentIndex(-1)

    def clear(self):
        """Clear display."""
        self._current_uuid = None
        self._current_tag_ids = []
        self._update_display(None)

    @property
    def current_tag_ids(self) -> List[int]:
        """Get current tag IDs."""
        return self._current_tag_ids.copy()


__all__ = ['TagsWidget']
