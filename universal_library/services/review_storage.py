"""
ReviewStorage - File storage management for review screenshots

Handles saving, copying, and managing screenshot files for asset review.

New Structure (matching archive_service):
    storage/reviews/{uuid_short}_{name}/{variant}/{version_label}/
    ├── screenshots/
    │   ├── 001_face_closeup.png
    │   ├── 002_hands_detail.png
    │   └── 003_full_body.png
    ├── drawovers/
    │   ├── screenshot_123.json    # Vector annotations (by screenshot_id)
    │   └── screenshot_123.png     # Rasterized cache
    └── manifest.json
"""

import shutil
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from ..config import Config


class ReviewStorage:
    """
    Manages review screenshot file storage on disk.

    File structure:
        storage/reviews/{uuid_short}_{name}/{variant}/{version_label}/
        ├── screenshots/
        │   ├── 001_face_closeup.png
        │   ├── 002_hands_detail.png
        │   └── 003_full_body.png
        ├── drawovers/
        │   ├── screenshot_123.json    # Vector annotations
        │   └── screenshot_123.png     # Rasterized cache
        └── manifest.json
    """

    def __init__(self):
        # Base is now the reviews folder from Config
        pass

    def get_review_dir(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ) -> Path:
        """Get directory for a version's review files."""
        review_dir = Config.get_asset_reviews_path(asset_id, asset_name, variant_name, version_label)
        review_dir.mkdir(parents=True, exist_ok=True)
        return review_dir

    def get_screenshots_dir(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ) -> Path:
        """Get screenshots directory for a version."""
        screenshots_dir = self.get_review_dir(asset_id, asset_name, variant_name, version_label) / 'screenshots'
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        return screenshots_dir

    def get_drawovers_dir(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ) -> Path:
        """Get drawovers directory for a version."""
        drawovers_dir = self.get_review_dir(asset_id, asset_name, variant_name, version_label) / 'drawovers'
        drawovers_dir.mkdir(parents=True, exist_ok=True)
        return drawovers_dir

    # ==================== Screenshot Management ====================

    def save_screenshot(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        source_path: Path,
        display_name: str = '',
        order: int = 0
    ) -> Optional[Dict]:
        """
        Copy a screenshot to the review storage.

        Args:
            asset_id: Asset family UUID
            asset_name: Human-readable asset name
            variant_name: Variant name (e.g., 'Base')
            version_label: Version label (e.g., 'v001')
            source_path: Path to the source image file
            display_name: Optional display name for the screenshot
            order: Display order (used in filename prefix)

        Returns:
            Dict with 'filename', 'file_path', 'display_name' if successful, None otherwise
        """
        try:
            source = Path(source_path)
            if not source.exists():
                return None

            screenshots_dir = self.get_screenshots_dir(asset_id, asset_name, variant_name, version_label)

            # Generate filename with order prefix
            original_name = source.stem
            extension = source.suffix.lower()

            # Normalize display name
            if not display_name:
                display_name = original_name

            # Sanitize filename
            safe_name = self._sanitize_filename(display_name)
            filename = f"{order:03d}_{safe_name}{extension}"
            dest_path = screenshots_dir / filename

            # Handle duplicate filenames
            counter = 1
            while dest_path.exists():
                filename = f"{order:03d}_{safe_name}_{counter}{extension}"
                dest_path = screenshots_dir / filename
                counter += 1

            # Copy file
            shutil.copy2(source, dest_path)

            return {
                'filename': filename,
                'file_path': str(dest_path),
                'display_name': display_name
            }

        except Exception as e:
            return None

    def delete_screenshot(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        filename: str
    ) -> bool:
        """
        Delete a screenshot file and its associated drawover.

        Args:
            asset_id: Asset family UUID
            asset_name: Human-readable asset name
            variant_name: Variant name (e.g., 'Base')
            version_label: Version label
            filename: Screenshot filename to delete

        Returns:
            True if deleted successfully
        """
        try:
            screenshots_dir = self.get_screenshots_dir(asset_id, asset_name, variant_name, version_label)
            screenshot_path = screenshots_dir / filename

            if screenshot_path.exists():
                screenshot_path.unlink()

            # Also delete associated drawover files
            drawovers_dir = self.get_drawovers_dir(asset_id, asset_name, variant_name, version_label)
            base_name = Path(filename).stem

            # Delete JSON and PNG drawover files
            for ext in ['.json', '.png']:
                drawover_path = drawovers_dir / f"{base_name}{ext}"
                if drawover_path.exists():
                    drawover_path.unlink()

            return True

        except Exception as e:
            return False

    def rename_screenshot(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        old_filename: str,
        new_display_name: str
    ) -> Optional[str]:
        """
        Rename a screenshot file.

        Args:
            asset_id: Asset family UUID
            asset_name: Human-readable asset name
            variant_name: Variant name (e.g., 'Base')
            version_label: Version label
            old_filename: Current filename
            new_display_name: New display name

        Returns:
            New filename if successful, None otherwise
        """
        try:
            screenshots_dir = self.get_screenshots_dir(asset_id, asset_name, variant_name, version_label)
            old_path = screenshots_dir / old_filename

            if not old_path.exists():
                return None

            # Extract order prefix and extension
            parts = old_filename.split('_', 1)
            order_prefix = parts[0] if parts else '000'
            extension = old_path.suffix.lower()

            # Generate new filename
            safe_name = self._sanitize_filename(new_display_name)
            new_filename = f"{order_prefix}_{safe_name}{extension}"
            new_path = screenshots_dir / new_filename

            if new_path.exists() and new_path != old_path:
                return None

            # Rename file
            old_path.rename(new_path)

            # Also rename associated drawover files
            drawovers_dir = self.get_drawovers_dir(asset_id, asset_name, variant_name, version_label)
            old_base = old_path.stem
            new_base = new_path.stem

            for ext in ['.json', '.png']:
                old_drawover = drawovers_dir / f"{old_base}{ext}"
                new_drawover = drawovers_dir / f"{new_base}{ext}"
                if old_drawover.exists():
                    old_drawover.rename(new_drawover)

            return new_filename

        except Exception as e:
            return None

    def reorder_screenshots(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        filename_order: List[str]
    ) -> List[str]:
        """
        Reorder screenshots by renaming with new order prefixes.

        Args:
            asset_id: Asset family UUID
            asset_name: Human-readable asset name
            variant_name: Variant name (e.g., 'Base')
            version_label: Version label
            filename_order: List of filenames in desired order

        Returns:
            List of new filenames in order
        """
        try:
            screenshots_dir = self.get_screenshots_dir(asset_id, asset_name, variant_name, version_label)
            drawovers_dir = self.get_drawovers_dir(asset_id, asset_name, variant_name, version_label)

            new_filenames = []
            temp_renames = []

            # First pass: rename to temp names to avoid conflicts
            for i, old_filename in enumerate(filename_order):
                old_path = screenshots_dir / old_filename
                if not old_path.exists():
                    continue

                temp_filename = f"_temp_{i:03d}_{old_filename}"
                temp_path = screenshots_dir / temp_filename
                old_path.rename(temp_path)

                # Also rename drawovers
                old_base = Path(old_filename).stem
                for ext in ['.json', '.png']:
                    old_drawover = drawovers_dir / f"{old_base}{ext}"
                    if old_drawover.exists():
                        temp_drawover = drawovers_dir / f"_temp_{i:03d}_{old_base}{ext}"
                        old_drawover.rename(temp_drawover)

                temp_renames.append((i, temp_filename, old_filename))

            # Second pass: rename to final names with new order
            for i, temp_filename, original_filename in temp_renames:
                temp_path = screenshots_dir / temp_filename

                # Extract original name without old order prefix
                parts = original_filename.split('_', 1)
                name_part = parts[1] if len(parts) > 1 else original_filename

                new_filename = f"{i:03d}_{name_part}"
                new_path = screenshots_dir / new_filename
                temp_path.rename(new_path)
                new_filenames.append(new_filename)

                # Also finalize drawover renames
                temp_base = temp_path.stem
                new_base = new_path.stem
                for ext in ['.json', '.png']:
                    temp_drawover = drawovers_dir / f"{temp_base[6:]}{ext}"  # Remove '_temp_NNN_' prefix
                    if temp_drawover.exists():
                        new_drawover = drawovers_dir / f"{new_base}{ext}"
                        temp_drawover.rename(new_drawover)

            return new_filenames

        except Exception as e:
            return filename_order

    def list_screenshots(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ) -> List[Dict]:
        """
        List all screenshots for a version.

        Args:
            asset_id: Asset family UUID
            asset_name: Human-readable asset name
            variant_name: Variant name (e.g., 'Base')
            version_label: Version label

        Returns:
            List of dicts with 'filename', 'file_path', 'display_name', 'order'
        """
        screenshots_dir = self.get_screenshots_dir(asset_id, asset_name, variant_name, version_label)
        if not screenshots_dir.exists():
            return []

        screenshots = []
        for path in sorted(screenshots_dir.iterdir()):
            if path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp']:
                # Extract display name and order from filename
                filename = path.name
                parts = filename.split('_', 1)

                try:
                    order = int(parts[0])
                except ValueError:
                    order = 0

                display_name = parts[1].rsplit('.', 1)[0] if len(parts) > 1 else path.stem

                screenshots.append({
                    'filename': filename,
                    'file_path': str(path),
                    'display_name': display_name,
                    'order': order
                })

        return screenshots

    def get_screenshot_path(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str,
        filename: str
    ) -> Optional[Path]:
        """Get full path to a screenshot file."""
        screenshots_dir = self.get_screenshots_dir(asset_id, asset_name, variant_name, version_label)
        path = screenshots_dir / filename
        return path if path.exists() else None

    # ==================== Utilities ====================

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as a filename."""
        # Replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        safe_name = name
        for char in invalid_chars:
            safe_name = safe_name.replace(char, '_')

        # Replace spaces with underscores
        safe_name = safe_name.replace(' ', '_')

        # Remove leading/trailing underscores
        safe_name = safe_name.strip('_')

        # Limit length
        if len(safe_name) > 100:
            safe_name = safe_name[:100]

        return safe_name or 'screenshot'

    def get_storage_size(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ) -> int:
        """Get total size of review files for a version in bytes."""
        review_dir = self.get_review_dir(asset_id, asset_name, variant_name, version_label)
        if not review_dir.exists():
            return 0

        total = 0
        for path in review_dir.rglob('*'):
            if path.is_file():
                total += path.stat().st_size

        return total

    def cleanup_empty_directories(
        self,
        asset_id: str,
        asset_name: str
    ) -> int:
        """Remove empty version directories for an asset family."""
        try:
            family_folder = Config.get_family_folder_name(asset_id, asset_name)
            reviews_base = Config.get_reviews_folder()
            asset_dir = reviews_base / family_folder

            if not asset_dir.exists():
                return 0

            removed = 0
            for variant_dir in asset_dir.iterdir():
                if variant_dir.is_dir():
                    for version_dir in variant_dir.iterdir():
                        if version_dir.is_dir():
                            # Check if directory is effectively empty
                            has_content = False
                            for item in version_dir.rglob('*'):
                                if item.is_file():
                                    has_content = True
                                    break

                            if not has_content:
                                shutil.rmtree(version_dir)
                                removed += 1

                    # Remove variant directory if empty
                    if not any(variant_dir.iterdir()):
                        variant_dir.rmdir()

            # Remove family directory if empty
            if asset_dir.exists() and not any(asset_dir.iterdir()):
                asset_dir.rmdir()

            return removed

        except Exception as e:
            return 0

    def delete_version_reviews(
        self,
        asset_id: str,
        asset_name: str,
        variant_name: str,
        version_label: str
    ) -> bool:
        """Delete all review files for a version."""
        try:
            review_dir = self.get_review_dir(asset_id, asset_name, variant_name, version_label)
            if review_dir.exists():
                shutil.rmtree(review_dir)
            return True
        except Exception as e:
            return False


# Singleton instance
_storage_instance: Optional[ReviewStorage] = None


def get_review_storage() -> ReviewStorage:
    """Get singleton ReviewStorage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = ReviewStorage()
    return _storage_instance


__all__ = ['ReviewStorage', 'get_review_storage']
