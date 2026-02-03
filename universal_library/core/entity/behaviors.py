"""
Behavior mixins for entities.

Behaviors add capabilities to entities through composition.
Each behavior defines properties and methods that entities
gain when they inherit from the mixin.
"""

from abc import ABC
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Entity


class Versionable(ABC):
    """
    Mixin for entities that support versioning.

    Adds version tracking with version numbers, labels, and
    version group identification for tracking version chains.

    Required fields: version, version_label, version_group_id, is_latest
    """

    @property
    def version(self) -> int:
        """Get version number (1, 2, 3, ...)."""
        return self.get('version', 1)

    @property
    def version_label(self) -> str:
        """Get human-readable version label (v001, v002, ...)."""
        return self.get('version_label', 'v001')

    @property
    def version_group_id(self) -> Optional[str]:
        """Get version group ID (shared across versions of same entity)."""
        return self.get('version_group_id')

    @property
    def is_latest(self) -> bool:
        """Check if this is the latest version."""
        return bool(self.get('is_latest', True))

    @property
    def parent_version_uuid(self) -> Optional[str]:
        """Get parent version UUID (if this is a new version of existing)."""
        return self.get('parent_version_uuid')

    def get_version_history(self) -> List['Entity']:
        """
        Get all versions of this entity.

        Returns:
            List of entities in version order (oldest first)
        """
        from ...services import get_database_service
        db = get_database_service()
        return db.get_version_history(self.version_group_id)


class Variantable(ABC):
    """
    Mixin for entities that support variants.

    Variants are alternative versions of an entity that share
    a common origin but differ in some way (e.g., different armor styles).

    Required fields: asset_id, variant_name, variant_set, variant_source_uuid
    """

    @property
    def asset_id(self) -> Optional[str]:
        """Get asset family ID (shared across all variants)."""
        return self.get('asset_id')

    @property
    def variant_name(self) -> str:
        """Get variant name (Base, Heavy_Armor, etc.)."""
        return self.get('variant_name', 'Base')

    @property
    def variant_set(self) -> Optional[str]:
        """Get variant set category (Armor, Color, LOD, etc.)."""
        return self.get('variant_set')

    @property
    def variant_source_uuid(self) -> Optional[str]:
        """Get UUID of entity this variant was created from."""
        return self.get('variant_source_uuid')

    @property
    def is_base_variant(self) -> bool:
        """Check if this is the base variant."""
        return self.variant_name == 'Base'

    def get_variants(self) -> List['Entity']:
        """
        Get all variants of this entity family.

        Returns:
            List of variant entities
        """
        from ...services import get_database_service
        db = get_database_service()
        return db.get_variants(self.asset_id)

    def get_variant_count(self) -> int:
        """Get number of variants for this entity family."""
        from ...services import get_database_service
        db = get_database_service()
        return db.get_variant_count(self.asset_id)


class Reviewable(ABC):
    """
    Mixin for entities that support review workflow.

    Enables review cycles with states like needs_review, in_review,
    in_progress, approved, and final.

    Depends on: Versionable, Variantable (for identifiers)
    """

    @property
    def review_state(self) -> Optional[str]:
        """Get current review state (needs_review, in_review, etc.)."""
        return self.get('review_state')

    @property
    def is_in_review(self) -> bool:
        """Check if entity is in active review workflow."""
        state = self.review_state
        return state in ('needs_review', 'in_review', 'in_progress', 'approved')

    @property
    def is_review_final(self) -> bool:
        """Check if review is marked final."""
        return self.review_state == 'final'

    def get_active_cycle(self) -> Optional[Dict[str, Any]]:
        """
        Get active review cycle for this entity.

        Returns:
            Review cycle dict or None if no active cycle
        """
        from ...services.review_state_manager import get_review_state_manager
        state_manager = get_review_state_manager()

        # Use asset_id for cycle lookup (shared across variants)
        asset_id = self.get('asset_id') or self.get('version_group_id') or self.uuid
        return state_manager.get_active_cycle(asset_id)

    def get_review_notes_count(self) -> Dict[str, int]:
        """
        Get review note counts by status.

        Returns:
            Dict with 'open', 'addressed', 'approved', 'total' counts
        """
        from ...services.review_database import get_review_database
        review_db = get_review_database()

        asset_id = self.get('asset_id') or self.get('version_group_id') or self.uuid
        cycle = self.get_active_cycle()

        if cycle:
            return review_db.get_cycle_note_counts(cycle['id'])
        return review_db.get_note_status_counts(self.uuid, self.version_label)


class Taggable(ABC):
    """
    Mixin for entities that support tagging.

    Enables multiple tags per entity for categorization and filtering.
    """

    def get_tags(self) -> List[Dict[str, Any]]:
        """
        Get all tags for this entity.

        Returns:
            List of tag dicts with id, name, color
        """
        return self.get('tags_v2', [])

    def get_tag_ids(self) -> List[int]:
        """Get list of tag IDs."""
        return [t.get('id') for t in self.get_tags() if t.get('id')]

    def get_tag_names(self) -> List[str]:
        """Get list of tag names."""
        return [t.get('name') for t in self.get_tags() if t.get('name')]

    def has_tag(self, tag_id: int) -> bool:
        """Check if entity has a specific tag."""
        return tag_id in self.get_tag_ids()

    def add_tag(self, tag_id: int) -> bool:
        """
        Add tag to entity.

        Args:
            tag_id: ID of tag to add

        Returns:
            True if successful
        """
        from ...services import get_database_service
        db = get_database_service()
        return db.add_tag_to_asset(self.uuid, tag_id)

    def remove_tag(self, tag_id: int) -> bool:
        """
        Remove tag from entity.

        Args:
            tag_id: ID of tag to remove

        Returns:
            True if successful
        """
        from ...services import get_database_service
        db = get_database_service()
        return db.remove_tag_from_asset(self.uuid, tag_id)


class Folderable(ABC):
    """
    Mixin for entities that support folder membership.

    Enables entities to belong to multiple folders for organization.
    """

    @property
    def folder_id(self) -> Optional[int]:
        """Get primary folder ID."""
        return self.get('folder_id')

    def get_folders(self) -> List[Dict[str, Any]]:
        """
        Get all folders this entity belongs to.

        Returns:
            List of folder dicts with id, name, path
        """
        return self.get('folders_v2', [])

    def get_folder_ids(self) -> List[int]:
        """Get list of folder IDs."""
        return [f.get('id') for f in self.get_folders() if f.get('id')]

    def in_folder(self, folder_id: int) -> bool:
        """Check if entity is in a specific folder."""
        return folder_id in self.get_folder_ids()

    def add_to_folder(self, folder_id: int) -> bool:
        """
        Add entity to folder.

        Args:
            folder_id: ID of folder to add to

        Returns:
            True if successful
        """
        from ...services import get_database_service
        db = get_database_service()
        return db.add_asset_to_folder(self.uuid, folder_id)

    def remove_from_folder(self, folder_id: int) -> bool:
        """
        Remove entity from folder.

        Args:
            folder_id: ID of folder to remove from

        Returns:
            True if successful
        """
        from ...services import get_database_service
        db = get_database_service()
        return db.remove_asset_from_folder(self.uuid, folder_id)


__all__ = [
    'Versionable',
    'Variantable',
    'Reviewable',
    'Taggable',
    'Folderable',
]
