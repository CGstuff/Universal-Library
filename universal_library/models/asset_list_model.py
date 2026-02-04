"""
AssetListModel - Qt Model for USD asset data

Pattern: Model/View architecture with QAbstractListModel
Based on animation_library architecture.
"""

import time
from enum import IntEnum
from typing import List, Dict, Any, Optional
from PyQt6.QtCore import (
    QAbstractListModel, QModelIndex, Qt, QMimeData, QByteArray
)


class AssetRole(IntEnum):
    """Custom Qt roles for USD asset data"""

    # Required fields
    UUIDRole = Qt.ItemDataRole.UserRole + 1
    NameRole = Qt.ItemDataRole.UserRole + 2
    FolderIdRole = Qt.ItemDataRole.UserRole + 3
    AssetTypeRole = Qt.ItemDataRole.UserRole + 4

    # USD-specific
    UsdFilePathRole = Qt.ItemDataRole.UserRole + 10
    BlendBackupPathRole = Qt.ItemDataRole.UserRole + 11
    FileSizeMBRole = Qt.ItemDataRole.UserRole + 12
    HasMaterialsRole = Qt.ItemDataRole.UserRole + 13
    HasSkeletonRole = Qt.ItemDataRole.UserRole + 14
    HasAnimationsRole = Qt.ItemDataRole.UserRole + 15
    PolygonCountRole = Qt.ItemDataRole.UserRole + 16
    MaterialCountRole = Qt.ItemDataRole.UserRole + 17

    # File paths
    ThumbnailPathRole = Qt.ItemDataRole.UserRole + 30
    PreviewPathRole = Qt.ItemDataRole.UserRole + 31

    # Organization
    DescriptionRole = Qt.ItemDataRole.UserRole + 40
    TagsRole = Qt.ItemDataRole.UserRole + 41
    AuthorRole = Qt.ItemDataRole.UserRole + 42
    SourceApplicationRole = Qt.ItemDataRole.UserRole + 43

    # Timestamps
    CreatedDateRole = Qt.ItemDataRole.UserRole + 60
    ModifiedDateRole = Qt.ItemDataRole.UserRole + 61

    # User features
    IsFavoriteRole = Qt.ItemDataRole.UserRole + 70
    LastViewedDateRole = Qt.ItemDataRole.UserRole + 71
    CustomOrderRole = Qt.ItemDataRole.UserRole + 72
    IsLockedRole = Qt.ItemDataRole.UserRole + 73

    # Lifecycle status
    StatusRole = Qt.ItemDataRole.UserRole + 80

    # Versioning
    VersionRole = Qt.ItemDataRole.UserRole + 85
    VersionLabelRole = Qt.ItemDataRole.UserRole + 86
    VersionGroupIdRole = Qt.ItemDataRole.UserRole + 87
    IsLatestRole = Qt.ItemDataRole.UserRole + 88

    # Cold Storage
    IsColdRole = Qt.ItemDataRole.UserRole + 90
    ColdStoragePathRole = Qt.ItemDataRole.UserRole + 91
    IsImmutableRole = Qt.ItemDataRole.UserRole + 92
    RepresentationTypeRole = Qt.ItemDataRole.UserRole + 93

    # Variant system
    AssetIdRole = Qt.ItemDataRole.UserRole + 94
    VariantNameRole = Qt.ItemDataRole.UserRole + 95
    VariantSourceUuidRole = Qt.ItemDataRole.UserRole + 96
    SourceAssetNameRole = Qt.ItemDataRole.UserRole + 101
    SourceVersionLabelRole = Qt.ItemDataRole.UserRole + 102
    VariantSetRole = Qt.ItemDataRole.UserRole + 103

    # Version notes (changelog)
    VersionNotesRole = Qt.ItemDataRole.UserRole + 104

    # Variant count (number of variants excluding Base)
    VariantCountRole = Qt.ItemDataRole.UserRole + 105

    # Rich tag data (list of dicts with id, name, color)
    TagsV2Role = Qt.ItemDataRole.UserRole + 97

    # Rich folder data (list of dicts with id, name, path) - multi-folder membership
    FoldersV2Role = Qt.ItemDataRole.UserRole + 98

    # Complete data dict
    AssetDataRole = Qt.ItemDataRole.UserRole + 100

    # Comment/Review indicators
    HasUnresolvedCommentsRole = Qt.ItemDataRole.UserRole + 110
    UnresolvedCommentCountRole = Qt.ItemDataRole.UserRole + 111

    # Review workflow state
    ReviewStateRole = Qt.ItemDataRole.UserRole + 112  # 'needs_review', 'in_review', 'in_progress', 'approved', 'final', or None


class AssetListModel(QAbstractListModel):
    """
    Qt model for USD asset list

    Features:
    - Lightweight data storage
    - Custom Qt roles for all fields
    - Sparse data access with .get()
    - Performance logging
    - Drag & drop support

    Usage:
        model = AssetListModel()
        model.set_assets(asset_list)
        view.setModel(model)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._assets: List[Dict[str, Any]] = []

        # Variant counts cache (asset_id -> count)
        self._variant_counts: Dict[str, int] = {}

        # Performance monitoring
        self._load_time: float = 0.0
        self._data_access_count: int = 0

    def set_assets(self, assets: List[Dict[str, Any]]):
        """
        Set asset data

        Args:
            assets: List of asset dicts from database
        """
        start_time = time.time()

        self.beginResetModel()
        self._assets = assets
        self.endResetModel()

        self._load_time = (time.time() - start_time) * 1000  # Convert to ms

    def set_variant_counts(self, counts: Dict[str, int]):
        """
        Set variant counts cache

        Args:
            counts: Dict mapping asset_id to variant count
        """
        self._variant_counts = counts

    def append_asset(self, asset: Dict[str, Any]):
        """
        Append single asset to model

        Args:
            asset: Asset data dict
        """
        row = len(self._assets)
        self.beginInsertRows(QModelIndex(), row, row)
        self._assets.append(asset)
        self.endInsertRows()

    def remove_asset(self, uuid: str) -> bool:
        """
        Remove asset by UUID

        Args:
            uuid: Asset UUID

        Returns:
            True if removed, False if not found
        """
        for i, asset in enumerate(self._assets):
            if asset.get('uuid') == uuid:
                self.beginRemoveRows(QModelIndex(), i, i)
                del self._assets[i]
                self.endRemoveRows()
                return True
        return False

    def update_asset(self, uuid: str, updates: Dict[str, Any]) -> bool:
        """
        Update asset data

        Args:
            uuid: Asset UUID
            updates: Dict of fields to update

        Returns:
            True if updated, False if not found
        """
        for i, asset in enumerate(self._assets):
            if asset.get('uuid') == uuid:
                asset.update(updates)
                # Emit dataChanged for this row
                index = self.index(i, 0)
                self.dataChanged.emit(index, index)
                return True
        return False

    def refresh_asset(self, uuid: str) -> bool:
        """
        Refresh asset data from database

        Args:
            uuid: Asset UUID

        Returns:
            True if refreshed, False if not found
        """
        from ..services.database_service import get_database_service

        db_service = get_database_service()
        updated_data = db_service.get_asset_by_uuid(uuid)

        if updated_data:
            # Enrich with tags_v2 and folders_v2 (not in raw database row)
            updated_data['tags_v2'] = db_service.get_asset_tags(uuid)
            updated_data['folders_v2'] = db_service.get_asset_folders(uuid)
            
            for i, asset in enumerate(self._assets):
                if asset.get('uuid') == uuid:
                    self._assets[i] = updated_data
                    # Emit dataChanged for this row
                    index = self.index(i, 0)
                    self.dataChanged.emit(index, index)
                    return True
        return False

    def get_asset_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get asset data by UUID

        Args:
            uuid: Asset UUID

        Returns:
            Asset dict or None
        """
        for asset in self._assets:
            if asset.get('uuid') == uuid:
                return asset
        return None

    def get_asset_at_index(self, row: int) -> Optional[Dict[str, Any]]:
        """
        Get asset data at row index

        Args:
            row: Row index

        Returns:
            Asset dict or None
        """
        if 0 <= row < len(self._assets):
            return self._assets[row]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:
        """Return number of assets"""
        if parent.isValid():
            return 0
        return len(self._assets)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """
        Get data for index and role

        Args:
            index: Model index
            role: Data role

        Returns:
            Data for role or None
        """
        if not index.isValid() or index.row() >= len(self._assets):
            return None

        asset = self._assets[index.row()]
        self._data_access_count += 1

        # Sparse data access - use .get() for optional fields
        if role == Qt.ItemDataRole.DisplayRole:
            return asset.get('name', 'Unknown')

        elif role == AssetRole.UUIDRole:
            return asset.get('uuid')

        elif role == AssetRole.NameRole:
            return asset.get('name', 'Unknown')

        elif role == AssetRole.FolderIdRole:
            return asset.get('folder_id')

        elif role == AssetRole.AssetTypeRole:
            return asset.get('asset_type', 'model')

        elif role == AssetRole.UsdFilePathRole:
            return asset.get('usd_file_path')

        elif role == AssetRole.BlendBackupPathRole:
            return asset.get('blend_backup_path')

        elif role == AssetRole.FileSizeMBRole:
            return asset.get('file_size_mb')

        elif role == AssetRole.HasMaterialsRole:
            return asset.get('has_materials', 0)

        elif role == AssetRole.HasSkeletonRole:
            return asset.get('has_skeleton', 0)

        elif role == AssetRole.HasAnimationsRole:
            return asset.get('has_animations', 0)

        elif role == AssetRole.PolygonCountRole:
            return asset.get('polygon_count')

        elif role == AssetRole.MaterialCountRole:
            return asset.get('material_count')

        elif role == AssetRole.ThumbnailPathRole:
            return asset.get('thumbnail_path')

        elif role == AssetRole.PreviewPathRole:
            return asset.get('preview_path')

        elif role == AssetRole.DescriptionRole:
            return asset.get('description', '')

        elif role == AssetRole.TagsRole:
            return asset.get('tags', [])

        elif role == AssetRole.AuthorRole:
            return asset.get('author', '')

        elif role == AssetRole.SourceApplicationRole:
            return asset.get('source_application', 'Unknown')

        elif role == AssetRole.CreatedDateRole:
            return asset.get('created_date')

        elif role == AssetRole.ModifiedDateRole:
            return asset.get('modified_date')

        elif role == AssetRole.IsFavoriteRole:
            return asset.get('is_favorite', 0)

        elif role == AssetRole.LastViewedDateRole:
            return asset.get('last_viewed_date')

        elif role == AssetRole.CustomOrderRole:
            return asset.get('custom_order')

        elif role == AssetRole.IsLockedRole:
            return asset.get('is_locked', 0)

        elif role == AssetRole.StatusRole:
            return asset.get('status', 'wip')

        elif role == AssetRole.VersionRole:
            return asset.get('version', 1)

        elif role == AssetRole.VersionLabelRole:
            return asset.get('version_label', 'v001')

        elif role == AssetRole.VersionGroupIdRole:
            return asset.get('version_group_id')

        elif role == AssetRole.IsLatestRole:
            return asset.get('is_latest', 1)

        elif role == AssetRole.IsColdRole:
            return asset.get('is_cold', 0)

        elif role == AssetRole.ColdStoragePathRole:
            return asset.get('cold_storage_path')

        elif role == AssetRole.IsImmutableRole:
            return asset.get('is_immutable', 0)

        elif role == AssetRole.RepresentationTypeRole:
            return asset.get('representation_type', 'final')

        elif role == AssetRole.AssetIdRole:
            return asset.get('asset_id', asset.get('version_group_id'))

        elif role == AssetRole.VariantNameRole:
            return asset.get('variant_name', 'Base')

        elif role == AssetRole.VariantSourceUuidRole:
            return asset.get('variant_source_uuid')

        elif role == AssetRole.SourceAssetNameRole:
            return asset.get('source_asset_name')

        elif role == AssetRole.SourceVersionLabelRole:
            return asset.get('source_version_label')

        elif role == AssetRole.VariantSetRole:
            return asset.get('variant_set')

        elif role == AssetRole.VersionNotesRole:
            return asset.get('version_notes', '')

        elif role == AssetRole.VariantCountRole:
            asset_id = asset.get('asset_id')
            if asset_id:
                return self._variant_counts.get(asset_id, 0)
            return 0

        elif role == AssetRole.TagsV2Role:
            # Return rich tag data (list of dicts with id, name, color)
            return asset.get('tags_v2', [])

        elif role == AssetRole.FoldersV2Role:
            # Return rich folder data (list of dicts with id, name, path)
            return asset.get('folders_v2', [])

        elif role == AssetRole.AssetDataRole:
            return asset

        elif role == AssetRole.HasUnresolvedCommentsRole:
            return asset.get('has_unresolved_comments', False)

        elif role == AssetRole.UnresolvedCommentCountRole:
            return asset.get('unresolved_comment_count', 0)

        elif role == AssetRole.ReviewStateRole:
            return asset.get('review_state')  # 'needs_review', 'in_review', 'in_progress', 'approved', 'final', or None

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """
        Return item flags for drag & drop support

        Args:
            index: Model index

        Returns:
            Item flags
        """
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return (
            Qt.ItemFlag.ItemIsEnabled |
            Qt.ItemFlag.ItemIsSelectable |
            Qt.ItemFlag.ItemIsDragEnabled
        )

    def supportedDragActions(self) -> Qt.DropAction:
        """Return supported drag actions"""
        return Qt.DropAction.CopyAction | Qt.DropAction.MoveAction

    def mimeTypes(self) -> List[str]:
        """Return supported MIME types for drag & drop"""
        return ['application/x-asset-uuid']

    def mimeData(self, indexes: List[QModelIndex]) -> QMimeData:
        """
        Create MIME data for drag operation

        Args:
            indexes: List of dragged indexes

        Returns:
            MIME data with asset UUIDs
        """
        mime_data = QMimeData()
        uuids = []

        for index in indexes:
            if index.isValid():
                uuid = self.data(index, AssetRole.UUIDRole)
                if uuid:
                    uuids.append(uuid)

        # Encode as newline-separated UUIDs
        mime_data.setData('application/x-asset-uuid', QByteArray('\n'.join(uuids).encode()))
        return mime_data

    # ==================== PERFORMANCE MONITORING ====================

    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics

        Returns:
            Dict with performance metrics
        """
        return {
            'asset_count': len(self._assets),
            'load_time_ms': self._load_time,
            'data_access_count': self._data_access_count,
        }

    def reset_performance_stats(self):
        """Reset performance counters"""
        self._data_access_count = 0
        self._load_time = 0.0


__all__ = ['AssetListModel', 'AssetRole']
