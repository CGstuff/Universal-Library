"""
Event system for Universal Library

Central event bus for cross-widget communication.
Entity event bus for extensible entity system events.
"""

from .event_bus import EventBus, get_event_bus
from .entity_events import EntityEventBus, get_entity_event_bus

__all__ = [
    'EventBus',
    'get_event_bus',
    'EntityEventBus',
    'get_entity_event_bus',
]
