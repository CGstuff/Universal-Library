"""
USDService - Core USD file handling

Provides utilities for reading, writing, and analyzing USD files.
Uses OpenUSD Python bindings (pxr module).
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class USDMetadata:
    """Metadata extracted from a USD file"""

    # Basic info
    file_path: str = ""
    file_size_mb: float = 0.0

    # Geometry
    has_geometry: bool = False
    polygon_count: int = 0
    mesh_count: int = 0
    point_count: int = 0

    # Materials
    has_materials: bool = False
    material_count: int = 0
    material_names: List[str] = field(default_factory=list)

    # Skeleton
    has_skeleton: bool = False
    joint_count: int = 0
    skeleton_name: str = ""

    # Animation
    has_animations: bool = False
    start_frame: float = 0.0
    end_frame: float = 0.0
    fps: float = 24.0

    # Scene info
    up_axis: str = "Y"
    meters_per_unit: float = 0.01

    # Prims
    prim_count: int = 0
    root_prims: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            'file_size_mb': self.file_size_mb,
            'has_materials': 1 if self.has_materials else 0,
            'has_skeleton': 1 if self.has_skeleton else 0,
            'has_animations': 1 if self.has_animations else 0,
            'polygon_count': self.polygon_count,
            'material_count': self.material_count,
        }


class USDService:
    """
    Service for USD file operations

    Features:
    - Read USD file metadata
    - Extract geometry, material, skeleton info
    - Validate USD files
    - Create simple USD files

    Usage:
        service = USDService()
        metadata = service.analyze_usd_file("/path/to/asset.usd")
    """

    def __init__(self):
        self._pxr_available = self._check_pxr_available()

    def _check_pxr_available(self) -> bool:
        """Check if OpenUSD (pxr) module is available"""
        try:
            from pxr import Usd, UsdGeom, UsdShade, UsdSkel
            return True
        except ImportError:
            logger.warning("OpenUSD (pxr) module not available. Install with: pip install usd-core")
            return False

    @property
    def is_available(self) -> bool:
        """Check if USD functionality is available"""
        return self._pxr_available

    def analyze_usd_file(self, file_path: str) -> Optional[USDMetadata]:
        """
        Analyze a USD file and extract metadata

        Args:
            file_path: Path to USD file (.usd, .usda, .usdc, .usdz)

        Returns:
            USDMetadata object or None if failed
        """
        if not self._pxr_available:
            logger.error("Cannot analyze USD: pxr module not available")
            return None

        path = Path(file_path)
        if not path.exists():
            logger.error(f"USD file not found: {file_path}")
            return None

        try:
            from pxr import Usd, UsdGeom, UsdShade, UsdSkel

            # Open stage
            stage = Usd.Stage.Open(str(path))
            if not stage:
                logger.error(f"Failed to open USD stage: {file_path}")
                return None

            metadata = USDMetadata()
            metadata.file_path = str(path)
            metadata.file_size_mb = path.stat().st_size / (1024 * 1024)

            # Get stage info
            metadata.up_axis = UsdGeom.GetStageUpAxis(stage)
            metadata.meters_per_unit = UsdGeom.GetStageMetersPerUnit(stage)

            # Get time info
            metadata.start_frame = stage.GetStartTimeCode()
            metadata.end_frame = stage.GetEndTimeCode()
            metadata.fps = stage.GetFramesPerSecond()
            metadata.has_animations = metadata.end_frame > metadata.start_frame

            # Get root prims
            root_layer = stage.GetRootLayer()
            metadata.root_prims = [str(p.GetPath()) for p in stage.GetPseudoRoot().GetChildren()]

            # Traverse and analyze prims
            prim_count = 0
            mesh_count = 0
            total_polygons = 0
            total_points = 0
            material_paths = set()
            skeleton_found = False
            skeleton_name = ""
            joint_count = 0

            for prim in stage.Traverse():
                prim_count += 1

                # Check for mesh
                if prim.IsA(UsdGeom.Mesh):
                    mesh_count += 1
                    mesh = UsdGeom.Mesh(prim)

                    # Get face counts
                    face_counts = mesh.GetFaceVertexCountsAttr().Get()
                    if face_counts:
                        total_polygons += len(face_counts)

                    # Get points
                    points = mesh.GetPointsAttr().Get()
                    if points:
                        total_points += len(points)

                    # Check for material binding
                    binding_api = UsdShade.MaterialBindingAPI(prim)
                    material, _ = binding_api.ComputeBoundMaterial()
                    if material:
                        material_paths.add(str(material.GetPath()))

                # Check for materials
                if prim.IsA(UsdShade.Material):
                    material_paths.add(str(prim.GetPath()))

                # Check for skeleton
                if prim.IsA(UsdSkel.Skeleton):
                    skeleton_found = True
                    skeleton = UsdSkel.Skeleton(prim)
                    skeleton_name = prim.GetName()

                    joints = skeleton.GetJointsAttr().Get()
                    if joints:
                        joint_count = len(joints)

            # Populate metadata
            metadata.prim_count = prim_count
            metadata.mesh_count = mesh_count
            metadata.polygon_count = total_polygons
            metadata.point_count = total_points
            metadata.has_geometry = mesh_count > 0

            metadata.material_count = len(material_paths)
            metadata.material_names = [p.split('/')[-1] for p in material_paths]
            metadata.has_materials = len(material_paths) > 0

            metadata.has_skeleton = skeleton_found
            metadata.skeleton_name = skeleton_name
            metadata.joint_count = joint_count

            logger.info(f"Analyzed USD: {path.name} - {mesh_count} meshes, {total_polygons} polys, {len(material_paths)} materials")

            return metadata

        except Exception as e:
            logger.error(f"Error analyzing USD file {file_path}: {e}")
            return None

    def validate_usd_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Validate a USD file

        Args:
            file_path: Path to USD file

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self._pxr_available:
            return False, "pxr module not available"

        path = Path(file_path)
        if not path.exists():
            return False, f"File not found: {file_path}"

        # Check extension
        valid_extensions = ['.usd', '.usda', '.usdc', '.usdz']
        if path.suffix.lower() not in valid_extensions:
            return False, f"Invalid extension: {path.suffix}"

        try:
            from pxr import Usd

            stage = Usd.Stage.Open(str(path))
            if not stage:
                return False, "Failed to open stage"

            # Check for root prims
            root = stage.GetPseudoRoot()
            if not root.GetChildren():
                return False, "No root prims found"

            return True, ""

        except Exception as e:
            return False, str(e)

    def get_default_prim(self, file_path: str) -> Optional[str]:
        """
        Get the default prim path from a USD file

        Args:
            file_path: Path to USD file

        Returns:
            Default prim path or None
        """
        if not self._pxr_available:
            return None

        try:
            from pxr import Usd

            stage = Usd.Stage.Open(str(file_path))
            if not stage:
                return None

            default_prim = stage.GetDefaultPrim()
            if default_prim:
                return str(default_prim.GetPath())

            return None

        except Exception as e:
            logger.debug(f"Could not get default prim for {file_path}: {e}")
            return None

    def get_sublayers(self, file_path: str) -> List[str]:
        """
        Get sublayer references from a USD file

        Args:
            file_path: Path to USD file

        Returns:
            List of sublayer paths
        """
        if not self._pxr_available:
            return []

        try:
            from pxr import Usd

            stage = Usd.Stage.Open(str(file_path))
            if not stage:
                return []

            root_layer = stage.GetRootLayer()
            return list(root_layer.subLayerPaths)

        except Exception as e:
            logger.debug(f"Could not get sublayers for {file_path}: {e}")
            return []

    def create_reference_usd(
        self,
        output_path: str,
        reference_path: str,
        default_prim_name: str = "Asset"
    ) -> bool:
        """
        Create a USD file that references another USD

        Useful for creating library entries that reference original assets.

        Args:
            output_path: Path for new USD file
            reference_path: Path to USD file to reference
            default_prim_name: Name for the default prim

        Returns:
            True if successful
        """
        if not self._pxr_available:
            return False

        try:
            from pxr import Usd, UsdGeom, Sdf

            # Create new stage
            stage = Usd.Stage.CreateNew(output_path)

            # Set up axis and units
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
            UsdGeom.SetStageMetersPerUnit(stage, 0.01)

            # Create root prim
            root_prim = stage.DefinePrim(f"/{default_prim_name}", "Xform")
            stage.SetDefaultPrim(root_prim)

            # Add reference
            root_prim.GetReferences().AddReference(reference_path)

            # Save
            stage.GetRootLayer().Save()

            logger.info(f"Created reference USD: {output_path} -> {reference_path}")
            return True

        except Exception as e:
            logger.error(f"Error creating reference USD: {e}")
            return False


# Singleton
_usd_service_instance: Optional[USDService] = None


def get_usd_service() -> USDService:
    """Get global USDService singleton"""
    global _usd_service_instance
    if _usd_service_instance is None:
        _usd_service_instance = USDService()
    return _usd_service_instance


__all__ = ['USDService', 'USDMetadata', 'get_usd_service']
