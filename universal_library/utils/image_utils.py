"""
Image utilities for loading and processing

Pattern: Image loading helpers
Based on animation_library patterns.
"""

from pathlib import Path
from typing import Optional, Tuple
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt


def load_image_as_pixmap(
    image_path: Path,
    max_size: Optional[int] = None,
    smooth_scaling: bool = True
) -> Optional[QPixmap]:
    """
    Load image file as QPixmap with optional scaling

    Args:
        image_path: Path to image file
        max_size: Maximum dimension (width or height)
        smooth_scaling: Use smooth scaling algorithm

    Returns:
        QPixmap or None if load failed
    """
    if not image_path.exists():
        return None

    pixmap = QPixmap(str(image_path))
    if pixmap.isNull():
        return None

    # Scale if max_size specified
    if max_size and (pixmap.width() > max_size or pixmap.height() > max_size):
        transform_mode = Qt.TransformationMode.SmoothTransformation if smooth_scaling else Qt.TransformationMode.FastTransformation
        pixmap = pixmap.scaled(
            max_size,
            max_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            transform_mode
        )

    return pixmap


def load_image_as_qimage(image_path: Path) -> Optional[QImage]:
    """
    Load image file as QImage

    Args:
        image_path: Path to image file

    Returns:
        QImage or None if load failed
    """
    if not image_path.exists():
        return None

    image = QImage(str(image_path))
    if image.isNull():
        return None

    return image


def get_image_size(image_path: Path) -> Optional[Tuple[int, int]]:
    """
    Get image dimensions without loading full image

    Args:
        image_path: Path to image file

    Returns:
        Tuple of (width, height) or None
    """
    if not image_path.exists():
        return None

    image = QImage(str(image_path))
    if image.isNull():
        return None

    return (image.width(), image.height())


def scale_image(
    image: QImage,
    max_size: int,
    smooth: bool = True
) -> QImage:
    """
    Scale QImage to fit within max_size

    Args:
        image: Source QImage
        max_size: Maximum dimension
        smooth: Use smooth scaling

    Returns:
        Scaled QImage
    """
    if image.width() <= max_size and image.height() <= max_size:
        return image

    transform_mode = Qt.TransformationMode.SmoothTransformation if smooth else Qt.TransformationMode.FastTransformation

    return image.scaled(
        max_size,
        max_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        transform_mode
    )


def scale_and_crop_image(
    image: QImage,
    target_size: int,
    smooth: bool = True
) -> QImage:
    """
    Scale and center-crop QImage to exact target size

    Args:
        image: Source QImage
        target_size: Target width and height
        smooth: Use smooth scaling

    Returns:
        Scaled and cropped QImage
    """
    transform_mode = Qt.TransformationMode.SmoothTransformation if smooth else Qt.TransformationMode.FastTransformation

    # Scale to fit (expanding to cover target)
    scaled = image.scaled(
        target_size,
        target_size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        transform_mode
    )

    # Center crop
    x_offset = (scaled.width() - target_size) // 2
    y_offset = (scaled.height() - target_size) // 2

    return scaled.copy(x_offset, y_offset, target_size, target_size)


__all__ = [
    'load_image_as_pixmap',
    'load_image_as_qimage',
    'get_image_size',
    'scale_image',
    'scale_and_crop_image',
]
