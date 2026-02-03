"""
Gizmos for Universal Library
"""

from . import thumbnail_helper


def register():
    thumbnail_helper.register()


def unregister():
    thumbnail_helper.unregister()
