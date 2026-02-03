"""
TagsTab - Tag management settings tab

Pattern: QWidget tab for settings dialog
Provides CRUD operations for tags.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QLabel, QGroupBox, QColorDialog,
    QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QIcon, QPixmap

from ...services.database_service import get_database_service
from ...services.tag_repository import TagRepository


class TagsTab(QWidget):
    """
    Tag management tab for settings dialog

    Features:
    - View all tags with colors and usage counts
    - Create new tags
    - Edit tag names and colors
    - Delete tags (with confirmation)
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._db_service = get_database_service()

        self._create_ui()
        self._load_tags()

    def _create_ui(self):
        """Create UI layout"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header_label = QLabel("Manage Tags")
        header_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header_label)

        desc_label = QLabel(
            "Create, edit, and delete tags used to organize your assets."
        )
        desc_label.setStyleSheet("color: #808080;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Tags list
        list_group = QGroupBox("Tags")
        list_layout = QVBoxLayout(list_group)

        self._tag_list = QListWidget()
        self._tag_list.setIconSize(QSize(16, 16))
        self._tag_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._tag_list.itemDoubleClicked.connect(self._on_edit_tag)
        list_layout.addWidget(self._tag_list)

        layout.addWidget(list_group, 1)

        # Add new tag section
        add_group = QGroupBox("Add New Tag")
        add_layout = QHBoxLayout(add_group)

        self._new_tag_input = QLineEdit()
        self._new_tag_input.setPlaceholderText("Enter tag name...")
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
        actions_layout = QHBoxLayout()

        self._edit_btn = QPushButton("Edit Selected")
        self._edit_btn.clicked.connect(self._on_edit_selected)

        self._delete_btn = QPushButton("Delete Selected")
        self._delete_btn.clicked.connect(self._on_delete_selected)
        self._delete_btn.setStyleSheet("color: #c0392b;")

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._load_tags)

        actions_layout.addWidget(self._edit_btn)
        actions_layout.addWidget(self._delete_btn)
        actions_layout.addStretch()
        actions_layout.addWidget(self._refresh_btn)

        layout.addLayout(actions_layout)

    def _update_color_button(self):
        """Update the color button appearance"""
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

    def _load_tags(self):
        """Load tags from database"""
        self._tag_list.clear()

        tags = self._db_service.get_tags_with_counts()

        for tag in tags:
            tag_id = tag.get('id')
            tag_name = tag.get('name', 'Unknown')
            tag_color = tag.get('color', '#607D8B')
            count = tag.get('count', 0)

            item = QListWidgetItem(f"{tag_name} ({count} assets)")
            item.setData(Qt.ItemDataRole.UserRole, tag_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, tag_name)
            item.setData(Qt.ItemDataRole.UserRole + 2, tag_color)

            # Create color icon
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(tag_color))
            item.setIcon(QIcon(pixmap))

            self._tag_list.addItem(item)

        if not tags:
            item = QListWidgetItem("No tags yet. Create one above.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setForeground(QColor("#808080"))
            self._tag_list.addItem(item)

    def _on_choose_color(self):
        """Open color picker for new tag"""
        color = QColorDialog.getColor(
            QColor(self._current_color),
            self,
            "Choose Tag Color"
        )
        if color.isValid():
            self._current_color = color.name()
            self._update_color_button()

    def _on_add_tag(self):
        """Add a new tag"""
        name = self._new_tag_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a tag name.")
            return

        # Check if tag already exists
        existing = self._db_service.get_tag_by_name(name)
        if existing:
            QMessageBox.warning(
                self, "Tag Exists",
                f"A tag named '{name}' already exists."
            )
            return

        # Create the tag
        tag_id = self._db_service.create_tag(name, self._current_color)
        if tag_id:
            self._new_tag_input.clear()
            self._load_tags()
            # Cycle to next color from palette
            self._cycle_color()
        else:
            QMessageBox.critical(self, "Error", "Failed to create tag.")

    def _cycle_color(self):
        """Cycle to next default color"""
        colors = TagRepository.DEFAULT_COLORS
        try:
            idx = colors.index(self._current_color)
            self._current_color = colors[(idx + 1) % len(colors)]
        except ValueError:
            self._current_color = colors[0]
        self._update_color_button()

    def _on_edit_selected(self):
        """Edit the selected tag"""
        item = self._tag_list.currentItem()
        if not item or not item.data(Qt.ItemDataRole.UserRole):
            QMessageBox.information(self, "No Selection", "Please select a tag to edit.")
            return
        self._on_edit_tag(item)

    def _on_edit_tag(self, item: QListWidgetItem):
        """Edit a tag (name and color)"""
        tag_id = item.data(Qt.ItemDataRole.UserRole)
        tag_name = item.data(Qt.ItemDataRole.UserRole + 1)
        tag_color = item.data(Qt.ItemDataRole.UserRole + 2)

        if not tag_id:
            return

        # Ask for new name
        new_name, ok = QInputDialog.getText(
            self, "Edit Tag",
            "Enter new tag name:",
            text=tag_name
        )

        if not ok:
            return

        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Tag name cannot be empty.")
            return

        # Ask for new color
        color = QColorDialog.getColor(
            QColor(tag_color),
            self,
            f"Choose color for '{new_name}'"
        )

        new_color = color.name() if color.isValid() else tag_color

        # Update the tag
        if self._db_service.update_tag(tag_id, name=new_name, color=new_color):
            self._load_tags()
        else:
            QMessageBox.critical(self, "Error", "Failed to update tag.")

    def _on_delete_selected(self):
        """Delete the selected tag"""
        item = self._tag_list.currentItem()
        if not item or not item.data(Qt.ItemDataRole.UserRole):
            QMessageBox.information(self, "No Selection", "Please select a tag to delete.")
            return

        tag_id = item.data(Qt.ItemDataRole.UserRole)
        tag_name = item.data(Qt.ItemDataRole.UserRole + 1)

        # Confirm deletion
        reply = QMessageBox.question(
            self, "Delete Tag",
            f"Are you sure you want to delete the tag '{tag_name}'?\n\n"
            "This will remove the tag from all assets.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self._db_service.delete_tag(tag_id):
                self._load_tags()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete tag.")

    def save_settings(self):
        """Save settings (no-op for tags - saved immediately)"""
        pass


__all__ = ['TagsTab']
