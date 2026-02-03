"""
AssetTreeModel - Hierarchical model grouping assets by family (base + variants)

Pattern: QStandardItemModel with parent-child hierarchy
Builds tree from flat asset data: Base assets as parents, variants as children.
"""

from typing import List, Dict, Any, Optional
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt


# Custom data roles for tree items
TREE_ASSET_ROLE = Qt.ItemDataRole.UserRole      # Full asset dict
TREE_UUID_ROLE = Qt.ItemDataRole.UserRole + 1    # Asset UUID shortcut
TREE_IS_PARENT = Qt.ItemDataRole.UserRole + 2    # True if parent row


class AssetTreeModel(QStandardItemModel):
    """
    Hierarchical model for asset family tree view.

    Groups assets by asset_id (family). For each family:
    - The latest Base version becomes the parent row
    - Latest variants become child rows under their base
    - Solo assets (no variants) are top-level with no children

    Only shows latest versions (is_latest=1).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._uuid_to_item: Dict[str, QStandardItem] = {}

    def build_from_assets(self, assets: List[Dict[str, Any]],
                          variant_counts: Optional[Dict[str, int]] = None):
        """
        Rebuild the tree from a flat asset list.

        Args:
            assets: List of asset dicts (already filtered by the proxy model).
                    Should only contain is_latest=1 assets.
            variant_counts: Optional dict mapping asset_id to variant count.
        """
        self.clear()
        self._uuid_to_item.clear()

        if not assets:
            return

        variant_counts = variant_counts or {}

        # Group assets by asset_id (family identifier)
        families: Dict[str, List[Dict]] = {}
        for asset in assets:
            # Determine family key: asset_id > version_group_id > uuid
            family_key = (
                asset.get('asset_id')
                or asset.get('version_group_id')
                or asset.get('uuid', '')
            )
            families.setdefault(family_key, []).append(asset)

        # Build tree rows
        for family_key, members in families.items():
            # Separate base and variants
            base = None
            variants = []

            for m in members:
                vname = m.get('variant_name', 'Base')
                if vname == 'Base':
                    # Pick latest base (highest version)
                    if base is None or (m.get('version', 0) > base.get('version', 0)):
                        base = m
                else:
                    variants.append(m)

            # If no Base found, use first member as parent
            if base is None:
                base = members[0]
                variants = members[1:]

            # Inject variant count into base data for delegate
            base_with_count = dict(base)
            base_with_count['_variant_count'] = variant_counts.get(
                base.get('asset_id', ''), len(variants)
            )

            # Create parent item
            parent_item = QStandardItem()
            parent_item.setData(base_with_count, TREE_ASSET_ROLE)
            parent_item.setData(base.get('uuid', ''), TREE_UUID_ROLE)
            parent_item.setData(True, TREE_IS_PARENT)
            parent_item.setEditable(False)

            # Track UUID -> item
            uuid = base.get('uuid', '')
            if uuid:
                self._uuid_to_item[uuid] = parent_item

            # Add variant children (sorted by variant name)
            variants.sort(key=lambda v: (v.get('variant_name', '') or '').lower())
            for variant in variants:
                child_item = QStandardItem()
                child_item.setData(variant, TREE_ASSET_ROLE)
                child_item.setData(variant.get('uuid', ''), TREE_UUID_ROLE)
                child_item.setData(False, TREE_IS_PARENT)
                child_item.setEditable(False)
                parent_item.appendRow(child_item)

                vuuid = variant.get('uuid', '')
                if vuuid:
                    self._uuid_to_item[vuuid] = child_item

            self.appendRow(parent_item)

    def get_uuid_for_index(self, index) -> Optional[str]:
        """Get asset UUID for a model index."""
        if not index.isValid():
            return None
        return index.data(TREE_UUID_ROLE)

    def get_asset_for_index(self, index) -> Optional[Dict[str, Any]]:
        """Get full asset dict for a model index."""
        if not index.isValid():
            return None
        return index.data(TREE_ASSET_ROLE)

    def find_index_for_uuid(self, uuid: str):
        """Find the QModelIndex for a given UUID."""
        item = self._uuid_to_item.get(uuid)
        if item:
            return item.index()
        return None


__all__ = ['AssetTreeModel', 'TREE_ASSET_ROLE', 'TREE_UUID_ROLE', 'TREE_IS_PARENT']
