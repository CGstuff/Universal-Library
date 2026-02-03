"""
AppearanceTab - Appearance settings tab

Pattern: QWidget for settings tab
Based on animation_library architecture.
"""

from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QComboBox, QSlider, QSpinBox, QCheckBox,
    QPushButton, QFrame, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QSettings

from ...config import Config
from ...themes import get_theme_manager


class AppearanceTab(QWidget):
    """
    Appearance settings tab

    Features:
    - Theme selection
    - Default view mode (grid/list)
    - Default card size
    - UI behavior options
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_manager = get_theme_manager()
        self._init_ui()
        self._load_settings()
        self._connect_signals()

    def _init_ui(self):
        """Initialize UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Theme Group
        theme_group = QGroupBox("Theme")
        theme_layout = QVBoxLayout(theme_group)

        # Theme selector row
        theme_row = QHBoxLayout()
        theme_label = QLabel("Theme:")
        theme_label.setFixedWidth(100)
        theme_row.addWidget(theme_label)

        self._theme_combo = QComboBox()
        self._theme_combo.setMinimumWidth(150)
        theme_row.addWidget(self._theme_combo)

        theme_row.addStretch()
        theme_layout.addLayout(theme_row)

        # Color preview (create before populating themes)
        preview_label = QLabel("Color Preview:")
        theme_layout.addWidget(preview_label)

        self._color_preview = self._create_color_preview()
        theme_layout.addWidget(self._color_preview)

        # Theme info label
        self._theme_info = QLabel()
        self._theme_info.setStyleSheet("font-style: italic; color: #808080;")
        theme_layout.addWidget(self._theme_info)

        # Theme management buttons
        btn_row1 = QHBoxLayout()
        self._customize_btn = QPushButton("Customize...")
        self._customize_btn.clicked.connect(self._on_customize_clicked)
        btn_row1.addWidget(self._customize_btn)

        self._import_btn = QPushButton("Import...")
        self._import_btn.clicked.connect(self._on_import_clicked)
        btn_row1.addWidget(self._import_btn)
        btn_row1.addStretch()
        theme_layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        self._export_btn = QPushButton("Export...")
        self._export_btn.clicked.connect(self._on_export_clicked)
        btn_row2.addWidget(self._export_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        btn_row2.addWidget(self._delete_btn)
        btn_row2.addStretch()
        theme_layout.addLayout(btn_row2)

        # Now populate themes (after all widgets are created)
        self._populate_themes()

        layout.addWidget(theme_group)

        # View Settings Group
        view_group = QGroupBox("View Settings")
        view_layout = QVBoxLayout(view_group)

        # Default view mode
        mode_row = QHBoxLayout()
        mode_label = QLabel("Default View:")
        mode_label.setFixedWidth(100)
        mode_row.addWidget(mode_label)

        self._view_mode_combo = QComboBox()
        self._view_mode_combo.addItem("Grid", "grid")
        self._view_mode_combo.addItem("List", "list")
        mode_row.addWidget(self._view_mode_combo)

        mode_row.addStretch()
        view_layout.addLayout(mode_row)

        # Default card size
        size_row = QHBoxLayout()
        size_label = QLabel("Card Size:")
        size_label.setFixedWidth(100)
        size_row.addWidget(size_label)

        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setMinimum(Config.MIN_CARD_SIZE)
        self._size_slider.setMaximum(Config.MAX_CARD_SIZE)
        self._size_slider.setValue(Config.DEFAULT_CARD_SIZE)
        self._size_slider.setSingleStep(Config.CARD_SIZE_STEP)
        self._size_slider.setFixedWidth(200)
        self._size_slider.valueChanged.connect(self._on_size_changed)
        size_row.addWidget(self._size_slider)

        self._size_value = QLabel(f"{Config.DEFAULT_CARD_SIZE}px")
        self._size_value.setFixedWidth(50)
        size_row.addWidget(self._size_value)

        size_row.addStretch()
        view_layout.addLayout(size_row)

        layout.addWidget(view_group)

        # Behavior Group
        behavior_group = QGroupBox("Behavior")
        behavior_layout = QVBoxLayout(behavior_group)

        # Remember window position
        self._remember_position = QCheckBox("Remember window position and size")
        self._remember_position.setChecked(True)
        behavior_layout.addWidget(self._remember_position)

        # Remember splitter sizes
        self._remember_splitter = QCheckBox("Remember panel sizes")
        self._remember_splitter.setChecked(True)
        behavior_layout.addWidget(self._remember_splitter)

        # Show tooltips
        self._show_tooltips = QCheckBox("Show tooltips")
        self._show_tooltips.setChecked(True)
        behavior_layout.addWidget(self._show_tooltips)

        layout.addWidget(behavior_group)

        # Performance Group
        perf_group = QGroupBox("Performance")
        perf_layout = QVBoxLayout(perf_group)

        # Thumbnail threads
        thread_row = QHBoxLayout()
        thread_label = QLabel("Thumbnail Threads:")
        thread_label.setFixedWidth(120)
        thread_row.addWidget(thread_label)

        self._thread_spin = QSpinBox()
        self._thread_spin.setMinimum(1)
        self._thread_spin.setMaximum(8)
        self._thread_spin.setValue(Config.THUMBNAIL_THREAD_COUNT)
        thread_row.addWidget(self._thread_spin)

        thread_note = QLabel("(More threads = faster loading, higher CPU usage)")
        thread_note.setStyleSheet("color: #808080;")
        thread_row.addWidget(thread_note)

        thread_row.addStretch()
        perf_layout.addLayout(thread_row)

        layout.addWidget(perf_group)

        layout.addStretch()

    def _create_color_preview(self) -> QWidget:
        """Create color preview widget with 6 color squares"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._color_squares = []
        for i in range(6):
            square = QFrame()
            square.setFixedSize(40, 40)
            square.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
            square.setLineWidth(1)
            self._color_squares.append(square)
            layout.addWidget(square)

        layout.addStretch()
        return widget

    def _update_theme_preview(self):
        """Update color preview and theme info for current theme"""
        current_theme = self._theme_manager.get_current_theme()
        if not current_theme:
            return

        palette = current_theme.palette

        # Update color squares (6 representative colors)
        colors = [
            palette.background,
            palette.text_primary,
            palette.accent,
            palette.header_gradient_start,
            palette.success,
            palette.error,
        ]

        for square, color in zip(self._color_squares, colors):
            square.setStyleSheet(f"background-color: {color}; border: 1px solid #666;")

        # Update theme info
        is_custom = not self._theme_manager.is_builtin_theme(current_theme.name)
        type_str = "Custom" if is_custom else "Built-in"
        self._theme_info.setText(f"{current_theme.name} ({type_str})")

        # Enable/disable delete button (only for custom themes)
        self._delete_btn.setEnabled(is_custom)

    def _populate_themes(self):
        """Populate theme dropdown from theme manager"""
        self._theme_combo.blockSignals(True)
        self._theme_combo.clear()

        current_theme = self._theme_manager.get_current_theme()
        current_name = current_theme.name if current_theme else "Dark"

        for theme in self._theme_manager.get_all_themes():
            self._theme_combo.addItem(theme.name, theme.name)

        # Select current theme
        index = self._theme_combo.findData(current_name)
        if index >= 0:
            self._theme_combo.setCurrentIndex(index)

        self._theme_combo.blockSignals(False)

        # Update preview
        self._update_theme_preview()

    def _connect_signals(self):
        """Connect signals"""
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self, index: int):
        """Handle theme selection change - apply immediately"""
        theme_name = self._theme_combo.currentData()
        if theme_name:
            try:
                self._theme_manager.set_theme(theme_name)
                self._update_theme_preview()
            except ValueError as e:
                pass

    def _on_customize_clicked(self):
        """Open theme editor dialog"""
        from .theme_editor_dialog import ThemeEditorDialog

        current_theme = self._theme_manager.get_current_theme()
        if not current_theme:
            QMessageBox.warning(self, "No Theme", "No theme selected.")
            return

        is_custom = not self._theme_manager.is_builtin_theme(current_theme.name)

        dialog = ThemeEditorDialog(
            current_theme,
            self._theme_manager,
            is_custom_theme=is_custom,
            parent=self
        )

        if dialog.exec():
            # Theme was saved, refresh list and select it
            saved_theme = dialog.get_theme()
            self._populate_themes()
            self._select_theme(saved_theme.name)

    def _on_import_clicked(self):
        """Import theme from JSON file"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Import Theme",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if not filepath:
            return

        if self._theme_manager.import_theme(Path(filepath)):
            QMessageBox.information(self, "Success", "Theme imported successfully.")
            self._populate_themes()
        else:
            QMessageBox.critical(self, "Error", "Failed to import theme.")

    def _on_export_clicked(self):
        """Export current theme to JSON file"""
        current_theme = self._theme_manager.get_current_theme()
        if not current_theme:
            QMessageBox.warning(self, "No Theme", "No theme selected.")
            return

        # Suggest filename
        suggested_name = current_theme.name.lower().replace(' ', '_') + '.json'

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Theme",
            suggested_name,
            "JSON Files (*.json);;All Files (*)"
        )

        if not filepath:
            return

        if self._theme_manager.export_theme(current_theme.name, Path(filepath)):
            QMessageBox.information(self, "Success", f"Theme exported to:\n{filepath}")
        else:
            QMessageBox.critical(self, "Error", "Failed to export theme.")

    def _on_delete_clicked(self):
        """Delete custom theme"""
        current_theme = self._theme_manager.get_current_theme()
        if not current_theme:
            return

        if self._theme_manager.is_builtin_theme(current_theme.name):
            QMessageBox.warning(self, "Cannot Delete", "Built-in themes cannot be deleted.")
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Theme",
            f"Are you sure you want to delete '{current_theme.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        if self._theme_manager.delete_custom_theme(current_theme.name):
            QMessageBox.information(self, "Success", "Theme deleted successfully.")
            # Switch to default theme
            self._theme_manager.set_theme("Dark")
            self._populate_themes()
        else:
            QMessageBox.critical(self, "Error", "Failed to delete theme.")

    def _select_theme(self, theme_name: str):
        """Select theme in dropdown"""
        index = self._theme_combo.findData(theme_name)
        if index >= 0:
            self._theme_combo.setCurrentIndex(index)

    def _on_size_changed(self, value: int):
        """Handle card size slider change"""
        self._size_value.setText(f"{value}px")

    def _load_settings(self):
        """Load settings from QSettings"""
        settings = QSettings(Config.APP_AUTHOR, Config.APP_NAME)

        # Theme is loaded by theme manager automatically

        # View mode
        view_mode = settings.value("appearance/view_mode", "grid")
        index = self._view_mode_combo.findData(view_mode)
        if index >= 0:
            self._view_mode_combo.setCurrentIndex(index)

        # Card size
        card_size = settings.value("appearance/card_size", Config.DEFAULT_CARD_SIZE, type=int)
        self._size_slider.setValue(card_size)

        # Behavior
        self._remember_position.setChecked(
            settings.value("appearance/remember_position", True, type=bool)
        )
        self._remember_splitter.setChecked(
            settings.value("appearance/remember_splitter", True, type=bool)
        )
        self._show_tooltips.setChecked(
            settings.value("appearance/show_tooltips", True, type=bool)
        )

        # Performance
        threads = settings.value("performance/thumbnail_threads", Config.THUMBNAIL_THREAD_COUNT, type=int)
        self._thread_spin.setValue(threads)

    def save_settings(self):
        """Save settings to QSettings"""
        settings = QSettings(Config.APP_AUTHOR, Config.APP_NAME)

        # Theme is saved by theme manager when changed

        # View mode
        settings.setValue("appearance/view_mode", self._view_mode_combo.currentData())

        # Card size
        settings.setValue("appearance/card_size", self._size_slider.value())

        # Behavior
        settings.setValue("appearance/remember_position", self._remember_position.isChecked())
        settings.setValue("appearance/remember_splitter", self._remember_splitter.isChecked())
        settings.setValue("appearance/show_tooltips", self._show_tooltips.isChecked())

        # Performance
        settings.setValue("performance/thumbnail_threads", self._thread_spin.value())


__all__ = ['AppearanceTab']
