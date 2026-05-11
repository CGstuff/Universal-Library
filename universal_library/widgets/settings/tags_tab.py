"""
TagsTab - Hierarchical tag management settings tab.

Tree view for browsing/editing the tag hierarchy.
Supports creating tags via dot-separated paths, adding children,
renaming, recoloring, and deleting.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLineEdit, QLabel, QGroupBox, QColorDialog,
    QMessageBox, QInputDialog, QHeaderView
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QIcon, QPixmap

from ...services.database_service import get_database_service
from ...services.tag_repository import TagRepository


class TagsTab(QWidget):
    """
    Hierarchical tag management tab for settings dialog.

    Features:
    - Tree view of tag hierarchy
    - Create tags via dot-separated path (auto-creates parents)
    - Add child tags on selected parent
    - Edit tag name and color
    - Delete tag and descendants
    - Usage counts per tag
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db_service = get_database_service()
        self._create_ui()
        self._load_tags()

    def _create_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("Manage Tags")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "Tags are hierarchical (e.g. Vegetation.Tree.Oak). "
            "Type a dot-separated path to auto-create the full chain."
        )
        desc.setStyleSheet("color: #808080;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Tree view
        tree_group = QGroupBox("Tag Hierarchy")
        tree_layout = QVBoxLayout(tree_group)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Tag", "Assets", "Path"])
        self._tree.setColumnCount(3)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.itemDoubleClicked.connect(self._on_edit_tag)

        header_view = self._tree.header()
        header_view.setStretchLastSection(True)
        header_view.resizeSection(0, 200)
        header_view.resizeSection(1, 60)

        tree_layout.addWidget(self._tree)
        layout.addWidget(tree_group, 1)

        # Add new tag section
        add_group = QGroupBox("Add Tag")
        add_layout = QHBoxLayout(add_group)

        self._new_tag_input = QLineEdit()
        self._new_tag_input.setPlaceholderText("e.g. Vegetation.Tree.Oak or just Oak")
        self._new_tag_input.returnPressed.connect(self._on_add_tag)

        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(32, 32)
        self._color_btn.setToolTip("Click to choose color")
        self._current_color = "#607D8B"
        self._update_color_button()
        self._color_btn.clicked.connect(self._on_choose_color)

        self._add_btn = QPushButton("Add")
        self._add_btn.clicked.connect(self._on_add_tag)

        add_layout.addWidget(self._new_tag_input, 1)
        add_layout.addWidget(self._color_btn)
        add_layout.addWidget(self._add_btn)
        layout.addWidget(add_group)

        # Action buttons
        actions = QHBoxLayout()

        self._add_child_btn = QPushButton("Add Child")
        self._add_child_btn.setToolTip("Add a child tag under selected")
        self._add_child_btn.clicked.connect(self._on_add_child)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.clicked.connect(self._on_edit_selected)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setStyleSheet("color: #c0392b;")
        self._delete_btn.clicked.connect(self._on_delete_selected)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._load_tags)

        actions.addWidget(self._add_child_btn)
        actions.addWidget(self._edit_btn)
        actions.addWidget(self._delete_btn)
        actions.addStretch()
        actions.addWidget(self._refresh_btn)
        layout.addLayout(actions)

    def _update_color_button(self):
        pixmap = QPixmap(24, 24)
        pixmap.fill(QColor(self._current_color))
        self._color_btn.setIcon(QIcon(pixmap))
        self._color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._current_color};
                border: 1px solid #404040;
                border-radius: 0px;
            }}
        """)

    def _make_color_icon(self, color: str) -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(color))
        return QIcon(pixmap)

    def _load_tags(self):
        self._tree.clear()
        usage = self._db_service.get_tags_with_counts()
        count_map = {t['id']: t.get('count', 0) for t in usage}

        tree_data = self._db_service.get_tag_tree()
        if not tree_data:
            placeholder = QTreeWidgetItem(self._tree, ["No tags yet"])
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            placeholder.setForeground(0, QColor("#808080"))
            return

        def populate(parent_widget, nodes):
            for node in nodes:
                count = count_map.get(node['id'], 0)
                item = QTreeWidgetItem(parent_widget, [
                    node['name'],
                    str(count) if count > 0 else "",
                    node.get('full_path', node['name'])
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, node['id'])
                item.setData(0, Qt.ItemDataRole.UserRole + 1, node.get('color', '#607D8B'))
                item.setIcon(0, self._make_color_icon(node.get('color', '#607D8B')))

                if node.get('children'):
                    populate(item, node['children'])

        populate(self._tree, tree_data)
        self._tree.expandAll()

    def _on_choose_color(self):
        color = QColorDialog.getColor(QColor(self._current_color), self, "Choose Tag Color")
        if color.isValid():
            self._current_color = color.name()
            self._update_color_button()

    def _on_add_tag(self):
        text = self._new_tag_input.text().strip()
        if not text:
            QMessageBox.warning(self, "Invalid", "Please enter a tag name or path.")
            return

        # Check if path already exists
        existing = self._db_service.get_tag_by_path(text)
        if existing:
            QMessageBox.warning(self, "Exists", f"Tag '{text}' already exists.")
            return

        tag_id = self._db_service.create_tag_from_path(text, self._current_color)
        if tag_id:
            self._new_tag_input.clear()
            self._load_tags()
            self._cycle_color()
        else:
            QMessageBox.critical(self, "Error", "Failed to create tag.")

    def _on_add_child(self):
        item = self._tree.currentItem()
        if not item or item.data(0, Qt.ItemDataRole.UserRole) is None:
            QMessageBox.information(self, "No Selection", "Select a parent tag first.")
            return

        parent_id = item.data(0, Qt.ItemDataRole.UserRole)
        parent_path = item.text(2)

        name, ok = QInputDialog.getText(
            self, "Add Child Tag",
            f"New child tag under '{parent_path}':"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        # If they typed dots, create the sub-chain
        if '.' in name:
            full_path = f"{parent_path}.{name}"
            tag_id = self._db_service.create_tag_from_path(full_path, self._current_color)
        else:
            tag_id = self._db_service.create_tag(name, self._current_color, parent_id)

        if tag_id:
            self._load_tags()
            self._cycle_color()
        else:
            QMessageBox.critical(self, "Error", "Failed to create child tag.")

    def _on_edit_selected(self):
        item = self._tree.currentItem()
        if not item or item.data(0, Qt.ItemDataRole.UserRole) is None:
            QMessageBox.information(self, "No Selection", "Select a tag to edit.")
            return
        self._on_edit_tag(item, 0)

    def _on_edit_tag(self, item: QTreeWidgetItem, column: int = 0):
        tag_id = item.data(0, Qt.ItemDataRole.UserRole)
        if tag_id is None:
            return

        tag_name = item.text(0)
        tag_color = item.data(0, Qt.ItemDataRole.UserRole + 1) or '#607D8B'

        new_name, ok = QInputDialog.getText(
            self, "Edit Tag", "Tag name (leaf only, not full path):", text=tag_name
        )
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid", "Tag name cannot be empty.")
            return

        color = QColorDialog.getColor(QColor(tag_color), self, f"Color for '{new_name}'")
        new_color = color.name() if color.isValid() else tag_color

        if self._db_service.update_tag(tag_id, name=new_name, color=new_color):
            self._load_tags()
        else:
            QMessageBox.critical(self, "Error", "Failed to update tag.")

    def _on_delete_selected(self):
        item = self._tree.currentItem()
        if not item or item.data(0, Qt.ItemDataRole.UserRole) is None:
            QMessageBox.information(self, "No Selection", "Select a tag to delete.")
            return

        tag_id = item.data(0, Qt.ItemDataRole.UserRole)
        tag_path = item.text(2)
        has_children = item.childCount() > 0

        msg = f"Delete tag '{tag_path}'?"
        if has_children:
            msg += "\n\nThis will also delete all child tags."
        msg += "\n\nThe tag will be removed from all assets."

        reply = QMessageBox.question(
            self, "Delete Tag", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self._db_service.delete_tag(tag_id):
                self._load_tags()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete tag.")

    def _cycle_color(self):
        colors = TagRepository.DEFAULT_COLORS
        try:
            idx = colors.index(self._current_color)
            self._current_color = colors[(idx + 1) % len(colors)]
        except ValueError:
            self._current_color = colors[0]
        self._update_color_button()

    def save_settings(self):
        """No-op — tags are saved immediately."""
        pass


__all__ = ['TagsTab']
