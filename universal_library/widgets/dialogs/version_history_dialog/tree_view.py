"""
Tree view for version history dialog.

Displays variant hierarchy with branch points.
"""

from typing import Dict, List, Any, Optional, Callable

from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QStyledItemDelegate, QStyle,
    QStyleOptionViewItem, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QIcon, QPixmap

from .config import VersionHistoryConfig, THUMBNAIL_UUID_ROLE
from ....config import Config
from ....services.version_diff import compute_version_diff


class _DiffColorDelegate(QStyledItemDelegate):
    """Item delegate that honors per-item foreground color even when a global
    QSS rule (QTreeView::item { color: ... }) would otherwise override
    QTreeWidgetItem.setForeground. Used for inline diff child rows so each row
    can render in green/red/blue.

    Default rendering is preserved for items without an explicit foreground
    brush (i.e. all the normal variant/version rows).
    """

    def paint(self, painter, option, index):
        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        if brush is None:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""  # we'll draw the text ourselves below

        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, opt, widget
        )
        color = brush.color() if isinstance(brush, QBrush) else QColor(brush)

        painter.save()
        painter.setPen(color)
        painter.setFont(opt.font)
        elided = opt.fontMetrics.elidedText(
            text, Qt.TextElideMode.ElideRight, text_rect.width()
        )
        align = int(opt.displayAlignment) or int(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        painter.drawText(text_rect, align, elided)
        painter.restore()


class VersionTreeView:
    """
    Manages tree view display for version history.

    Features:
    - Variant hierarchy with branch points
    - Hide intermediate versions filter
    - Search filter for variants
    - Optional inline diff rows under each version
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
        self._show_diff = False

        # Install a delegate so per-item foreground colors on the inline diff
        # rows aren't clobbered by the global QSS rule on QTreeView::item.
        self._diff_delegate = _DiffColorDelegate(self._tree)
        self._tree.setItemDelegate(self._diff_delegate)

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

    def set_show_diff(self, show: bool):
        """Set whether to inject inline diff child rows under each version."""
        self._show_diff = show

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
        variant_node.setText(3, variant_set)
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

        # VariantSet (only for non-Base)
        variant_name = version.get('_variant_name', 'Base')
        if variant_name != 'Base':
            node.setText(3, version.get('variant_set', ''))

        # Store UUID for selection
        node.setData(0, Qt.ItemDataRole.UserRole, uuid)

        # Highlight retired (brown/gray background, dimmed text)
        if is_retired:
            for col in range(4):
                node.setBackground(col, QBrush(QColor(121, 85, 72, 40)))  # Brown tint
                node.setForeground(col, QBrush(QColor("#888888")))  # Gray text
        # Highlight latest (only if not retired)
        elif is_latest:
            for col in range(4):
                node.setBackground(col, QBrush(QColor(76, 175, 80, 30)))

        # Load thumbnail
        if self._show_version_thumbnails and self._on_thumbnail_request:
            thumb_path = version.get('thumbnail_path')
            if thumb_path:
                self._on_thumbnail_request(uuid, thumb_path, node)

        # Inline diff child row (if Show Diff toggle is on)
        if self._show_diff:
            self._append_diff_child(node, version)

        return node

    # Colors for inline diff rows. Match the preview panel's Surface A palette.
    _DIFF_COLOR_ADDED = QColor("#4CAF50")    # green
    _DIFF_COLOR_REMOVED = QColor("#F44336")  # red
    _DIFF_COLOR_CHANGED = QColor("#90A4AE")  # gray-blue
    _DIFF_COLOR_DIM = QColor("#666666")      # initial / no-changes

    # Max diff entries shown per version. Beyond this, last row says "+N more".
    _DIFF_INLINE_LIMIT = 5

    def _append_diff_child(self, parent_node: QTreeWidgetItem, version: Dict[str, Any]):
        """Inject non-selectable child rows beneath the version row, one per
        change, each colored by its change type (green/red/blue)."""
        prev_version = self._find_previous_version(version)
        result = compute_version_diff(prev_version, version)

        # Initial version or no changes — one dim row
        if result.is_initial:
            self._add_diff_row(parent_node, "(initial version)", self._DIFF_COLOR_DIM)
            parent_node.setExpanded(True)
            return
        if not result.has_changes():
            self._add_diff_row(parent_node, "— no changes —", self._DIFF_COLOR_DIM)
            parent_node.setExpanded(True)
            return

        # One row per change, colored by type, capped at _DIFF_INLINE_LIMIT
        top = result.top_changes(self._DIFF_INLINE_LIMIT)
        for fd in top:
            color = {
                'added': self._DIFF_COLOR_ADDED,
                'removed': self._DIFF_COLOR_REMOVED,
            }.get(fd.change_type, self._DIFF_COLOR_CHANGED)
            self._add_diff_row(parent_node, fd.format_short(), color)

        remaining = len(result.fields) - len(top)
        if remaining > 0:
            self._add_diff_row(
                parent_node,
                f"+{remaining} more change(s) — see preview",
                self._DIFF_COLOR_DIM,
            )

        parent_node.setExpanded(True)

    def _add_diff_row(self, parent_node: QTreeWidgetItem, text: str, color: QColor):
        """Add one non-selectable italic child row with the given text + color."""
        child = QTreeWidgetItem(parent_node)
        child.setText(0, text)
        # Non-selectable, non-focusable — purely informational
        child.setFlags(Qt.ItemFlag.ItemIsEnabled)
        # Italic, slightly smaller, colored only on the text column (0).
        # Other columns stay empty so the colored line reads as a single fragment.
        font = child.font(0)
        font.setItalic(True)
        font.setPointSize(max(8, font.pointSize() - 1))
        child.setFont(0, font)
        child.setForeground(0, QBrush(color))

    def _find_previous_version(self, version: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find the version immediately preceding `version` in the same variant."""
        target_variant = version.get('variant_name') or version.get('_variant_name', 'Base')
        target_num = version.get('version', 0) or 0
        prev = None
        prev_num = -1
        for v in self._all_variants_data:
            vname = v.get('variant_name') or v.get('_variant_name', 'Base')
            if vname != target_variant:
                continue
            vnum = v.get('version', 0) or 0
            if vnum >= target_num:
                continue
            if vnum > prev_num:
                prev = v
                prev_num = vnum
        return prev

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
