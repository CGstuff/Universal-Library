"""
List view for version history dialog.

Simple table display of versions.
"""

from typing import Dict, List, Any

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from ....config import Config


class VersionListView:
    """
    Manages list view display for version history.

    Simple table with version, name, status, date, etc.
    """

    def __init__(self, table: QTableWidget):
        """
        Initialize list view manager.

        Args:
            table: QTableWidget to manage
        """
        self._table = table
        self._versions: List[Dict[str, Any]] = []

    def set_data(self, versions: List[Dict[str, Any]]):
        """Set the version data to display."""
        self._versions = versions

    def populate(self):
        """Populate table with version data."""
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._versions))

        status_colors = Config.LIFECYCLE_STATUSES

        for row, version in enumerate(self._versions):
            self._add_version_row(row, version, status_colors)

    def _add_version_row(
        self,
        row: int,
        version: Dict[str, Any],
        status_colors: Dict[str, Any]
    ):
        """Add a single version row to the table."""
        # Version label
        version_label = version.get('version_label', f"v{version.get('version', 1):03d}")
        version_item = QTableWidgetItem(version_label)
        version_item.setData(Qt.ItemDataRole.UserRole, version.get('uuid'))
        self._table.setItem(row, 0, version_item)

        # Name
        name_item = QTableWidgetItem(version.get('name', 'Unknown'))
        self._table.setItem(row, 1, name_item)

        # Status with color
        status = version.get('status', 'wip')
        status_info = status_colors.get(status, {'label': status.upper(), 'color': '#9E9E9E'})
        status_item = QTableWidgetItem(status_info['label'])
        status_item.setForeground(QBrush(QColor(status_info['color'])))
        self._table.setItem(row, 2, status_item)

        # Created date
        created = version.get('created_date', '')
        if created:
            if isinstance(created, str) and 'T' in created:
                created = created.replace('T', ' ').split('.')[0]
        created_item = QTableWidgetItem(str(created)[:19] if created else '-')
        self._table.setItem(row, 3, created_item)

        # Is Latest
        is_latest = version.get('is_latest', 0) == 1
        latest_item = QTableWidgetItem("Yes" if is_latest else "")
        if is_latest:
            latest_item.setForeground(QBrush(QColor("#4CAF50")))
        self._table.setItem(row, 4, latest_item)

        # Is Cold
        is_cold = version.get('is_cold', 0) == 1
        cold_item = QTableWidgetItem("Yes" if is_cold else "")
        if is_cold:
            cold_item.setForeground(QBrush(QColor("#2196F3")))
        self._table.setItem(row, 5, cold_item)

        # Is Locked
        is_locked = version.get('is_immutable', 0) == 1
        locked_item = QTableWidgetItem("Yes" if is_locked else "")
        if is_locked:
            locked_item.setForeground(QBrush(QColor("#FF9800")))
        self._table.setItem(row, 6, locked_item)

        # Highlight latest row
        if is_latest:
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(QBrush(QColor(76, 175, 80, 30)))


__all__ = ['VersionListView']
