"""
Control Authority - Determines who controls asset status and delete behavior.

This service provides a central point for checking operation mode:
- STANDALONE: Universal Library has full control, permanent delete allowed
- STUDIO: Multi-user environment, retire instead of delete, audit trail
- PIPELINE: External apps (Pipeline Control) control asset status, retire instead of delete

The operation mode is stored in the shared database.db so that
Pipeline Control and other external tools can detect the configuration.
"""

from enum import Enum
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    from .database_service import DatabaseService


class OperationMode(Enum):
    """Operation mode for Universal Library."""

    STANDALONE = "standalone"  # Universal Library controls everything, permanent delete allowed
    STUDIO = "studio"          # Multi-user environment, retire instead of delete
    PIPELINE = "pipeline"      # Pipeline Control manages asset status, retire instead of delete


class ControlAuthority(QObject):
    """
    Central service for operation mode checking.
    
    Singleton pattern - use get_control_authority() to get the instance.
    
    Signals:
        mode_changed: Emitted when operation mode changes (OperationMode)
    """
    
    mode_changed = pyqtSignal(object)  # OperationMode
    
    _instance: Optional["ControlAuthority"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._initialized = True
        self._db_service: Optional["DatabaseService"] = None
        self._cached_mode: Optional[OperationMode] = None
    
    def set_db_service(self, db_service: "DatabaseService") -> None:
        """
        Set the database service for persistence.
        
        Args:
            db_service: DatabaseService instance for reading/writing settings
        """
        self._db_service = db_service
        # Clear cache when db service changes
        self._cached_mode = None
    
    def get_operation_mode(self) -> OperationMode:
        """
        Get current operation mode from shared database.
        
        Returns:
            OperationMode.STANDALONE or OperationMode.PIPELINE
        """
        if self._cached_mode is not None:
            return self._cached_mode
        
        if not self._db_service:
            return OperationMode.STANDALONE
        
        try:
            mode_str = self._db_service.get_app_setting("operation_mode", "standalone")
            self._cached_mode = OperationMode(mode_str)
            return self._cached_mode
        except (ValueError, Exception):
            return OperationMode.STANDALONE
    
    def set_operation_mode(self, mode: OperationMode) -> bool:
        """
        Set operation mode in shared database.
        
        Args:
            mode: The operation mode to set
            
        Returns:
            True if successful, False otherwise
        """
        if not self._db_service:
            return False
        
        try:
            success = self._db_service.set_app_setting("operation_mode", mode.value)
            if success:
                old_mode = self._cached_mode
                self._cached_mode = mode
                if old_mode != mode:
                    self.mode_changed.emit(mode)
            return success
        except Exception as e:
            return False
    
    def can_edit_status(self) -> bool:
        """
        Check if status editing is allowed.
        
        Only allowed in Standalone mode. In Pipeline mode,
        status is controlled by Pipeline Control.
        
        Returns:
            True if Universal Library can edit asset status
        """
        return self.get_operation_mode() == OperationMode.STANDALONE
    
    def is_pipeline_mode(self) -> bool:
        """
        Check if Pipeline Control is the status authority.
        
        Returns:
            True if in Pipeline mode
        """
        return self.get_operation_mode() == OperationMode.PIPELINE
    
    def is_standalone_mode(self) -> bool:
        """
        Check if Universal Library has full control.

        Returns:
            True if in Standalone mode
        """
        return self.get_operation_mode() == OperationMode.STANDALONE

    def is_studio_mode(self) -> bool:
        """
        Check if in Studio mode (multi-user environment).

        Returns:
            True if in Studio mode
        """
        return self.get_operation_mode() == OperationMode.STUDIO

    def can_delete(self) -> bool:
        """
        Check if permanent delete is allowed.

        Only allowed in Standalone mode. In Studio/Pipeline modes,
        assets are retired instead of deleted.

        Returns:
            True if permanent delete is allowed (Standalone mode only)
        """
        return self.get_operation_mode() == OperationMode.STANDALONE

    def clear_cache(self) -> None:
        """Clear the cached mode to force a fresh read from database."""
        self._cached_mode = None
    
    def get_mode_description(self) -> str:
        """
        Get a human-readable description of the current mode.

        Returns:
            Description string for UI display
        """
        mode = self.get_operation_mode()
        if mode == OperationMode.STANDALONE:
            return "Standalone - Universal Library controls asset status"
        elif mode == OperationMode.STUDIO:
            return "Studio - Multi-user mode with retire instead of delete"
        else:
            return "Pipeline - Status controlled by Pipeline Control"


# Module-level singleton accessor
_control_authority: Optional[ControlAuthority] = None


def get_control_authority() -> ControlAuthority:
    """
    Get the singleton ControlAuthority instance.
    
    Returns:
        The global ControlAuthority instance
    """
    global _control_authority
    if _control_authority is None:
        _control_authority = ControlAuthority()
    return _control_authority


__all__ = ['OperationMode', 'ControlAuthority', 'get_control_authority']
