"""
CurrentReferenceService - Creates and manages .current/.proxy/.render blend files.

These are file copies placed in the library folder at stable paths:
    - .current.blend  -> copy of latest version (default link target)
    - .proxy.blend    -> copy of designated proxy version (for playblasts)
    - .render.blend   -> copy of designated render version (for lookdev)

Structure:
    library/meshes/Sword/Base/
      Sword.v002.blend      <- Latest version (versioned filename)
      Sword.current.blend   <- Copy of latest (stable link target, NO version)
      Sword.proxy.blend     <- Copy of designated proxy (stable, NO version)
      Sword.render.blend    <- Copy of designated render (stable, NO version)
      Sword.v002.json
      thumbnail.png

The representation files (.current, .proxy, .render) use BASE names without
version numbers because they are stable link targets. Shot Library links to
Sword.current.blend and it always points to the latest version.

When a new version is saved, .current.blend is re-copied from the new version.
.proxy.blend and .render.blend are updated only when the user changes the
designation in the desktop app.
"""

import re
import shutil
from pathlib import Path
from typing import Optional, Tuple

from ..config import Config


class CurrentReferenceService:
    """Creates and manages .current/.proxy/.render blend file copies."""

    CURRENT_SUFFIX = ".current"
    PROXY_SUFFIX = ".proxy"
    RENDER_SUFFIX = ".render"

    @staticmethod
    def extract_version_from_stem(stem: str) -> Optional[str]:
        """
        Extract version label from a versioned filename stem.

        Examples:
            'Sword.v002' -> 'v002'
            'Sword.v002.current' -> 'v002'
            'Sword' -> None

        Args:
            stem: Filename stem (without .blend extension)

        Returns:
            Version label (e.g., 'v002') or None if not versioned
        """
        match = re.search(r'\.(v\d{3,})(?:\.|$)', stem)
        return match.group(1) if match else None

    @staticmethod
    def get_base_name_from_stem(stem: str) -> str:
        """
        Extract base asset name from a versioned filename stem.

        Examples:
            'Sword.v002' -> 'Sword'
            'Sword.v002.current' -> 'Sword'
            'Sword.v002.proxy' -> 'Sword'
            'Sword' -> 'Sword'

        Args:
            stem: Filename stem (without .blend extension)

        Returns:
            Base asset name without version or representation suffix
        """
        # Remove version and everything after it
        result = re.sub(r'\.(v\d{3,}).*$', '', stem)
        # Also remove any representation suffix from legacy files
        for suffix in ('.current', '.proxy', '.render', '.nothing'):
            if result.endswith(suffix):
                result = result[:-len(suffix)]
        return result

    def get_current_path(self, asset_blend_path: Path) -> Path:
        """
        Get the .current.blend path for a given asset .blend file.

        The .current.blend always uses the BASE name (no version) because
        it's a stable link target that gets updated when new versions are saved.

        Args:
            asset_blend_path: Path to the actual asset .blend file

        Returns:
            Path to the .current.blend file (e.g., Sword.current.blend)
        """
        stem = asset_blend_path.stem  # "Sword" or "Sword.v002"
        base_name = self.get_base_name_from_stem(stem)
        return asset_blend_path.parent / f"{base_name}{self.CURRENT_SUFFIX}.blend"

    def create_current_reference(
        self,
        asset_blend_path: Path,
        blender_executable: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """
        Create a .current.blend file by copying the asset .blend.

        .current.blend is a stable-path copy that Shot Library uses as
        the link target. When a new version is saved, this file is
        re-copied so the name stays constant while the content updates.

        Args:
            asset_blend_path: Path to the actual asset .blend file
            blender_executable: Unused, kept for API compatibility

        Returns:
            Tuple of (success, message or error)
        """
        if not asset_blend_path.exists():
            return False, f"Asset blend file not found: {asset_blend_path}"

        current_path = self.get_current_path(asset_blend_path)

        try:
            current_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(asset_blend_path), str(current_path))

            if current_path.exists():
                return True, str(current_path)
            else:
                return False, "Current reference file was not created"

        except Exception as e:
            return False, f"Error creating current reference: {e}"

    def update_current_reference(
        self,
        current_path: Path,
        new_target: Path,
        blender_executable: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """
        Update a .current.blend to match a new target (e.g., after rename).

        Deletes the old copy and re-copies from the new target.

        Args:
            current_path: Path to existing .current.blend
            new_target: Path to the new target .blend file

        Returns:
            Tuple of (success, message or error)
        """
        if current_path.exists():
            try:
                current_path.unlink()
            except Exception as e:
                return False, f"Failed to remove old reference: {e}"

        return self.create_current_reference(new_target, blender_executable)

    def delete_current_reference(self, asset_blend_path: Path) -> Tuple[bool, str]:
        """
        Delete the .current.blend for an asset.

        Args:
            asset_blend_path: Path to the asset .blend file

        Returns:
            Tuple of (success, message)
        """
        current_path = self.get_current_path(asset_blend_path)

        if not current_path.exists():
            return True, "Reference file does not exist"

        try:
            current_path.unlink()
            return True, f"Deleted: {current_path}"
        except Exception as e:
            return False, f"Failed to delete reference: {e}"

    def rename_current_reference(
        self,
        old_blend_path: Path,
        new_blend_path: Path
    ) -> Tuple[bool, str]:
        """
        Rename a .current.blend when the asset is renamed.

        Args:
            old_blend_path: Original asset .blend path
            new_blend_path: New asset .blend path

        Returns:
            Tuple of (success, message)
        """
        old_current = self.get_current_path(old_blend_path)
        new_current = self.get_current_path(new_blend_path)

        if not old_current.exists():
            return self.create_current_reference(new_blend_path)

        try:
            old_current.rename(new_current)
            return self.update_current_reference(new_current, new_blend_path)
        except Exception as e:
            return False, f"Failed to rename reference: {e}"

    # ==================== REPRESENTATION REFERENCES ====================

    def get_proxy_path(self, asset_blend_path: Path) -> Path:
        """Get the .proxy.blend path for a given asset .blend file.

        Uses BASE name (no version) for stable linking.
        e.g., Sword.v002.blend -> Sword.proxy.blend
        """
        stem = asset_blend_path.stem
        base_name = self.get_base_name_from_stem(stem)
        return asset_blend_path.parent / f"{base_name}{self.PROXY_SUFFIX}.blend"

    def get_render_path(self, asset_blend_path: Path) -> Path:
        """Get the .render.blend path for a given asset .blend file.

        Uses BASE name (no version) for stable linking.
        e.g., Sword.v002.blend -> Sword.render.blend
        """
        stem = asset_blend_path.stem
        base_name = self.get_base_name_from_stem(stem)
        return asset_blend_path.parent / f"{base_name}{self.RENDER_SUFFIX}.blend"

    def create_representation_reference(
        self,
        target_blend_path: Path,
        output_path: Path,
        blender_executable: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """
        Create a representation .blend file by copying the archived version.

        Representation files are fixed snapshots of a specific version.

        Args:
            target_blend_path: Path to the source .blend (e.g., _archive/.../v001/Sword.v001.blend)
            output_path: Path where the copy should go (e.g., Sword.proxy.blend)
            blender_executable: Unused, kept for API compatibility

        Returns:
            Tuple of (success, message or error)
        """
        if not target_blend_path.exists():
            return False, f"Target blend file not found: {target_blend_path}"

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(target_blend_path), str(output_path))

            if output_path.exists():
                return True, str(output_path)
            else:
                return False, "File copy did not produce output"

        except Exception as e:
            return False, f"Error copying representation file: {e}"

    def delete_representation_references(self, asset_blend_path: Path) -> Tuple[bool, str]:
        """Delete both .proxy.blend and .render.blend for an asset."""
        proxy_path = self.get_proxy_path(asset_blend_path)
        render_path = self.get_render_path(asset_blend_path)
        deleted = []
        errors = []

        for path, label in [(proxy_path, "proxy"), (render_path, "render")]:
            if path.exists():
                try:
                    path.unlink()
                    deleted.append(label)
                except Exception as e:
                    errors.append(f"Failed to delete {label}: {e}")

        if errors:
            return False, "; ".join(errors)
        if deleted:
            return True, f"Deleted: {', '.join(deleted)}"
        return True, "No representation files to delete"

    def has_proxy_reference(self, asset_blend_path: Path) -> bool:
        """Check if a .proxy.blend exists for an asset."""
        return self.get_proxy_path(asset_blend_path).exists()

    def has_render_reference(self, asset_blend_path: Path) -> bool:
        """Check if a .render.blend exists for an asset."""
        return self.get_render_path(asset_blend_path).exists()

    def rename_representation_references(
        self,
        old_blend_path: Path,
        new_blend_path: Path
    ) -> Tuple[bool, str]:
        """Rename .proxy.blend and .render.blend when the asset is renamed."""
        old_base = self.get_base_name_from_stem(old_blend_path.stem)
        new_base = self.get_base_name_from_stem(new_blend_path.stem)
        renamed = []
        errors = []

        for suffix in [self.PROXY_SUFFIX, self.RENDER_SUFFIX]:
            old_ref = old_blend_path.parent / f"{old_base}{suffix}.blend"
            new_ref = new_blend_path.parent / f"{new_base}{suffix}.blend"

            if old_ref.exists():
                try:
                    old_ref.rename(new_ref)
                    renamed.append(suffix)
                except Exception as e:
                    errors.append(f"Failed to rename {suffix}: {e}")

        if errors:
            return False, "; ".join(errors)
        if renamed:
            return True, f"Renamed: {', '.join(renamed)}"
        return True, "No representation files to rename"

    def has_current_reference(self, asset_blend_path: Path) -> bool:
        """Check if a .current.blend exists for an asset."""
        return self.get_current_path(asset_blend_path).exists()


# Singleton instance
_current_reference_service_instance: Optional[CurrentReferenceService] = None


def get_current_reference_service() -> CurrentReferenceService:
    """Get global CurrentReferenceService singleton instance."""
    global _current_reference_service_instance
    if _current_reference_service_instance is None:
        _current_reference_service_instance = CurrentReferenceService()
    return _current_reference_service_instance


__all__ = ['CurrentReferenceService', 'get_current_reference_service']
