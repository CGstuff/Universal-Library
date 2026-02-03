"""
AssetCardDelegate - Custom rendering for USD asset items

Pattern: QStyledItemDelegate for Model/View
Based on animation_library architecture.
"""

import math
from pathlib import Path
from typing import Optional, Dict
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PyQt6.QtCore import QSize, QRect, Qt, QPoint, QEvent, QItemSelectionModel, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QPixmap, QFont, QPen, QColor, QFontMetrics,
    QPolygonF, QBrush
)
from PyQt6.QtSvg import QSvgRenderer

from ..models.asset_list_model import AssetRole
from ..services.thumbnail_loader import get_thumbnail_loader
from ..services.user_service import get_user_service
from ..services.control_authority import get_control_authority, OperationMode
from ..config import Config

# Path to data type icons
ICONS_DIR = Path(__file__).parent.parent / "widgets" / "icons" / "data_types"
UTILITY_ICONS_DIR = Path(__file__).parent.parent / "widgets" / "icons" / "utility"

# Map asset types to SVG icon files
ASSET_TYPE_ICONS = {
    'mesh': 'mesh_data.svg',           # Mesh data type
    'model': 'mesh_data.svg',
    'material': 'material_data.svg',
    'rig': 'armature_data.svg',
    'animation': 'anim_data.svg',
    'light': 'light_data.svg',
    'camera': 'camera_data.svg',
    'environment': 'world_data.svg',
    'character': 'armature_data.svg',  # Use armature for characters (rigged)
    'vehicle': 'mesh_data.svg',        # Use mesh for vehicles
    'prop': 'object_data.svg',         # Use object for props
    'collection': 'collection.svg',    # Collection icon
    'grease_pencil': 'gp_data.svg',    # Grease Pencil data type
    'curve': 'curve_data.svg',         # Curve data type
    'scene': 'scene_data.svg',         # Scene data type
    'other': 'object_data.svg',
}


class AssetCardDelegate(QStyledItemDelegate):
    """
    Custom delegate for rendering USD asset cards in grid and list modes

    Features:
    - Grid mode: Card layout with thumbnail, name, type badge
    - List mode: Row layout with smaller thumbnail
    - Async thumbnail loading
    - Selection highlighting
    - Edit mode checkboxes
    - Favorite star
    - Asset type badges

    Usage:
        delegate = AssetCardDelegate(view_mode="grid")
        list_view.setItemDelegate(delegate)
    """

    # Theme colors (will be updated by theme manager)
    COLORS = {
        'background': '#1e1e1e',
        'background_secondary': '#2d2d2d',
        'accent': '#0078d4',
        'text_primary': '#ffffff',
        'text_secondary': '#a0a0a0',
        'border': '#404040',
        'gold': '#ffc107',
        'selection_text': '#ffffff',
    }

    # Asset type badge colors
    TYPE_COLORS = {
        'mesh': '#4CAF50',         # Green for mesh data type
        'model': '#4CAF50',
        'material': '#9C27B0',
        'rig': '#FF9800',
        'animation': '#2196F3',
        'environment': '#795548',
        'prop': '#607D8B',
        'character': '#E91E63',
        'vehicle': '#00BCD4',
        'light': '#FFD700',
        'camera': '#87CEEB',
        'collection': '#00ACC1',  # Cyan for collections
        'grease_pencil': '#66BB6A',  # Light green for Grease Pencil
        'curve': '#26C6DA',          # Cyan-teal for Curves
        'scene': '#AB47BC',          # Purple for Scenes
        'other': '#9E9E9E',
    }

    # Lifecycle status colors
    STATUS_COLORS = {
        'wip': '#FF9800',        # Orange - Work in progress
        'review': '#2196F3',     # Blue - Under review
        'approved': '#4CAF50',   # Green - Approved for use
        'deprecated': '#F44336', # Red - Deprecated
        'archived': '#9E9E9E',   # Gray - Archived
    }

    STATUS_LABELS = {
        'wip': 'WIP',
        'review': 'REV',
        'approved': 'OK',
        'deprecated': 'DEP',
        'archived': 'ARC',
    }

    # Representation type colors and labels
    REP_TYPE_COLORS = {
        'model': '#4CAF50',
        'lookdev': '#9C27B0',
        'rig': '#FF9800',
        'final': '#2196F3',
    }

    REP_TYPE_LABELS = {
        'model': 'MDL',
        'lookdev': 'LDV',
        'rig': 'RIG',
        'final': 'FNL',
    }

    # Comment badge color (for assets with unresolved review comments)
    COMMENT_BADGE_COLOR = '#E91E63'  # Pink/Magenta - distinct and attention-grabbing

    def __init__(self, parent=None, view_mode: str = "grid"):
        super().__init__(parent)
        self._view_mode = view_mode
        self._card_size = Config.DEFAULT_CARD_SIZE
        self._thumbnail_loader = get_thumbnail_loader()
        self._edit_mode = False

        # Cache for SVG renderers
        self._svg_cache: Dict[str, QSvgRenderer] = {}

        # Connect thumbnail loader signals
        self._thumbnail_loader.thumbnail_loaded.connect(self._on_thumbnail_loaded)

    def set_view_mode(self, mode: str):
        """
        Set view mode

        Args:
            mode: "grid" or "list"
        """
        if mode in ("grid", "list"):
            self._view_mode = mode

    def set_card_size(self, size: int):
        """
        Set card size for grid mode

        Args:
            size: Size in pixels
        """
        self._card_size = max(Config.MIN_CARD_SIZE, min(size, Config.MAX_CARD_SIZE))

    def set_edit_mode(self, enabled: bool):
        """
        Enable/disable edit mode

        Args:
            enabled: True to show checkboxes
        """
        self._edit_mode = enabled

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        """
        Return size hint for item

        Args:
            option: Style options
            index: Model index

        Returns:
            QSize for item
        """
        if self._view_mode == "grid":
            # Square + name below
            name_height = 28
            return QSize(self._card_size, self._card_size + name_height)
        else:
            # List mode: fixed row height
            return QSize(option.rect.width(), Config.LIST_ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        """
        Paint item

        Args:
            painter: QPainter instance
            option: Style options
            index: Model index
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._view_mode == "grid":
            self._paint_grid_mode(painter, option, index)
        else:
            self._paint_list_mode(painter, option, index)

        painter.restore()

    def editorEvent(self, event, model, option, index):
        """
        Handle mouse events for checkbox (edit mode) and favorite star

        Args:
            event: QEvent instance
            model: Model instance
            option: Style options
            index: Model index

        Returns:
            bool: True if event was handled
        """
        # Only handle mouse button release
        if event.type() != QEvent.Type.MouseButtonRelease:
            return super().editorEvent(event, model, option, index)

        rect = option.rect
        click_pos = event.position().toPoint()

        # Calculate star position based on view mode
        if self._view_mode == "grid":
            star_size = 24
            star_padding = 5
            star_rect = QRect(
                rect.x() + self._card_size - star_size - star_padding,
                rect.y() + star_padding,
                star_size,
                star_size
            )
            checkbox_size = 20
            checkbox_rect = QRect(
                rect.x() + 5,
                rect.y() + 5,
                checkbox_size,
                checkbox_size
            )
        else:
            star_size = 20
            star_padding = 8
            star_rect = QRect(
                rect.right() - star_size - star_padding,
                rect.y() + (rect.height() - star_size) // 2,
                star_size,
                star_size
            )
            checkbox_size = 20
            padding = 4
            checkbox_rect = QRect(
                rect.x() + padding,
                rect.y() + (rect.height() - checkbox_size) // 2,
                checkbox_size,
                checkbox_size
            )

        # Check favorite star click
        if star_rect.contains(click_pos):
            uuid = index.data(AssetRole.UUIDRole)
            if uuid:
                # Import here to avoid circular import
                from ..events.event_bus import get_event_bus
                get_event_bus().request_toggle_favorite.emit(uuid)
                return True

        # Check checkbox click (only in edit mode)
        if self._edit_mode and checkbox_rect.contains(click_pos):
            is_selected = option.state & QStyle.StateFlag.State_Selected

            if self.parent() and hasattr(self.parent(), 'selectionModel'):
                selection_model = self.parent().selectionModel()
                if is_selected:
                    selection_model.select(index, QItemSelectionModel.SelectionFlag.Deselect)
                else:
                    selection_model.select(index, QItemSelectionModel.SelectionFlag.Select)

            return True

        return super().editorEvent(event, model, option, index)

    def _paint_grid_mode(self, painter: QPainter, option: QStyleOptionViewItem, index):
        """Paint item in grid mode"""

        rect = option.rect
        is_selected = option.state & QStyle.StateFlag.State_Selected
        is_hovered = option.state & QStyle.StateFlag.State_MouseOver

        # Draw selection background
        if is_selected:
            painter.fillRect(rect, QColor(self.COLORS['accent']))

        # Draw thumbnail
        thumbnail_rect = QRect(rect.x(), rect.y(), self._card_size, self._card_size)
        self._draw_thumbnail(painter, thumbnail_rect, index)

        # Draw type badge (bottom-left corner, on thumbnail)
        asset_type = index.data(AssetRole.AssetTypeRole)
        if asset_type:
            self._draw_type_badge(painter, thumbnail_rect, asset_type)

        # Draw representation type badge (bottom-left, above type badge)
        rep_type = index.data(AssetRole.RepresentationTypeRole)
        if rep_type and rep_type not in ('none', 'final'):  # Hide for 'none' (no pipeline) and 'final'
            self._draw_representation_badge(painter, thumbnail_rect, rep_type)

        # Draw status badge (top-right corner, below star)
        status = index.data(AssetRole.StatusRole)
        if status:
            self._draw_status_badge(painter, thumbnail_rect, status)

        # Draw variant badge (above version badge, only if not Base)
        variant_name = index.data(AssetRole.VariantNameRole)
        if variant_name and variant_name != "Base":
            self._draw_variant_badge(painter, thumbnail_rect, variant_name)
        else:
            # For Base assets, show variant count if > 0
            variant_count = index.data(AssetRole.VariantCountRole)
            if variant_count and variant_count > 0:
                self._draw_variant_count_badge(painter, thumbnail_rect, variant_count)

        # Draw version label badge (bottom-right corner)
        version_label = index.data(AssetRole.VersionLabelRole)
        if version_label:
            self._draw_version_badge(painter, thumbnail_rect, version_label)

        # Draw cold storage indicator (snowflake icon)
        is_cold = index.data(AssetRole.IsColdRole)
        if is_cold:
            self._draw_cold_indicator(painter, thumbnail_rect)

        # Draw edit mode checkbox
        if self._edit_mode:
            checkbox_size = 20
            checkbox_rect = QRect(rect.x() + 5, rect.y() + 5, checkbox_size, checkbox_size)
            self._draw_checkbox(painter, checkbox_rect, is_selected)

        # Draw favorite star
        is_favorite = index.data(AssetRole.IsFavoriteRole)
        star_size = 24
        star_padding = 5
        star_rect = QRect(
            rect.x() + self._card_size - star_size - star_padding,
            rect.y() + star_padding,
            star_size,
            star_size
        )
        self._draw_favorite_star(painter, star_rect, is_favorite, is_hovered)

        # Draw tag count indicator (top area, after COLD badge if present)
        tags_v2 = index.data(AssetRole.TagsV2Role)
        tag_count = len(tags_v2) if tags_v2 else 0
        has_tag_badge = tag_count > 0
        if has_tag_badge:
            self._draw_tag_count(painter, thumbnail_rect, tag_count, is_cold)

        # Draw review state badge or comment badge (only in Studio/Pipeline mode)
        control_authority = get_control_authority()
        if control_authority.get_operation_mode() != OperationMode.STANDALONE:
            review_state = index.data(AssetRole.ReviewStateRole)
            unresolved_count = index.data(AssetRole.UnresolvedCommentCountRole) or 0

            if review_state:
                # Asset is in review workflow - show review state badge
                self._draw_review_state_badge(painter, thumbnail_rect, review_state,
                                              unresolved_count, is_cold, has_tag_badge, tag_count)
            elif unresolved_count > 0:
                # Legacy: assets not in review workflow but have comments
                self._draw_comment_badge(painter, thumbnail_rect, unresolved_count,
                                         is_cold, has_tag_badge, tag_count)

        # Draw text below thumbnail
        name_height = 28
        text_rect = QRect(rect.x(), rect.y() + self._card_size, self._card_size, name_height)
        self._draw_grid_text(painter, text_rect, index, is_selected)

    def _paint_list_mode(self, painter: QPainter, option: QStyleOptionViewItem, index):
        """Paint item in list mode"""

        rect = option.rect
        is_selected = option.state & QStyle.StateFlag.State_Selected
        is_hovered = option.state & QStyle.StateFlag.State_MouseOver

        # Draw background
        if is_selected:
            painter.fillRect(rect, QColor(self.COLORS['accent']))
        elif is_hovered:
            hover_color = QColor(self.COLORS['accent'])
            hover_color.setAlpha(30)
            painter.fillRect(rect, hover_color)

        # Layout
        padding = 4
        thumbnail_size = Config.LIST_ROW_HEIGHT - (padding * 2)
        checkbox_size = 20
        checkbox_offset = (checkbox_size + padding * 2) if self._edit_mode else 0

        # Draw checkbox
        if self._edit_mode:
            checkbox_rect = QRect(
                rect.x() + padding,
                rect.y() + (rect.height() - checkbox_size) // 2,
                checkbox_size,
                checkbox_size
            )
            self._draw_checkbox(painter, checkbox_rect, is_selected)

        # Draw thumbnail
        thumbnail_rect = QRect(
            rect.x() + padding + checkbox_offset,
            rect.y() + padding,
            thumbnail_size,
            thumbnail_size
        )
        self._draw_thumbnail(painter, thumbnail_rect, index)

        # Draw favorite star
        is_favorite = index.data(AssetRole.IsFavoriteRole)
        star_size = 20
        star_padding = 8
        star_rect = QRect(
            rect.right() - star_size - star_padding,
            rect.y() + (rect.height() - star_size) // 2,
            star_size,
            star_size
        )
        self._draw_favorite_star(painter, star_rect, is_favorite, is_hovered)

        # Draw text
        text_x = rect.x() + thumbnail_size + (padding * 3) + checkbox_offset
        text_rect = QRect(
            text_x,
            rect.y() + padding,
            rect.width() - text_x - star_size - star_padding - padding,
            thumbnail_size
        )
        self._draw_list_text(painter, text_rect, index, is_selected)

    def _draw_thumbnail(self, painter: QPainter, rect: QRect, index):
        """Draw thumbnail image"""

        uuid = index.data(AssetRole.UUIDRole)
        thumbnail_path = index.data(AssetRole.ThumbnailPathRole)

        if not thumbnail_path:
            self._draw_placeholder(painter, rect)
            return

        # Request thumbnail (async loading)
        pixmap = self._thumbnail_loader.request_thumbnail(
            uuid,
            thumbnail_path,
            target_size=rect.width()
        )

        if pixmap:
            # Scale and draw
            scaled = pixmap.scaled(
                rect.width(),
                rect.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )

            # Center crop if needed
            x_offset = (scaled.width() - rect.width()) // 2
            y_offset = (scaled.height() - rect.height()) // 2

            painter.drawPixmap(
                rect.x(), rect.y(),
                rect.width(), rect.height(),
                scaled,
                x_offset, y_offset,
                rect.width(), rect.height()
            )
        else:
            self._draw_loading_placeholder(painter, rect)

    def _draw_placeholder(self, painter: QPainter, rect: QRect):
        """Draw placeholder when no thumbnail"""
        painter.fillRect(rect, QColor(self.COLORS['background_secondary']))
        painter.setPen(QColor("#808080"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No Image")

    def _draw_loading_placeholder(self, painter: QPainter, rect: QRect):
        """Draw placeholder while loading"""
        painter.fillRect(rect, QColor(self.COLORS['background_secondary']))
        painter.setPen(QColor("#A0A0A0"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Loading...")

    def _get_svg_renderer(self, asset_type: str) -> Optional[QSvgRenderer]:
        """Get cached SVG renderer for asset type"""
        asset_type = asset_type.lower()

        if asset_type in self._svg_cache:
            return self._svg_cache[asset_type]

        icon_file = ASSET_TYPE_ICONS.get(asset_type, 'object_data.svg')
        icon_path = ICONS_DIR / icon_file

        if icon_path.exists():
            renderer = QSvgRenderer(str(icon_path))
            if renderer.isValid():
                self._svg_cache[asset_type] = renderer
                return renderer

        return None

    def _draw_type_badge(self, painter: QPainter, thumbnail_rect: QRect, asset_type: str):
        """Draw asset type badge with Blender SVG icon"""

        badge_color = QColor(self.TYPE_COLORS.get(asset_type.lower(), '#9E9E9E'))
        badge_size = 20
        padding = 4

        badge_rect = QRect(
            thumbnail_rect.x() + padding,
            thumbnail_rect.bottom() - badge_size - padding,
            badge_size,
            badge_size
        )

        # Draw badge background (sharp)
        painter.fillRect(badge_rect, badge_color)

        # Draw SVG icon
        self._draw_type_icon(painter, badge_rect, asset_type.lower())

    def _draw_type_icon(self, painter: QPainter, rect: QRect, asset_type: str):
        """Draw SVG icon for the asset type"""
        renderer = self._get_svg_renderer(asset_type)

        if renderer:
            # Add padding inside the badge for the icon
            icon_padding = 2
            icon_rect = QRectF(
                rect.x() + icon_padding,
                rect.y() + icon_padding,
                rect.width() - icon_padding * 2,
                rect.height() - icon_padding * 2
            )
            renderer.render(painter, icon_rect)

    def _draw_status_badge(self, painter: QPainter, thumbnail_rect: QRect, status: str):
        """Draw lifecycle status badge (top-right corner, below star)"""

        if not status or status == 'approved':
            # Don't show badge for approved assets (clean look for ready assets)
            return

        badge_text = self.STATUS_LABELS.get(status.lower(), status.upper()[:3])
        badge_color = QColor(self.STATUS_COLORS.get(status.lower(), '#9E9E9E'))

        font = QFont("Segoe UI", 6, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(badge_text)

        badge_padding = 3
        badge_height = 14
        badge_width = text_width + (badge_padding * 2)

        # Position: top-right, below the favorite star area
        badge_rect = QRect(
            thumbnail_rect.right() - badge_width - 4,
            thumbnail_rect.y() + 30,  # Below star
            badge_width,
            badge_height
        )

        # Draw badge background with slight transparency
        badge_color.setAlpha(220)
        painter.fillRect(badge_rect, badge_color)

        # Draw badge text
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

    def _draw_representation_badge(self, painter: QPainter, thumbnail_rect: QRect, rep_type: str):
        """Draw representation type badge (above type badge in bottom-left)"""

        badge_text = self.REP_TYPE_LABELS.get(rep_type.lower(), rep_type.upper()[:3])
        badge_color = QColor(self.REP_TYPE_COLORS.get(rep_type.lower(), '#607D8B'))

        font = QFont("Segoe UI", 6, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(badge_text)

        badge_padding = 3
        badge_height = 14
        badge_width = text_width + (badge_padding * 2)

        # Position: bottom-left, above the type badge (type badge is 20px + 4px padding)
        badge_rect = QRect(
            thumbnail_rect.x() + 4,
            thumbnail_rect.bottom() - badge_height - 4 - 24,  # 24px above type badge
            badge_width,
            badge_height
        )

        # Draw badge background
        badge_color.setAlpha(220)
        painter.fillRect(badge_rect, badge_color)

        # Draw badge text
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

    def _draw_version_badge(self, painter: QPainter, thumbnail_rect: QRect, version_label: str):
        """Draw version label badge (bottom-right corner)"""

        font = QFont("Segoe UI", 7, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(version_label)

        badge_padding = 4
        badge_height = 14
        badge_width = text_width + (badge_padding * 2)

        # Position: bottom-right corner
        badge_rect = QRect(
            thumbnail_rect.right() - badge_width - 4,
            thumbnail_rect.bottom() - badge_height - 4,
            badge_width,
            badge_height
        )

        # Draw badge background (dark semi-transparent)
        bg_color = QColor("#000000")
        bg_color.setAlpha(180)
        painter.fillRect(badge_rect, bg_color)

        # Draw badge text
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, version_label)

    def _draw_variant_badge(self, painter: QPainter, thumbnail_rect: QRect, variant_name: str):
        """Draw variant indicator badge (above version badge, bottom-right)"""

        font = QFont("Segoe UI", 7, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)

        # Simple "var" indicator
        display_text = "var"
        text_width = fm.horizontalAdvance(display_text)

        badge_padding = 4
        badge_height = 14
        badge_width = text_width + (badge_padding * 2)

        # Position: above version badge (bottom-right, shifted up)
        badge_rect = QRect(
            thumbnail_rect.right() - badge_width - 4,
            thumbnail_rect.bottom() - badge_height - 22,  # 22 = 14 (version badge) + 4 (gap) + 4 (margin)
            badge_width,
            badge_height
        )

        # Draw badge background (purple for variants)
        bg_color = QColor("#7B1FA2")  # Purple
        bg_color.setAlpha(220)
        painter.fillRect(badge_rect, bg_color)

        # Draw badge text
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, display_text)

    def _draw_variant_count_badge(self, painter: QPainter, thumbnail_rect: QRect, count: int):
        """Draw variant count badge for Base assets (above version badge, bottom-right)"""

        font = QFont("Segoe UI", 7, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)

        # Show count like "2 var"
        display_text = f"{count} var"
        text_width = fm.horizontalAdvance(display_text)

        badge_padding = 4
        badge_height = 14
        badge_width = text_width + (badge_padding * 2)

        # Position: above version badge (bottom-right, shifted up)
        badge_rect = QRect(
            thumbnail_rect.right() - badge_width - 4,
            thumbnail_rect.bottom() - badge_height - 22,  # 22 = 14 (version badge) + 4 (gap) + 4 (margin)
            badge_width,
            badge_height
        )

        # Draw badge background (darker purple for variant count)
        bg_color = QColor("#512DA8")  # Darker purple
        bg_color.setAlpha(220)
        painter.fillRect(badge_rect, bg_color)

        # Draw badge text
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, display_text)

    def _draw_cold_indicator(self, painter: QPainter, thumbnail_rect: QRect):
        """Draw cold storage indicator (snowflake-like icon in top-left)"""

        # Draw a blue "COLD" indicator
        font = QFont("Segoe UI", 6, QFont.Weight.Bold)
        painter.setFont(font)

        badge_text = "COLD"
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(badge_text)

        badge_padding = 3
        badge_height = 14
        badge_width = text_width + (badge_padding * 2)

        # Position: top-left corner (offset for checkbox if in edit mode)
        badge_rect = QRect(
            thumbnail_rect.x() + 30 if self._edit_mode else thumbnail_rect.x() + 4,
            thumbnail_rect.y() + 4,
            badge_width,
            badge_height
        )

        # Draw badge background (blue)
        bg_color = QColor("#1565C0")
        bg_color.setAlpha(220)
        painter.fillRect(badge_rect, bg_color)

        # Draw badge text
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

    def _draw_tag_count(self, painter: QPainter, thumbnail_rect: QRect, count: int, has_cold_badge: bool):
        """Draw tag count indicator (small number badge)"""

        font = QFont("Segoe UI", 7, QFont.Weight.Bold)
        painter.setFont(font)

        badge_text = str(count)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(badge_text)

        # Badge size - circular for single digit, pill for multiple
        badge_height = 14
        badge_width = max(badge_height, text_width + 6)

        # Position: top-left, offset if edit mode checkbox or COLD badge present
        x_offset = 4
        if self._edit_mode:
            x_offset += 26
        if has_cold_badge:
            x_offset += 38  # After COLD badge

        badge_rect = QRect(
            thumbnail_rect.x() + x_offset,
            thumbnail_rect.y() + 4,
            badge_width,
            badge_height
        )

        # Draw badge background (sharp, subtle grey-blue)
        bg_color = QColor("#546E7A")
        bg_color.setAlpha(220)
        painter.fillRect(badge_rect, bg_color)

        # Draw tag icon (simple label shape) and count
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, f"#{badge_text}")

    def _get_info_icon_renderer(self) -> Optional[QSvgRenderer]:
        """Get cached SVG renderer for info icon"""
        if 'info_icon' in self._svg_cache:
            return self._svg_cache['info_icon']

        icon_path = UTILITY_ICONS_DIR / 'info.svg'
        if icon_path.exists():
            renderer = QSvgRenderer(str(icon_path))
            if renderer.isValid():
                self._svg_cache['info_icon'] = renderer
                return renderer
        return None

    def _draw_comment_badge(self, painter: QPainter, thumbnail_rect: QRect, count: int,
                            has_cold_badge: bool, has_tag_badge: bool, tag_count: int = 0):
        """Draw comment count indicator badge (for unresolved review comments)"""

        if count <= 0:
            return

        # Icon and text sizing
        icon_size = 18
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)

        # Calculate dimensions
        count_text = str(count)
        text_width = fm.horizontalAdvance(count_text)
        total_width = icon_size + 2 + text_width  # icon + gap + text

        # Position: top-left, after other badges (checkbox, COLD, tags)
        x_offset = 4
        if self._edit_mode:
            x_offset += 26
        if has_cold_badge:
            x_offset += 38  # After COLD badge
        if has_tag_badge:
            # Calculate tag badge width
            tag_text = f"#{tag_count}"
            tag_width = max(14, fm.horizontalAdvance(tag_text) + 6)
            x_offset += tag_width + 4  # After tag badge + spacing

        # Draw info icon
        renderer = self._get_info_icon_renderer()
        if renderer:
            icon_rect = QRectF(
                thumbnail_rect.x() + x_offset,
                thumbnail_rect.y() + 4,
                icon_size,
                icon_size
            )
            renderer.render(painter, icon_rect)

        # Draw count text (white with slight shadow for visibility)
        text_x = thumbnail_rect.x() + x_offset + icon_size + 2
        text_y = thumbnail_rect.y() + 4 + (icon_size + fm.ascent()) // 2 - 2

        # Shadow for readability
        painter.setPen(QColor(0, 0, 0, 180))
        painter.drawText(int(text_x + 1), int(text_y + 1), count_text)

        # Main text
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(int(text_x), int(text_y), count_text)

    def _draw_review_state_badge(self, painter: QPainter, thumbnail_rect: QRect,
                                  review_state: str, comment_count: int,
                                  has_cold_badge: bool, has_tag_badge: bool, tag_count: int = 0):
        """
        Draw review workflow state badge.

        Shows different colored badges based on review state:
        - needs_review: Blue badge with "REV" (waiting for lead)
        - in_review: Orange badge with "REV" + comment count
        - in_progress: Cyan badge with "WIP" (artist working on fixes)
        - approved: Green badge with "OK"
        - final: Purple badge with "FNL"
        """
        # Get badge config from Config.REVIEW_STATES
        state_config = Config.REVIEW_STATES.get(review_state)
        if not state_config or not state_config.get('color'):
            return

        badge_color = state_config['color']
        badge_text = state_config.get('badge', 'REV')

        # For in_review, append comment count
        if review_state == 'in_review' and comment_count > 0:
            badge_text = f"{badge_text}:{comment_count}"

        # Font for badge text
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)

        # Calculate badge dimensions
        text_width = fm.horizontalAdvance(badge_text)
        badge_width = max(text_width + 8, 28)  # Min width 28px
        badge_height = 16

        # Position: top-left, after other badges (checkbox, COLD, tags)
        x_offset = 4
        if self._edit_mode:
            x_offset += 26
        if has_cold_badge:
            x_offset += 38  # After COLD badge
        if has_tag_badge:
            # Calculate tag badge width
            tag_text = f"#{tag_count}"
            tag_width = max(14, fm.horizontalAdvance(tag_text) + 6)
            x_offset += tag_width + 4  # After tag badge + spacing

        badge_x = thumbnail_rect.x() + x_offset
        badge_y = thumbnail_rect.y() + 4

        # Draw badge background (rounded rectangle)
        badge_rect = QRectF(badge_x, badge_y, badge_width, badge_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(badge_color))
        painter.drawRoundedRect(badge_rect, 3, 3)

        # Draw badge text (white, centered)
        painter.setPen(QColor("#FFFFFF"))
        text_x = badge_x + (badge_width - text_width) / 2
        text_y = badge_y + (badge_height + fm.ascent() - fm.descent()) / 2 - 1
        painter.drawText(int(text_x), int(text_y), badge_text)

    def _draw_checkbox(self, painter: QPainter, rect: QRect, is_checked: bool):
        """Draw edit mode checkbox"""

        bg_color = QColor(self.COLORS['accent']) if is_checked else QColor(self.COLORS['background_secondary'])
        painter.fillRect(rect, bg_color)

        pen = QPen(QColor(self.COLORS['border']), 2)
        painter.setPen(pen)
        painter.drawRect(rect)

        if is_checked:
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.drawLine(
                rect.x() + 4, rect.y() + rect.height() // 2,
                rect.x() + rect.width() // 3, rect.y() + rect.height() - 4
            )
            painter.drawLine(
                rect.x() + rect.width() // 3, rect.y() + rect.height() - 4,
                rect.x() + rect.width() - 4, rect.y() + 4
            )

    def _draw_favorite_star(self, painter: QPainter, rect: QRect, is_favorite: bool, is_hovered: bool):
        """Draw favorite star icon"""

        cx, cy = rect.center().x(), rect.center().y()
        outer_radius = rect.width() / 2.0 - 2
        inner_radius = outer_radius * 0.4

        points = []
        for i in range(10):
            angle = (i * 36 - 90) * math.pi / 180
            radius = outer_radius if i % 2 == 0 else inner_radius
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            points.append(QPointF(x, y))

        star_polygon = QPolygonF(points)

        if is_favorite:
            painter.setBrush(QBrush(QColor(self.COLORS['gold'])))
            painter.setPen(QPen(QColor(self.COLORS['gold']), 1))
        else:
            if is_hovered:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#FFFFFF"), 2))
            else:
                color = QColor("#FFFFFF")
                color.setAlpha(80)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(color, 1))

        painter.drawPolygon(star_polygon)

    def _draw_grid_text(self, painter: QPainter, rect: QRect, index, is_selected: bool):
        """Draw text for grid mode (below thumbnail)"""

        name = index.data(AssetRole.NameRole)
        if not name:
            return

        # Background for non-selected (30% opacity like animation_library)
        if not is_selected:
            bg_color = QColor(self.COLORS['background_secondary'])
            bg_color.setAlpha(77)  # 30% opacity (0.30 * 255 = 77)
            painter.fillRect(rect, bg_color)

        # Font
        font = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        painter.setFont(font)

        # Color
        if is_selected:
            painter.setPen(QColor(self.COLORS['selection_text']))
        else:
            painter.setPen(QColor(self.COLORS['text_primary']))

        # Draw name (elided)
        fm = QFontMetrics(font)
        elided_name = fm.elidedText(name, Qt.TextElideMode.ElideRight, rect.width() - 8)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, elided_name)

    def _draw_list_text(self, painter: QPainter, rect: QRect, index, is_selected: bool):
        """Draw text for list mode"""

        name = index.data(AssetRole.NameRole)
        asset_type = index.data(AssetRole.AssetTypeRole)
        polygon_count = index.data(AssetRole.PolygonCountRole)
        file_size = index.data(AssetRole.FileSizeMBRole)
        status = index.data(AssetRole.StatusRole)
        version_label = index.data(AssetRole.VersionLabelRole)
        rep_type = index.data(AssetRole.RepresentationTypeRole)
        is_cold = index.data(AssetRole.IsColdRole)

        # Draw asset type icon first (inline with name)
        icon_size = 16
        icon_x = rect.x()
        if asset_type:
            badge_color = QColor(self.TYPE_COLORS.get(asset_type.lower(), '#9E9E9E'))
            icon_rect = QRect(icon_x, rect.y() + 2, icon_size, icon_size)
            painter.setBrush(QBrush(badge_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(icon_rect, 2, 2)
            # Draw SVG icon
            self._draw_type_icon(painter, icon_rect, asset_type.lower())
            icon_x += icon_size + 6

        # Name (bold)
        font_bold = QFont("Segoe UI", 10)
        font_bold.setBold(True)
        painter.setFont(font_bold)

        if is_selected:
            painter.setPen(QColor(self.COLORS['selection_text']))
        else:
            painter.setPen(QColor(self.COLORS['text_primary']))

        name_rect = QRect(icon_x, rect.y(), rect.width() - (icon_x - rect.x()), 20)
        fm = QFontMetrics(font_bold)
        elided_name = fm.elidedText(name or "Unknown", Qt.TextElideMode.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_name)

        # Draw inline badges next to name
        badge_x = icon_x + fm.horizontalAdvance(elided_name) + 8
        font_badge = QFont("Segoe UI", 6, QFont.Weight.Bold)
        painter.setFont(font_badge)
        badge_fm = QFontMetrics(font_badge)

        # Cold storage badge
        if is_cold:
            cold_text = "COLD"
            cold_width = badge_fm.horizontalAdvance(cold_text) + 6
            cold_rect = QRect(badge_x, rect.y() + 4, cold_width, 12)
            painter.fillRect(cold_rect, QColor("#1565C0"))
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(cold_rect, Qt.AlignmentFlag.AlignCenter, cold_text)
            badge_x += cold_width + 4

        # Status badge (if not approved)
        if status and status != 'approved':
            status_text = self.STATUS_LABELS.get(status.lower(), status.upper()[:3])
            status_color = QColor(self.STATUS_COLORS.get(status.lower(), '#9E9E9E'))
            status_width = badge_fm.horizontalAdvance(status_text) + 6

            status_rect = QRect(badge_x, rect.y() + 4, status_width, 12)
            painter.fillRect(status_rect, status_color)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(status_rect, Qt.AlignmentFlag.AlignCenter, status_text)
            badge_x += status_width + 4

        # Representation badge (hide for 'none' and 'final')
        if rep_type and rep_type not in ('none', 'final'):
            rep_text = self.REP_TYPE_LABELS.get(rep_type.lower(), rep_type.upper()[:3])
            rep_color = QColor(self.REP_TYPE_COLORS.get(rep_type.lower(), '#607D8B'))
            rep_width = badge_fm.horizontalAdvance(rep_text) + 6

            rep_rect = QRect(badge_x, rect.y() + 4, rep_width, 12)
            painter.fillRect(rep_rect, rep_color)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(rep_rect, Qt.AlignmentFlag.AlignCenter, rep_text)

        # Metadata (smaller)
        font_small = QFont("Segoe UI", 8)
        painter.setFont(font_small)

        if is_selected:
            painter.setPen(QColor(self.COLORS['selection_text']))
        else:
            painter.setPen(QColor(self.COLORS['text_secondary']))

        metadata_parts = []
        # Asset type is now shown as icon, no need for text
        # Show variant name if not Base
        variant_name = index.data(AssetRole.VariantNameRole)
        if variant_name and variant_name != "Base":
            metadata_parts.append(f"[{variant_name}]")
        if version_label:
            metadata_parts.append(version_label)
        if polygon_count:
            metadata_parts.append(f"{polygon_count:,} polys")
        if file_size:
            metadata_parts.append(f"{file_size:.1f} MB")

        metadata_text = " | ".join(metadata_parts)
        # Align metadata with name (after icon)
        metadata_start_x = rect.x() + (icon_size + 6 if asset_type else 0)
        metadata_rect = QRect(metadata_start_x, rect.y() + 22, rect.width() - (metadata_start_x - rect.x()), 18)
        painter.drawText(metadata_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, metadata_text)

    def _on_thumbnail_loaded(self, uuid: str, pixmap: QPixmap):
        """Handle thumbnail loaded signal"""
        if self.parent() and hasattr(self.parent(), 'viewport'):
            self.parent().viewport().update()


__all__ = ['AssetCardDelegate']
