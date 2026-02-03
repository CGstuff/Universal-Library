"""
Base service class for Universal Library.

Provides a standardized singleton pattern for all services:
- Thread-safe singleton access via get_instance()
- Separate initialize() method for setup after construction
- Consistent pattern across all services

Usage:
    class MyService(BaseService):
        def initialize(self):
            # Setup database connections, etc.
            pass

        def do_something(self):
            ...

    # Access singleton
    service = MyService.get_instance()
"""

import threading
from typing import TypeVar, Type

T = TypeVar('T', bound='BaseService')


class BaseService:
    """
    Base class for singleton services.

    Subclasses should:
    1. Override initialize() for setup logic (not __init__)
    2. Access via MyService.get_instance()

    Thread-safe singleton implementation.
    """

    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __init__(self):
        """
        Constructor - do NOT put initialization logic here.
        Use initialize() instead.
        """
        pass

    @classmethod
    def get_instance(cls: Type[T]) -> T:
        """
        Get singleton instance, creating if necessary.

        Thread-safe implementation using double-checked locking.

        Returns:
            The singleton instance of the service
        """
        if cls._instance is None:
            with cls._lock:
                # Double-check after acquiring lock
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance.initialize()
                    cls._initialized = True
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset the singleton instance.

        Useful for testing or reinitializing services.
        """
        with cls._lock:
            if cls._instance is not None:
                cls._instance.shutdown()
            cls._instance = None
            cls._initialized = False

    def initialize(self) -> None:
        """
        Initialize the service.

        Override in subclasses to set up resources:
        - Database connections
        - File handles
        - Caches
        - Event listeners

        Called automatically by get_instance() on first access.
        """
        pass

    def shutdown(self) -> None:
        """
        Clean up resources.

        Override in subclasses to release resources:
        - Close database connections
        - Flush caches
        - Remove event listeners

        Called automatically by reset_instance().
        """
        pass


# Convenience function for services that want a module-level getter
def create_service_getter(service_class: Type[T]):
    """
    Create a getter function for a service.

    Usage:
        class MyService(BaseService):
            ...

        get_my_service = create_service_getter(MyService)

    Args:
        service_class: The service class to create a getter for

    Returns:
        A function that returns the singleton instance
    """
    def getter() -> T:
        return service_class.get_instance()
    return getter


__all__ = ['BaseService', 'create_service_getter']
