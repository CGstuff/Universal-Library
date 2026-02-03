# UI Style Guide
## For Universal Asset Library and Future Applications

Based on the Action Library v2 design language.

---

## 1. DESIGN PHILOSOPHY

### Sharp vs Rounded Elements
- **Sharp (border-radius: 0px)**: Buttons, input fields, dropdowns, sliders, badges, media controls
- **Rounded (border-radius: 4px)**: Toolbar icon buttons (hover background only)
- **Subtle (border-radius: 3px)**: Section headers, checkboxes

### Visual Hierarchy
| Level | Style | Example |
|-------|-------|---------|
| Primary | Bold font, accent color background | Main action buttons |
| Secondary | Regular font, bordered | Cancel, Back buttons |
| Tertiary | Icon-only, transparent | Toolbar icons |
| Disabled | 30% opacity or gray | Inactive controls |

---

## 2. COLOR PALETTE (Dark Theme)

### Backgrounds
```
Primary:        #1E1E1E    (main background)
Secondary:      #2D2D2D    (panels, cards)
Tertiary:       #3A3A3A    (buttons, list items)
```

### Text
```
Primary:        #FFFFFF    (main text)
Secondary:      #B0B0B0    (labels, hints)
Disabled:       #606060    (inactive text)
```

### Accent (Blue)
```
Primary:        #3A8FB7    (links, selections)
Hover:          #4A9FC7
Pressed:        #2A7FA7
```

### Status Colors
```
Success:        #4CAF50    (green)
Warning:        #F39C12    (orange)
Error:          #E74C3C    (red)
```

### Borders
```
Primary:        #404040    (standard borders)
Divider:        #353535    (subtle separators)
Selection:      #3A8FB7    (selected items)
```

---

## 3. TYPOGRAPHY

### Font Family
```
Primary:        "Segoe UI", Arial, sans-serif
```

### Font Sizes
```
Body:           10pt
Compact:        9pt       (badges, search)
Title:          12pt+     (section headers)
Large Title:    14pt      (dialog titles)
```

### Font Weights
```
Normal:         400       (body text)
Bold:           700       (titles, emphasis)
```

---

## 4. SPACING

### Standard Values
```
Tiny:           4px       (toolbar spacing)
Small:          8px       (item spacing)
Medium:         12px      (section spacing)
Large:          16px      (panel padding)
XLarge:         20px      (dialog margins)
```

### Component Padding
```
Buttons:        6px 12px  (vertical horizontal)
Inputs:         4px 8px   (compact)
               5px 12px  (standard)
Section Title:  4px 8px
```

---

## 5. COMPONENT STYLES

### Buttons - Standard (Secondary)
```css
QPushButton {
    padding: 5px 12px;
    border: 1px solid #555;
    border-radius: 0px;
    background-color: #3c3c3c;
    color: white;
}
QPushButton:hover {
    background-color: #4a4a4a;
}
QPushButton:pressed {
    background-color: #2d2d2d;
}
QPushButton:disabled {
    color: #666;
    background-color: #2d2d2d;
    border-color: #444;
}
```

### Buttons - Primary (Accent)
```css
QPushButton[accent="true"] {
    background-color: #0078d4;
    border: 1px solid #0078d4;
    border-radius: 0px;
    color: white;
}
QPushButton[accent="true"]:hover {
    background-color: #1084d8;
    border-color: #1084d8;
}
```

### Buttons - Danger
```css
QPushButton[danger="true"] {
    background-color: #E74C3C;
    border: 1px solid #E74C3C;
    border-radius: 0px;
    color: white;
}
QPushButton[danger="true"]:hover {
    background-color: #ef5350;
}
```

### Buttons - Link Style
```css
QPushButton[link="true"] {
    background-color: transparent;
    color: #0078d4;
    border: none;
    padding: 5px;
}
QPushButton[link="true"]:hover {
    color: #1084d8;
    text-decoration: underline;
}
```

### Buttons - Toolbar (Icon-only)
```css
QToolButton {
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px;
}
QToolButton:hover {
    background-color: rgba(255, 255, 255, 0.1);
}
QToolButton:pressed {
    background-color: rgba(255, 255, 255, 0.05);
}
```

### Input Fields
```css
QLineEdit {
    padding: 5px 8px;
    border: 1px solid #555;
    border-radius: 0px;
    background-color: #2d2d2d;
    color: white;
    selection-background-color: #3A8FB7;
}
QLineEdit:focus {
    border-color: #3A8FB7;
}
QLineEdit:disabled {
    background-color: #252525;
    color: #666;
}
```

### Dropdowns (ComboBox)
```css
QComboBox {
    padding: 4px 8px;
    border: 1px solid #555;
    border-radius: 0px;
    background-color: #3c3c3c;
    color: white;
}
QComboBox:hover {
    background-color: #4a4a4a;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #3A3A3A;
    border: 1px solid #555;
    selection-background-color: #3A8FB7;
}
```

### Group Box
```css
QGroupBox {
    border: 1px solid #444;
    border-radius: 0px;
    margin-top: 10px;
    padding-top: 10px;
    font-size: 10pt;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
```

### Scroll Bars
```css
QScrollBar:vertical {
    width: 12px;
    background-color: #2D2D2D;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #3A3A3A;
    min-height: 20px;
    border-radius: 6px;
}
QScrollBar::handle:vertical:hover {
    background-color: #4A4A4A;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}
```

### Sliders
```css
QSlider::groove:horizontal {
    background-color: #2D2D2D;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background-color: #3A8FB7;
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -5px 0;
}
QSlider::handle:horizontal:hover {
    background-color: #4A9FC7;
}
```

### Sliders - Flat (Card Size, Progress)
```css
QSlider[flat="true"]::groove:horizontal {
    background: rgba(255, 255, 255, 0.2);
    height: 20px;
    border-radius: 0px;
}
QSlider[flat="true"]::handle:horizontal {
    background: white;
    width: 10px;
    height: 20px;
    border-radius: 0px;
    margin: 0px;
}
QSlider[flat="true"]::sub-page:horizontal {
    background: #3A8FB7;
}
```

### Checkboxes
```css
QCheckBox {
    color: white;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #555;
    border-radius: 3px;
    background-color: #2D2D2D;
}
QCheckBox::indicator:checked {
    background-color: #3A8FB7;
    border-color: #3A8FB7;
}
QCheckBox::indicator:hover {
    border-color: #4A9FC7;
}
```

### List/Tree Views
```css
QListView, QTreeView {
    background-color: #1E1E1E;
    border: 1px solid #404040;
    outline: none;
}
QListView::item, QTreeView::item {
    padding: 4px;
    background-color: transparent;
}
QListView::item:selected, QTreeView::item:selected {
    background-color: #3A8FB7;
    color: white;
}
QListView::item:hover:!selected, QTreeView::item:hover:!selected {
    background-color: #3A3A3A;
}
```

### Tabs
```css
QTabWidget::pane {
    border: 1px solid #404040;
    background-color: #1E1E1E;
}
QTabBar::tab {
    background-color: #3A3A3A;
    color: #B0B0B0;
    padding: 8px 16px;
    border: 1px solid #404040;
    border-bottom: none;
}
QTabBar::tab:selected {
    background-color: #1E1E1E;
    color: white;
}
QTabBar::tab:hover:!selected {
    background-color: #4A4A4A;
}
```

### Tooltips
```css
QToolTip {
    background-color: #2D2D2D;
    color: white;
    border: 1px solid #404040;
    padding: 4px;
}
```

### Menus
```css
QMenu {
    background-color: #3A3A3A;
    color: white;
    border: 1px solid #555;
}
QMenu::item {
    padding: 6px 20px;
}
QMenu::item:selected {
    background-color: #3A8FB7;
}
```

---

## 6. DIALOG STYLES

### Standard Dialog
```css
QDialog {
    background-color: #1E1E1E;
}
```

### Dialog Window Size
```
Small:          400 x 300   (simple confirmations)
Medium:         500 x 400   (setup wizards)
Large:          700 x 500   (complex dialogs)
```

### Dialog Layout
```
Margins:        50px horizontal, 30px top, 20px bottom
Spacing:        10px between elements
Button Bar:     15px padding, border-top: 1px solid #333
```

---

## 7. HEADER/TOOLBAR

### Header Bar (Gradient)
```css
QWidget[header="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #E5C046, stop:1 #D4AF37);
    min-height: 50px;
    max-height: 50px;
}
```

### Header Buttons
```css
QWidget[header="true"] QPushButton {
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 0px;
}
QWidget[header="true"] QPushButton:hover {
    background: rgba(0, 0, 0, 0.15);
}
```

### Header Search
```css
QWidget[header="true"] QLineEdit {
    background: rgba(255, 255, 255, 0.9);
    color: #1a1a1a;
    border: none;
    border-radius: 0px;
    padding: 6px 12px;
    font-size: 9pt;
}
```

---

## 8. STATUS BADGES

### Success Badge
```css
QLabel[status="success"] {
    background-color: #4CAF50;
    color: white;
    padding: 2px 6px;
    border-radius: 0px;
    font-size: 9pt;
    font-weight: bold;
}
```

### Warning Badge
```css
QLabel[status="warning"] {
    background-color: #F39C12;
    color: white;
    padding: 2px 6px;
    border-radius: 0px;
    font-size: 9pt;
    font-weight: bold;
}
```

### Error Badge
```css
QLabel[status="error"] {
    background-color: #E74C3C;
    color: white;
    padding: 2px 6px;
    border-radius: 0px;
    font-size: 9pt;
    font-weight: bold;
}
```

### Info Badge (Variant Count, etc.)
```css
QLabel[status="info"] {
    background-color: #512DA8;
    color: white;
    padding: 2px 6px;
    border-radius: 0px;
    font-size: 7pt;
    font-weight: bold;
}
```

---

## 9. SECTION HEADERS

```css
QLabel[section="true"] {
    font-weight: bold;
    background-color: rgba(128, 128, 128, 0.15);
    padding: 4px 8px;
    border-radius: 3px;
}
```

---

## 10. USING PROPERTIES

Apply contextual styles using Qt properties:

```python
# Primary/Accent button
button.setProperty("accent", "true")

# Danger button
button.setProperty("danger", "true")

# Link-style button
button.setProperty("link", "true")

# Section header label
label.setProperty("section", "true")

# Status badge
label.setProperty("status", "success")  # success, warning, error, info

# Flat slider
slider.setProperty("flat", "true")

# Header widget
widget.setProperty("header", "true")
widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

# Then refresh style
widget.style().unpolish(widget)
widget.style().polish(widget)
```

---

## 11. LAYOUT PATTERNS

### Main Window (3-Panel)
```
┌─────────────────────────────────────────────┐
│ Header Toolbar (50px fixed)                 │
├────────────┬──────────────────┬─────────────┤
│ Side Panel │  Main Content    │  Detail     │
│ (Fixed)    │  (Stretch: 1)    │  Panel      │
│            │                  │  (300px+)   │
├────────────┴──────────────────┴─────────────┤
│ Status Bar                                  │
└─────────────────────────────────────────────┘

Splitter Stretch Factors: 0, 1, 0
```

### Dialog Layout
```
┌─────────────────────────────────────────────┐
│                                             │
│  [Icon/Logo - centered]                     │
│                                             │
│  Title (14pt bold, centered)                │
│                                             │
│  Description (10pt, centered)               │
│                                             │
│  ┌─ GroupBox ──────────────────────────┐   │
│  │ • Item 1                            │   │
│  │ • Item 2                            │   │
│  │ • Item 3                            │   │
│  └─────────────────────────────────────┘   │
│                                             │
├─────────────────────────────────────────────┤
│ [Back]                            [Next]    │
└─────────────────────────────────────────────┘
```

---

## 12. ICON GUIDELINES

### Sizes
```
Toolbar:        24x24 (standard), 20x20 (compact)
Button:         40x40 container, 24x24 icon
Small:          16x16 (badges, indicators)
```

### Colors
- Use white (#FFFFFF) base SVGs
- Colorize dynamically based on theme
- Header icons: dark (#1A1A1A) on gradient background

---

## 13. QUICK REFERENCE

### Border Radius
| Element | Radius |
|---------|--------|
| Buttons (standard) | 0px |
| Inputs | 0px |
| Dropdowns | 0px |
| Badges | 0px |
| Sliders | 0px |
| Toolbar buttons | 4px |
| Checkboxes | 3px |
| Section headers | 3px |
| Scrollbar handles | 6px |

### Z-Index / Layering
```
Base content:       0
Panels:             1
Floating buttons:   2
Tooltips:           3
Dialogs:            4
Popups/Menus:       5
```

---

## 14. IMPLEMENTATION CHECKLIST

When styling a new application:

- [ ] Set up base color palette constants
- [ ] Create global stylesheet with common components
- [ ] Use property selectors for variants (accent, danger, etc.)
- [ ] Apply consistent spacing (4/8/12/16/20px scale)
- [ ] Use Segoe UI font family
- [ ] Ensure sharp inputs (border-radius: 0)
- [ ] Add hover/pressed/disabled states
- [ ] Style scrollbars
- [ ] Style tooltips and menus
- [ ] Test all interactive states

---

*Version 1.0 - Based on Action Library v2*
