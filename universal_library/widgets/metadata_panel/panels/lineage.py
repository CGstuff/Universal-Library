"""
LineagePanel - Version, badges, and status indicators.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon

from ....config import Config
from ....services.database_service import get_database_service
from .representations_dialog import RepresentationsDialog


class LineagePanel(QWidget):
    """
    Panel showing version lineage information.

    Features:
    - Version label (v001, v002, etc.)
    - Variant badge (shown if not Base)
    - Variant set badge
    - Status badge (WIP, Approved, etc.)
    - Representation badge (Model, Lookdev, etc.)
    - Comment indicator
    - Latest/Cold/Locked indicators
    - Provenance label (for variants)
    - Representations button (opens dialog for mesh/rig)
    - View Lineage button
    """

    # Signal emitted when View Lineage button clicked
    history_requested = pyqtSignal()

    # Signal emitted when user applies proxy/render selection (proxy_uuid, render_uuid, proxy_source)
    representation_apply_requested = pyqtSignal(object, object, str)

    # Signal emitted when user wants to regenerate representation files
    representation_regenerate_requested = pyqtSignal()

    # Signal emitted when user wants to clear representations
    representation_clear_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db_service = get_database_service()
        self._representations_dialog: Optional[RepresentationsDialog] = None
        
        # Data for representations dialog
        self._versions_list: List[Dict[str, Any]] = []
        self._custom_proxies_list: List[Dict[str, Any]] = []
        self._current_designations: Dict[str, Any] = {}
        
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._group = QGroupBox("Lineage")
        group_layout = QVBoxLayout(self._group)

        # Version label and badges row
        version_row = QHBoxLayout()

        self._version_label = QLabel("v001")
        self._version_label.setStyleSheet("""
            QLabel {
                background-color: #404040;
                color: white;
                padding: 2px 8px;
                border-radius: 0px;
                font-weight: bold;
            }
        """)
        version_row.addWidget(self._version_label)

        self._variant_badge = QLabel("Base")
        self._variant_badge.setStyleSheet("""
            QLabel {
                background-color: #7B1FA2;
                color: white;
                padding: 2px 8px;
                border-radius: 0px;
                font-size: 11px;
            }
        """)
        self._variant_badge.hide()
        version_row.addWidget(self._variant_badge)

        self._variant_set_badge = QLabel("Default")
        self._variant_set_badge.setStyleSheet("""
            QLabel {
                background-color: #607D8B;
                color: white;
                padding: 2px 8px;
                border-radius: 0px;
                font-size: 11px;
            }
        """)
        self._variant_set_badge.hide()
        version_row.addWidget(self._variant_set_badge)

        self._status_badge = QLabel("WIP")
        self._status_badge.setStyleSheet("""
            QLabel {
                background-color: #FF9800;
                color: white;
                padding: 2px 8px;
                border-radius: 0px;
                font-size: 11px;
            }
        """)
        version_row.addWidget(self._status_badge)

        self._rep_badge = QLabel("Final")
        self._rep_badge.setStyleSheet("""
            QLabel {
                background-color: #2196F3;
                color: white;
                padding: 2px 8px;
                border-radius: 0px;
                font-size: 11px;
            }
        """)
        version_row.addWidget(self._rep_badge)

        # Comment indicator
        self._comment_widget = QWidget()
        comment_layout = QHBoxLayout(self._comment_widget)
        comment_layout.setContentsMargins(0, 0, 0, 0)
        comment_layout.setSpacing(4)

        self._comment_icon = QLabel()
        icon_path = Path(__file__).parent.parent.parent / "icons" / "utility" / "info.svg"
        if icon_path.exists():
            self._comment_icon.setPixmap(QIcon(str(icon_path)).pixmap(14, 14))
        self._comment_icon.setFixedSize(14, 14)
        comment_layout.addWidget(self._comment_icon)

        self._comment_indicator = QLabel("0")
        self._comment_indicator.setStyleSheet("""
            QLabel {
                color: #E91E63;
                font-size: 11px;
            }
        """)
        comment_layout.addWidget(self._comment_indicator)

        self._comment_widget.hide()
        version_row.addWidget(self._comment_widget)

        version_row.addStretch()
        group_layout.addLayout(version_row)

        # Indicators row
        indicators_row = QHBoxLayout()

        self._latest_indicator = QLabel("Latest")
        self._latest_indicator.setStyleSheet("""
            QLabel {
                background-color: #4CAF50;
                color: white;
                padding: 2px 6px;
                border-radius: 0px;
                font-size: 10px;
            }
        """)
        indicators_row.addWidget(self._latest_indicator)

        self._cold_indicator = QLabel("Cold Storage")
        self._cold_indicator.setStyleSheet("""
            QLabel {
                background-color: #2196F3;
                color: white;
                padding: 2px 6px;
                border-radius: 0px;
                font-size: 10px;
            }
        """)
        self._cold_indicator.hide()
        indicators_row.addWidget(self._cold_indicator)

        self._locked_indicator = QLabel("Locked")
        self._locked_indicator.setStyleSheet("""
            QLabel {
                background-color: #FF9800;
                color: white;
                padding: 2px 6px;
                border-radius: 0px;
                font-size: 10px;
            }
        """)
        self._locked_indicator.hide()
        indicators_row.addWidget(self._locked_indicator)

        # Base Retired indicator (for variants whose base is retired)
        self._retired_base_indicator = QLabel("Base Retired")
        self._retired_base_indicator.setStyleSheet("""
            QLabel {
                background-color: #795548;
                color: white;
                padding: 2px 6px;
                border-radius: 0px;
                font-size: 10px;
            }
        """)
        self._retired_base_indicator.hide()
        indicators_row.addWidget(self._retired_base_indicator)

        indicators_row.addStretch()
        group_layout.addLayout(indicators_row)

        # Provenance label (for variants)
        self._provenance_label = QLabel("")
        self._provenance_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        self._provenance_label.hide()
        group_layout.addWidget(self._provenance_label)

        # Representations button (mesh/rig only)
        self._setup_representations_button(group_layout)

        # View lineage button
        self._history_btn = QPushButton("View Lineage")
        self._history_btn.setEnabled(False)
        self._history_btn.clicked.connect(self._on_history_clicked)
        group_layout.addWidget(self._history_btn)

        layout.addWidget(self._group)

    def _setup_representations_button(self, parent_layout: QVBoxLayout):
        """Setup the representations button with status indicators."""
        self._rep_button_container = QWidget()
        rep_layout = QHBoxLayout(self._rep_button_container)
        rep_layout.setContentsMargins(0, 4, 0, 4)
        rep_layout.setSpacing(8)
        
        # Button
        self._rep_button = QPushButton("Representations")
        self._rep_button.setFixedHeight(28)
        self._rep_button.setStyleSheet("""
            QPushButton {
                font-size: 11px;
                padding: 4px 12px;
                border: 1px solid #555;
                border-radius: 4px;
                background: #2d2d2d;
                text-align: left;
            }
            QPushButton:hover { 
                background: #383838;
                border-color: #666;
            }
            QPushButton:pressed { background: #404040; }
        """)
        self._rep_button.clicked.connect(self._on_representations_clicked)
        rep_layout.addWidget(self._rep_button)
        
        # Status indicators
        self._proxy_status = QLabel("Proxy")
        self._proxy_status.setStyleSheet("""
            QLabel {
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 2px;
                background: #333;
                color: #666;
            }
        """)
        rep_layout.addWidget(self._proxy_status)
        
        self._render_status = QLabel("Render")
        self._render_status.setStyleSheet("""
            QLabel {
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 2px;
                background: #333;
                color: #666;
            }
        """)
        rep_layout.addWidget(self._render_status)
        
        rep_layout.addStretch()
        
        self._rep_button_container.hide()
        parent_layout.addWidget(self._rep_button_container)

    def _on_history_clicked(self):
        """Handle history button click."""
        self.history_requested.emit()

    def _on_representations_clicked(self):
        """Open the representations dialog."""
        if self._representations_dialog is None:
            self._representations_dialog = RepresentationsDialog(self)
            self._representations_dialog.apply_requested.connect(self._on_dialog_apply)
            self._representations_dialog.regenerate_requested.connect(self._on_dialog_regenerate)
            self._representations_dialog.clear_requested.connect(self._on_dialog_clear)
        
        # Populate with current data
        self._representations_dialog.populate(
            self._versions_list,
            self._custom_proxies_list,
            self._current_designations
        )
        
        self._representations_dialog.show()
        self._representations_dialog.raise_()
        self._representations_dialog.activateWindow()

    def _on_dialog_apply(self, proxy_uuid, render_uuid, proxy_source):
        """Handle apply from dialog."""
        self.representation_apply_requested.emit(proxy_uuid, render_uuid, proxy_source)

    def _on_dialog_regenerate(self):
        """Handle regenerate from dialog."""
        self.representation_regenerate_requested.emit()

    def _on_dialog_clear(self):
        """Handle clear from dialog."""
        self.representation_clear_requested.emit()

    def display(self, asset: Dict[str, Any], unresolved_count: int = 0):
        """Display asset lineage info."""
        # Version label
        version_label = asset.get('version_label', 'v001')
        self._version_label.setText(version_label)

        # Variant badge
        variant_name = asset.get('variant_name', 'Base')
        if variant_name and variant_name != 'Base':
            self._variant_badge.setText(variant_name)
            self._variant_badge.show()

            # Variant set badge
            variant_set = asset.get('variant_set')
            if variant_set:
                self._variant_set_badge.setText(variant_set)
                self._variant_set_badge.show()
            else:
                self._variant_set_badge.hide()

            # Provenance
            source_name = asset.get('source_asset_name')
            source_version = asset.get('source_version_label')
            if source_name and source_version:
                self._provenance_label.setText(f"Branched from: {source_name} {source_version}")
                self._provenance_label.show()
            elif source_name:
                self._provenance_label.setText(f"Branched from: {source_name}")
                self._provenance_label.show()
            else:
                self._provenance_label.hide()
        else:
            self._variant_badge.hide()
            self._variant_set_badge.hide()
            self._provenance_label.hide()

        # Status badge
        status = asset.get('status', 'none')
        status_info = Config.LIFECYCLE_STATUSES.get(status, {'label': status.upper(), 'color': '#9E9E9E'})
        if status == 'none' or status_info.get('color') is None:
            self._status_badge.hide()
        else:
            self._status_badge.setText(status_info['label'])
            self._status_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {status_info['color']};
                    color: white;
                    padding: 2px 8px;
                    border-radius: 0px;
                    font-size: 11px;
                }}
            """)
            self._status_badge.show()

        # Representation badge
        rep_type = asset.get('representation_type', 'none')
        rep_info = Config.REPRESENTATION_TYPES.get(rep_type, {'label': rep_type.capitalize(), 'color': '#607D8B'})
        if rep_type == 'none' or rep_info.get('color') is None:
            self._rep_badge.hide()
        else:
            self._rep_badge.setText(rep_info['label'])
            self._rep_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {rep_info['color']};
                    color: white;
                    padding: 2px 8px;
                    border-radius: 0px;
                    font-size: 11px;
                }}
            """)
            self._rep_badge.show()

        # Comment indicator
        if unresolved_count > 0:
            comment_text = f"{unresolved_count} comment{'s' if unresolved_count > 1 else ''}"
            self._comment_indicator.setText(comment_text)
            self._comment_widget.show()
        else:
            self._comment_widget.hide()

        # Status indicators
        is_latest = asset.get('is_latest', 1) == 1
        is_cold = asset.get('is_cold', 0) == 1
        is_locked = asset.get('is_immutable', 0) == 1

        self._latest_indicator.setVisible(is_latest)
        self._cold_indicator.setVisible(is_cold)
        self._locked_indicator.setVisible(is_locked)

        # Check if this is a variant and if its base/source is retired
        source_uuid = asset.get('variant_source_uuid')
        if source_uuid:
            source_asset = self._db_service.get_asset_by_uuid(source_uuid)
            if source_asset and source_asset.get('is_retired', 0) == 1:
                self._retired_base_indicator.show()
            else:
                self._retired_base_indicator.hide()
        else:
            self._retired_base_indicator.hide()

        # Show representations button for mesh and rig types
        asset_type = asset.get('asset_type', '')
        self._rep_button_container.setVisible(asset_type in ('mesh', 'rig'))

        # Enable history button
        self._history_btn.setEnabled(True)

    def display_representations(self, designations: Dict[str, Any]):
        """
        Update the representation status indicators.

        Args:
            designations: Dict from RepresentationService.get_effective_designations()
        """
        self._current_designations = designations
        
        has_proxy = designations.get('has_proxy_file', False)
        has_render = designations.get('has_render_file', False)

        # Update proxy status indicator
        if has_proxy:
            self._proxy_status.setStyleSheet("""
                QLabel {
                    font-size: 10px;
                    padding: 2px 6px;
                    border-radius: 2px;
                    background: #1B5E20;
                    color: #81C784;
                }
            """)
            self._proxy_status.setText("Proxy ✓")
        else:
            self._proxy_status.setStyleSheet("""
                QLabel {
                    font-size: 10px;
                    padding: 2px 6px;
                    border-radius: 2px;
                    background: #333;
                    color: #666;
                }
            """)
            self._proxy_status.setText("Proxy")

        # Update render status indicator
        if has_render:
            self._render_status.setStyleSheet("""
                QLabel {
                    font-size: 10px;
                    padding: 2px 6px;
                    border-radius: 2px;
                    background: #1B5E20;
                    color: #81C784;
                }
            """)
            self._render_status.setText("Render ✓")
        else:
            self._render_status.setStyleSheet("""
                QLabel {
                    font-size: 10px;
                    padding: 2px 6px;
                    border-radius: 2px;
                    background: #333;
                    color: #666;
                }
            """)
            self._render_status.setText("Render")

        # Update dialog if open
        if self._representations_dialog and self._representations_dialog.isVisible():
            self._representations_dialog.populate(
                self._versions_list,
                self._custom_proxies_list,
                designations
            )

    def populate_version_dropdowns(
        self,
        versions: List[Dict[str, Any]],
        custom_proxies: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Store version and proxy data for the representations dialog.

        Args:
            versions: List of version dicts
            custom_proxies: List of custom proxy dicts
        """
        self._versions_list = versions or []
        self._custom_proxies_list = custom_proxies or []

    def clear(self):
        """Clear display."""
        self._version_label.setText("v001")
        self._variant_badge.hide()
        self._variant_set_badge.hide()
        self._provenance_label.hide()
        self._status_badge.hide()
        self._rep_badge.hide()
        self._comment_widget.hide()
        self._latest_indicator.show()
        self._cold_indicator.hide()
        self._locked_indicator.hide()
        self._retired_base_indicator.hide()
        self._rep_button_container.hide()
        self._history_btn.setEnabled(False)
        
        # Reset data
        self._versions_list = []
        self._custom_proxies_list = []
        self._current_designations = {}


__all__ = ['LineagePanel']
