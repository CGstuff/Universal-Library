"""
DarkTheme - Dark theme implementation

Pattern: Theme subclass with stylesheet generation
Based on animation_library architecture.
"""

from .theme_manager import Theme, ColorPalette


class DarkTheme(Theme):
    """Dark theme with professional color palette"""

    def __init__(self):
        palette = ColorPalette(
            # Background colors
            background="#1e1e1e",
            background_secondary="#2d2d2d",

            # Text colors
            text_primary="#e0e0e0",
            text_secondary="#a0a0a0",
            text_disabled="#606060",

            # Accent colors (blue)
            accent="#0078d4",
            accent_hover="#1084d8",
            accent_pressed="#006cc1",

            # Card colors
            card_background="#2d2d2d",
            card_border="#404040",
            card_selected="#0078d4",

            # Button colors
            button_background="#3d3d3d",
            button_hover="#4d4d4d",
            button_pressed="#2d2d2d",
            button_disabled="#252525",

            # Status colors
            error="#ff6b6b",
            warning="#ffa500",
            success="#4CAF50",

            # Border/Divider colors
            border="#404040",
            divider="#353535",

            # Header gradient (blue/teal for USD theme)
            header_gradient_start="#1a5276",
            header_gradient_end="#2874a6",
            header_icon_color="#ffffff",

            # List item colors (for dropdowns, lists, menus)
            list_item_background="#3A3A3A",
            list_item_hover="#4A4A4A",
            list_item_selected="#0078d4",
            selection_border="#0078d4",
        )

        super().__init__("Dark", palette, is_dark=True)

    def get_stylesheet(self) -> str:
        """Generate QSS stylesheet for dark theme"""
        p = self.palette

        return f"""
/* ===== GLOBAL STYLES ===== */
QWidget {{
    background-color: {p.background};
    color: {p.text_primary};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {p.background};
}}

/* ===== HEADER TOOLBAR ===== */
/* Gradient header to visually separate from content */
QWidget[header="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {p.header_gradient_start},
        stop:1 {p.header_gradient_end});
    min-height: 50px;
    max-height: 50px;
}}

/* Header toolbar buttons (icon-only, transparent background) */
QWidget[header="true"] QPushButton {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 0px;
}}

QWidget[header="true"] QPushButton:hover {{
    background: rgba(255, 255, 255, 0.15);
}}

QWidget[header="true"] QPushButton:pressed {{
    background: rgba(255, 255, 255, 0.25);
}}

QWidget[header="true"] QPushButton:checked {{
    background: rgba(255, 255, 255, 0.2);
}}

QWidget[header="true"] QPushButton:disabled {{
    opacity: 0.3;
}}

/* Search box on header (white background for contrast) */
QWidget[header="true"] QLineEdit {{
    background: rgba(255, 255, 255, 0.9);
    color: #1a1a1a;
    border: none;
    border-radius: 0px;
    padding: 6px 12px;
}}

QWidget[header="true"] QLineEdit:focus {{
    background: rgba(255, 255, 255, 1.0);
}}

/* Combo boxes on header */
QWidget[header="true"] QComboBox {{
    background: rgba(255, 255, 255, 0.15);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.3);
    border-radius: 0px;
    padding: 4px 8px;
}}

QWidget[header="true"] QComboBox:hover {{
    background: rgba(255, 255, 255, 0.25);
    border-color: rgba(255, 255, 255, 0.5);
}}

QWidget[header="true"] QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

/* Labels on header */
QWidget[header="true"] QLabel {{
    color: {p.header_icon_color};
    background: transparent;
}}

/* Checkboxes on header */
QWidget[header="true"] QCheckBox {{
    color: {p.header_icon_color};
    background: transparent;
    spacing: 6px;
}}

QWidget[header="true"] QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 2px solid {p.header_icon_color};
    border-radius: 2px;
    background: transparent;
}}

QWidget[header="true"] QCheckBox::indicator:hover {{
    border-color: {p.header_icon_color};
    background: rgba(255, 255, 255, 0.1);
}}

QWidget[header="true"] QCheckBox::indicator:checked {{
    background: {p.header_icon_color};
    border-color: {p.header_icon_color};
}}

/* Slider on header */
QWidget[header="true"] QSlider::groove:horizontal {{
    background: rgba(255, 255, 255, 0.2);
    height: 4px;
    border-radius: 2px;
}}

QWidget[header="true"] QSlider::handle:horizontal {{
    background: white;
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -5px 0;
}}

QWidget[header="true"] QSlider::sub-page:horizontal {{
    background: rgba(255, 255, 255, 0.5);
    border-radius: 2px;
}}

/* ===== CARD SIZE SLIDER (header) ===== */
/* More specific selector to override header slider styles */
QWidget[header="true"] QSlider[cardsize="true"]::groove:horizontal {{
    background: rgba(255, 255, 255, 0.2);
    height: 20px;
    border: none;
    border-radius: 0px;
}}

QWidget[header="true"] QSlider[cardsize="true"]::handle:horizontal {{
    background: {p.header_icon_color};
    width: 10px;
    height: 20px;
    margin: 0px;
    border: none;
    border-radius: 0px;
}}

QWidget[header="true"] QSlider[cardsize="true"]::handle:horizontal:hover {{
    background: {p.accent};
}}

QWidget[header="true"] QSlider[cardsize="true"]::handle:horizontal:pressed {{
    background: {p.accent};
}}

QWidget[header="true"] QSlider[cardsize="true"]::sub-page:horizontal {{
    background: {p.accent};
    height: 20px;
    border: none;
    border-radius: 0px;
}}

QWidget[header="true"] QSlider[cardsize="true"]::add-page:horizontal {{
    background: rgba(255, 255, 255, 0.2);
    height: 20px;
    border: none;
    border-radius: 0px;
}}

/* ===== LABELS ===== */
QLabel {{
    color: {p.text_primary};
    background-color: transparent;
}}

/* ===== PUSH BUTTONS ===== */
QPushButton {{
    background-color: {p.button_background};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 0px;
    padding: 6px 12px;
    min-height: 24px;
}}

QPushButton:hover {{
    background-color: {p.button_hover};
}}

QPushButton:pressed {{
    background-color: {p.button_pressed};
}}

QPushButton:disabled {{
    background-color: {p.button_disabled};
    color: {p.text_disabled};
}}

/* Accent button style */
QPushButton[accent="true"] {{
    background-color: {p.accent};
    color: white;
    border: none;
    font-weight: bold;
}}

QPushButton[accent="true"]:hover {{
    background-color: {p.accent_hover};
}}

QPushButton[accent="true"]:pressed {{
    background-color: {p.accent_pressed};
}}

/* ===== LINE EDIT ===== */
QLineEdit {{
    background-color: {p.background_secondary};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 0px;
    padding: 4px 8px;
    selection-background-color: {p.accent};
}}

QLineEdit:focus {{
    border-color: {p.accent};
}}

QLineEdit:disabled {{
    background-color: {p.button_disabled};
    color: {p.text_disabled};
}}

/* ===== TEXT EDIT ===== */
QTextEdit {{
    background-color: {p.background_secondary};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 0px;
    padding: 4px;
}}

QTextEdit:focus {{
    border-color: {p.accent};
}}

/* ===== COMBO BOX ===== */
QComboBox {{
    background-color: {p.button_background};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 0px;
    padding: 4px 8px;
}}

QComboBox:hover {{
    border-color: {p.accent};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {p.list_item_background};
    color: {p.text_primary};
    border: 1px solid {p.border};
    selection-background-color: transparent;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    padding: 4px 8px;
    background-color: {p.list_item_background};
    border: 1px solid transparent;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {p.list_item_hover};
    border: 1px solid {p.selection_border};
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: {p.list_item_selected};
    border: 1px solid {p.selection_border};
}}

/* ===== SPIN BOX ===== */
QSpinBox {{
    background-color: {p.background_secondary};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 0px;
    padding: 4px 8px;
}}

QSpinBox:focus {{
    border-color: {p.accent};
}}

/* ===== LIST VIEW ===== */
QListView {{
    background-color: {p.background};
    border: none;
    outline: none;
}}

QListView::item {{
    background-color: {p.list_item_background};
    padding: 4px;
}}

QListView::item:selected {{
    background-color: {p.list_item_selected};
    border: 1px solid {p.selection_border};
}}

QListView::item:hover:!selected {{
    background-color: {p.list_item_hover};
}}

/* ===== TABLE VIEW / TABLE WIDGET ===== */
QTableWidget, QTableView {{
    background-color: {p.background};
    alternate-background-color: {p.list_item_background};
    color: {p.text_primary};
    gridline-color: {p.border};
    border: 1px solid {p.border};
    outline: none;
}}

QTableWidget::item, QTableView::item {{
    background-color: {p.background_secondary};
    color: {p.text_primary};
    padding: 4px;
}}

QTableWidget::item:alternate, QTableView::item:alternate {{
    background-color: {p.list_item_background};
}}

QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {p.list_item_selected};
    color: white;
}}

QTableWidget::item:hover:!selected, QTableView::item:hover:!selected {{
    background-color: {p.list_item_hover};
}}

QHeaderView {{
    background-color: {p.background_secondary};
}}

QHeaderView::section {{
    background-color: {p.list_item_background};
    color: {p.text_primary};
    padding: 6px;
    border: none;
    border-right: 1px solid {p.border};
    border-bottom: 1px solid {p.border};
}}

QHeaderView::section:hover {{
    background-color: {p.list_item_hover};
}}

/* ===== TREE VIEW ===== */
QTreeWidget, QTreeView {{
    background-color: {p.background_secondary};
    color: {p.text_primary};
    border: none;
    outline: none;
    alternate-background-color: transparent;
}}

QTreeWidget::item, QTreeView::item {{
    padding: 4px;
    color: {p.text_primary};
}}

QTreeWidget::item:selected, QTreeView::item:selected {{
    background-color: {p.accent};
    color: white;
}}

QTreeWidget::item:hover:!selected, QTreeView::item:hover:!selected {{
    background-color: {p.button_hover};
}}

/* ===== SCROLL BARS ===== */
QScrollBar:vertical {{
    background-color: {p.background_secondary};
    width: 12px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background-color: {p.button_background};
    min-height: 20px;
    border-radius: 4px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {p.button_hover};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {p.background_secondary};
    height: 12px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background-color: {p.button_background};
    min-width: 20px;
    border-radius: 4px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {p.button_hover};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ===== SCROLL AREA ===== */
QScrollArea {{
    border: none;
}}

/* ===== SLIDERS ===== */
QSlider::groove:horizontal {{
    background-color: {p.background_secondary};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {p.accent};
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -6px 0;
}}

QSlider::handle:horizontal:hover {{
    background-color: {p.accent_hover};
}}

QSlider::sub-page:horizontal {{
    background-color: {p.accent};
    border-radius: 2px;
}}

/* ===== SPLITTER ===== */
QSplitter::handle {{
    background-color: {p.divider};
}}

QSplitter::handle:horizontal {{
    width: 2px;
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

QSplitter::handle:hover {{
    background-color: {p.border};
}}

/* ===== GROUP BOX ===== */
QGroupBox {{
    font-weight: bold;
    border: 1px solid {p.border};
    border-radius: 0px;
    margin-top: 8px;
    padding-top: 8px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {p.text_primary};
}}

/* ===== TABS ===== */
QTabWidget::pane {{
    border: 1px solid {p.border};
    background-color: {p.background};
}}

QTabBar::tab {{
    background-color: {p.background_secondary};
    color: {p.text_secondary};
    padding: 8px 16px;
    border: 1px solid {p.border};
    border-bottom: none;
}}

QTabBar::tab:selected {{
    background-color: {p.background};
    color: {p.text_primary};
}}

QTabBar::tab:hover:!selected {{
    background-color: {p.button_hover};
}}

/* ===== CHECK BOX ===== */
QCheckBox {{
    color: {p.text_primary};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {p.border};
    border-radius: 3px;
    background-color: {p.background_secondary};
}}

QCheckBox::indicator:checked {{
    background-color: {p.accent};
    border-color: {p.accent};
}}

QCheckBox::indicator:hover {{
    border-color: {p.accent};
}}

/* ===== PROGRESS BAR ===== */
QProgressBar {{
    background-color: {p.background_secondary};
    border: 1px solid {p.border};
    border-radius: 0px;
    text-align: center;
    color: {p.text_primary};
}}

QProgressBar::chunk {{
    background-color: {p.accent};
    border-radius: 0px;
}}

/* ===== MENU ===== */
QMenu {{
    background-color: {p.list_item_background};
    color: {p.text_primary};
    border: 1px solid {p.border};
}}

QMenu::item {{
    padding: 6px 20px;
    background-color: {p.list_item_background};
}}

QMenu::item:selected {{
    background-color: {p.list_item_selected};
    border: 1px solid {p.selection_border};
}}

QMenu::item:hover {{
    background-color: {p.list_item_hover};
}}

QMenu::separator {{
    height: 1px;
    background-color: {p.divider};
    margin: 4px 8px;
}}

/* ===== MESSAGE BOX ===== */
QMessageBox {{
    background-color: {p.background};
}}

QMessageBox QLabel {{
    color: {p.text_primary};
}}

/* ===== DIALOG ===== */
QDialog {{
    background-color: {p.background};
}}

/* ===== TOOLTIP ===== */
QToolTip {{
    background-color: {p.background_secondary};
    color: {p.text_primary};
    border: 1px solid {p.border};
    padding: 4px;
}}
"""


__all__ = ['DarkTheme']
