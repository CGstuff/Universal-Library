"""
Version Diff Engine

Computes structured diffs between two asset versions. Surfaces (preview panel,
inline tree toggle) consume DiffResult and never compute or format anything
themselves — all formatting lives here.

To add a new metric:
    1. Add a field to FIELD_REGISTRY with the right DiffShape
    2. Add the field name to the relevant asset type(s) in TYPE_FIELDS

To add a new diff shape (e.g., ListDiff for per-mesh comparison in v2):
    1. Subclass DiffShape, implement compare / format_long_block / format_short
    2. Use it in FIELD_REGISTRY for the appropriate field
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config


# =============================================================================
# Result types
# =============================================================================

@dataclass
class FieldDiff:
    """A single field's change between two versions."""
    field_name: str
    label: str
    prev_value: Any
    curr_value: Any
    change_type: str  # 'added' | 'removed' | 'changed' | 'unchanged'
    shape: 'DiffShape'  # the rule that produced this diff (used for formatting)
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_change(self) -> bool:
        return self.change_type != 'unchanged'

    def format_short(self) -> str:
        return self.shape.format_short(self)

    def format_long_block(self) -> List[str]:
        return self.shape.format_long_block(self)


@dataclass
class DiffResult:
    """Aggregate result of comparing two asset versions."""
    prev_label: str
    curr_label: str
    asset_type: str
    fields: List[FieldDiff] = field(default_factory=list)
    is_initial: bool = False

    def has_changes(self) -> bool:
        return bool(self.fields)

    # Significance ranking for short-form: numeric percent-change first,
    # then categorical/boolean changes. Used to pick top-N for inline view.
    def _significance(self, fd: FieldDiff) -> float:
        if isinstance(fd.shape, NumericDiff):
            percent = abs(fd.extra.get('percent', 0.0) or 0.0)
            # Cap percent at 1000 so a 0→N change doesn't dominate everything
            return min(percent, 1000.0) + 1.0  # +1 so 0% still ranks above non-numeric
        # All non-numeric changes get the same priority below max numeric
        return 0.5

    def top_changes(self, n: int = 3) -> List[FieldDiff]:
        """Return the top N most-significant changes (numeric % change wins)."""
        return sorted(self.fields, key=self._significance, reverse=True)[:n]

    def format_short_summary(self, max_items: int = 3) -> str:
        """One-line summary suitable for inline tree rows."""
        if self.is_initial:
            return "(initial version)"
        if not self.fields:
            return "— no changes —"
        top = self.top_changes(max_items)
        parts = [fd.format_short() for fd in top]
        remaining = len(self.fields) - len(top)
        if remaining > 0:
            parts.append(f"+{remaining} more")
        return " · ".join(parts)


# =============================================================================
# Diff shapes
# =============================================================================

class DiffShape:
    """Base class for field diff rules. Subclasses implement compare + format."""

    def __init__(self, label: str):
        self.label = label

    def compare(self, prev: Any, curr: Any) -> Optional[FieldDiff]:
        """Return a FieldDiff (or None if unchanged/not-comparable)."""
        raise NotImplementedError

    def format_short(self, diff: FieldDiff) -> str:
        """One-line short form, e.g. '+500 polys'."""
        raise NotImplementedError

    def format_long_block(self, diff: FieldDiff) -> List[str]:
        """List of lines for preview-panel rendering. First line is the label."""
        raise NotImplementedError


class NumericDiff(DiffShape):
    """Numeric scalar diff with delta and optional percent change."""

    def __init__(self, label: str, show_percent: bool = False, precision: int = 0,
                 short_label: Optional[str] = None):
        super().__init__(label)
        self.show_percent = show_percent
        self.precision = precision
        # Short label for inline form (e.g. 'polys' for polygon_count)
        self.short_label = short_label or label.lower()

    def _fmt(self, value: Any) -> str:
        if value is None:
            return '—'
        try:
            if self.precision > 0:
                return f"{float(value):,.{self.precision}f}"
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return str(value)

    def _fmt_delta(self, delta: float) -> str:
        sign = '+' if delta >= 0 else ''
        if self.precision > 0:
            return f"{sign}{delta:,.{self.precision}f}"
        return f"{sign}{int(delta):,}"

    def compare(self, prev: Any, curr: Any) -> Optional[FieldDiff]:
        prev_n = self._coerce(prev)
        curr_n = self._coerce(curr)
        if prev_n is None and curr_n is None:
            return None
        # Treat None as 0 for delta math but flag the change type
        prev_val = prev_n if prev_n is not None else 0
        curr_val = curr_n if curr_n is not None else 0
        delta = curr_val - prev_val
        if delta == 0 and prev_n == curr_n:
            return FieldDiff(self.label, self.label, prev, curr, 'unchanged', self)
        percent = None
        if self.show_percent and prev_val != 0:
            percent = (delta / abs(prev_val)) * 100.0
        change_type = 'added' if delta > 0 else 'removed' if delta < 0 else 'changed'
        return FieldDiff(
            self.label, self.label, prev_val, curr_val, change_type, self,
            extra={'delta': delta, 'percent': percent}
        )

    @staticmethod
    def _coerce(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def format_short(self, diff: FieldDiff) -> str:
        delta = diff.extra.get('delta', 0)
        return f"{self._fmt_delta(delta)} {self.short_label}"

    def format_long_block(self, diff: FieldDiff) -> List[str]:
        lines = [self.label]
        lines.append(f"  {self._fmt(diff.prev_value)} → {self._fmt(diff.curr_value)}")
        delta = diff.extra.get('delta', 0)
        percent = diff.extra.get('percent')
        if percent is not None:
            lines.append(f"  {self._fmt_delta(delta)} ({percent:+.1f}%)")
        else:
            lines.append(f"  {self._fmt_delta(delta)}")
        return lines


class BooleanDiff(DiffShape):
    """Boolean toggle: emits 'Added' or 'Removed' on change, hides unchanged."""

    def __init__(self, label: str, short_label: Optional[str] = None):
        super().__init__(label)
        self.short_label = short_label or label.lower()

    def compare(self, prev: Any, curr: Any) -> Optional[FieldDiff]:
        prev_b = self._coerce(prev)
        curr_b = self._coerce(curr)
        if prev_b == curr_b:
            return FieldDiff(self.label, self.label, prev_b, curr_b, 'unchanged', self)
        change_type = 'added' if curr_b and not prev_b else 'removed'
        return FieldDiff(self.label, self.label, prev_b, curr_b, change_type, self)

    @staticmethod
    def _coerce(v: Any) -> bool:
        if v is None or v == 0 or v is False:
            return False
        if isinstance(v, str):
            return v.lower() not in ('', '0', 'false', 'no')
        return bool(v)

    def format_short(self, diff: FieldDiff) -> str:
        prefix = '+' if diff.change_type == 'added' else '−'
        return f"{prefix}{self.short_label}"

    def format_long_block(self, diff: FieldDiff) -> List[str]:
        prev_s = 'YES' if diff.prev_value else 'NO'
        curr_s = 'YES' if diff.curr_value else 'NO'
        verb = 'Added' if diff.change_type == 'added' else 'Removed'
        return [
            self.label,
            f"  {prev_s} → {curr_s}  ({verb})",
        ]


class CategoricalDiff(DiffShape):
    """Enum-like string change. Always 'changed' (or unchanged)."""

    def compare(self, prev: Any, curr: Any) -> Optional[FieldDiff]:
        prev_s = self._coerce(prev)
        curr_s = self._coerce(curr)
        if prev_s == curr_s:
            return FieldDiff(self.label, self.label, prev_s, curr_s, 'unchanged', self)
        return FieldDiff(self.label, self.label, prev_s, curr_s, 'changed', self)

    @staticmethod
    def _coerce(v: Any) -> str:
        if v is None:
            return ''
        return str(v).lower()

    def format_short(self, diff: FieldDiff) -> str:
        prev_s = diff.prev_value or '—'
        curr_s = diff.curr_value or '—'
        return f"{prev_s} → {curr_s}"

    def format_long_block(self, diff: FieldDiff) -> List[str]:
        prev_s = (diff.prev_value or '—').upper()
        curr_s = (diff.curr_value or '—').upper()
        return [
            self.label,
            f"  {prev_s} → {curr_s}  (Changed)",
        ]


class SetDiff(DiffShape):
    """List/set diff: added items, removed items."""

    def __init__(self, label: str, short_label: Optional[str] = None):
        super().__init__(label)
        self.short_label = short_label or label.lower()

    def compare(self, prev: Any, curr: Any) -> Optional[FieldDiff]:
        prev_set = self._coerce(prev)
        curr_set = self._coerce(curr)
        if prev_set == curr_set:
            return FieldDiff(self.label, self.label, prev_set, curr_set, 'unchanged', self)
        added = sorted(curr_set - prev_set)
        removed = sorted(prev_set - curr_set)
        if not added and not removed:
            return FieldDiff(self.label, self.label, prev_set, curr_set, 'unchanged', self)
        change_type = 'changed'
        if added and not removed:
            change_type = 'added'
        elif removed and not added:
            change_type = 'removed'
        return FieldDiff(
            self.label, self.label, prev_set, curr_set, change_type, self,
            extra={'added': added, 'removed': removed},
        )

    @staticmethod
    def _coerce(v: Any) -> set:
        if v is None:
            return set()
        if isinstance(v, str):
            # JSON-encoded list (legacy format)
            import json
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return {str(x) for x in parsed if x is not None}
            except (ValueError, TypeError):
                pass
            return set() if not v else {v}
        if isinstance(v, (list, tuple, set)):
            return {str(x) for x in v if x is not None}
        return {str(v)}

    def format_short(self, diff: FieldDiff) -> str:
        added = diff.extra.get('added', [])
        removed = diff.extra.get('removed', [])
        n_added = len(added)
        n_removed = len(removed)
        if n_added and not n_removed:
            head = ', '.join(added[:2])
            tail = f' +{n_added - 2}' if n_added > 2 else ''
            return f"+{n_added} {self.short_label} ({head}{tail})"
        if n_removed and not n_added:
            head = ', '.join(removed[:2])
            tail = f' +{n_removed - 2}' if n_removed > 2 else ''
            return f"−{n_removed} {self.short_label} ({head}{tail})"
        return f"+{n_added}/−{n_removed} {self.short_label}"

    def format_long_block(self, diff: FieldDiff) -> List[str]:
        prev_list = sorted(diff.prev_value) if diff.prev_value else []
        curr_list = sorted(diff.curr_value) if diff.curr_value else []
        lines = [self.label]
        lines.append(f"  [{', '.join(prev_list) or '—'}]")
        lines.append(f"  → [{', '.join(curr_list) or '—'}]")
        for item in diff.extra.get('added', []):
            lines.append(f"  + {item}")
        for item in diff.extra.get('removed', []):
            lines.append(f"  − {item}")
        return lines


class ColorDiff(DiffShape):
    """Hex color change with warmer/cooler heuristic."""

    def compare(self, prev: Any, curr: Any) -> Optional[FieldDiff]:
        prev_s = self._normalize(prev)
        curr_s = self._normalize(curr)
        if prev_s == curr_s:
            return FieldDiff(self.label, self.label, prev_s, curr_s, 'unchanged', self)
        return FieldDiff(self.label, self.label, prev_s, curr_s, 'changed', self,
                         extra={'temp_shift': self._temp_shift(prev_s, curr_s)})

    @staticmethod
    def _normalize(v: Any) -> str:
        if not v:
            return ''
        s = str(v).strip().upper()
        if s and not s.startswith('#'):
            s = '#' + s
        return s

    @staticmethod
    def _temp_shift(prev_hex: str, curr_hex: str) -> str:
        """Crude: more red than blue → warmer, more blue than red → cooler."""
        def rgb(h):
            try:
                h = h.lstrip('#')
                if len(h) != 6:
                    return None
                return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            except ValueError:
                return None
        prev_rgb = rgb(prev_hex)
        curr_rgb = rgb(curr_hex)
        if not prev_rgb or not curr_rgb:
            return ''
        prev_warmth = prev_rgb[0] - prev_rgb[2]  # R - B
        curr_warmth = curr_rgb[0] - curr_rgb[2]
        delta = curr_warmth - prev_warmth
        if abs(delta) < 8:
            return ''
        return 'warmer' if delta > 0 else 'cooler'

    def format_short(self, diff: FieldDiff) -> str:
        shift = diff.extra.get('temp_shift', '')
        if shift:
            return f"{shift} color"
        return "color changed"

    def format_long_block(self, diff: FieldDiff) -> List[str]:
        shift = diff.extra.get('temp_shift', '')
        suffix = f"  ({shift})" if shift else ""
        return [
            self.label,
            f"  {diff.prev_value or '—'} → {diff.curr_value or '—'}{suffix}",
        ]


class DimensionalDiff(DiffShape):
    """Bbox-style multi-axis diff with uniform-scale detection."""

    def __init__(self, label: str, axes: Tuple[str, ...]):
        super().__init__(label)
        self.axes = axes  # e.g. ('bbox_x', 'bbox_y', 'bbox_z')

    # Compare uses the full asset dict (multi-field). The engine special-cases this.
    def compare_multi(
        self, prev_asset: Dict[str, Any], curr_asset: Dict[str, Any]
    ) -> Optional[FieldDiff]:
        prev_vals = [self._coerce(prev_asset.get(a)) for a in self.axes]
        curr_vals = [self._coerce(curr_asset.get(a)) for a in self.axes]
        if all(v is None for v in prev_vals + curr_vals):
            return None
        if all(p == c for p, c in zip(prev_vals, curr_vals)):
            return FieldDiff(self.label, self.label, prev_vals, curr_vals, 'unchanged', self)
        # Compute per-axis percent delta where possible
        per_axis = []
        for axis, p, c in zip(self.axes, prev_vals, curr_vals):
            if p is None or c is None or p == 0:
                per_axis.append((axis, None))
            else:
                per_axis.append((axis, (c - p) / p * 100.0))
        # Detect uniform scale: all defined percents equal within tolerance
        defined = [pct for _, pct in per_axis if pct is not None]
        uniform_pct = None
        if defined and max(defined) - min(defined) < 1.5:  # within 1.5%
            uniform_pct = sum(defined) / len(defined)
        return FieldDiff(
            self.label, self.label, prev_vals, curr_vals, 'changed', self,
            extra={'per_axis': per_axis, 'uniform_pct': uniform_pct},
        )

    @staticmethod
    def _coerce(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def compare(self, prev: Any, curr: Any) -> Optional[FieldDiff]:
        # Not used — bbox goes through compare_multi
        return None

    def format_short(self, diff: FieldDiff) -> str:
        uniform_pct = diff.extra.get('uniform_pct')
        if uniform_pct is not None:
            sign = '+' if uniform_pct >= 0 else ''
            return f"bbox {sign}{uniform_pct:.0f}% uniform"
        # Find biggest axis change
        biggest_axis = None
        biggest_pct = 0.0
        for axis, pct in diff.extra.get('per_axis', []):
            if pct is not None and abs(pct) > abs(biggest_pct):
                biggest_pct = pct
                biggest_axis = axis
        if biggest_axis:
            axis_letter = biggest_axis[-1].upper()
            sign = '+' if biggest_pct >= 0 else ''
            return f"bbox {sign}{biggest_pct:.0f}% on {axis_letter}"
        return "bbox changed"

    def format_long_block(self, diff: FieldDiff) -> List[str]:
        lines = [self.label]
        def fmt_dim(vals):
            return '×'.join(
                f"{v:.2f}" if isinstance(v, (int, float)) else '—' for v in vals
            )
        lines.append(f"  {fmt_dim(diff.prev_value)} → {fmt_dim(diff.curr_value)}")
        uniform_pct = diff.extra.get('uniform_pct')
        if uniform_pct is not None:
            sign = '+' if uniform_pct >= 0 else ''
            lines.append(f"  {sign}{uniform_pct:.1f}% uniform")
        else:
            parts = []
            for axis, pct in diff.extra.get('per_axis', []):
                if pct is None:
                    parts.append(f"{axis[-1].upper()}: —")
                else:
                    sign = '+' if pct >= 0 else ''
                    parts.append(f"{axis[-1].upper()}: {sign}{pct:.0f}%")
            lines.append(f"  ({', '.join(parts)})")
        return lines


# =============================================================================
# Registry & per-type field lists
# =============================================================================

FIELD_REGISTRY: Dict[str, DiffShape] = {
    # Numeric counts
    'polygon_count':           NumericDiff('Polygons',     show_percent=True, short_label='polys'),
    'material_count':          NumericDiff('Materials',                       short_label='mat'),
    'vertex_group_count':      NumericDiff('Vertex groups',                   short_label='vgrps'),
    'shape_key_count':         NumericDiff('Shape keys',                      short_label='shape keys'),
    'mesh_count':              NumericDiff('Meshes',                          short_label='mesh'),
    'light_count':             NumericDiff('Lights',                          short_label='lights'),
    'camera_count':            NumericDiff('Cameras',                         short_label='cams'),
    'armature_count':          NumericDiff('Armatures',                       short_label='armatures'),
    'bone_count':              NumericDiff('Bones',                           short_label='bones'),
    'control_count':           NumericDiff('Controls',                        short_label='ctrls'),
    'point_count':             NumericDiff('Points',                          short_label='points'),
    'spline_count':            NumericDiff('Splines',                         short_label='splines'),
    'layer_count':             NumericDiff('Layers',                          short_label='layers'),
    'stroke_count':            NumericDiff('Strokes',                         short_label='strokes'),
    'frame_count':             NumericDiff('Frames',                          short_label='frames'),
    'object_count':            NumericDiff('Objects',                         short_label='obj'),
    'collection_count':        NumericDiff('Collections',                     short_label='colls'),
    'nested_collection_count': NumericDiff('Nested collections',              short_label='nested'),
    'light_power':             NumericDiff('Power',         show_percent=True, precision=2, short_label='power'),
    'light_spot_size':         NumericDiff('Spot angle',    precision=1,      short_label='spot°'),
    'focal_length':            NumericDiff('Focal length',  precision=1,      short_label='mm'),
    'camera_sensor_width':     NumericDiff('Sensor width',  precision=1,      short_label='sensor'),
    'camera_clip_start':       NumericDiff('Clip start',    precision=2,      short_label='clip'),
    'camera_clip_end':         NumericDiff('Clip end',      precision=1,      short_label='clip'),
    'camera_ortho_scale':      NumericDiff('Ortho scale',   precision=2,      short_label='ortho'),
    'frame_start':             NumericDiff('Start frame',                     short_label='start'),
    'frame_end':               NumericDiff('End frame',                       short_label='end'),
    'frame_rate':              NumericDiff('FPS',           precision=2,      short_label='fps'),
    'resolution_x':            NumericDiff('Width',                           short_label='w'),
    'resolution_y':            NumericDiff('Height',                          short_label='h'),

    # Booleans
    'has_skeleton':            BooleanDiff('Skeleton',          short_label='skel'),
    'has_animations':          BooleanDiff('Animations',        short_label='anim'),
    'has_facial_rig':          BooleanDiff('Facial rig',        short_label='facial'),
    'has_nested_collections':  BooleanDiff('Nested collections',short_label='nested'),
    'is_loop':                 BooleanDiff('Loop',              short_label='loop'),
    'light_shadow':            BooleanDiff('Shadow',            short_label='shadow'),
    'camera_dof_enabled':      BooleanDiff('DOF',               short_label='DOF'),

    # Categoricals
    'light_type':              CategoricalDiff('Light type'),
    'light_area_shape':        CategoricalDiff('Area shape'),
    'curve_type':              CategoricalDiff('Curve type'),
    'camera_type':             CategoricalDiff('Camera type'),
    'render_engine':           CategoricalDiff('Render engine'),
    'world_name':              CategoricalDiff('World'),
    'texture_resolution':      CategoricalDiff('Texture resolution'),

    # Colors
    'light_color':             ColorDiff('Light color'),

    # Sets
    'texture_maps':            SetDiff('Texture maps', short_label='maps'),

    # Dimensional (bbox, multi-field)
    'bbox':                    DimensionalDiff('Bbox', axes=('bbox_x', 'bbox_y', 'bbox_z')),
}


TYPE_FIELDS: Dict[str, List[str]] = {
    'mesh': [
        'polygon_count', 'material_count', 'vertex_group_count', 'shape_key_count',
        'has_skeleton', 'has_animations', 'bone_count', 'has_facial_rig', 'bbox',
    ],
    'rig': [
        'bone_count', 'control_count', 'has_facial_rig', 'shape_key_count',
    ],
    'material': [
        'texture_maps', 'texture_resolution', 'material_count',
    ],
    'light': [
        'light_type', 'light_count', 'light_power', 'light_color',
        'light_shadow', 'light_spot_size', 'light_area_shape',
    ],
    'camera': [
        'camera_type', 'focal_length', 'camera_sensor_width',
        'camera_clip_start', 'camera_clip_end', 'camera_dof_enabled',
        'camera_ortho_scale',
    ],
    'collection': [
        'mesh_count', 'light_count', 'camera_count', 'armature_count',
        'polygon_count', 'has_nested_collections', 'nested_collection_count',
        'bbox',
    ],
    'grease_pencil': [
        'layer_count', 'stroke_count', 'frame_count',
        'material_count', 'has_animations',
    ],
    'curve': [
        'curve_type', 'point_count', 'spline_count', 'material_count',
    ],
    'scene': [
        'object_count', 'collection_count', 'polygon_count',
        'render_engine', 'resolution_x', 'resolution_y',
        'frame_start', 'frame_end', 'frame_rate', 'world_name',
    ],
    'other': [
        'polygon_count', 'material_count', 'has_skeleton',
        'has_animations', 'bbox',
    ],
}


def _resolve_type_fields(asset_type: str) -> List[str]:
    """Resolve asset_type to its diff field list, honoring ASSET_TYPE_CATEGORY aliases."""
    if asset_type in TYPE_FIELDS:
        return TYPE_FIELDS[asset_type]
    category = Config.ASSET_TYPE_CATEGORY.get(asset_type, 'mesh')
    return TYPE_FIELDS.get(category, TYPE_FIELDS['other'])


# =============================================================================
# Public API
# =============================================================================

def compute_version_diff(
    prev_asset: Optional[Dict[str, Any]],
    curr_asset: Dict[str, Any],
) -> DiffResult:
    """
    Compute diff between two asset version dicts.

    Args:
        prev_asset: Previous version row from DB (or None for initial version).
        curr_asset: Current version row from DB.

    Returns:
        DiffResult containing only the FieldDiffs that actually changed.
    """
    curr_label = curr_asset.get('version_label', '?')
    asset_type = curr_asset.get('asset_type', 'other')

    if prev_asset is None:
        return DiffResult(
            prev_label='—',
            curr_label=curr_label,
            asset_type=asset_type,
            fields=[],
            is_initial=True,
        )

    prev_label = prev_asset.get('version_label', '?')
    field_names = _resolve_type_fields(asset_type)

    fields: List[FieldDiff] = []
    for fname in field_names:
        shape = FIELD_REGISTRY.get(fname)
        if shape is None:
            continue
        # DimensionalDiff is special — it reads multiple keys
        if isinstance(shape, DimensionalDiff):
            fd = shape.compare_multi(prev_asset, curr_asset)
        else:
            fd = shape.compare(prev_asset.get(fname), curr_asset.get(fname))
        if fd is not None and fd.is_change:
            fields.append(fd)

    return DiffResult(
        prev_label=prev_label,
        curr_label=curr_label,
        asset_type=asset_type,
        fields=fields,
        is_initial=False,
    )


__all__ = [
    'FieldDiff',
    'DiffResult',
    'DiffShape',
    'NumericDiff',
    'BooleanDiff',
    'CategoricalDiff',
    'SetDiff',
    'ColorDiff',
    'DimensionalDiff',
    'FIELD_REGISTRY',
    'TYPE_FIELDS',
    'compute_version_diff',
]
