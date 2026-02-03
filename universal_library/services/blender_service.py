"""
Blender Service - Manages communication with Blender addon

Handles queuing import requests to be picked up by the Blender addon.
Uses file-based IPC through a temp directory queue.

Now uses the protocol module for schema-driven message building.
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from ..protocol import build_message, QUEUE_DIR_NAME


class BlenderService:
    """
    Service for communicating with the Blender addon.

    Uses a file-based queue system where:
    1. Desktop app writes JSON request files to temp directory
    2. Blender addon polls the directory and processes requests
    3. Blender addon deletes processed files

    Usage:
        service = BlenderService.get_instance()
        service.queue_import_asset(
            uuid="xxx-xxx",
            asset_name="Cube",
            usd_file_path="/path/to/asset.usdc",
            import_method="BLEND",
            link_mode="APPEND"
        )
    """

    _instance: Optional['BlenderService'] = None

    @classmethod
    def get_instance(cls) -> 'BlenderService':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize the Blender service"""
        self._queue_dir = Path(tempfile.gettempdir()) / QUEUE_DIR_NAME
        self._ensure_queue_dir()

    def _ensure_queue_dir(self):
        """Ensure queue directory exists"""
        self._queue_dir.mkdir(parents=True, exist_ok=True)

    @property
    def queue_directory(self) -> Path:
        """Get the queue directory path"""
        return self._queue_dir

    def queue_import_asset(
        self,
        uuid: str,
        asset_name: str,
        usd_file_path: str,
        blend_file_path: Optional[str] = None,
        import_method: str = "BLEND",
        link_mode: str = "APPEND",
        keep_location: bool = True,
        asset_type: str = "model",
        # Versioning fields
        version_group_id: Optional[str] = None,
        version: int = 1,
        version_label: str = "v001",
        representation_type: str = "none",
        # Variant system fields
        asset_id: Optional[str] = None,
        variant_name: str = "Base"
    ) -> bool:
        """
        Queue an asset import request for Blender.

        Args:
            uuid: Asset UUID
            asset_name: Display name of the asset
            usd_file_path: Path to the USD file
            blend_file_path: Optional path to .blend backup file
            import_method: "USD" or "BLEND"
            link_mode: "APPEND" or "LINK"
            keep_location: Whether to preserve original location
            asset_type: Type of asset ("model", "material", "rig", etc.)
            version_group_id: Version group ID (for linking versions)
            version: Version number
            version_label: Version label (e.g., "v001")
            representation_type: Representation type (model, lookdev, rig, final)

        Returns:
            True if request was queued successfully
        """
        self._ensure_queue_dir()

        # Build metadata dict for protocol
        metadata: Dict[str, Any] = {
            "uuid": uuid,
            "name": asset_name,
            "asset_type": asset_type,
            "version_group_id": version_group_id or uuid,
            "version": version,
            "version_label": version_label,
            "representation_type": representation_type,
            "asset_id": asset_id or version_group_id or uuid,
            "variant_name": variant_name,
            "usd_file_path": usd_file_path,
            "blend_file_path": blend_file_path,
            "import_method": import_method,
            "link_mode": link_mode,
            "keep_location": keep_location,
        }

        # Build message using protocol schema
        try:
            request = build_message("import_asset", metadata)
        except Exception as e:
            return False

        # Write to queue file with unique name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        queue_file = self._queue_dir / f"import_{timestamp}.json"

        try:
            with open(queue_file, 'w', encoding='utf-8') as f:
                json.dump(request, f, indent=2)
            return True
        except Exception as e:
            return False

    def queue_replace_asset(
        self,
        uuid: str,
        asset_name: str,
        usd_file_path: str,
        blend_file_path: Optional[str] = None,
        import_method: str = "BLEND",
        link_mode: str = "APPEND",
        keep_location: bool = True,
        asset_type: str = "model",
        version_group_id: Optional[str] = None,
        version: int = 1,
        version_label: str = "v001",
        representation_type: str = "none",
        asset_id: Optional[str] = None,
        variant_name: str = "Base"
    ) -> bool:
        """
        Queue a replace-selected request for Blender.

        Same as queue_import_asset but with command:"replace" so the
        Blender addon replaces selected objects instead of adding new ones.

        Returns:
            True if request was queued successfully
        """
        self._ensure_queue_dir()

        metadata: Dict[str, Any] = {
            "uuid": uuid,
            "name": asset_name,
            "asset_type": asset_type,
            "version_group_id": version_group_id or uuid,
            "version": version,
            "version_label": version_label,
            "representation_type": representation_type,
            "asset_id": asset_id or version_group_id or uuid,
            "variant_name": variant_name,
            "usd_file_path": usd_file_path,
            "blend_file_path": blend_file_path,
            "import_method": import_method,
            "link_mode": link_mode,
            "keep_location": keep_location,
        }

        try:
            request = build_message("import_asset", metadata)
        except Exception as e:
            return False

        # Mark as replace command - use replace_any to support plain empties (scatter workflows)
        request["command"] = "replace_any"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        queue_file = self._queue_dir / f"import_{timestamp}.json"

        try:
            with open(queue_file, 'w', encoding='utf-8') as f:
                json.dump(request, f, indent=2)
            return True
        except Exception as e:
            return False

    def queue_regenerate_thumbnail(
        self,
        uuid: str,
        asset_name: str,
        usd_file_path: str,
        thumbnail_path: str
    ) -> bool:
        """
        Queue a thumbnail regeneration request for Blender.

        Args:
            uuid: Asset UUID
            asset_name: Display name of the asset
            usd_file_path: Path to the USD file to render
            thumbnail_path: Path where thumbnail should be saved

        Returns:
            True if request was queued successfully
        """
        self._ensure_queue_dir()

        # Build metadata dict for protocol
        metadata: Dict[str, Any] = {
            "uuid": uuid,
            "name": asset_name,
            "usd_file_path": usd_file_path,
            "thumbnail_path": thumbnail_path,
        }

        # Build message using protocol schema
        try:
            request = build_message("regenerate_thumbnail", metadata)
        except Exception as e:
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        queue_file = self._queue_dir / f"thumbnail_{timestamp}.json"

        try:
            with open(queue_file, 'w', encoding='utf-8') as f:
                json.dump(request, f, indent=2)
            return True
        except Exception as e:
            return False

    def get_queue_status(self) -> dict:
        """
        Get status of pending requests.

        Returns:
            Dictionary with queue status info
        """
        self._ensure_queue_dir()

        pending_files = list(self._queue_dir.glob("import_*.json"))

        return {
            "queue_dir": str(self._queue_dir),
            "pending_count": len(pending_files),
            "pending_files": [f.name for f in pending_files]
        }

    def clear_queue(self):
        """Clear all pending requests (for testing/debugging)"""
        self._ensure_queue_dir()

        for f in self._queue_dir.glob("import_*.json"):
            try:
                f.unlink()
            except Exception:
                pass


def get_blender_service() -> BlenderService:
    """Get the BlenderService singleton instance"""
    return BlenderService.get_instance()


__all__ = ['BlenderService', 'get_blender_service']
