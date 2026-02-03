"""
ScreenshotQueueHandler - Processes screenshot capture requests from Blender

Monitors a temp queue directory for screenshot requests from the Blender plugin
and imports them into the review system.

Now uses the protocol module for schema-driven message validation.
"""

import json
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from .review_storage import get_review_storage
from .review_database import get_review_database
from ..protocol import validate_message, get_field, QUEUE_DIR_NAME, ValidationError


class ScreenshotQueueHandler:
    """
    Handles screenshot capture requests from Blender.

    Monitors the temp queue directory for screenshot_*.json files,
    processes them by copying to review storage and registering in DB.
    """

    def __init__(self):
        self._queue_dir = Path(tempfile.gettempdir()) / QUEUE_DIR_NAME
        self._review_storage = get_review_storage()
        self._review_db = get_review_database()

    @property
    def queue_directory(self) -> Path:
        """Get the queue directory path"""
        return self._queue_dir

    def get_pending_screenshot_requests(self) -> List[Dict[str, Any]]:
        """
        Get all pending screenshot capture requests.

        Returns:
            List of request dictionaries with added 'queue_file_path' key
        """
        if not self._queue_dir.exists():
            return []

        requests = []
        for json_file in sorted(self._queue_dir.glob("screenshot_*.json")):
            try:
                request = self._read_request(json_file)
                if request:
                    # Treat missing status as 'pending' (backwards compatibility)
                    status = request.get('status', 'pending')
                    if status == 'pending' and request.get('type') == 'review_screenshot':
                        request['queue_file_path'] = str(json_file)
                        requests.append(request)
                    # Skip failed/processed files silently
            except Exception as e:
                pass

        return requests

    def process_all_pending(self) -> int:
        """
        Process all pending screenshot requests.

        Returns:
            Number of screenshots successfully imported
        """
        requests = self.get_pending_screenshot_requests()
        success_count = 0

        for request in requests:
            try:
                if self.process_screenshot_request(request):
                    success_count += 1
            except Exception as e:
                # Mark as failed
                self._mark_failed(request.get('queue_file_path'), str(e))

        return success_count

    def process_screenshot_request(self, request: Dict[str, Any]) -> bool:
        """
        Process a single screenshot request.

        1. Validate the request data using protocol schema
        2. Copy screenshot to review storage
        3. Register in review database
        4. Clean up queue file and temp screenshot

        Args:
            request: Request dictionary from queue file

        Returns:
            True if successfully processed
        """
        try:
            # Validate using protocol schema
            try:
                validate_message(request, "review_screenshot")
            except ValidationError as e:
                # Mark as failed so we don't keep retrying
                self._mark_failed(request.get('queue_file_path'), str(e))
                return False

            # Get fields using semantic identifiers from schema
            asset_uuid = get_field(request, "session_identifier")  # version_group_id for sessions
            asset_id = get_field(request, "storage_identifier")    # asset_id for file paths
            version_label = request.get('version_label')
            screenshot_path = request.get('screenshot_path')
            display_name = request.get('display_name', 'Screenshot')
            queue_file_path = request.get('queue_file_path')
            asset_name = request.get('asset_name', 'Asset')
            variant_name = request.get('variant_name', 'Base')

            source_path = Path(screenshot_path)
            if not source_path.exists():
                return False


            # Get current screenshot count for ordering
            existing_screenshots = self._review_db.get_screenshots(asset_uuid, version_label)
            order = len(existing_screenshots)

            # Copy to review storage (new API with 4 params for path)
            result = self._review_storage.save_screenshot(
                asset_id=asset_id,
                asset_name=asset_name,
                variant_name=variant_name,
                version_label=version_label,
                source_path=source_path,
                display_name=display_name,
                order=order
            )

            if not result:
                return False

            # Register in database
            uploaded_by = request.get('source', 'blender')
            screenshot_id = self._review_db.add_screenshot(
                asset_uuid=asset_uuid,
                version_label=version_label,
                filename=result['filename'],
                file_path=result['file_path'],
                display_name=result['display_name'],
                uploaded_by=uploaded_by
            )

            if not screenshot_id:
                return False

            # Success - clean up
            self._cleanup_request(queue_file_path, source_path)

            return True

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False

    def _read_request(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Read a queue file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return None

    def _mark_failed(self, queue_file_path: str, error: str):
        """Mark a request as failed"""
        if not queue_file_path:
            return

        try:
            path = Path(queue_file_path)
            if path.exists():
                request = self._read_request(path)
                if request:
                    request['status'] = 'failed'
                    request['error'] = error
                    request['failed_at'] = datetime.now().isoformat()
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(request, f, indent=2)
        except Exception as e:
            pass

    def _cleanup_request(self, queue_file_path: str, screenshot_path: Path):
        """Clean up queue file and temp screenshot after successful import"""
        try:
            # Delete queue file
            if queue_file_path:
                queue_path = Path(queue_file_path)
                if queue_path.exists():
                    queue_path.unlink()

            # Delete temp screenshot
            if screenshot_path and screenshot_path.exists():
                screenshot_path.unlink()

        except Exception as e:
            pass


# Singleton instance
_handler_instance: Optional[ScreenshotQueueHandler] = None


def get_screenshot_queue_handler() -> ScreenshotQueueHandler:
    """Get singleton ScreenshotQueueHandler instance"""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = ScreenshotQueueHandler()
    return _handler_instance


__all__ = ['ScreenshotQueueHandler', 'get_screenshot_queue_handler']
