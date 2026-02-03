"""
DynamicMetadataRenderer - Auto-generates UI from schema-defined metadata fields.

Reads field definitions from MetadataService and creates appropriate widgets
based on field type and UI hints. This enables adding new metadata fields
without modifying UI code.
"""

import json
from typing import Dict, Any, List, Optional, Callable
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox,
    QTextEdit, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt

from ....services.metadata_service import get_metadata_service


class DynamicFieldWidget(QWidget):
    """
    Widget for a single dynamic metadata field.

    Supports different field types and UI widgets:
    - string: QLineEdit or QTextEdit (multiline)
    - integer: QSpinBox
    - real: QDoubleSpinBox
    - boolean: QCheckBox
    - json: QTextEdit with JSON formatting
    """

    value_changed = pyqtSignal(str, object)  # field_name, new_value

    def __init__(
        self,
        field_def: Dict[str, Any],
        read_only: bool = True,
        parent=None
    ):
        super().__init__(parent)
        self._field_def = field_def
        self._field_name = field_def['field_name']
        self._field_type = field_def['field_type']
        self._ui_widget = field_def.get('ui_widget', 'text')
        self._read_only = read_only

        self._setup_ui()

    def _setup_ui(self):
        """Create the appropriate widget based on field type."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        # Label
        display_name = self._field_def.get('display_name', self._field_name)
        self._label = QLabel(f"{display_name}:")
        self._label.setMinimumWidth(100)
        self._label.setStyleSheet("color: #a0a0a0;")
        layout.addWidget(self._label)

        # Value widget based on type
        self._value_widget = self._create_value_widget()
        layout.addWidget(self._value_widget, 1)

    def _create_value_widget(self) -> QWidget:
        """Create the appropriate input widget."""
        if self._read_only:
            # Read-only mode: just use labels
            label = QLabel("-")
            label.setWordWrap(True)
            return label

        # Editable mode
        if self._field_type == 'boolean':
            widget = QCheckBox()
            widget.stateChanged.connect(self._on_checkbox_changed)
            return widget

        elif self._field_type == 'integer':
            widget = QSpinBox()
            widget.setRange(-999999, 999999)
            widget.valueChanged.connect(self._on_spinbox_changed)
            return widget

        elif self._field_type == 'real':
            widget = QDoubleSpinBox()
            widget.setRange(-999999.0, 999999.0)
            widget.setDecimals(2)
            widget.valueChanged.connect(self._on_doublespinbox_changed)
            return widget

        elif self._ui_widget == 'multiline' or self._field_type == 'json':
            widget = QTextEdit()
            widget.setMaximumHeight(80)
            widget.textChanged.connect(self._on_text_changed)
            return widget

        elif self._ui_widget == 'dropdown':
            widget = QComboBox()
            # TODO: Populate from validation_rules if available
            widget.currentTextChanged.connect(self._on_combo_changed)
            return widget

        else:
            # Default: single line text
            widget = QLineEdit()
            widget.textChanged.connect(self._on_line_changed)
            return widget

    def set_value(self, value: Any):
        """Set the displayed value."""
        if self._read_only:
            # Format value for display
            display_value = self._format_value(value)
            self._value_widget.setText(display_value)
        else:
            self._set_editable_value(value)

    def _format_value(self, value: Any) -> str:
        """Format value for read-only display."""
        if value is None:
            return "-"

        if self._field_type == 'boolean':
            return "Yes" if value else "No"

        if self._field_type == 'json':
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            if isinstance(value, list):
                return ", ".join(str(v) for v in value)
            if isinstance(value, dict):
                return json.dumps(value, indent=2)
            return str(value)

        if self._field_type == 'real':
            return f"{value:.2f}"

        if self._field_type == 'integer':
            # Format large numbers with commas
            return f"{value:,}" if isinstance(value, int) else str(value)

        return str(value) if value else "-"

    def _set_editable_value(self, value: Any):
        """Set value on editable widget."""
        if self._field_type == 'boolean':
            self._value_widget.setChecked(bool(value))
        elif self._field_type == 'integer':
            self._value_widget.setValue(int(value) if value else 0)
        elif self._field_type == 'real':
            self._value_widget.setValue(float(value) if value else 0.0)
        elif isinstance(self._value_widget, QTextEdit):
            if self._field_type == 'json' and not isinstance(value, str):
                value = json.dumps(value, indent=2)
            self._value_widget.setPlainText(str(value) if value else "")
        elif isinstance(self._value_widget, QComboBox):
            self._value_widget.setCurrentText(str(value) if value else "")
        elif isinstance(self._value_widget, QLineEdit):
            self._value_widget.setText(str(value) if value else "")

    def get_value(self) -> Any:
        """Get the current value."""
        if self._read_only:
            return None

        if self._field_type == 'boolean':
            return self._value_widget.isChecked()
        elif self._field_type == 'integer':
            return self._value_widget.value()
        elif self._field_type == 'real':
            return self._value_widget.value()
        elif isinstance(self._value_widget, QTextEdit):
            text = self._value_widget.toPlainText()
            if self._field_type == 'json':
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
            return text
        elif isinstance(self._value_widget, QComboBox):
            return self._value_widget.currentText()
        elif isinstance(self._value_widget, QLineEdit):
            return self._value_widget.text()

        return None

    # Signal handlers for editable mode
    def _on_checkbox_changed(self, state):
        self.value_changed.emit(self._field_name, self._value_widget.isChecked())

    def _on_spinbox_changed(self, value):
        self.value_changed.emit(self._field_name, value)

    def _on_doublespinbox_changed(self, value):
        self.value_changed.emit(self._field_name, value)

    def _on_text_changed(self):
        self.value_changed.emit(self._field_name, self.get_value())

    def _on_combo_changed(self, text):
        self.value_changed.emit(self._field_name, text)

    def _on_line_changed(self, text):
        self.value_changed.emit(self._field_name, text)

    def clear(self):
        """Clear the displayed value."""
        if self._read_only:
            self._value_widget.setText("-")
        else:
            self._set_editable_value(None)


class DynamicMetadataRenderer(QWidget):
    """
    Auto-generates metadata UI from database field definitions.

    Features:
    - Reads field definitions from MetadataService
    - Groups fields by category
    - Creates appropriate widgets based on field type
    - Supports read-only and editable modes
    - Only shows fields that have values (in read-only mode)

    Usage:
        renderer = DynamicMetadataRenderer('asset')
        renderer.render(asset_data, category='rig')

        # Or render all categories
        renderer.render(asset_data)
    """

    # Emitted when a field value changes (in editable mode)
    field_changed = pyqtSignal(str, str, object)  # entity_uuid, field_name, new_value

    def __init__(
        self,
        entity_type: str = 'asset',
        read_only: bool = True,
        show_empty: bool = False,
        parent=None
    ):
        """
        Initialize dynamic renderer.

        Args:
            entity_type: Entity type to get field definitions for
            read_only: If True, show values as labels; if False, show editable widgets
            show_empty: If True, show fields even when empty
            parent: Parent widget
        """
        super().__init__(parent)
        self._entity_type = entity_type
        self._read_only = read_only
        self._show_empty = show_empty
        self._metadata_service = get_metadata_service()

        self._current_uuid: Optional[str] = None
        self._field_widgets: Dict[str, DynamicFieldWidget] = {}
        self._category_groups: Dict[str, QGroupBox] = {}

        self._setup_ui()

    def _setup_ui(self):
        """Setup the container layout."""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

    def _ensure_category_group(self, category: str) -> QGroupBox:
        """Get or create a group box for a category."""
        if category not in self._category_groups:
            # Format category name for display
            display_name = category.replace('_', ' ').title()
            group = QGroupBox(f"{display_name} Info")
            group_layout = QVBoxLayout(group)
            group_layout.setSpacing(4)
            group.hide()  # Hidden until fields are added

            self._category_groups[category] = group
            self._layout.addWidget(group)

        return self._category_groups[category]

    def _ensure_field_widget(self, field_def: Dict[str, Any]) -> DynamicFieldWidget:
        """Get or create a widget for a field."""
        field_name = field_def['field_name']

        if field_name not in self._field_widgets:
            widget = DynamicFieldWidget(field_def, self._read_only)

            if not self._read_only:
                widget.value_changed.connect(self._on_field_changed)

            # Add to category group
            category = field_def.get('category', 'general')
            group = self._ensure_category_group(category)
            group.layout().addWidget(widget)

            self._field_widgets[field_name] = widget

        return self._field_widgets[field_name]

    def render(
        self,
        entity_data: Dict[str, Any],
        category: Optional[str] = None,
        entity_uuid: Optional[str] = None
    ):
        """
        Render metadata fields for an entity.

        Args:
            entity_data: Entity data dict with field values
            category: Optional category filter (e.g., 'rig', 'animation')
            entity_uuid: Entity UUID (for editable mode signals)
        """
        self._current_uuid = entity_uuid or entity_data.get('uuid')

        # Get field definitions
        fields = self._metadata_service.get_fields_for_type(
            self._entity_type,
            category=category
        )

        # Hide all groups first
        for group in self._category_groups.values():
            group.hide()

        # Render each field
        visible_categories = set()

        for field_def in fields:
            field_name = field_def['field_name']
            value = entity_data.get(field_name)

            # Skip empty values in read-only mode unless show_empty is True
            if self._read_only and not self._show_empty:
                if value is None or value == '' or value == 0:
                    # Hide widget if it exists
                    if field_name in self._field_widgets:
                        self._field_widgets[field_name].hide()
                    continue

            # Create/update widget
            widget = self._ensure_field_widget(field_def)
            widget.set_value(value)
            widget.show()

            # Track visible categories
            field_category = field_def.get('category', 'general')
            visible_categories.add(field_category)

        # Show categories that have visible fields
        for cat_name in visible_categories:
            if cat_name in self._category_groups:
                self._category_groups[cat_name].show()

    def render_category(
        self,
        entity_data: Dict[str, Any],
        category: str,
        entity_uuid: Optional[str] = None
    ):
        """
        Render a specific category of metadata.

        Args:
            entity_data: Entity data dict
            category: Category to render ('rig', 'animation', 'material', etc.)
            entity_uuid: Entity UUID
        """
        self.render(entity_data, category=category, entity_uuid=entity_uuid)

    def get_values(self) -> Dict[str, Any]:
        """
        Get all current field values (for editable mode).

        Returns:
            Dict of field_name -> value
        """
        values = {}
        for field_name, widget in self._field_widgets.items():
            value = widget.get_value()
            if value is not None:
                values[field_name] = value
        return values

    def clear(self):
        """Clear all field displays."""
        self._current_uuid = None
        for widget in self._field_widgets.values():
            widget.clear()
            widget.hide()
        for group in self._category_groups.values():
            group.hide()

    def _on_field_changed(self, field_name: str, value: Any):
        """Handle field value change in editable mode."""
        if self._current_uuid:
            self.field_changed.emit(self._current_uuid, field_name, value)

    def refresh_fields(self):
        """
        Refresh field definitions from database.

        Call this after registering new fields to update the UI.
        """
        # Clear existing widgets
        for widget in self._field_widgets.values():
            widget.deleteLater()
        self._field_widgets.clear()

        for group in self._category_groups.values():
            group.deleteLater()
        self._category_groups.clear()


class DynamicTechnicalInfoRenderer:
    """
    Drop-in replacement for TechnicalInfoRenderer that uses dynamic fields.

    This adapter allows using DynamicMetadataRenderer where TechnicalInfoRenderer
    was used, providing backward compatibility while enabling dynamic fields.
    """

    # Category mapping from asset_type to metadata category
    CATEGORY_MAP = {
        'mesh': 'mesh',
        'material': 'material',
        'rig': 'rig',
        'animation': 'animation',
        'light': 'light',
        'camera': 'camera',
        'collection': 'collection',
    }

    def __init__(self, container: QWidget = None):
        """
        Initialize the dynamic technical info renderer.

        Args:
            container: Parent widget to add the dynamic renderer to
        """
        self._renderer = DynamicMetadataRenderer(
            entity_type='asset',
            read_only=True,
            show_empty=False
        )

        if container:
            if container.layout():
                container.layout().addWidget(self._renderer)
            else:
                layout = QVBoxLayout(container)
                layout.addWidget(self._renderer)

    @property
    def widget(self) -> QWidget:
        """Get the renderer widget."""
        return self._renderer

    def render(self, asset: Dict[str, Any], category: str):
        """
        Render technical info for an asset.

        Args:
            asset: Asset data dict
            category: Asset category (mesh, rig, animation, etc.)
        """
        # Map category if needed
        metadata_category = self.CATEGORY_MAP.get(category, category)

        self._renderer.render(
            asset,
            category=metadata_category,
            entity_uuid=asset.get('uuid')
        )

    def clear(self):
        """Clear the display."""
        self._renderer.clear()


__all__ = [
    'DynamicFieldWidget',
    'DynamicMetadataRenderer',
    'DynamicTechnicalInfoRenderer',
]
