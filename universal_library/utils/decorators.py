"""
Utility decorators for Universal Library

Simple, practical decorators added as needed.
"""

import time
import logging
import functools
from typing import Callable, Any, TypeVar, Optional

logger = logging.getLogger(__name__)

T = TypeVar('T')


def timed(func: Callable) -> Callable:
    """
    Decorator to log execution time of a function.

    Usage:
        @timed
        def slow_operation():
            ...

    Logs: "slow_operation took 123.4ms"
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(f"{func.__name__} took {elapsed_ms:.1f}ms")
        return result
    return wrapper


def timed_info(func: Callable) -> Callable:
    """
    Same as @timed but logs at INFO level (visible by default).

    Use for operations you always want to see timing for.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(f"{func.__name__} took {elapsed_ms:.1f}ms")
        return result
    return wrapper


def safe_db_operation(default: Any = None, log_level: int = logging.WARNING):
    """
    Decorator for database operations that should not raise exceptions.

    Catches exceptions, logs them, and returns a default value.
    Use for operations where failure should not crash the application.

    Args:
        default: Value to return on failure (default: None)
        log_level: Logging level for errors (default: WARNING)

    Usage:
        @safe_db_operation(default=[])
        def get_items():
            ...

        @safe_db_operation(default=False)
        def update_item(item_id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.log(
                    log_level,
                    f"{func.__name__} failed: {e}",
                    exc_info=log_level <= logging.DEBUG
                )
                return default
        return wrapper
    return decorator


def transactional(connection_getter: str = '_get_connection'):
    """
    Decorator for wrapping methods in a database transaction.

    Automatically commits on success, rolls back on failure.
    The decorated method's class must have a method that returns
    a sqlite3.Connection (default: _get_connection).

    Args:
        connection_getter: Name of method to get connection (default: '_get_connection')

    Usage:
        class MyRepository:
            def _get_connection(self):
                return self._conn

            @transactional()
            def update_multiple(self, items):
                # All operations in this method are wrapped in a transaction
                for item in items:
                    self._do_update(item)

    Note:
        This decorator is for methods on classes with a connection getter.
        For standalone functions, use the transaction context manager directly.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs) -> Any:
            # Get connection from the instance
            get_conn = getattr(self, connection_getter, None)
            if get_conn is None:
                raise AttributeError(
                    f"Class {self.__class__.__name__} has no method '{connection_getter}'"
                )

            conn = get_conn()
            try:
                result = func(self, *args, **kwargs)
                conn.commit()
                return result
            except Exception as e:
                conn.rollback()
                raise
        return wrapper
    return decorator


def validate_not_none(*param_names: str):
    """
    Decorator to validate that specified parameters are not None.

    Args:
        *param_names: Names of parameters that must not be None

    Usage:
        @validate_not_none('uuid', 'name')
        def update_asset(self, uuid: str, name: str):
            ...

    Raises:
        ValueError: If any specified parameter is None
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            import inspect
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            for param_name in param_names:
                if param_name in bound.arguments:
                    value = bound.arguments[param_name]
                    if value is None:
                        raise ValueError(
                            f"Parameter '{param_name}' in {func.__name__} cannot be None"
                        )

            return func(*args, **kwargs)
        return wrapper
    return decorator


__all__ = ['timed', 'timed_info', 'safe_db_operation', 'transactional', 'validate_not_none']
