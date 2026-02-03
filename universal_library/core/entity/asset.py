"""
AssetEntity - Concrete entity implementation for assets.

Combines all behaviors needed for asset management:
- Versionable: Version tracking and history
- Variantable: Variant support for different versions
- Reviewable: Review workflow integration
- Taggable: Tag-based categorization
- Folderable: Folder organization
"""

from typing import Optional, List, Dict, Any

from .base import Entity, EntityDefinition
from .behaviors import Versionable, Variantable, Reviewable, Taggable, Folderable


class AssetEntity(Entity, Versionable, Variantable, Reviewable, Taggable, Folderable):
    """
    Asset entity with full behavior composition.

    Represents a USD asset in the library with support for:
    - Versioning (v001, v002, etc.)
    - Variants (Base, Heavy_Armor, etc.)
    - Review workflow (needs_review, approved, etc.)
    - Tags and folders for organization

    Core fields (stored in assets table):
        uuid, name, description, folder_id, asset_type,
        usd_file_path, blend_backup_path, thumbnail_path, preview_path,
        version, version_label, version_group_id, is_latest, parent_version_uuid,
        asset_id, variant_name, variant_set, variant_source_uuid,
        status, is_locked, is_cold, created_date, modified_date

    Dynamic fields (stored in entity_metadata):
        bone_count, control_count, frame_start, frame_end, frame_rate,
        texture_maps, texture_resolution, light_type, light_count,
        camera_type, focal_length, mesh_count, etc.
    """

    _definition = EntityDefinition(
        name='asset',
        table_name='assets',
        behaviors=['versionable', 'variantable', 'reviewable', 'taggable', 'folderable'],
        core_fields=[
            # Identity
            'uuid', 'name', 'description', 'folder_id', 'asset_type',
            # Files
            'usd_file_path', 'blend_backup_path', 'thumbnail_path', 'preview_path',
            'cold_storage_path', 'original_usd_path', 'original_blend_path', 'original_thumbnail_path',
            # Versioning
            'version', 'version_label', 'version_group_id', 'is_latest', 'parent_version_uuid',
            'version_notes',
            # Variants
            'asset_id', 'variant_name', 'variant_set', 'variant_source_uuid',
            'source_asset_name', 'source_version_label',
            # Status
            'status', 'representation_type', 'is_locked', 'is_immutable', 'is_cold',
            'published_date', 'published_by',
            # Basic metadata
            'file_size_mb', 'has_materials', 'has_skeleton', 'has_animations',
            'polygon_count', 'material_count', 'tags', 'author', 'source_application',
            # User features
            'is_favorite', 'last_viewed_date', 'custom_order',
            # Timestamps
            'created_date', 'modified_date',
        ]
    )

    # =========================================================================
    # Asset-Specific Properties
    # =========================================================================

    @property
    def name(self) -> str:
        """Get asset name."""
        return self.get('name', '')

    @property
    def description(self) -> Optional[str]:
        """Get asset description."""
        return self.get('description')

    @property
    def asset_type(self) -> str:
        """Get asset type (mesh, material, rig, light, camera, collection, other)."""
        return self.get('asset_type', 'mesh')

    @property
    def status(self) -> str:
        """Get lifecycle status (wip, review, approved, deprecated, archived)."""
        return self.get('status', 'wip')

    @property
    def representation_type(self) -> str:
        """Get representation type (model, lookdev, rig, final, none)."""
        return self.get('representation_type', 'none')

    # =========================================================================
    # File Paths
    # =========================================================================

    @property
    def thumbnail_path(self) -> Optional[str]:
        """Get thumbnail image path."""
        return self.get('thumbnail_path')

    @property
    def preview_path(self) -> Optional[str]:
        """Get preview image path."""
        return self.get('preview_path')

    @property
    def usd_file_path(self) -> Optional[str]:
        """Get USD file path."""
        return self.get('usd_file_path')

    @property
    def blend_backup_path(self) -> Optional[str]:
        """Get Blender backup file path."""
        return self.get('blend_backup_path')

    # =========================================================================
    # State Flags
    # =========================================================================

    @property
    def is_favorite(self) -> bool:
        """Check if asset is marked as favorite."""
        return bool(self.get('is_favorite', False))

    @property
    def is_locked(self) -> bool:
        """Check if asset is locked (immutable)."""
        return bool(self.get('is_locked', False))

    @property
    def is_cold(self) -> bool:
        """Check if asset is in cold storage."""
        return bool(self.get('is_cold', False))

    @property
    def is_immutable(self) -> bool:
        """Check if asset is published/immutable."""
        return bool(self.get('is_immutable', False))

    # =========================================================================
    # Basic Metadata (Core Fields)
    # =========================================================================

    @property
    def file_size_mb(self) -> Optional[float]:
        """Get file size in megabytes."""
        return self.get('file_size_mb')

    @property
    def polygon_count(self) -> Optional[int]:
        """Get polygon count."""
        return self.get('polygon_count')

    @property
    def material_count(self) -> Optional[int]:
        """Get material count."""
        return self.get('material_count')

    @property
    def has_materials(self) -> bool:
        """Check if asset has materials."""
        return bool(self.get('has_materials', False))

    @property
    def has_skeleton(self) -> bool:
        """Check if asset has a skeleton/armature."""
        return bool(self.get('has_skeleton', False))

    @property
    def has_animations(self) -> bool:
        """Check if asset has animations."""
        return bool(self.get('has_animations', False))

    @property
    def author(self) -> Optional[str]:
        """Get asset author."""
        return self.get('author')

    # =========================================================================
    # Type-Specific Metadata (Dynamic Fields)
    # These will be migrated to entity_metadata in future
    # =========================================================================

    @property
    def bone_count(self) -> Optional[int]:
        """Get bone count (for rigs)."""
        return self.get('bone_count')

    @property
    def control_count(self) -> Optional[int]:
        """Get control count (for rigs)."""
        return self.get('control_count')

    @property
    def has_facial_rig(self) -> bool:
        """Check if rig has facial controls."""
        return bool(self.get('has_facial_rig', False))

    @property
    def frame_start(self) -> Optional[int]:
        """Get animation start frame."""
        return self.get('frame_start')

    @property
    def frame_end(self) -> Optional[int]:
        """Get animation end frame."""
        return self.get('frame_end')

    @property
    def frame_rate(self) -> Optional[float]:
        """Get animation frame rate."""
        return self.get('frame_rate')

    @property
    def is_loop(self) -> bool:
        """Check if animation is looping."""
        return bool(self.get('is_loop', False))

    @property
    def texture_maps(self) -> Optional[List[str]]:
        """Get texture map list (for materials)."""
        maps = self.get('texture_maps')
        if isinstance(maps, str):
            import json
            try:
                return json.loads(maps)
            except Exception:
                return None
        return maps

    @property
    def texture_resolution(self) -> Optional[str]:
        """Get texture resolution (for materials)."""
        return self.get('texture_resolution')

    @property
    def light_type(self) -> Optional[str]:
        """Get light type (for lights)."""
        return self.get('light_type')

    @property
    def light_count(self) -> Optional[int]:
        """Get light count (for light assets)."""
        return self.get('light_count')

    @property
    def camera_type(self) -> Optional[str]:
        """Get camera type (for cameras)."""
        return self.get('camera_type')

    @property
    def focal_length(self) -> Optional[float]:
        """Get focal length (for cameras)."""
        return self.get('focal_length')

    # =========================================================================
    # Collection-Specific
    # =========================================================================

    @property
    def collection_name(self) -> Optional[str]:
        """Get collection name (for collections)."""
        return self.get('collection_name')

    @property
    def mesh_count(self) -> Optional[int]:
        """Get mesh count in collection."""
        return self.get('mesh_count')

    @property
    def camera_count(self) -> Optional[int]:
        """Get camera count in collection."""
        return self.get('camera_count')

    @property
    def armature_count(self) -> Optional[int]:
        """Get armature count in collection."""
        return self.get('armature_count')

    @property
    def has_nested_collections(self) -> bool:
        """Check if collection has nested collections."""
        return bool(self.get('has_nested_collections', False))

    @property
    def nested_collection_count(self) -> Optional[int]:
        """Get nested collection count."""
        return self.get('nested_collection_count')

    # =========================================================================
    # Timestamps
    # =========================================================================

    @property
    def created_date(self) -> Optional[str]:
        """Get creation date."""
        return self.get('created_date')

    @property
    def modified_date(self) -> Optional[str]:
        """Get last modified date."""
        return self.get('modified_date')

    @property
    def last_viewed_date(self) -> Optional[str]:
        """Get last viewed date."""
        return self.get('last_viewed_date')

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_display_name(self) -> str:
        """Get display name with variant suffix if not Base."""
        name = self.name
        if not self.is_base_variant:
            name = f"{name} [{self.variant_name}]"
        return name

    def get_type_category(self) -> str:
        """
        Get type category for UI display grouping.

        Returns:
            Category name (mesh, material, rig, light, camera, collection)
        """
        from ...config import ASSET_TYPE_CATEGORY
        return ASSET_TYPE_CATEGORY.get(self.asset_type, 'mesh')


__all__ = ['AssetEntity']
