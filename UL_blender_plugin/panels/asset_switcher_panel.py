"""
Asset Switcher Panel - Thumbnail grid for switching versions and variants.

Uses Blender's template_icon_view with dynamic EnumProperty to show
thumbnail grids (like KIT OPS). Click a thumbnail to select, then
press the Switch button to swap in-place.
"""

import bpy
from bpy.types import Panel, PropertyGroup
from bpy.props import EnumProperty, StringProperty, BoolProperty
from pathlib import Path

from ..utils.metadata_handler import has_ual_metadata, read_ual_metadata, detect_link_mode
from ..utils.asset_switcher_db import get_switcher_db
from ..operators.material_preview import PREVIEW_SCENE_NAME


# ---------------------------------------------------------------------------
# Preview collections (thumbnail image caches)
# ---------------------------------------------------------------------------

preview_collections = {}


# ---------------------------------------------------------------------------
# Enum items caches (must stay alive to avoid Blender GC crash)
# ---------------------------------------------------------------------------

_version_items_cache = []
_version_cache_key = ""
_variant_items_cache = []
_variant_cache_key = ""
_last_cache_generation = 0


# ---------------------------------------------------------------------------
# Dynamic enum item callbacks
# ---------------------------------------------------------------------------

def _check_cache_generation():
    """Reset panel caches if the DB generation changed (e.g. after refresh)."""
    global _last_cache_generation, _version_cache_key, _variant_cache_key
    global _version_items_cache, _variant_items_cache
    db = get_switcher_db()
    if not db:
        return
    gen = db.cache_generation
    if gen != _last_cache_generation and _last_cache_generation != 0:
        # Only clear on explicit refresh (generation > 0), not on first draw
        _version_cache_key = ""
        _variant_cache_key = ""
        _version_items_cache = []
        _variant_items_cache = []
        for pcoll in preview_collections.values():
            pcoll.clear()
    _last_cache_generation = gen


def _get_version_items(self, context):
    """Build enum items for version thumbnails from the database."""
    global _version_items_cache, _version_cache_key

    _check_cache_generation()

    pcoll = preview_collections.get("versions")

    obj = context.active_object
    if not obj or not has_ual_metadata(obj):
        _version_items_cache = [('NONE', 'No Asset', 'Select a library asset', 0, 0)]
        return _version_items_cache

    metadata = read_ual_metadata(obj)
    vg_id = metadata.get('version_group_id', '')
    if not vg_id:
        _version_items_cache = [('NONE', 'No Versions', '', 0, 0)]
        return _version_items_cache

    # Return cached items if version_group hasn't changed
    if vg_id == _version_cache_key and _version_items_cache:
        return _version_items_cache

    db = get_switcher_db()
    if not db:
        _version_items_cache = [('NONE', 'DB Error', 'Database not connected', 0, 0)]
        return _version_items_cache

    versions = db.get_version_siblings(vg_id)
    if not versions:
        _version_items_cache = [('NONE', 'No Versions', '', 0, 0)]
        return _version_items_cache

    items = []
    for idx, v in enumerate(versions):
        uuid = v['uuid']
        label = v.get('version_label', 'v???')

        # Build tooltip
        extras = []
        if v.get('is_latest'):
            extras.append("Latest")
        if v.get('is_cold'):
            extras.append("Cold Storage")
        poly = v.get('polygon_count', 0) or 0
        if poly:
            extras.append(f"{poly:,} polys")
        desc = " | ".join(extras) if extras else label

        # Load thumbnail into preview collection
        icon_id = 0
        if pcoll is not None:
            thumb_path = v.get('thumbnail_path') or ''
            if thumb_path:
                resolved = str(Path(thumb_path).resolve())
                if Path(resolved).exists():
                    if uuid not in pcoll:
                        try:
                            preview = pcoll.load(uuid, resolved, 'IMAGE')
                            icon_id = preview.icon_id
                        except Exception as e:
                            pass
                    else:
                        icon_id = pcoll[uuid].icon_id

        items.append((uuid, label, desc, icon_id, idx))

    _version_items_cache = items
    _version_cache_key = vg_id
    return _version_items_cache


def _get_variant_items(self, context):
    """Build enum items for variant thumbnails from the database."""
    global _variant_items_cache, _variant_cache_key

    _check_cache_generation()

    pcoll = preview_collections.get("variants")

    obj = context.active_object
    if not obj or not has_ual_metadata(obj):
        _variant_items_cache = [('NONE', 'No Asset', '', 0, 0)]
        return _variant_items_cache

    metadata = read_ual_metadata(obj)
    asset_id = metadata.get('asset_id', '')
    if not asset_id:
        _variant_items_cache = [('NONE', 'No Variants', '', 0, 0)]
        return _variant_items_cache

    if asset_id == _variant_cache_key and _variant_items_cache:
        return _variant_items_cache

    db = get_switcher_db()
    if not db:
        _variant_items_cache = [('NONE', 'DB Error', '', 0, 0)]
        return _variant_items_cache

    variants = db.get_variant_siblings(asset_id)
    if not variants:
        _variant_items_cache = [('NONE', 'No Variants', '', 0, 0)]
        return _variant_items_cache

    items = []
    for idx, v in enumerate(variants):
        uuid = v['uuid']
        v_name = v.get('variant_name', 'Base')

        # Build tooltip
        extras = []
        v_label = v.get('version_label', '')
        if v_label:
            extras.append(v_label)
        poly = v.get('polygon_count', 0) or 0
        if poly:
            extras.append(f"{poly:,} polys")
        desc = " | ".join(extras) if extras else v_name

        icon_id = 0
        if pcoll is not None:
            thumb_path = v.get('thumbnail_path') or ''
            if thumb_path:
                resolved = str(Path(thumb_path).resolve())
                if Path(resolved).exists():
                    if uuid not in pcoll:
                        try:
                            preview = pcoll.load(uuid, resolved, 'IMAGE')
                            icon_id = preview.icon_id
                        except Exception as e:
                            pass
                    else:
                        icon_id = pcoll[uuid].icon_id

        items.append((uuid, v_name, desc, icon_id, idx))

    _variant_items_cache = items
    _variant_cache_key = asset_id
    return _variant_items_cache


# ---------------------------------------------------------------------------
# PropertyGroup
# ---------------------------------------------------------------------------

class UAL_SwitcherProps(PropertyGroup):
    """Properties for the asset switcher thumbnail grids."""
    version_enum: EnumProperty(
        items=_get_version_items,
        name="Version",
        description="Select a version to switch to",
    )
    variant_enum: EnumProperty(
        items=_get_variant_items,
        name="Variant",
        description="Select a variant to switch to",
    )
    representation_scope: EnumProperty(
        name="Scope",
        description="Apply representation swap to all libraries or only selected asset",
        items=[
            ('ALL', "All", "Swap all linked libraries in the scene"),
            ('SELECTED', "Selected", "Swap only the selected asset's library"),
        ],
        default='SELECTED',
    )


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class UAL_PT_asset_switcher_panel(Panel):
    """In-scene asset switcher with thumbnail grids"""
    bl_label = "Asset Switcher"
    bl_idname = "UAL_PT_asset_switcher_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Asset Library"
    bl_parent_id = "UAL_PT_main_panel"

    @classmethod
    def poll(cls, context):
        if context.scene.name.startswith(PREVIEW_SCENE_NAME):
            return False
        obj = context.active_object
        return obj is not None and has_ual_metadata(obj)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        metadata = read_ual_metadata(obj)
        if not metadata:
            return

        db = get_switcher_db()
        props = context.window_manager.ual_switcher

        # --- Header ---
        self._draw_header(layout, context, metadata, obj)

        if not db:
            layout.label(text="Database not connected", icon='ERROR')
            return

        # --- Version section ---
        self._draw_version_section(layout, context, metadata, db, props)

        # --- Variant section ---
        self._draw_variant_section(layout, context, metadata, db, props)

        # --- Representation section ---
        self._draw_representation_section(layout, context, metadata, props)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _draw_header(self, layout, context, metadata, obj):
        """Draw asset name, version, variant, mode, and refresh button."""
        header_box = layout.box()

        # Top row: name + refresh
        row = header_box.row()
        asset_name = metadata.get('asset_name', 'Unknown')
        version_label = metadata.get('version_label', 'v001')
        variant_name = metadata.get('variant_name', 'Base')
        name_text = f"{asset_name}  {version_label}"
        if variant_name != 'Base':
            name_text += f"  ({variant_name})"
        row.label(text=name_text, icon='OBJECT_DATA')
        row.operator("ual.refresh_switcher", text="", icon='FILE_REFRESH')

        # Mode row
        link_mode = detect_link_mode(obj)
        if link_mode:
            header_box.label(text=f"Mode: {link_mode}", icon='LINKED')

        # Batch indicator
        vg_id = metadata.get('version_group_id', '')
        if vg_id:
            batch_count = sum(
                1 for o in context.selected_objects
                if has_ual_metadata(o) and o.get('ual_version_group_id') == vg_id
            )
            if batch_count > 1:
                header_box.label(
                    text=f"{batch_count} objects selected (batch switch)",
                    icon='GROUP'
                )

    # ------------------------------------------------------------------
    # Version section
    # ------------------------------------------------------------------

    def _draw_version_section(self, layout, context, metadata, db, props):
        """Draw version thumbnail grid with switch button."""
        vg_id = metadata.get('version_group_id', '')
        if not vg_id:
            return

        versions = db.get_version_siblings(vg_id)
        if not versions:
            return

        box = layout.box()
        box.label(text=f"Version ({len(versions)} available)", icon='BOOKMARKS')

        # Thumbnail grid
        box.template_icon_view(props, "version_enum", show_labels=True)

        current_uuid = metadata.get('uuid', '')
        selected_uuid = props.version_enum

        # Info line about selected version
        if selected_uuid and selected_uuid != 'NONE':
            selected_info = None
            for v in versions:
                if v['uuid'] == selected_uuid:
                    selected_info = v
                    break

            if selected_info:
                info_parts = []
                if selected_info.get('is_latest'):
                    info_parts.append("Latest")
                if selected_info.get('is_cold'):
                    info_parts.append("Cold")
                poly = selected_info.get('polygon_count', 0) or 0
                if poly:
                    info_parts.append(f"{poly:,} polys")
                if info_parts:
                    box.label(text="  ".join(info_parts), icon='INFO')

        # Switch button or current indicator
        if selected_uuid == current_uuid or selected_uuid == 'NONE':
            box.label(text="Current version", icon='CHECKMARK')
        else:
            # Find label for selected version
            sel_label = selected_uuid[:8]
            for v in versions:
                if v['uuid'] == selected_uuid:
                    sel_label = v.get('version_label', sel_label)
                    # Warn about cold storage
                    if v.get('is_cold'):
                        row = box.row()
                        row.alert = True
                        row.label(text="In cold storage", icon='FREEZE')
                    break

            row = box.row()
            row.scale_y = 1.5
            op = row.operator(
                "ual.switch_version",
                text=f"Switch to {sel_label}",
                icon='FILE_REFRESH',
            )
            op.target_uuid = selected_uuid

    # ------------------------------------------------------------------
    # Representation section (Proxy/Render/Restore swap buttons)
    # ------------------------------------------------------------------

    def _draw_representation_section(self, layout, context, metadata, props):
        """Draw representation swap buttons (Proxy/Render/Restore)."""
        from ..operators.representation_swap import find_ual_libraries, get_libraries_for_objects

        asset_type = metadata.get('asset_type', '')
        if asset_type not in ('mesh', 'rig'):
            return

        box = layout.box()
        box.label(text="Representations", icon='FILE_REFRESH')

        # Proxy creation button
        row = box.row()
        row.scale_y = 1.2
        row.operator("ual.update_proxy", text="Save Proxy Version", icon='EXPORT')

        box.separator()

        # Check if there are any UAL libraries in the scene
        ual_libs = find_ual_libraries()
        if not ual_libs:
            box.label(text="No UAL assets linked", icon='INFO')
            return

        box.label(text=f"{len(ual_libs)} linked libraries", icon='LINKED')

        # Scope toggle: All vs Selected
        row = box.row(align=True)
        row.prop(props, "representation_scope", expand=True)

        use_selected = (props.representation_scope == 'SELECTED')

        # Swap buttons row: Proxy / Render / Nothing
        row = box.row(align=True)
        if use_selected:
            op = row.operator("ual.swap_representation_selected", text="Proxy", icon='MESH_CUBE')
            op.representation = 'proxy'
            op = row.operator("ual.swap_representation_selected", text="Render", icon='SHADING_RENDERED')
            op.representation = 'render'
            op = row.operator("ual.swap_representation_selected", text="Nothing", icon='GHOST_ENABLED')
            op.representation = 'nothing'
        else:
            op = row.operator("ual.swap_representation", text="Proxy", icon='MESH_CUBE')
            op.representation = 'proxy'
            op = row.operator("ual.swap_representation", text="Render", icon='SHADING_RENDERED')
            op.representation = 'render'
            op = row.operator("ual.swap_representation", text="Nothing", icon='GHOST_ENABLED')
            op.representation = 'nothing'

        # Restore button
        if use_selected:
            box.operator("ual.restore_representation_selected", text="Restore", icon='LOOP_BACK')
        else:
            box.operator("ual.restore_representation", text="Restore", icon='LOOP_BACK')

    # ------------------------------------------------------------------
    # Variant section
    # ------------------------------------------------------------------

    def _draw_variant_section(self, layout, context, metadata, db, props):
        """Draw variant thumbnail grid with switch button."""
        asset_id = metadata.get('asset_id', '')
        if not asset_id:
            return

        variants = db.get_variant_siblings(asset_id)
        if len(variants) <= 1:
            return

        box = layout.box()
        box.label(text=f"Variant ({len(variants)} available)", icon='MOD_ARRAY')

        # Thumbnail grid
        box.template_icon_view(props, "variant_enum", show_labels=True)

        current_variant = metadata.get('variant_name', 'Base')
        current_vg_id = metadata.get('version_group_id', '')
        selected_uuid = props.variant_enum

        # Determine if selected is current
        is_current = False
        selected_info = None
        selected_name = ''
        for v in variants:
            if v['uuid'] == selected_uuid:
                selected_info = v
                selected_name = v.get('variant_name', 'Base')
                is_current = (
                    selected_name == current_variant
                    and v.get('version_group_id', '') == current_vg_id
                )
                break

        # Info line
        if selected_info:
            info_parts = []
            v_label = selected_info.get('version_label', '')
            if v_label:
                info_parts.append(v_label)
            poly = selected_info.get('polygon_count', 0) or 0
            if poly:
                info_parts.append(f"{poly:,} polys")
            if info_parts:
                box.label(text="  ".join(info_parts), icon='INFO')

        if is_current or selected_uuid == 'NONE':
            box.label(text="Current variant", icon='CHECKMARK')
        else:
            row = box.row()
            row.scale_y = 1.5
            op = row.operator(
                "ual.switch_variant",
                text=f"Switch to {selected_name}",
                icon='FILE_REFRESH',
            )
            op.target_uuid = selected_uuid
            op.target_variant_name = selected_name


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = [
    UAL_SwitcherProps,
    UAL_PT_asset_switcher_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.ual_switcher = bpy.props.PointerProperty(
        type=UAL_SwitcherProps
    )
    # Create preview collections
    preview_collections["versions"] = bpy.utils.previews.new()
    preview_collections["variants"] = bpy.utils.previews.new()


def unregister():
    # Remove preview collections
    for key, pcoll in preview_collections.items():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()

    del bpy.types.WindowManager.ual_switcher
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_SwitcherProps',
    'UAL_PT_asset_switcher_panel',
    'register',
    'unregister',
]
