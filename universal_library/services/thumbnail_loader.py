"""
ThumbnailLoader - Async thumbnail loading with QThreadPool

Pattern: Background loading with QRunnable workers
Based on animation_library architecture.
"""

import time
from pathlib import Path
from typing import Optional, Set, Dict, Any
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, QThreadPool
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPixmapCache, QImage

from ..config import Config
from ..utils.image_utils import load_image_as_qimage, scale_and_crop_image


class ThumbnailLoadSignals(QObject):
    """Signals for ThumbnailLoadTask"""
    load_complete = pyqtSignal(str, str, QImage, float)  # uuid, cache_key, image, elapsed_ms
    load_failed = pyqtSignal(str, str)  # uuid, error_message


class ThumbnailLoadTask(QRunnable):
    """
    Background task for loading thumbnails

    Features:
    - Loads image from disk in background thread
    - Scales and crops to target size
    - DPI scaling support
    - Performance timing

    Usage:
        task = ThumbnailLoadTask(uuid, thumbnail_path, cache_key, size)
        threadpool.start(task)
    """

    def __init__(
        self,
        asset_uuid: str,
        thumbnail_path: Path,
        cache_key: str,
        target_size: int = 300
    ):
        super().__init__()
        self.asset_uuid = asset_uuid
        self.thumbnail_path = thumbnail_path
        self.cache_key = cache_key
        self.target_size = target_size
        self.signals = ThumbnailLoadSignals()
        self.start_time = time.time()

    def run(self):
        """Execute thumbnail loading task"""
        try:
            # Load source image (this is the slow disk I/O operation)
            source_image = load_image_as_qimage(self.thumbnail_path)
            if source_image is None:
                self.signals.load_failed.emit(
                    self.asset_uuid,
                    f"Failed to load image: {self.thumbnail_path}"
                )
                return

            # Scale and crop to target size
            processed_image = scale_and_crop_image(
                source_image,
                self.target_size,
                smooth=True
            )

            # Apply DPI scaling for high-resolution displays
            if QApplication.instance():
                screen = QApplication.primaryScreen()
                if screen:
                    device_ratio = screen.devicePixelRatio()
                    processed_image.setDevicePixelRatio(device_ratio)

            # Calculate elapsed time
            elapsed_ms = (time.time() - self.start_time) * 1000

            # Emit success signal
            self.signals.load_complete.emit(
                self.asset_uuid,
                self.cache_key,
                processed_image,
                elapsed_ms
            )

        except Exception as e:
            self.signals.load_failed.emit(
                self.asset_uuid,
                f"Thumbnail load error: {e}"
            )


class ThumbnailLoader(QObject):
    """
    Manages async thumbnail loading with QThreadPool

    Features:
    - Background loading with worker threads
    - Load deduplication (prevents duplicate requests)
    - Performance monitoring (cache hit rates, load times)
    - QPixmapCache integration
    - DPI scaling support

    Usage:
        loader = get_thumbnail_loader()
        loader.thumbnail_loaded.connect(on_thumbnail_ready)
        pixmap = loader.request_thumbnail(uuid, path, size)
        if pixmap is None:
            # Loading in background, will emit thumbnail_loaded when done
    """

    # Signals
    thumbnail_loaded = pyqtSignal(str, QPixmap)  # uuid, pixmap
    thumbnail_failed = pyqtSignal(str, str)  # uuid, error_message

    def __init__(self, parent=None):
        super().__init__(parent)

        # Thread pool for background loading
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(Config.THUMBNAIL_THREAD_COUNT)

        # Load deduplication - prevents same thumbnail being loaded multiple times
        self.pending_requests: Set[str] = set()

        # Performance monitoring
        self.load_times: list[float] = []
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.total_requests: int = 0

    def request_thumbnail(
        self,
        asset_uuid: str,
        thumbnail_path: str,
        target_size: int = 300
    ) -> Optional[QPixmap]:
        """
        Request thumbnail (returns from cache or starts async load)

        Args:
            asset_uuid: Asset UUID
            thumbnail_path: Path to thumbnail image file
            target_size: Target size for scaling

        Returns:
            QPixmap if in cache, None if loading in background
        """
        if not thumbnail_path:
            return None

        path = Path(thumbnail_path)
        if not path.exists():
            # File missing (possibly moved to archive) - emit failed so UI can refresh from DB
            self.thumbnail_failed.emit(asset_uuid, "File not found (may have been archived)")
            return None

        self.total_requests += 1

        # Generate cache key (includes file mtime for auto-invalidation)
        cache_key = self._generate_cache_key(asset_uuid, target_size, thumbnail_path)

        # Check cache first (fast path)
        pixmap = QPixmapCache.find(cache_key)
        if pixmap:
            self.cache_hits += 1
            return pixmap

        self.cache_misses += 1

        # Check if already loading (deduplication)
        if cache_key in self.pending_requests:
            # Already loading, don't start duplicate request
            return None

        # Not in cache - start background load
        self.pending_requests.add(cache_key)

        task = ThumbnailLoadTask(
            asset_uuid,
            path,
            cache_key,
            target_size=target_size
        )

        # Connect signals
        task.signals.load_complete.connect(self._on_load_complete)
        task.signals.load_failed.connect(self._on_load_failed)

        # Start task in thread pool
        self.thread_pool.start(task)

        return None  # Caller should show placeholder

    def _on_load_complete(self, uuid: str, cache_key: str, image: QImage, elapsed_ms: float):
        """Handle successful thumbnail load"""
        # Remove from pending
        self.pending_requests.discard(cache_key)

        # Track load time
        self.load_times.append(elapsed_ms)

        # Convert to pixmap
        pixmap = QPixmap.fromImage(image)

        # Store in cache
        QPixmapCache.insert(cache_key, pixmap)

        # Emit signal so views can update
        self.thumbnail_loaded.emit(uuid, pixmap)

    def _on_load_failed(self, uuid: str, error_message: str):
        """Handle failed thumbnail load"""
        # Remove from pending using exact cache key prefix matching
        # Use f"asset_{uuid}_" to avoid uuid_1 matching uuid_11
        key_prefix = f"asset_{uuid}_"
        to_remove = [key for key in self.pending_requests if key.startswith(key_prefix)]
        for key in to_remove:
            self.pending_requests.discard(key)

        # Emit failure signal
        self.thumbnail_failed.emit(uuid, error_message)

    def _generate_cache_key(self, asset_uuid: str, target_size: int, thumbnail_path: str = None) -> str:
        """Generate unique cache key for thumbnail.
        
        Includes file modification time so cache auto-invalidates when file changes.
        """
        mtime_suffix = ""
        if thumbnail_path:
            try:
                path = Path(thumbnail_path)
                if path.exists():
                    mtime_suffix = f"_{int(path.stat().st_mtime)}"
            except Exception:
                pass
        return f"asset_{asset_uuid}_{target_size}{mtime_suffix}"
    
    def invalidate_thumbnail(self, asset_uuid: str):
        """Remove cached thumbnails for a specific asset.
        
        Call this when a thumbnail file has been updated externally.
        """
        # QPixmapCache doesn't support prefix removal, so we need to
        # remove common sizes manually
        for size in [64, 128, 256, 300, 512]:
            # Try without mtime (old keys) and hope it matches
            key = f"asset_{asset_uuid}_{size}"
            QPixmapCache.remove(key)
        
        # Also remove from pending requests
        to_remove = [k for k in self.pending_requests if asset_uuid in k]
        for k in to_remove:
            self.pending_requests.discard(k)

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics

        Returns:
            Dict with cache statistics
        """
        hit_rate = (self.cache_hits / self.total_requests * 100) if self.total_requests > 0 else 0
        avg_load_time = (sum(self.load_times) / len(self.load_times)) if self.load_times else 0

        return {
            'total_requests': self.total_requests,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_hit_rate': hit_rate,
            'avg_load_time_ms': avg_load_time,
            'pending_count': len(self.pending_requests),
            'thread_count': self.thread_pool.maxThreadCount(),
        }

    def clear_cache(self):
        """Clear QPixmapCache"""
        QPixmapCache.clear()
        self.pending_requests.clear()

    def reset_stats(self):
        """Reset performance statistics"""
        self.load_times.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_requests = 0


# Singleton instance
_thumbnail_loader_instance: Optional[ThumbnailLoader] = None


def get_thumbnail_loader() -> ThumbnailLoader:
    """
    Get global ThumbnailLoader singleton

    Returns:
        Global ThumbnailLoader instance
    """
    global _thumbnail_loader_instance
    if _thumbnail_loader_instance is None:
        _thumbnail_loader_instance = ThumbnailLoader()
    return _thumbnail_loader_instance


__all__ = ['ThumbnailLoader', 'ThumbnailLoadTask', 'get_thumbnail_loader']
