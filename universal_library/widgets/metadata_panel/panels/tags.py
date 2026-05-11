"""
TagsWidget - Tag assignment for assets via checkbox tree popup.

Click "+ Add Tags" to open a popup showing the tag hierarchy as a
collapsible tree with checkboxes. Tags display as full dot-paths
(e.g. Tree.Deciduous.Oak) on the asset.
"""

import json
from typing import List, Dict, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QSizePolicy, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt, QPoint
from PyQt6.QtGui import QColor, QIcon, QPixmap


class _TagTreePopup(QFrame):
    """
    Popup with a searchable, collapsible checkbox tree of tags.
    Starts collapsed — user expands categories they care about.
    """

    tag_toggled = pyqtSignal(int, bool)  # tag_id, checked

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            _TagTreePopup {
                background-color: #2a2a2e;
                border: 1px solid #555;
            }
        """)
        self.setMinimumWidth(320)
        self.setMaximumHeight(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Search filter
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Search tags…")
        self._filter.setFixedHeight(26)
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._on_filter)
        layout.addWidget(self._filter)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setAnimated(False)
        self._tree.setIndentation(18)
        self._tree.setStyleSheet("""
            QTreeWidget {
                background-color: #2a2a2e;
                border: none;
                outline: none;
            }
            QTreeWidget::item {
                padding: 2px 0;
            }
            QTreeWidget::item:hover {
                background-color: #353538;
            }
        """)
        self._tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._tree, 1)

        self._updating = False

    def populate(self, tree_data: List[Dict], assigned_ids: set):
        """Fill tree from tag hierarchy. Starts collapsed."""
        self._updating = True
        self._tree.clear()

        def add_nodes(parent_widget, nodes):
            for node in nodes:
                item = QTreeWidgetItem(parent_widget)
                item.setText(0, node['name'])
                item.setData(0, Qt.ItemDataRole.UserRole, node['id'])
                item.setData(0, Qt.ItemDataRole.UserRole + 1,
                             node.get('full_path', node['name']))

                # Tooltip shows full path
                item.setToolTip(0, node.get('full_path', node['name']))

                # Color dot
                color = node.get('color', '#607D8B')
                px = QPixmap(12, 12)
                px.fill(QColor(color))
                item.setIcon(0, QIcon(px))

                # Checkbox
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                checked = node['id'] in assigned_ids
                item.setCheckState(
                    0,
                    Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked,
                )

                if node.get('children'):
                    add_nodes(item, node['children'])

        add_nodes(self._tree, tree_data)

        # Start collapsed — user expands what they need
        self._tree.collapseAll()

        # But expand nodes that have checked children (so assigned tags are visible)
        self._expand_checked(self._tree.invisibleRootItem())

        self._updating = False
        self._filter.clear()

    def _expand_checked(self, item: QTreeWidgetItem) -> bool:
        """Expand parent nodes that contain checked children. Returns True if any checked."""
        has_checked = False

        for i in range(item.childCount()):
            child = item.child(i)
            child_checked = child.checkState(0) == Qt.CheckState.Checked
            descendant_checked = self._expand_checked(child)

            if child_checked or descendant_checked:
                has_checked = True

        if has_checked and item is not self._tree.invisibleRootItem():
            item.setExpanded(True)

        return has_checked

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if self._updating:
            return
        tag_id = item.data(0, Qt.ItemDataRole.UserRole)
        if tag_id is None:
            return
        checked = item.checkState(0) == Qt.CheckState.Checked
        self.tag_toggled.emit(tag_id, checked)

    def _on_filter(self, text: str):
        """Show items matching the query + their parent chain."""
        query = text.strip().lower()

        def filter_item(item: QTreeWidgetItem) -> bool:
            name = item.text(0).lower()
            path = (item.data(0, Qt.ItemDataRole.UserRole + 1) or '').lower()
            self_match = query in name or query in path

            child_match = False
            for i in range(item.childCount()):
                if filter_item(item.child(i)):
                    child_match = True

            visible = self_match or child_match or not query
            item.setHidden(not visible)

            if (child_match or self_match) and query:
                item.setExpanded(True)

            return visible

        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            filter_item(root.child(i))

    def showAt(self, global_pos: QPoint):
        self.show()
        self.move(global_pos)
        self._filter.setFocus()


class TagsWidget(QWidget):
    """
    Asset tag management widget.

    Displays assigned tags as full dot-path pills (e.g. Tree.Deciduous.Oak).
    "+ Add Tags" opens a collapsible checkbox tree for quick assignment.

    Signals:
        tag_added(uuid, tag_id)
        tag_removed(uuid, tag_id)
        tags_changed(uuid, [tag_ids])
    """

    tag_added = pyqtSignal(str, int)
    tag_removed = pyqtSignal(str, int)
    tags_changed = pyqtSignal(str, list)

    def __init__(self, db_service, parent=None):
        super().__init__(parent)
        self._db_service = db_service
        self._current_uuid: Optional[str] = None
        self._current_tag_ids: List[int] = []
        self._popup: Optional[_TagTreePopup] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._group = QGroupBox("Tags")
        group_layout = QVBoxLayout(self._group)
        group_layout.setSpacing(4)

        # Pills container
        self._pills_widget = QWidget()
        self._pills_layout = QVBoxLayout(self._pills_widget)
        self._pills_layout.setContentsMargins(0, 0, 0, 0)
        self._pills_layout.setSpacing(2)
        group_layout.addWidget(self._pills_widget)

        # Add Tags button
        self._add_btn = QPushButton("+ Add Tags")
        self._add_btn.setFixedHeight(26)
        self._add_btn.setStyleSheet("""
            QPushButton {
                background-color: #333;
                border: 1px dashed #555;
                color: #999;
                font-size: 11px;
            }
            QPushButton:hover {
                border-color: #888;
                color: #ccc;
            }
        """)
        self._add_btn.clicked.connect(self._on_add_clicked)
        group_layout.addWidget(self._add_btn)

        layout.addWidget(self._group)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_asset(self, uuid: str):
        """Set current asset and refresh pills."""
        self._current_uuid = uuid
        tags_v2 = self._db_service.get_asset_tags(uuid)
        self._rebuild_pills(tags_v2)

    def clear(self):
        self._current_uuid = None
        self._current_tag_ids = []
        self._rebuild_pills(None)

    @property
    def current_tag_ids(self) -> List[int]:
        return self._current_tag_ids.copy()

    # ------------------------------------------------------------------
    # Popup
    # ------------------------------------------------------------------

    def _on_add_clicked(self):
        if not self._current_uuid:
            return

        tree_data = self._db_service.get_tag_tree()
        if not tree_data:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "No Tags",
                "No tags exist yet.\n"
                "Create tags in Settings → Tags first.",
            )
            return

        self._popup = _TagTreePopup(self)
        self._popup.tag_toggled.connect(self._on_tag_toggled)
        self._popup.populate(tree_data, set(self._current_tag_ids))

        pos = self._add_btn.mapToGlobal(QPoint(0, self._add_btn.height()))
        self._popup.showAt(pos)

    def _on_tag_toggled(self, tag_id: int, checked: bool):
        if not self._current_uuid:
            return

        if checked and tag_id not in self._current_tag_ids:
            self._db_service.add_tag_to_asset(self._current_uuid, tag_id)
            self._current_tag_ids.append(tag_id)
            self.tag_added.emit(self._current_uuid, tag_id)
        elif not checked and tag_id in self._current_tag_ids:
            self._db_service.remove_tag_from_asset(self._current_uuid, tag_id)
            self._current_tag_ids.remove(tag_id)
            self.tag_removed.emit(self._current_uuid, tag_id)

        # Refresh pills
        tags_v2 = self._db_service.get_asset_tags(self._current_uuid)
        self._rebuild_pills(tags_v2)
        self.tags_changed.emit(self._current_uuid, self._current_tag_ids.copy())

    # ------------------------------------------------------------------
    # Pill display
    # ------------------------------------------------------------------

    def _rebuild_pills(self, tags_data):
        """Rebuild the pill display from tag data."""
        # Clear old pills
        self._clear_pills_layout()
        self._current_tag_ids = []

        # v2 format: list of dicts with full_path
        if isinstance(tags_data, list) and tags_data and isinstance(tags_data[0], dict):
            row = self._new_pill_row()
            row_width = 0
            max_width = max(self._pills_widget.width() - 8, 240)

            for tag in tags_data[:30]:
                tag_id = tag.get('id')
                full_path = tag.get('full_path', tag.get('name', '?'))
                tag_color = tag.get('color', '#607D8B')
                self._current_tag_ids.append(tag_id)

                pill = self._make_pill(full_path, tag_color, tag_id)
                pill_width = pill.sizeHint().width()

                # Wrap to next row if needed
                if row_width > 0 and row_width + pill_width + 4 > max_width:
                    row.addStretch()
                    row = self._new_pill_row()
                    row_width = 0

                row.addWidget(pill)
                row_width += pill_width + 4

            row.addStretch()
            return

        # Empty state
        lbl = QLabel("No tags assigned")
        lbl.setStyleSheet("color: #555; font-size: 11px; padding: 2px;")
        self._pills_layout.addWidget(lbl)

    def _new_pill_row(self) -> QHBoxLayout:
        """Add a new horizontal row to the pills layout and return it."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self._pills_layout.addLayout(row)
        return row

    def _make_pill(self, full_path: str, color: str, tag_id: int) -> QPushButton:
        """Colored pill showing the full dot path. Click to remove."""
        pill = QPushButton(f"{full_path}  ×")
        pill.setToolTip(f"Click to remove: {full_path}")
        pill.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        pill.setCursor(Qt.CursorShape.PointingHandCursor)
        pill.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                padding: 2px 8px;
                border: none;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #c0392b;
            }}
        """)
        pill.clicked.connect(lambda: self._on_remove_tag(tag_id))
        return pill

    def _on_remove_tag(self, tag_id: int):
        if not self._current_uuid:
            return
        if self._db_service.remove_tag_from_asset(self._current_uuid, tag_id):
            if tag_id in self._current_tag_ids:
                self._current_tag_ids.remove(tag_id)
            tags_v2 = self._db_service.get_asset_tags(self._current_uuid)
            self._rebuild_pills(tags_v2)
            self.tag_removed.emit(self._current_uuid, tag_id)
            self.tags_changed.emit(self._current_uuid, self._current_tag_ids.copy())

    def _clear_pills_layout(self):
        """Remove all widgets and sub-layouts from the pills layout."""
        while self._pills_layout.count():
            item = self._pills_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    child = sub.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()


__all__ = ['TagsWidget']
