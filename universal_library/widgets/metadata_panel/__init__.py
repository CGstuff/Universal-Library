"""
MetadataPanel - Asset metadata display widget.

Modular structure:
- panels/: Sub-panels for identification, lineage, tags, folders
- renderers/: Technical info and review state rendering
- utils.py: Formatting utilities
"""

from .metadata_panel import MetadataPanel

__all__ = ['MetadataPanel']
