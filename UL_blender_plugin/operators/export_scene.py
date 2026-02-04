"""
Export Scene to Library Operator

Exports a Blender Scene to the Universal Library.
Saves the entire .blend file (copy=True), similar to collection export.
"""

import bpy
import uuid
import json
import shutil
from pathlib import Path
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

from ..utils.library_connection import get_library_connection
from ..utils.metadata_collector import collect_scene_metadata
from ..utils.naming_utils import get_asset_namer, set_custom_prefixes
from ..utils.viewport_capture import capture_scene_thumbnail, create_placeholder_thumbnail
from ..preferences import get_preferences, get_naming_prefixes
from .export_to_library import generate_asset_json_metadata, write_json_metadata


class UAL_OT_export_scene(Operator):
    """Export a scene to Universal Library"""
    bl_idname = "ual.export_scene"
    bl_label = "Export Scene to Library"
    bl_description = "Export a scene as a scene asset"
    bl_options = {'REGISTER', 'UNDO'}

    # Properties
    asset_name: StringProperty(
        name="Asset Name",
        description="Name for the scene asset in the library",
        default=""
    )

    description: StringProperty(
        name="Description",
        description="Optional description for the scene",
        default=""
    )

    scene_name: EnumProperty(
        name="Scene",
        description="Select scene to export",
        items=lambda self, context: UAL_OT_export_scene._get_scene_items(context)
    )

    # Versioning properties
    export_mode: EnumProperty(
        name="Export Mode",
        description="Export as new asset or new version of existing",
        items=[
            ('NEW_ASSET', "New Asset", "Create a brand new scene asset"),
            ('NEW_VERSION', "New Version", "Create new version of existing scene"),
        ],
        default='NEW_ASSET'
    )

    archive_previous: BoolProperty(
        name="Archive Previous Version",
        description="Move previous version to cold storage",
        default=True
    )

    # Hidden properties for version tracking
    source_uuid: StringProperty(default="")
    source_version_group_id: StringProperty(default="")
    source_version: bpy.props.IntProperty(default=0)
    source_asset_name: StringProperty(default="")
    has_ual_metadata: BoolProperty(default=False)
    source_asset_id: StringProperty(default="")
    source_variant_name: StringProperty(default="Base")

    @staticmethod
    def _get_scene_items(context):
        """Get list of scenes for enum property"""
        items = []
        for scene in bpy.data.scenes:
            items.append((scene.name, scene.name, f"Scene: {scene.name}"))
        if not items:
            items.append(('NONE', "No Scenes", "No scenes found"))
        return items

    @classmethod
    def poll(cls, context):
        """Always available when there are scenes"""
        return len(bpy.data.scenes) > 0

    def invoke(self, context, event):
        """Show dialog before export"""
        # Default to active scene
        self.scene_name = context.scene.name
        self.asset_name = context.scene.name

        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        """Draw dialog UI"""
        layout = self.layout

        layout.prop(self, "scene_name")

        # Show scene info
        scene = bpy.data.scenes.get(self.scene_name)
        if scene:
            box = layout.box()
            box.label(text=f"Scene: {scene.name}", icon='SCENE_DATA')

            obj_count = len(scene.objects)
            col_count = len(scene.collection.children)
            box.label(text=f"{obj_count} objects, {col_count} collections")
            box.label(text=f"Render: {scene.render.engine}")
            box.label(text=f"Resolution: {scene.render.resolution_x}x{scene.render.resolution_y}")

        layout.separator()

        # Versioning section
        if self.has_ual_metadata:
            version_box = layout.box()
            version_box.label(text="Versioning:", icon='FILE_REFRESH')

            info_row = version_box.row()
            info_row.label(text=f"Source: {self.source_asset_name} (v{self.source_version:03d})")

            version_box.prop(self, "export_mode", expand=True)

            if self.export_mode == 'NEW_VERSION':
                next_version = self.source_version + 1
                version_box.label(text=f"Will create: v{next_version:03d}", icon='INFO')
                version_box.prop(self, "archive_previous")

            layout.separator()

        layout.prop(self, "asset_name")
        layout.prop(self, "description")

    def execute(self, context):
        """Execute the scene export"""
        if not self.asset_name:
            self.report({'ERROR'}, "Asset name is required")
            return {'CANCELLED'}

        if not self.scene_name or self.scene_name == 'NONE':
            self.report({'ERROR'}, "No scene selected")
            return {'CANCELLED'}

        scene = bpy.data.scenes.get(self.scene_name)
        if not scene:
            self.report({'ERROR'}, f"Scene '{self.scene_name}' not found")
            return {'CANCELLED'}

        # Get library connection
        library = get_library_connection()

        # Determine if this is a new version or new asset
        is_new_version = (
            self.export_mode == 'NEW_VERSION' and
            self.has_ual_metadata and
            self.source_version_group_id
        )

        # Collision check: For new assets, check if name already exists within same type
        if not is_new_version:
            if library.asset_name_exists(self.asset_name, asset_type='scene'):
                self.report(
                    {'ERROR'},
                    f"A scene asset named '{self.asset_name}' already exists! "
                    "Please choose a different name, or use 'New Version' to add a version."
                )
                return {'CANCELLED'}

        # Retirement check: For new versions, verify source asset isn't retired
        if is_new_version and self.source_uuid:
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
            asset_id = self.source_asset_id or version_group_id
            variant_name = self.source_variant_name or "Base"
        else:
            version_group_id = asset_uuid
            version = 1
            version_label = "v001"
            asset_id = asset_uuid
            variant_name = "Base"

        # Get asset folder using library structure
        library_folder = library.get_library_folder_path(
            asset_id, self.asset_name, variant_name, 'scene'
        )

        try:
            # If new version, archive previous version's files BEFORE writing
            # new ones. Both versions share the same library_folder, so the
            # previous version's files must be moved out first.
            if is_new_version and self.source_uuid:
                previous_version_label = f"v{self.source_version:03d}"
                prev_archive_folder = library.get_archive_folder_path(
                    asset_id, self.asset_name, variant_name, previous_version_label, 'scene'
                )
                # Move all current library files to previous version's archive
                # Skip representation files — they belong to the library folder.
                skip_suffixes = ('.current.blend', '.proxy.blend', '.render.blend')
                if library_folder.exists():
                    for file in library_folder.iterdir():
                        if file.is_file() and not any(file.name.endswith(s) for s in skip_suffixes):
                            shutil.move(str(file), str(prev_archive_folder / file.name))

                # Use previous version label for archived paths
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

            # Export as .blend file (full scene, same pattern as collection export)
            # Include version in filename to prevent Blender from merging libraries
            blend_path = library_folder / f"{self.asset_name}.{version_label}.blend"
            self._save_scene_blend(context, scene, str(blend_path))

            if not blend_path.exists():
                self.report({'ERROR'}, "Failed to save .blend file")
                return {'CANCELLED'}

            # Create .current.blend for representation swap support
            from ..utils.current_reference_helper import create_current_reference
            create_current_reference(blend_path)

            # Generate thumbnail (versioned, viewport capture of scene objects)
            thumbnail_filename = f"thumbnail.{version_label}.png"
            thumbnail_versioned = library_folder / thumbnail_filename
            self._generate_thumbnail(context, scene, str(thumbnail_versioned))
            
            # Create thumbnail.current.png (stable path for cache watching)
            thumbnail_current = library_folder / "thumbnail.current.png"
            if thumbnail_versioned.exists():
                shutil.copy2(str(thumbnail_versioned), str(thumbnail_current))
            thumbnail_path = thumbnail_current  # DB stores .current for latest

            # Collect metadata
            metadata = collect_scene_metadata(scene)

            # Generate JSON sidecar metadata (versioned to match blend)
            json_filename = f"{self.asset_name}.{version_label}.json"
            json_path = library_folder / json_filename
            json_metadata = generate_asset_json_metadata(
                asset_uuid=asset_uuid,
                name=self.asset_name,
                asset_type='scene',
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
                extended_metadata=metadata
            )
            write_json_metadata(json_path, json_metadata)

            # Copy new version's files to its archive (versioned thumbnail, not .current)
            archive_folder = library.get_archive_folder_path(
                asset_id, self.asset_name, variant_name, version_label, 'scene'
            )
            for src_file in [blend_path, thumbnail_versioned, json_path]:
                if src_file.exists():
                    shutil.copy2(str(src_file), str(archive_folder / src_file.name))

            # Add to library database
            asset_data = {
                'uuid': asset_uuid,
                'name': self.asset_name,
                'description': self.description,
                'folder_id': 1,  # Root folder
                'asset_type': 'scene',
                'usd_file_path': None,
                'blend_backup_path': str(blend_path),
                'thumbnail_path': str(thumbnail_path) if thumbnail_path.exists() else None,
                'file_size_mb': blend_path.stat().st_size / (1024 * 1024) if blend_path.exists() else 0,
                'has_materials': 1 if metadata.get('material_count', 0) > 0 else 0,
                'has_skeleton': 0,
                'has_animations': 0,
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
                # Variant system fields
                'asset_id': asset_id,
                'variant_name': variant_name,
                # Scene-specific fields
                'scene_name': metadata.get('scene_name'),
                'object_count': metadata.get('object_count'),
                'collection_count': metadata.get('collection_count'),
                'render_engine': metadata.get('render_engine'),
                'resolution_x': metadata.get('resolution_x'),
                'resolution_y': metadata.get('resolution_y'),
                'world_name': metadata.get('world_name'),
                'frame_start': metadata.get('frame_start'),
                'frame_end': metadata.get('frame_end'),
                'frame_rate': metadata.get('frame_rate'),
            }

            # Add the new asset/version
            library.add_asset(asset_data)

            # Copy folder memberships from source to new version
            if is_new_version and self.source_uuid:
                library.copy_folders_to_asset(self.source_uuid, asset_uuid)

            if is_new_version:
                self.report({'INFO'}, f"Exported scene '{self.asset_name}' as {version_label}")
            else:
                self.report({'INFO'}, f"Exported scene '{self.asset_name}' to library")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            import traceback
            traceback.print_exc()
            if library_folder.exists():
                shutil.rmtree(library_folder, ignore_errors=True)
            return {'CANCELLED'}

    def _save_scene_blend(self, context, scene, filepath: str):
        """Save .blend file containing the entire scene (same as collection export)"""
        try:
            bpy.ops.wm.save_as_mainfile(filepath=filepath, copy=True, compress=True)
        except Exception as e:
            raise

    def _generate_thumbnail(self, context, scene, filepath: str):
        """Generate thumbnail for the scene using camera or viewport framing."""
        capture_scene_thumbnail(context, scene, filepath, size=256)


# Registration
classes = [
    UAL_OT_export_scene,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = ['UAL_OT_export_scene', 'register', 'unregister']
