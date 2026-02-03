"""
BackupTab - Library backup and restore settings

Provides UI for:
- Export entire library to .assetlib archive
- Import library from .assetlib archive
- Preview archive contents before import
"""

from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QMessageBox, QFileDialog,
    QProgressDialog, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ...config import Config
from ...services.backup_service import BackupService
from ...services.database_service import get_database_service
from ...services.review_database import get_review_database


class ExportWorker(QThread):
    """Background worker for export operation"""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, storage_path: Path, output_path: Path):
        super().__init__()
        self.storage_path = storage_path
        self.output_path = output_path

    def run(self):
        try:
            success = BackupService.export_library(
                self.storage_path,
                self.output_path,
                self._progress_callback
            )
            self.finished.emit(success, "Export completed successfully!" if success else "Export failed")
        except Exception as e:
            self.finished.emit(False, f"Export error: {str(e)}")

    def _progress_callback(self, current, total, message):
        self.progress.emit(current, total, message)


class ImportWorker(QThread):
    """Background worker for import operation"""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)

    def __init__(self, archive_path: Path, storage_path: Path):
        super().__init__()
        self.archive_path = archive_path
        self.storage_path = storage_path

    def run(self):
        try:
            stats = BackupService.import_library(
                self.archive_path,
                self.storage_path,
                self._progress_callback
            )
            self.finished.emit(stats)
        except Exception as e:
            self.finished.emit({'errors': [str(e)]})

    def _progress_callback(self, current, total, message):
        self.progress.emit(current, total, message)


class BackupTab(QWidget):
    """Library backup and restore settings tab"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._storage_path = Config.load_library_path()
        self._init_ui()
        self._refresh_stats()

    def _init_ui(self):
        """Initialize UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Export Section
        layout.addWidget(self._create_export_section())

        # Import Section
        layout.addWidget(self._create_import_section())

        layout.addStretch()

        # Note at bottom
        note = QLabel(
            "Note: Importing a backup will replace your current library. "
            "Your existing databases are automatically backed up before import."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-style: italic; color: #808080;")
        layout.addWidget(note)

    def _create_export_section(self):
        """Create export section"""
        group = QGroupBox("Export Library")
        group_layout = QVBoxLayout(group)

        # Library stats
        self._stats_label = QLabel("Loading library statistics...")
        group_layout.addWidget(self._stats_label)

        group_layout.addSpacing(10)

        # Export button
        btn_layout = QHBoxLayout()

        self._export_btn = QPushButton("Export to .assetlib...")
        self._export_btn.setMinimumWidth(200)
        self._export_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #555555;
            }
        """)
        self._export_btn.clicked.connect(self._on_export_clicked)
        btn_layout.addWidget(self._export_btn)

        btn_layout.addStretch()
        group_layout.addLayout(btn_layout)

        # Description
        desc = QLabel("Creates a complete backup including all assets, versions, reviews, and database.")
        desc.setStyleSheet("color: #808080;")
        group_layout.addWidget(desc)

        return group

    def _create_import_section(self):
        """Create import section"""
        group = QGroupBox("Import Library")
        group_layout = QVBoxLayout(group)

        # Warning
        warning = QLabel("⚠ This will replace your current library with the archive contents.")
        warning.setStyleSheet("color: #FFA500; font-weight: bold;")
        group_layout.addWidget(warning)

        group_layout.addSpacing(10)

        # Import button
        btn_layout = QHBoxLayout()

        self._import_btn = QPushButton("Import from .assetlib...")
        self._import_btn.setMinimumWidth(200)
        self._import_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #555555;
            }
        """)
        self._import_btn.clicked.connect(self._on_import_clicked)
        btn_layout.addWidget(self._import_btn)

        btn_layout.addStretch()
        group_layout.addLayout(btn_layout)

        # Description
        desc = QLabel("Import a previously exported .assetlib archive. Application restart required after import.")
        desc.setStyleSheet("color: #808080;")
        group_layout.addWidget(desc)

        return group

    def _refresh_stats(self):
        """Refresh library statistics"""
        if not self._storage_path or not self._storage_path.exists():
            self._stats_label.setText("No library configured")
            self._export_btn.setEnabled(False)
            return

        try:
            stats = BackupService.get_library_stats(self._storage_path)
            stats_text = (
                f"<b>Assets:</b> {stats.get('asset_count', 0)}  |  "
                f"<b>Folders:</b> {stats.get('folder_count', 0)}  |  "
                f"<b>Tags:</b> {stats.get('tag_count', 0)}<br>"
                f"<b>Estimated Size:</b> {stats.get('estimated_size_mb', 0):.1f} MB"
            )
            if stats.get('has_reviews'):
                stats_text += "  |  <b>Reviews:</b> Included"

            self._stats_label.setText(stats_text)
            self._export_btn.setEnabled(True)
        except Exception as e:
            self._stats_label.setText(f"Error loading stats: {str(e)}")
            self._export_btn.setEnabled(False)

    def _on_export_clicked(self):
        """Handle export button click"""
        if not self._storage_path:
            QMessageBox.warning(self, "Error", "No library configured")
            return

        # Get output file path
        default_name = f"library_backup_{datetime.now().strftime('%Y%m%d')}.assetlib"
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Library",
            str(Path.home() / default_name),
            "Asset Library Archive (*.assetlib)"
        )

        if not output_path:
            return

        # Create progress dialog
        self._progress = QProgressDialog("Exporting library...", "Cancel", 0, 100, self)
        self._progress.setWindowTitle("Export")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setValue(0)

        # Disable buttons during export
        self._export_btn.setEnabled(False)
        self._import_btn.setEnabled(False)

        # Start export worker
        self._export_worker = ExportWorker(self._storage_path, Path(output_path))
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.start()

    def _on_export_progress(self, current, total, message):
        """Handle export progress updates"""
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(current)
        self._progress.setLabelText(message)
        QApplication.processEvents()

    def _on_export_finished(self, success, message):
        """Handle export completion"""
        self._progress.close()
        self._export_btn.setEnabled(True)
        self._import_btn.setEnabled(True)

        if success:
            QMessageBox.information(self, "Export Complete", message)
        else:
            QMessageBox.warning(self, "Export Failed", message)

    def _on_import_clicked(self):
        """Handle import button click"""
        # Get archive file path
        archive_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Library",
            str(Path.home()),
            "Asset Library Archive (*.assetlib)"
        )

        if not archive_path:
            return

        archive_path = Path(archive_path)

        # Validate archive
        is_valid, message = BackupService.validate_archive(archive_path)
        if not is_valid:
            QMessageBox.warning(self, "Invalid Archive", message)
            return

        # Get archive info for preview
        info = BackupService.get_archive_info(archive_path)
        if not info:
            QMessageBox.warning(self, "Error", "Could not read archive information")
            return

        # Show confirmation dialog with archive info
        info_text = (
            f"Archive Contents:\n\n"
            f"  Created: {info.get('created', 'Unknown')[:19]}\n"
            f"  App Version: {info.get('app_version', 'Unknown')}\n"
            f"  Schema Version: {info.get('schema_version', 'Unknown')}\n\n"
            f"  Assets: {info.get('asset_count', 0)}\n"
            f"  Folders: {info.get('folder_count', 0)}\n"
            f"  Tags: {info.get('tag_count', 0)}\n"
            f"  Size: {info.get('total_size_mb', 0):.1f} MB\n\n"
            f"This will REPLACE your current library.\n"
            f"Your existing databases will be backed up.\n\n"
            f"Continue with import?"
        )

        reply = QMessageBox.question(
            self,
            "Confirm Import",
            info_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        if not self._storage_path:
            QMessageBox.warning(self, "Error", "No library configured")
            return

        # Close database connections before import (to release file locks)
        try:
            db_service = get_database_service()
            db_service.close()
        except Exception:
            pass

        try:
            review_db = get_review_database()
            review_db.close()
        except Exception:
            pass

        # Create progress dialog
        self._progress = QProgressDialog("Importing library...", "Cancel", 0, 100, self)
        self._progress.setWindowTitle("Import")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setValue(0)

        # Disable buttons during import
        self._export_btn.setEnabled(False)
        self._import_btn.setEnabled(False)

        # Start import worker
        self._import_worker = ImportWorker(archive_path, self._storage_path)
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.start()

    def _on_import_progress(self, current, total, message):
        """Handle import progress updates"""
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(current)
        self._progress.setLabelText(message)
        QApplication.processEvents()

    def _on_import_finished(self, stats):
        """Handle import completion"""
        self._progress.close()
        self._export_btn.setEnabled(True)
        self._import_btn.setEnabled(True)

        errors = stats.get('errors', [])
        imported = stats.get('imported', 0)
        db_replaced = stats.get('databases_replaced', 0)

        if errors:
            error_text = "\n".join(errors[:5])
            if len(errors) > 5:
                error_text += f"\n... and {len(errors) - 5} more errors"
            QMessageBox.warning(
                self,
                "Import Completed with Errors",
                f"Imported {imported} files with {len(errors)} errors:\n\n{error_text}"
            )
        else:
            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully imported {imported} files.\n"
                f"Databases replaced: {db_replaced}\n\n"
                f"Please restart the application to load the imported library."
            )

        # Refresh stats
        self._refresh_stats()


__all__ = ['BackupTab']
