"""
Version History Dialog - Asset lineage management.

Modular structure:
- config.py: Configuration constants
- preview_panel.py: Async preview loading
- tree_view.py: Tree view with badges
- list_view.py: Table view
- action_handlers.py: Button handlers
- variant_manager.py: Create variant workflow
"""

from .version_history_dialog import VersionHistoryDialog

__all__ = ['VersionHistoryDialog']
