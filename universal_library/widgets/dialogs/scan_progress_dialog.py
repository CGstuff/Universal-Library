"""
ScanProgressDialog - Progress dialog for asset scanning

Pattern: QDialog with progress bar
Based on animation_library architecture.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal


class ScanProgressDialog(QDialog):
    """
    Progress dialog for asset scanning operations

    Features:
    - Progress bar
    - Current file display
    - Status message
    - Cancel button

    Usage:
        dialog = ScanProgressDialog(parent=main_window)
        dialog.show()

        # Update progress from scanner
        dialog.set_progress(50, 100)
        dialog.set_current_file("/path/to/file.usd")
        dialog.set_status("Scanning...")

        # Check if cancelled
        if dialog.was_cancelled():
            # Stop scanning
            pass
    """

    # Signal emitted when cancel is clicked
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._cancelled = False

        self.setWindowTitle("Scanning Assets")
        self.setModal(True)
        self.setFixedSize(450, 180)

        # Prevent closing with X button during scan
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint
        )

        self._create_ui()

    def _create_ui(self):
        """Create UI layout"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Status label
        self._status_label = QLabel("Preparing scan...")
        self._status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._status_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)

        # Current file label
        self._file_label = QLabel("")
        self._file_label.setStyleSheet("color: #808080; font-size: 11px;")
        self._file_label.setWordWrap(True)
        self._file_label.setMaximumHeight(40)
        layout.addWidget(self._file_label)

        # Cancel button
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _on_cancel(self):
        """Handle cancel button click"""
        self._cancelled = True
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("Cancelling...")
        self._status_label.setText("Cancelling scan...")
        self.cancel_requested.emit()

    def set_progress(self, current: int, total: int):
        """Set progress bar value"""
        if total > 0:
            percentage = int((current / total) * 100)
            self._progress_bar.setValue(percentage)
            self._progress_bar.setFormat(f"{current} / {total} ({percentage}%)")
        else:
            self._progress_bar.setValue(0)
            self._progress_bar.setFormat("0%")

    def set_status(self, message: str):
        """Set status message"""
        self._status_label.setText(message)

    def set_current_file(self, file_path: str):
        """Set current file being processed"""
        # Truncate long paths
        if len(file_path) > 60:
            file_path = "..." + file_path[-57:]
        self._file_label.setText(file_path)

    def was_cancelled(self) -> bool:
        """Check if user cancelled the operation"""
        return self._cancelled

    def finish(self, message: str = "Scan complete"):
        """Mark scan as finished"""
        self._status_label.setText(message)
        self._file_label.setText("")
        self._cancel_btn.setText("Close")
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.clicked.disconnect()
        self._cancel_btn.clicked.connect(self.accept)

        # Allow closing with X button
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.show()  # Re-show to apply new flags

    def set_indeterminate(self, indeterminate: bool = True):
        """Set progress bar to indeterminate mode"""
        if indeterminate:
            self._progress_bar.setMaximum(0)  # Indeterminate
        else:
            self._progress_bar.setMaximum(100)


__all__ = ['ScanProgressDialog']
