"""
Export to Library Operator

Exports selected objects to USD and adds them to the Universal Library.
"""

import bpy
import uuid
import json
import shutil
import os
from pathlib import Path
from datetime import datetime
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

from ..utils.library_connection import get_library_connection
from ..utils.material_converter import get_material_converter
from ..utils.naming_utils import get_asset_namer, set_custom_prefixes
from ..utils.metadata_collector import collect_all_metadata, collect_material_metadata
from ..utils.viewport_capture import capture_viewport_thumbnail, create_placeholder_thumbnail
from ..preferences import get_preferences, get_naming_prefixes


# JSON Metadata Schema Version
METADATA_SCHEMA_VERSION = 1


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

    new_variant_name: StringProperty(
        name="Variant Name",
        description="Name for the new variant (e.g., 'Destroyed', 'Red')",
        default=""
    )

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

        # Check for UAL metadata on selected objects (imported from library)
        self._check_ual_metadata(context)

        # Auto-detect type first (needed for naming)
        if context.selected_objects:
            self.asset_type = self._detect_asset_type(context.selected_objects)

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
                'author': '',
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

            # For rigs: also save collections (needed for custom shapes when linking)
            has_armature = any(
                isinstance(b, bpy.types.Object) and b.type == 'ARMATURE'
                for b in data_blocks
            )
            if has_armature:
                exported_objects = {b for b in data_blocks if isinstance(b, bpy.types.Object)}
                for col in bpy.data.collections:
                    for obj in col.objects:
                        if obj in exported_objects:
                            data_blocks.add(col)
                            break

            # Write only selected data blocks to file
            bpy.data.libraries.write(
                filepath,
                data_blocks,
                path_remap='RELATIVE_ALL',
                compress=True
            )

        except Exception:
            pass  # Blend backup is best-effort

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
                'author': '',
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

            # Copy folder memberships from source version to new version
            if is_new_version and self.source_uuid:
                library.copy_folders_to_asset(self.source_uuid, asset_uuid)

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
classes = [
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
