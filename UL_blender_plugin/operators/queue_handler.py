"""
Queue Handler Operator - Polls and processes import requests from desktop app

Uses a modal timer operator to check for pending import requests
and executes them automatically.

Now uses the protocol module for schema-driven message validation.
"""

import bpy
from bpy.types import Operator
from pathlib import Path

from ..utils import (
    get_queue_client,
    # Import helpers
    import_asset,
    import_material_from_blend,
    import_material_from_usd,
    # Metadata
    store_ual_metadata,
    has_ual_metadata,
    # Blender helpers
    find_3d_viewport,
    select_objects,
    # Thumbnail
    generate_thumbnail,
    # Context managers
    render_settings,
)
from ..utils.protocol_loader import validate_message

# ValidationError for protocol validation failures
class ValidationError(Exception):
    """Raised when message validation fails."""
    pass


class UAL_OT_check_import_queue(Operator):
    """Check for pending requests from desktop app"""
    bl_idname = "ual.check_import_queue"
    bl_label = "Check Import Queue"
    bl_description = "Check for pending asset requests"

    def execute(self, context):
        """Process any pending requests"""
        client = get_queue_client()

        # Process import requests
        for request in client.get_pending_requests():
            self._process_import_request(context, request, client)

        # Process thumbnail requests
        for request in client.get_pending_thumbnail_requests():
            self._process_thumbnail_request(context, request, client)

        return {'FINISHED'}

    def _process_import_request(self, context, request: dict, client):
        """Process a single import request with protocol validation"""
        # Dispatch replace commands to dedicated handler
        command = request.get('command', 'import')
        if command == 'replace':
            self._process_replace_request(context, request, client)
            return
        if command == 'replace_any':
            self._process_replace_any_request(context, request, client)
            return

        file_path = request.get('file_path', '')

        # Validate message against protocol schema
        try:
            validate_message(request, "import_asset")
        except ValidationError as e:
            # Continue processing - validation is advisory for backwards compatibility
            pass

        asset_name = request.get('asset_name', 'Unknown')
        asset_type = request.get('asset_type', 'model')

        # Track objects before import
        objects_before = set(context.scene.objects)

        try:
            import_method = request.get('import_method', 'BLEND')
            link_mode = request.get('link_mode', 'APPEND')
            keep_location = request.get('keep_location', True)
            usd_file_path = request.get('usd_file_path', '')
            blend_file_path = request.get('blend_file_path', '')

            success = False

            # Handle material imports specially
            if asset_type == 'material':
                success = self._handle_material_import(
                    context, blend_file_path, usd_file_path, asset_name
                )
            else:
                # Standard asset import using helper
                filepath = blend_file_path if import_method == 'BLEND' else usd_file_path
                if filepath and Path(filepath).exists():
                    success, imported_objects = import_asset(
                        context,
                        filepath,
                        import_method=import_method,
                        link_mode=link_mode,
                        keep_location=keep_location
                    )
                else:
                    self.report({'ERROR'}, f"No valid file found for '{asset_name}'")
                    client.mark_failed(file_path, "No valid file path")
                    return

            if success:
                self._store_asset_metadata(context, objects_before, request)
                self.report({'INFO'}, f"Imported '{asset_name}'")
                client.mark_completed(file_path)
            else:
                client.mark_failed(file_path, "Import failed")

        except Exception as e:
            self.report({'ERROR'}, f"Import failed for '{asset_name}': {str(e)}")
            client.mark_failed(file_path, str(e))

    def _process_replace_request(self, context, request: dict, client):
        """Replace selected objects in Blender with the requested asset."""
        file_path = request.get('file_path', '')
        asset_name = request.get('asset_name', 'Unknown')

        # 1. Get selected objects and filter to replaceable types
        selected = list(context.selected_objects)
        replaceable = []
        for obj in selected:
            if obj.instance_type == 'COLLECTION' and obj.instance_collection:
                replaceable.append(obj)
            elif has_ual_metadata(obj):
                replaceable.append(obj)

        if not replaceable:
            self.report({'WARNING'}, "No replaceable objects selected in Blender")
            client.mark_failed(file_path, "No replaceable objects selected")
            return

        # 2. Snapshot undo state before destructive changes so Ctrl+Z
        #    restores the full pre-replace scene instead of hitting freed data.
        bpy.ops.ed.undo_push(message="Before Replace")

        # 3. Capture world matrices and collection membership
        transforms = []
        for obj in replaceable:
            collections = [c for c in obj.users_collection]
            target_col = collections[0] if collections else context.scene.collection
            transforms.append({
                'matrix_world': obj.matrix_world.copy(),
                'collection': target_col,
            })

        # 4. Delete originals
        for obj in replaceable:
            bpy.data.objects.remove(obj, do_unlink=True)

        # 5. Import replacement asset once
        import_method = request.get('import_method', 'BLEND')
        link_mode = request.get('link_mode', 'INSTANCE')
        blend_path = request.get('blend_file_path', '')
        usd_path = request.get('usd_file_path', '')
        filepath = blend_path if import_method == 'BLEND' else usd_path

        if not filepath or not Path(filepath).exists():
            self.report({'ERROR'}, f"No valid file found for '{asset_name}'")
            client.mark_failed(file_path, "No valid file path")
            return

        try:
            success, imported_objects = import_asset(
                context, filepath,
                import_method=import_method,
                link_mode=link_mode,
                keep_location=True
            )
        except Exception as e:
            self.report({'ERROR'}, f"Replace import failed: {e}")
            client.mark_failed(file_path, str(e))
            return

        if not success or not imported_objects:
            client.mark_failed(file_path, "Failed to import replacement")
            return

        # 6. Place first instance at first transform
        first_obj = imported_objects[0]
        first_transform = transforms[0]
        first_obj.matrix_world = first_transform['matrix_world']

        # Move to correct collection if needed
        target_col = first_transform['collection']
        if first_obj.name not in target_col.objects:
            target_col.objects.link(first_obj)
        for col in first_obj.users_collection:
            if col != target_col:
                col.objects.unlink(first_obj)

        new_objects = [first_obj]

        # 7. Duplicate for remaining transforms
        for transform in transforms[1:]:
            dup = first_obj.copy()
            target_col = transform['collection']
            target_col.objects.link(dup)
            dup.matrix_world = transform['matrix_world']
            new_objects.append(dup)

        # 8. Store UAL metadata on all new objects
        asset_uuid = request.get('asset_uuid', '')
        version_group_id = request.get('version_group_id') or asset_uuid
        for obj in new_objects:
            store_ual_metadata(
                obj,
                uuid=asset_uuid,
                version_group_id=version_group_id,
                version=request.get('version', 1) or 1,
                version_label=request.get('version_label', 'v001') or 'v001',
                asset_name=request.get('asset_name', ''),
                asset_type=request.get('asset_type', 'model'),
                representation_type=request.get('representation_type', 'none') or 'none',
                imported=True,
                asset_id=request.get('asset_id') or version_group_id,
                variant_name=request.get('variant_name') or 'Base',
                link_mode=request.get('link_mode', 'INSTANCE')
            )

        # 9. Select new objects and finalize
        select_objects(context, new_objects)
        context.view_layer.update()

        # Push undo so Ctrl+Z lands on the clean "Before Replace" snapshot
        bpy.ops.ed.undo_push(message="Replace Selected")

        self.report({'INFO'},
            f"Replaced {len(transforms)} object(s) with '{asset_name}'")
        client.mark_completed(file_path)

    def _process_replace_any_request(self, context, request: dict, client):
        """
        Replace ANY selected objects with the requested asset.

        Unlike 'replace', this doesn't filter by UAL metadata or instance type.
        Useful for scatter workflows where plain empties need to be replaced.
        """
        file_path = request.get('file_path', '')
        asset_name = request.get('asset_name', 'Unknown')
        filter_type = request.get('filter_type', None)  # Optional: 'EMPTY', 'MESH', etc.

        # Get selected objects, optionally filtered by type
        selected = list(context.selected_objects)
        if filter_type:
            selected = [obj for obj in selected if obj.type == filter_type]

        if not selected:
            msg = f"No objects selected" + (f" of type {filter_type}" if filter_type else "")
            self.report({'WARNING'}, msg)
            client.mark_failed(file_path, msg)
            return

        # Push undo before destructive changes
        bpy.ops.ed.undo_push(message="Before Replace Any")

        # Capture transforms and collection membership
        transforms = []
        for obj in selected:
            collections = [c for c in obj.users_collection]
            target_col = collections[0] if collections else context.scene.collection
            transforms.append({
                'matrix_world': obj.matrix_world.copy(),
                'collection': target_col,
            })

        # Delete originals
        for obj in selected:
            bpy.data.objects.remove(obj, do_unlink=True)

        # Import replacement asset
        import_method = request.get('import_method', 'BLEND')
        link_mode = request.get('link_mode', 'INSTANCE')
        blend_path = request.get('blend_file_path', '')
        usd_path = request.get('usd_file_path', '')
        filepath = blend_path if import_method == 'BLEND' else usd_path

        if not filepath or not Path(filepath).exists():
            self.report({'ERROR'}, f"No valid file found for '{asset_name}'")
            client.mark_failed(file_path, "No valid file path")
            return

        try:
            success, imported_objects = import_asset(
                context, filepath,
                import_method=import_method,
                link_mode=link_mode,
                keep_location=True
            )
        except Exception as e:
            self.report({'ERROR'}, f"Replace import failed: {e}")
            client.mark_failed(file_path, str(e))
            return

        if not success or not imported_objects:
            client.mark_failed(file_path, "Failed to import replacement")
            return

        # Place first instance at first transform
        first_obj = imported_objects[0]
        first_transform = transforms[0]
        first_obj.matrix_world = first_transform['matrix_world']

        # Move to correct collection
        target_col = first_transform['collection']
        if first_obj.name not in target_col.objects:
            target_col.objects.link(first_obj)
        for col in list(first_obj.users_collection):
            if col != target_col:
                try:
                    col.objects.unlink(first_obj)
                except RuntimeError:
                    pass

        new_objects = [first_obj]

        # Duplicate for remaining transforms
        for transform in transforms[1:]:
            dup = first_obj.copy()
            target_col = transform['collection']
            target_col.objects.link(dup)
            dup.matrix_world = transform['matrix_world']
            new_objects.append(dup)

        # Store UAL metadata on all new objects
        asset_uuid = request.get('asset_uuid', '')
        version_group_id = request.get('version_group_id') or asset_uuid
        for obj in new_objects:
            store_ual_metadata(
                obj,
                uuid=asset_uuid,
                version_group_id=version_group_id,
                version=request.get('version', 1) or 1,
                version_label=request.get('version_label', 'v001') or 'v001',
                asset_name=request.get('asset_name', ''),
                asset_type=request.get('asset_type', 'model'),
                representation_type=request.get('representation_type', 'none') or 'none',
                imported=True,
                asset_id=request.get('asset_id') or version_group_id,
                variant_name=request.get('variant_name') or 'Base',
                link_mode=request.get('link_mode', 'INSTANCE')
            )

        # Select new objects
        select_objects(context, new_objects)
        context.view_layer.update()

        bpy.ops.ed.undo_push(message="Replace Any")

        self.report({'INFO'},
            f"Replaced {len(transforms)} object(s) with '{asset_name}'")
        client.mark_completed(file_path)

    def _handle_material_import(
        self,
        context,
        blend_file_path: str,
        usd_file_path: str,
        asset_name: str
    ) -> bool:
        """Handle material-specific import logic"""
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if blend_file_path and Path(blend_file_path).exists():
            success, material = import_material_from_blend(
                context, blend_file_path, apply_to_selection=bool(selected_meshes)
            )
            if success and material:
                if selected_meshes:
                    self.report({'INFO'}, f"Applied '{material.name}' to {len(selected_meshes)} object(s)")
                else:
                    self.report({'INFO'}, f"Imported material '{material.name}'")
            return success

        elif usd_file_path and Path(usd_file_path).exists():
            success, material = import_material_from_usd(
                context, usd_file_path, apply_to_selection=bool(selected_meshes)
            )
            if success and material:
                if selected_meshes:
                    self.report({'INFO'}, f"Applied '{material.name}' to {len(selected_meshes)} object(s)")
                else:
                    self.report({'INFO'}, f"Imported material '{material.name}'")
            return success

        self.report({'ERROR'}, f"No valid file found for material '{asset_name}'")
        return False

    def _store_asset_metadata(self, context, objects_before: set, request: dict):
        """Store UAL metadata on imported objects for version tracking"""
        context.view_layer.update()

        # Find new objects
        objects_after = set(context.scene.objects)
        new_objects = objects_after - objects_before

        # Fallback to selected objects
        if not new_objects:
            new_objects = set(context.selected_objects)

        if not new_objects:
            return

        # Extract asset info and store on each object
        asset_uuid = request.get('asset_uuid', '')
        version_group_id = request.get('version_group_id') or asset_uuid

        for obj in new_objects:
            store_ual_metadata(
                obj,
                uuid=asset_uuid,
                version_group_id=version_group_id,
                version=request.get('version', 1) or 1,
                version_label=request.get('version_label', 'v001') or 'v001',
                asset_name=request.get('asset_name', ''),
                asset_type=request.get('asset_type', 'model'),
                representation_type=request.get('representation_type', 'none') or 'none',
                imported=True,
                asset_id=request.get('asset_id') or version_group_id,
                variant_name=request.get('variant_name') or 'Base',
                link_mode=request.get('link_mode', 'APPEND')
            )


    def _process_thumbnail_request(self, context, request: dict, client):
        """Process a thumbnail regeneration request with protocol validation"""
        file_path = request.get('file_path', '')

        # Validate message against protocol schema
        try:
            validate_message(request, "regenerate_thumbnail")
        except ValidationError as e:
            # Continue processing - validation is advisory for backwards compatibility
            pass

        asset_name = request.get('asset_name', 'Unknown')
        usd_file_path = request.get('usd_file_path', '')
        thumbnail_path = request.get('thumbnail_path', '')

        try:
            if not usd_file_path or not Path(usd_file_path).exists():
                client.mark_failed(file_path, "USD file not found")
                return

            # Import USD temporarily
            bpy.ops.wm.usd_import(filepath=usd_file_path)

            if not context.selected_objects:
                client.mark_failed(file_path, "No objects imported")
                return

            # Frame objects in viewport
            view3d_area, view3d_region, _ = find_3d_viewport(context)
            if view3d_area and view3d_region:
                with context.temp_override(area=view3d_area, region=view3d_region):
                    bpy.ops.view3d.view_selected()

            # Generate thumbnail using utility
            success = generate_thumbnail(context, thumbnail_path, size=256)

            # Delete imported objects
            bpy.ops.object.delete()

            if success:
                self.report({'INFO'}, f"Regenerated thumbnail for '{asset_name}'")
                client.mark_completed(file_path)
            else:
                client.mark_failed(file_path, "Thumbnail generation failed")

        except Exception as e:
            self.report({'ERROR'}, f"Thumbnail failed for '{asset_name}': {str(e)}")
            client.mark_failed(file_path, str(e))


class UAL_OT_start_queue_listener(Operator):
    """Start the queue listener modal operator"""
    bl_idname = "ual.start_queue_listener"
    bl_label = "Start Queue Listener"
    bl_description = "Start listening for import requests from desktop app"

    _timer = None
    _is_running = False

    def modal(self, context, event):
        if event.type == 'TIMER':
            bpy.ops.ual.check_import_queue()
        return {'PASS_THROUGH'}

    def execute(self, context):
        if UAL_OT_start_queue_listener._is_running:
            return {'CANCELLED'}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)

        UAL_OT_start_queue_listener._is_running = True

        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        UAL_OT_start_queue_listener._is_running = False


class UAL_OT_stop_queue_listener(Operator):
    """Stop the queue listener"""
    bl_idname = "ual.stop_queue_listener"
    bl_label = "Stop Queue Listener"
    bl_description = "Stop listening for import requests"

    def execute(self, context):
        UAL_OT_start_queue_listener._is_running = False
        return {'FINISHED'}


# Registration
classes = [
    UAL_OT_check_import_queue,
    UAL_OT_start_queue_listener,
    UAL_OT_stop_queue_listener,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    UAL_OT_start_queue_listener._is_running = False
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_OT_check_import_queue',
    'UAL_OT_start_queue_listener',
    'UAL_OT_stop_queue_listener',
    'register',
    'unregister',
]
