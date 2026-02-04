"""
FolderTree - Folder navigation tree

Pattern: QTreeWidget for folder hierarchy
Based on animation_library architecture.

Virtual Folder System:
- Type folders (meshes, materials, rigs, etc.) are physical for asset type organization
- User folders are VIRTUAL (database only) - no physical directories created
- Moving assets between folders = database update only, files never move
- This ensures linked/instanced assets never have broken paths

Layout:
    All Assets, Favorites, Recent (virtual special folders)
    ─────────────────
    Meshes, Materials, Rigs... (physical type folders - filter by asset type)
    ─────────────────
    User Folder 1, User Folder 2... (virtual database folders - organize assets)
"""

from pathlib import Path
from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu, QAbstractItemView,
    QInputDialog, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QPoint, QTimer
from PyQt6.QtGui import QAction, QFont, QColor, QIcon

from ..config import Config
from ..services.database_service import get_database_service
from ..services.user_service import get_user_service
from ..services.control_authority import get_control_authority, OperationMode
from ..events.event_bus import get_event_bus


class FolderTree(QTreeWidget):
    """
    Tree widget for folder navigation

    Features:
    - Virtual folders (All Assets, Recent, Favorites)
    - User folders from database
    - Context menus (create, rename, delete)
    - Drag & drop support for moving assets
    - Selection handling

    Layout:
        All Assets
        Favorites
        Recent
        ───────────────
        User Folder 1
        User Folder 2
          └─ Subfolder
    """

    # Signals
    folder_selected = pyqtSignal(int)  # folder_id (negative for virtual)
    asset_type_selected = pyqtSignal(str)  # asset_type when system folder selected (empty string = clear filter)
    physical_path_selected = pyqtSignal(str)  # physical path for subfolder filtering (empty string = clear filter)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._db_service = get_database_service()
        self._user_service = get_user_service()
        self._control_authority = get_control_authority()
        self._event_bus = get_event_bus()
        self._dragged_folder_item = None  # Track dragged folder
        self._review_folder_item = None  # Review folder (hidden in standalone mode)

        self._setup_tree()
        self._load_folders()
        self._connect_signals()
        self._update_review_folder_visibility()

    def _setup_tree(self):
        """Configure tree widget"""

        # Hide header
        self.setHeaderHidden(True)

        # Selection
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)

        # Drag & drop for folders and receiving assets
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Styling
        self.setAlternatingRowColors(True)
        self.setMinimumWidth(180)
        self.setIndentation(16)

    def _connect_signals(self):
        """Connect internal signals"""
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self._control_authority.mode_changed.connect(self._on_operation_mode_changed)

    def _on_operation_mode_changed(self, mode):
        """Handle operation mode change - show/hide review folder."""
        self._update_review_folder_visibility()

    def _update_review_folder_visibility(self):
        """Update review folder visibility based on operation mode.
        
        Review features are visible in Studio and Pipeline modes only,
        hidden in Standalone mode.
        """
        if self._review_folder_item:
            # Show review folder in Studio or Pipeline mode, hide in Standalone
            show_review = self._control_authority.get_operation_mode() != OperationMode.STANDALONE
            self._review_folder_item.setHidden(not show_review)

    def _load_folders(self):
        """Load folders from database and create tree"""
        self.clear()

        # Create virtual folders
        self._create_virtual_folders()

        # Add separator
        separator = QTreeWidgetItem(self)
        separator.setText(0, "─" * 15)
        separator.setFlags(Qt.ItemFlag.NoItemFlags)

        # Create physical type folders (system folders)
        # These folders map to physical directories on disk
        # User subfolders under types are virtual (database-only)
        self._create_type_folders()

        # Apply studio mode visibility to review folder
        self._update_review_folder_visibility()

        # Select "All Assets" by default
        if self.topLevelItemCount() > 0:
            self.setCurrentItem(self.topLevelItem(0))

    def _create_virtual_folders(self):
        """Create virtual folders"""

        # Main virtual folders (top level)
        virtual_folders = [
            (Config.VIRTUAL_FOLDER_ALL, "All Assets"),
            (Config.VIRTUAL_FOLDER_BASE, "Base"),
            (Config.VIRTUAL_FOLDER_VARIANTS, "Variants"),
            (Config.VIRTUAL_FOLDER_FAVORITES, "Favorites"),
            (Config.VIRTUAL_FOLDER_RECENT, "Recent"),
            # Cold Storage hidden - automatic archiving via .archive handles old versions
        ]

        for folder_id, folder_name in virtual_folders:
            item = QTreeWidgetItem(self)
            item.setText(0, folder_name)
            item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'virtual',
                'folder_id': folder_id,
                'folder_name': folder_name
            })

            # Make virtual folders bold
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)

        # Review section with child folders (hidden in solo mode)
        self._review_folder_item = QTreeWidgetItem(self)
        self._review_folder_item.setText(0, "Review")
        self._review_folder_item.setData(0, Qt.ItemDataRole.UserRole, {
            'type': 'virtual_group',
            'folder_name': 'Review'
        })

        # Make review parent bold
        font = self._review_folder_item.font(0)
        font.setBold(True)
        self._review_folder_item.setFont(0, font)

        # Review workflow folders (children of Review)
        review_folders = [
            (Config.VIRTUAL_FOLDER_NEEDS_REVIEW, "Needs Review"),
            (Config.VIRTUAL_FOLDER_IN_REVIEW, "In Review"),
            (Config.VIRTUAL_FOLDER_IN_PROGRESS, "In Progress"),
            (Config.VIRTUAL_FOLDER_APPROVED, "Approved"),
            (Config.VIRTUAL_FOLDER_FINAL, "Final"),
        ]

        for folder_id, folder_name in review_folders:
            item = QTreeWidgetItem(self._review_folder_item)
            item.setText(0, folder_name)
            item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'virtual',
                'folder_id': folder_id,
                'folder_name': folder_name
            })

        # Expand review section by default
        self._review_folder_item.setExpanded(True)

    def _create_type_folders(self):
        """
        Create physical asset type folders in the tree.

        These are system folders that:
        - Map to physical directories (library/meshes/, library/materials/, etc.)
        - Cannot be deleted from the app
        - Auto-recreate if physically deleted
        - User subfolders are virtual (database-only) to prevent broken links
        """
        library_folder = Config.get_library_folder()

        # Store type folder items for later reference
        self._type_folder_items = {}

        # Type folder display names and SVG icon filenames
        icons_dir = Path(__file__).parent / 'icons' / 'data_types'
        type_display = {
            'mesh': ('Meshes', 'mesh_data.svg'),
            'material': ('Materials', 'material_data.svg'),
            'rig': ('Rigs', 'armature_data.svg'),
            'light': ('Lights', 'light_data.svg'),
            'camera': ('Cameras', 'camera_data.svg'),
            'collection': ('Collections', 'collection.svg'),
            'grease_pencil': ('Grease_pencils', 'gp_data.svg'),
            'curve': ('Curves', 'curve_data.svg'),
            'scene': ('Scenes', 'scene_data.svg'),
            'other': ('Other', 'object_data.svg'),
        }

        for asset_type in Config.ASSET_TYPES:
            folder_name = Config.get_type_folder(asset_type)
            display_name, icon_file = type_display.get(asset_type, (folder_name.capitalize(), 'object_data.svg'))

            # Ensure physical folder exists (auto-recreate if deleted)
            physical_path = library_folder / folder_name
            physical_path.mkdir(parents=True, exist_ok=True)

            # Create tree item
            item = QTreeWidgetItem(self)
            item.setText(0, display_name)
            icon_path = icons_dir / icon_file
            if icon_path.exists():
                item.setIcon(0, QIcon(str(icon_path)))

            # Store metadata - mark as 'system' type
            item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'system',
                'asset_type': asset_type,
                'folder_name': folder_name,
                'physical_path': str(physical_path),
                'display_name': display_name
            })

            # Styling
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)

            # Store reference
            self._type_folder_items[asset_type] = item

            # Load virtual subfolders from database for this asset type
            self._load_virtual_subfolders(item, asset_type)

    def _load_virtual_subfolders(self, parent_item: QTreeWidgetItem, asset_type: str):
        """
        Load virtual subfolders from database for a specific asset type.
        
        Folders are identified by having 'asset_type:{type}' in their description.
        """
        folders = self._db_service.get_all_folders()
        
        # Find the type root folder
        type_root_name = f"__type_root_{asset_type}__"
        type_root_id = None
        
        for folder in folders:
            if folder.get('name') == type_root_name:
                type_root_id = folder['id']
                break
        
        if type_root_id is None:
            return  # No folders for this type yet
        
        # Build folder tree for this type
        folder_dict = {f['id']: f for f in folders}
        self._build_type_folder_tree(type_root_id, folder_dict, parent_item, asset_type)
    
    def _build_type_folder_tree(self, parent_id: int, folder_dict: dict, 
                                 parent_item: QTreeWidgetItem, asset_type: str):
        """Recursively build folder tree under a type folder."""
        
        # Find children of this parent
        children = [f for f in folder_dict.values() if f.get('parent_id') == parent_id]
        children.sort(key=lambda f: f['name'].lower())
        
        for folder in children:
            # Skip type root markers
            if folder['name'].startswith('__type_root_'):
                continue
            
            # Create tree item
            item = QTreeWidgetItem(parent_item)
            item.setText(0, folder['name'])
            
            # Store metadata
            item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'user',
                'folder_id': folder['id'],
                'folder_name': folder['name'],
                'asset_type': asset_type  # Inherit from parent type folder
            })
            
            # Recursively build children
            self._build_type_folder_tree(folder['id'], folder_dict, item, asset_type)

    def _on_selection_changed(self):
        """Handle selection change"""

        selected_items = self.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)

        if not data:
            return

        folder_type = data.get('type')

        # Handle system folders (type folders like meshes, materials, etc.)
        if folder_type == 'system':
            asset_type = data.get('asset_type', '')
            physical_path = data.get('physical_path', '')
            # Emit asset type filter signal
            self.asset_type_selected.emit(asset_type)
            # Emit physical path for the type folder root (shows all assets in that type)
            self.physical_path_selected.emit(physical_path)
            # Use VIRTUAL_FOLDER_ALL as the folder filter (show all in folder terms)
            self.folder_selected.emit(Config.VIRTUAL_FOLDER_ALL)
            self._event_bus.emit_folder_selected(Config.VIRTUAL_FOLDER_ALL)
            return

        # Handle user folders (virtual database folders)
        if folder_type == 'user':
            folder_id = data.get('folder_id')
            asset_type = data.get('asset_type', '')

            # Filter by asset type if folder is under a type folder
            if asset_type:
                self.asset_type_selected.emit(asset_type)
            else:
                self.asset_type_selected.emit('')

            # Clear physical path filter (virtual folders don't use physical paths)
            self.physical_path_selected.emit('')

            # Emit folder_id for filtering by folder membership
            self.folder_selected.emit(folder_id if folder_id else Config.VIRTUAL_FOLDER_ALL)
            self._event_bus.emit_folder_selected(folder_id if folder_id else Config.VIRTUAL_FOLDER_ALL)
            return

        # For virtual folders, clear the asset type filter and physical path filter
        self.asset_type_selected.emit('')  # Clear asset type filter
        self.physical_path_selected.emit('')  # Clear physical path filter

        folder_id = data.get('folder_id')

        # Emit signal
        self.folder_selected.emit(folder_id if folder_id is not None else Config.VIRTUAL_FOLDER_ALL)

        # Update event bus
        self._event_bus.emit_folder_selected(folder_id if folder_id is not None else Config.VIRTUAL_FOLDER_ALL)

    def _on_context_menu(self, position: QPoint):
        """Handle context menu request"""

        item = self.itemAt(position)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        menu = QMenu(self)

        if data.get('type') == 'system':
            # Type folder - create subfolder
            asset_type = data.get('asset_type')
            create_action = menu.addAction("Create Folder...")
            action = menu.exec(self.viewport().mapToGlobal(position))
            if action == create_action:
                self._create_folder_under_type(item, asset_type)

        elif data.get('type') == 'user':
            # User folder - create/rename/delete
            folder_id = data.get('folder_id')
            asset_type = data.get('asset_type')

            create_action = menu.addAction("Create Subfolder...")
            menu.addSeparator()
            rename_action = menu.addAction("Rename...")
            delete_action = menu.addAction("Delete")

            action = menu.exec(self.viewport().mapToGlobal(position))

            if action == create_action:
                self._create_folder_under_type(item, asset_type, folder_id)
            elif action == rename_action:
                self._rename_folder(item, folder_id)
            elif action == delete_action:
                self._delete_folder(item, folder_id)

    def _create_folder(self, parent_id: int):
        """Create new folder (legacy - database only)"""

        folder_name, ok = QInputDialog.getText(
            self,
            "Create Folder",
            "Folder name:",
            text="New Folder"
        )

        if not ok or not folder_name.strip():
            return

        folder_name = folder_name.strip()

        folder_id = self._db_service.create_folder(
            name=folder_name,
            parent_id=parent_id
        )

        if folder_id:
            self._load_folders()
            self._event_bus.folder_added.emit(folder_id)
        else:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to create folder '{folder_name}'.\n\nA folder with this name may already exist."
            )

    def _create_folder_under_type(self, parent_item: QTreeWidgetItem, asset_type: str, parent_folder_id: int = None):
        """Create a virtual folder under a type folder or user subfolder."""
        
        folder_name, ok = QInputDialog.getText(
            self,
            "Create Folder",
            "Folder name:",
            text="New Folder"
        )

        if not ok or not folder_name.strip():
            return

        folder_name = folder_name.strip()

        # Get or create root folder for this asset type
        if parent_folder_id is None:
            parent_folder_id = self._get_or_create_type_root(asset_type)

        folder_id = self._db_service.create_folder(
            name=folder_name,
            parent_id=parent_folder_id,
            description=f"asset_type:{asset_type}"  # Store asset type in description for filtering
        )

        if folder_id:
            self._load_folders()
            self._event_bus.folder_added.emit(folder_id)
        else:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to create folder '{folder_name}'.\n\nA folder with this name may already exist."
            )

    def _get_or_create_type_root(self, asset_type: str) -> int:
        """Get or create the root folder for an asset type."""
        # Use a special naming convention for type roots
        root_name = f"__type_root_{asset_type}__"
        
        # Check if it exists
        folders = self._db_service.get_all_folders()
        for folder in folders:
            if folder.get('name') == root_name:
                return folder['id']
        
        # Create it under the global root
        global_root = self._db_service.get_root_folder_id()
        folder_id = self._db_service.create_folder(
            name=root_name,
            parent_id=global_root,
            description=f"asset_type:{asset_type}"
        )
        return folder_id

    def _rename_folder(self, item: QTreeWidgetItem, folder_id: int):
        """Rename folder"""

        current_name = item.text(0)

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Folder",
            "New name:",
            text=current_name
        )

        if not ok or not new_name.strip() or new_name.strip() == current_name:
            return

        new_name = new_name.strip()

        if self._db_service.rename_folder(folder_id, new_name):
            self._load_folders()
            self._event_bus.folder_renamed.emit(folder_id, new_name)
        else:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to rename folder to '{new_name}'."
            )

    def _delete_folder(self, item: QTreeWidgetItem, folder_id: int):
        """Delete folder"""

        folder_name = item.text(0)

        reply = QMessageBox.question(
            self,
            "Delete Folder",
            f"Delete folder '{folder_name}'?\n\nAssets in this folder will be moved to Root.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        if self._db_service.delete_folder(folder_id):
            self._load_folders()
            self._event_bus.folder_removed.emit(folder_id)
        else:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to delete folder '{folder_name}'."
            )

    # ==================== DRAG & DROP ====================

    def startDrag(self, supportedActions):
        """Store dragged folder item before drag starts"""
        selected = self.selectedItems()
        if selected:
            item = selected[0]
            data = item.data(0, Qt.ItemDataRole.UserRole)
            # Only allow dragging user folders (not system/type folders)
            if data and data.get('type') == 'user':
                self._dragged_folder_item = item
            else:
                self._dragged_folder_item = None
                # Prevent dragging system folders
                if data and data.get('type') == 'system':
                    return  # Don't start drag for system folders
        super().startDrag(supportedActions)

    def dragEnterEvent(self, event):
        """Accept asset drops and folder drops"""
        mime_data = event.mimeData()
        # Accept asset UUID drops
        if mime_data.hasFormat('application/x-asset-uuid'):
            event.acceptProposedAction()
        # Accept internal folder drags
        elif mime_data.hasFormat('application/x-qabstractitemmodeldatalist'):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """Highlight target folder during drag"""
        mime_data = event.mimeData()
        item = self.itemAt(event.position().toPoint())

        # Asset drops - on system or user folders (physical folders)
        if mime_data.hasFormat('application/x-asset-uuid'):
            if item:
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get('type') in ('system', 'user'):
                    self.setCurrentItem(item)
                    event.acceptProposedAction()
                    return
            event.ignore()
            return

        # Folder drops - on system or user folders
        if mime_data.hasFormat('application/x-qabstractitemmodeldatalist'):
            if item is None:
                event.ignore()  # Can't drop on empty space
                return
            data = item.data(0, Qt.ItemDataRole.UserRole)
            # Can drop user folders onto system or user folders
            if data and data.get('type') in ('system', 'user'):
                self.setCurrentItem(item)
                event.acceptProposedAction()
                return

        event.ignore()

    def dropEvent(self, event):
        """Handle asset drop or folder drop"""
        mime_data = event.mimeData()

        # Handle folder drops
        if mime_data.hasFormat('application/x-qabstractitemmodeldatalist'):
            self._handle_folder_drop(event)
            return

        # Handle asset drops
        if mime_data.hasFormat('application/x-asset-uuid'):
            self._handle_asset_drop(event)
            return

        event.ignore()

    def _handle_folder_drop(self, event):
        """Handle folder-to-folder drop (virtual folders - database only)"""
        if not self._dragged_folder_item:
            event.ignore()
            return

        source_data = self._dragged_folder_item.data(0, Qt.ItemDataRole.UserRole)
        if not source_data or source_data.get('type') != 'user':
            event.ignore()
            return

        source_id = source_data.get('folder_id')
        source_name = source_data.get('folder_name')

        if not source_id:
            event.ignore()
            self._dragged_folder_item = None
            return

        target_item = self.itemAt(event.position().toPoint())

        if target_item is None:
            event.ignore()
            self._dragged_folder_item = None
            return

        target_data = target_item.data(0, Qt.ItemDataRole.UserRole)

        # Can only drop on system (type) or user folders
        if not target_data or target_data.get('type') not in ('system', 'user'):
            event.ignore()
            self._dragged_folder_item = None
            return

        # Determine target parent ID
        if target_data.get('type') == 'system':
            # Dropping on a type folder - get or create the type root as parent
            asset_type = target_data.get('asset_type')
            target_id = self._get_or_create_type_root(asset_type)
            target_name = target_data.get('display_name', asset_type)
        else:
            # Dropping on a user folder
            target_id = target_data.get('folder_id')
            target_name = target_data.get('folder_name')

        if not target_id:
            event.ignore()
            self._dragged_folder_item = None
            return

        # Use the existing database move method
        if self._move_folder_to_folder(source_id, target_id, source_name, target_name):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

        self._dragged_folder_item = None

    def _move_folder_to_root(self, folder_id: int, folder_name: str) -> bool:
        """Move folder to root level"""
        root_id = self._db_service.get_root_folder_id()

        # Check if already at root
        folder = self._db_service.get_folder_by_id(folder_id)
        if folder and folder.get('parent_id') == root_id:
            return False  # Already at root

        if self._db_service.update_folder_parent(folder_id, root_id):
            QTimer.singleShot(0, lambda: self._reload_after_move(f"Moved '{folder_name}' to root"))
            return True
        return False

    def _move_folder_to_folder(self, source_id: int, target_id: int, source_name: str, target_name: str) -> bool:
        """Move folder into another folder"""
        # Validate: cannot move into self
        if source_id == target_id:
            QMessageBox.warning(self, "Invalid Move", "Cannot move folder into itself.")
            return False

        # Validate: cannot move into descendant (circular reference)
        if self._is_descendant(target_id, source_id):
            QMessageBox.warning(self, "Invalid Move", "Cannot move folder into its own subfolder.")
            return False

        if self._db_service.update_folder_parent(source_id, target_id):
            QTimer.singleShot(0, lambda: self._reload_after_move(f"Moved '{source_name}' into '{target_name}'"))
            return True

        QMessageBox.warning(self, "Error", "Failed to move folder.")
        return False

    def _is_descendant(self, folder_id: int, ancestor_id: int) -> bool:
        """Check if folder_id is a descendant of ancestor_id"""
        folder = self._db_service.get_folder_by_id(folder_id)
        if not folder:
            return False

        current_id = folder.get('parent_id')
        visited = set()

        while current_id:
            if current_id == ancestor_id:
                return True
            if current_id in visited:
                break  # Circular ref detected
            visited.add(current_id)

            parent = self._db_service.get_folder_by_id(current_id)
            if not parent:
                break
            current_id = parent.get('parent_id')

        return False

    def _reload_after_move(self, message: str):
        """Reload tree after folder move"""
        self._load_folders()
        self._event_bus.status_message.emit(message)

    def _handle_asset_drop(self, event):
        """Handle asset drop - move assets to virtual folder (database only)"""
        target_item = self.itemAt(event.position().toPoint())
        if not target_item:
            event.ignore()
            return

        data = target_item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get('type') not in ('system', 'user'):
            event.ignore()
            return

        # Get target folder info
        folder_name = data.get('folder_name') or data.get('display_name', 'folder')
        target_asset_type = data.get('asset_type')  # For filtering

        # Extract asset UUIDs
        try:
            uuid_data = bytes(event.mimeData().data('application/x-asset-uuid')).decode('utf-8')
            asset_uuids = [u.strip() for u in uuid_data.strip().split('\n') if u.strip()]
        except Exception:
            event.ignore()
            return

        if not asset_uuids:
            event.ignore()
            return

        # Virtual folder move - database only
        success_count = 0
        failed_assets = []

        for uuid in asset_uuids:
            asset = self._db_service.get_asset_by_uuid(uuid)
            if not asset:
                failed_assets.append(uuid)
                continue

            asset_type = asset.get('asset_type', 'mesh')

            # Check type compatibility
            if target_asset_type and target_asset_type != asset_type:
                failed_assets.append(uuid)
                continue

            # Get target folder_id
            if data.get('type') == 'system':
                # Moving to type folder root = remove from all folders
                target_folder_id = None
            else:
                # Moving to user folder
                target_folder_id = data.get('folder_id')

            # Virtual move - database only, no file operations
            success, msg = self._db_service.move_asset_to_folder(uuid, target_folder_id)
            if success:
                success_count += 1
            else:
                failed_assets.append(uuid)

        if success_count > 0:
            event.acceptProposedAction()
            self._event_bus.assets_moved.emit(asset_uuids, -1, success_count)
            self._event_bus.status_message.emit(f"Moved {success_count} asset(s) to '{folder_name}'")
        else:
            event.ignore()
            if failed_assets:
                QMessageBox.warning(
                    self,
                    "Move Failed",
                    f"Could not move assets. Check that assets match the folder type."
                )

    # ==================== PUBLIC METHODS ====================

    def refresh(self):
        """Refresh folder tree"""
        self._load_folders()

    def create_folder_dialog(self):
        """Show create folder dialog (called from toolbar)"""
        # Get selected folder as parent, or use root
        parent_id = self._db_service.get_root_folder_id()

        selected_items = self.selectedItems()
        if selected_items:
            data = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
            if data and data.get('type') == 'user':
                parent_id = data.get('folder_id')

        self._create_folder(parent_id)

    def get_selected_folder_id(self) -> int:
        """Get currently selected folder ID"""
        selected_items = self.selectedItems()
        if selected_items:
            data = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
            if data:
                return data.get('folder_id', Config.VIRTUAL_FOLDER_ALL)
        return Config.VIRTUAL_FOLDER_ALL


__all__ = ['FolderTree']
