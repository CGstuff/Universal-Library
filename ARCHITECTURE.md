# Architecture

This document describes the technical architecture of Universal Library for developers and contributors.

## Table of Contents

- [Tech Stack](#tech-stack)
- [Design Patterns](#design-patterns)
- [Directory Structure](#directory-structure)
- [Storage Layout](#storage-layout)
- [Database Schema](#database-schema)
- [Event System](#event-system)
- [Service Layer](#service-layer)
- [Blender Integration](#blender-integration)

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| UI Framework | PyQt6 | Cross-platform desktop GUI |
| Database | SQLite + WAL | Metadata storage, concurrent access |
| Asset Storage | Native .blend | Full Blender fidelity |
| Image Processing | Pillow, OpenCV | Thumbnails, screenshots |
| Build | PyInstaller | Portable executable packaging |

### Python Requirements

- Python 3.9+
- PyQt6 6.5+ (Qt6 bindings)
- Pillow 10.0+ (image processing)
- opencv-python 4.8+ (video/image capture)

---

## Design Patterns

### Model/View/Controller

Universal Library uses Qt's Model/View pattern:

```
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│     View       │◄───│     Model      │◄───│   Repository   │
│  (QListView)   │    │ (QAbstractList │    │ (SQLite)       │
│                │    │  Model)        │    │                │
└────────────────┘    └────────────────┘    └────────────────┘
        │                     │
        │   ┌─────────────────┘
        ▼   ▼
┌────────────────┐
│    Delegate    │
│ (QStyledItem   │
│  Delegate)     │
└────────────────┘
```

**Key classes:**
- `AssetListModel` — Qt model providing asset data
- `AssetFilterProxyModel` — Filtering and sorting
- `AssetCardDelegate` — Custom rendering for grid/list views

### Event Bus

Decoupled communication via central event bus:

```python
from universal_library.events import get_event_bus

bus = get_event_bus()

# Emit events
bus.emit_asset_selected(uuid)

# Subscribe to events
bus.asset_selected.connect(self.on_asset_selected)
```

**Event categories:**
- **Selection signals** — `asset_selected`, `folder_selected`
- **View state** — `view_mode_changed`, `card_size_changed`
- **Data changes** — `asset_added`, `asset_updated`, `asset_removed`
- **Requests** — `request_delete_asset`, `request_import_asset`

### Repository Pattern

Data access abstracted through repositories:

```python
# Direct database access is discouraged
# Use repositories instead:

from universal_library.services import AssetRepository

repo = AssetRepository()
asset = repo.get_by_uuid(uuid)
repo.update(asset)
```

**Repositories:**
- `AssetRepository` — CRUD for assets
- `FolderRepository` — Folder hierarchy
- `TagRepository` — Tag management
- `AssetFolderRepository` — Multi-folder assignments

### Service Layer

Business logic encapsulated in services:

```
┌─────────────────────────────────────────┐
│              DatabaseService            │
│  (Facade coordinating repositories)     │
├─────────────────────────────────────────┤
│  AssetRepository  │  FolderRepository   │
│  TagRepository    │  AssetFolderRepo    │
├─────────────────────────────────────────┤
│           BaseRepository                │
│      (Connection pooling, WAL)          │
└─────────────────────────────────────────┘
```

**Key services:**
- `DatabaseService` — Facade for all database operations
- `ThumbnailService` — Async thumbnail loading with caching
- `WatcherService` — File system monitoring
- `ColdStorageService` — Version archival
- `ReviewService` — Review workflow management

### Singleton Services

Services use singleton pattern with getter functions:

```python
from universal_library.services import get_database_service

db = get_database_service()
```

This ensures consistent state across the application.

---

## Directory Structure

```
universal_library/
├── __init__.py
├── main.py              # Application entry point
├── config.py            # Configuration and constants
│
├── core/                # Core abstractions
│   ├── base_service.py  # Service base class
│   ├── service_locator.py
│   ├── asset_scanner.py # Library scanning
│   └── entity/          # Entity behavior system
│
├── services/            # Business logic
│   ├── database_service.py    # Database facade
│   ├── schema_manager.py      # Schema migrations
│   ├── asset_repository.py    # Asset CRUD
│   ├── folder_repository.py   # Folder CRUD
│   ├── tag_repository.py      # Tag CRUD
│   ├── thumbnail_service.py   # Thumbnail management
│   ├── watcher_service.py     # File system watching
│   ├── cold_storage_service.py # Version archival
│   ├── control_authority.py   # Operation mode control
│   ├── user_service.py        # User/role management
│   ├── backup_service.py      # Database backups
│   └── review/                # Review subsystem
│       ├── review_service.py
│       └── data/              # Review data layer
│
├── models/              # Qt data models
│   ├── asset_list_model.py
│   └── asset_filter_proxy_model.py
│
├── views/               # Custom views and delegates
│   └── asset_card_delegate.py
│
├── widgets/             # UI components
│   ├── main_window.py
│   ├── header_toolbar.py
│   ├── status_bar.py
│   ├── metadata_panel/       # Right-side info panel
│   ├── dialogs/              # Modal dialogs
│   ├── settings/             # Settings tabs
│   ├── review/               # Review UI components
│   └── icons/                # SVG icon files
│
├── events/              # Event system
│   ├── event_bus.py
│   └── entity_events.py
│
├── themes/              # Theming system
│   ├── theme_manager.py
│   ├── dark_theme.py
│   └── light_theme.py
│
└── utils/               # Utilities
    ├── path_utils.py
    ├── image_utils.py
    └── logging_config.py

UL_blender_plugin/       # Blender addon
├── __init__.py          # Addon registration
├── operators/           # Blender operators
├── utils/               # Blender utilities
└── viewport/            # Viewport overlays
```

---

## Storage Layout

### Active Library

```
your-library/
├── library/                    # Active/latest versions
│   ├── meshes/
│   │   └── Sword/              # Asset family folder
│   │       └── Base/           # Variant folder
│   │           ├── Sword.v003.blend    # Current version
│   │           ├── Sword.v003.png      # Thumbnail
│   │           └── Sword.current.blend # Reference proxy
│   ├── materials/
│   ├── rigs/
│   ├── lights/
│   ├── cameras/
│   ├── collections/
│   ├── curves/
│   ├── grease_pencils/
│   └── scenes/
│
├── _archive/                   # Version history
│   └── meshes/
│       └── Sword/
│           └── Base/
│               ├── v001/
│               └── v002/
│
├── _retired/                   # Soft-deleted assets
│   └── meshes/
│       └── OldProp/
│
├── reviews/                    # Review screenshots
│   └── meshes/
│       └── Sword/
│           └── Base/
│               └── v003/
│                   ├── screenshot_001.png
│                   └── drawover_001.png
│
├── cache/                      # Generated content
│   └── thumbnails/
│
└── .meta/                      # Metadata (hidden)
    ├── database.db             # Main database
    ├── database.db-wal         # WAL file
    ├── database.db-shm         # Shared memory
    ├── reviews.db              # Review database
    └── logs/                   # Application logs
```

### File Naming Convention

```
{AssetName}.v{XXX}.{extension}
```

Examples:
- `Sword.v001.blend`
- `Sword.v001.png` (thumbnail)
- `Sword.current.blend` (reference proxy)

---

## Database Schema

### Main Database (`database.db`)

#### assets

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `uuid` | TEXT | Unique identifier |
| `name` | TEXT | Display name |
| `description` | TEXT | User notes |
| `folder_id` | INTEGER | Primary folder (FK) |
| `asset_type` | TEXT | mesh, material, rig, etc. |
| `blend_file_path` | TEXT | Path to .blend file |
| `thumbnail_path` | TEXT | Path to thumbnail |
| `file_size_mb` | REAL | File size in MB |
| `polygon_count` | INTEGER | Mesh statistics |
| `material_count` | INTEGER | Material count |
| `status` | TEXT | wip, review, approved, etc. |
| `version` | INTEGER | Version number |
| `version_label` | TEXT | v001, v002, etc. |
| `version_group_id` | TEXT | Groups versions together |
| `variant_name` | TEXT | Base, Gold, etc. |
| `is_latest` | INTEGER | 1 if current version |
| `is_favorite` | INTEGER | Favorited flag |
| `is_retired` | INTEGER | Soft-delete flag |
| `representation` | TEXT | model, lookdev, rig, final |
| `review_state` | TEXT | needs_review, approved, etc. |
| `created_date` | TIMESTAMP | Creation time |
| `modified_date` | TIMESTAMP | Last modification |

#### folders

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | TEXT | Folder name |
| `parent_id` | INTEGER | Parent folder (FK) |
| `path` | TEXT | Full path (e.g., "/Props/Weapons") |
| `description` | TEXT | Folder notes |
| `icon_name` | TEXT | Custom icon |
| `icon_color` | TEXT | Icon color hex |

#### tags

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | TEXT | Tag name |
| `color` | TEXT | Display color |
| `description` | TEXT | Tag description |

#### asset_tags

| Column | Type | Description |
|--------|------|-------------|
| `asset_id` | INTEGER | FK to assets |
| `tag_id` | INTEGER | FK to tags |

#### asset_folders

| Column | Type | Description |
|--------|------|-------------|
| `asset_uuid` | TEXT | FK to assets.uuid |
| `folder_id` | INTEGER | FK to folders |

#### app_settings

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT | Setting name |
| `value` | TEXT | Setting value |

### Review Database (`reviews.db`)

Separate database for review data to allow independent access:

#### review_cycles

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `version_group_id` | TEXT | Asset family |
| `cycle_type` | TEXT | modeling, texturing, etc. |
| `status` | TEXT | active, completed |
| `created_by` | TEXT | User who started |
| `created_date` | TIMESTAMP | Start time |

#### review_sessions

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `cycle_id` | INTEGER | FK to review_cycles |
| `asset_uuid` | TEXT | Specific version |
| `status` | TEXT | Session state |

#### review_notes

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `session_id` | INTEGER | FK to review_sessions |
| `author` | TEXT | Note author |
| `content` | TEXT | Note text |
| `status` | TEXT | open, addressed, approved |
| `screenshot_path` | TEXT | Attached image |

---

## Event System

### EventBus Signals

```python
class EventBus(QObject):
    # Selection
    asset_selected = pyqtSignal(str)           # uuid
    assets_selected = pyqtSignal(list)         # [uuids]
    folder_selected = pyqtSignal(int)          # folder_id

    # View state
    view_mode_changed = pyqtSignal(str)        # "grid" or "list"
    card_size_changed = pyqtSignal(int)        # pixels
    search_text_changed = pyqtSignal(str)      # query

    # Data changes
    assets_loaded = pyqtSignal(int)            # count
    asset_added = pyqtSignal(str)              # uuid
    asset_updated = pyqtSignal(str)            # uuid
    asset_removed = pyqtSignal(str)            # uuid

    # Batch operations
    assets_batch_added = pyqtSignal(list)      # [uuids]
    assets_batch_updated = pyqtSignal(list)    # [uuids]
    assets_batch_removed = pyqtSignal(list)    # [uuids]

    # Requests (actions to perform)
    request_toggle_favorite = pyqtSignal(str)  # uuid
    request_delete_asset = pyqtSignal(str)     # uuid
    request_import_asset = pyqtSignal(str)     # uuid
```

### Usage Pattern

```python
from universal_library.events import get_event_bus

class MyWidget(QWidget):
    def __init__(self):
        super().__init__()
        bus = get_event_bus()
        bus.asset_selected.connect(self._on_asset_selected)

    def _on_asset_selected(self, uuid: str):
        if uuid:
            # Handle selection
            pass
```

---

## Service Layer

### DatabaseService

The main facade for database operations:

```python
from universal_library.services import get_database_service

db = get_database_service()

# Asset operations
asset = db.get_asset_by_uuid(uuid)
assets = db.get_assets_by_folder(folder_id)
db.update_asset(uuid, {'status': 'approved'})

# Folder operations
folders = db.get_all_folders()
db.create_folder(name, parent_id)

# Settings
mode = db.get_app_setting('operation_mode', 'standalone')
```

### ControlAuthority

Manages operation mode:

```python
from universal_library.services import get_control_authority

auth = get_control_authority()

if auth.can_edit_status():
    # In standalone mode, can change status
    pass

if auth.can_delete():
    # Only in standalone mode
    pass
else:
    # Studio/Pipeline mode - retire instead
    pass
```

### ThumbnailService

Async thumbnail loading with caching:

```python
from universal_library.services import ThumbnailService

service = ThumbnailService()
service.request_thumbnail(uuid, callback=self._on_thumbnail_loaded)
```

---

## Blender Integration

### IPC Protocol

Communication via file-based IPC:

```
{user_data}/blender_ipc/
├── command.json    # UL writes commands here
└── response.json   # Addon writes responses here
```

**Command format:**
```json
{
    "action": "import",
    "asset_uuid": "abc-123",
    "file_path": "C:/library/meshes/Sword/Base/Sword.v003.blend",
    "import_mode": "LINK"
}
```

**Response format:**
```json
{
    "success": true,
    "message": "Imported successfully",
    "imported_objects": ["Sword"]
}
```

### Addon Structure

```
UL_blender_plugin/
├── __init__.py              # bl_info, register/unregister
├── operators/
│   ├── export_presets.py    # Export to library
│   ├── material_preview.py  # Material sphere render
│   └── viewport_overlay.py  # Asset info overlay
├── utils/
│   ├── blender_helpers.py   # Blender API helpers
│   ├── thumbnail_generator.py
│   └── naming_utils.py
└── viewport/
    └── asset_overlay.py     # Viewport drawing
```

### Export Workflow

1. User selects objects in Blender
2. Invokes export operator (Ctrl+Shift+E)
3. Addon collects data (geometry, materials, thumbnail)
4. Writes .blend file to library path
5. Registers asset via IPC or direct database access

### Import Workflow

1. User double-clicks asset in Universal Library
2. UL writes import command to IPC
3. Blender addon detects command
4. Addon imports asset (link/append/instance)
5. Writes response confirming import

---

## Performance Considerations

### Virtual Scrolling

The asset grid uses virtual scrolling—only visible items are rendered:

```python
class AssetListModel(QAbstractListModel):
    def rowCount(self, parent=None):
        return len(self._assets)  # Can be thousands

    def data(self, index, role):
        # Only called for visible rows
        pass
```

### Thumbnail Caching

Multi-level thumbnail cache:

1. **Memory cache** — QPixmapCache (512MB default)
2. **Disk cache** — `cache/thumbnails/` folder
3. **Source** — Original thumbnail files

### Database WAL Mode

SQLite Write-Ahead Logging enables:
- Concurrent reads during writes
- Better crash recovery
- Improved performance for multi-user access

---

## Extending Universal Library

### Adding Asset Types

1. Add to `Config.ASSET_TYPES` in `config.py`
2. Add folder mapping in `Config.ASSET_TYPE_FOLDERS`
3. Add color in `Config.ASSET_TYPE_COLORS`
4. Update Blender addon export options

### Adding Review Cycle Types

1. Add to `REVIEW_CYCLE_TYPES` in `config.py`
2. No database migration needed (cycle type stored as string)

### Creating Custom Widgets

```python
from universal_library.widgets.core import BaseWidget

class MyWidget(BaseWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        # Build UI
        pass

    def _connect_signals(self):
        bus = get_event_bus()
        bus.asset_selected.connect(self._on_asset_selected)
```

---

*For user documentation, see [GETTING_STARTED.md](GETTING_STARTED.md) and [STUDIO_GUIDE.md](STUDIO_GUIDE.md).*
