"""
RetiredAssetsDialog - Dialog for viewing and restoring retired assets.
"""

from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QHeaderView, QAbstractItemView,
    QMessageBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap

from ...services.retire_service import get_retire_service
from ...services.thumbnail_loader import get_thumbnail_loader


class RetiredAssetsDialog(QDialog):
    """
    Dialog for browsing and restoring retired assets.
    """

    THUMB_SIZE = 32

    def __init__(self, parent=None):
        super().__init__(parent)
        self._retire_service = get_retire_service()
        self._thumbnail_loader = get_thumbnail_loader()
        self._retired_assets: List[Dict[str, Any]] = []

        self.setWindowTitle("Retired Assets")
        self.setModal(True)
        self.resize(850, 500)
        self.setMinimumSize(650, 400)

        self._setup_ui()
        self._connect_signals()
        self._load_retired_assets()

    def _connect_signals(self):
        """Connect signals."""
        self._thumbnail_loader.thumbnail_loaded.connect(self._on_thumbnail_loaded)

    def _setup_ui(self):
        """Setup dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header_layout = QHBoxLayout()

        header_label = QLabel("Retired Assets")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Search filter
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search...")
        self._search_edit.setFixedWidth(200)
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_changed)
        header_layout.addWidget(self._search_edit)

        layout.addLayout(header_layout)

        # Info label
        self._info_label = QLabel("Assets that have been retired can be restored here.")
        self._info_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._info_label)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "", "Name", "Variant", "Type", "Version", "Retired Date", "Retired By"
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setIconSize(QSize(self.THUMB_SIZE, self.THUMB_SIZE))

        # Column sizing
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # Thumbnail
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Name
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)

        self._table.setColumnWidth(0, self.THUMB_SIZE + 8)  # Thumbnail
        self._table.setColumnWidth(2, 100)
        self._table.setColumnWidth(3, 80)
        self._table.setColumnWidth(4, 60)
        self._table.setColumnWidth(5, 140)
        self._table.setColumnWidth(6, 100)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

        # Action buttons
        action_layout = QHBoxLayout()

        self._restore_btn = QPushButton("Restore Selected")
        self._restore_btn.setEnabled(False)
        self._restore_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #43A047; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self._restore_btn.clicked.connect(self._on_restore_clicked)
        action_layout.addWidget(self._restore_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._load_retired_assets)
        action_layout.addWidget(self._refresh_btn)

        action_layout.addStretch()

        # Count label
        self._count_label = QLabel("0 retired assets")
        self._count_label.setStyleSheet("color: #888;")
        action_layout.addWidget(self._count_label)

        layout.addLayout(action_layout)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

    def _load_retired_assets(self):
        """Load retired assets from service."""
        self._retired_assets = self._retire_service.get_retired_assets()
        # DEBUG: Check what thumbnail paths we're getting
        for a in self._retired_assets:
            print(f"[RETIRE DEBUG] {a.get('name')} {a.get('version_label')}: {a.get('thumbnail_path')}")
        self._populate_table()

    def _populate_table(self, filter_text: str = ""):
        """Populate table with retired assets."""
        self._table.setRowCount(0)
        filter_lower = filter_text.lower()

        visible_count = 0
        for asset in self._retired_assets:
            name = asset.get('name', 'Unknown')
            variant = asset.get('variant_name', 'Base')
            asset_type = asset.get('asset_type', 'other')
            uuid = asset.get('uuid')

            # Apply filter
            if filter_lower:
                if (filter_lower not in name.lower() and
                    filter_lower not in variant.lower() and
                    filter_lower not in asset_type.lower()):
                    continue

            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setRowHeight(row, self.THUMB_SIZE + 4)

            # Thumbnail (column 0)
            thumb_item = QTableWidgetItem()
            thumb_item.setData(Qt.ItemDataRole.UserRole, uuid)
            self._table.setItem(row, 0, thumb_item)

            # Load thumbnail
            thumb_path = asset.get('thumbnail_path', '')
            if thumb_path:
                pixmap = self._thumbnail_loader.request_thumbnail(uuid, thumb_path, self.THUMB_SIZE)
                if pixmap:
                    thumb_item.setIcon(QIcon(pixmap))

            # Name (column 1)
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, uuid)
            self._table.setItem(row, 1, name_item)

            # Variant
            self._table.setItem(row, 2, QTableWidgetItem(variant))

            # Type
            self._table.setItem(row, 3, QTableWidgetItem(asset_type.capitalize()))

            # Version
            version_label = asset.get('version_label', 'v001')
            self._table.setItem(row, 4, QTableWidgetItem(version_label))

            # Retired Date
            retired_date = asset.get('retired_date', '')
            if retired_date:
                # Format date nicely
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(retired_date)
                    retired_date = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    pass
            self._table.setItem(row, 5, QTableWidgetItem(retired_date))

            # Retired By
            retired_by = asset.get('retired_by', '')
            self._table.setItem(row, 6, QTableWidgetItem(retired_by))

            visible_count += 1

        self._count_label.setText(f"{visible_count} retired asset{'s' if visible_count != 1 else ''}")
        self._restore_btn.setEnabled(False)

    def _on_search_changed(self, text: str):
        """Handle search text changed."""
        self._populate_table(text)

    def _on_selection_changed(self):
        """Handle table selection changed."""
        selected = self._table.selectedItems()
        self._restore_btn.setEnabled(len(selected) > 0)

    def _on_thumbnail_loaded(self, uuid: str, pixmap: QPixmap):
        """Handle thumbnail loaded from loader."""
        for row in range(self._table.rowCount()):
            thumb_item = self._table.item(row, 0)
            if thumb_item and thumb_item.data(Qt.ItemDataRole.UserRole) == uuid:
                thumb_item.setIcon(QIcon(pixmap))
                break

    def _on_restore_clicked(self):
        """Handle restore button clicked."""
        selected_rows = self._table.selectedIndexes()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        name_item = self._table.item(row, 1)  # Name is now column 1
        if not name_item:
            return

        uuid = name_item.data(Qt.ItemDataRole.UserRole)
        name = name_item.text()
        variant = self._table.item(row, 2).text()  # Variant is now column 2

        # Confirm restore
        reply = QMessageBox.question(
            self,
            "Confirm Restore",
            f"Restore '{name}/{variant}' and all its versions back to active library?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Perform restore
        success, message = self._retire_service.restore_from_retired(uuid)

        if success:
            QMessageBox.information(self, "Restored", message)
            self._load_retired_assets()
        else:
            QMessageBox.warning(self, "Restore Failed", message)


__all__ = ['RetiredAssetsDialog']
