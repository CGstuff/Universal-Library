"""
Metadata panel sub-panels.
"""

from .identification import IdentificationPanel
from .lineage import LineagePanel
from .thumbnail import ThumbnailPanel
from .tags import TagsWidget
from .folders import FoldersWidget
from .representations_dialog import RepresentationsDialog

__all__ = [
    'IdentificationPanel',
    'LineagePanel',
    'ThumbnailPanel',
    'TagsWidget',
    'FoldersWidget',
    'RepresentationsDialog',
]
