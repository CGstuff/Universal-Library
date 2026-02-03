"""
Reload Libraries Operator

Reloads all UAL-linked assets (via .current.blend proxies) to get latest versions.
"""

import bpy
from bpy.types import Operator


class UAL_OT_reload_current_assets(Operator):
    """Reload all UAL-linked assets to get latest versions"""
    bl_idname = "ual.reload_current_assets"
    bl_label = "Reload UAL Assets"
    bl_description = "Reload all assets linked via .current.blend to get latest versions"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Check if there are any UAL libraries to reload"""
        for lib in bpy.data.libraries:
            if lib.filepath and '.current.blend' in lib.filepath:
                return True
        return False

    def execute(self, context):
        """Reload all .current.blend libraries"""
        reloaded = 0
        failed = 0
        library_names = []

        for lib in bpy.data.libraries:
            if lib.filepath and '.current.blend' in lib.filepath:
                try:
                    lib.reload()
                    reloaded += 1
                    library_names.append(lib.name)
                except Exception as e:
                    failed += 1

        # Update the view layer to reflect changes
        context.view_layer.update()

        if reloaded > 0:
            self.report({'INFO'}, f"Reloaded {reloaded} UAL asset(s)")
        elif failed > 0:
            self.report({'WARNING'}, f"Failed to reload {failed} library(ies)")
        else:
            self.report({'INFO'}, "No UAL current-reference assets to reload")

        return {'FINISHED'}


class UAL_OT_reload_all_libraries(Operator):
    """Reload all external libraries in the scene"""
    bl_idname = "ual.reload_all_libraries"
    bl_label = "Reload All Libraries"
    bl_description = "Reload all external library links in the scene"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Check if there are any libraries to reload"""
        return len(bpy.data.libraries) > 0

    def execute(self, context):
        """Reload all libraries"""
        reloaded = 0
        failed = 0

        for lib in bpy.data.libraries:
            if lib.filepath:
                try:
                    lib.reload()
                    reloaded += 1
                except Exception as e:
                    failed += 1

        # Update the view layer to reflect changes
        context.view_layer.update()

        if reloaded > 0:
            self.report({'INFO'}, f"Reloaded {reloaded} library(ies)")
        elif failed > 0:
            self.report({'WARNING'}, f"Failed to reload {failed} library(ies)")
        else:
            self.report({'INFO'}, "No libraries to reload")

        return {'FINISHED'}


class UAL_OT_list_linked_libraries(Operator):
    """List all linked libraries in the scene"""
    bl_idname = "ual.list_linked_libraries"
    bl_label = "List Linked Libraries"
    bl_description = "Show all external library links in the scene"

    def execute(self, context):
        """List all linked libraries"""
        ual_libs = []
        other_libs = []

        for lib in bpy.data.libraries:
            if lib.filepath:
                if '.current.blend' in lib.filepath:
                    ual_libs.append(lib)
                else:
                    other_libs.append(lib)

        # Print to console
        if ual_libs:
            for lib in ual_libs:
                pass
        if other_libs:
            for lib in other_libs:
                pass
        if not ual_libs and not other_libs:
            pass

        total = len(ual_libs) + len(other_libs)
        self.report({'INFO'}, f"Found {len(ual_libs)} UAL, {len(other_libs)} other libraries (see console)")
        return {'FINISHED'}


# Registration
classes = [
    UAL_OT_reload_current_assets,
    UAL_OT_reload_all_libraries,
    UAL_OT_list_linked_libraries,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_OT_reload_current_assets',
    'UAL_OT_reload_all_libraries',
    'UAL_OT_list_linked_libraries',
    'register',
    'unregister',
]
