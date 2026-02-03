"""
CreateVariantDialog - Dialog for creating a new variant from a base version

Pattern: QDialog for variant creation with VariantSet selection
Extracted from version_history_dialog.py for modularity
"""

from typing import List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QMessageBox
)


class CreateVariantDialog(QDialog):
    """Dialog for creating a new variant with VariantSet selection"""

    # Common VariantSet presets
    VARIANT_SET_PRESETS = ["Default", "Armor", "Color", "LOD", "Damage", "Material", "Season"]

    def __init__(
        self,
        source_name: str,
        source_version: str,
        existing_variants: List[str],
        existing_variant_sets: List[str],
        parent=None
    ):
        super().__init__(parent)

        self._source_name = source_name
        self._source_version = source_version
        self._existing_variants = existing_variants
        self._existing_variant_sets = existing_variant_sets or []

        self.setWindowTitle("Create New Variant")
        self.setModal(True)
        self.resize(400, 200)

        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel(f"Create new variant from <b>{self._source_name} {self._source_version}</b>")
        header.setWordWrap(True)
        layout.addWidget(header)

        # VariantSet selection
        variant_set_layout = QHBoxLayout()
        variant_set_layout.addWidget(QLabel("VariantSet:"))

        self._variant_set_combo = QComboBox()
        self._variant_set_combo.setEditable(True)
        self._variant_set_combo.setMinimumWidth(150)

        # Populate with existing variant sets first, then presets
        all_sets = set(self._existing_variant_sets)
        all_sets.update(self.VARIANT_SET_PRESETS)
        for vs in sorted(all_sets):
            self._variant_set_combo.addItem(vs)

        # Default to "Default" if available
        idx = self._variant_set_combo.findText("Default")
        if idx >= 0:
            self._variant_set_combo.setCurrentIndex(idx)

        variant_set_layout.addWidget(self._variant_set_combo, 1)
        layout.addLayout(variant_set_layout)

        # Variant name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Variant Name:"))

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g., Heavy_Armor, Damaged, Red")
        name_layout.addWidget(self._name_edit, 1)
        layout.addLayout(name_layout)

        # Hint
        hint = QLabel("Spaces will be replaced with underscores")
        hint.setStyleSheet("color: #808080; font-size: 11px;")
        layout.addWidget(hint)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self._create_btn = QPushButton("Create Variant")
        self._create_btn.setDefault(True)
        self._create_btn.clicked.connect(self._on_create_clicked)
        self._create_btn.setStyleSheet("background-color: #0078d4; color: white;")
        button_layout.addWidget(self._create_btn)

        layout.addLayout(button_layout)

    def _on_create_clicked(self):
        """Handle create button click"""
        name = self._name_edit.text().strip().replace(" ", "_")

        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a variant name.")
            return

        if name in self._existing_variants:
            QMessageBox.warning(
                self,
                "Variant Exists",
                f"A variant named '{name}' already exists."
            )
            return

        if name == "Base":
            QMessageBox.warning(
                self,
                "Reserved Name",
                "'Base' is reserved and cannot be used as a variant name."
            )
            return

        self.accept()

    def get_variant_name(self) -> str:
        """Get the entered variant name"""
        return self._name_edit.text().strip().replace(" ", "_")

    def get_variant_set(self) -> str:
        """Get the selected variant set"""
        return self._variant_set_combo.currentText().strip() or "Default"


__all__ = ['CreateVariantDialog']
