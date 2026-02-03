"""
Decorators for Blender Operators

Provides reusable decorators for common operator patterns like
error handling and library connection requirements.
"""

from functools import wraps
from typing import Callable, Any
import traceback


def require_library_connection(func: Callable) -> Callable:
    """
    Decorator that ensures library is connected before operator runs.

    Sets self._library to the library connection for use in the operator.

    Usage:
        class MyOperator(Operator):
            @require_library_connection
            def execute(self, context):
                # self._library is available here
                asset = self._library.get_asset_by_uuid(uuid)

    Returns:
        {'CANCELLED'} if library not connected, otherwise function result
    """
    @wraps(func)
    def wrapper(self, context):
        from .library_connection import get_library_connection

        library = get_library_connection()
        if not library:
            self.report({'ERROR'}, "Library not connected. Check addon preferences.")
            return {'CANCELLED'}

        self._library = library
        return func(self, context)

    return wrapper


def handle_errors(error_message: str = "Operation failed"):
    """
    Decorator for consistent error handling in operators.

    Catches exceptions and reports them with a user-friendly message.

    Args:
        error_message: Base error message to show (exception details appended)

    Usage:
        class MyOperator(Operator):
            @handle_errors("Export failed")
            def execute(self, context):
                # Code that might raise exceptions
                raise ValueError("Something went wrong")
                # User sees: "Export failed: Something went wrong"

    Returns:
        {'CANCELLED'} on exception, otherwise function result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, context):
            try:
                return func(self, context)
            except Exception as e:
                self.report({'ERROR'}, f"{error_message}: {e}")
                traceback.print_exc()
                return {'CANCELLED'}

        return wrapper
    return decorator


def require_selection(min_count: int = 1, object_types: tuple = None):
    """
    Decorator that ensures objects are selected before operator runs.

    Args:
        min_count: Minimum number of objects required
        object_types: Tuple of allowed object types (e.g., ('MESH', 'ARMATURE'))

    Usage:
        class MyOperator(Operator):
            @require_selection(min_count=1, object_types=('MESH',))
            def execute(self, context):
                # At least 1 MESH is selected
                pass

    Returns:
        {'CANCELLED'} if selection requirements not met
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, context):
            selected = context.selected_objects

            if len(selected) < min_count:
                self.report({'ERROR'}, f"Select at least {min_count} object(s)")
                return {'CANCELLED'}

            if object_types:
                valid_objects = [obj for obj in selected if obj.type in object_types]
                if len(valid_objects) < min_count:
                    types_str = ", ".join(object_types)
                    self.report({'ERROR'}, f"Select at least {min_count} {types_str} object(s)")
                    return {'CANCELLED'}

            return func(self, context)

        return wrapper
    return decorator


def log_execution(operation_name: str = None):
    """
    Decorator that logs operator execution for debugging.

    Args:
        operation_name: Name to use in log messages (defaults to function name)

    Usage:
        class MyOperator(Operator):
            @log_execution("Asset Export")
            def execute(self, context):
                pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, context):
            name = operation_name or func.__name__
            try:
                result = func(self, context)
                return result
            except Exception as e:
                raise

        return wrapper
    return decorator


def with_library(func: Callable) -> Callable:
    """
    Simplified decorator that provides library as first argument after self.

    Similar to require_library_connection but passes library as argument.

    Usage:
        class MyOperator(Operator):
            @with_library
            def execute(self, context, library):
                asset = library.get_asset_by_uuid(uuid)
    """
    @wraps(func)
    def wrapper(self, context):
        from .library_connection import get_library_connection

        library = get_library_connection()
        if not library:
            self.report({'ERROR'}, "Library not connected. Check addon preferences.")
            return {'CANCELLED'}

        return func(self, context, library)

    return wrapper


__all__ = [
    'require_library_connection',
    'handle_errors',
    'require_selection',
    'log_execution',
    'with_library',
]
