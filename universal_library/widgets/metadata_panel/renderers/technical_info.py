"""
TechnicalInfoRenderer - Category-specific technical metadata.

Supports both hardcoded fields and dynamic fields from MetadataService.
"""

import json
from typing import Dict, Any, List, Optional
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt

from ..utils import format_number


class TechnicalInfoRenderer:
    """
    Renders technical info based on asset category.

    Categories:
    - mesh: polygon count, materials, skeleton, animations
    - material: material count, texture maps, resolution
    - rig: bone count, facial rig, controls
    - animation: frame range, fps, duration, loop
    - light: light type, count
    - camera: camera type, focal length
    - collection: contents summary, nested collections

    Now supports reading field definitions from MetadataService
    for dynamic field visibility.
    """

    def __init__(self, labels: Dict[str, QLabel]):
        """
        Initialize with label references.

        Args:
            labels: Dict mapping field names to QLabel widgets
        """
        self._labels = labels
        self._metadata_service = None  # Lazy load

    def _get_metadata_service(self):
        """Lazy load MetadataService to avoid circular imports."""
        if self._metadata_service is None:
            try:
                from ....services.metadata_service import get_metadata_service
                self._metadata_service = get_metadata_service()
            except ImportError:
                pass
        return self._metadata_service

    def render(self, asset: Dict[str, Any], category: str):
        """
        Update technical info display based on asset category.

        Args:
            asset: Asset data dict
            category: Asset category (mesh, material, rig, etc.)
        """
        # Hide all technical labels first
        for name, label in self._labels.items():
            if name != 'filesize':
                label.hide()

        # Show file size always
        file_size = asset.get('file_size_mb', 0)
        if 'filesize' in self._labels:
            self._labels['filesize'].setText(
                f"File Size: {file_size:.2f} MB" if file_size else "File Size: -"
            )
            self._labels['filesize'].show()

        # Render category-specific info
        render_method = getattr(self, f'_render_{category}', None)
        if render_method:
            render_method(asset)

    def _render_mesh(self, asset: Dict[str, Any]):
        """Render mesh category info."""
        polygon_count = asset.get('polygon_count', 0)
        if 'polygons' in self._labels:
            self._labels['polygons'].setText(f"Polygons: {format_number(polygon_count)}")
            self._labels['polygons'].show()

        material_count = asset.get('material_count', 0)
        if 'materials' in self._labels:
            self._labels['materials'].setText(
                f"Materials: {material_count}" if material_count else "Materials: -"
            )
            self._labels['materials'].show()

        vertex_group_count = asset.get('vertex_group_count', 0)
        if vertex_group_count and vertex_group_count > 0 and 'vertex_groups' in self._labels:
            self._labels['vertex_groups'].setText(f"Vertex Groups: {vertex_group_count}")
            self._labels['vertex_groups'].show()

        shape_key_count = asset.get('shape_key_count', 0)
        if shape_key_count and shape_key_count > 0 and 'shape_keys' in self._labels:
            self._labels['shape_keys'].setText(f"Shape Keys: {shape_key_count}")
            self._labels['shape_keys'].show()

        bone_count = asset.get('bone_count', 0)
        if bone_count and bone_count > 0 and 'bone_count' in self._labels:
            self._labels['bone_count'].setText(f"Bones: {format_number(bone_count)}")
            self._labels['bone_count'].show()

        has_skeleton = asset.get('has_skeleton', 0)
        if 'skeleton' in self._labels:
            self._labels['skeleton'].setText(f"Skeleton: {'Yes' if has_skeleton else 'No'}")
            self._labels['skeleton'].show()

        has_animations = asset.get('has_animations', 0)
        if 'animations' in self._labels:
            self._labels['animations'].setText(f"Animations: {'Yes' if has_animations else 'No'}")
            self._labels['animations'].show()

        if has_skeleton and 'facial_rig' in self._labels:
            has_facial = asset.get('has_facial_rig', 0)
            self._labels['facial_rig'].setText(f"Facial Rig: {'Yes' if has_facial else 'No'}")
            self._labels['facial_rig'].show()

    def _render_material(self, asset: Dict[str, Any]):
        """Render material category info."""
        material_count = asset.get('material_count', 0)
        if 'materials' in self._labels:
            self._labels['materials'].setText(
                f"Materials: {material_count}" if material_count else "Materials: -"
            )
            self._labels['materials'].show()

        texture_maps = asset.get('texture_maps')
        if 'texture_maps' in self._labels:
            if texture_maps:
                try:
                    maps = json.loads(texture_maps) if isinstance(texture_maps, str) else texture_maps
                    self._labels['texture_maps'].setText(f"Texture Maps: {', '.join(maps)}")
                except (json.JSONDecodeError, TypeError):
                    self._labels['texture_maps'].setText(f"Texture Maps: {texture_maps}")
            else:
                self._labels['texture_maps'].setText("Texture Maps: -")
            self._labels['texture_maps'].show()

        texture_res = asset.get('texture_resolution', '-')
        if 'texture_res' in self._labels:
            self._labels['texture_res'].setText(f"Resolution: {texture_res}")
            self._labels['texture_res'].show()

    def _render_rig(self, asset: Dict[str, Any]):
        """Render rig category info."""
        bone_count = asset.get('bone_count', 0)
        if 'bone_count' in self._labels:
            self._labels['bone_count'].setText(f"Bones: {format_number(bone_count)}")
            self._labels['bone_count'].show()

        has_facial = asset.get('has_facial_rig', 0)
        if 'facial_rig' in self._labels:
            self._labels['facial_rig'].setText(f"Facial Rig: {'Yes' if has_facial else 'No'}")
            self._labels['facial_rig'].show()

        control_count = asset.get('control_count', 0)
        if control_count and control_count > 0 and 'control_count' in self._labels:
            self._labels['control_count'].setText(f"Controls: {format_number(control_count)}")
            self._labels['control_count'].show()

    def _render_animation(self, asset: Dict[str, Any]):
        """Render animation category info."""
        frame_start = asset.get('frame_start', 0)
        frame_end = asset.get('frame_end', 0)

        if 'frame_range' in self._labels:
            if frame_start is not None and frame_end is not None:
                self._labels['frame_range'].setText(f"Frame Range: {frame_start} - {frame_end}")
            else:
                self._labels['frame_range'].setText("Frame Range: -")
            self._labels['frame_range'].show()

        fps = asset.get('frame_rate', 0)
        if 'fps' in self._labels:
            self._labels['fps'].setText(f"Frame Rate: {fps:.0f} fps" if fps else "Frame Rate: -")
            self._labels['fps'].show()

        if 'duration' in self._labels:
            duration = self._format_duration(frame_start, frame_end, fps)
            self._labels['duration'].setText(f"Duration: {duration}")
            self._labels['duration'].show()

        is_loop = asset.get('is_loop', 0)
        if 'loop' in self._labels:
            self._labels['loop'].setText(f"Loop: {'Yes' if is_loop else 'No'}")
            self._labels['loop'].show()

    def _render_light(self, asset: Dict[str, Any]):
        """Render light category info."""
        light_type = asset.get('light_type', '-')
        if 'light_type' in self._labels:
            self._labels['light_type'].setText(
                f"Light Type: {light_type.capitalize() if light_type else '-'}"
            )
            self._labels['light_type'].show()

        light_count = asset.get('light_count', 1)
        if light_count and light_count > 1 and 'light_count' in self._labels:
            self._labels['light_count'].setText(f"Light Count: {light_count}")
            self._labels['light_count'].show()

        light_power = asset.get('light_power')
        if light_power is not None and 'light_power' in self._labels:
            self._labels['light_power'].setText(f"Power: {light_power:.0f} W")
            self._labels['light_power'].show()

        light_color = asset.get('light_color')
        if light_color and 'light_color' in self._labels:
            label = self._labels['light_color']
            label.setTextFormat(Qt.TextFormat.RichText)
            if light_color.startswith('#'):
                # Color swatch using background-color on non-breaking spaces
                label.setText(
                    f'Color: '
                    f'<span style="background-color:{light_color};">'
                    f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>'
                    f' {light_color}'
                )
            else:
                label.setText(f"Color: {light_color}")
            label.show()

        light_shadow = asset.get('light_shadow')
        if light_shadow is not None and 'light_shadow' in self._labels:
            self._labels['light_shadow'].setText(f"Shadow: {'Yes' if light_shadow else 'No'}")
            self._labels['light_shadow'].show()

        light_spot_size = asset.get('light_spot_size')
        if light_spot_size is not None and light_type == 'spot' and 'light_spot_size' in self._labels:
            self._labels['light_spot_size'].setText(f"Spot Size: {light_spot_size:.0f}\u00b0")
            self._labels['light_spot_size'].show()

        light_area_shape = asset.get('light_area_shape')
        if light_area_shape and light_type == 'area' and 'light_area_shape' in self._labels:
            self._labels['light_area_shape'].setText(f"Area Shape: {light_area_shape.capitalize()}")
            self._labels['light_area_shape'].show()

    def _render_camera(self, asset: Dict[str, Any]):
        """Render camera category info."""
        camera_type = asset.get('camera_type', '-')
        if 'camera_type' in self._labels:
            self._labels['camera_type'].setText(
                f"Camera Type: {camera_type.capitalize() if camera_type else '-'}"
            )
            self._labels['camera_type'].show()

        # For ortho cameras, show ortho scale instead of focal length
        if camera_type == 'ortho':
            ortho_scale = asset.get('camera_ortho_scale')
            if ortho_scale is not None and 'camera_ortho_scale' in self._labels:
                self._labels['camera_ortho_scale'].setText(f"Ortho Scale: {ortho_scale:.2f}")
                self._labels['camera_ortho_scale'].show()
        else:
            focal_length = asset.get('focal_length', 0)
            if focal_length and focal_length > 0 and 'focal_length' in self._labels:
                self._labels['focal_length'].setText(f"Focal Length: {focal_length:.0f}mm")
                self._labels['focal_length'].show()

        sensor_width = asset.get('camera_sensor_width')
        if sensor_width is not None and 'camera_sensor' in self._labels:
            self._labels['camera_sensor'].setText(f"Sensor: {sensor_width:.0f}mm")
            self._labels['camera_sensor'].show()

        dof_enabled = asset.get('camera_dof_enabled')
        if dof_enabled is not None and 'camera_dof' in self._labels:
            self._labels['camera_dof'].setText(f"DOF: {'Yes' if dof_enabled else 'No'}")
            self._labels['camera_dof'].show()

    def _render_grease_pencil(self, asset: Dict[str, Any]):
        """Render grease pencil category info."""
        layer_count = asset.get('layer_count', 0)
        if layer_count and 'gp_layers' in self._labels:
            self._labels['gp_layers'].setText(f"Layers: {layer_count}")
            self._labels['gp_layers'].show()

        stroke_count = asset.get('stroke_count', 0)
        if stroke_count and 'gp_strokes' in self._labels:
            self._labels['gp_strokes'].setText(f"Strokes: {format_number(stroke_count)}")
            self._labels['gp_strokes'].show()

        material_count = asset.get('material_count', 0)
        if 'materials' in self._labels:
            self._labels['materials'].setText(
                f"Materials: {material_count}" if material_count else "Materials: -"
            )
            self._labels['materials'].show()

        frame_count = asset.get('frame_count', 0)
        if frame_count and 'gp_frames' in self._labels:
            self._labels['gp_frames'].setText(f"Frames: {frame_count}")
            self._labels['gp_frames'].show()

        has_animations = asset.get('has_animations', 0)
        if 'animations' in self._labels:
            self._labels['animations'].setText(f"Animations: {'Yes' if has_animations else 'No'}")
            self._labels['animations'].show()

    def _render_curve(self, asset: Dict[str, Any]):
        """Render curve category info."""
        curve_type = asset.get('curve_type')
        if curve_type and 'curve_type' in self._labels:
            self._labels['curve_type'].setText(f"Curve Type: {curve_type.capitalize()}")
            self._labels['curve_type'].show()

        point_count = asset.get('point_count', 0)
        if point_count and 'curve_points' in self._labels:
            self._labels['curve_points'].setText(f"Points: {format_number(point_count)}")
            self._labels['curve_points'].show()

        spline_count = asset.get('spline_count', 0)
        if spline_count and 'curve_splines' in self._labels:
            self._labels['curve_splines'].setText(f"Splines: {spline_count}")
            self._labels['curve_splines'].show()

        material_count = asset.get('material_count', 0)
        if 'materials' in self._labels:
            self._labels['materials'].setText(
                f"Materials: {material_count}" if material_count else "Materials: -"
            )
            self._labels['materials'].show()

    def _render_scene(self, asset: Dict[str, Any]):
        """Render scene category info."""
        scene_name = asset.get('scene_name', '')
        if scene_name and 'scene_name' in self._labels:
            self._labels['scene_name'].setText(f"Scene: {scene_name}")
            self._labels['scene_name'].show()

        object_count = asset.get('object_count', 0)
        if 'scene_objects' in self._labels:
            self._labels['scene_objects'].setText(
                f"Objects: {object_count}" if object_count else "Objects: -"
            )
            self._labels['scene_objects'].show()

        collection_count = asset.get('collection_count', 0)
        if collection_count and 'scene_collections' in self._labels:
            self._labels['scene_collections'].setText(f"Collections: {collection_count}")
            self._labels['scene_collections'].show()

        polygon_count = asset.get('polygon_count', 0)
        if polygon_count and polygon_count > 0 and 'polygons' in self._labels:
            self._labels['polygons'].setText(f"Polygons: {format_number(polygon_count)}")
            self._labels['polygons'].show()

        render_engine = asset.get('render_engine', '')
        if render_engine and 'scene_render_engine' in self._labels:
            # Format engine name nicely
            engine_display = render_engine.replace('blender_', '').replace('_', ' ').title()
            self._labels['scene_render_engine'].setText(f"Render Engine: {engine_display}")
            self._labels['scene_render_engine'].show()

        res_x = asset.get('resolution_x', 0)
        res_y = asset.get('resolution_y', 0)
        if res_x and res_y and 'scene_resolution' in self._labels:
            self._labels['scene_resolution'].setText(f"Resolution: {res_x}x{res_y}")
            self._labels['scene_resolution'].show()

        world_name = asset.get('world_name', '')
        if world_name and 'scene_world' in self._labels:
            self._labels['scene_world'].setText(f"World: {world_name}")
            self._labels['scene_world'].show()

        # Frame range if available
        frame_start = asset.get('frame_start')
        frame_end = asset.get('frame_end')
        if frame_start is not None and frame_end is not None and 'frame_range' in self._labels:
            self._labels['frame_range'].setText(f"Frame Range: {frame_start} - {frame_end}")
            self._labels['frame_range'].show()

        fps = asset.get('frame_rate', 0)
        if fps and 'fps' in self._labels:
            self._labels['fps'].setText(f"Frame Rate: {fps:.0f} fps")
            self._labels['fps'].show()

    def _render_collection(self, asset: Dict[str, Any]):
        """Render collection category info."""
        # Collection name
        collection_name = asset.get('collection_name', '')
        if collection_name and 'collection_name' in self._labels:
            self._labels['collection_name'].setText(f"Collection: {collection_name}")
            self._labels['collection_name'].show()

        # Contents summary
        mesh_count = asset.get('mesh_count', 0) or 0
        light_count = asset.get('light_count', 0) or 0
        camera_count = asset.get('camera_count', 0) or 0
        armature_count = asset.get('armature_count', 0) or 0
        gp_count = asset.get('gp_count', 0) or 0
        curve_count = asset.get('curve_count', 0) or 0
        empty_count = asset.get('empty_count', 0) or 0

        contents_parts = []
        if mesh_count > 0:
            contents_parts.append(f"{mesh_count} Mesh{'es' if mesh_count != 1 else ''}")
        if light_count > 0:
            contents_parts.append(f"{light_count} Light{'s' if light_count != 1 else ''}")
        if camera_count > 0:
            contents_parts.append(f"{camera_count} Camera{'s' if camera_count != 1 else ''}")
        if armature_count > 0:
            contents_parts.append(f"{armature_count} Armature{'s' if armature_count != 1 else ''}")
        if gp_count > 0:
            contents_parts.append(f"{gp_count} GP{'s' if gp_count != 1 else ''}")
        if curve_count > 0:
            contents_parts.append(f"{curve_count} Curve{'s' if curve_count != 1 else ''}")
        if empty_count > 0:
            contents_parts.append(f"{empty_count} Empty" + ("" if empty_count == 1 else " objects"))

        if 'contents' in self._labels:
            if contents_parts:
                separator = ' \u00b7 '
                self._labels['contents'].setText(f"Contents: {separator.join(contents_parts)}")
            else:
                self._labels['contents'].setText("Contents: Empty")
            self._labels['contents'].show()

        # Nested collections
        has_nested = asset.get('has_nested_collections', 0)
        nested_count = asset.get('nested_collection_count', 0) or 0
        if has_nested and nested_count > 0 and 'nested_collections' in self._labels:
            self._labels['nested_collections'].setText(f"Nested Collections: {nested_count}")
            self._labels['nested_collections'].show()

        # Mesh breakdown if collection has meshes
        if mesh_count > 0:
            polygon_count = asset.get('polygon_count', 0)
            if polygon_count and polygon_count > 0 and 'polygons' in self._labels:
                self._labels['polygons'].setText(f"Polygons: {format_number(polygon_count)}")
                self._labels['polygons'].show()

            material_count = asset.get('material_count', 0)
            if material_count and material_count > 0 and 'materials' in self._labels:
                self._labels['materials'].setText(f"Materials: {material_count}")
                self._labels['materials'].show()

            has_skeleton = asset.get('has_skeleton', 0)
            if has_skeleton and 'skeleton' in self._labels:
                self._labels['skeleton'].setText("Skeleton: Yes")
                self._labels['skeleton'].show()

                bone_count = asset.get('bone_count', 0)
                if bone_count and bone_count > 0 and 'bone_count' in self._labels:
                    self._labels['bone_count'].setText(f"Bones: {format_number(bone_count)}")
                    self._labels['bone_count'].show()

        # Light info breakdown
        if light_count > 0:
            light_type = asset.get('light_type', '')
            if light_type and 'light_type' in self._labels:
                self._labels['light_type'].setText(f"Light Type: {light_type.capitalize()}")
                self._labels['light_type'].show()

        # Camera info breakdown
        if camera_count > 0:
            camera_type = asset.get('camera_type', '')
            if camera_type and 'camera_type' in self._labels:
                self._labels['camera_type'].setText(f"Camera Type: {camera_type.capitalize()}")
                self._labels['camera_type'].show()

            focal_length = asset.get('focal_length', 0)
            if focal_length and focal_length > 0 and 'focal_length' in self._labels:
                self._labels['focal_length'].setText(f"Focal Length: {focal_length:.0f}mm")
                self._labels['focal_length'].show()

    def _format_duration(self, frame_start: int, frame_end: int, fps: float) -> str:
        """Calculate and format duration from frame range and fps."""
        if not fps or fps <= 0:
            return "-"
        frames = (frame_end or 0) - (frame_start or 0)
        if frames <= 0:
            return "-"
        seconds = frames / fps
        return f"{seconds:.1f} sec"

    def clear(self):
        """Hide all technical labels."""
        for label in self._labels.values():
            label.setText("-")
            label.hide()

        if 'filesize' in self._labels:
            self._labels['filesize'].setText("File Size: -")


__all__ = ['TechnicalInfoRenderer']
