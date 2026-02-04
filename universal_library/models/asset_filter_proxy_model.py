"""
AssetFilterProxyModel - Filtering and searching for USD assets

Pattern: Proxy pattern with QSortFilterProxyModel
Based on animation_library architecture.
"""

from typing import Optional, Set
from PyQt6.QtCore import QSortFilterProxyModel, QModelIndex, Qt

from .asset_list_model import AssetRole
from ..config import Config


class AssetFilterProxyModel(QSortFilterProxyModel):
    """
    Proxy model for filtering and searching USD assets

    Features:
    - Instant text search (name, description, tags)
    - Folder filtering (including virtual folders)
    - Asset type filtering
    - Tag filtering
    - Case-insensitive search
    - Performance: Uses Qt's built-in caching

    Usage:
        proxy = AssetFilterProxyModel()
        proxy.setSourceModel(asset_list_model)
        proxy.set_search_text("cube")
        proxy.set_folder_filter(5)
        view.setModel(proxy)
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Filter criteria
        self._search_text: str = ""
        self._folder_id: Optional[int] = None
        self._folder_ids: Set[int] = set()  # For recursive folder filtering
        self._filter_tags: Set[str] = set()  # Legacy tag name filter
        self._filter_tag_ids: Set[int] = set()  # New tag ID filter
        self._filter_asset_types: Set[str] = set()
        self._filter_statuses: Set[str] = set()  # Lifecycle status filter
        self._filter_physical_path: Optional[str] = None  # Physical path prefix filter
        self._favorites_only: bool = False
        self._recent_only: bool = False
        self._cold_storage_only: bool = False  # Filter for cold storage assets
        self._base_only: bool = False  # Filter for base assets (variant_name == 'Base')
        self._variants_only: bool = False  # Filter for variant assets (variant_name != 'Base')
        self._needs_review_only: bool = False  # Filter for review_state == 'needs_review'
        self._in_review_only: bool = False  # Filter for review_state == 'in_review'
        self._in_progress_only: bool = False  # Filter for review_state == 'in_progress'
        self._approved_only: bool = False  # Filter for review_state == 'approved'
        self._final_only: bool = False  # Filter for review_state == 'final'
        self._show_only_latest: bool = True  # Show only latest versions by default

        # Sort configuration
        self._sort_by: str = "name"  # name, date, file_size, polygon_count
        self._sort_order: str = "ASC"  # ASC or DESC
        self._group_by_family: bool = False  # Group variants with their base

        # Configure sorting/filtering
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setDynamicSortFilter(True)  # Auto-refilter on data changes
        self.setSortRole(AssetRole.NameRole)  # Enable sorting by default

    def set_search_text(self, text: str):
        """
        Set search text filter

        Args:
            text: Search query (searches name, description, tags)
        """
        if self._search_text != text:
            self._search_text = text.strip().lower()
            self.invalidateFilter()

    def set_folder_filter(self, folder_id: Optional[int], folder_ids: Optional[Set[int]] = None):
        """
        Set folder filter

        Args:
            folder_id: Folder ID to filter by:
                - None: Show all
                - Config.VIRTUAL_FOLDER_ALL (-1): Show all
                - Config.VIRTUAL_FOLDER_FAVORITES (-2): Show favorites
                - Config.VIRTUAL_FOLDER_RECENT (-3): Show recent
                - Positive int: Show specific folder
            folder_ids: Set of folder IDs for recursive filtering (optional)
        """
        changed = False

        # Helper to clear all virtual folder flags
        def clear_virtual_flags():
            self._folder_id = None
            self._favorites_only = False
            self._recent_only = False
            self._cold_storage_only = False
            self._base_only = False
            self._variants_only = False
            self._needs_review_only = False
            self._in_review_only = False
            self._in_progress_only = False
            self._approved_only = False
            self._final_only = False

        def has_any_virtual_flag():
            return (self._folder_id is not None or self._favorites_only or
                    self._recent_only or self._cold_storage_only or
                    self._base_only or self._variants_only or
                    self._needs_review_only or self._in_review_only or
                    self._in_progress_only or self._approved_only or self._final_only)

        # Handle virtual folders
        if folder_id == Config.VIRTUAL_FOLDER_ALL:
            # All Assets - clear folder filter
            if has_any_virtual_flag():
                clear_virtual_flags()
                changed = True
        elif folder_id == Config.VIRTUAL_FOLDER_FAVORITES:
            # Favorites virtual folder
            if not self._favorites_only:
                clear_virtual_flags()
                self._favorites_only = True
                changed = True
        elif folder_id == Config.VIRTUAL_FOLDER_RECENT:
            # Recent virtual folder
            if not self._recent_only:
                clear_virtual_flags()
                self._recent_only = True
                changed = True
        elif folder_id == Config.VIRTUAL_FOLDER_COLD_STORAGE:
            # Cold Storage virtual folder
            if not self._cold_storage_only:
                clear_virtual_flags()
                self._cold_storage_only = True
                changed = True
        elif folder_id == Config.VIRTUAL_FOLDER_BASE:
            # Base virtual folder - show only base assets
            if not self._base_only:
                clear_virtual_flags()
                self._base_only = True
                changed = True
        elif folder_id == Config.VIRTUAL_FOLDER_VARIANTS:
            # Variants virtual folder - show only variant assets
            if not self._variants_only:
                clear_virtual_flags()
                self._variants_only = True
                changed = True
        elif folder_id == Config.VIRTUAL_FOLDER_NEEDS_REVIEW:
            # Needs Review virtual folder - show assets with review_state == 'needs_review'
            if not self._needs_review_only:
                clear_virtual_flags()
                self._needs_review_only = True
                changed = True
        elif folder_id == Config.VIRTUAL_FOLDER_IN_REVIEW:
            # In Review virtual folder - show assets with review_state == 'in_review'
            if not self._in_review_only:
                clear_virtual_flags()
                self._in_review_only = True
                changed = True
        elif folder_id == Config.VIRTUAL_FOLDER_IN_PROGRESS:
            # In Progress virtual folder - show assets with review_state == 'in_progress'
            if not self._in_progress_only:
                clear_virtual_flags()
                self._in_progress_only = True
                changed = True
        elif folder_id == Config.VIRTUAL_FOLDER_APPROVED:
            # Approved virtual folder - show assets with review_state == 'approved'
            if not self._approved_only:
                clear_virtual_flags()
                self._approved_only = True
                changed = True
        elif folder_id == Config.VIRTUAL_FOLDER_FINAL:
            # Final virtual folder - show assets with review_state == 'final'
            if not self._final_only:
                clear_virtual_flags()
                self._final_only = True
                changed = True
        else:
            # Regular folder
            if has_any_virtual_flag() or self._folder_id != folder_id:
                clear_virtual_flags()
                self._folder_id = folder_id
                changed = True

        # Combine parent folder + children for recursive filtering
        new_folder_ids = set(folder_ids) if folder_ids else set()
        if self._folder_id is not None and self._folder_id > 0:
            new_folder_ids.add(self._folder_id)
        if self._folder_ids != new_folder_ids:
            self._folder_ids = new_folder_ids
            changed = True

        if changed:
            self.invalidateFilter()

    def set_tag_filter(self, tags: Set[str]):
        """
        Set tag filter (assets must have ALL specified tags)

        Args:
            tags: Set of tag strings
        """
        if self._filter_tags != tags:
            self._filter_tags = tags
            self.invalidateFilter()

    def add_tag_filter(self, tag: str):
        """Add single tag to filter"""
        self._filter_tags.add(tag)
        self.invalidateFilter()

    def remove_tag_filter(self, tag: str):
        """Remove single tag from filter"""
        self._filter_tags.discard(tag)
        self.invalidateFilter()

    def clear_tag_filter(self):
        """Clear all tag filters"""
        if self._filter_tags:
            self._filter_tags.clear()
            self.invalidateFilter()

    def set_tag_id_filter(self, tag_ids: list):
        """
        Set tag ID filter (assets must have ANY of the specified tags)

        Args:
            tag_ids: List of tag IDs
        """
        new_ids = set(tag_ids) if tag_ids else set()
        if self._filter_tag_ids != new_ids:
            self._filter_tag_ids = new_ids
            self.invalidateFilter()

    def clear_tag_id_filter(self):
        """Clear tag ID filter"""
        if self._filter_tag_ids:
            self._filter_tag_ids.clear()
            self.invalidateFilter()

    def set_asset_type_filter(self, asset_types: Set[str]):
        """
        Set asset type filter

        Args:
            asset_types: Set of asset type strings (e.g., {"model", "material", "rig"})
        """
        if self._filter_asset_types != asset_types:
            self._filter_asset_types = asset_types
            self.invalidateFilter()

    def add_asset_type_filter(self, asset_type: str):
        """Add single asset type to filter"""
        self._filter_asset_types.add(asset_type)
        self.invalidateFilter()

    def remove_asset_type_filter(self, asset_type: str):
        """Remove single asset type from filter"""
        self._filter_asset_types.discard(asset_type)
        self.invalidateFilter()

    def clear_asset_type_filter(self):
        """Clear all asset type filters"""
        if self._filter_asset_types:
            self._filter_asset_types.clear()
            self.invalidateFilter()

    # ==================== STATUS FILTERING ====================

    def set_status_filter(self, statuses: Set[str]):
        """
        Set lifecycle status filter

        Args:
            statuses: Set of status strings (e.g., {"wip", "approved"})
        """
        if self._filter_statuses != statuses:
            self._filter_statuses = statuses
            self.invalidateFilter()

    def add_status_filter(self, status: str):
        """Add single status to filter"""
        self._filter_statuses.add(status)
        self.invalidateFilter()

    def remove_status_filter(self, status: str):
        """Remove single status from filter"""
        self._filter_statuses.discard(status)
        self.invalidateFilter()

    def clear_status_filter(self):
        """Clear all status filters"""
        if self._filter_statuses:
            self._filter_statuses.clear()
            self.invalidateFilter()

    # ==================== PHYSICAL PATH FILTERING ====================

    def set_physical_path_filter(self, path_prefix: Optional[str]):
        """
        Set physical path filter - show only assets in a specific folder

        Args:
            path_prefix: Path prefix to filter by (assets must have blend_backup_path
                        starting with this prefix). None or empty string clears filter.
        """
        # Normalize path separators
        normalized = path_prefix.replace('/', '\\') if path_prefix else None
        if self._filter_physical_path != normalized:
            self._filter_physical_path = normalized
            self.invalidateFilter()

    def clear_physical_path_filter(self):
        """Clear physical path filter"""
        if self._filter_physical_path:
            self._filter_physical_path = None
            self.invalidateFilter()

    def set_show_only_latest(self, show_only_latest: bool):
        """
        Set whether to show only latest versions

        Args:
            show_only_latest: True to hide older versions
        """
        if self._show_only_latest != show_only_latest:
            self._show_only_latest = show_only_latest
            self.invalidateFilter()

    def set_favorites_only(self, favorites_only: bool):
        """
        Set favorites only filter

        Args:
            favorites_only: True to show only favorited assets
        """
        if self._favorites_only != favorites_only:
            self._favorites_only = favorites_only
            self.invalidateFilter()

    def set_recent_only(self, recent_only: bool):
        """
        Set recent only filter

        Args:
            recent_only: True to show only recently viewed assets
        """
        if self._recent_only != recent_only:
            self._recent_only = recent_only
            self.invalidateFilter()

    def set_sort_config(self, sort_by: str, sort_order: str):
        """
        Set sort configuration

        Args:
            sort_by: Field to sort by (name, created_date, file_size, polygon_count)
            sort_order: Sort order (ASC or DESC)
        """
        if self._sort_by != sort_by or self._sort_order != sort_order:
            self._sort_by = sort_by
            self._sort_order = sort_order
            self.invalidate()  # Clear cache and re-sort
            self.sort(0)  # Trigger re-sort (column 0)

    def set_group_by_family(self, group: bool):
        """
        Set group by family mode

        When enabled, assets are sorted so that variants appear next to their
        base asset (grouped by asset_id, with Base variant first in each group).

        Args:
            group: True to enable family grouping
        """
        if self._group_by_family != group:
            self._group_by_family = group
            # Force re-sort by toggling sort order
            order = Qt.SortOrder.AscendingOrder if self._sort_order == "ASC" else Qt.SortOrder.DescendingOrder
            self.invalidate()
            # Toggle sort to force Qt to re-evaluate lessThan
            opposite = Qt.SortOrder.DescendingOrder if order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
            self.sort(0, opposite)
            self.sort(0, order)

    def is_group_by_family(self) -> bool:
        """Check if group by family mode is enabled"""
        return self._group_by_family

    def clear_all_filters(self):
        """Clear all filters"""
        changed = False

        if self._search_text:
            self._search_text = ""
            changed = True

        if self._folder_id is not None:
            self._folder_id = None
            changed = True

        if self._folder_ids:
            self._folder_ids.clear()
            changed = True

        if self._filter_tags:
            self._filter_tags.clear()
            changed = True

        if self._filter_tag_ids:
            self._filter_tag_ids.clear()
            changed = True

        if self._filter_asset_types:
            self._filter_asset_types.clear()
            changed = True

        if self._filter_statuses:
            self._filter_statuses.clear()
            changed = True

        if self._filter_physical_path:
            self._filter_physical_path = None
            changed = True

        if self._favorites_only:
            self._favorites_only = False
            changed = True

        if self._recent_only:
            self._recent_only = False
            changed = True

        if self._cold_storage_only:
            self._cold_storage_only = False
            changed = True

        if self._needs_review_only:
            self._needs_review_only = False
            changed = True

        if self._in_review_only:
            self._in_review_only = False
            changed = True

        if self._in_progress_only:
            self._in_progress_only = False
            changed = True

        if self._approved_only:
            self._approved_only = False
            changed = True

        if self._final_only:
            self._final_only = False
            changed = True

        if changed:
            self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """
        Determine if row should be shown

        Args:
            source_row: Row in source model
            source_parent: Parent index

        Returns:
            True if row matches filters, False otherwise
        """
        source_model = self.sourceModel()
        if not source_model:
            return True

        index = source_model.index(source_row, 0, source_parent)

        # Favorites only filter
        if self._favorites_only:
            is_favorite = source_model.data(index, AssetRole.IsFavoriteRole)
            if not is_favorite:
                return False

        # Recent only filter
        if self._recent_only:
            last_viewed = source_model.data(index, AssetRole.LastViewedDateRole)
            if not last_viewed:
                return False

        # Cold storage filter
        is_cold = source_model.data(index, AssetRole.IsColdRole)
        if self._cold_storage_only:
            # In Cold Storage view: show only cold assets
            if not is_cold:
                return False
        else:
            # In regular views: hide cold assets (they only appear in Cold Storage folder)
            if is_cold:
                return False

        # Review state filters (filter by review workflow state)
        review_state = source_model.data(index, AssetRole.ReviewStateRole)
        if self._needs_review_only:
            if review_state != 'needs_review':
                return False
        if self._in_review_only:
            if review_state != 'in_review':
                return False
        if self._in_progress_only:
            if review_state != 'in_progress':
                return False
        if self._approved_only:
            if review_state != 'approved':
                return False
        if self._final_only:
            if review_state != 'final':
                return False

        # Base/Variants filter
        if self._base_only or self._variants_only:
            variant_name = source_model.data(index, AssetRole.VariantNameRole) or 'Base'
            if self._base_only and variant_name != 'Base':
                return False
            if self._variants_only and variant_name == 'Base':
                return False

        # Folder filter - uses multi-folder membership (FoldersV2Role)
        if self._folder_ids:
            # Recursive folder filtering (check if asset is in ANY of the folder IDs)
            folders_v2 = source_model.data(index, AssetRole.FoldersV2Role)
            if folders_v2:
                asset_folder_ids = {f.get('id') for f in folders_v2 if f.get('id')}
                if not asset_folder_ids.intersection(self._folder_ids):
                    return False
            else:
                # Fallback to legacy folder_id for assets not yet migrated
                folder_id = source_model.data(index, AssetRole.FolderIdRole)
                if folder_id not in self._folder_ids:
                    return False
        elif self._folder_id is not None:
            # Single folder filtering - check multi-folder membership
            folders_v2 = source_model.data(index, AssetRole.FoldersV2Role)
            if folders_v2:
                asset_folder_ids = {f.get('id') for f in folders_v2 if f.get('id')}
                if self._folder_id not in asset_folder_ids:
                    return False
            else:
                # Fallback to legacy folder_id for assets not yet migrated
                folder_id = source_model.data(index, AssetRole.FolderIdRole)
                if folder_id != self._folder_id:
                    return False

        # Asset type filter
        if self._filter_asset_types:
            asset_type = source_model.data(index, AssetRole.AssetTypeRole)
            if asset_type not in self._filter_asset_types:
                return False

        # Physical path filter (for subfolder filtering)
        if self._filter_physical_path:
            blend_path = source_model.data(index, AssetRole.BlendBackupPathRole)
            if not blend_path:
                return False
            # Normalize path and check if it starts with the filter prefix
            normalized_blend = blend_path.replace('/', '\\')
            if not normalized_blend.startswith(self._filter_physical_path):
                return False

        # Status filter
        if self._filter_statuses:
            status = source_model.data(index, AssetRole.StatusRole)
            if status not in self._filter_statuses:
                return False

        # Version filter (show only latest by default)
        if self._show_only_latest:
            is_latest = source_model.data(index, AssetRole.IsLatestRole)
            if is_latest is not None and not is_latest:
                return False

        # Tag filter (legacy - asset must have ALL specified tag names)
        if self._filter_tags:
            asset_tags = source_model.data(index, AssetRole.TagsRole)
            if not asset_tags:
                return False
            asset_tag_set = set(asset_tags)
            if not self._filter_tags.issubset(asset_tag_set):
                return False

        # Tag ID filter (new - asset must have ANY of the specified tag IDs)
        if self._filter_tag_ids:
            tags_v2 = source_model.data(index, AssetRole.TagsV2Role)
            if not tags_v2:
                return False
            asset_tag_ids = {tag.get('id') for tag in tags_v2 if tag.get('id')}
            # Check if any of the filter tags match
            if not asset_tag_ids.intersection(self._filter_tag_ids):
                return False

        # Search text filter
        if self._search_text:
            # Search in name
            name = source_model.data(index, AssetRole.NameRole)
            if name and self._search_text in name.lower():
                return True

            # Search in description
            description = source_model.data(index, AssetRole.DescriptionRole)
            if description and self._search_text in description.lower():
                return True

            # Search in tags
            tags = source_model.data(index, AssetRole.TagsRole)
            if tags:
                for tag in tags:
                    if self._search_text in tag.lower():
                        return True

            # Search in asset type
            asset_type = source_model.data(index, AssetRole.AssetTypeRole)
            if asset_type and self._search_text in asset_type.lower():
                return True

            # Not found in any searchable field
            return False

        # No filters active or all filters passed
        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        """
        Compare items for sorting based on current sort configuration

        Args:
            left: Left index
            right: Right index

        Returns:
            True if left < right
        """
        source_model = self.sourceModel()
        if not source_model:
            return False

        # When group by family is enabled, sort by asset_id first, then variant
        if self._group_by_family:
            left_asset_id = source_model.data(left, AssetRole.AssetIdRole) or ''
            right_asset_id = source_model.data(right, AssetRole.AssetIdRole) or ''
            left_variant = source_model.data(left, AssetRole.VariantNameRole) or 'Base'
            right_variant = source_model.data(right, AssetRole.VariantNameRole) or 'Base'

            # Different families - sort by asset_id to keep families grouped together
            if left_asset_id != right_asset_id:
                # Compare asset_ids directly - this groups all items with same asset_id together
                result = str(left_asset_id) < str(right_asset_id)
                if self._sort_order == "DESC":
                    return not result
                return result

            # Same family (same asset_id) - Base comes first, then variants alphabetically
            # Base always comes first within a family
            if left_variant == 'Base' and right_variant != 'Base':
                return True  # Base comes before variant
            if left_variant != 'Base' and right_variant == 'Base':
                return False  # Variant comes after Base

            # Both are variants (not Base) - sort alphabetically by variant name
            if left_variant != right_variant:
                return str(left_variant).lower() < str(right_variant).lower()

            # Same variant name - fall through to normal sorting

        # Map sort_by to AssetRole
        role_map = {
            "name": AssetRole.NameRole,
            "created_date": AssetRole.CreatedDateRole,
            "modified_date": AssetRole.ModifiedDateRole,
            "file_size": AssetRole.FileSizeMBRole,
            "polygon_count": AssetRole.PolygonCountRole,
            "last_viewed_date": AssetRole.LastViewedDateRole,
        }

        role = role_map.get(self._sort_by, AssetRole.NameRole)

        left_value = source_model.data(left, role)
        right_value = source_model.data(right, role)

        # Handle None values (put them at the end)
        if left_value is None and right_value is None:
            return False
        if left_value is None:
            return self._sort_order == "DESC"
        if right_value is None:
            return self._sort_order == "ASC"

        # Compare based on type
        if self._sort_by == "name":
            # Case-insensitive string comparison
            result = str(left_value).lower() < str(right_value).lower()
        else:
            # Numeric or date comparison
            result = left_value < right_value

        # Reverse for DESC order
        if self._sort_order == "DESC":
            return not result

        return result

    # ==================== GETTERS FOR CURRENT FILTERS ====================

    def get_search_text(self) -> str:
        """Get current search text"""
        return self._search_text

    def get_folder_filter(self) -> Optional[int]:
        """Get current folder filter"""
        return self._folder_id

    def get_tag_filter(self) -> Set[str]:
        """Get current tag filter"""
        return self._filter_tags.copy()

    def get_asset_type_filter(self) -> Set[str]:
        """Get current asset type filter"""
        return self._filter_asset_types.copy()

    def get_status_filter(self) -> Set[str]:
        """Get current status filter"""
        return self._filter_statuses.copy()

    def is_showing_only_latest(self) -> bool:
        """Check if showing only latest versions"""
        return self._show_only_latest

    def is_favorites_only(self) -> bool:
        """Check if favorites only filter is active"""
        return self._favorites_only

    def is_recent_only(self) -> bool:
        """Check if recent only filter is active"""
        return self._recent_only

    def is_cold_storage_only(self) -> bool:
        """Check if cold storage only filter is active"""
        return self._cold_storage_only

    def has_active_filters(self) -> bool:
        """Check if any filters are active"""
        return bool(
            self._search_text or
            self._folder_id is not None or
            self._filter_tags or
            self._filter_asset_types or
            self._filter_statuses or
            self._favorites_only or
            self._recent_only or
            self._cold_storage_only or
            self._needs_review_only or
            self._in_review_only or
            self._in_progress_only or
            self._approved_only or
            self._final_only
        )

    def is_needs_review_only(self) -> bool:
        """Check if needs review only filter is active"""
        return self._needs_review_only

    def is_in_review_only(self) -> bool:
        """Check if in review only filter is active"""
        return self._in_review_only

    def is_in_progress_only(self) -> bool:
        """Check if in progress only filter is active"""
        return self._in_progress_only

    def is_approved_only(self) -> bool:
        """Check if approved only filter is active"""
        return self._approved_only

    def is_final_only(self) -> bool:
        """Check if final only filter is active"""
        return self._final_only

    def is_any_review_filter(self) -> bool:
        """Check if any review filter is active"""
        return (self._needs_review_only or self._in_review_only or
                self._in_progress_only or self._approved_only or self._final_only)


__all__ = ['AssetFilterProxyModel']
