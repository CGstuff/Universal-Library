"""
Variant management for version history dialog.

Handles creating new variants from Base versions.
"""

import shutil
import uuid as uuid_module
from pathlib import Path
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import QMessageBox, QWidget, QDialog

from ....config import Config


class VariantManager:
    """
    Manages variant creation workflow.

    Handles:
    - Loading asset info and variants
    - Creating new variants from Base versions
    - File operations for variant creation
    """

    def __init__(
        self,
        parent: QWidget,
        db_service,
        version_group_id: str
    ):
        """
        Initialize variant manager.

        Args:
            parent: Parent widget for dialogs
            db_service: Database service
            version_group_id: Initial version group ID
        """
        self._parent = parent
        self._db_service = db_service
        self._version_group_id = version_group_id

        self._asset_id: Optional[str] = None
        self._variants: List[Dict[str, Any]] = []
        self._all_variants_data: List[Dict[str, Any]] = []
        self._current_variant: str = "Base"

    @property
    def asset_id(self) -> Optional[str]:
        """Get current asset ID."""
        return self._asset_id

    @property
    def variants(self) -> List[Dict[str, Any]]:
        """Get list of variants."""
        return self._variants

    @property
    def all_variants_data(self) -> List[Dict[str, Any]]:
        """Get all variant version data."""
        return self._all_variants_data

    def load_asset_info(self):
        """Load asset info to get asset_id from version_group_id."""
        versions = self._db_service.get_version_history(self._version_group_id)
        if versions:
            first = versions[0]
            self._asset_id = first.get('asset_id') or first.get('version_group_id')
            self._current_variant = first.get('variant_name', 'Base')

    def load_variants(self):
        """Load all variants for this asset."""
        if not self._asset_id:
            return
        self._variants = self._db_service.get_variants(self._asset_id)

    def load_all_variants_data(self):
        """Load all versions across all variants for tree view."""
        if not self._asset_id:
            return

        self._all_variants_data = []
        for variant in self._variants:
            vgid = variant.get('version_group_id')
            if vgid:
                versions = self._db_service.get_version_history(vgid)
                for v in versions:
                    v['_variant_name'] = variant.get('variant_name', 'Base')
                    self._all_variants_data.append(v)

    def create_new_variant(
        self,
        selected_uuid: str,
        version: Dict[str, Any],
        variant_name: str,
        variant_set: str,
        on_success: callable
    ) -> bool:
        """
        Create a new variant from a selected version.

        Args:
            selected_uuid: UUID of source version
            version: Source version data
            variant_name: Name for new variant
            variant_set: Variant set name
            on_success: Callback on success

        Returns:
            True if variant created successfully
        """
        # Check if variant already exists
        for variant in self._variants:
            if variant.get('variant_name') == variant_name:
                QMessageBox.warning(
                    self._parent,
                    "Variant Exists",
                    f"A variant named '{variant_name}' already exists."
                )
                return False

        # Get source paths
        blend_path = version.get('blend_backup_path')
        thumbnail_path = version.get('thumbnail_path')

        blend_exists = blend_path and Path(blend_path).exists()
        thumb_exists = thumbnail_path and Path(thumbnail_path).exists()

        if not blend_exists:
            QMessageBox.warning(
                self._parent,
                "Source File Missing",
                f"Cannot create variant: source .blend file not found.\n\n"
                f"Expected path:\n{blend_path}\n\n"
                f"This can happen if the asset was exported with a different folder structure. "
                f"Please re-export the source asset from Blender first."
            )
            return False

        asset_name = version.get('name', 'Asset')
        asset_type = version.get('asset_type', 'mesh')

        # Create new variant folder
        try:
            library_folder = Config.get_asset_library_path(
                self._asset_id, asset_name, variant_name, asset_type
            )
            library_folder.mkdir(parents=True, exist_ok=True)
        except ValueError:
            QMessageBox.warning(self._parent, "Error", "Library path not configured.")
            return False

        try:
            # Copy files (versioned - new variant starts at v001)
            new_version_label = "v001"
            new_blend = library_folder / f"{asset_name}.{new_version_label}.blend"
            shutil.copy2(blend_path, new_blend)

            if thumb_exists:
                new_thumbnail = library_folder / f"thumbnail.{new_version_label}.png"
                shutil.copy2(thumbnail_path, new_thumbnail)
            else:
                new_thumbnail = None

            # Prepare asset data
            new_uuid = str(uuid_module.uuid4())
            asset_data = {
                'uuid': new_uuid,
                'name': asset_name,
                'description': version.get('description', ''),
                'folder_id': version.get('folder_id', 1),
                'asset_type': version.get('asset_type', 'mesh'),
                'blend_backup_path': str(new_blend) if new_blend else None,
                'thumbnail_path': str(new_thumbnail) if new_thumbnail else None,
                'file_size_mb': version.get('file_size_mb', 0),
                'polygon_count': version.get('polygon_count'),
                'material_count': version.get('material_count'),
                'has_materials': version.get('has_materials', 0),
                'has_skeleton': version.get('has_skeleton', 0),
                'has_animations': version.get('has_animations', 0),
                'source_application': version.get('source_application', 'Unknown'),
                'representation_type': version.get('representation_type', 'none'),
                'variant_set': variant_set,
                # Versioning fields - new variant starts at v001
                'version': 1,
                'version_label': new_version_label,
                'is_latest': 1,
            }

            # Create in database
            result = self._db_service.create_new_variant(
                selected_uuid, variant_name, asset_data, variant_set
            )

            if result:
                version_label = version.get('version_label', 'Unknown')
                QMessageBox.information(
                    self._parent,
                    "Variant Created",
                    f"Variant '{variant_name}' created successfully from {version_label}.\n"
                    f"VariantSet: {variant_set}"
                )
                self._current_variant = variant_name
                on_success()
                return True
            else:
                QMessageBox.warning(self._parent, "Error", "Failed to create variant.")
                if library_folder.exists():
                    shutil.rmtree(library_folder, ignore_errors=True)
                return False

        except Exception as e:
            QMessageBox.warning(self._parent, "Error", f"Failed to create variant: {str(e)}")
            import traceback
            traceback.print_exc()
            if library_folder.exists():
                shutil.rmtree(library_folder, ignore_errors=True)
            return False


__all__ = ['VariantManager']
