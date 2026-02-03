"""
Queue Client - Reads import requests from the desktop app

Monitors a temp directory for JSON request files and processes them.
Matching the queue system used by the desktop app's BlenderService.
"""

import json
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any

from .constants import QUEUE_DIR_NAME, STATUS_PENDING


class QueueClient:
    """
    Client for reading import requests from the desktop app queue.

    The desktop app writes JSON files to a temp directory, and
    this client reads and processes them.

    Usage:
        client = QueueClient.get_instance()
        requests = client.get_pending_requests()
        for req in requests:
            # Process request
            client.mark_completed(req['file_path'])
    """

    _instance: Optional['QueueClient'] = None

    @classmethod
    def get_instance(cls) -> 'QueueClient':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize the queue client"""
        self._queue_dir = Path(tempfile.gettempdir()) / QUEUE_DIR_NAME

    @property
    def queue_directory(self) -> Path:
        """Get the queue directory path"""
        return self._queue_dir

    def get_pending_count(self) -> int:
        """Get count of pending requests (import + thumbnail)"""
        if not self._queue_dir.exists():
            return 0
        import_count = len(list(self._queue_dir.glob("import_*.json")))
        thumbnail_count = len(list(self._queue_dir.glob("thumbnail_*.json")))
        return import_count + thumbnail_count

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """
        Get all pending import requests.

        Returns:
            List of request dictionaries, each with added 'file_path' key
        """
        if not self._queue_dir.exists():
            return []

        requests = []
        for json_file in sorted(self._queue_dir.glob("import_*.json")):
            try:
                request = self.read_request(json_file)
                if request and request.get('status') == STATUS_PENDING:
                    request['file_path'] = str(json_file)
                    request['command'] = request.get('command', 'import')  # Default to import
                    requests.append(request)
            except Exception as e:
                pass

        return requests

    def get_pending_thumbnail_requests(self) -> List[Dict[str, Any]]:
        """
        Get all pending thumbnail regeneration requests.

        Returns:
            List of request dictionaries
        """
        if not self._queue_dir.exists():
            return []

        requests = []
        for json_file in sorted(self._queue_dir.glob("thumbnail_*.json")):
            try:
                request = self.read_request(json_file)
                if request and request.get('status') == STATUS_PENDING:
                    request['file_path'] = str(json_file)
                    requests.append(request)
            except Exception as e:
                pass

        return requests

    def read_request(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Read a single request file.

        Args:
            file_path: Path to the JSON request file

        Returns:
            Request dictionary or None if failed
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return None

    def mark_completed(self, file_path: str) -> bool:
        """
        Mark a request as completed by deleting the file.

        Args:
            file_path: Path to the request file to delete

        Returns:
            True if successful
        """
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
            return True
        except Exception as e:
            return False

    def mark_failed(self, file_path: str, error: str) -> bool:
        """
        Mark a request as failed by updating its status.

        Args:
            file_path: Path to the request file
            error: Error message

        Returns:
            True if successful
        """
        try:
            path = Path(file_path)
            if path.exists():
                request = self.read_request(path)
                if request:
                    request['status'] = 'failed'
                    request['error'] = error
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(request, f, indent=2)
                    return True
        except Exception as e:
            pass
        return False


def get_queue_client() -> QueueClient:
    """Get the QueueClient singleton instance"""
    return QueueClient.get_instance()


__all__ = ['QueueClient', 'get_queue_client']
