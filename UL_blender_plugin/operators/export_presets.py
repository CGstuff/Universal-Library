"""
Export Presets - Save and load export settings

Provides preset management for export operations.
"""

import bpy
import json
from pathlib import Path
from bpy.types import Operator, Menu
from bpy.props import StringProperty, EnumProperty


def get_presets_dir() -> Path:
    """Get the presets directory, creating if needed"""
    presets_dir = Path(bpy.utils.user_resource('SCRIPTS')) / "presets" / "ual_export"
    presets_dir.mkdir(parents=True, exist_ok=True)
    return presets_dir


def get_preset_items(self, context):
    """Get list of available presets for enum property"""
    presets_dir = get_presets_dir()
    items = [('NONE', "Select Preset...", "")]

    for preset_file in sorted(presets_dir.glob("*.json")):
        name = preset_file.stem
        items.append((name, name, f"Load preset: {name}"))

    return items


class UAL_OT_save_export_preset(Operator):
    """Save current export settings as a preset"""
    bl_idname = "ual.save_export_preset"
    bl_label = "Save Export Preset"
    bl_description = "Save current export settings as a reusable preset"

    preset_name: StringProperty(
        name="Preset Name",
        description="Name for this preset",
        default="My Preset"
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if not self.preset_name.strip():
            self.report({'ERROR'}, "Preset name is required")
            return {'CANCELLED'}

        # Get current settings from scene properties
        scene = context.scene

        preset_data = {
            'asset_type': scene.get('ual_export_type', 'model'),
            'include_materials': scene.get('ual_export_materials', True),
            'include_animations': scene.get('ual_export_animations', True),
            'create_blend_backup': scene.get('ual_export_blend_backup', True),
            'export_selected_only': scene.get('ual_export_selected_only', True),
        }

        # Save to file
        presets_dir = get_presets_dir()
        preset_file = presets_dir / f"{self.preset_name.strip()}.json"

        try:
            with open(preset_file, 'w', encoding='utf-8') as f:
                json.dump(preset_data, f, indent=2)
            self.report({'INFO'}, f"Saved preset: {self.preset_name}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to save preset: {e}")
            return {'CANCELLED'}


class UAL_OT_load_export_preset(Operator):
    """Load export settings from a preset"""
    bl_idname = "ual.load_export_preset"
    bl_label = "Load Export Preset"
    bl_description = "Load export settings from a saved preset"

    preset_name: StringProperty(
        name="Preset",
        description="Preset to load"
    )

    def execute(self, context):
        if not self.preset_name:
            return {'CANCELLED'}

        presets_dir = get_presets_dir()
        preset_file = presets_dir / f"{self.preset_name}.json"

        if not preset_file.exists():
            self.report({'ERROR'}, f"Preset not found: {self.preset_name}")
            return {'CANCELLED'}

        try:
            with open(preset_file, 'r', encoding='utf-8') as f:
                preset_data = json.load(f)

            # Apply to scene properties
            scene = context.scene
            scene['ual_export_type'] = preset_data.get('asset_type', 'model')
            scene['ual_export_materials'] = preset_data.get('include_materials', True)
            scene['ual_export_animations'] = preset_data.get('include_animations', True)
            scene['ual_export_blend_backup'] = preset_data.get('create_blend_backup', True)
            scene['ual_export_selected_only'] = preset_data.get('export_selected_only', True)

            self.report({'INFO'}, f"Loaded preset: {self.preset_name}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load preset: {e}")
            return {'CANCELLED'}


class UAL_OT_delete_export_preset(Operator):
    """Delete an export preset"""
    bl_idname = "ual.delete_export_preset"
    bl_label = "Delete Export Preset"
    bl_description = "Delete a saved export preset"

    preset_name: StringProperty(
        name="Preset",
        description="Preset to delete"
    )

    def execute(self, context):
        if not self.preset_name:
            return {'CANCELLED'}

        presets_dir = get_presets_dir()
        preset_file = presets_dir / f"{self.preset_name}.json"

        if preset_file.exists():
            try:
                preset_file.unlink()
                self.report({'INFO'}, f"Deleted preset: {self.preset_name}")
                return {'FINISHED'}
            except Exception as e:
                self.report({'ERROR'}, f"Failed to delete preset: {e}")
                return {'CANCELLED'}

        return {'CANCELLED'}


class UAL_MT_export_presets(Menu):
    """Export presets menu"""
    bl_idname = "UAL_MT_export_presets"
    bl_label = "Export Presets"

    def draw(self, context):
        layout = self.layout

        # Save current
        layout.operator("ual.save_export_preset", text="Save Preset...", icon='ADD')

        layout.separator()

        # List presets
        presets_dir = get_presets_dir()
        preset_files = sorted(presets_dir.glob("*.json"))

        if preset_files:
            for preset_file in preset_files:
                name = preset_file.stem
                row = layout.row()
                op = row.operator("ual.load_export_preset", text=name, icon='PRESET')
                op.preset_name = name
        else:
            layout.label(text="No presets saved", icon='INFO')


# Registration
classes = [
    UAL_OT_save_export_preset,
    UAL_OT_load_export_preset,
    UAL_OT_delete_export_preset,
    UAL_MT_export_presets,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [
    'UAL_OT_save_export_preset',
    'UAL_OT_load_export_preset',
    'UAL_OT_delete_export_preset',
    'UAL_MT_export_presets',
    'register',
    'unregister',
]
