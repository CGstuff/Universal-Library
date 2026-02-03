"""
AssetHistoryDialog - Dialog for viewing asset audit trail (Studio Mode only).

Shows who did what and when for an asset - complete audit history.
"""

import csv
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QLabel, QPushButton,
    QDialogButtonBox, QHeaderView, QAbstractItemView, QComboBox,
    QTableWidgetItem, QApplication, QFileDialog, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QIcon

from ...services.database_service import get_database_service
from ...services.user_service import get_user_service


# Action icons and colors
ACTION_STYLES = {
    'create': {'icon': 'SP_FileIcon', 'color': '#4CAF50', 'label': 'Created'},
    'version_create': {'icon': 'SP_FileDialogNewFolder', 'color': '#2196F3', 'label': 'New Version'},
    'update_metadata': {'icon': 'SP_FileDialogDetailedView', 'color': '#FF9800', 'label': 'Updated'},
    'status_change': {'icon': 'SP_BrowserReload', 'color': '#9C27B0', 'label': 'Status Changed'},
    'approve': {'icon': 'SP_DialogApplyButton', 'color': '#4CAF50', 'label': 'Approved'},
    'finalize': {'icon': 'SP_DialogYesButton', 'color': '#4CAF50', 'label': 'Finalized'},
    'archive': {'icon': 'SP_TrashIcon', 'color': '#607D8B', 'label': 'Archived'},
    'restore': {'icon': 'SP_DialogResetButton', 'color': '#00BCD4', 'label': 'Restored'},
    'delete': {'icon': 'SP_TrashIcon', 'color': '#F44336', 'label': 'Deleted'},
    'import': {'icon': 'SP_ArrowDown', 'color': '#3F51B5', 'label': 'Imported'},
    'export': {'icon': 'SP_ArrowUp', 'color': '#009688', 'label': 'Exported'},
    'thumbnail_update': {'icon': 'SP_DesktopIcon', 'color': '#795548', 'label': 'Thumbnail Updated'},
    'variant_create': {'icon': 'SP_FileDialogContentsView', 'color': '#E91E63', 'label': 'Variant Created'},
    'promote_latest': {'icon': 'SP_ArrowUp', 'color': '#FFC107', 'label': 'Promoted to Latest'},
}


class AssetHistoryDialog(QDialog):
    """
    Dialog for viewing asset audit trail.

    Features:
    - Shows all audit actions for an asset
    - Filter by action type and user
    - Export to CSV for compliance
    - Only available in Studio Mode
    """

    def __init__(self, asset_uuid: str, asset_name: str = "Asset", parent=None):
        super().__init__(parent)

        self._asset_uuid = asset_uuid
        self._asset_name = asset_name
        self._db_service = get_database_service()
        self._user_service = get_user_service()
        self._history: List[Dict[str, Any]] = []

        self.setWindowTitle(f"Audit History - {asset_name}")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        # Size
        self._setup_size()
        self._create_ui()
        self._load_history()

    def _setup_size(self):
        """Configure dialog size based on screen."""
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            width = int(screen_rect.width() * 0.5)
            height = int(screen_rect.height() * 0.6)
            self.resize(width, height)
            x = screen_rect.x() + (screen_rect.width() - width) // 2
            y = screen_rect.y() + (screen_rect.height() - height) // 2
            self.move(x, y)
        else:
            self.resize(800, 600)
        self.setMinimumSize(600, 400)

    def _create_ui(self):
        """Create UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header with asset info
        header = QLabel(f"<b>{self._asset_name}</b> - Audit Trail")
        header.setStyleSheet("font-size: 14px;")
        layout.addWidget(header)

        # Filter row
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Filter by Action:"))
        self._action_filter = QComboBox()
        self._action_filter.setMinimumWidth(150)
        self._action_filter.addItem("All Actions", None)
        for action, style in ACTION_STYLES.items():
            self._action_filter.addItem(style['label'], action)
        self._action_filter.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self._action_filter)

        filter_layout.addWidget(QLabel("Filter by User:"))
        self._user_filter = QComboBox()
        self._user_filter.setMinimumWidth(150)
        self._user_filter.addItem("All Users", None)
        # Users will be populated from history
        self._user_filter.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self._user_filter)

        filter_layout.addStretch()

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_history)
        filter_layout.addWidget(refresh_btn)

        # Export button
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        filter_layout.addWidget(export_btn)

        layout.addLayout(filter_layout)

        # History table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "Timestamp", "Action", "User", "Role", "Version", "Details"
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888;")
        layout.addWidget(self._status_label)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_history(self):
        """Load audit history from database."""
        try:
            self._history = self._db_service.get_asset_audit_history(
                self._asset_uuid,
                limit=500
            )
            self._populate_user_filter()
            self._apply_filters()
        except Exception as e:
            self._history = []
            self._status_label.setText(f"Error loading history: {e}")

    def _populate_user_filter(self):
        """Populate user filter from history."""
        self._user_filter.blockSignals(True)
        self._user_filter.clear()
        self._user_filter.addItem("All Users", None)

        users = set()
        for entry in self._history:
            actor = entry.get('actor')
            display_name = entry.get('actor_display_name') or actor
            if actor and actor not in users:
                users.add(actor)
                self._user_filter.addItem(display_name, actor)

        self._user_filter.blockSignals(False)

    def _apply_filters(self):
        """Apply filters and refresh table."""
        action_filter = self._action_filter.currentData()
        user_filter = self._user_filter.currentData()

        filtered = []
        for entry in self._history:
            if action_filter and entry.get('action') != action_filter:
                continue
            if user_filter and entry.get('actor') != user_filter:
                continue
            filtered.append(entry)

        self._populate_table(filtered)

    def _populate_table(self, entries: List[Dict[str, Any]]):
        """Populate table with audit entries."""
        self._table.setRowCount(0)

        for entry in entries:
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Timestamp
            timestamp = entry.get('timestamp', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    pass
            self._table.setItem(row, 0, QTableWidgetItem(timestamp))

            # Action with color
            action = entry.get('action', '')
            style = ACTION_STYLES.get(action, {'label': action.title(), 'color': '#888'})
            action_item = QTableWidgetItem(style['label'])
            action_item.setForeground(QColor(style['color']))
            self._table.setItem(row, 1, action_item)

            # User
            actor_display = entry.get('actor_display_name') or entry.get('actor', '')
            self._table.setItem(row, 2, QTableWidgetItem(actor_display))

            # Role
            role = entry.get('actor_role', '').title()
            self._table.setItem(row, 3, QTableWidgetItem(role))

            # Version
            version = entry.get('version_label', '')
            variant = entry.get('variant_name', '')
            if variant and variant != 'Base':
                version = f"{version} ({variant})"
            self._table.setItem(row, 4, QTableWidgetItem(version))

            # Details
            details = self._format_details(entry)
            self._table.setItem(row, 5, QTableWidgetItem(details))

        self._status_label.setText(f"Showing {len(entries)} of {len(self._history)} entries")

    def _format_details(self, entry: Dict[str, Any]) -> str:
        """Format details for display."""
        details_parts = []

        # Previous -> New value
        prev = entry.get('previous_value')
        new = entry.get('new_value')
        if prev and new:
            details_parts.append(f"{prev} → {new}")
        elif new:
            details_parts.append(f"→ {new}")

        # Source
        source = entry.get('source', '')
        if source and source != 'desktop':
            details_parts.append(f"[{source}]")

        # JSON details (truncated)
        details_json = entry.get('details')
        if details_json:
            try:
                import json
                details_dict = json.loads(details_json) if isinstance(details_json, str) else details_json
                if isinstance(details_dict, dict):
                    for key, value in details_dict.items():
                        details_parts.append(f"{key}: {value}")
            except (json.JSONDecodeError, TypeError):
                pass

        return " | ".join(details_parts) if details_parts else ""

    def _export_csv(self):
        """Export audit history to CSV file."""
        # Prompt for file location
        default_name = f"{self._asset_name}_audit_history.csv".replace(" ", "_")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Audit History",
            default_name,
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        try:
            # Get data from audit service (full history, not filtered)
            data = self._db_service.audit.get_audit_log_for_export(
                asset_uuid=self._asset_uuid
            )

            # Write CSV
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Header
                writer.writerow([
                    'Timestamp', 'Action', 'Action Category', 'Actor', 'Actor Role',
                    'Actor Display Name', 'Asset UUID', 'Asset Name', 'Version',
                    'Variant', 'Source', 'Previous Value', 'New Value', 'Details'
                ])

                # Data rows
                for entry in data:
                    writer.writerow([
                        entry.get('timestamp', ''),
                        entry.get('action', ''),
                        entry.get('action_category', ''),
                        entry.get('actor', ''),
                        entry.get('actor_role', ''),
                        entry.get('actor_display_name', ''),
                        entry.get('asset_uuid', ''),
                        entry.get('asset_name', self._asset_name),
                        entry.get('version_label', ''),
                        entry.get('variant_name', ''),
                        entry.get('source', ''),
                        entry.get('previous_value', ''),
                        entry.get('new_value', ''),
                        entry.get('details', ''),
                    ])

            QMessageBox.information(
                self,
                "Export Complete",
                f"Exported {len(data)} entries to:\n{file_path}"
            )

        except Exception as e:
            QMessageBox.warning(
                self,
                "Export Failed",
                f"Failed to export audit history:\n{e}"
            )


def show_asset_history_dialog(asset_uuid: str, asset_name: str = "Asset", parent=None) -> bool:
    """
    Show asset history dialog if in Studio Mode.

    Args:
        asset_uuid: UUID of the asset
        asset_name: Display name of the asset
        parent: Parent widget

    Returns:
        True if dialog was shown, False if Studio Mode is disabled
    """
    user_service = get_user_service()
    if not user_service.is_studio_mode():
        QMessageBox.information(
            parent,
            "Studio Mode Required",
            "Asset audit history is only available in Studio Mode.\n\n"
            "Enable Studio Mode in Settings → Users to view audit trails."
        )
        return False

    dialog = AssetHistoryDialog(asset_uuid, asset_name, parent)
    dialog.exec()
    return True


__all__ = ['AssetHistoryDialog', 'show_asset_history_dialog']
