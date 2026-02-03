"""
Import from Library Operator

Imports assets from Universal Library into Blender.
"""

import bpy
import json
from pathlib import Path
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty
from bpy.types import Operator

from ..utils.library_connection import get_library_connection


class UAL_OT_import_from_library(Operator):
    """Import asset from Universal Library"""
    bl_idname = "ual.import_from_library"
    bl_label = "Import from Library"
    bl_description = "Import a USD asset from the library"
    bl_options = {'REGISTER', 'UNDO'}

    # Properties
    asset_uuid: StringProperty(
        name="Asset UUID",
        description="UUID of the asset to import",
        default=""
    )

    import_method: EnumProperty(
        name="Import Method",
        description="How to import the asset",
        items=[
            ('USD', "USD (Universal)", "Import via USD format"),
            ('BLEND', "Blend (Full Fidelity)", "Import from .blend backup if available"),
        ],
        default='USD'
    )

    link_or_append: EnumProperty(
        name="Link/Append",
        description="Link or append when importing from .blend",
        items=[
            ('APPEND', "Append", "Copy data into current file"),
            ('LINK', "Link", "Reference data from external file"),
        ],
        default='APPEND'
    )

    use_current_reference: BoolProperty(
        name="Link as Current (Auto-Update)",
        description="Link via .current.blend proxy - asset auto-updates when library is reloaded",
        default=True
    )

    import_materials: BoolProperty(
        name="Import Materials",
        description="Import materials with the asset",
        default=True
    )

    import_animations: BoolProperty(
        name="Import Animations",
        description="Import animation data",
        default=True
    )

    scale: FloatProperty(
        name="Scale",
        description="Scale factor for imported asset",
        default=1.0,
        min=0.001,
        max=1000.0
    )

    place_at_cursor: BoolProperty(
        name="Place at Cursor",
        description="Place imported asset at 3D cursor location (disable to keep original location)",
        default=False
    )

    keep_original_location: BoolProperty(
        name="Keep Original Location",
        description="Preserve the original world location from when the asset was saved",
        default=True
    )

    @classmethod
    def poll(cls, context):
        """Always available if library is connected"""
        return True

    def invoke(self, context, event):
        """Show dialog if UUID not set"""
        if not self.asset_uuid:
            # Would normally show asset browser here
            self.report({'ERROR'}, "No asset selected")
            return {'CANCELLED'}

        # Get asset info for dialog
        library = get_library_connection()
        asset = library.get_asset_by_uuid(self.asset_uuid)

        if not asset:
            self.report({'ERROR'}, f"Asset not found: {self.asset_uuid}")
            return {'CANCELLED'}

        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        """Draw dialog UI"""
        layout = self.layout

        # Get asset info
        library = get_library_connection()
        asset = library.get_asset_by_uuid(self.asset_uuid)

        if asset:
            box = layout.box()
            box.label(text=f"Asset: {asset.get('name', 'Unknown')}")
            box.label(text=f"Type: {asset.get('asset_type', 'Unknown').title()}")

            if asset.get('polygon_count'):
                box.label(text=f"Polygons: {asset['polygon_count']:,}")

            # Show if blend backup available
            has_blend = asset.get('blend_backup_path') and Path(asset['blend_backup_path']).exists()
            if has_blend:
                box.label(text="Blend backup available", icon='CHECKMARK')

        layout.separator()

        # Collection and scene assets always use .blend and need Link/Append choice
        is_collection = asset and asset.get('asset_type') == 'collection'
        is_scene = asset and asset.get('asset_type') == 'scene'

        if is_collection:
            # Collections always import from .blend
            box = layout.box()
            box.label(text="Import Mode:", icon='OUTLINER_COLLECTION')
            box.prop(self, "link_or_append", expand=True)
            if self.link_or_append == 'LINK':
                box.label(text="Creates instanced collection (read-only)", icon='INFO')
                box.prop(self, "use_current_reference")
                if self.use_current_reference:
                    box.label(text="Auto-updates when library reloaded", icon='FILE_REFRESH')
            else:
                box.label(text="Copies all objects as local", icon='INFO')
        elif is_scene:
            # Scenes always import from .blend
            box = layout.box()
            box.label(text="Import Mode:", icon='SCENE_DATA')
            box.prop(self, "link_or_append", expand=True)
            if self.link_or_append == 'LINK':
                box.label(text="Links scene as read-only reference", icon='INFO')
            else:
                box.label(text="Appends scene as editable copy", icon='INFO')
        else:
            layout.prop(self, "import_method")

            if self.import_method == 'BLEND':
                layout.prop(self, "link_or_append")
                # Show "Link as Current" option only for LINK mode
                if self.link_or_append == 'LINK':
                    layout.prop(self, "use_current_reference")
                    if self.use_current_reference:
                        layout.label(text="Auto-updates when library reloaded", icon='FILE_REFRESH')

        layout.prop(self, "import_materials")
        layout.prop(self, "import_animations")
        layout.prop(self, "scale")

        layout.separator()
        layout.label(text="Placement:")
        layout.prop(self, "keep_original_location")
        row = layout.row()
        row.enabled = not self.keep_original_location
        row.prop(self, "place_at_cursor")

    def execute(self, context):
        """Execute the import"""
        if not self.asset_uuid:
            self.report({'ERROR'}, "No asset UUID specified")
            return {'CANCELLED'}

        # Get asset from library
        library = get_library_connection()
        asset = library.get_asset_by_uuid(self.asset_uuid)

        if not asset:
            self.report({'ERROR'}, f"Asset not found: {self.asset_uuid}")
            return {'CANCELLED'}

        # Store selection before import to identify new objects
        objects_before = set(context.scene.objects)

        # Handle collection and scene assets specially
        asset_type = asset.get('asset_type', '')
        if asset_type == 'collection':
            result = self._import_collection(context, asset)
        elif asset_type == 'scene':
            result = self._import_scene(context, asset)
        # Choose import method for other assets
        elif self.import_method == 'BLEND':
            result = self._import_blend(context, asset)
        else:
            result = self._import_usd(context, asset)

        if result:
            # Force scene update to ensure new objects are visible
            context.view_layer.update()

            # Identify newly imported objects
            objects_after = set(context.scene.objects)
            new_objects = objects_after - objects_before

            # Fallback 1: if no new objects detected, use selected objects
            if not new_objects:
                new_objects = set(context.selected_objects)

            # Fallback 2: if still empty, try to find objects by name pattern
            if not new_objects:
                asset_name = asset.get('name', '')
                for obj in context.scene.objects:
                    if asset_name and asset_name in obj.name:
                        new_objects.add(obj)

            # Store UAL metadata on imported objects for versioning
            if new_objects:
                self._store_asset_metadata(new_objects, asset)

            # Update last viewed date
            try:
                from datetime import datetime
                library.update_asset(self.asset_uuid, {
                    'last_viewed_date': datetime.now().isoformat()
                })
            except Exception:
                pass  # Non-critical, ignore errors

            self.report({'INFO'}, f"Imported '{asset.get('name', 'Unknown')}'")
            return {'FINISHED'}
        else:
            return {'CANCELLED'}

    def _store_asset_metadata(self, objects, asset: dict):
        """
        Store UAL metadata on imported objects for version tracking.

        This allows the export operator to detect that these objects
        came from the library and offer "Export as New Version" option.
        """
        uuid = asset.get('uuid', '')
        # Use version_group_id if exists, otherwise use uuid as the group
        version_group_id = asset.get('version_group_id') or uuid
        version = asset.get('version', 1)
        version_label = asset.get('version_label', 'v001')
        name = asset.get('name', '')
        asset_type = asset.get('asset_type', 'model')
        representation_type = asset.get('representation_type', 'none')

        # Variant system properties - critical for maintaining variant lineage
        asset_id = asset.get('asset_id') or version_group_id
        variant_name = asset.get('variant_name') or 'Base'

        for obj in objects:
            # Store as custom properties
            obj["ual_uuid"] = uuid
            obj["ual_version_group_id"] = version_group_id
            obj["ual_version"] = version
            obj["ual_version_label"] = version_label
            obj["ual_asset_name"] = name
            obj["ual_asset_type"] = asset_type
            obj["ual_representation_type"] = representation_type

            # Variant system - ensures variant exports stay in their lineage
            obj["ual_asset_id"] = asset_id
            obj["ual_variant_name"] = variant_name

            # Mark as imported from UAL
            obj["ual_imported"] = True

    def _import_usd(self, context, asset: dict) -> bool:
        """Import via USD"""
        usd_path = asset.get('usd_file_path')

        if not usd_path or not Path(usd_path).exists():
            self.report({'ERROR'}, f"USD file not found: {usd_path}")
            return False

        try:
            # Build import settings - use only well-supported parameters
            import_kwargs = {
                'filepath': usd_path,
            }

            # Add scale if supported (Blender 4.0+)
            try:
                import_kwargs['scale'] = self.scale
            except Exception:
                pass

            # Execute import
            result = bpy.ops.wm.usd_import(**import_kwargs)

            if result != {'FINISHED'}:
                return False

            # Handle placement - only move if NOT keeping original location
            if not self.keep_original_location and self.place_at_cursor:
                if context.selected_objects:
                    cursor_loc = context.scene.cursor.location.copy()
                    root_objects = [obj for obj in context.selected_objects if obj.parent is None]
                    for obj in root_objects:
                        obj.location = cursor_loc

            return True

        except Exception as e:
            self.report({'ERROR'}, f"USD import failed: {str(e)}")
            return False

    def _import_blend(self, context, asset: dict) -> bool:
        """Import from .blend backup"""
        blend_path = asset.get('blend_backup_path')

        if not blend_path or not Path(blend_path).exists():
            self.report({'WARNING'}, "No .blend backup available, falling back to USD")
            return self._import_usd(context, asset)

        # Use .current.blend proxy for auto-updating links when linking
        if self.link_or_append == 'LINK' and self.use_current_reference:
            current_path = self._get_current_blend_path(blend_path)
            if current_path and Path(current_path).exists():
                blend_path = current_path

        try:
            # Track materials before import (for material assets)
            materials_before = set(bpy.data.materials.keys())
            existing_collections = set(bpy.data.collections.keys())
            existing_objects = set(bpy.data.objects.keys())
            link = (self.link_or_append == 'LINK')

            # Import objects and collections from blend file
            with bpy.data.libraries.load(blend_path, link=link) as (data_from, data_to):
                data_to.objects = data_from.objects
                data_to.collections = data_from.collections

                # Import materials if requested
                if self.import_materials:
                    data_to.materials = data_from.materials

            # Find newly imported collections and objects
            new_collection_names = set(bpy.data.collections.keys()) - existing_collections
            new_object_names = set(bpy.data.objects.keys()) - existing_objects

            # Link root collections to scene (preserves hierarchy + custom shapes)
            if new_collection_names:
                imported_collections = [bpy.data.collections[n] for n in new_collection_names]
                # Find nested names so we only link root-level collections
                nested_names = set()
                for col in imported_collections:
                    for child in col.children:
                        nested_names.add(child.name)
                root_collections = [c for c in imported_collections if c.name not in nested_names]

                for col in root_collections:
                    if col.name not in [c.name for c in context.scene.collection.children]:
                        context.scene.collection.children.link(col)

            # Gather imported objects
            imported_objects = [bpy.data.objects[n] for n in new_object_names if n in bpy.data.objects]

            # If no collections were imported, link objects directly (backward compat)
            if not new_collection_names:
                for obj in imported_objects:
                    if obj is not None:
                        if obj.name not in context.collection.objects:
                            context.collection.objects.link(obj)

            # Select imported objects
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.update()
            for obj in imported_objects:
                try:
                    obj.select_set(True)
                except RuntimeError:
                    pass  # Object may not be in view layer (hidden collection)

            if imported_objects:
                # Set active to first selectable object
                for obj in imported_objects:
                    if obj.visible_get():
                        context.view_layer.objects.active = obj
                        break

            # Apply scale (only to root objects)
            if self.scale != 1.0:
                for obj in imported_objects:
                    if obj.parent is None:
                        obj.scale *= self.scale

            # Handle placement - only move if NOT keeping original location
            if not self.keep_original_location and self.place_at_cursor:
                cursor_loc = context.scene.cursor.location.copy()
                root_objects = [obj for obj in imported_objects if obj.parent is None]
                for obj in root_objects:
                    obj.location = cursor_loc

            # Tag imported materials with UAL metadata (for material versioning)
            if asset.get('asset_type') == 'material':
                self._tag_imported_materials(asset, materials_before)

            return True

        except Exception as e:
            self.report({'ERROR'}, f"Blend import failed: {str(e)}")
            return False

    def _tag_imported_materials(self, asset: dict, materials_before: set):
        """Tag imported materials with UAL metadata for version tracking."""
        from ..utils.metadata_handler import store_material_metadata

        asset_name = asset.get('name', '')
        materials_after = set(bpy.data.materials.keys())
        new_material_names = materials_after - materials_before

        # Find the imported material
        for mat_name in new_material_names:
            mat = bpy.data.materials.get(mat_name)
            if mat:
                store_material_metadata(mat, asset)
                break

        # Fallback: if no new materials detected, try to find by name
        if not new_material_names:
            for mat in bpy.data.materials:
                if mat.name == asset_name or mat.name.startswith(asset_name):
                    store_material_metadata(mat, asset)
                    break

    def _get_current_blend_path(self, blend_path: str) -> str:
        """
        Get the .current.blend proxy path for auto-updating links.

        Args:
            blend_path: Path to the actual .blend file

        Returns:
            Path to .current.blend if it exists, otherwise original path
        """
        if not blend_path:
            return blend_path

        path = Path(blend_path)
        
        # Strip version suffix (e.g., .v003) to get base name
        # AST_Cube.v003.blend -> AST_Cube.current.blend
        import re
        stem = path.stem
        base_name = re.sub(r'\.(v\d{3,})$', '', stem)
        
        current_path = path.parent / f"{base_name}.current.blend"

        if current_path.exists():
            return str(current_path)

        return blend_path

    def _import_collection(self, context, asset: dict) -> bool:
        """Import a collection asset with Link or Append based on user choice"""
        blend_path = asset.get('blend_backup_path')

        if not blend_path or not Path(blend_path).exists():
            self.report({'ERROR'}, f"Collection .blend file not found: {blend_path}")
            return False

        try:
            is_link = (self.link_or_append == 'LINK')

            # Use .current.blend proxy for auto-updating links when linking
            if is_link and self.use_current_reference:
                current_path = self._get_current_blend_path(blend_path)
                if current_path and Path(current_path).exists():
                    blend_path = current_path

            if is_link:
                # Link mode: Import as instanced collection
                return self._import_collection_as_instance(context, asset, blend_path)
            else:
                # Append mode: Import all contents as local copies
                return self._import_collection_append(context, asset, blend_path)

        except Exception as e:
            self.report({'ERROR'}, f"Collection import failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def _import_collection_as_instance(self, context, asset: dict, blend_path: str) -> bool:
        """Import collection as linked instance (creates Empty with instanced collection)"""
        collection_name = asset.get('collection_name') or asset.get('name', 'Collection')

        # Normalize path for Blender's internal use (forward slashes)
        blend_path_normalized = blend_path.replace('\\', '/')

        # First, find available collections in the file
        with bpy.data.libraries.load(blend_path, link=True) as (data_from, data_to):
            available_collections = list(data_from.collections)

        if not available_collections:
            self.report({'ERROR'}, "No collections found in .blend file")
            return False

        # Find the target collection
        target_collection = None
        if collection_name in available_collections:
            target_collection = collection_name
        else:
            # Try to find a matching collection
            for col_name in available_collections:
                if col_name.startswith(collection_name) or collection_name in col_name:
                    target_collection = col_name
                    break

        # Fallback to first non-scene collection
        if not target_collection:
            for col_name in available_collections:
                if 'scene' not in col_name.lower():
                    target_collection = col_name
                    break
            if not target_collection:
                target_collection = available_collections[0]

        # Build proper paths
        inner_path = "Collection"
        directory = f"{blend_path_normalized}/{inner_path}/"
        filepath = f"{blend_path_normalized}/{inner_path}/{target_collection}"

        # Link the collection using bpy.ops.wm.link - preserves hierarchy
        bpy.ops.wm.link(
            filepath=filepath,
            directory=directory,
            filename=target_collection,
            link=True,
            autoselect=False,
            active_collection=False,
            instance_collections=True,  # Create instance automatically
        )

        # Find the created instance Empty (most recently added object)
        instance_empty = None
        for obj in context.selected_objects:
            if obj.instance_type == 'COLLECTION' and obj.instance_collection:
                instance_empty = obj
                break

        # If no instance found, create one manually
        if not instance_empty:
            # Get the linked collection
            linked_collection = bpy.data.collections.get(target_collection)
            if not linked_collection:
                # Try with .001 suffix or find by library
                for col in bpy.data.collections:
                    if col.name.startswith(target_collection) and col.library:
                        linked_collection = col
                        break

            if linked_collection:
                instance_empty = bpy.data.objects.new(
                    name=f"{asset.get('name', 'Collection')}_Instance",
                    object_data=None
                )
                instance_empty.instance_type = 'COLLECTION'
                instance_empty.instance_collection = linked_collection
                context.collection.objects.link(instance_empty)

        if not instance_empty:
            self.report({'ERROR'}, "Failed to create collection instance")
            return False

        # Select the instance
        bpy.ops.object.select_all(action='DESELECT')
        instance_empty.select_set(True)
        context.view_layer.objects.active = instance_empty

        # Apply scale
        if self.scale != 1.0:
            instance_empty.scale = (self.scale, self.scale, self.scale)

        # Handle placement
        if not self.keep_original_location and self.place_at_cursor:
            instance_empty.location = context.scene.cursor.location.copy()

        # Hide any WGT collections that came through the link
        from ..utils.widget_helpers import hide_widget_collections
        hide_widget_collections(context)

        return True

    def _import_collection_append(self, context, asset: dict, blend_path: str) -> bool:
        """Import collection by appending all contents as local copies, preserving hierarchy"""
        collection_name = asset.get('collection_name') or asset.get('name', 'Collection')

        # Track what exists before import
        existing_collections = set(bpy.data.collections.keys())
        existing_objects = set(bpy.data.objects.keys())

        # First, find what collections are in the file
        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            available_collections = list(data_from.collections)
            available_objects = list(data_from.objects)

        # Find the target collection
        target_collection = None
        if collection_name in available_collections:
            target_collection = collection_name
        else:
            for col_name in available_collections:
                if col_name.startswith(collection_name) or collection_name in col_name:
                    target_collection = col_name
                    break
            # Fallback to first non-scene collection
            if not target_collection:
                for col_name in available_collections:
                    if 'scene' not in col_name.lower() and 'master' not in col_name.lower():
                        target_collection = col_name
                        break

        if not target_collection:
            self.report({'ERROR'}, f"Could not find collection '{collection_name}' in file")
            return False

        # METHOD: Use bpy.ops.wm.append with files parameter for multiple items
        # This is exactly how Blender's File > Append works
        blend_path_normalized = blend_path.replace('\\', '/')

        # Append the collection (this should bring nested collections too)
        directory = f"{blend_path_normalized}/Collection/"

        # Build list of files to append - the collection
        files = [{"name": target_collection}]

        try:
            bpy.ops.wm.append(
                directory=directory,
                files=files,
                link=False,
                autoselect=True,
                active_collection=True,  # Add to active collection in scene
                instance_collections=False,
            )
        except Exception:
            pass

        # Check what was imported
        new_collection_names = set(bpy.data.collections.keys()) - existing_collections
        new_object_names = set(bpy.data.objects.keys()) - existing_objects

        # Find the main imported collection
        imported_collection = None
        for name in new_collection_names:
            if name == target_collection or name.startswith(target_collection):
                imported_collection = bpy.data.collections.get(name)
                break

        if not imported_collection and new_collection_names:
            # Get the first non-nested collection
            nested = set()
            for col_name in new_collection_names:
                col = bpy.data.collections.get(col_name)
                if col:
                    for child in col.children:
                        nested.add(child.name)
            for col_name in new_collection_names:
                if col_name not in nested:
                    imported_collection = bpy.data.collections.get(col_name)
                    break

        # Link collection to scene if not already linked
        if imported_collection:
            scene_children = [c.name for c in context.scene.collection.children]
            if imported_collection.name not in scene_children:
                context.scene.collection.children.link(imported_collection)

        # Get all imported objects
        imported_objects = [bpy.data.objects[name] for name in new_object_names if name in bpy.data.objects]

        # Update view layer
        context.view_layer.update()

        # Select imported objects
        bpy.ops.object.select_all(action='DESELECT')
        for obj in imported_objects:
            try:
                obj.select_set(True)
            except RuntimeError:
                pass

        if imported_objects:
            context.view_layer.objects.active = imported_objects[0]

        # Apply scale
        if self.scale != 1.0:
            for obj in imported_objects:
                if obj.parent is None:
                    obj.scale *= self.scale

        # Handle placement
        if not self.keep_original_location and self.place_at_cursor:
            cursor_loc = context.scene.cursor.location.copy()
            for obj in imported_objects:
                if obj.parent is None:
                    obj.location = cursor_loc

        return True


    def _import_scene(self, context, asset: dict) -> bool:
        """Import a scene asset with Link or Append based on user choice"""
        blend_path = asset.get('blend_backup_path')

        if not blend_path or not Path(blend_path).exists():
            self.report({'ERROR'}, f"Scene .blend file not found: {blend_path}")
            return False

        try:
            is_link = (self.link_or_append == 'LINK')
            scene_name = asset.get('scene_name') or asset.get('name', 'Scene')

            # Track existing scenes
            existing_scenes = set(bpy.data.scenes.keys())

            # Load scenes from the blend file
            with bpy.data.libraries.load(blend_path, link=is_link) as (data_from, data_to):
                available_scenes = list(data_from.scenes)

                # Find the target scene
                if scene_name in available_scenes:
                    data_to.scenes = [scene_name]
                else:
                    # Try partial match or fallback to first
                    target = None
                    for name in available_scenes:
                        if scene_name in name or name in scene_name:
                            target = name
                            break
                    if not target and available_scenes:
                        target = available_scenes[0]

                    if target:
                        data_to.scenes = [target]
                    else:
                        self.report({'ERROR'}, f"No scenes found in file")
                        return False

            # Find the newly imported scene
            new_scene_names = set(bpy.data.scenes.keys()) - existing_scenes

            if not new_scene_names:
                self.report({'WARNING'}, "Scene may have already existed in file")
                return True

            # Get the imported scene
            imported_scene_name = list(new_scene_names)[0]
            imported_scene = bpy.data.scenes.get(imported_scene_name)

            if imported_scene:

                # Optionally switch to the imported scene
                context.window.scene = imported_scene

                self.report(
                    {'INFO'},
                    f"Imported scene '{imported_scene.name}' ({'linked' if is_link else 'appended'})"
                )

            return True

        except Exception as e:
            self.report({'ERROR'}, f"Scene import failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


class UAL_OT_browse_library(Operator):
    """Open library browser"""
    bl_idname = "ual.browse_library"
    bl_label = "Browse Asset Library"
    bl_description = "Open the desktop asset library application"

    def execute(self, context):
        import subprocess
        import os
        from ..preferences import get_preferences

        prefs = get_preferences()
        if not prefs:
            self.report({'ERROR'}, "Could not get addon preferences")
            return {'CANCELLED'}

        try:
            if prefs.launch_mode == 'PRODUCTION':
                # Production mode - launch executable
                app_path = prefs.app_executable_path

                if not app_path:
                    self.report({'ERROR'}, "Desktop app path not set. Check addon preferences.")
                    return {'CANCELLED'}

                if not Path(app_path).exists():
                    self.report({'ERROR'}, f"App not found: {app_path}")
                    return {'CANCELLED'}

                # Launch the app
                if app_path.endswith('.bat'):
                    # Run batch file
                    subprocess.Popen(
                        ['cmd', '/c', app_path],
                        cwd=str(Path(app_path).parent),
                        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
                    )
                else:
                    # Run executable
                    subprocess.Popen(
                        [app_path],
                        cwd=str(Path(app_path).parent)
                    )

                self.report({'INFO'}, "Launching Universal Library...")

            else:
                # Development mode - run with Python
                script_path = prefs.dev_script_path
                python_exe = prefs.python_executable or 'python'

                if not script_path:
                    self.report({'ERROR'}, "Dev script path not set. Check addon preferences.")
                    return {'CANCELLED'}

                if not Path(script_path).exists():
                    self.report({'ERROR'}, f"Script not found: {script_path}")
                    return {'CANCELLED'}

                # Run with Python
                subprocess.Popen(
                    [python_exe, script_path],
                    cwd=str(Path(script_path).parent),
                    creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
                )

                self.report({'INFO'}, "Launching Universal Library (dev mode)...")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to launch app: {str(e)}")
            return {'CANCELLED'}


class UAL_OT_refresh_library(Operator):
    """Refresh library connection"""
    bl_idname = "ual.refresh_library"
    bl_label = "Refresh Library"
    bl_description = "Refresh connection to the asset library"

    def execute(self, context):
        library = get_library_connection()
        library.disconnect()
        library.connect()

        assets = library.get_all_assets()
        self.report({'INFO'}, f"Library refreshed: {len(assets)} assets")
        return {'FINISHED'}


# Registration
classes = [
    UAL_OT_import_from_library,
    UAL_OT_browse_library,
    UAL_OT_refresh_library,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_OT_import_from_library',
    'UAL_OT_browse_library',
    'UAL_OT_refresh_library',
    'register',
    'unregister'
]
