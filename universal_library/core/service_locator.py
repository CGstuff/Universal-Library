"""
Service Locator for Universal Library.

Provides a central registry for services, enabling:
- Loose coupling between components
- Easy testing with mock services
- Runtime service discovery

Usage:
    # Registration (typically in app startup)
    ServiceLocator.register('review', ReviewService.get_instance())
    ServiceLocator.register('asset', AssetService.get_instance())

    # Usage (anywhere in the app)
    review_service = ServiceLocator.get('review')

    # Testing (swap with mock)
    ServiceLocator.register('review', MockReviewService())
"""

import threading
from typing import Dict, Any, Optional, TypeVar, Type

T = TypeVar('T')


class ServiceLocator:
    """
    Central registry for service instances.

    Thread-safe implementation for service registration and retrieval.
    Supports both instance registration and lazy initialization.
    """

    _services: Dict[str, Any] = {}
    _factories: Dict[str, callable] = {}
    _lock = threading.Lock()

    @classmethod
    def register(cls, name: str, service: Any) -> None:
        """
        Register a service instance.

        Args:
            name: Service name (e.g., 'review', 'asset', 'database')
            service: The service instance to register
        """
        with cls._lock:
            cls._services[name] = service

    @classmethod
    def register_factory(cls, name: str, factory: callable) -> None:
        """
        Register a factory function for lazy service creation.

        The factory is called on first access and the result is cached.

        Args:
            name: Service name
            factory: Callable that returns the service instance
        """
        with cls._lock:
            cls._factories[name] = factory

    @classmethod
    def get(cls, name: str) -> Optional[Any]:
        """
        Get a service by name.

        If a factory was registered, creates the service on first access.

        Args:
            name: Service name

        Returns:
            The service instance, or None if not found
        """
        # Check if already instantiated
        service = cls._services.get(name)
        if service is not None:
            return service

        # Check if factory exists
        with cls._lock:
            if name in cls._factories and name not in cls._services:
                cls._services[name] = cls._factories[name]()

        return cls._services.get(name)

    @classmethod
    def get_typed(cls, name: str, expected_type: Type[T]) -> Optional[T]:
        """
        Get a service by name with type checking.

        Args:
            name: Service name
            expected_type: Expected type of the service

        Returns:
            The service instance if it matches the type, None otherwise
        """
        service = cls.get(name)
        if service is not None and isinstance(service, expected_type):
            return service
        return None

    @classmethod
    def has(cls, name: str) -> bool:
        """
        Check if a service is registered.

        Args:
            name: Service name

        Returns:
            True if service or factory is registered
        """
        return name in cls._services or name in cls._factories

    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        Remove a service from the registry.

        Args:
            name: Service name

        Returns:
            True if service was removed, False if not found
        """
        with cls._lock:
            removed = False
            if name in cls._services:
                del cls._services[name]
                removed = True
            if name in cls._factories:
                del cls._factories[name]
                removed = True
            return removed

    @classmethod
    def clear(cls) -> None:
        """
        Remove all registered services.

        Useful for testing or application shutdown.
        """
        with cls._lock:
            cls._services.clear()
            cls._factories.clear()

    @classmethod
    def list_services(cls) -> list:
        """
        List all registered service names.

        Returns:
            List of service names
        """
        return list(set(cls._services.keys()) | set(cls._factories.keys()))


# Well-known service names (constants for type safety)
class ServiceNames:
    """Well-known service names to avoid typos."""

    REVIEW = 'review'
    ASSET = 'asset'
    FOLDER = 'folder'
    DATABASE = 'database'
    USER = 'user'
    THUMBNAIL = 'thumbnail'
    BLENDER = 'blender'


__all__ = ['ServiceLocator', 'ServiceNames']
