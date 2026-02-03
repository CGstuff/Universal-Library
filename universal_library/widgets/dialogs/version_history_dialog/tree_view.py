"""
Tree view for version history dialog.

Displays variant hierarchy with branch points.
"""

from typing import Dict, List, Any, Optional, Callable

from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QWidget, QHBoxLayout, QLabel
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QBrush, QIcon, QPixmap

from .config import VersionHistoryConfig, THUMBNAIL_UUID_ROLE
from ....config import Config, REVIEW_CYCLE_TYPES
from ....services.review_database import get_review_database
from ....services.review_state_manager import get_review_state_manager


class VersionTreeView:
    """
    Manages tree view display for version history.

    Features:
    - Variant hierarchy with branch points
    - Hide intermediate versions filter
    - Search filter for variants
    - Review badges
    """

    def __init__(
        self,
        tree: QTreeWidget,
        thumbnail_loader,
        on_thumbnail_request: Callable[[str, str, QTreeWidgetItem], None] = None
    ):
        """
        Initialize tree view manager.

        Args:
            tree: QTreeWidget to manage
            thumbnail_loader: Thumbnail loader service
            on_thumbnail_request: Callback to request thumbnail
        """
        self._tree = tree
        self._thumbnail_loader = thumbnail_loader
        self._on_thumbnail_request = on_thumbnail_request

        self._all_variants_data: List[Dict[str, Any]] = []
        self._hide_intermediate = False
        self._search_filter = ""
        self._show_version_thumbnails = True

    def set_data(self, all_variants_data: List[Dict[str, Any]]):
        """Set the variant data to display."""
        self._all_variants_data = all_variants_data

    def set_hide_intermediate(self, hide: bool):
        """Set whether to hide intermediate versions."""
        self._hide_intermediate = hide

    def set_search_filter(self, text: str):
        """Set search filter for variant names."""
        self._search_filter = text.lower().strip()

    def set_show_thumbnails(self, show: bool):
        """Set whether to show version thumbnails."""
        self._show_version_thumbnails = show

    def populate(self):
        """Populate the tree view with variant hierarchy."""
        self._tree.clear()

        if not self._all_variants_data:
            return

        # Get Base variant versions first
        base_versions = [v for v in self._all_variants_data if v.get('_variant_name') == 'Base']
        base_versions.sort(key=lambda x: x.get('version', 1))

        # Get all non-Base variants
        non_base_variants = {}
        for v in self._all_variants_data:
            vname = v.get('_variant_name', 'Base')
            if vname != 'Base':
                if self._search_filter and self._search_filter not in vname.lower():
                    continue
                if vname not in non_base_variants:
                    non_base_variants[vname] = []
                non_base_variants[vname].append(v)

        # Sort each variant's versions
        for vname in non_base_variants:
            non_base_variants[vname].sort(key=lambda x: x.get('version', 1))

        # Determine if Base should be shown
        show_base = True
        if self._search_filter:
            show_base = "base" in self._search_filter or len(non_base_variants) > 0

        # Build branch points map
        branch_points = {}
        for vname, versions in non_base_variants.items():
            if versions:
                source_uuid = versions[0].get('variant_source_uuid')
                if source_uuid:
                    if source_uuid not in branch_points:
                        branch_points[source_uuid] = []
                    branch_points[source_uuid].append((vname, versions))

        # Create Base node as root
        if base_versions and show_base:
            self._create_base_node(base_versions, branch_points, non_base_variants)

        self._tree.expandAll()

        # Deferred badge widget creation
        QTimer.singleShot(50, self._create_deferred_badge_widgets)

    def _create_base_node(
        self,
        base_versions: List[Dict[str, Any]],
        branch_points: Dict[str, List],
        non_base_variants: Dict[str, List]
    ):
        """Create Base root node with versions."""
        first_base = base_versions[0]
        latest_base = next((v for v in base_versions if v.get('is_latest', 0) == 1), base_versions[-1])

        base_node = QTreeWidgetItem(self._tree)
        base_node.setText(0, f"Base ({first_base.get('name', 'Unknown')})")
        base_node.setText(1, "")
        base_node.setText(2, "")
        base_node.setText(3, "")
        base_node.setText(4, "")
        base_node.setData(0, Qt.ItemDataRole.UserRole, None)
        base_node.setExpanded(True)

        # Load thumbnail for Base header
        thumb_path = latest_base.get('thumbnail_path')
        if thumb_path and self._on_thumbnail_request:
            base_node.setData(0, THUMBNAIL_UUID_ROLE, latest_base.get('uuid'))
            self._on_thumbnail_request(latest_base.get('uuid'), thumb_path, base_node)

        # Add Base version nodes
        for base_ver in base_versions:
            uuid = base_ver.get('uuid')
            is_branch_point = uuid in branch_points

            if self._hide_intermediate:
                is_latest = base_ver.get('is_latest', 0) == 1
                if not (is_branch_point or is_latest):
                    continue

            ver_node = self._create_version_node(base_node, base_ver)

            if is_branch_point:
                for vname, variant_versions in branch_points[uuid]:
                    self._create_variant_branch(ver_node, vname, variant_versions)

    def _create_variant_branch(
        self,
        parent_node: QTreeWidgetItem,
        variant_name: str,
        variant_versions: List[Dict[str, Any]]
    ):
        """Create a variant branch node with its versions."""
        variant_set = variant_versions[0].get('variant_set', 'Default')
        variant_node = QTreeWidgetItem(parent_node)
        variant_node.setText(0, variant_name)
        variant_node.setText(1, "")
        variant_node.setText(2, "")
        variant_node.setText(3, "")
        variant_node.setText(4, variant_set)
        variant_node.setData(0, Qt.ItemDataRole.UserRole, None)
        variant_node.setForeground(0, QBrush(QColor("#7B1FA2")))
        variant_node.setExpanded(True)

        # Load thumbnail for variant header
        if variant_versions:
            latest_variant = next(
                (v for v in variant_versions if v.get('is_latest', 0) == 1),
                variant_versions[-1]
            )
            vthumb = latest_variant.get('thumbnail_path')
            if vthumb and self._on_thumbnail_request:
                variant_node.setData(0, THUMBNAIL_UUID_ROLE, latest_variant.get('uuid'))
                self._on_thumbnail_request(latest_variant.get('uuid'), vthumb, variant_node)

        # Add variant version nodes
        for vv in variant_versions:
            if self._hide_intermediate:
                if not vv.get('is_latest', 0) == 1:
                    continue
            self._create_version_node(variant_node, vv)

    def _create_version_node(
        self,
        parent: QTreeWidgetItem,
        version: Dict[str, Any]
    ) -> QTreeWidgetItem:
        """Create a tree node for a version."""
        status_colors = Config.LIFECYCLE_STATUSES

        node = QTreeWidgetItem(parent)
        version_label = version.get('version_label', f"v{version.get('version', 1):03d}")
        uuid = version.get('uuid')

        # Build display label
        indicators = []
        is_latest = version.get('is_latest', 0) == 1
        is_cold = version.get('is_cold', 0) == 1
        is_locked = version.get('is_immutable', 0) == 1
        is_retired = version.get('is_retired', 0) == 1

        if is_retired:
            indicators.append("RETIRED")
        if is_latest:
            indicators.append("latest")
        if is_cold:
            indicators.append("cold")
        if is_locked:
            indicators.append("locked")

        display = version_label
        if indicators:
            display += f" ({', '.join(indicators)})"

        # Add X mark prefix for retired versions
        if is_retired:
            display = f"✗ {display}"

        node.setText(0, display)
        node.setText(1, version_label)

        # Status
        status = version.get('status', 'wip')
        status_info = status_colors.get(status, {'label': status.upper(), 'color': '#9E9E9E'})
        node.setText(2, status_info['label'])
        node.setForeground(2, QBrush(QColor(status_info['color'])))

        # Review badge data
        self._set_review_badge_data(node, version, uuid, version_label)

        # VariantSet (only for non-Base)
        variant_name = version.get('_variant_name', 'Base')
        if variant_name != 'Base':
            node.setText(4, version.get('variant_set', ''))

        # Store UUID for selection
        node.setData(0, Qt.ItemDataRole.UserRole, uuid)

        # Highlight retired (brown/gray background, dimmed text)
        if is_retired:
            for col in range(5):
                node.setBackground(col, QBrush(QColor(121, 85, 72, 40)))  # Brown tint
                node.setForeground(col, QBrush(QColor("#888888")))  # Gray text
        # Highlight latest (only if not retired)
        elif is_latest:
            for col in range(5):
                node.setBackground(col, QBrush(QColor(76, 175, 80, 30)))

        # Load thumbnail
        if self._show_version_thumbnails and self._on_thumbnail_request:
            thumb_path = version.get('thumbnail_path')
            if thumb_path:
                self._on_thumbnail_request(uuid, thumb_path, node)

        return node

    def _set_review_badge_data(
        self,
        node: QTreeWidgetItem,
        version: Dict[str, Any],
        uuid: str,
        version_label: str
    ):
        """Set review badge data on tree node for deferred widget creation."""
        review_db = get_review_database()
        state_manager = get_review_state_manager()

        # Use version_group_id for cycle lookup since cycles are stored with that identifier
        version_group_id = version.get('version_group_id') or version.get('asset_id') or uuid
        cycle = state_manager.get_cycle_for_version(version_group_id, version_label)
        if cycle:
            cycle_type = cycle.get('cycle_type', 'general')
            cycle_info = REVIEW_CYCLE_TYPES.get(cycle_type, {})
            cycle_label = cycle_info.get('label', cycle_type.title())
            cycle_color = cycle_info.get('color', '#607D8B')
            cycle_state = cycle.get('review_state', 'needs_review')
            is_final = cycle_state == 'final'
            note_counts = review_db.get_cycle_note_counts(cycle.get('id'))
        else:
            cycle_label = None
            cycle_color = None
            cycle_state = None
            is_final = False
            note_counts = review_db.get_note_status_counts(uuid, version_label)

        total_notes = note_counts.get('total', 0)

        if total_notes > 0 or cycle_label:
            version_group_id = version.get('version_group_id') or version.get('asset_id') or uuid
            node.setData(3, Qt.ItemDataRole.UserRole + 10, {
                'open': note_counts.get('open', 0),
                'addressed': note_counts.get('addressed', 0),
                'approved': note_counts.get('approved', 0),
                'cycle_label': cycle_label,
                'cycle_color': cycle_color,
                'cycle_state': cycle_state,
                'is_final': is_final,
                'uuid': uuid,
                'version_label': version_label,
                'version_group_id': version_group_id,
                'cycle_id': cycle.get('id') if cycle else None
            })

    def _create_deferred_badge_widgets(self):
        """Create badge widgets for all nodes after tree is fully built."""
        def process_node(item: QTreeWidgetItem):
            badge_data = item.data(3, Qt.ItemDataRole.UserRole + 10)
            if badge_data:
                self._create_badge_widget(item, badge_data)

            for i in range(item.childCount()):
                process_node(item.child(i))

        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            process_node(root.child(i))

    def _create_badge_widget(self, item: QTreeWidgetItem, badge_data: dict):
        """Create badge widget for a tree item."""
        open_count = badge_data.get('open', 0)
        addressed_count = badge_data.get('addressed', 0)
        approved_count = badge_data.get('approved', 0)
        cycle_label = badge_data.get('cycle_label')
        cycle_color = badge_data.get('cycle_color')
        cycle_state = badge_data.get('cycle_state')
        is_final = badge_data.get('is_final', False)

        badge_widget = QWidget()
        badge_widget.setStyleSheet("background: transparent;")
        badge_layout = QHBoxLayout(badge_widget)
        badge_layout.setContentsMargins(4, 0, 0, 0)
        badge_layout.setSpacing(2)

        # Cycle badge
        if cycle_label:
            cycle_badge = QLabel(cycle_label)
            if is_final:
                cycle_badge.setStyleSheet(f"""
                    background: #333;
                    color: {cycle_color};
                    padding: 1px 6px;
                    border-radius: 3px;
                    font-size: 10px;
                    font-weight: bold;
                """)
                cycle_badge.setToolTip(f"{cycle_label} cycle (Final)")
            else:
                cycle_badge.setStyleSheet(f"""
                    background: {cycle_color};
                    color: white;
                    padding: 1px 6px;
                    border-radius: 3px;
                    font-size: 10px;
                    font-weight: bold;
                """)
                state_labels = {
                    'needs_review': 'Needs Review',
                    'in_review': 'In Review',
                    'in_progress': 'In Progress',
                    'approved': 'Approved'
                }
                state_label = state_labels.get(cycle_state, cycle_state)
                cycle_badge.setToolTip(f"{cycle_label} cycle: {state_label}")
            badge_layout.addWidget(cycle_badge)
            badge_layout.addSpacing(6)

        def add_count_badge(count: int, color: str, tooltip: str):
            if count > 0:
                dot = QLabel("\u25cf")
                dot.setStyleSheet(f"color: {color}; font-size: 10px;")
                dot.setToolTip(tooltip)
                badge_layout.addWidget(dot)

                num_label = QLabel(str(count))
                num_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
                num_label.setToolTip(tooltip)
                badge_layout.addWidget(num_label)
                badge_layout.addSpacing(4)

        add_count_badge(open_count, "#FF9800", f"{open_count} open (awaiting fix)")
        add_count_badge(addressed_count, "#00BCD4", f"{addressed_count} addressed (awaiting approval)")
        add_count_badge(approved_count, "#4CAF50", f"{approved_count} approved")

        badge_layout.addStretch()
        self._tree.setItemWidget(item, 3, badge_widget)

    def on_thumbnail_loaded(self, uuid: str, pixmap: QPixmap):
        """Handle thumbnail loaded for tree view."""
        def find_and_set(item):
            for i in range(item.childCount()):
                child = item.child(i)
                item_uuid = child.data(0, Qt.ItemDataRole.UserRole)
                thumb_uuid = child.data(0, THUMBNAIL_UUID_ROLE)
                if item_uuid == uuid or thumb_uuid == uuid:
                    child.setIcon(0, QIcon(pixmap))
                find_and_set(child)

        root = self._tree.invisibleRootItem()
        find_and_set(root)


__all__ = ['VersionTreeView']
