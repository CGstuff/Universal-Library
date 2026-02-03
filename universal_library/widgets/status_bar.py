"""
StatusBar - Bottom status bar

Pattern: QWidget with horizontal layout
Based on animation_library architecture.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt

from ..events.event_bus import get_event_bus


class StatusBar(QWidget):
    """
    Bottom status bar

    Features:
    - Status message display
    - Asset count display

    Layout:
        [Status message...                    ] [1,234 assets]
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._event_bus = get_event_bus()
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Setup status bar UI"""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(16)

        # Status message (left, stretches)
        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #a0a0a0;")
        layout.addWidget(self._status_label, 1)

        # Asset count (right)
        self._count_label = QLabel("0 assets")
        self._count_label.setStyleSheet("color: #808080;")
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._count_label)

        # Fixed height
        self.setFixedHeight(28)

    def _connect_signals(self):
        """Connect signals"""
        self._event_bus.status_message.connect(self.set_status)
        self._event_bus.status_error.connect(self.set_error)
        self._event_bus.assets_loaded.connect(self._on_assets_loaded)

    def set_status(self, message: str):
        """Set status message"""
        self._status_label.setText(message)
        self._status_label.setStyleSheet("color: #a0a0a0;")

    def set_error(self, message: str):
        """Set error message (red)"""
        self._status_label.setText(message)
        self._status_label.setStyleSheet("color: #ff6b6b;")

    def set_asset_count(self, count: int, filtered: bool = False):
        """Set asset count display"""
        if filtered:
            self._count_label.setText(f"{count:,} assets (filtered)")
        else:
            self._count_label.setText(f"{count:,} assets")

    def _on_assets_loaded(self, count: int):
        """Handle assets loaded event"""
        self.set_asset_count(count)
        self.set_status("Ready")


__all__ = ['StatusBar']
