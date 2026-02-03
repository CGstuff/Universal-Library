"""
Update Service for Universal Library

Checks GitHub for new releases and provides update information.
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Tuple

from ..config import Config

logger = logging.getLogger(__name__)


class UpdateService:
    """
    Service for checking GitHub releases for updates.

    Usage:
        service = UpdateService()
        has_update, version, url = service.check_for_updates()
        if has_update:
            pass
    """

    # GitHub API URL for latest release
    # TODO: Update with actual repo owner/name when published
    GITHUB_OWNER = "CGstuff"
    GITHUB_REPO = "Universal-Library"
    UPDATE_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

    # Request timeout in seconds
    TIMEOUT = 5

    def __init__(self):
        """Initialize update service."""
        self._cached_result: Optional[Tuple[bool, Optional[str], Optional[str]]] = None

    def check_for_updates(self, force: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check GitHub for new releases.

        Args:
            force: If True, bypass cache and check again

        Returns:
            Tuple of (has_update, latest_version, download_url)
            - has_update: True if a newer version is available
            - latest_version: Version string (e.g., "v1.2.0") or None if check failed
            - download_url: URL to the release page or None if check failed
        """
        if self._cached_result is not None and not force:
            return self._cached_result

        try:
            result = self._fetch_latest_release()
            self._cached_result = result
            return result
        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return (False, None, None)

    def _fetch_latest_release(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Fetch latest release info from GitHub API.

        Returns:
            Tuple of (has_update, latest_version, download_url)
        """
        logger.info(f"Checking for updates at: {self.UPDATE_URL}")

        req = urllib.request.Request(self.UPDATE_URL)
        req.add_header('User-Agent', f'UniversalLibrary/{Config.APP_VERSION}')
        req.add_header('Accept', 'application/vnd.github.v3+json')

        try:
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as response:
                data = json.loads(response.read().decode('utf-8'))

                tag_name = data.get('tag_name', '')
                html_url = data.get('html_url', '')
                prerelease = data.get('prerelease', False)

                # Skip pre-releases for normal update checks
                if prerelease:
                    logger.info(f"Latest release {tag_name} is a pre-release, skipping")
                    return (False, tag_name, html_url)

                logger.info(f"Latest release: {tag_name}")
                logger.info(f"Current version: {Config.APP_VERSION}")

                # Compare versions
                current = self._parse_version(Config.APP_VERSION)
                latest = self._parse_version(tag_name)

                has_update = latest > current
                if has_update:
                    logger.info(f"Update available: {tag_name}")
                else:
                    logger.info("Already on latest version")

                return (has_update, tag_name, html_url)

        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.warning("GitHub repository not found or no releases")
            else:
                logger.error(f"HTTP error: {e.code} {e.reason}")
            return (False, None, None)
        except urllib.error.URLError as e:
            logger.warning(f"Network error: {e.reason}")
            return (False, None, None)

    def _parse_version(self, version_str: str) -> Tuple[int, ...]:
        """
        Parse version string into comparable tuple.

        Args:
            version_str: Version like "1.2.3", "v1.2.3", or "1.2"

        Returns:
            Tuple of integers (e.g., (1, 2, 3))
        """
        # Remove 'v' prefix if present
        v = version_str.lower().lstrip('v')

        # Split by dots and convert to integers
        parts = v.split('.')
        result = []
        for part in parts:
            # Handle cases like "1.2.3-beta" by taking only the number
            num_str = ''
            for char in part:
                if char.isdigit():
                    num_str += char
                else:
                    break
            result.append(int(num_str) if num_str else 0)

        # Pad to at least 3 parts for consistent comparison
        while len(result) < 3:
            result.append(0)

        return tuple(result)

    def get_current_version(self) -> str:
        """Get the current application version."""
        return Config.APP_VERSION

    def clear_cache(self):
        """Clear the cached update check result."""
        self._cached_result = None


# Singleton instance
_update_service: Optional[UpdateService] = None


def get_update_service() -> UpdateService:
    """Get the global UpdateService singleton instance."""
    global _update_service
    if _update_service is None:
        _update_service = UpdateService()
    return _update_service


__all__ = ['UpdateService', 'get_update_service']
