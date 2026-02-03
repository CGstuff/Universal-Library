"""
IdentificationPanel - Author, dates, UUID display.
"""

from typing import Dict, Any, Optional
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox
from PyQt6.QtCore import Qt

from ..utils import format_date


class IdentificationPanel(QWidget):
    """
    Panel showing asset identification info.

    Fields:
    - Author
    - Created date
    - Modified date
    - UUID (individual record)
    - Asset ID (shared across variants)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._group = QGroupBox("Identification")
        group_layout = QVBoxLayout(self._group)
        group_layout.setSpacing(4)

        # Author
        author_row = QHBoxLayout()
        author_row.addWidget(QLabel("Author:"))
        self._author_label = QLabel("-")
        self._author_label.setStyleSheet("color: #a0a0a0;")
        author_row.addWidget(self._author_label, 1)
        group_layout.addLayout(author_row)

        # Created date
        created_row = QHBoxLayout()
        created_row.addWidget(QLabel("Created:"))
        self._created_label = QLabel("-")
        self._created_label.setStyleSheet("color: #a0a0a0;")
        created_row.addWidget(self._created_label, 1)
        group_layout.addLayout(created_row)

        # Modified date
        modified_row = QHBoxLayout()
        modified_row.addWidget(QLabel("Modified:"))
        self._modified_label = QLabel("-")
        self._modified_label.setStyleSheet("color: #a0a0a0;")
        modified_row.addWidget(self._modified_label, 1)
        group_layout.addLayout(modified_row)

        # UUID (individual record)
        uuid_row = QHBoxLayout()
        uuid_row.addWidget(QLabel("UUID:"))
        self._uuid_label = QLabel("-")
        self._uuid_label.setStyleSheet("color: #a0a0a0; font-size: 10px;")
        self._uuid_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._uuid_label.setToolTip("Individual record UUID")
        uuid_row.addWidget(self._uuid_label, 1)
        group_layout.addLayout(uuid_row)

        # Asset ID (shared identity across variants)
        asset_id_row = QHBoxLayout()
        asset_id_row.addWidget(QLabel("Asset ID:"))
        self._asset_id_label = QLabel("-")
        self._asset_id_label.setStyleSheet("color: #a0a0a0; font-size: 10px;")
        self._asset_id_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._asset_id_label.setToolTip("Shared identity across all variants")
        asset_id_row.addWidget(self._asset_id_label, 1)
        group_layout.addLayout(asset_id_row)

        layout.addWidget(self._group)

    def display(self, asset: Dict[str, Any]):
        """Display asset identification info."""
        author = asset.get('author', '-')
        self._author_label.setText(author if author else '-')

        self._created_label.setText(format_date(asset.get('created_date', '')))
        self._modified_label.setText(format_date(asset.get('modified_date', '')))

        uuid = asset.get('uuid', '-')
        self._uuid_label.setText(uuid if uuid else '-')

        asset_id = asset.get('asset_id') or asset.get('version_group_id') or '-'
        self._asset_id_label.setText(asset_id if asset_id else '-')

    def clear(self):
        """Clear display."""
        self._author_label.setText("-")
        self._created_label.setText("-")
        self._modified_label.setText("-")
        self._uuid_label.setText("-")
        self._asset_id_label.setText("-")


__all__ = ['IdentificationPanel']
