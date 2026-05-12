"""
Export to Library Operator

Exports selected objects to USD and adds them to the Universal Library.
"""

import bpy
import contextlib
import logging
import uuid
import json
import shutil
import os
from pathlib import Path
from datetime import datetime
from bpy.props import (
    StringProperty, BoolProperty, EnumProperty, IntProperty, CollectionProperty,
)
from bpy.types import Operator, PropertyGroup, UIList

from ..utils.library_connection import get_library_connection
from ..utils.material_converter import get_material_converter
from ..utils.naming_utils import get_asset_namer, set_custom_prefixes
from ..utils.metadata_collector import collect_all_metadata, collect_material_metadata
from ..utils.viewport_capture import capture_viewport_thumbnail, create_placeholder_thumbnail
from ..preferences import get_preferences, get_naming_prefixes
from ..gltf_action_filter import gltf_action_filter_session


logger = logging.getLogger(__name__)


# JSON Metadata Schema Version
METADATA_SCHEMA_VERSION = 1


@contextlib.contextmanager
def _silence_native_stdout():
    """Suppress Python-level stdout/stderr around a block.

    Blender's glTF exporter prints a lot of status during export
    (Draco encoder messages, image-format INFO lines, etc.). We
    redirect Python's stdout/stderr to /dev/null for the duration of
    the block so those don't clutter the user's console.

    Implementation choice: pure-Python `redirect_stdout/stderr` only
    (NOT fd-level `os.dup2`). The dup2 approach catches more output —
    including C-level prints — but breaks Python's `print()` on Windows
    with `OSError: [WinError 1] Incorrect function` because the gltf
    addon's `print()` calls find a stale TextIOWrapper state after the
    underlying fd has been swapped. Python-level redirect is safe and
    catches everything the gltf addon emits via Python; some pure-C
    Draco status may still leak, but no crash.

    Fail-open: if anything in the redirect setup fails (rare), we just
    run the block without suppression rather than aborting the export.
    """
    try:
        sink = open(os.devnull, 'w')
    except OSError:
        # If we can't even open devnull, run unredirected.
        yield
        return
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            yield
    finally:
        try:
            sink.close()
        except OSError:
            pass


def _wrap_for_dialog(text: str, width: int = 58) -> list:
    """Word-wrap a single warning string into ≤`width`-char lines.

    Blender's operator-dialog `layout.label(text=…)` does not word-wrap;
    long strings get clipped at the dialog's right edge. We split on word
    boundaries ourselves so multi-line warnings actually appear readable.
    """
    words = text.split()
    if not words:
        return [""]
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_asset_json_metadata(
    asset_uuid: str,
    name: str,
    asset_type: str,
    variant_name: str = "Base",
    asset_id: str = None,
    version: int = 1,
    version_label: str = "v001",
    version_group_id: str = None,
    is_latest: bool = True,
    representation_type: str = "none",
    description: str = "",
    author: str = "",
    tags: list = None,
    extended_metadata: dict = None
) -> dict:
    """
    Generate JSON metadata structure for an asset.

    This creates a sidecar JSON file with asset metadata that can be used for:
    - Rename validation (Blender can check if UUID/name matches library)
    - Portable libraries (share/backup without database)
    - Library scanning (reconstruct database from filesystem)
    - Cross-app consistency

    Args:
        asset_uuid: Unique asset UUID for this version
        name: Human-readable asset name
        asset_type: Type (mesh, material, rig, etc.)
        variant_name: Variant name (Base, Destroyed, etc.)
        asset_id: Asset family UUID (shared across variants)
        version: Version number
        version_label: Version label string (v001)
        version_group_id: Version group UUID (shared across versions)
        is_latest: Whether this is the latest version
        representation_type: Pipeline stage (model, lookdev, rig, final)
        description: Asset description
        author: Asset author
        tags: List of tags
        extended_metadata: Additional type-specific metadata

    Returns:
        Dictionary with full metadata structure
    """
    now = datetime.utcnow().isoformat() + 'Z'

    metadata = {
        # Identity (immutable except name)
        "uuid": asset_uuid,
        "name": name,
        "asset_type": asset_type,

        # Family (variant relationships)
        "variant_name": variant_name,
        "asset_id": asset_id or asset_uuid,
        "source_asset_name": None,

        # Versioning
        "version": version,
        "version_label": version_label,
        "version_group_id": version_group_id or asset_uuid,
        "is_latest": is_latest,

        # Pipeline stage
        "representation_type": representation_type,

        # Descriptive
        "description": description,
        "author": author,
        "tags": tags or [],

        # Temporal
        "created_date": now,
        "modified_date": now,

        # Source
        "source_application": f"Blender {bpy.app.version_string}",

        # Schema version for future migrations
        "metadata_version": METADATA_SCHEMA_VERSION,
    }

    # Add extended metadata (type-specific fields)
    if extended_metadata:
        metadata["extended"] = extended_metadata

    return metadata


def write_json_metadata(json_path: Path, metadata: dict) -> bool:
    """
    Write JSON metadata to file atomically.

    Uses temp file + rename pattern for atomic writes to prevent
    corruption if interrupted.

    Args:
        json_path: Path to write JSON file
        metadata: Metadata dictionary

    Returns:
        True if successful
    """
    try:
        # Ensure parent directory exists
        json_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first
        temp_path = json_path.with_suffix('.json.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        # Atomic rename
        os.replace(str(temp_path), str(json_path))
        return True

    except Exception:
        # Cleanup temp file if exists
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass
        return False


def read_json_metadata(json_path: Path) -> dict:
    """
    Read JSON metadata from file.

    Args:
        json_path: Path to JSON file

    Returns:
        Metadata dictionary or empty dict if not found/invalid
    """
    try:
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


class UAL_ActionPickerItem(PropertyGroup):
    """One row in the rig export's animation picker.

    The picker lists every OBJECT-rooted Action in the .blend so the user
    explicitly chooses which animations belong to *this* rig. The picked
    set drives both the .blend save (data_blocks for libraries.write) and
    the .glb export filter (gltf_action_filter_session). No bone-name
    heuristics, no NLA staging — the user is the source of truth.
    """
    action_name: StringProperty()
    include: BoolProperty(default=False)
    attached: BoolProperty(
        default=False,
        description="Whether this action is currently attached to the armature "
                    "(active action or in an NLA strip). Display-only hint."
    )


class UAL_UL_action_picker(UIList):
    """Scrollable checkbox list rendered inside the rig export dialog."""

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, 'include', text='')
        row.label(text=item.action_name)
        if item.attached:
            sub = row.row()
            sub.alignment = 'RIGHT'
            sub.label(text="(attached)", icon='ANIM_DATA')


class UAL_OT_export_to_library(Operator):
    """Export selected objects to Universal Library"""
    bl_idname = "ual.export_to_library"
    bl_label = "Export to Library"
    bl_description = "Export selected objects to the asset library"
    bl_options = {'REGISTER', 'UNDO'}

    # Properties
    asset_name: StringProperty(
        name="Asset Name",
        description="Name for the asset in the library",
        default=""
    )

    asset_type: EnumProperty(
        name="Asset Type",
        description="Type of asset being exported (data type)",
        items=[
            ('mesh', "Mesh", "3D geometry/mesh data"),
            ('material', "Material", "Material/shader only"),
            ('rig', "Rig", "Armature with rig controls"),
            ('light', "Light", "Light source or lighting setup"),
            ('camera', "Camera", "Camera or camera rig"),
            ('collection', "Collection", "Collection of objects"),
            ('grease_pencil', "Grease Pencil", "Grease Pencil drawing/animation"),
            ('curve', "Curve", "Curve, NURBS, or surface data"),
            ('other', "Other", "Other data type"),
        ],
        default='mesh'
    )

    representation_type: EnumProperty(
        name="Representation",
        description="Pipeline stage of this asset version",
        items=[
            ('none', "None", "No pipeline stage (cameras, lights, utilities)"),
            ('model', "Model", "Base geometry only"),
            ('lookdev', "Lookdev", "Model with materials/textures"),
            ('rig', "Rig", "Rigged for animation"),
            ('final', "Final", "Complete, render-ready asset"),
        ],
        default='none'
    )

    description: StringProperty(
        name="Description",
        description="Optional description for the asset",
        default=""
    )

    include_materials: BoolProperty(
        name="Include Materials",
        description="Export materials with geometry",
        default=True
    )

    include_animations: BoolProperty(
        name="Include Animations",
        description="Export animation data",
        default=True
    )

    # USD export temporarily disabled - Blender-centric workflow
    # export_usd: BoolProperty(
    #     name="Export USD",
    #     description="Also export USD file for interchange with other DCC apps",
    #     default=False
    # )

    export_selected_only: BoolProperty(
        name="Selected Only",
        description="Export only selected objects",
        default=True
    )

    # Versioning properties
    export_mode: EnumProperty(
        name="Export Mode",
        description="Export as new asset or new version of existing",
        items=[
            ('NEW_ASSET', "New Asset", "Create a brand new asset"),
            ('NEW_VERSION', "New Version", "Create new version of existing asset"),
            ('NEW_VARIANT', "New Variant", "Create new variant of existing asset"),
        ],
        default='NEW_ASSET'
    )

    archive_previous: BoolProperty(
        name="Archive Previous Version",
        description="Move previous version to cold storage",
        default=True
    )

    confirm_partial_export: BoolProperty(
        name="Confirm partial export",
        description=(
            "I'm intentionally saving fewer meshes/polygons than the previous "
            "version. Tick this only if you mean to shrink the asset; otherwise "
            "check your selection."
        ),
        default=False,
    )

    # M6: Attribution — by default the export inherits from addon prefs
    # (Preferences → Universal Library → Attribution Defaults). Tick the
    # `attr_override` box in the export dialog to set per-asset values
    # for this export only. The override does NOT change the defaults.
    attr_override: BoolProperty(
        name="Override Attribution",
        description=(
            "Use custom license / copyright / author for this asset only. "
            "Otherwise inherit from Preferences → Attribution Defaults."
        ),
        default=False,
    )
    attr_license_enum: EnumProperty(
        name="License",
        description="License code for this asset",
        items=[
            ('',             "—",                    ""),
            ('CC0',          "CC0 (Public Domain)",  ""),
            ('CC-BY',        "CC-BY",                ""),
            ('CC-BY-SA',     "CC-BY-SA",             ""),
            ('CC-BY-NC',     "CC-BY-NC",             ""),
            ('MIT',          "MIT",                  ""),
            ('GPL-3.0',      "GPL-3.0",              ""),
            ('Proprietary',  "Proprietary",          ""),
            ('Custom',       "Custom...",            ""),
        ],
        default='',
    )
    attr_license_custom: StringProperty(
        name="License (Custom)",
        description="Custom license text",
        default="",
    )
    attr_copyright: StringProperty(
        name="Copyright",
        description="Copyright string (e.g. '© 2026 Your Name')",
        default="",
    )
    attr_author: StringProperty(
        name="Author",
        description="Creator name",
        default="",
    )

    # Mesh-only: opt-in to save the user-organized collection structure
    # alongside the exported objects. Rigs always preserve collections
    # (they need them for bone widgets to link correctly), so this only
    # affects mesh exports — see _save_blend_backup() for the gating logic.
    preserve_collections: BoolProperty(
        name="Preserve Collections",
        description=(
            "Save the user-created collections that contain selected objects "
            "into the .blend so the same folder structure appears on re-import. "
            "Especially useful for kitbash sets and multi-collection assets "
            "imported via INSTANCE mode."
        ),
        default=False,
    )

    new_variant_name: StringProperty(
        name="Variant Name",
        description="Name for the new variant (e.g., 'Destroyed', 'Red')",
        default=""
    )

    # Rig-only: explicit picker of which Actions belong to this rig.
    # Populated in invoke() when the asset type is detected as 'rig'.
    # Drives both the .blend save and the .glb export filter.
    action_picker: CollectionProperty(type=UAL_ActionPickerItem)
    action_picker_index: IntProperty(default=0)

    # Hidden properties for version tracking (set automatically)
    source_uuid: StringProperty(default="")
    source_version_group_id: StringProperty(default="")
    source_version: bpy.props.IntProperty(default=0)
    source_asset_name: StringProperty(default="")
    has_ual_metadata: BoolProperty(default=False)
    # Variant system properties
    source_asset_id: StringProperty(default="")
    source_variant_name: StringProperty(default="Base")

    @classmethod
    def poll(cls, context):
        """Check if operator can run"""
        # Need at least one selected object or export_selected_only=False
        return context.selected_objects or not context.scene.get('ual_export_selected_only', True)

    def invoke(self, context, event):
        """Show dialog before export"""
        # Get preferences
        prefs = get_preferences()
        use_auto_naming = prefs.use_auto_naming if prefs else True

        # M6: Pre-fill attribution from prefs so the override fields show
        # the defaults as a *starting point* when the user ticks Override.
        # When override is off these props aren't used — execute() reads
        # prefs directly. We still populate them so toggling override on
        # mid-dialog doesn't show empty fields.
        if prefs is not None:
            try:
                # License: prefer the enum value; fall back to Custom +
                # custom text if the stored license is non-standard.
                license_val = prefs.default_license
                if license_val == 'Custom':
                    self.attr_license_enum = 'Custom'
                    self.attr_license_custom = prefs.default_license_custom
                elif license_val:
                    self.attr_license_enum = license_val
                    self.attr_license_custom = ""
                else:
                    self.attr_license_enum = ''
                    self.attr_license_custom = ""
                self.attr_copyright = prefs.default_copyright
                self.attr_author = prefs.default_author
                # Default: override off (use prefs)
                self.attr_override = False
            except Exception:
                pass

        # Check for UAL metadata on selected objects (imported from library)
        self._check_ual_metadata(context)

        # Auto-detect type first (needed for naming)
        if context.selected_objects:
            self.asset_type = self._detect_asset_type(context.selected_objects)

            # Populate the rig action picker. Pre-checks the actions currently
            # attached to the selected armature (active + NLA strip references),
            # leaves everything else unchecked. The user explicitly picks the
            # extras they want shipped.
            self._populate_action_picker(context)

            # If we have UAL metadata, use the source asset name and suggest new version
            if self.has_ual_metadata and self.source_asset_name:
                self.asset_name = self.source_asset_name
                self.export_mode = 'NEW_VERSION'
                # Suggest next representation stage based on current
                self._suggest_representation()
            elif use_auto_naming:
                # Configure namer with user prefixes
                set_custom_prefixes(get_naming_prefixes())
                namer = get_asset_namer()
                self.asset_name = namer.generate_from_objects(
                    context.selected_objects,
                    self.asset_type,
                    use_prefix=True
                )
            else:
                # Simple default naming
                if len(context.selected_objects) == 1:
                    self.asset_name = context.selected_objects[0].name
                else:
                    self.asset_name = f"Asset_{len(context.selected_objects)}_objects"

        return context.window_manager.invoke_props_dialog(self, width=400)

    def _check_ual_metadata(self, context):
        """Check if selected objects have UAL metadata from library import"""
        self.has_ual_metadata = False
        self.source_uuid = ""
        self.source_version_group_id = ""
        self.source_version = 0
        self.source_asset_name = ""
        self.source_asset_id = ""
        self.source_variant_name = "Base"

        for obj in context.selected_objects:
            # Debug: print custom properties
            if obj.get("ual_imported"):
                self.has_ual_metadata = True
                self.source_uuid = obj.get("ual_uuid", "")
                self.source_version_group_id = obj.get("ual_version_group_id", "")
                self.source_version = obj.get("ual_version", 0)
                self.source_asset_name = obj.get("ual_asset_name", "")
                # Variant system - fallback to version_group_id for legacy objects
                self.source_asset_id = obj.get("ual_asset_id", self.source_version_group_id)
                self.source_variant_name = obj.get("ual_variant_name", "Base")

                # Get representation type from source
                src_rep = obj.get("ual_representation_type", "none")
                if src_rep in ['none', 'model', 'lookdev', 'rig', 'final']:
                    self.representation_type = src_rep

                break  # Use first object with metadata

    def _suggest_representation(self):
        """Suggest next representation based on current and changes"""
        # If current is model and we're adding materials, suggest lookdev
        current_rep = self.representation_type

        # Simple heuristic: if adding materials to a model, suggest lookdev
        if current_rep == 'model' and self.include_materials:
            has_materials = any(
                obj.type == 'MESH' and len(obj.material_slots) > 0
                for obj in bpy.context.selected_objects
            )
            if has_materials:
                self.representation_type = 'lookdev'

    def draw(self, context):
        """Draw dialog UI"""
        layout = self.layout

        # Presets row
        row = layout.row(align=True)
        row.menu("UAL_MT_export_presets", text="Presets", icon='PRESET')
        row.operator("ual.save_export_preset", text="", icon='ADD')

        layout.separator()

        # Versioning section (if imported from library)
        if self.has_ual_metadata:
            version_box = layout.box()
            version_box.label(text="Versioning:", icon='FILE_REFRESH')

            # Show source info with variant name
            info_row = version_box.row()
            variant_str = f" [{self.source_variant_name}]" if self.source_variant_name != "Base" else ""
            info_row.label(text=f"Source: {self.source_asset_name}{variant_str} (v{self.source_version:03d})")

            # Export mode selection
            version_box.prop(self, "export_mode", expand=True)

            if self.export_mode == 'NEW_VERSION':
                next_version = self.source_version + 1
                version_box.label(text=f"Will create: v{next_version:03d}", icon='INFO')
                version_box.prop(self, "archive_previous")

                # Partial-export warning (catches accidental single-mesh re-exports)
                partial_info = self._check_partial_export(context)
                if partial_info:
                    self._draw_partial_export_warning(layout, partial_info)

                # Show version comparison
                self._draw_version_comparison(context, layout)

            elif self.export_mode == 'NEW_VARIANT':
                version_box.prop(self, "new_variant_name")
                if self.new_variant_name:
                    version_box.label(text=f"Will create: {self.new_variant_name} v001", icon='INFO')
                else:
                    version_box.label(text="Enter a variant name", icon='ERROR')

            # Version history button
            version_box.separator()
            op = version_box.operator("ual.show_version_history", text="View All Versions", icon='TIME')
            op.version_group_id = self.source_version_group_id
            op.asset_name = self.source_asset_name

            layout.separator()

        layout.prop(self, "asset_name")
        layout.prop(self, "asset_type")
        layout.prop(self, "representation_type")

        # Show naming validation warning
        prefs = get_preferences()
        if prefs and prefs.validate_names and self.asset_name:
            set_custom_prefixes(get_naming_prefixes())
            namer = get_asset_namer()
            is_valid, message = namer.validate_name(self.asset_name, self.asset_type)
            if not is_valid:
                warn_row = layout.row()
                warn_row.alert = True
                warn_row.label(text=message, icon='ERROR')
                # Show suggested fix
                suggested = namer.suggest_fix(self.asset_name, self.asset_type)
                if suggested != self.asset_name:
                    fix_row = layout.row()
                    fix_row.label(text=f"Suggested: {suggested}", icon='INFO')

        layout.prop(self, "description")

        layout.separator()

        box = layout.box()
        box.label(text="Export Options:")
        box.prop(self, "include_materials")
        box.prop(self, "include_animations")
        box.prop(self, "export_selected_only")

        # M6: Attribution. Default: read-only display of values inherited
        # from addon prefs (grayed out — same look as Blender's modifier
        # overrides). Tick "Override" to set per-asset values; those values
        # apply ONLY to this export and do not update the defaults.
        attr_box = layout.box()
        header = attr_box.row()
        header.label(text="Attribution:", icon='USER')
        header.prop(self, "attr_override", text="Override")

        if self.attr_override:
            attr_box.prop(self, "attr_license_enum", text="License")
            if self.attr_license_enum == 'Custom':
                attr_box.prop(self, "attr_license_custom", text="")
            attr_box.prop(self, "attr_copyright", text="Copyright")
            attr_box.prop(self, "attr_author", text="Author")
        else:
            # Read-only inheritance view. Pull live from prefs so any change
            # the user makes in Preferences without closing the dialog is
            # reflected on the next redraw.
            col = attr_box.column(align=True)
            col.enabled = False
            license_display = "—"
            cr_display = "—"
            author_display = "—"
            if prefs is not None:
                try:
                    resolved = prefs._resolved_license()
                    license_display = resolved if resolved else "—"
                    cr_display = prefs.default_copyright or "—"
                    author_display = prefs.default_author or "—"
                except Exception:
                    pass
            col.label(text=f"License: {license_display}")
            col.label(text=f"Copyright: {cr_display}")
            col.label(text=f"Author: {author_display}")

        # Mesh-only: opt-in collection preservation. Rigs already do this
        # automatically because bone widgets need it, so we don't show the
        # checkbox for them.
        if self.asset_type == 'mesh':
            box.prop(self, "preserve_collections")

        # Rig-only: soft warning when the armature is parented only to the
        # Scene Collection root while meshes live in a sub-collection. This
        # is the "armature vanishes on INSTANCE import" pitfall.
        if self.asset_type == 'rig':
            arm_warning = self._check_armature_collection_warning(context)
            if arm_warning:
                warn_box = layout.box()
                warn_row = warn_box.row()
                warn_row.alert = True
                warn_row.label(text="Armature collection warning:", icon='ERROR')
                # Wrap the message across multiple label rows since Blender
                # doesn't word-wrap a single label inside an operator dialog.
                for line in _wrap_for_dialog(arm_warning, width=58):
                    warn_box.label(text=line)

        # Rig-only: explicit animation picker. Drives both .blend save and
        # .glb export — no bone-name guessing, no NLA staging.
        if self.asset_type == 'rig' and len(self.action_picker) > 0:
            anim_box = layout.box()
            anim_box.label(text="Animations to include:", icon='ANIM')
            row_count = min(8, max(3, len(self.action_picker)))
            anim_box.template_list(
                'UAL_UL_action_picker', '',
                self, 'action_picker',
                self, 'action_picker_index',
                rows=row_count,
            )
            # Quick summary so the user can see how many they've picked
            picked = sum(1 for it in self.action_picker if it.include)
            anim_box.label(
                text=f"{picked} of {len(self.action_picker)} selected",
                icon='CHECKMARK' if picked else 'INFO',
            )

        # USD export temporarily disabled - Blender-centric workflow
        # box.separator()
        # box.prop(self, "export_usd")

        # Show material warnings
        if self.include_materials:
            warnings = self._check_material_warnings(context)
            if warnings:
                layout.separator()
                warn_box = layout.box()
                warn_box.label(text="Material Warnings:", icon='ERROR')
                for warn in warnings[:3]:
                    warn_box.label(text=warn)

    def execute(self, context):
        """Execute the export"""
        if not self.asset_name:
            self.report({'ERROR'}, "Asset name is required")
            return {'CANCELLED'}

        # Validate variant name for NEW_VARIANT mode
        if self.export_mode == 'NEW_VARIANT':
            if not self.new_variant_name:
                self.report({'ERROR'}, "Variant name is required")
                return {'CANCELLED'}
            if self.new_variant_name.lower() == 'base':
                self.report({'ERROR'}, "'Base' is reserved and cannot be used as a variant name")
                return {'CANCELLED'}

        # Get library connection
        library = get_library_connection()

        # Determine if this is a new version or new asset
        # If name changed from source, treat as new asset even if mode is NEW_VERSION
        name_changed = self.asset_name != self.source_asset_name
        is_new_version = (
            self.export_mode == 'NEW_VERSION' and
            self.has_ual_metadata and
            self.source_version_group_id and
            not name_changed  # Different name = new asset, not new version
        )
        is_new_variant = (
            self.export_mode == 'NEW_VARIANT' and
            self.has_ual_metadata and
            self.source_asset_id
        )

        # Collision check: For new assets, check if name already exists within same type
        if not is_new_version and not is_new_variant:
            if library.asset_name_exists(self.asset_name, asset_type=self.asset_type):
                self.report(
                    {'ERROR'},
                    f"A {self.asset_type} asset named '{self.asset_name}' already exists! "
                    "Please choose a different name, or use 'New Version' to add a version."
                )
                return {'CANCELLED'}

        # Retirement check: For new versions/variants, verify source asset isn't retired
        if (is_new_version or is_new_variant) and self.source_uuid:
            source_asset = library.get_asset_by_uuid(self.source_uuid)
            if source_asset and source_asset.get('is_retired'):
                self.report(
                    {'ERROR'},
                    f"Asset '{self.source_asset_name}' has been retired. "
                    "Cannot add new versions to a retired asset. "
                    "Restore it first or export as a new asset."
                )
                return {'CANCELLED'}

        # Partial-export guard: if the current selection is much smaller than the
        # previous version, abort unless the user explicitly confirmed.
        if is_new_version and not self.confirm_partial_export:
            partial_info = self._check_partial_export(context)
            if partial_info:
                self.report(
                    {'ERROR'},
                    f"Selection looks smaller than previous version "
                    f"({partial_info['prev_label']}): "
                    f"{partial_info['curr_meshes']} mesh(es) / {partial_info['curr_polys']:,} polys "
                    f"vs {partial_info['prev_meshes']} mesh(es) / {partial_info['prev_polys']:,} polys. "
                    "If this is intentional, tick 'Confirm partial export' in the dialog and try again."
                )
                return {'CANCELLED'}

        # Generate UUID for new asset
        asset_uuid = str(uuid.uuid4())

        # Version info
        if is_new_version:
            version_group_id = self.source_version_group_id
            version = self.source_version + 1
            version_label = f"v{version:03d}"
            # Preserve asset_id and variant_name from source
            asset_id = self.source_asset_id or version_group_id
            variant_name = self.source_variant_name or "Base"
        elif is_new_variant:
            # New variant: same family (asset_id), new variant name, version starts at 1
            version_group_id = asset_uuid  # New version chain for this variant
            version = 1
            version_label = "v001"
            asset_id = self.source_asset_id  # Same family as source
            variant_name = self.new_variant_name  # New variant name
        else:
            # New asset - UUID is also the version_group_id and asset_id
            version_group_id = asset_uuid
            version = 1
            version_label = "v001"
            # New asset gets its own asset_id and default "Base" variant
            asset_id = asset_uuid
            variant_name = "Base"

        # Get asset folder using library structure
        # library/{type}/{name}/{variant}/ - for latest only
        library_folder = library.get_library_folder_path(
            asset_id, self.asset_name, variant_name, self.asset_type
        )

        try:
            import shutil

            # If this is a new version, archive the PREVIOUS version first
            # Move files from library/ to _archive/{type}/{version}/ before saving new
            if is_new_version and self.source_uuid:
                previous_version_label = f"v{self.source_version:03d}"
                prev_archive_folder = library.get_archive_folder_path(
                    asset_id, self.asset_name, variant_name, previous_version_label, self.asset_type
                )
                # Move current library files to archive (previous version)
                # Skip representation files (.current.blend, .proxy.blend, .render.blend)
                # — they belong to the library folder, not any single version.
                skip_suffixes = ('.current.blend', '.proxy.blend', '.render.blend')
                if library_folder.exists():
                    for file in library_folder.iterdir():
                        if file.is_file() and not any(file.name.endswith(s) for s in skip_suffixes):
                            shutil.move(str(file), str(prev_archive_folder / file.name))

            # Primary format: .blend file (saved to library only - it's the latest)
            # Include version in filename to prevent Blender from merging libraries
            blend_filename = f"{self.asset_name}.{version_label}.blend"

            # Update metadata on objects BEFORE saving so the .blend contains correct metadata
            # This ensures child meshes get new rig metadata, not stale independent asset metadata
            self._update_object_metadata(context, asset_uuid, version_group_id, version, version_label,
                                         asset_id, variant_name)

            # Save to library (active/latest)
            library_blend_path = library_folder / blend_filename
            self._save_blend_backup(context, str(library_blend_path))

            if not library_blend_path.exists():
                self.report({'ERROR'}, "Failed to save .blend file")
                return {'CANCELLED'}

            # Create .current.blend for representation swap support
            from ..utils.current_reference_helper import create_current_reference
            create_current_reference(library_blend_path)

            # Use library path as the primary blend_backup_path
            blend_path = library_blend_path

            # USD export temporarily disabled - Blender-centric workflow
            usd_path = None

            # Generate thumbnail (versioned to match blend file)
            thumbnail_filename = f"thumbnail.{version_label}.png"
            thumbnail_versioned = library_folder / thumbnail_filename
            self._generate_thumbnail(context, str(thumbnail_versioned))
            
            # Also create thumbnail.current.png (stable path for cache watching)
            # DB stores thumbnail.current.png for latest version
            thumbnail_current = library_folder / "thumbnail.current.png"
            if thumbnail_versioned.exists():
                shutil.copy2(str(thumbnail_versioned), str(thumbnail_current))
            
            # Export glTF preview for WL/3D viewport (mesh, collection, rig).
            # Rigs export at rest pose with their bound meshes only — no joints
            # or animation. Camera/light/material/etc. don't need 3D preview.
            if self.asset_type in ('mesh', 'collection', 'rig'):
                gltf_filename = f"preview.{version_label}.glb"
                gltf_versioned = library_folder / gltf_filename
                self._export_gltf_preview(context, str(gltf_versioned))

                # Also create preview.current.glb (stable path)
                gltf_current = library_folder / "preview.current.glb"
                if gltf_versioned.exists():
                    shutil.copy2(str(gltf_versioned), str(gltf_current))
            
            # For DB and archive, use appropriate paths
            thumbnail_path = thumbnail_current  # Latest uses .current for cache watching

            # Collect metadata
            metadata = self._collect_metadata(context)

            # Generate JSON sidecar metadata file (versioned to match blend)
            json_filename = f"{self.asset_name}.{version_label}.json"
            json_path = library_folder / json_filename
            json_metadata = generate_asset_json_metadata(
                asset_uuid=asset_uuid,
                name=self.asset_name,
                asset_type=self.asset_type,
                variant_name=variant_name,
                asset_id=asset_id,
                version=version,
                version_label=version_label,
                version_group_id=version_group_id,
                is_latest=True,
                representation_type=self.representation_type,
                description=self.description,
                author='',
                tags=[],
                extended_metadata=metadata
            )
            write_json_metadata(json_path, json_metadata)

            # Copy all files to archive for this version as well
            # Archive contains complete history, library is just the latest
            # Archive uses versioned thumbnail, not .current
            archive_folder = library.get_archive_folder_path(
                asset_id, self.asset_name, variant_name, version_label, self.asset_type
            )
            for src_file in [library_blend_path, thumbnail_versioned, json_path]:
                if src_file.exists():
                    shutil.copy2(str(src_file), str(archive_folder / src_file.name))

            # Serialize texture_maps list to JSON if present
            texture_maps = metadata.get('texture_maps')
            if texture_maps and isinstance(texture_maps, list):
                texture_maps = json.dumps(texture_maps)

            # Add to library database
            # Primary format is .blend, USD is optional for interchange
            asset_data = {
                'uuid': asset_uuid,
                'name': self.asset_name,
                'description': self.description,
                'folder_id': 1,  # Root folder
                'asset_type': self.asset_type,
                'representation_type': self.representation_type,
                'usd_file_path': str(usd_path) if usd_path and usd_path.exists() else None,
                'blend_backup_path': str(blend_path),  # Primary file
                'thumbnail_path': str(thumbnail_path) if thumbnail_path.exists() else None,
                'file_size_mb': blend_path.stat().st_size / (1024 * 1024) if blend_path.exists() else 0,
                'has_materials': 1 if metadata.get('material_count', 0) > 0 else 0,
                'has_skeleton': metadata.get('has_skeleton', 0),
                'has_animations': metadata.get('has_animations', 0),
                'polygon_count': metadata.get('polygon_count', 0),
                'material_count': metadata.get('material_count', 0),
                'tags': [],
                # M6: Attribution — resolved from prefs OR override
                # (see _resolve_attribution). Author, license, copyright
                # are baked in here; the app's metadata panel displays
                # them read-only.
                **self._resolve_attribution(),
                'source_application': f'Blender {bpy.app.version_string}',
                # Versioning fields
                'version': version,
                'version_label': version_label,
                'version_group_id': version_group_id,
                'is_latest': 1,
                'parent_version_uuid': self.source_uuid if is_new_version else None,
                'variant_source_uuid': self.source_uuid if is_new_variant else None,
                # Variant system fields
                'asset_id': asset_id,
                'variant_name': variant_name,
                # Extended metadata fields (Phase 4)
                'bone_count': metadata.get('bone_count'),
                'has_facial_rig': metadata.get('has_facial_rig', 0),
                'control_count': metadata.get('control_count'),
                'frame_start': metadata.get('frame_start'),
                'frame_end': metadata.get('frame_end'),
                'frame_rate': metadata.get('frame_rate'),
                'is_loop': metadata.get('is_loop', 0),
                'texture_maps': texture_maps,
                'texture_resolution': metadata.get('texture_resolution'),
                'light_type': metadata.get('light_type'),
                'light_count': metadata.get('light_count'),
                'light_power': metadata.get('light_power'),
                'light_color': metadata.get('light_color'),
                'light_shadow': metadata.get('light_shadow'),
                'light_spot_size': metadata.get('light_spot_size'),
                'light_area_shape': metadata.get('light_area_shape'),
                'camera_type': metadata.get('camera_type'),
                'focal_length': metadata.get('focal_length'),
                'camera_sensor_width': metadata.get('camera_sensor_width'),
                'camera_clip_start': metadata.get('camera_clip_start'),
                'camera_clip_end': metadata.get('camera_clip_end'),
                'camera_dof_enabled': metadata.get('camera_dof_enabled'),
                'camera_ortho_scale': metadata.get('camera_ortho_scale'),
                # Bounding box (world-space dimensions)
                'bbox_x': metadata.get('bbox_x'),
                'bbox_y': metadata.get('bbox_y'),
                'bbox_z': metadata.get('bbox_z'),
                # Mesh extended metadata
                'vertex_group_count': metadata.get('vertex_group_count'),
                'shape_key_count': metadata.get('shape_key_count'),
                # Grease Pencil metadata
                'layer_count': metadata.get('layer_count'),
                'stroke_count': metadata.get('stroke_count'),
                'frame_count': metadata.get('frame_count'),
                # Curve metadata
                'curve_type': metadata.get('curve_type'),
                'point_count': metadata.get('point_count'),
                'spline_count': metadata.get('spline_count'),
            }

            # If new version, update previous version in database
            if is_new_version and self.source_uuid:
                previous_version_label = f"v{self.source_version:03d}"
                prev_archive_folder = library.get_archive_folder_path(
                    asset_id, self.asset_name, variant_name, previous_version_label, self.asset_type
                )
                # Update previous version: mark as not latest, update paths to archive
                # Use versioned filename for archived version
                prev_blend_filename = f"{self.asset_name}.{previous_version_label}.blend"
                prev_thumbnail_filename = f"thumbnail.{previous_version_label}.png"
                library.update_asset(self.source_uuid, {
                    'is_latest': 0,
                    'is_cold': 1,
                    'is_immutable': 1,
                    'cold_storage_path': str(prev_archive_folder),
                    'blend_backup_path': str(prev_archive_folder / prev_blend_filename),
                    'thumbnail_path': str(prev_archive_folder / prev_thumbnail_filename),
                })

            # Add the new asset/version
            library.add_asset(asset_data)

            # Copy folder memberships from source to new asset
            # - New version: inherits folders from previous version (same variant)
            # - New variant: inherits folders from source variant (same family)
            if (is_new_version or is_new_variant) and self.source_uuid:
                library.copy_folders_to_asset(self.source_uuid, asset_uuid)
                library.copy_tags_to_asset(self.source_uuid, asset_uuid)

            # Note: _update_object_metadata was already called before save to ensure the .blend
            # file has correct metadata. This second call ensures the current scene objects
            # also have updated metadata for continued editing (redundant but safe).
            self._update_object_metadata(context, asset_uuid, version_group_id, version, version_label,
                                         asset_id, variant_name)

            if is_new_version:
                self.report({'INFO'}, f"Exported '{self.asset_name}' as {version_label}")
            elif is_new_variant:
                self.report({'INFO'}, f"Exported '{self.asset_name}' as variant '{variant_name}' {version_label}")
            else:
                self.report({'INFO'}, f"Exported '{self.asset_name}' to library")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            import traceback
            traceback.print_exc()
            # Cleanup on failure
            try:
                if library_folder.exists():
                    shutil.rmtree(library_folder, ignore_errors=True)
            except Exception:
                pass
            return {'CANCELLED'}

    def _update_object_metadata(self, context, asset_uuid, version_group_id, version, version_label,
                                  asset_id, variant_name):
        """
        Update UAL metadata on ALL objects in the export hierarchy.
        
        This OVERWRITES any existing metadata, which is intentional:
        - When saving a rig, child meshes that were previously independent assets
          get new metadata pointing to this rig asset (not their old mesh asset)
        - This prevents accidental updates to independent assets when editing
          a rig that absorbed them
        """
        objects = context.selected_objects if self.export_selected_only else context.scene.objects

        # Expand to full export hierarchy (children, parents, custom shapes)
        # All objects get the SAME metadata - they're all part of this asset now
        all_objects = set(objects)
        for obj in list(all_objects):
            for child in obj.children_recursive:
                all_objects.add(child)
            parent = obj.parent
            while parent:
                all_objects.add(parent)
                parent = parent.parent
            if obj.type == 'ARMATURE' and obj.pose:
                for pose_bone in obj.pose.bones:
                    if pose_bone.custom_shape is not None:
                        all_objects.add(pose_bone.custom_shape)

        for obj in all_objects:
            obj["ual_uuid"] = asset_uuid
            obj["ual_version_group_id"] = version_group_id
            obj["ual_version"] = version
            obj["ual_version_label"] = version_label
            obj["ual_asset_name"] = self.asset_name
            obj["ual_asset_type"] = self.asset_type
            obj["ual_representation_type"] = self.representation_type
            obj["ual_imported"] = True
            # Variant system
            obj["ual_asset_id"] = asset_id
            obj["ual_variant_name"] = variant_name

    def _detect_asset_type(self, objects) -> str:
        """Auto-detect asset type from selected objects"""
        has_armature = any(obj.type == 'ARMATURE' for obj in objects)
        has_mesh = any(obj.type == 'MESH' for obj in objects)
        has_light = any(obj.type == 'LIGHT' for obj in objects)
        has_camera = any(obj.type == 'CAMERA' for obj in objects)
        has_gp = any(obj.type in ('GPENCIL', 'GREASEPENCIL') for obj in objects)
        has_curve = any(obj.type in ('CURVE', 'CURVES', 'SURFACE') for obj in objects)

        # Check for pure type selections first
        if has_light and not has_mesh and not has_armature:
            return 'light'
        if has_camera and not has_mesh and not has_armature:
            return 'camera'
        if has_gp and not has_mesh and not has_armature:
            return 'grease_pencil'
        if has_curve and not has_mesh and not has_armature:
            return 'curve'

        if has_armature:
            return 'rig'

        return 'mesh'

    def _resolve_attribution(self) -> dict:
        """M6: pick the attribution values for this export.

        If `attr_override` is on, use the per-export values from the
        dialog. Otherwise inherit from Preferences → Attribution Defaults.
        Returns a dict ready to merge into `asset_data`.
        """
        if self.attr_override:
            if self.attr_license_enum == 'Custom':
                license_value = self.attr_license_custom.strip() or 'Custom'
            else:
                license_value = self.attr_license_enum
            copyright_value = self.attr_copyright.strip()
            author_value = self.attr_author.strip()
        else:
            prefs = get_preferences()
            if prefs is not None:
                try:
                    license_value = prefs._resolved_license()
                    copyright_value = prefs.default_copyright
                    author_value = prefs.default_author
                except Exception:
                    license_value = copyright_value = author_value = ''
            else:
                license_value = copyright_value = author_value = ''

        return {
            'author': author_value or '',
            'license': license_value or None,
            'copyright': copyright_value or None,
        }

    def _check_armature_collection_warning(self, context) -> str:
        """Detect the "armature in Scene Collection root" rig-export pitfall.

        Returns a user-facing warning string when:
            - we are exporting a rig (asset_type == 'rig')
            - the armature object is NOT in any user-created sub-collection
              (i.e. it lives only in the Scene Collection root)
            - AND at least one selected mesh IS in a user-created sub-collection

        The mechanics: `_save_blend_backup` iterates `bpy.data.collections` to
        decide which collections to bundle into the .blend. `bpy.data.collections`
        excludes the Scene Collection root, so an armature parented only there
        has no collection saved with it. On INSTANCE import the linked collection
        contains only the meshes — the armature appears to vanish.

        IMPORTANT — Blender API gotcha:
        `obj.users_collection` INCLUDES the master Scene Collection
        (`scene.collection`). An object that lives "only in the root" still
        returns `(scene.collection,)` here, not an empty tuple. So we have
        to explicitly compare against `scene.collection` rather than just
        truth-testing the result.

        Returns empty string when the check doesn't apply or no issue is detected.
        """
        if self.asset_type != 'rig':
            return ""

        selected = context.selected_objects
        if not selected:
            return ""

        armatures = [o for o in selected if o.type == 'ARMATURE']
        if not armatures:
            return ""

        # Rig export pulls in bound meshes automatically — user only needs
        # to select the armature. Use the same resolver the actual export
        # uses so the warning reflects what will actually be saved.
        meshes = self._collect_rig_export_meshes(selected)
        if not meshes:
            return ""

        scene_root = context.scene.collection

        def _in_subcollection(obj):
            """True if obj is a member of any collection other than the scene root."""
            for col in obj.users_collection:
                if col != scene_root:
                    return True
            return False

        armature_in_sub = any(_in_subcollection(arm) for arm in armatures)
        mesh_in_sub = any(_in_subcollection(m) for m in meshes)

        if not armature_in_sub and mesh_in_sub:
            arm_name = armatures[0].name if len(armatures) == 1 else f"{len(armatures)} armatures"
            return (
                f"'{arm_name}' is in the Scene Collection (root). "
                "On INSTANCE import the armature won't appear, because only "
                "sub-collections are saved with the asset. "
                "Move the armature into a sub-collection (with the meshes "
                "or its own) before exporting."
            )

        return ""

    def _check_material_warnings(self, context) -> list:
        """Check for material conversion warnings"""
        warnings = []
        converter = get_material_converter()

        checked_materials = set()
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue

            for slot in obj.material_slots:
                if not slot.material or slot.material.name in checked_materials:
                    continue

                checked_materials.add(slot.material.name)
                complexity = converter.get_material_complexity(slot.material)

                if complexity == 'complex':
                    warnings.append(f"'{slot.material.name}': Complex nodes will be simplified")
                elif complexity == 'moderate':
                    warnings.append(f"'{slot.material.name}': Some features may be lost")

        return warnings

    # ------------------------------------------------------------------
    # Partial-export safeguard
    # ------------------------------------------------------------------

    # Suspicious shrink threshold: current must be < 50% of previous AND
    # previous must be substantial enough that the drop is meaningful.
    _PARTIAL_DROP_THRESHOLD = 0.5
    _PARTIAL_MIN_PREV_POLYS = 1000
    _PARTIAL_MIN_PREV_MESHES = 2

    def _check_partial_export(self, context):
        """
        Check if this looks like an accidental partial re-export.

        Catches the gotcha where a user selects ONE mesh from a multi-mesh
        asset that still carries UAL metadata and exports — which would
        replace the whole asset with just that one mesh.

        Returns:
            dict with prev_polys, prev_meshes, curr_polys, curr_meshes if a
            suspicious drop is detected. None otherwise.
        """
        # Only relevant for re-exports of an existing asset
        if self.export_mode != 'NEW_VERSION' or not self.has_ual_metadata or not self.source_uuid:
            return None

        try:
            library = get_library_connection()
            prev_asset = library.get_asset_by_uuid(self.source_uuid)
        except Exception:
            return None
        if not prev_asset:
            return None

        prev_polys = prev_asset.get('polygon_count') or 0
        prev_meshes = prev_asset.get('mesh_count') or 0

        # Fallback: if mesh_count wasn't stored on previous (older plugin),
        # treat "has_skeleton or many polys" as a multi-object asset for
        # the warning threshold. Otherwise we can only act on poly count.

        sel = context.selected_objects or []
        curr_polys = 0
        curr_meshes = 0
        for obj in sel:
            if obj.type == 'MESH' and obj.data:
                curr_polys += len(obj.data.polygons)
                curr_meshes += 1

        poly_drop = (
            prev_polys >= self._PARTIAL_MIN_PREV_POLYS and
            curr_polys < prev_polys * self._PARTIAL_DROP_THRESHOLD
        )
        mesh_drop = (
            prev_meshes >= self._PARTIAL_MIN_PREV_MESHES and
            curr_meshes < prev_meshes * self._PARTIAL_DROP_THRESHOLD
        )

        if not (poly_drop or mesh_drop):
            return None

        return {
            'prev_polys': prev_polys,
            'prev_meshes': prev_meshes,
            'curr_polys': curr_polys,
            'curr_meshes': curr_meshes,
            'prev_label': prev_asset.get('version_label', 'v???'),
        }

    def _draw_partial_export_warning(self, layout, info):
        """Yellow warning box in the export dialog with the confirm checkbox."""
        warn_box = layout.box()
        warn_box.alert = True
        warn_box.label(text="Smaller selection than previous version", icon='ERROR')
        warn_box.label(
            text=f"  Previous ({info['prev_label']}): "
                 f"{info['prev_meshes']} mesh(es), {info['prev_polys']:,} polys"
        )
        warn_box.label(
            text=f"  Current selection: "
                 f"{info['curr_meshes']} mesh(es), {info['curr_polys']:,} polys"
        )
        warn_box.label(
            text="Did you only select one mesh from a multi-mesh asset?",
            icon='QUESTION'
        )
        warn_box.prop(self, "confirm_partial_export")

    def _draw_version_comparison(self, context, layout):
        """Draw version comparison section showing changes from previous version"""
        from ..utils.version_comparison import (
            collect_scene_stats,
            get_version_stats,
            compare_versions
        )

        # Get current scene stats
        current_stats = collect_scene_stats(context)

        # Get previous version stats
        previous_stats = get_version_stats(self.source_uuid)

        if not previous_stats:
            return

        # Compare versions
        diff = compare_versions(current_stats, previous_stats)

        if not diff:
            return

        # Draw comparison box
        comp_box = layout.box()
        comp_box.label(text="Changes from Previous:", icon='ZOOM_ALL')

        # Polygon changes
        if 'polygon_count' in diff:
            poly = diff['polygon_count']
            row = comp_box.row()
            row.label(text="Polygons:")

            sub = row.row()
            sub.alignment = 'RIGHT'
            sub.label(text=f"{poly['previous']:,}")
            sub.label(text="->")
            sub.label(text=f"{poly['current']:,}")

            if poly['change_type'] == 'added':
                sub.label(text=poly['diff_text'], icon='ADD')
            elif poly['change_type'] == 'removed':
                sub.alert = True
                sub.label(text=poly['diff_text'], icon='REMOVE')

        # Material changes
        if 'material_count' in diff:
            mat = diff['material_count']
            row = comp_box.row()
            row.label(text="Materials:")

            sub = row.row()
            sub.alignment = 'RIGHT'
            sub.label(text=str(mat['previous']))
            sub.label(text="->")
            sub.label(text=str(mat['current']))

            if mat['change_type'] == 'added':
                sub.label(text=mat['diff_text'], icon='ADD')
            elif mat['change_type'] == 'removed':
                sub.alert = True
                sub.label(text=mat['diff_text'], icon='REMOVE')

        # Skeleton changes
        if 'has_armature' in diff:
            skel = diff['has_armature']
            row = comp_box.row()
            if skel['change_type'] == 'added':
                row.label(text="Skeleton: Added", icon='ARMATURE_DATA')
            elif skel['change_type'] == 'removed':
                row.alert = True
                row.label(text="Skeleton: Removed", icon='ARMATURE_DATA')

        # Animation changes
        if 'has_animations' in diff:
            anim = diff['has_animations']
            row = comp_box.row()
            if anim['change_type'] == 'added':
                row.label(text="Animations: Added", icon='ACTION')
            elif anim['change_type'] == 'removed':
                row.alert = True
                row.label(text="Animations: Removed", icon='ACTION')

    def _export_usd(self, context, filepath: str) -> bool:
        """Export to USD using Blender's built-in operator"""
        try:
            # Store selection
            original_selection = context.selected_objects.copy()
            original_active = context.active_object

            # Build export settings
            export_kwargs = {
                'filepath': filepath,
                'selected_objects_only': self.export_selected_only,
                'export_materials': self.include_materials,
                'generate_preview_surface': self.include_materials,
                'export_textures': self.include_materials,
            }

            # Add animation settings if available
            if hasattr(bpy.ops.wm, 'usd_export'):
                if self.include_animations:
                    export_kwargs['export_animation'] = True

            # Execute export
            result = bpy.ops.wm.usd_export(**export_kwargs)

            return result == {'FINISHED'}

        except Exception:
            return False

    def _save_blend_backup(self, context, filepath: str):
        """Save .blend backup of selected objects only"""
        try:
            # Collect all data blocks needed for selected objects
            data_blocks = set()

            for obj in context.selected_objects:
                # Add the object itself
                data_blocks.add(obj)

                # Add object data (mesh, armature, etc.)
                if obj.data:
                    data_blocks.add(obj.data)

                # Add materials
                if hasattr(obj, 'material_slots'):
                    for slot in obj.material_slots:
                        if slot.material:
                            data_blocks.add(slot.material)
                            # Add material node textures
                            if slot.material.use_nodes:
                                for node in slot.material.node_tree.nodes:
                                    if node.type == 'TEX_IMAGE' and node.image:
                                        data_blocks.add(node.image)

                # Add armature modifier targets
                for mod in obj.modifiers:
                    if mod.type == 'ARMATURE' and mod.object:
                        data_blocks.add(mod.object)
                        if mod.object.data:
                            data_blocks.add(mod.object.data)

                # Add parent hierarchy
                parent = obj.parent
                while parent:
                    data_blocks.add(parent)
                    if parent.data:
                        data_blocks.add(parent.data)
                    parent = parent.parent

                # Add children
                for child in obj.children_recursive:
                    data_blocks.add(child)
                    if child.data:
                        data_blocks.add(child.data)

                # Add bone custom shape (widget) objects for armatures
                if obj.type == 'ARMATURE' and obj.pose:
                    for pose_bone in obj.pose.bones:
                        if pose_bone.custom_shape is not None:
                            widget = pose_bone.custom_shape
                            data_blocks.add(widget)
                            if widget.data:
                                data_blocks.add(widget.data)

            # Save user-created collections that contain any exported object.
            # Required for rigs (bone widgets need their collection to link
            # correctly); optional for meshes via the `preserve_collections`
            # checkbox so users can keep kitbash / multi-folder organization
            # intact for INSTANCE-mode re-imports.
            has_armature = any(
                isinstance(b, bpy.types.Object) and b.type == 'ARMATURE'
                for b in data_blocks
            )
            preserve_collections = bool(getattr(self, 'preserve_collections', False))
            if has_armature or preserve_collections:
                exported_objects = {b for b in data_blocks if isinstance(b, bpy.types.Object)}
                for col in bpy.data.collections:
                    for obj in col.objects:
                        if obj in exported_objects:
                            data_blocks.add(col)
                            break

            # Rig-specific: explicitly include the actions the user ticked in
            # the rig picker. `bpy.data.libraries.write` is a SUBSET save — it
            # only follows references reachable from data_blocks. Actions the
            # user marked with fake_user but didn't currently attach via
            # active/NLA would otherwise be silently dropped.
            # Scoped to `has_armature` so mesh exports with preserve_collections
            # don't run rig-only logging.
            if has_armature:
                picked_names = self._selected_action_names()
                added = []
                missing = []
                for name in picked_names:
                    action = bpy.data.actions.get(name)
                    if action is not None:
                        data_blocks.add(action)
                        added.append(name)
                    else:
                        missing.append(name)
                logger.debug(
                    "_save_blend_backup: picker=%s, added_to_save=%s%s",
                    sorted(picked_names), sorted(added),
                    f", MISSING_FROM_BPY={sorted(missing)}" if missing else "",
                )
                if missing:
                    logger.warning(
                        "_save_blend_backup: picker references missing actions: %s",
                        sorted(missing),
                    )
                action_blocks = [
                    b for b in data_blocks if isinstance(b, bpy.types.Action)
                ]
                logger.debug(
                    "_save_blend_backup: total data_blocks=%d, actions=%s",
                    len(data_blocks), [a.name for a in action_blocks],
                )

            # Pack textures so the saved .blend is portable. Without this,
            # external image references break on other machines / library
            # installs. Restored in finally below — user's working file
            # state goes back to what it was before this call.
            export_objects_in_blocks = [
                b for b in data_blocks
                if isinstance(b, bpy.types.Object) and b.type == 'MESH'
            ]
            restore_packing = self._pack_textures_for_save(
                export_objects_in_blocks
            )

            try:
                # Write only selected data blocks to file
                bpy.data.libraries.write(
                    filepath,
                    data_blocks,
                    path_remap='RELATIVE_ALL',
                    compress=True
                )
                logger.debug("_save_blend_backup: wrote %s", filepath)
            finally:
                restore_packing()

        except Exception:
            # Surface the failure instead of swallowing — best-effort meant
            # "don't abort the whole export" not "hide bugs from us".
            logger.exception("_save_blend_backup FAILED for %s", filepath)

    # Max dimension for textures embedded in the preview .glb. Anything larger
    # is downscaled in a temporary copy before export and restored after.
    _PREVIEW_TEXTURE_CAP = 1024

    def _export_gltf_preview(self, context, filepath: str):
        """Export lightweight glTF preview for the in-app 3D viewport.

        Exports selected objects as a .glb file with:
        - Meshes with normals + UVs
        - Basic materials (PBR baseColor only, used by the in-app viewer)
        - No animations
        - For rig assets: bound meshes only, baked at rest pose. Armatures
          themselves are not exported (the viewer doesn't render joints).
        - Textures over _PREVIEW_TEXTURE_CAP² are temporarily downscaled.
        """
        from pathlib import Path

        # Store state we may need to restore
        original_selection = list(context.selected_objects)
        original_active = context.view_layer.objects.active

        if not original_selection:
            logger.debug("glTF preview: no objects selected, skipping")
            return

        # Build the export-time selection. Rigs ship as armature + bound meshes
        # with skinning + animations. Other types just ship the user's selection.
        is_rig = (self.asset_type == 'rig')
        hidden_to_restore = []                # objects whose hide state we changed
        restore_textures = lambda: None       # filled in before gltf export
        rig_armature = None                   # primary armature for the action filter
        rig_action_names = set()              # discovered actions for the rig

        try:
            if is_rig:
                bound_meshes = self._collect_rig_export_meshes(original_selection)
                if not bound_meshes:
                    logger.info("glTF preview: rig has no bound meshes, skipping .glb")
                    return

                armatures = [obj for obj in original_selection if obj.type == 'ARMATURE']
                if not armatures:
                    logger.info("glTF preview: rig has no armature, skipping .glb")
                    return
                rig_armature = armatures[0]

                # Use the explicit set the user picked in the rig dialog.
                # Single source of truth — same set drives .blend preservation.
                rig_action_names = self._selected_action_names()
                logger.debug(
                    "glTF preview: rig actions picked: %s",
                    sorted(rig_action_names) or '<none>',
                )

                # Export selection = armatures + bound meshes.
                # Armature(s) carry the skinning info that glTF needs.
                export_objects = list(armatures) + bound_meshes
                for obj in original_selection:
                    obj.select_set(False)
                for obj in export_objects:
                    if obj.hide_get():
                        obj.hide_set(False)
                        hidden_to_restore.append(obj)
                    obj.select_set(True)
                context.view_layer.objects.active = rig_armature
            else:
                export_objects = original_selection
                for obj in export_objects:
                    if obj.hide_get():
                        obj.hide_set(False)
                        hidden_to_restore.append(obj)

            logger.debug("glTF preview: exporting %d objects to %s", len(export_objects), filepath)

            # Swap any oversized textures for downscaled copies. Returns a
            # restore callable so the user's source materials revert in finally.
            restore_textures = self._downscale_textures_for_export(
                export_objects, self._PREVIEW_TEXTURE_CAP
            )

            # Standard glTF uses Y-up; the in-app viewer converts to Z-up on load.
            # WEBP textures (quality 75) typically shrink the .glb by 5-15x vs the
            # default 'AUTO' format, which preserves source PNGs. Qt 5.13+ decodes
            # WEBP natively via QImage, so no loader change is needed.
            # Draco compression bakes mesh data via KHR_draco_mesh_compression;
            # the in-app viewer decodes this via the DracoPy module on load.
            gltf_kwargs = dict(
                filepath=filepath,
                use_selection=True,
                export_format='GLB',
                export_texcoords=True,
                export_normals=True,
                export_materials='EXPORT',
                export_image_format='WEBP',
                export_image_quality=75,
                export_draco_mesh_compression_enable=True,
                export_draco_mesh_compression_level=6,
                export_draco_position_quantization=14,
                export_draco_normal_quantization=10,
                export_draco_texcoord_quantization=12,
                export_draco_color_quantization=10,
                export_draco_generic_quantization=12,
                export_cameras=False,
                export_lights=False,
            )
            if is_rig:
                # Rigs: keep skinning, export deform-only skeleton + animations.
                # `export_anim_single_armature=True` makes Blender's ACTIONS
                # mode iterate every armature-targeting Action in bpy.data.actions
                # (not just active + NLA) — that's what offers "loose" actions
                # to our gather_actions_hook. The filter (Phase 6.2) then trims
                # the offered list to ONLY what the user picked, so the dump
                # is constrained and there's no cross-rig leakage.
                gltf_kwargs.update(
                    export_animations=True,
                    export_animation_mode='ACTIONS',
                    export_def_bones=True,         # only deform bones in the skeleton
                    export_skins=True,
                    export_apply=False,            # don't bake — would destroy skinning
                    export_anim_single_armature=True,
                )
                with gltf_action_filter_session(rig_armature, rig_action_names):
                    with _silence_native_stdout():
                        result = bpy.ops.export_scene.gltf(**gltf_kwargs)
            else:
                # Static meshes / collections: bake modifiers, no animation.
                gltf_kwargs.update(
                    export_animations=False,
                    export_apply=True,             # apply modifiers
                )
                with _silence_native_stdout():
                    result = bpy.ops.export_scene.gltf(**gltf_kwargs)

            logger.debug("glTF preview: export result = %s", result)

            if Path(filepath).exists():
                size = Path(filepath).stat().st_size
                logger.debug("glTF preview: wrote %d bytes to %s", size, filepath)
            else:
                logger.warning("glTF preview: file not created at %s", filepath)

        except Exception:
            logger.exception("glTF preview export failed")
        finally:
            # Revert any texture swaps + delete temp downscaled copies.
            try:
                restore_textures()
            except Exception:
                logger.exception("glTF preview: texture restore failed")

            # Restore visibility of objects we un-hid
            for obj in hidden_to_restore:
                try:
                    obj.hide_set(True)
                except Exception:
                    pass

            # Restore selection
            try:
                for obj in bpy.context.selected_objects:
                    obj.select_set(False)
                for obj in original_selection:
                    if obj:
                        obj.select_set(True)
                if original_active:
                    context.view_layer.objects.active = original_active
            except Exception:
                pass

    def _downscale_textures_for_export(self, export_objects, cap: int):
        """Swap oversized textures on the selected objects' materials for
        downscaled copies, then return a callable that reverts every change
        and removes the temp copies. Safe to call on any selection — if no
        texture exceeds `cap`, the returned restore is a no-op.

        We touch only `ShaderNodeTexImage` nodes (including those inside node
        groups). Multiple nodes that point at the same source image share a
        single downscaled copy.
        """
        swap_nodes = self._collect_image_nodes(export_objects)

        # original Image -> downscaled-copy Image (so we make one copy per src)
        copies: dict = {}
        # (node, original_image) — list of swaps to revert
        swaps: list = []

        for node in swap_nodes:
            original = node.image
            if original is None:
                continue
            sw, sh = original.size
            if sw <= 0 or sh <= 0:
                # Unloaded / placeholder image — skip
                continue
            if sw <= cap and sh <= cap:
                continue

            copy = copies.get(original.name)
            if copy is None:
                # Preserve aspect ratio
                if sw >= sh:
                    nw, nh = cap, max(1, int(sh * cap / sw))
                else:
                    nw, nh = max(1, int(sw * cap / sh)), cap
                try:
                    copy = original.copy()
                    copy.name = f"_UL_PREVIEW_{original.name}"
                    copy.scale(nw, nh)
                    copies[original.name] = copy
                    logger.debug(
                        "glTF preview: downscaled '%s' %dx%d -> %dx%d",
                        original.name, sw, sh, nw, nh,
                    )
                except Exception:
                    logger.exception(
                        "glTF preview: downscale failed for '%s'", original.name,
                    )
                    continue

            swaps.append((node, original))
            node.image = copy

        def _restore():
            # Revert node pointers first
            for node, original in swaps:
                try:
                    node.image = original
                except Exception:
                    pass
            # Then remove the temp copies
            for copy in copies.values():
                try:
                    bpy.data.images.remove(copy)
                except Exception:
                    pass

        return _restore

    def _pack_textures_for_save(self, export_objects):
        """Pack every external image referenced by the export objects'
        materials so the saved `.blend` carries the texture bytes — making
        the asset portable to other machines / library installs.

        Returns a restore callable that unpacks the images we packed (via
        method='REMOVE' — drops the packed bytes, keeps the filepath
        reference, so the user's working file goes back to external refs).

        Skips:
        - Already-packed images (leave them as the user configured)
        - Library-linked images (read-only, can't modify)
        - Images without a source (no bytes to pack)
        """
        nodes = self._collect_image_nodes(export_objects)

        # Dedupe — same image may appear in multiple nodes/materials.
        images_seen = set()
        packed_by_us = []  # images we packed, for restore

        for node in nodes:
            img = node.image
            if img is None or img.name in images_seen:
                continue
            images_seen.add(img.name)

            # Already packed → leave alone (user's intent).
            if img.packed_file is not None:
                continue
            # Library-linked → can't modify.
            if getattr(img, 'library', None) is not None:
                logger.debug("_save_blend_backup: skipping linked image '%s'", img.name)
                continue
            # No filepath and not generated → nothing to pack.
            if not img.filepath and img.source != 'GENERATED':
                logger.debug("_save_blend_backup: '%s' has no source, skipping pack", img.name)
                continue

            try:
                img.pack()
                packed_by_us.append(img)
                logger.debug(
                    "_save_blend_backup: packed '%s' (%dx%d)",
                    img.name, img.size[0], img.size[1],
                )
            except Exception:
                logger.exception("_save_blend_backup: failed to pack '%s'", img.name)

        def _restore():
            for img in packed_by_us:
                try:
                    # method='REMOVE' drops the packed_file but keeps the
                    # image's filepath reference — user's working file
                    # goes back to external references.
                    img.unpack(method='REMOVE')
                except Exception:
                    logger.exception("_save_blend_backup: failed to unpack '%s'", img.name)

        return _restore

    def _collect_image_nodes(self, export_objects):
        """Yield every `ShaderNodeTexImage` reachable from the export objects'
        materials, recursing into node groups."""
        out = []
        seen_trees = set()  # node_tree names already walked
        seen_materials = set()

        def _walk(tree):
            if tree is None:
                return
            key = tree.name_full if hasattr(tree, 'name_full') else tree.name
            if key in seen_trees:
                return
            seen_trees.add(key)
            for node in tree.nodes:
                if node.bl_idname == 'ShaderNodeTexImage':
                    if getattr(node, 'image', None):
                        out.append(node)
                elif node.type == 'GROUP' and getattr(node, 'node_tree', None):
                    _walk(node.node_tree)

        for obj in export_objects:
            if obj.type != 'MESH':
                continue
            for slot in obj.material_slots:
                mat = slot.material
                if not mat or mat.name in seen_materials:
                    continue
                seen_materials.add(mat.name)
                if not getattr(mat, 'use_nodes', False):
                    continue
                _walk(mat.node_tree)
        return out

    def _collect_rig_export_meshes(self, selection):
        """Return the mesh objects that belong to the rig in `selection`.

        A mesh is considered "bound" to the rig if any of these holds:
        - It has an Armature modifier targeting one of the selected armatures.
        - It is parented to one of the selected armatures.
        - It is already in the selection alongside the armature.
        """
        armatures = [obj for obj in selection if obj.type == 'ARMATURE']
        if not armatures:
            return []

        arm_set = set(armatures)
        out = []
        seen = set()

        def _add(obj):
            if obj is None or obj.name in seen:
                return
            if obj.type != 'MESH':
                return
            seen.add(obj.name)
            out.append(obj)

        # Meshes already in the user's selection
        for obj in selection:
            if obj.type == 'MESH':
                _add(obj)

        # Walk the scene for meshes bound to any of our armatures
        try:
            scene_objects = list(bpy.context.view_layer.objects)
        except Exception:
            scene_objects = []

        for obj in scene_objects:
            if obj.type != 'MESH':
                continue
            # Direct parent armature
            if obj.parent in arm_set:
                _add(obj)
                continue
            # Armature modifier targeting our armature
            for mod in getattr(obj, 'modifiers', []):
                if getattr(mod, 'type', None) == 'ARMATURE':
                    if getattr(mod, 'object', None) in arm_set:
                        _add(obj)
                        break

        return out

    def _populate_action_picker(self, context):
        """Fill the action_picker collection. Pre-checks any action currently
        attached to the selected armature (active + NLA strips on it)."""
        self.action_picker.clear()

        # Find which actions are already attached to the rig's armature, if any
        attached_names = set()
        for obj in context.selected_objects:
            if obj.type != 'ARMATURE':
                continue
            anim = obj.animation_data
            if anim is None:
                continue
            if anim.action is not None:
                attached_names.add(anim.action.name)
            for track in anim.nla_tracks:
                for strip in track.strips:
                    if strip.action is not None:
                        attached_names.add(strip.action.name)

        # List every OBJECT-rooted action in the .blend. Sorted alphabetically
        # so the user gets a stable, scannable list.
        for action in sorted(bpy.data.actions, key=lambda a: a.name.lower()):
            id_root = getattr(action, 'id_root', None)
            if id_root not in (None, 'OBJECT'):
                continue
            item = self.action_picker.add()
            item.action_name = action.name
            item.attached = action.name in attached_names
            item.include = item.attached  # default: ship the attached ones

    def _selected_action_names(self) -> set:
        """Return the set of action names the user ticked in the picker."""
        return {item.action_name for item in self.action_picker if item.include}

    def _generate_thumbnail(self, context, filepath: str):
        """Generate thumbnail using shared viewport capture utility."""
        objects = list(context.selected_objects)
        if not objects:
            create_placeholder_thumbnail(filepath)
            return

        capture_viewport_thumbnail(context, objects, filepath, size=256, asset_type=self.asset_type)

    def _collect_metadata(self, context) -> dict:
        """Collect metadata from selected objects using the metadata collector"""
        objects = list(context.selected_objects if self.export_selected_only else context.scene.objects)

        # Use the centralized metadata collector for extended metadata
        metadata = collect_all_metadata(objects, self.asset_type)

        # Add object count (not part of type-specific collection)
        metadata['object_count'] = len(objects)

        return metadata


class UAL_OT_export_material(Operator):
    """Export material only with sphere preview"""
    bl_idname = "ual.export_material"
    bl_label = "Export Material to Library"
    bl_description = "Export a material to the asset library with sphere preview"
    bl_options = {'REGISTER', 'UNDO'}

    # Material selection - populated dynamically
    material_name: EnumProperty(
        name="Material",
        description="Select material to export",
        items=lambda self, context: UAL_OT_export_material._get_material_items(context)
    )

    description: StringProperty(
        name="Description",
        description="Optional description for the material",
        default=""
    )

    # Versioning properties
    export_mode: EnumProperty(
        name="Export Mode",
        description="Export as new asset or new version of existing",
        items=[
            ('NEW_ASSET', "New Asset", "Create a brand new material asset"),
            ('NEW_VERSION', "New Version", "Create new version of existing material"),
        ],
        default='NEW_ASSET'
    )

    # Hidden properties for version tracking
    source_uuid: StringProperty(default="")
    source_version_group_id: StringProperty(default="")
    source_version: bpy.props.IntProperty(default=0)
    source_asset_name: StringProperty(default="")
    has_ual_metadata: BoolProperty(default=False)
    source_asset_id: StringProperty(default="")
    source_variant_name: StringProperty(default="Base")

    # USD export temporarily disabled - Blender-centric workflow
    # export_usd: BoolProperty(
    #     name="Export USD",
    #     description="Also export USD file for interchange with other DCC apps",
    #     default=False
    # )

    @staticmethod
    def _get_material_items(context):
        """Get list of materials for enum property"""
        items = []

        # First add materials from active object
        if context.active_object and hasattr(context.active_object, 'material_slots'):
            for slot in context.active_object.material_slots:
                if slot.material and slot.material.name not in [i[0] for i in items]:
                    items.append((slot.material.name, slot.material.name, f"Material from {context.active_object.name}"))

        # Then add all other materials in the scene
        for mat in bpy.data.materials:
            if mat.name not in [i[0] for i in items] and not mat.name.startswith('_'):
                items.append((mat.name, mat.name, "Scene material"))

        if not items:
            items.append(('NONE', "No Materials", "No materials found"))

        return items

    @classmethod
    def poll(cls, context):
        """Check if any materials exist"""
        return len(bpy.data.materials) > 0

    def invoke(self, context, event):
        """Show dialog before export"""
        # Set default to active object's material if available
        if context.active_object and hasattr(context.active_object, 'material_slots'):
            if context.active_object.material_slots:
                first_mat = context.active_object.material_slots[0].material
                if first_mat:
                    self.material_name = first_mat.name

        # Check if selected material has UAL metadata for versioning
        if self.material_name and self.material_name != 'NONE':
            mat = bpy.data.materials.get(self.material_name)
            if mat:
                self._check_material_metadata(mat)

        return context.window_manager.invoke_props_dialog(self, width=400)

    def _check_material_metadata(self, material):
        """Check if material has UAL metadata from library import."""
        from ..utils.metadata_handler import read_material_metadata

        metadata = read_material_metadata(material)
        if metadata:
            self.has_ual_metadata = True
            self.source_uuid = metadata.get('uuid', '')
            self.source_version_group_id = metadata.get('version_group_id', '')
            self.source_version = metadata.get('version', 0)
            self.source_asset_name = metadata.get('asset_name', '')
            self.source_asset_id = metadata.get('asset_id', '')
            self.source_variant_name = metadata.get('variant_name', 'Base')
            self.export_mode = 'NEW_VERSION'
        else:
            self.has_ual_metadata = False
            self.source_uuid = ""
            self.source_version_group_id = ""
            self.source_version = 0
            self.source_asset_name = ""
            self.source_asset_id = ""
            self.source_variant_name = "Base"
            self.export_mode = 'NEW_ASSET'

    def draw(self, context):
        """Draw dialog UI"""
        layout = self.layout

        layout.prop(self, "material_name")

        # Re-check metadata when material selection changes
        if self.material_name and self.material_name != 'NONE':
            mat = bpy.data.materials.get(self.material_name)
            if mat:
                self._check_material_metadata(mat)

        # Versioning section (if material has UAL metadata)
        if self.has_ual_metadata:
            version_box = layout.box()
            version_box.label(text="Versioning:", icon='FILE_REFRESH')

            info_row = version_box.row()
            info_row.label(text=f"Source: {self.source_asset_name} (v{self.source_version:03d})")

            version_box.prop(self, "export_mode", expand=True)

            if self.export_mode == 'NEW_VERSION':
                next_version = self.source_version + 1
                version_box.label(text=f"Will create: v{next_version:03d}", icon='INFO')

            layout.separator()

        layout.prop(self, "description")

        # USD export temporarily disabled - Blender-centric workflow
        # layout.separator()
        # layout.prop(self, "export_usd")

        # Show material preview info
        if self.material_name and self.material_name != 'NONE':
            mat = bpy.data.materials.get(self.material_name)
            if mat:
                box = layout.box()
                box.label(text="Preview:", icon='MATERIAL')
                box.label(text="A sphere preview will be generated")

    def _material_attribution_defaults(self) -> dict:
        """M6: pull attribution defaults from addon prefs. Material export
        doesn't surface these in its dialog (the dialog is busy with
        material-specific bits), so we silently apply the defaults.
        Source of truth: Preferences → Universal Library → Attribution
        Defaults.
        """
        try:
            prefs = get_preferences()
            if prefs is None:
                return {'author': '', 'license': None, 'copyright': None}
            return {
                'author': prefs.default_author or '',
                'license': prefs._resolved_license() or None,
                'copyright': prefs.default_copyright or None,
            }
        except Exception:
            return {'author': '', 'license': None, 'copyright': None}

    def execute(self, context):
        """Execute the material export"""
        if not self.material_name or self.material_name == 'NONE':
            self.report({'ERROR'}, "No material selected")
            return {'CANCELLED'}

        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'ERROR'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}

        # Generate asset name with auto-naming
        prefs = get_preferences()
        use_auto_naming = prefs.use_auto_naming if prefs else True

        if use_auto_naming:
            set_custom_prefixes(get_naming_prefixes())
            namer = get_asset_namer()
            asset_name = namer.generate_name(material.name, 'material', use_prefix=True)
        else:
            asset_name = material.name

        # Get library connection
        library = get_library_connection()

        # Determine if this is a new version or new asset
        is_new_version = (
            self.export_mode == 'NEW_VERSION' and
            self.has_ual_metadata and
            self.source_version_group_id
        )
        # Material variants not yet supported
        is_new_variant = False

        # Generate UUID for this version (always new)
        asset_uuid = str(uuid.uuid4())

        # Set versioning info based on mode
        if is_new_version:
            version_group_id = self.source_version_group_id
            version = self.source_version + 1
            version_label = f"v{version:03d}"
            asset_id = self.source_asset_id or version_group_id
            variant_name = self.source_variant_name or "Base"
            # Use original asset name for consistency
            asset_name = self.source_asset_name or asset_name
        else:
            version_group_id = asset_uuid
            version = 1
            version_label = "v001"
            asset_id = asset_uuid
            variant_name = "Base"

        # Get folder using library structure
        library_folder = library.get_library_folder_path(asset_id, asset_name, variant_name, 'material')
        archive_folder = library.get_archive_folder_path(asset_id, asset_name, variant_name, version_label, 'material')

        try:
            import shutil

            # If new version, archive the PREVIOUS version first
            if is_new_version and self.source_uuid:
                previous_version_label = f"v{self.source_version:03d}"
                prev_archive_folder = library.get_archive_folder_path(
                    asset_id, asset_name, variant_name, previous_version_label, 'material'
                )
                # Move current library files to archive (previous version)
                # Skip representation files — they belong to the library folder.
                skip_suffixes = ('.current.blend', '.proxy.blend', '.render.blend')
                if library_folder.exists():
                    for file in library_folder.iterdir():
                        if file.is_file() and not any(file.name.endswith(s) for s in skip_suffixes):
                            shutil.move(str(file), str(prev_archive_folder / file.name))

            # Primary format: .blend file (always saved to both library and archive)
            # Include version in filename to prevent Blender from merging libraries
            blend_filename = f"{asset_name}.{version_label}.blend"
            library_blend_path = library_folder / blend_filename
            self._save_material_blend(material, str(library_blend_path))

            if not library_blend_path.exists():
                self.report({'ERROR'}, "Failed to save .blend file")
                return {'CANCELLED'}

            # Create .current.blend for representation swap support
            from ..utils.current_reference_helper import create_current_reference
            create_current_reference(library_blend_path)

            # Copy to archive
            archive_blend_path = archive_folder / blend_filename
            shutil.copy2(str(library_blend_path), str(archive_blend_path))

            blend_path = library_blend_path

            # USD export temporarily disabled - Blender-centric workflow
            usd_path = None

            # Generate sphere preview thumbnail (versioned)
            thumbnail_filename = f"thumbnail.{version_label}.png"
            thumbnail_versioned = library_folder / thumbnail_filename
            self._generate_material_thumbnail(context, material, str(thumbnail_versioned))

            # Create thumbnail.current.png (stable path for cache watching)
            thumbnail_current = library_folder / "thumbnail.current.png"
            if thumbnail_versioned.exists():
                shutil.copy2(str(thumbnail_versioned), str(thumbnail_current))
            thumbnail_path = thumbnail_current  # DB stores .current for latest

            # Copy versioned thumbnail to archive
            if thumbnail_versioned.exists():
                shutil.copy2(str(thumbnail_versioned), str(archive_folder / thumbnail_filename))

            # Collect material-specific metadata
            mat_metadata = collect_material_metadata([material])

            # Generate JSON sidecar metadata file for material (versioned to match blend)
            json_filename = f"{asset_name}.{version_label}.json"
            json_path = library_folder / json_filename
            json_metadata = generate_asset_json_metadata(
                asset_uuid=asset_uuid,
                name=asset_name,
                asset_type='material',
                variant_name=variant_name,
                asset_id=asset_id,
                version=version,
                version_label=version_label,
                version_group_id=version_group_id,
                is_latest=True,
                representation_type='none',
                description=self.description,
                author='',
                tags=[],
                extended_metadata=mat_metadata
            )
            write_json_metadata(json_path, json_metadata)

            # Copy JSON to archive
            if json_path.exists():
                shutil.copy2(str(json_path), str(archive_folder / json_filename))

            # Serialize texture_maps list to JSON if present
            texture_maps = mat_metadata.get('texture_maps')
            if texture_maps and isinstance(texture_maps, list):
                texture_maps = json.dumps(texture_maps)

            # If new version, update previous version in database first
            if is_new_version and self.source_uuid:
                previous_version_label = f"v{self.source_version:03d}"
                prev_archive_folder = library.get_archive_folder_path(
                    asset_id, asset_name, variant_name, previous_version_label, 'material'
                )
                # Use versioned filename for archived version
                prev_blend_filename = f"{asset_name}.{previous_version_label}.blend"
                prev_thumbnail_filename = f"thumbnail.{previous_version_label}.png"
                library.update_asset(self.source_uuid, {
                    'is_latest': 0,
                    'is_cold': 1,
                    'is_immutable': 1,
                    'cold_storage_path': str(prev_archive_folder),
                    'blend_backup_path': str(prev_archive_folder / prev_blend_filename),
                    'thumbnail_path': str(prev_archive_folder / prev_thumbnail_filename),
                })

            # Add to library database
            # Primary format is .blend, USD is optional for interchange
            asset_data = {
                'uuid': asset_uuid,
                'name': asset_name,
                'description': self.description,
                'folder_id': 1,  # Root folder
                'asset_type': 'material',
                'representation_type': 'none',
                'usd_file_path': str(usd_path) if usd_path and usd_path.exists() else None,
                'blend_backup_path': str(blend_path),  # Primary file
                'thumbnail_path': str(thumbnail_path) if thumbnail_path.exists() else None,
                'file_size_mb': blend_path.stat().st_size / (1024 * 1024) if blend_path.exists() else 0,
                'has_materials': 1,
                'has_skeleton': 0,
                'has_animations': 0,
                'polygon_count': 0,
                'material_count': mat_metadata.get('material_count', 1),
                'tags': [],
                # M6: Attribution. Material export doesn't show a dialog
                # for these so we silently pull from the AppData defaults —
                # user can still edit in the metadata panel post-export.
                **self._material_attribution_defaults(),
                'source_application': f'Blender {bpy.app.version_string}',
                # Versioning fields
                'version': version,
                'version_label': version_label,
                'version_group_id': version_group_id,
                'is_latest': 1,
                'parent_version_uuid': self.source_uuid if is_new_version else None,
                'variant_source_uuid': self.source_uuid if is_new_variant else None,
                # Variant system fields
                'asset_id': asset_id,
                'variant_name': variant_name,
                # Material-specific metadata
                'texture_maps': texture_maps,
                'texture_resolution': mat_metadata.get('texture_resolution'),
            }

            library.add_asset(asset_data)

            # Copy folder memberships and tags from source version to new version
            if is_new_version and self.source_uuid:
                library.copy_folders_to_asset(self.source_uuid, asset_uuid)
                library.copy_tags_to_asset(self.source_uuid, asset_uuid)

            # Store metadata back on material for future versioning
            from ..utils.metadata_handler import store_material_metadata
            store_material_metadata(material, {
                'uuid': asset_uuid,
                'version_group_id': version_group_id,
                'version': version,
                'version_label': version_label,
                'name': asset_name,
                'asset_id': asset_id,
                'variant_name': variant_name,
            })

            if is_new_version:
                self.report({'INFO'}, f"Exported material '{asset_name}' as {version_label}")
            else:
                self.report({'INFO'}, f"Exported material '{asset_name}' to library")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            import traceback
            traceback.print_exc()
            # Cleanup on failure
            try:
                if library_folder.exists():
                    shutil.rmtree(library_folder, ignore_errors=True)
                if archive_folder.exists():
                    shutil.rmtree(archive_folder, ignore_errors=True)
            except Exception:
                pass
            return {'CANCELLED'}

    def _export_material_usd(self, context, material, filepath: str) -> bool:
        """Export material on a small sphere to USD"""
        try:
            # Store original state
            original_selection = [obj for obj in context.selected_objects]
            original_active = context.active_object

            # Create temporary sphere with material
            bpy.ops.mesh.primitive_uv_sphere_add(
                segments=16, ring_count=8, radius=0.5, location=(0, 0, 0)
            )
            temp_sphere = context.active_object
            temp_sphere.name = "_UAL_MaterialSphere"

            # Assign material
            temp_sphere.data.materials.append(material)

            # Select only the sphere
            bpy.ops.object.select_all(action='DESELECT')
            temp_sphere.select_set(True)
            context.view_layer.objects.active = temp_sphere

            # Export USD
            result = bpy.ops.wm.usd_export(
                filepath=filepath,
                selected_objects_only=True,
                export_materials=True,
                generate_preview_surface=True,
                export_textures=True
            )

            # Cleanup: delete temp sphere
            bpy.data.objects.remove(temp_sphere, do_unlink=True)

            # Restore selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj and obj.name in bpy.data.objects:
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                context.view_layer.objects.active = original_active

            return result == {'FINISHED'}

        except Exception:
            return False

    def _save_material_blend(self, material, filepath: str):
        """Save .blend backup with just the material"""
        try:
            data_blocks = {material}

            # Add material node textures
            if material.use_nodes:
                for node in material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        data_blocks.add(node.image)

            bpy.data.libraries.write(
                filepath,
                data_blocks,
                path_remap='RELATIVE_ALL',
                compress=True
            )

        except Exception:
            pass  # Best-effort

    def _generate_material_thumbnail(self, context, material, filepath: str) -> bool:
        """Generate material preview using fast viewport rendering with bundled preview scene.

        Opens preview scene, renders thumbnail, and KEEPS preview scene open.
        User stays in preview scene until they manually close it.
        """
        from .material_preview import (
            get_preview_blend_path,
            PREVIEW_COLLECTION_NAME,
            PREVIEW_BALL_NAME,
            PREVIEW_CAMERA_NAME,
            PREVIEW_SCENE_NAME,
            UAL_OT_open_material_preview,
        )

        try:
            # Only store original scene/state if NOT already in preview scene
            # This preserves the true original state across multiple exports
            current_scene = context.window.scene
            already_in_preview = current_scene.name.startswith(PREVIEW_SCENE_NAME)

            if not already_in_preview:
                # Store original scene for Close Preview to return to
                UAL_OT_open_material_preview._original_scene_name = current_scene.name

                # Store viewport state for Close Preview to restore
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        for space in area.spaces:
                            if space.type == 'VIEW_3D':
                                UAL_OT_open_material_preview._original_view_perspective = space.region_3d.view_perspective
                                UAL_OT_open_material_preview._original_shading_type = space.shading.type
                                UAL_OT_open_material_preview._original_show_overlays = space.overlay.show_overlays
                                break
                        break

            # Get preview blend path
            preview_blend = get_preview_blend_path()
            if not preview_blend.exists():
                return self._fallback_material_thumbnail(context, material, filepath)

            # Check if preview scene already exists, reuse it
            preview_scene = bpy.data.scenes.get(PREVIEW_SCENE_NAME)
            if not preview_scene:
                preview_scene = bpy.data.scenes.new(PREVIEW_SCENE_NAME)

                # Switch to preview scene BEFORE appending
                context.window.scene = preview_scene

                # Append the preview collection
                blend_path_str = str(preview_blend).replace('\\', '/')

                with bpy.data.libraries.load(blend_path_str, link=False) as (data_from, data_to):
                    available_collections = list(data_from.collections)

                collection_to_append = PREVIEW_COLLECTION_NAME
                if PREVIEW_COLLECTION_NAME not in available_collections:
                    if available_collections:
                        collection_to_append = available_collections[0]
                    else:
                        context.window.scene = original_scene
                        bpy.data.scenes.remove(preview_scene)
                        return self._fallback_material_thumbnail(context, material, filepath)

                directory = f"{blend_path_str}/Collection/"
                bpy.ops.wm.append(
                    directory=directory,
                    files=[{"name": collection_to_append}],
                    link=False,
                    autoselect=False,
                    active_collection=False,
                    instance_collections=False,
                )

                # Find and link appended collection
                appended_collection = bpy.data.collections.get(collection_to_append)
                if not appended_collection:
                    for col in bpy.data.collections:
                        if col.name.startswith(collection_to_append):
                            appended_collection = col
                            break

                if appended_collection and appended_collection.name not in preview_scene.collection.children:
                    preview_scene.collection.children.link(appended_collection)
            else:
                # Reuse existing preview scene
                context.window.scene = preview_scene

            # Find preview ball and camera
            ball = None
            camera = None
            for obj in preview_scene.objects:
                if obj.name.startswith(PREVIEW_BALL_NAME):
                    ball = obj
                if obj.name.startswith(PREVIEW_CAMERA_NAME):
                    camera = obj

            if not ball:
                return self._fallback_material_thumbnail(context, material, filepath)

            # Assign material to preview ball
            if ball.data.materials:
                ball.data.materials[0] = material
            else:
                ball.data.materials.append(material)

            # Set scene camera
            if camera:
                preview_scene.camera = camera

            # Configure render settings
            render = preview_scene.render
            render.resolution_x = 512
            render.resolution_y = 512
            render.resolution_percentage = 100

            original_format = render.image_settings.file_format
            original_color = render.image_settings.color_mode
            original_media_type = None
            if hasattr(render.image_settings, 'media_type'):
                original_media_type = render.image_settings.media_type
                render.image_settings.media_type = 'IMAGE'

            render.image_settings.file_format = 'PNG'
            render.image_settings.color_mode = 'RGBA'

            # Find viewport and setup for render
            success = False
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    view3d_area = area
                    view3d_region = None
                    view3d_space = None
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            view3d_region = region
                            break
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            view3d_space = space
                            break

                    if view3d_space and view3d_region:
                        # Set viewport to camera and material/rendered mode
                        if view3d_space.shading.type not in ('MATERIAL', 'RENDERED'):
                            view3d_space.shading.type = 'MATERIAL'
                        view3d_space.overlay.show_overlays = False

                        if view3d_space.region_3d.view_perspective != 'CAMERA':
                            with context.temp_override(area=view3d_area, region=view3d_region):
                                bpy.ops.view3d.view_camera()

                        # Render thumbnail
                        original_filepath = render.filepath
                        render.filepath = filepath
                        with context.temp_override(area=view3d_area, region=view3d_region):
                            bpy.ops.render.opengl(write_still=True)
                        render.filepath = original_filepath

                        if Path(filepath).exists():
                            success = True
                    break

            # Restore render settings (but NOT scene - user stays in preview)
            render.image_settings.file_format = original_format
            render.image_settings.color_mode = original_color
            if original_media_type is not None and hasattr(render.image_settings, 'media_type'):
                render.image_settings.media_type = original_media_type

            # NO CLEANUP - User stays in preview scene with everything intact
            # User will use "Close Material Preview" when done

            if not success:
                return self._fallback_material_thumbnail(context, material, filepath)

            return True

        except Exception:
            return self._fallback_material_thumbnail(context, material, filepath)

    def _fallback_material_thumbnail(self, context, material, filepath: str) -> bool:
        """Fallback to Blender's built-in preview system if fast method fails."""
        import time

        try:
            # Set preview type to sphere
            material.preview_render_type = 'SPHERE'
            material.asset_generate_preview()

            # Wait for async preview generation
            max_wait = 5.0
            wait_interval = 0.1
            elapsed = 0

            while elapsed < max_wait:
                preview = material.preview_ensure()
                if preview and preview.image_size[0] > 0 and preview.image_size[1] > 0:
                    pixels = preview.image_pixels_float[:]
                    if len(pixels) > 0 and any(p > 0 for p in pixels[:100]):
                        break
                time.sleep(wait_interval)
                elapsed += wait_interval

            # Get preview and save to file
            preview = material.preview
            if preview and preview.image_size[0] > 0 and preview.image_size[1] > 0:
                width, height = preview.image_size
                pixels = list(preview.image_pixels_float)

                if len(pixels) == width * height * 4:
                    img = bpy.data.images.new("_UAL_temp_preview", width, height, alpha=True)
                    img.pixels = pixels
                    img.filepath_raw = filepath
                    img.file_format = 'PNG'
                    img.save()
                    bpy.data.images.remove(img)

                    if Path(filepath).exists():
                        return True

            return False

        except Exception:
            return False


# Registration
# Order matters — UAL_ActionPickerItem must register BEFORE the operator that
# uses it as a CollectionProperty type.
classes = [
    UAL_ActionPickerItem,
    UAL_UL_action_picker,
    UAL_OT_export_to_library,
    UAL_OT_export_material,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = ['UAL_OT_export_to_library', 'UAL_OT_export_material', 'register', 'unregister']
