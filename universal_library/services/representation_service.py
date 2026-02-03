"""
RepresentationService - Orchestrates proxy/render representation file creation.

High-level service that coordinates:
- Database writes (representation_designations table)
- File creation (.proxy.blend, .render.blend via CurrentReferenceService)
- Auto-update logic when new versions are created

Emulates USD's Purpose concept (proxy/render) using .blend versioning.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from ..config import Config
from .database_service import get_database_service
from .archive_service import get_archive_service
from .current_reference_service import get_current_reference_service

logger = logging.getLogger(__name__)


class RepresentationService:
    """
    Orchestrates proxy/render representation designation and file management.

    Defaults:
    - Proxy: v001 (first version, typically low-poly blockout)
    - Render: latest version (highest fidelity)
    Both are overridable per asset variant via the desktop UI.
    """

    def __init__(self):
        self._db = get_database_service()
        self._archive = get_archive_service()
        self._current_ref = get_current_reference_service()

    def designate_representations(
        self,
        version_group_id: str,
        variant_name: str = 'Base',
        proxy_uuid: Optional[str] = None,
        render_uuid: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Set proxy and/or render designations for an asset variant.

        Creates .proxy.blend and .render.blend files in the library folder
        pointing to the designated archived versions.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name (default 'Base')
            proxy_uuid: UUID of version to use as proxy (None = v001 default)
            render_uuid: UUID of version to use as render (None = latest default)

        Returns:
            Tuple of (success, message)
        """
        # Resolve the asset info
        versions = self._db.get_asset_versions(version_group_id)
        if not versions:
            return False, "No versions found for this asset"

        # Sort by version number ascending
        versions_sorted = sorted(versions, key=lambda v: v.get('version') or 0)
        latest_version = versions_sorted[-1]
        first_version = versions_sorted[0]

        asset_name = latest_version.get('name')
        asset_type = latest_version.get('asset_type', 'other')
        asset_id = latest_version.get('asset_id') or version_group_id

        # Support mesh and rig types
        if asset_type not in ('mesh', 'rig'):
            return False, "Representation designations are only supported for mesh and rig assets"

        # Resolve proxy version
        if proxy_uuid:
            proxy_version = self._db.get_asset_by_uuid(proxy_uuid)
        else:
            proxy_version = first_version  # Default: v001

        # Resolve render version
        if render_uuid:
            render_version = self._db.get_asset_by_uuid(render_uuid)
        else:
            render_version = latest_version  # Default: latest

        if not proxy_version or not render_version:
            return False, "Could not resolve proxy or render version"

        proxy_label = proxy_version.get('version_label', 'v001')
        render_label = render_version.get('version_label', 'v001')
        proxy_v_uuid = proxy_version.get('uuid')
        render_v_uuid = render_version.get('uuid')

        # Find the archive .blend paths
        logger.debug(
            f"Looking for proxy blend: asset_id={asset_id}, "
            f"asset_name={asset_name}, variant={variant_name}, version={proxy_label}"
        )

        proxy_blend = self._archive.get_version_blend_path(
            asset_id, asset_name, variant_name, proxy_label, asset_type
        )
        render_blend = self._archive.get_version_blend_path(
            asset_id, asset_name, variant_name, render_label, asset_type
        )

        logger.debug(f"Found proxy_blend: {proxy_blend}")
        logger.debug(f"Found render_blend: {render_blend}")

        if not proxy_blend:
            return False, f"Proxy version .blend not found in archive: {variant_name}/{proxy_label}"
        if not render_blend:
            return False, f"Render version .blend not found in archive: {variant_name}/{render_label}"

        # Get the library .blend path (for output path calculation)
        library_blend = self._archive.get_latest_blend_path(
            asset_id, asset_name, variant_name, asset_type
        )
        if not library_blend:
            return False, "Library .blend file not found"

        # Ensure .current.blend exists (may be missing for assets saved before this feature)
        if not self._current_ref.has_current_reference(library_blend):
            success_c, msg_c = self._current_ref.create_current_reference(library_blend)
            if success_c:
                logger.debug(f"Created missing .current.blend: {msg_c}")
            else:
                logger.warning(f"Could not create .current.blend: {msg_c}")

        # Create .proxy.blend
        proxy_output = self._current_ref.get_proxy_path(library_blend)
        logger.debug(f"Copying proxy: {proxy_blend} -> {proxy_output}")
        success_p, msg_p = self._current_ref.create_representation_reference(
            proxy_blend, proxy_output
        )
        logger.debug(f"Proxy copy result: success={success_p}, msg={msg_p}")
        if not success_p:
            return False, f"Failed to create .proxy.blend: {msg_p}"

        # Create .render.blend
        render_output = self._current_ref.get_render_path(library_blend)
        success_r, msg_r = self._current_ref.create_representation_reference(
            render_blend, render_output
        )
        if not success_r:
            return False, f"Failed to create .render.blend: {msg_r}"

        # Write to database
        logger.debug(
            f"Saving designation: version_group_id={version_group_id}, "
            f"variant={variant_name}, proxy={proxy_label}, render={render_label}"
        )

        self._db.set_representation_designation(
            version_group_id,
            variant_name=variant_name,
            proxy_version_uuid=proxy_v_uuid,
            render_version_uuid=render_v_uuid,
            proxy_version_label=proxy_label,
            render_version_label=render_label,
            proxy_blend_path=str(proxy_output),
            render_blend_path=str(render_output),
        )

        logger.info(
            f"Designated proxy={proxy_label}, render={render_label} "
            f"for {asset_name}/{variant_name}"
        )
        return True, f"Proxy: {proxy_label}, Render: {render_label}"

    def on_new_version_created(
        self,
        version_group_id: str,
        variant_name: str = 'Base',
        asset_name: Optional[str] = None,
        asset_type: str = 'other',
        asset_id: Optional[str] = None,
    ):
        """
        Called after a new version is saved. Auto-updates .render.blend if
        the render designation uses the default (latest).

        Proxy designation is unaffected by new versions.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name
            asset_name: Asset name (for path resolution)
            asset_type: Asset type
            asset_id: Asset family ID
        """
        if asset_type not in ('mesh', 'rig'):
            return

        designation = self._db.get_representation_designation(version_group_id, variant_name)
        if not designation:
            return  # No designations set

        render_uuid = designation.get('render_version_uuid')

        # If render_uuid is None, the user is using "latest" default
        # In that case, we need to update the .render.blend to point to the new latest
        if render_uuid is not None:
            # User explicitly set a render version, don't auto-update
            return

        # Auto-update render to new latest
        asset_id = asset_id or version_group_id
        if not asset_name:
            latest = self._db.get_latest_asset_version(version_group_id)
            if not latest:
                return
            asset_name = latest.get('name')
            asset_type = latest.get('asset_type', 'other')

        # Get the new latest version
        versions = self._db.get_asset_versions(version_group_id)
        if not versions:
            return

        versions_sorted = sorted(versions, key=lambda v: v.get('version') or 0)
        new_latest = versions_sorted[-1]
        new_label = new_latest.get('version_label')
        new_uuid = new_latest.get('uuid')

        # Find archive blend for new latest
        render_blend = self._archive.get_version_blend_path(
            asset_id, asset_name, variant_name, new_label, asset_type
        )
        if not render_blend:
            logger.warning(f"Could not find archive blend for {new_label}")
            return

        # Get library blend for output path
        library_blend = self._archive.get_latest_blend_path(
            asset_id, asset_name, variant_name, asset_type
        )
        if not library_blend:
            return

        # Recreate .render.blend
        render_output = self._current_ref.get_render_path(library_blend)
        success, msg = self._current_ref.create_representation_reference(
            render_blend, render_output
        )

        if success:
            # Update DB path
            self._db.update_render_designation_path(
                version_group_id, variant_name,
                new_uuid, new_label, str(render_output)
            )
            logger.info(
                f"Auto-updated render to {new_label} for {asset_name}/{variant_name}"
            )
        else:
            logger.warning(f"Failed to auto-update render: {msg}")

    def get_effective_designations(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> Dict[str, Any]:
        """
        Get the effective proxy/render designations with resolved defaults.

        Returns:
            Dict with keys:
            - proxy_label: version label (e.g., 'v001')
            - proxy_uuid: version UUID or None
            - proxy_is_default: True if using v001 default
            - render_label: version label (e.g., 'v003')
            - render_uuid: version UUID or None
            - render_is_default: True if using latest default
            - has_proxy_file: True if .proxy.blend exists
            - has_render_file: True if .render.blend exists
        """
        designation = self._db.get_representation_designation(version_group_id, variant_name)

        # Get versions for defaults
        versions = self._db.get_asset_versions(version_group_id)
        if not versions:
            return {
                'proxy_label': None, 'proxy_uuid': None, 'proxy_is_default': True,
                'proxy_source': 'version', 'proxy_is_custom': False,
                'render_label': None, 'render_uuid': None, 'render_is_default': True,
                'has_proxy_file': False, 'has_render_file': False,
                'custom_proxy_count': 0,
            }

        versions_sorted = sorted(versions, key=lambda v: v.get('version') or 0)
        first = versions_sorted[0]
        latest = versions_sorted[-1]

        asset_name = latest.get('name')
        asset_type = latest.get('asset_type', 'other')
        asset_id = latest.get('asset_id') or version_group_id

        # Resolve effective values
        if designation:
            proxy_uuid = designation.get('proxy_version_uuid')
            render_uuid = designation.get('render_version_uuid')
            proxy_label = designation.get('proxy_version_label') or first.get('version_label', 'v001')
            render_label = designation.get('render_version_label') or latest.get('version_label')
        else:
            proxy_uuid = None
            render_uuid = None
            proxy_label = first.get('version_label', 'v001')
            render_label = latest.get('version_label')

        # Check file existence
        library_blend = self._archive.get_latest_blend_path(
            asset_id, asset_name, variant_name, asset_type
        )
        has_proxy = False
        has_render = False
        if library_blend:
            has_proxy = self._current_ref.has_proxy_reference(library_blend)
            has_render = self._current_ref.has_render_reference(library_blend)

        # Get custom proxy count
        custom_proxy_count = self._db.get_custom_proxy_count(version_group_id, variant_name)

        # Determine proxy source
        proxy_source = 'version'
        if designation:
            proxy_source = designation.get('proxy_source', 'version') or 'version'

        return {
            'proxy_label': proxy_label,
            'proxy_uuid': proxy_uuid,
            'proxy_is_default': proxy_uuid is None,
            'proxy_source': proxy_source,
            'render_label': render_label,
            'render_uuid': render_uuid,
            'render_is_default': render_uuid is None,
            'has_proxy_file': has_proxy,
            'has_render_file': has_render,
            'custom_proxy_count': custom_proxy_count,
        }

    def designate_custom_proxy(
        self,
        version_group_id: str,
        variant_name: str,
        proxy_uuid: str,
    ) -> Tuple[bool, str]:
        """
        Designate a custom proxy as the active proxy representation.

        1. Look up custom_proxies record
        2. Copy proxy .blend to .proxy.blend in library folder
        3. Update representation_designations with proxy_source='custom'

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name
            proxy_uuid: UUID of the custom proxy to designate

        Returns:
            Tuple of (success, message)
        """
        proxy = self._db.get_custom_proxy_by_uuid(proxy_uuid)
        if not proxy:
            return False, f"Custom proxy not found: {proxy_uuid}"

        proxy_blend_str = proxy.get('blend_path')
        proxy_label = proxy.get('proxy_label', 'p001')
        asset_name = proxy.get('asset_name')

        if not proxy_blend_str:
            return False, "Custom proxy has no blend_path in database"

        proxy_blend = Path(proxy_blend_str)

        logger.info(f"[designate_custom_proxy] proxy_uuid={proxy_uuid}, label={proxy_label}")
        logger.info(f"[designate_custom_proxy] DB blend_path: {proxy_blend_str}")
        logger.info(f"[designate_custom_proxy] Path exists: {proxy_blend.exists()}")

        # Try the stored path first
        if not proxy_blend.exists():
            # Fallback: try versioned filename (AssetName.p001.blend)
            safe_name = Config.sanitize_filename(asset_name)
            versioned_path = proxy_blend.parent / f"{safe_name}.{proxy_label}.blend"
            if versioned_path.exists():
                proxy_blend = versioned_path
            else:
                # No more fallbacks - don't risk copying wrong file
                return False, f"Custom proxy .blend file not found: {proxy_blend_str} (also tried {versioned_path})"
        

        # Get library .blend path for output
        asset_id = proxy.get('asset_id') or version_group_id
        asset_type = proxy.get('asset_type', 'mesh')

        library_blend = self._archive.get_latest_blend_path(
            asset_id, asset_name, variant_name, asset_type
        )
        if not library_blend:
            return False, "Library .blend file not found"

        # Ensure .current.blend exists
        if not self._current_ref.has_current_reference(library_blend):
            self._current_ref.create_current_reference(library_blend)

        # Copy custom proxy .blend to .proxy.blend
        proxy_output = self._current_ref.get_proxy_path(library_blend)
        success, msg = self._current_ref.create_representation_reference(
            proxy_blend, proxy_output
        )
        if not success:
            return False, f"Failed to create .proxy.blend: {msg}"

        # Preserve existing render designation (INSERT OR REPLACE replaces entire row)
        existing = self._db.get_representation_designation(version_group_id, variant_name)
        render_uuid = existing.get('render_version_uuid') if existing else None
        render_label = existing.get('render_version_label') if existing else None
        render_path = existing.get('render_blend_path') if existing else None

        # Auto-create .render.blend from latest version if missing
        render_output = self._current_ref.get_render_path(library_blend)
        if not render_output.exists():
            versions = self._db.get_asset_versions(version_group_id)
            if versions:
                versions_sorted = sorted(versions, key=lambda v: v.get('version', 0))
                latest = versions_sorted[-1]
                latest_label = latest.get('version_label')
                latest_type = latest.get('asset_type', 'mesh')
                latest_name = latest.get('name') or asset_name
                latest_id = latest.get('asset_id') or version_group_id

                render_source = self._archive.get_version_blend_path(
                    latest_id, latest_name, variant_name, latest_label, latest_type
                )
                if render_source:
                    success_r, msg_r = self._current_ref.create_representation_reference(
                        render_source, render_output
                    )
                    if success_r:
                        render_path = str(render_output)
                        logger.debug(f"Auto-created .render.blend from {latest_label}")

        # Update designation in DB with proxy_source='custom', preserving render fields
        self._db.set_representation_designation(
            version_group_id,
            variant_name=variant_name,
            proxy_version_uuid=proxy_uuid,
            proxy_version_label=proxy_label,
            proxy_blend_path=str(proxy_output),
            render_version_uuid=render_uuid,
            render_version_label=render_label,
            render_blend_path=render_path,
            proxy_source='custom',
        )

        logger.info(
            f"Designated custom proxy {proxy_label} for {asset_name}/{variant_name}"
        )
        return True, f"Custom proxy: {proxy_label}"

    def clear_designations(
        self,
        version_group_id: str,
        variant_name: str = 'Base'
    ) -> Tuple[bool, str]:
        """
        Clear all designations and delete .proxy.blend / .render.blend files.

        Args:
            version_group_id: Version group identifier
            variant_name: Variant name

        Returns:
            Tuple of (success, message)
        """
        # Get asset info for file paths
        latest = self._db.get_latest_asset_version(version_group_id)
        if latest:
            asset_name = latest.get('name')
            asset_type = latest.get('asset_type', 'other')
            asset_id = latest.get('asset_id') or version_group_id

            library_blend = self._archive.get_latest_blend_path(
                asset_id, asset_name, variant_name, asset_type
            )
            if library_blend:
                self._current_ref.delete_representation_references(library_blend)

        # Clear DB
        self._db.clear_representation_designation(version_group_id, variant_name)
        return True, "Designations cleared"


# Singleton instance
_representation_service_instance: Optional[RepresentationService] = None


def get_representation_service() -> RepresentationService:
    """Get global RepresentationService singleton instance."""
    global _representation_service_instance
    if _representation_service_instance is None:
        _representation_service_instance = RepresentationService()
    return _representation_service_instance


__all__ = ['RepresentationService', 'get_representation_service']
