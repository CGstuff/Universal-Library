"""
Material Converter - Convert between Blender and USD materials

Handles conversion of Principled BSDF to UsdPreviewSurface and vice versa.
"""

import bpy
from typing import Dict, Any, Optional, Tuple
from pathlib import Path


class MaterialConverter:
    """
    Convert materials between Blender nodes and USD formats

    Supports:
    - Principled BSDF -> UsdPreviewSurface (export)
    - UsdPreviewSurface -> Principled BSDF (import)

    Usage:
        converter = MaterialConverter()
        usd_mat = converter.blender_to_usd(blender_material)
    """

    # Mapping of Principled BSDF inputs to UsdPreviewSurface
    PRINCIPLED_TO_USD = {
        'Base Color': 'diffuseColor',
        'Metallic': 'metallic',
        'Roughness': 'roughness',
        'IOR': 'ior',
        'Alpha': 'opacity',
        'Normal': 'normal',
        'Emission Color': 'emissiveColor',
        'Specular IOR Level': 'specularColor',
        'Coat Weight': 'clearcoat',
        'Coat Roughness': 'clearcoatRoughness',
    }

    # Reverse mapping
    USD_TO_PRINCIPLED = {v: k for k, v in PRINCIPLED_TO_USD.items()}

    def __init__(self):
        pass

    def get_principled_bsdf(self, material: bpy.types.Material) -> Optional[bpy.types.Node]:
        """Find Principled BSDF node in material"""
        if not material.use_nodes:
            return None

        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                return node

        return None

    def extract_material_data(self, material: bpy.types.Material) -> Dict[str, Any]:
        """
        Extract material properties for USD export

        Args:
            material: Blender material

        Returns:
            Dictionary of USD-compatible material properties
        """
        data = {
            'name': material.name,
            'type': 'UsdPreviewSurface',
            'inputs': {},
            'textures': {}
        }

        principled = self.get_principled_bsdf(material)
        if not principled:
            # Return defaults for non-node materials
            data['inputs'] = {
                'diffuseColor': (0.8, 0.8, 0.8),
                'roughness': 0.5,
                'metallic': 0.0,
            }
            return data

        # Extract each input
        for blender_name, usd_name in self.PRINCIPLED_TO_USD.items():
            input_socket = principled.inputs.get(blender_name)
            if not input_socket:
                continue

            # Check if connected to texture
            if input_socket.is_linked:
                texture_data = self._extract_texture_info(input_socket)
                if texture_data:
                    data['textures'][usd_name] = texture_data
            else:
                # Get default value
                value = self._get_socket_value(input_socket)
                if value is not None:
                    data['inputs'][usd_name] = value

        return data

    def _extract_texture_info(self, socket: bpy.types.NodeSocket) -> Optional[Dict[str, Any]]:
        """Extract texture information from connected node"""
        if not socket.is_linked:
            return None

        # Follow link to source
        link = socket.links[0]
        source_node = link.from_node

        # Handle Image Texture node
        if source_node.type == 'TEX_IMAGE':
            image = source_node.image
            if image:
                return {
                    'type': 'image',
                    'name': image.name,
                    'filepath': image.filepath if image.filepath else None,
                    'colorspace': image.colorspace_settings.name,
                }

        # Handle Normal Map node (follow to image)
        if source_node.type == 'NORMAL_MAP':
            color_input = source_node.inputs.get('Color')
            if color_input and color_input.is_linked:
                return self._extract_texture_info(color_input)

        return None

    def _get_socket_value(self, socket: bpy.types.NodeSocket) -> Any:
        """Get value from node socket"""
        if hasattr(socket, 'default_value'):
            value = socket.default_value

            # Handle color (RGBA)
            if hasattr(value, '__len__') and len(value) == 4:
                return tuple(value[:3])  # RGB only

            # Handle vector
            if hasattr(value, '__len__') and len(value) == 3:
                return tuple(value)

            # Handle single value
            return value

        return None

    def apply_material_data(
        self,
        material: bpy.types.Material,
        data: Dict[str, Any],
        texture_dir: Path = None
    ):
        """
        Apply USD material data to Blender material

        Args:
            material: Target Blender material
            data: USD material data dictionary
            texture_dir: Directory containing texture files
        """
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links

        # Clear existing nodes
        nodes.clear()

        # Create output node
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (300, 0)

        # Create Principled BSDF
        principled = nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (0, 0)

        # Connect to output
        links.new(principled.outputs['BSDF'], output.inputs['Surface'])

        # Apply input values
        inputs = data.get('inputs', {})
        for usd_name, value in inputs.items():
            blender_name = self.USD_TO_PRINCIPLED.get(usd_name)
            if blender_name and blender_name in principled.inputs:
                socket = principled.inputs[blender_name]
                self._set_socket_value(socket, value)

        # Apply textures
        textures = data.get('textures', {})
        x_offset = -300
        y_offset = 300

        for usd_name, tex_data in textures.items():
            blender_name = self.USD_TO_PRINCIPLED.get(usd_name)
            if not blender_name or blender_name not in principled.inputs:
                continue

            # Create image texture node
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.location = (x_offset, y_offset)
            y_offset -= 300

            # Load image
            image = self._load_texture(tex_data, texture_dir)
            if image:
                tex_node.image = image

                # Set colorspace
                if tex_data.get('colorspace'):
                    tex_node.image.colorspace_settings.name = tex_data['colorspace']

            # Handle normal maps specially
            if usd_name == 'normal':
                normal_node = nodes.new('ShaderNodeNormalMap')
                normal_node.location = (x_offset + 200, y_offset + 300)
                links.new(tex_node.outputs['Color'], normal_node.inputs['Color'])
                links.new(normal_node.outputs['Normal'], principled.inputs[blender_name])
            else:
                # Direct connection
                output_socket = 'Color' if usd_name in ['diffuseColor', 'emissiveColor'] else 'Color'
                links.new(tex_node.outputs[output_socket], principled.inputs[blender_name])

    def _set_socket_value(self, socket: bpy.types.NodeSocket, value: Any):
        """Set value on node socket"""
        if hasattr(socket, 'default_value'):
            if isinstance(value, (list, tuple)):
                # Extend to RGBA if needed
                if len(value) == 3 and hasattr(socket.default_value, '__len__') and len(socket.default_value) == 4:
                    value = (*value, 1.0)
                socket.default_value = value
            else:
                socket.default_value = value

    def _load_texture(self, tex_data: Dict[str, Any], texture_dir: Path = None) -> Optional[bpy.types.Image]:
        """Load texture image"""
        filepath = tex_data.get('filepath')
        name = tex_data.get('name', 'Texture')

        # Check if already loaded
        if name in bpy.data.images:
            return bpy.data.images[name]

        # Try to load from filepath
        if filepath:
            # Try absolute path first
            if Path(filepath).exists():
                return bpy.data.images.load(filepath)

            # Try relative to texture_dir
            if texture_dir:
                full_path = texture_dir / Path(filepath).name
                if full_path.exists():
                    return bpy.data.images.load(str(full_path))

        return None

    def get_material_complexity(self, material: bpy.types.Material) -> str:
        """
        Analyze material complexity for export warnings

        Returns:
            'simple': Can be fully converted
            'moderate': Some features may be lost
            'complex': Significant features will be lost
        """
        if not material.use_nodes:
            return 'simple'

        principled = self.get_principled_bsdf(material)
        if not principled:
            return 'complex'

        nodes = material.node_tree.nodes
        node_types = {node.type for node in nodes}

        # Complex procedural nodes
        complex_nodes = {
            'TEX_NOISE', 'TEX_VORONOI', 'TEX_WAVE', 'TEX_MUSGRAVE',
            'TEX_GRADIENT', 'TEX_BRICK', 'TEX_CHECKER',
            'MATH', 'VECT_MATH', 'MIX_RGB', 'MIX_SHADER',
            'LAYER_WEIGHT', 'FRESNEL'
        }

        if node_types & complex_nodes:
            return 'complex'

        # Check for multiple shaders
        shader_count = sum(1 for n in nodes if 'BSDF' in n.type or 'SHADER' in n.type)
        if shader_count > 1:
            return 'complex'

        # Moderate if using many texture nodes
        tex_count = sum(1 for n in nodes if 'TEX_IMAGE' in n.type)
        if tex_count > 5:
            return 'moderate'

        return 'simple'


# Global instance
_converter: Optional[MaterialConverter] = None


def get_material_converter() -> MaterialConverter:
    """Get global material converter instance"""
    global _converter
    if _converter is None:
        _converter = MaterialConverter()
    return _converter


__all__ = ['MaterialConverter', 'get_material_converter']
