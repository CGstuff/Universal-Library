"""
AssetTreeDelegate - Card-style painting for tree view rows

Pattern: QStyledItemDelegate for QTreeView
Draws card-style rows with thumbnail, name, badges for both parent (base) and child (variant) rows.
"""

from pathlib import Path
from typing import Optional, Dict
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PyQt6.QtCore import QSize, QRect, Qt, QRectF
from PyQt6.QtGui import (
    QPainter, QFont, QColor, QFontMetrics, QBrush, QPen
)
from PyQt6.QtSvg import QSvgRenderer

from ..models.asset_tree_model import TREE_ASSET_ROLE, TREE_IS_PARENT
from ..services.thumbnail_loader import get_thumbnail_loader
from ..config import Config

# Reuse icon paths from card delegate
ICONS_DIR = Path(__file__).parent.parent / "widgets" / "icons" / "data_types"

ASSET_TYPE_ICONS = {
    'mesh': 'mesh_data.svg',
    'model': 'mesh_data.svg',
    'material': 'material_data.svg',
    'rig': 'armature_data.svg',
    'animation': 'anim_data.svg',
    'light': 'light_data.svg',
    'camera': 'camera_data.svg',
    'environment': 'world_data.svg',
    'character': 'armature_data.svg',
    'vehicle': 'mesh_data.svg',
    'prop': 'object_data.svg',
    'collection': 'collection.svg',
    'grease_pencil': 'gp_data.svg',
    'curve': 'curve_data.svg',
    'scene': 'scene_data.svg',
    'other': 'object_data.svg',
}

# Colors (matching AssetCardDelegate)
COLORS = {
    'background': '#1e1e1e',
    'background_secondary': '#2d2d2d',
    'accent': '#0078d4',
    'text_primary': '#ffffff',
    'text_secondary': '#a0a0a0',
    'border': '#404040',
    'gold': '#ffc107',
}

TYPE_COLORS = {
    'mesh': '#4CAF50',
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
    'collection': '#00ACC1',
    'grease_pencil': '#66BB6A',
    'curve': '#26C6DA',
    'scene': '#AB47BC',
    'other': '#9E9E9E',
}

STATUS_COLORS = {
    'wip': '#FF9800',
    'review': '#2196F3',
    'approved': '#4CAF50',
    'deprecated': '#F44336',
    'archived': '#9E9E9E',
}

STATUS_LABELS = {
    'wip': 'WIP',
    'review': 'REV',
    'approved': 'OK',
    'deprecated': 'DEP',
    'archived': 'ARC',
}


class AssetTreeDelegate(QStyledItemDelegate):
    """
    Custom delegate for rendering asset rows in the tree view.

    Parent rows (Base assets): Full-height card with thumbnail, name, type badge,
    status badge, variant count.

    Child rows (Variants): Slightly smaller card with thumbnail, name, variant
    name badge, status badge.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumbnail_loader = get_thumbnail_loader()
        self._svg_cache: Dict[str, QSvgRenderer] = {}

        self._thumbnail_loader.thumbnail_loaded.connect(self._on_thumbnail_loaded)

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        is_parent = index.data(TREE_IS_PARENT)
        if is_parent:
            return QSize(option.rect.width(), Config.TREE_ROW_HEIGHT)
        return QSize(option.rect.width(), Config.TREE_CHILD_ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        asset = index.data(TREE_ASSET_ROLE)
        if not asset:
            painter.restore()
            return

        is_parent = index.data(TREE_IS_PARENT)
        rect = option.rect
        is_selected = option.state & QStyle.StateFlag.State_Selected
        is_hovered = option.state & QStyle.StateFlag.State_MouseOver

        # Draw background
        if is_selected:
            painter.fillRect(rect, QColor(COLORS['accent']))
        elif is_hovered:
            hover_color = QColor(COLORS['accent'])
            hover_color.setAlpha(30)
            painter.fillRect(rect, hover_color)

        # Draw bottom border
        painter.setPen(QPen(QColor(COLORS['border']), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        padding = 6
        row_height = rect.height()
        thumb_size = row_height - (padding * 2)

        # Draw thumbnail
        thumb_rect = QRect(
            rect.x() + padding,
            rect.y() + padding,
            thumb_size,
            thumb_size
        )
        self._draw_thumbnail(painter, thumb_rect, asset)

        # Text area starts after thumbnail
        text_x = thumb_rect.right() + padding * 2
        text_width = rect.width() - text_x - padding

        # Draw name (bold, first line)
        name = asset.get('name', 'Unknown')
        font_bold = QFont("Segoe UI", 10)
        font_bold.setBold(True)
        painter.setFont(font_bold)
        fm = QFontMetrics(font_bold)

        text_color = QColor('#ffffff') if is_selected else QColor(COLORS['text_primary'])
        painter.setPen(text_color)

        # Asset type icon inline with name
        asset_type = asset.get('asset_type', 'other')
        icon_size = 16
        icon_rect = QRect(text_x, rect.y() + padding + 2, icon_size, icon_size)
        self._draw_type_icon_badge(painter, icon_rect, asset_type)
        name_x = text_x + icon_size + 6

        name_rect = QRect(name_x, rect.y() + padding, text_width - icon_size - 6, 22)
        elided = fm.elidedText(name, Qt.TextElideMode.ElideRight, name_rect.width())
        painter.setPen(text_color)
        painter.setFont(font_bold)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        # Inline badges next to name
        badge_x = name_x + fm.horizontalAdvance(elided) + 8
        badge_font = QFont("Segoe UI", 6, QFont.Weight.Bold)
        painter.setFont(badge_font)
        badge_fm = QFontMetrics(badge_font)

        # Status badge
        status = asset.get('status', '')
        if status and status != 'approved':
            badge_text = STATUS_LABELS.get(status.lower(), status.upper()[:3])
            badge_color = QColor(STATUS_COLORS.get(status.lower(), '#9E9E9E'))
            bw = badge_fm.horizontalAdvance(badge_text) + 6
            br = QRect(badge_x, rect.y() + padding + 5, bw, 12)
            painter.fillRect(br, badge_color)
            painter.setPen(QColor('#FFFFFF'))
            painter.drawText(br, Qt.AlignmentFlag.AlignCenter, badge_text)
            badge_x += bw + 4

        # Variant badge (for children: show variant name; for parents: show count)
        if is_parent:
            vcount = asset.get('_variant_count', 0)
            if vcount > 0:
                vtext = f"{vcount} var"
                vw = badge_fm.horizontalAdvance(vtext) + 6
                vr = QRect(badge_x, rect.y() + padding + 5, vw, 12)
                painter.fillRect(vr, QColor('#512DA8'))
                painter.setPen(QColor('#FFFFFF'))
                painter.drawText(vr, Qt.AlignmentFlag.AlignCenter, vtext)
                badge_x += vw + 4
        else:
            variant_name = asset.get('variant_name', '')
            if variant_name and variant_name != 'Base':
                vw = badge_fm.horizontalAdvance(variant_name) + 6
                vr = QRect(badge_x, rect.y() + padding + 5, vw, 12)
                painter.fillRect(vr, QColor('#7B1FA2'))
                painter.setPen(QColor('#FFFFFF'))
                painter.drawText(vr, Qt.AlignmentFlag.AlignCenter, variant_name)
                badge_x += vw + 4

        # Second line: metadata
        meta_font = QFont("Segoe UI", 8)
        painter.setFont(meta_font)
        meta_color = QColor('#ffffff') if is_selected else QColor(COLORS['text_secondary'])
        painter.setPen(meta_color)

        meta_parts = []
        version_label = asset.get('version_label', '')
        if version_label:
            meta_parts.append(version_label)
        polygon_count = asset.get('polygon_count')
        if polygon_count:
            meta_parts.append(f"{polygon_count:,} polys")
        file_size = asset.get('file_size_mb')
        if file_size:
            meta_parts.append(f"{file_size:.1f} MB")

        meta_text = " | ".join(meta_parts)
        meta_y = rect.y() + padding + 24
        meta_rect = QRect(text_x + icon_size + 6, meta_y, text_width - icon_size - 6, 18)
        painter.drawText(meta_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, meta_text)

        painter.restore()

    def _draw_thumbnail(self, painter: QPainter, rect: QRect, asset: dict):
        """Draw thumbnail image for asset."""
        uuid = asset.get('uuid', '')
        thumbnail_path = asset.get('thumbnail_path', '')

        if not thumbnail_path:
            painter.fillRect(rect, QColor(COLORS['background_secondary']))
            painter.setPen(QColor("#808080"))
            f = QFont("Segoe UI", 7)
            painter.setFont(f)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No Image")
            return

        pixmap = self._thumbnail_loader.request_thumbnail(
            uuid, thumbnail_path, target_size=rect.width()
        )

        if pixmap:
            scaled = pixmap.scaled(
                rect.width(), rect.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            x_off = (scaled.width() - rect.width()) // 2
            y_off = (scaled.height() - rect.height()) // 2
            painter.drawPixmap(
                rect.x(), rect.y(), rect.width(), rect.height(),
                scaled, x_off, y_off, rect.width(), rect.height()
            )
        else:
            painter.fillRect(rect, QColor(COLORS['background_secondary']))
            painter.setPen(QColor("#A0A0A0"))
            f = QFont("Segoe UI", 7)
            painter.setFont(f)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Loading...")

    def _draw_type_icon_badge(self, painter: QPainter, rect: QRect, asset_type: str):
        """Draw small type icon badge (colored square with SVG icon)."""
        badge_color = QColor(TYPE_COLORS.get(asset_type.lower(), '#9E9E9E'))
        painter.setBrush(QBrush(badge_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 2, 2)

        # Draw SVG icon inside
        renderer = self._get_svg_renderer(asset_type.lower())
        if renderer:
            icon_padding = 2
            icon_rect = QRectF(
                rect.x() + icon_padding, rect.y() + icon_padding,
                rect.width() - icon_padding * 2, rect.height() - icon_padding * 2
            )
            renderer.render(painter, icon_rect)

    def _get_svg_renderer(self, asset_type: str) -> Optional[QSvgRenderer]:
        """Get cached SVG renderer for asset type."""
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

    def _on_thumbnail_loaded(self, uuid: str, pixmap):
        """Handle thumbnail loaded - trigger repaint."""
        if self.parent() and hasattr(self.parent(), 'viewport'):
            self.parent().viewport().update()


__all__ = ['AssetTreeDelegate']
