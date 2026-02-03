"""
Metadata Collector - Collects extended metadata from Blender objects

Gathers context-sensitive metadata based on asset type:
- Mesh: polygon count, materials, skeleton, animations
- Rig: bone count, facial rig detection, control count
- Animation: frame range, fps, loop detection
- Material: texture maps, resolution
- Light: type, count
- Camera: type, focal length
"""

import bpy
from typing import Dict, Any, List, Optional, Set


def collect_mesh_metadata(objects: List[bpy.types.Object]) -> Dict[str, Any]:
    """
    Collect metadata from mesh objects.

    Args:
        objects: List of Blender objects to analyze

    Returns:
        Dict with polygon_count, material_count, has_skeleton, has_animations,
        bone_count, has_facial_rig
    """
    total_polygons = 0
    materials: Set[str] = set()
    has_skeleton = False
    has_animations = False
    bone_count = 0
    has_facial_rig = False
    vertex_group_count = 0
    shape_key_count = 0

    for obj in objects:
        # Count polygons from mesh data
        if obj.type == 'MESH' and obj.data:
            mesh = obj.data
            total_polygons += len(mesh.polygons)

            # Collect materials
            for slot in obj.material_slots:
                if slot.material:
                    materials.add(slot.material.name)

            # Count vertex groups
            vertex_group_count += len(obj.vertex_groups)

            # Count shape keys
            if obj.data.shape_keys and obj.data.shape_keys.key_blocks:
                shape_key_count += len(obj.data.shape_keys.key_blocks)

        # Check for armature modifier (skeleton)
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE' and mod.object:
                has_skeleton = True
                armature = mod.object
                if armature.type == 'ARMATURE' and armature.data:
                    bone_count = max(bone_count, len(armature.data.bones))
                    # Check for facial rig (bones with face-related names)
                    has_facial_rig = has_facial_rig or _detect_facial_rig(armature.data.bones)

        # Check for animations
        if obj.animation_data and obj.animation_data.action:
            has_animations = True

    # Also check if any selected object IS an armature
    for obj in objects:
        if obj.type == 'ARMATURE' and obj.data:
            has_skeleton = True
            bone_count = max(bone_count, len(obj.data.bones))
            has_facial_rig = has_facial_rig or _detect_facial_rig(obj.data.bones)
            if obj.animation_data and obj.animation_data.action:
                has_animations = True

    return {
        'polygon_count': total_polygons,
        'material_count': len(materials),
        'has_skeleton': 1 if has_skeleton else 0,
        'has_animations': 1 if has_animations else 0,
        'bone_count': bone_count if bone_count > 0 else None,
        'has_facial_rig': 1 if has_facial_rig else 0,
        'vertex_group_count': vertex_group_count if vertex_group_count > 0 else None,
        'shape_key_count': shape_key_count if shape_key_count > 0 else None,
    }


def _detect_facial_rig(bones) -> bool:
    """Detect if bones contain facial rig elements."""
    facial_keywords = [
        'face', 'jaw', 'lip', 'mouth', 'eye', 'brow', 'nose', 'cheek',
        'tongue', 'teeth', 'eyelid', 'eyebrow', 'facial'
    ]
    for bone in bones:
        bone_name = bone.name.lower()
        for keyword in facial_keywords:
            if keyword in bone_name:
                return True
    return False


def collect_rig_metadata(armature: bpy.types.Object) -> Dict[str, Any]:
    """
    Collect metadata from armature/rig objects.

    Args:
        armature: Blender armature object

    Returns:
        Dict with bone_count, has_facial_rig, control_count
    """
    if not armature or armature.type != 'ARMATURE' or not armature.data:
        return {
            'bone_count': 0,
            'has_facial_rig': 0,
            'control_count': 0,
        }

    bones = armature.data.bones
    bone_count = len(bones)
    has_facial_rig = _detect_facial_rig(bones)

    # Count control bones (bones that are likely controls, not deform bones)
    control_count = 0
    for bone in bones:
        # Control bones often have specific naming conventions
        name_lower = bone.name.lower()
        if any(ctrl in name_lower for ctrl in ['ctrl', 'control', 'ik', 'fk', 'pole', 'target']):
            control_count += 1
        # Or bones that are not deform bones
        elif not bone.use_deform:
            control_count += 1

    return {
        'bone_count': bone_count,
        'has_facial_rig': 1 if has_facial_rig else 0,
        'control_count': control_count if control_count > 0 else None,
    }


def collect_animation_metadata(scene: bpy.types.Scene = None) -> Dict[str, Any]:
    """
    Collect animation metadata from scene.

    Args:
        scene: Blender scene (defaults to current scene)

    Returns:
        Dict with frame_start, frame_end, frame_rate, is_loop
    """
    if scene is None:
        scene = bpy.context.scene

    frame_start = scene.frame_start
    frame_end = scene.frame_end
    frame_rate = scene.render.fps

    # Try to detect if animation is a loop
    # Check if first and last keyframes are similar
    is_loop = _detect_animation_loop(scene)

    return {
        'frame_start': frame_start,
        'frame_end': frame_end,
        'frame_rate': float(frame_rate),
        'is_loop': 1 if is_loop else 0,
    }


def _detect_animation_loop(scene: bpy.types.Scene) -> bool:
    """
    Attempt to detect if animation is a loop.

    Checks if the animation has cyclic modifiers or if
    first/last frame values are similar.
    """
    # Check active action for cyclic modifiers
    for obj in scene.objects:
        if obj.animation_data and obj.animation_data.action:
            action = obj.animation_data.action
            for fcurve in action.fcurves:
                for mod in fcurve.modifiers:
                    if mod.type == 'CYCLES':
                        return True
    return False


def collect_material_metadata(materials: List[bpy.types.Material]) -> Dict[str, Any]:
    """
    Collect metadata from materials.

    Args:
        materials: List of Blender materials

    Returns:
        Dict with material_count, texture_maps, texture_resolution
    """
    texture_maps: Set[str] = set()
    max_resolution = 0
    resolutions: Set[int] = set()

    for mat in materials:
        if not mat or not mat.use_nodes:
            continue

        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                image = node.image

                # Detect texture map type from node name or socket connections
                map_type = _detect_texture_map_type(node, mat.node_tree)
                if map_type:
                    texture_maps.add(map_type)

                # Track resolution
                if image.size[0] > 0:
                    res = max(image.size[0], image.size[1])
                    resolutions.add(res)
                    max_resolution = max(max_resolution, res)

    # Format resolution string
    if len(resolutions) == 1:
        res = list(resolutions)[0]
        texture_resolution = f"{res}x{res}"
    elif len(resolutions) > 1:
        texture_resolution = "Mixed"
    else:
        texture_resolution = None

    return {
        'material_count': len(materials),
        'texture_maps': list(texture_maps) if texture_maps else None,
        'texture_resolution': texture_resolution,
    }


def _detect_texture_map_type(image_node, node_tree) -> Optional[str]:
    """Detect the type of texture map based on node connections and naming."""
    # Check node name first
    name_lower = image_node.name.lower()
    label_lower = (image_node.label or '').lower()
    image_name = (image_node.image.name if image_node.image else '').lower()

    # Common naming patterns for texture maps
    map_patterns = {
        'albedo': ['albedo', 'diffuse', 'base_color', 'basecolor', 'color', 'col'],
        'normal': ['normal', 'norm', 'nrm', 'bump'],
        'roughness': ['roughness', 'rough', 'rgh'],
        'metallic': ['metallic', 'metal', 'mtl'],
        'ao': ['ao', 'ambient_occlusion', 'occlusion', 'occ'],
        'emission': ['emission', 'emissive', 'emit', 'glow'],
        'height': ['height', 'displacement', 'disp'],
        'opacity': ['opacity', 'alpha', 'transparency'],
    }

    combined_name = f"{name_lower} {label_lower} {image_name}"

    for map_type, patterns in map_patterns.items():
        for pattern in patterns:
            if pattern in combined_name:
                return map_type

    # If no match found, try to detect from socket connections
    for link in node_tree.links:
        if link.from_node == image_node:
            socket_name = link.to_socket.name.lower()
            if 'color' in socket_name or 'base' in socket_name:
                return 'albedo'
            elif 'normal' in socket_name:
                return 'normal'
            elif 'rough' in socket_name:
                return 'roughness'
            elif 'metal' in socket_name:
                return 'metallic'

    return None


def collect_light_metadata(lights: List[bpy.types.Object]) -> Dict[str, Any]:
    """
    Collect metadata from light objects.

    Args:
        lights: List of Blender light objects

    Returns:
        Dict with light_type, light_count
    """
    if not lights:
        return {
            'light_type': None,
            'light_count': 0,
        }

    light_types: Set[str] = set()
    powers: List[float] = []
    colors: List[str] = []
    shadow_values: List[bool] = []
    spot_size = None
    area_shape = None

    for obj in lights:
        if obj.type == 'LIGHT' and obj.data:
            light_data = obj.data
            light_types.add(light_data.type.lower())

            # Collect power (energy)
            powers.append(light_data.energy)

            # Collect color as hex string
            r, g, b = light_data.color[0], light_data.color[1], light_data.color[2]
            hex_color = f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"
            colors.append(hex_color)

            # Collect shadow
            shadow_values.append(light_data.use_shadow)

            # Spot-specific: spot_size (radians to degrees)
            if light_data.type == 'SPOT' and hasattr(light_data, 'spot_size'):
                import math
                spot_size = math.degrees(light_data.spot_size)

            # Area-specific: shape
            if light_data.type == 'AREA' and hasattr(light_data, 'shape'):
                area_shape = light_data.shape.lower()

    # If all same type, use that; otherwise "mixed"
    if len(light_types) == 1:
        light_type = list(light_types)[0]
    elif len(light_types) > 1:
        light_type = "mixed"
    else:
        light_type = None

    # Power: use first value, or None
    light_power = powers[0] if powers else None

    # Color: use first value if all same, "Mixed" if different
    if colors:
        light_color = colors[0] if len(set(colors)) == 1 else "Mixed"
    else:
        light_color = None

    # Shadow: use first value
    light_shadow = 1 if (shadow_values and shadow_values[0]) else 0

    return {
        'light_type': light_type,
        'light_count': len(lights) if len(lights) > 1 else None,
        'light_power': light_power,
        'light_color': light_color,
        'light_shadow': light_shadow,
        'light_spot_size': spot_size,
        'light_area_shape': area_shape,
    }


def collect_camera_metadata(cameras: List[bpy.types.Object]) -> Dict[str, Any]:
    """
    Collect metadata from camera objects.

    Args:
        cameras: List of Blender camera objects

    Returns:
        Dict with camera_type, focal_length
    """
    if not cameras:
        return {
            'camera_type': None,
            'focal_length': None,
        }

    # Use first camera for primary metadata
    cam_obj = cameras[0]
    if cam_obj.type != 'CAMERA' or not cam_obj.data:
        return {
            'camera_type': None,
            'focal_length': None,
        }

    cam_data = cam_obj.data

    # Camera type
    camera_type = cam_data.type.lower()  # 'PERSP', 'ORTHO', 'PANO'

    # Focal length (only for perspective cameras)
    focal_length = None
    if cam_data.type == 'PERSP':
        focal_length = cam_data.lens

    # Sensor width (mm)
    camera_sensor_width = cam_data.sensor_width

    # Clip range
    camera_clip_start = cam_data.clip_start
    camera_clip_end = cam_data.clip_end

    # Depth of field
    camera_dof_enabled = 1 if cam_data.dof.use_dof else 0

    # Ortho scale (only for orthographic cameras)
    camera_ortho_scale = None
    if cam_data.type == 'ORTHO':
        camera_ortho_scale = cam_data.ortho_scale

    return {
        'camera_type': camera_type,
        'focal_length': focal_length,
        'camera_sensor_width': camera_sensor_width,
        'camera_clip_start': camera_clip_start,
        'camera_clip_end': camera_clip_end,
        'camera_dof_enabled': camera_dof_enabled,
        'camera_ortho_scale': camera_ortho_scale,
    }


def collect_grease_pencil_metadata(objects: List[bpy.types.Object]) -> Dict[str, Any]:
    """
    Collect metadata from Grease Pencil objects.

    Args:
        objects: List of Blender objects to analyze

    Returns:
        Dict with layer_count, stroke_count, material_count, frame_count, has_animations
    """
    total_layers = 0
    total_strokes = 0
    materials: Set[str] = set()
    has_animations = False
    frame_count = 0

    for obj in objects:
        if obj.type in ('GPENCIL', 'GREASEPENCIL') and obj.data:
            gp_data = obj.data

            # Blender 4.3+/5.0 uses new Grease Pencil v3 API
            if hasattr(gp_data, 'layers'):
                total_layers += len(gp_data.layers)

                # Count strokes across all layers/frames
                for layer in gp_data.layers:
                    if hasattr(layer, 'frames'):
                        frame_count = max(frame_count, len(layer.frames))
                        for frame in layer.frames:
                            if hasattr(frame, 'strokes'):
                                total_strokes += len(frame.strokes)

            # Collect materials
            if hasattr(obj, 'material_slots'):
                for slot in obj.material_slots:
                    if slot.material:
                        materials.add(slot.material.name)

            # Check for animations
            if obj.animation_data and obj.animation_data.action:
                has_animations = True

    return {
        'layer_count': total_layers if total_layers > 0 else None,
        'stroke_count': total_strokes if total_strokes > 0 else None,
        'material_count': len(materials),
        'frame_count': frame_count if frame_count > 0 else None,
        'has_animations': 1 if has_animations else 0,
    }


def collect_curve_metadata(objects: List[bpy.types.Object]) -> Dict[str, Any]:
    """
    Collect metadata from curve objects.

    Args:
        objects: List of Blender objects to analyze

    Returns:
        Dict with curve_type, point_count, spline_count, material_count
    """
    total_points = 0
    total_splines = 0
    curve_types: Set[str] = set()
    materials: Set[str] = set()

    for obj in objects:
        if obj.type in ('CURVE', 'SURFACE') and obj.data:
            curve_data = obj.data

            # Count splines and points
            if hasattr(curve_data, 'splines'):
                for spline in curve_data.splines:
                    total_splines += 1
                    spline_type = spline.type.lower()
                    curve_types.add(spline_type)

                    if spline_type == 'BEZIER'.lower():
                        total_points += len(spline.bezier_points)
                    else:
                        total_points += len(spline.points)

            # Collect materials
            if hasattr(obj, 'material_slots'):
                for slot in obj.material_slots:
                    if slot.material:
                        materials.add(slot.material.name)

        elif obj.type == 'CURVES' and obj.data:
            # Geometry nodes curves (Blender 3.3+)
            curve_types.add('hair')
            if hasattr(obj.data, 'curves'):
                total_splines += len(obj.data.curves)
                if hasattr(obj.data, 'points'):
                    total_points += len(obj.data.points)

            if hasattr(obj, 'material_slots'):
                for slot in obj.material_slots:
                    if slot.material:
                        materials.add(slot.material.name)

    # Determine curve type string
    if len(curve_types) == 0:
        curve_type = None
    elif len(curve_types) == 1:
        curve_type = list(curve_types)[0]
    else:
        curve_type = 'mixed'

    return {
        'curve_type': curve_type,
        'point_count': total_points if total_points > 0 else None,
        'spline_count': total_splines if total_splines > 0 else None,
        'material_count': len(materials),
    }


def collect_scene_metadata(scene: bpy.types.Scene) -> Dict[str, Any]:
    """
    Collect metadata from a Blender scene.

    Args:
        scene: Blender scene object

    Returns:
        Dict with object_count, collection_count, polygon_count, render_engine,
        resolution_x, resolution_y, frame_start, frame_end, frame_rate, world_name
    """
    # Count objects
    object_count = len(scene.objects)

    # Count collections (including nested)
    def count_collections(collection):
        count = len(collection.children)
        for child in collection.children:
            count += count_collections(child)
        return count

    collection_count = count_collections(scene.collection)

    # Count total polygons
    total_polygons = 0
    for obj in scene.objects:
        if obj.type == 'MESH' and obj.data:
            total_polygons += len(obj.data.polygons)

    # Render settings
    render_engine = scene.render.engine.lower()
    resolution_x = scene.render.resolution_x
    resolution_y = scene.render.resolution_y
    frame_start = scene.frame_start
    frame_end = scene.frame_end
    frame_rate = float(scene.render.fps)

    # World
    world_name = scene.world.name if scene.world else None

    return {
        'scene_name': scene.name,
        'object_count': object_count,
        'collection_count': collection_count if collection_count > 0 else None,
        'polygon_count': total_polygons,
        'render_engine': render_engine,
        'resolution_x': resolution_x,
        'resolution_y': resolution_y,
        'frame_start': frame_start,
        'frame_end': frame_end,
        'frame_rate': frame_rate,
        'world_name': world_name,
    }


def _get_all_collection_objects(collection: bpy.types.Collection) -> List[bpy.types.Object]:
    """
    Recursively get all objects from a collection and its nested children.

    Args:
        collection: Blender Collection object

    Returns:
        List of all objects in collection hierarchy
    """
    objects = list(collection.objects)

    for child_col in collection.children:
        objects.extend(_get_all_collection_objects(child_col))

    return objects


def _get_nested_collections(collection: bpy.types.Collection) -> List[bpy.types.Collection]:
    """
    Get all nested child collections recursively.

    Args:
        collection: Blender Collection object

    Returns:
        List of all nested child collections
    """
    nested = []
    for child_col in collection.children:
        nested.append(child_col)
        nested.extend(_get_nested_collections(child_col))
    return nested


def collect_collection_metadata(collection: bpy.types.Collection) -> Dict[str, Any]:
    """
    Collect metadata from a Blender Collection.

    Recursively gathers all objects including nested collections and
    combines mesh, light, camera, and rig metadata.

    Args:
        collection: Blender Collection object

    Returns:
        Dict with object counts, collection info, and type-specific metadata
    """
    all_objects = _get_all_collection_objects(collection)
    nested_collections = _get_nested_collections(collection)

    # Categorize objects
    meshes = [obj for obj in all_objects if obj.type == 'MESH']
    armatures = [obj for obj in all_objects if obj.type == 'ARMATURE']
    lights = [obj for obj in all_objects if obj.type == 'LIGHT']
    cameras = [obj for obj in all_objects if obj.type == 'CAMERA']
    gp_objects = [obj for obj in all_objects if obj.type in ('GPENCIL', 'GREASEPENCIL')]
    curve_objects = [obj for obj in all_objects if obj.type in ('CURVE', 'CURVES', 'SURFACE')]
    empties = [obj for obj in all_objects if obj.type == 'EMPTY']

    metadata = {
        # Object counts
        'mesh_count': len(meshes),
        'light_count': len(lights),
        'camera_count': len(cameras),
        'armature_count': len(armatures),
        'gp_count': len(gp_objects),
        'curve_count': len(curve_objects),
        'empty_count': len(empties),

        # Collection-specific
        'collection_name': collection.name,
        'has_nested_collections': 1 if nested_collections else 0,
        'nested_collection_count': len(nested_collections),
    }

    # Also collect type-specific metadata from contained objects
    if meshes or armatures:
        mesh_meta = collect_mesh_metadata(all_objects)
        metadata.update(mesh_meta)

    if lights:
        light_meta = collect_light_metadata(lights)
        metadata.update(light_meta)

    if cameras:
        camera_meta = collect_camera_metadata(cameras)
        metadata.update(camera_meta)

    return metadata


def collect_all_metadata(objects: List[bpy.types.Object], asset_type: str) -> Dict[str, Any]:
    """
    Collect all relevant metadata based on asset type.

    Args:
        objects: List of Blender objects
        asset_type: Type of asset ('model', 'rig', 'animation', 'material', 'light', 'camera')

    Returns:
        Dict with all relevant metadata fields
    """
    metadata = {}

    # Categorize objects
    meshes = [obj for obj in objects if obj.type == 'MESH']
    armatures = [obj for obj in objects if obj.type == 'ARMATURE']
    lights = [obj for obj in objects if obj.type == 'LIGHT']
    cameras = [obj for obj in objects if obj.type == 'CAMERA']

    # Collect materials from mesh objects
    materials = []
    for obj in meshes:
        for slot in obj.material_slots:
            if slot.material and slot.material not in materials:
                materials.append(slot.material)

    # Categorize GP and curve objects
    gp_objects = [obj for obj in objects if obj.type in ('GPENCIL', 'GREASEPENCIL')]
    curve_objects = [obj for obj in objects if obj.type in ('CURVE', 'CURVES', 'SURFACE')]

    # Category mapping (same as Config.ASSET_TYPE_CATEGORY)
    mesh_types = {'mesh', 'model', 'prop', 'vehicle', 'environment', 'character', 'other'}

    if asset_type in mesh_types:
        metadata.update(collect_mesh_metadata(objects))
    elif asset_type == 'rig':
        if armatures:
            metadata.update(collect_rig_metadata(armatures[0]))
        else:
            metadata.update(collect_rig_metadata(None))
    elif asset_type == 'animation':
        metadata.update(collect_animation_metadata())
    elif asset_type == 'material':
        metadata.update(collect_material_metadata(materials))
    elif asset_type == 'light':
        metadata.update(collect_light_metadata(lights))
    elif asset_type == 'camera':
        metadata.update(collect_camera_metadata(cameras))
    elif asset_type == 'grease_pencil':
        metadata.update(collect_grease_pencil_metadata(gp_objects if gp_objects else objects))
    elif asset_type == 'curve':
        metadata.update(collect_curve_metadata(curve_objects if curve_objects else objects))

    return metadata


__all__ = [
    'collect_mesh_metadata',
    'collect_rig_metadata',
    'collect_animation_metadata',
    'collect_material_metadata',
    'collect_light_metadata',
    'collect_camera_metadata',
    'collect_collection_metadata',
    'collect_grease_pencil_metadata',
    'collect_curve_metadata',
    'collect_scene_metadata',
    'collect_all_metadata',
]
