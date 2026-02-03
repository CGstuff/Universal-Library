"""
DrawoverStorage - File storage management for screenshot annotations

Handles saving/loading drawover JSON files and PNG cache generation.
Adapted from Animation Library for static images instead of video frames.

New Structure (matching archive_service):
    storage/reviews/{uuid_short}_{name}/{variant}/{version_label}/drawovers/
    ├── screenshot_123.json    # Screenshot drawover vector data (by screenshot_id)
    ├── screenshot_123.png     # Screenshot drawover PNG cache
    └── manifest.json          # Index of all drawovers
"""

import json
import uuid as uuid_lib
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime
from collections import OrderedDict

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool
from PyQt6.QtGui import QImage, QPainter, QColor, QPen, QPainterPath, QFont
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF

from ..config import Config


class DrawoverStorage:
    """
    Manages drawover file storage on disk for screenshots.

    File structure:
        storage/reviews/{uuid_short}_{name}/{variant}/{version_label}/drawovers/
        ├── screenshot_123.json    # Screenshot drawover vector data
        ├── screenshot_123.png     # Screenshot drawover PNG cache
        └── manifest.json          # Index of all drawovers
    """

    JSON_VERSION = "1.0"

    def __init__(self):
        # Base is now the reviews folder from Config
        pass

    def get_drawover_dir(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ) -> Path:
        """Get directory for a version's drawovers."""
        review_dir = Config.get_asset_reviews_path(asset_id, asset_name, variant_name, version_label)
        return review_dir / 'drawovers'

    def get_drawover_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int
    ) -> Path:
        """Get path for a screenshot's drawover JSON using unique screenshot_id."""
        drawover_dir = self.get_drawover_dir(asset_id, asset_name, variant_name, version_label)
        drawover_dir.mkdir(parents=True, exist_ok=True)
        return drawover_dir / f'screenshot_{screenshot_id}.json'

    def get_png_cache_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int
    ) -> Path:
        """Get path for a screenshot's PNG cache using unique screenshot_id."""
        drawover_dir = self.get_drawover_dir(asset_id, asset_name, variant_name, version_label)
        drawover_dir.mkdir(parents=True, exist_ok=True)
        return drawover_dir / f'screenshot_{screenshot_id}.png'

    def get_manifest_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ) -> Path:
        """Get path for manifest file."""
        return self.get_drawover_dir(asset_id, asset_name, variant_name, version_label) / 'manifest.json'

    # ==================== Save/Load ====================

    def save_drawover(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int,
        strokes: List[Dict],
        author: str = '',
        canvas_size: Tuple[int, int] = (1920, 1080)
    ) -> bool:
        """
        Save drawover data for a screenshot.

        Args:
            asset_id: Asset family UUID
            asset_name: Human-readable asset name
            variant_name: Variant name (e.g., 'Base')
            version_label: Version label (e.g., 'v001')
            screenshot_id: Unique screenshot database ID
            strokes: List of stroke dictionaries
            author: Current user (for new strokes)
            canvas_size: Image dimensions

        Returns:
            True if saved successfully
        """
        try:
            path = self.get_drawover_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Load existing data or create new
            existing = self.load_drawover(asset_id, asset_name, variant_name, version_label, screenshot_id)
            now = datetime.utcnow().isoformat() + 'Z'

            if existing:
                data = existing
                data['modified_at'] = now
                data['strokes'] = strokes
            else:
                data = {
                    'version': self.JSON_VERSION,
                    'screenshot_id': screenshot_id,
                    'canvas_size': list(canvas_size),
                    'created_at': now,
                    'modified_at': now,
                    'author': author,
                    'strokes': strokes,
                    'deleted_strokes': []
                }

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            # Invalidate PNG cache
            png_path = self.get_png_cache_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
            if png_path.exists():
                png_path.unlink()

            # Update manifest
            self._update_manifest(asset_id, asset_name, variant_name, version_label)

            return True

        except Exception as e:
            return False

    def load_drawover(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int
    ) -> Optional[Dict]:
        """Load drawover data for a screenshot."""
        path = self.get_drawover_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
        if not path.exists():
            return None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return None

    def delete_drawover(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int
    ) -> bool:
        """Delete a screenshot's drawover files (hard delete)."""
        try:
            json_path = self.get_drawover_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
            png_path = self.get_png_cache_path(asset_id, asset_name, variant_name, version_label, screenshot_id)

            if json_path.exists():
                json_path.unlink()
            if png_path.exists():
                png_path.unlink()

            self._update_manifest(asset_id, asset_name, variant_name, version_label)
            return True

        except Exception as e:
            return False

    def has_drawover(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int
    ) -> bool:
        """Check if a screenshot has drawover data."""
        return self.get_drawover_path(asset_id, asset_name, variant_name, version_label, screenshot_id).exists()

    def list_screenshots_with_drawovers(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ) -> List[int]:
        """Get list of screenshot IDs that have drawovers."""
        drawover_dir = self.get_drawover_dir(asset_id, asset_name, variant_name, version_label)
        if not drawover_dir.exists():
            return []

        screenshot_ids = []
        for path in drawover_dir.glob('screenshot_*.json'):
            if path.name != 'manifest.json':
                # Extract ID from filename like "screenshot_123.json"
                try:
                    id_str = path.stem.replace('screenshot_', '')
                    screenshot_ids.append(int(id_str))
                except ValueError:
                    continue

        return sorted(screenshot_ids)

    # ==================== Stroke Management ====================

    def add_stroke(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int,
        stroke: Dict,
        author: str = '',
        canvas_size: Tuple[int, int] = (1920, 1080)
    ) -> Optional[str]:
        """
        Add a single stroke to a screenshot's drawover.

        Returns:
            Stroke ID if successful, None otherwise
        """
        # Generate stroke ID if not present
        if 'id' not in stroke:
            stroke['id'] = f"stroke_{uuid_lib.uuid4().hex[:8]}"

        stroke['created_at'] = datetime.utcnow().isoformat() + 'Z'
        stroke['author'] = author

        # Load existing or create new
        existing = self.load_drawover(asset_id, asset_name, variant_name, version_label, screenshot_id)
        if existing:
            existing['strokes'].append(stroke)
            strokes = existing['strokes']
        else:
            strokes = [stroke]

        if self.save_drawover(asset_id, asset_name, variant_name, version_label, screenshot_id, strokes, author, canvas_size):
            return stroke['id']
        return None

    def remove_stroke(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int,
        stroke_id: str,
        soft_delete: bool = True,
        deleted_by: str = ''
    ) -> bool:
        """
        Remove a stroke from a screenshot's drawover.

        Args:
            soft_delete: If True, move to deleted_strokes array (Studio Mode)
                        If False, permanently remove (Solo Mode)
        """
        data = self.load_drawover(asset_id, asset_name, variant_name, version_label, screenshot_id)
        if not data:
            return False

        # Find stroke
        stroke_to_remove = None
        for i, stroke in enumerate(data['strokes']):
            if stroke.get('id') == stroke_id:
                stroke_to_remove = data['strokes'].pop(i)
                break

        if not stroke_to_remove:
            return False

        if soft_delete:
            # Move to deleted_strokes
            if 'deleted_strokes' not in data:
                data['deleted_strokes'] = []

            deleted_entry = {
                'id': stroke_id,
                'deleted_at': datetime.utcnow().isoformat() + 'Z',
                'deleted_by': deleted_by,
                'original_data': stroke_to_remove
            }
            data['deleted_strokes'].append(deleted_entry)

        # Save updated data
        path = self.get_drawover_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            # Invalidate PNG cache
            png_path = self.get_png_cache_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
            if png_path.exists():
                png_path.unlink()

            self._update_manifest(asset_id, asset_name, variant_name, version_label)
            return True

        except Exception as e:
            return False

    def restore_stroke(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int,
        stroke_id: str,
        restored_by: str = ''
    ) -> bool:
        """Restore a soft-deleted stroke."""
        data = self.load_drawover(asset_id, asset_name, variant_name, version_label, screenshot_id)
        if not data or 'deleted_strokes' not in data:
            return False

        # Find deleted stroke
        for i, deleted in enumerate(data['deleted_strokes']):
            if deleted.get('id') == stroke_id:
                # Restore original data
                original = deleted['original_data']
                data['strokes'].append(original)
                data['deleted_strokes'].pop(i)

                # Save
                path = self.get_drawover_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)

                # Invalidate cache
                png_path = self.get_png_cache_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
                if png_path.exists():
                    png_path.unlink()

                return True

        return False

    def clear_screenshot(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int,
        soft_delete: bool = True,
        deleted_by: str = ''
    ) -> bool:
        """Clear all strokes on a screenshot."""
        data = self.load_drawover(asset_id, asset_name, variant_name, version_label, screenshot_id)
        if not data:
            return True  # Nothing to clear

        if soft_delete:
            # Move all to deleted
            if 'deleted_strokes' not in data:
                data['deleted_strokes'] = []

            now = datetime.utcnow().isoformat() + 'Z'
            for stroke in data['strokes']:
                deleted_entry = {
                    'id': stroke.get('id', ''),
                    'deleted_at': now,
                    'deleted_by': deleted_by,
                    'original_data': stroke
                }
                data['deleted_strokes'].append(deleted_entry)

        data['strokes'] = []

        # Save
        path = self.get_drawover_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            # Invalidate cache
            png_path = self.get_png_cache_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
            if png_path.exists():
                png_path.unlink()

            self._update_manifest(asset_id, asset_name, variant_name, version_label)
            return True

        except Exception as e:
            return False

    # ==================== PNG Rendering ====================

    def render_to_png(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int,
        size: Tuple[int, int]
    ) -> Optional[Path]:
        """
        Render drawover to PNG, using cache if valid.

        Returns:
            Path to PNG file, or None if no drawover exists
        """
        json_path = self.get_drawover_path(asset_id, asset_name, variant_name, version_label, screenshot_id)
        png_path = self.get_png_cache_path(asset_id, asset_name, variant_name, version_label, screenshot_id)

        if not json_path.exists():
            return None

        # Check if cache is valid
        if png_path.exists():
            if png_path.stat().st_mtime >= json_path.stat().st_mtime:
                return png_path

        # Load and render
        data = self.load_drawover(asset_id, asset_name, variant_name, version_label, screenshot_id)
        if not data:
            return None

        try:
            self._render_strokes_to_png(data, png_path, size)
            return png_path
        except Exception as e:
            return None

    def _render_strokes_to_png(
        self,
        data: Dict,
        output_path: Path,
        size: Tuple[int, int]
    ):
        """Render strokes to PNG file with transparency."""
        width, height = size
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))  # Transparent

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Scale factor if canvas size differs from output size
        canvas_size = data.get('canvas_size', [width, height])
        scale_x = width / canvas_size[0]
        scale_y = height / canvas_size[1]

        for stroke in data.get('strokes', []):
            self._render_stroke(painter, stroke, scale_x, scale_y)

        painter.end()
        image.save(str(output_path), 'PNG')

    def _render_stroke(
        self,
        painter: QPainter,
        stroke: Dict,
        scale_x: float,
        scale_y: float
    ):
        """Render a single stroke."""
        stroke_type = stroke.get('type', 'path')
        color = QColor(stroke.get('color', '#FF5722'))
        opacity = stroke.get('opacity', 1.0)
        color.setAlphaF(opacity)
        width = stroke.get('width', 3)

        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        if stroke_type == 'path':
            points = stroke.get('points', [])
            if len(points) >= 2:
                path = QPainterPath()
                path.moveTo(points[0][0] * scale_x, points[0][1] * scale_y)
                for point in points[1:]:
                    path.lineTo(point[0] * scale_x, point[1] * scale_y)
                painter.drawPath(path)

        elif stroke_type == 'line':
            start = stroke.get('start', [0, 0])
            end = stroke.get('end', [0, 0])
            painter.drawLine(
                QPointF(start[0] * scale_x, start[1] * scale_y),
                QPointF(end[0] * scale_x, end[1] * scale_y)
            )

        elif stroke_type == 'arrow':
            start = stroke.get('start', [0, 0])
            end = stroke.get('end', [0, 0])
            head_size = stroke.get('head_size', 12) * scale_x

            # Draw line
            start_pt = QPointF(start[0] * scale_x, start[1] * scale_y)
            end_pt = QPointF(end[0] * scale_x, end[1] * scale_y)
            painter.drawLine(start_pt, end_pt)

            # Draw arrow head
            import math
            line = QLineF(start_pt, end_pt)
            angle = math.atan2(-line.dy(), line.dx())

            p1 = end_pt + QPointF(
                math.cos(angle + math.pi * 0.8) * head_size,
                -math.sin(angle + math.pi * 0.8) * head_size
            )
            p2 = end_pt + QPointF(
                math.cos(angle - math.pi * 0.8) * head_size,
                -math.sin(angle - math.pi * 0.8) * head_size
            )

            painter.drawLine(end_pt, p1)
            painter.drawLine(end_pt, p2)

        elif stroke_type == 'rect':
            bounds = stroke.get('bounds', [0, 0, 100, 100])
            fill = stroke.get('fill', False)
            rect = QRectF(
                bounds[0] * scale_x,
                bounds[1] * scale_y,
                bounds[2] * scale_x,
                bounds[3] * scale_y
            )
            if fill:
                painter.fillRect(rect, color)
            else:
                painter.drawRect(rect)

        elif stroke_type == 'ellipse':
            bounds = stroke.get('bounds', [0, 0, 100, 100])
            fill = stroke.get('fill', False)
            rect = QRectF(
                bounds[0] * scale_x,
                bounds[1] * scale_y,
                bounds[2] * scale_x,
                bounds[3] * scale_y
            )
            if fill:
                painter.setBrush(color)
            painter.drawEllipse(rect)

        elif stroke_type == 'text':
            position = stroke.get('position', [0, 0])
            text = stroke.get('text', '')
            font_size = int(stroke.get('font_size', 14) * scale_x)
            bg_color = stroke.get('background', None)

            font = QFont('Arial', font_size)
            painter.setFont(font)

            pos = QPointF(position[0] * scale_x, position[1] * scale_y)

            if bg_color:
                bg = QColor(bg_color)
                bg.setAlphaF(stroke.get('opacity', 0.8))
                metrics = painter.fontMetrics()
                text_rect = metrics.boundingRect(text)
                text_rect.moveTopLeft(pos.toPoint())
                text_rect.adjust(-4, -2, 4, 2)
                painter.fillRect(text_rect, bg)

            painter.setPen(color)
            painter.drawText(pos, text)

    # ==================== Manifest ====================

    def _update_manifest(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ):
        """Update manifest file for a version."""
        drawover_dir = self.get_drawover_dir(asset_id, asset_name, variant_name, version_label)
        if not drawover_dir.exists():
            return

        manifest_path = self.get_manifest_path(asset_id, asset_name, variant_name, version_label)

        screenshots = {}
        total_strokes = 0

        for json_path in drawover_dir.glob('*.json'):
            if json_path.name == 'manifest.json':
                continue

            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                stroke_count = len(data.get('strokes', []))
                total_strokes += stroke_count

                screenshots[json_path.stem] = {
                    'json': json_path.name,
                    'png': f'{json_path.stem}.png',
                    'modified_at': data.get('modified_at', ''),
                    'stroke_count': stroke_count
                }

            except Exception:
                continue

        manifest = {
            'version': '1.0',
            'asset_id': asset_id,
            'asset_name': asset_name,
            'variant_name': variant_name,
            'version_label': version_label,
            'screenshots': screenshots,
            'total_screenshots': len(screenshots),
            'total_strokes': total_strokes
        }

        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)

    def get_manifest(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ) -> Optional[Dict]:
        """Get manifest data for a version."""
        path = self.get_manifest_path(asset_id, asset_name, variant_name, version_label)
        if not path.exists():
            return None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None


# ==================== Cache ====================

class DrawoverCache:
    """LRU cache for loaded drawover data."""

    def __init__(self, max_size: int = 50):
        self._cache: OrderedDict[str, Dict] = OrderedDict()
        self._max_size = max_size

    def _make_key(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int
    ) -> str:
        return f"{asset_id}:{variant_name}:{version_label}:{screenshot_id}"

    def get(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int
    ) -> Optional[Dict]:
        key = self._make_key(asset_id, asset_name, variant_name, version_label, screenshot_id)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int,
        data: Dict
    ):
        key = self._make_key(asset_id, asset_name, variant_name, version_label, screenshot_id)
        self._cache[key] = data
        self._cache.move_to_end(key)

        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def invalidate(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        screenshot_id: int
    ):
        key = self._make_key(asset_id, asset_name, variant_name, version_label, screenshot_id)
        self._cache.pop(key, None)

    def invalidate_version(
        self,
        asset_id: str,
        variant_name: str,
        version_label: str
    ):
        """Invalidate all cached data for a version."""
        prefix = f"{asset_id}:{variant_name}:{version_label}:"
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]
        for key in keys_to_remove:
            self._cache.pop(key, None)

    def clear(self):
        self._cache.clear()


# ==================== Singleton ====================

_storage_instance: Optional[DrawoverStorage] = None
_cache_instance: Optional[DrawoverCache] = None


def get_drawover_storage() -> DrawoverStorage:
    """Get singleton DrawoverStorage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = DrawoverStorage()
    return _storage_instance


def get_drawover_cache() -> DrawoverCache:
    """Get singleton DrawoverCache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = DrawoverCache()
    return _cache_instance


__all__ = [
    'DrawoverStorage',
    'DrawoverCache',
    'get_drawover_storage',
    'get_drawover_cache'
]
