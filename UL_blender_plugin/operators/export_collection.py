"""
Export Collection to Library Operator

Exports the active Blender Collection to the Universal Library.
"""

import bpy
import uuid
import json
import shutil
from pathlib import Path
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

from ..utils.library_connection import get_library_connection
from ..utils.metadata_collector import collect_collection_metadata
from ..utils.naming_utils import get_asset_namer, set_custom_prefixes
from ..utils.viewport_capture import capture_collection_thumbnail, create_placeholder_thumbnail
from ..preferences import get_preferences, get_naming_prefixes


class UAL_OT_export_collection(Operator):
    """Export active collection to Universal Library"""
    bl_idname = "ual.export_collection"
    bl_label = "Export Collection to Library"
    bl_description = "Export the active collection as a collection asset"
    bl_options = {'REGISTER', 'UNDO'}

    # Properties
    asset_name: StringProperty(
        name="Asset Name",
        description="Name for the collection asset in the library",
        default=""
    )

    description: StringProperty(
        name="Description",
        description="Optional description for the collection",
        default=""
    )

    # Versioning properties
    export_mode: EnumProperty(
        name="Export Mode",
        description="Export as new asset or new version of existing",
        items=[
            ('NEW_ASSET', "New Asset", "Create a brand new collection asset"),
            ('NEW_VERSION', "New Version", "Create new version of existing collection"),
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
    # Variant system properties
    source_asset_id: StringProperty(default="")
    source_variant_name: StringProperty(default="Base")

    @classmethod
    def poll(cls, context):
        """Check if operator can run - must have active collection that's not scene root"""
        return (context.collection and
                context.collection != context.scene.collection)

    def invoke(self, context, event):
        """Show dialog before export"""
        collection = context.collection
        self.asset_name = collection.name

        # Check for UAL metadata on collection objects for versioning
        self._check_collection_ual_metadata(context, collection)

        return context.window_manager.invoke_props_dialog(self, width=400)

    def _check_collection_ual_metadata(self, context, collection):
        """Check if collection objects have UAL metadata from library import"""
        self.has_ual_metadata = False
        self.source_uuid = ""
        self.source_version_group_id = ""
        self.source_version = 0
        self.source_asset_name = ""
        self.source_asset_id = ""
        self.source_variant_name = "Base"

        # Check objects in collection for UAL metadata
        for obj in collection.objects:
            if obj.get("ual_imported") and obj.get("ual_asset_type") == "collection":
                self.has_ual_metadata = True
                self.source_uuid = obj.get("ual_uuid", "")
                self.source_version_group_id = obj.get("ual_version_group_id", "")
                self.source_version = obj.get("ual_version", 0)
                self.source_asset_name = obj.get("ual_asset_name", "")
                # Variant system - fallback to version_group_id for legacy objects
                self.source_asset_id = obj.get("ual_asset_id", self.source_version_group_id)
                self.source_variant_name = obj.get("ual_variant_name", "Base")

                break

    def _get_collection_stats(self, collection) -> dict:
        """Get statistics about collection contents"""
        all_objects = self._get_all_collection_objects(collection)
        nested = self._get_nested_collections(collection)

        meshes = [obj for obj in all_objects if obj.type == 'MESH']
        lights = [obj for obj in all_objects if obj.type == 'LIGHT']
        cameras = [obj for obj in all_objects if obj.type == 'CAMERA']
        armatures = [obj for obj in all_objects if obj.type == 'ARMATURE']

        return {
            'mesh_count': len(meshes),
            'light_count': len(lights),
            'camera_count': len(cameras),
            'armature_count': len(armatures),
            'nested_count': len(nested),
            'total_objects': len(all_objects),
        }

    def _get_all_collection_objects(self, collection) -> list:
        """Recursively get all objects from collection and nested children"""
        objects = list(collection.objects)
        for child_col in collection.children:
            objects.extend(self._get_all_collection_objects(child_col))
        return objects

    def _get_nested_collections(self, collection) -> list:
        """Get all nested child collections recursively"""
        nested = []
        for child_col in collection.children:
            nested.append(child_col)
            nested.extend(self._get_nested_collections(child_col))
        return nested

    def draw(self, context):
        """Draw dialog UI"""
        layout = self.layout
        collection = context.collection

        # Show collection info
        box = layout.box()
        box.label(text=f"Collection: {collection.name}", icon='OUTLINER_COLLECTION')

        # Show contents summary
        stats = self._get_collection_stats(collection)
        row = box.row()
        row.label(text=f"{stats['mesh_count']} Meshes")
        row.label(text=f"{stats['light_count']} Lights")
        row.label(text=f"{stats['camera_count']} Cameras")

        if stats['armature_count'] > 0:
            row = box.row()
            row.label(text=f"{stats['armature_count']} Armatures")

        if stats['nested_count'] > 0:
            box.label(text=f"{stats['nested_count']} nested collections", icon='OUTLINER')

        box.label(text=f"Total: {stats['total_objects']} objects")

        layout.separator()

        # Versioning section (if has UAL metadata)
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
        """Execute the collection export"""
        if not self.asset_name:
            self.report({'ERROR'}, "Asset name is required")
            return {'CANCELLED'}

        collection = context.collection
        if not collection or collection == context.scene.collection:
            self.report({'ERROR'}, "No valid collection selected")
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
            if library.asset_name_exists(self.asset_name, asset_type='collection'):
                self.report(
                    {'ERROR'},
                    f"A collection asset named '{self.asset_name}' already exists! "
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
            # Preserve asset_id and variant_name from source
            asset_id = self.source_asset_id or version_group_id
            variant_name = self.source_variant_name or "Base"
        else:
            version_group_id = asset_uuid
            version = 1
            version_label = "v001"
            # New asset gets its own asset_id and default "Base" variant
            asset_id = asset_uuid
            variant_name = "Base"

        # Get asset folder using library structure
        # library/{type}/{name}/{variant}/ - for latest only
        library_folder = library.get_library_folder_path(
            asset_id, self.asset_name, variant_name, 'collection'
        )

        try:
            # If new version, archive previous BEFORE writing new files.
            # Both versions share the same library_folder, so cold storage
            # must move v(N-1)'s files out before v(N) overwrites them.
            if is_new_version and self.source_uuid:
                library.update_asset(self.source_uuid, {'is_latest': 0})
                if self.archive_previous:
                    library.move_to_cold_storage(self.source_uuid)

            # Export as .blend file (full fidelity for collections)
            # Include version in filename to prevent Blender from merging libraries
            blend_path = library_folder / f"{self.asset_name}.{version_label}.blend"
            self._save_collection_blend(context, collection, str(blend_path))

            # Generate thumbnail
            thumbnail_path = library_folder / "thumbnail.png"
            self._generate_thumbnail(context, collection, str(thumbnail_path))

            # Collect metadata
            metadata = collect_collection_metadata(collection)

            # Add to library database
            asset_data = {
                'uuid': asset_uuid,
                'name': self.asset_name,
                'description': self.description,
                'folder_id': 1,  # Root folder
                'asset_type': 'collection',
                'usd_file_path': None,  # Collections use .blend only
                'blend_backup_path': str(blend_path),
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
                # Variant system fields
                'asset_id': asset_id,
                'variant_name': variant_name,
                # Collection-specific fields
                'mesh_count': metadata.get('mesh_count', 0),
                'light_count': metadata.get('light_count', 0),
                'camera_count': metadata.get('camera_count', 0),
                'armature_count': metadata.get('armature_count', 0),
                'collection_name': metadata.get('collection_name', collection.name),
                'has_nested_collections': metadata.get('has_nested_collections', 0),
                'nested_collection_count': metadata.get('nested_collection_count', 0),
                # Type-specific metadata from contained objects
                'bone_count': metadata.get('bone_count'),
                'has_facial_rig': metadata.get('has_facial_rig', 0),
                'light_type': metadata.get('light_type'),
                'camera_type': metadata.get('camera_type'),
                'focal_length': metadata.get('focal_length'),
            }

            # Add the new asset/version
            library.add_asset(asset_data)

            # Update metadata on collection objects
            self._update_object_metadata(context, collection, asset_uuid,
                                         version_group_id, version, version_label,
                                         asset_id, variant_name)

            if is_new_version:
                self.report({'INFO'}, f"Exported collection '{self.asset_name}' as {version_label}")
            else:
                self.report({'INFO'}, f"Exported collection '{self.asset_name}' to library")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            import traceback
            traceback.print_exc()
            if library_folder.exists():
                shutil.rmtree(library_folder, ignore_errors=True)
            return {'CANCELLED'}

    def _update_object_metadata(self, context, collection, asset_uuid,
                                 version_group_id, version, version_label,
                                 asset_id, variant_name):
        """Update UAL metadata on all objects in collection after export"""
        all_objects = self._get_all_collection_objects(collection)

        for obj in all_objects:
            obj["ual_uuid"] = asset_uuid
            obj["ual_version_group_id"] = version_group_id
            obj["ual_version"] = version
            obj["ual_version_label"] = version_label
            obj["ual_asset_name"] = self.asset_name
            obj["ual_asset_type"] = "collection"
            obj["ual_imported"] = True
            # Variant system
            obj["ual_asset_id"] = asset_id
            obj["ual_variant_name"] = variant_name

    def _save_collection_blend(self, context, collection, filepath: str):
        """Save .blend file containing the entire collection hierarchy"""
        try:
            # Ensure the collection is linked to the scene (required for save_as to include it)
            scene_collection = context.scene.collection
            if collection.name not in [c.name for c in scene_collection.children]:
                # Temporarily link to scene for export
                scene_collection.children.link(collection)
                was_linked = False
            else:
                was_linked = True

            # Save a copy of the file - this preserves ALL hierarchy relationships
            # The import side will extract only the collection we need
            bpy.ops.wm.save_as_mainfile(filepath=filepath, copy=True, compress=True)

        except Exception as e:
            raise

    def _generate_thumbnail(self, context, collection, filepath: str):
        """Generate thumbnail for the collection by framing all objects."""
        capture_collection_thumbnail(context, collection, filepath, size=256)


# Registration
classes = [
    UAL_OT_export_collection,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = ['UAL_OT_export_collection', 'register', 'unregister']
