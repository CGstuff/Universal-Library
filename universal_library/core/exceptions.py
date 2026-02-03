"""
Custom exceptions for Universal Library

Pattern: Domain-specific exceptions for proper error handling
Allows services to propagate errors to UI layer.
"""


class AssetLibraryError(Exception):
    """Base exception for all asset library errors"""

    def __init__(self, message: str, details: str = None):
        self.message = message
        self.details = details
        super().__init__(message)

    def __str__(self):
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class DatabaseError(AssetLibraryError):
    """Database operation failed"""
    pass


class AssetNotFoundError(AssetLibraryError):
    """Asset with given UUID not found"""
    pass


class FolderNotFoundError(AssetLibraryError):
    """Folder with given ID not found"""
    pass


class DuplicateAssetError(AssetLibraryError):
    """Asset with same UUID already exists"""
    pass


class DuplicateFolderError(AssetLibraryError):
    """Folder with same name exists at this location"""
    pass


class FileOperationError(AssetLibraryError):
    """File system operation failed"""
    pass


class BlenderConnectionError(AssetLibraryError):
    """Failed to communicate with Blender"""
    pass


class ThumbnailError(AssetLibraryError):
    """Thumbnail generation or loading failed"""
    pass


class ValidationError(AssetLibraryError):
    """Input validation failed"""

    def __init__(self, message: str, field: str = None, value: any = None):
        self.field = field
        self.value = value
        details = f"field={field}, value={value}" if field else None
        super().__init__(message, details)


class TransactionError(AssetLibraryError):
    """Database transaction failed"""
    pass


__all__ = [
    'AssetLibraryError',
    'DatabaseError',
    'AssetNotFoundError',
    'FolderNotFoundError',
    'DuplicateAssetError',
    'DuplicateFolderError',
    'FileOperationError',
    'BlenderConnectionError',
    'ThumbnailError',
    'ValidationError',
    'TransactionError',
]
