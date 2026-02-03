"""
Base widget classes for Universal Library UI.

Provides common patterns for panels, dialogs, and sections.

Usage:
    class MyPanel(BasePanel):
        def _setup_ui(self):
            layout = QVBoxLayout(self)
            # Add widgets...

        def _connect_signals(self):
            self.my_button.clicked.connect(self._on_click)
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QDialog, QGroupBox, QVBoxLayout, QHBoxLayout,
    QApplication, QFrame
)
from PyQt6.QtCore import Qt

from .styles import Colors


class BasePanel(QWidget):
    """
    Base class for panel widgets.

    Subclasses should implement:
    - _setup_ui(): Create layout and add widgets
    - _connect_signals(): Connect widget signals to handlers (optional)
    - _load_data(): Load initial data (optional)
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """
        Set up the UI layout and widgets.

        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _setup_ui()")

    def _connect_signals(self) -> None:
        """
        Connect widget signals to handlers.

        Override in subclasses to set up signal connections.
        Called after _setup_ui().
        """
        pass

    def _load_data(self) -> None:
        """
        Load initial data into the panel.

        Override in subclasses if needed.
        Call manually after construction if async loading is required.
        """
        pass


class BaseDialog(QDialog):
    """
    Base class for dialog windows.

    Provides:
    - Automatic sizing to percentage of screen
    - Automatic centering on screen
    - Common window flags

    Subclasses should implement:
    - _setup_ui(): Create layout and add widgets
    - _connect_signals(): Connect widget signals to handlers (optional)
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "Dialog",
        size_ratio: float = 0.8
    ):
        super().__init__(parent)
        self.setWindowTitle(title)

        # Window flags for proper behavior
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        # Size and position
        self._size_to_screen(size_ratio)
        self._center_on_screen()

        # Setup
        self._setup_ui()
        self._connect_signals()

    def _size_to_screen(self, ratio: float) -> None:
        """Resize dialog to a percentage of screen size."""
        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            width = int(rect.width() * ratio)
            height = int(rect.height() * ratio)
            self.resize(width, height)
            self.setMinimumSize(int(width * 0.5), int(height * 0.5))
        else:
            # Fallback
            self.resize(1200, 800)

    def _center_on_screen(self) -> None:
        """Center the dialog on the screen."""
        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            size = self.size()
            x = rect.x() + (rect.width() - size.width()) // 2
            y = rect.y() + (rect.height() - size.height()) // 2
            self.move(x, y)

    def _setup_ui(self) -> None:
        """
        Set up the UI layout and widgets.

        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _setup_ui()")

    def _connect_signals(self) -> None:
        """
        Connect widget signals to handlers.

        Override in subclasses to set up signal connections.
        """
        pass


class BaseSection(QGroupBox):
    """
    Base class for collapsible/grouped sections in panels.

    Use for logical groupings of related controls.

    Example:
        class IdentificationSection(BaseSection):
            def __init__(self, parent=None):
                super().__init__("Identification", parent)

            def _setup_ui(self):
                layout = QVBoxLayout(self)
                self._name_label = QLabel()
                layout.addWidget(self._name_label)
    """

    def __init__(self, title: str = "", parent: Optional[QWidget] = None):
        super().__init__(title, parent)

        # Default styling
        self.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: {Colors.BG_MEDIUM};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: {Colors.TEXT_SECONDARY};
            }}
        """)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """
        Set up the section layout and widgets.

        Override in subclasses.
        """
        pass

    def _connect_signals(self) -> None:
        """
        Connect widget signals to handlers.

        Override in subclasses.
        """
        pass


class HLine(QFrame):
    """Horizontal separator line."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setStyleSheet(f"color: {Colors.BORDER_DARK};")


class VLine(QFrame):
    """Vertical separator line."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.VLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setStyleSheet(f"color: {Colors.BORDER_DARK};")


__all__ = ['BasePanel', 'BaseDialog', 'BaseSection', 'HLine', 'VLine']
