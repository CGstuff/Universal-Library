# Studio Guide

This guide covers Universal Library features designed for multi-user environments, review workflows, and pipeline integration.

## Table of Contents

- [Operation Modes](#operation-modes)
- [Review System](#review-system)
- [Representation Workflow](#representation-workflow)
- [Version and Variant Management](#version-and-variant-management)
- [Retire and Restore](#retire-and-restore)
- [Multi-User Deployment](#multi-user-deployment)
- [Pipeline Integration](#pipeline-integration)

---

## Operation Modes

Universal Library supports three operation modes to fit different workflows:

### Standalone Mode

**Best for:** Solo artists, personal libraries

| Feature | Behavior |
|---------|----------|
| Status editing | Full control |
| Delete | Permanent delete |
| Reviews | Available but optional |
| Audit trail | Minimal |

This is the default mode. You have complete control over your assets, including permanent deletion.

### Studio Mode

**Best for:** Small teams, shared libraries without external pipeline tools

| Feature | Behavior |
|---------|----------|
| Status editing | Full control |
| Delete | Retire instead of delete |
| Reviews | Full review workflow |
| Audit trail | Full audit logging |

Studio mode enables collaborative features while keeping Universal Library as the authority for asset status.

**Key differences from Standalone:**
- Assets are **retired** instead of deleted (recoverable)
- Full review workflow with notes, screenshots, and approvals
- Audit trail tracks who changed what and when

### Pipeline Mode

**Best for:** Studios with Pipeline Control or external tools managing asset status

| Feature | Behavior |
|---------|----------|
| Status editing | Read-only (controlled externally) |
| Delete | Retire instead of delete |
| Reviews | Full review workflow |
| Audit trail | Full audit logging |

In Pipeline mode, the status field (WIP, Review, Approved, etc.) is controlled by an external system like Pipeline Control. Universal Library shows the status but doesn't allow changes.

### Changing Operation Mode

1. Go to **Settings → Pipeline**
2. Select your operation mode
3. Click **Apply**

The setting is stored in the shared database, so all users see the same mode.

---

## Review System

The review system provides structured feedback for assets in production.

### Review Cycles

Review cycles group feedback for specific phases of asset development:

| Cycle | Purpose | Example |
|-------|---------|---------|
| Modeling | Geometry review | Topology, silhouette, proportions |
| Texturing | Surface detail review | UV layout, texture resolution, materials |
| Rigging | Deformation review | Joint placement, weight painting, controls |
| Lookdev | Shading review | Material setup, lighting response |
| Animation | Motion review | (For animated assets) |
| General | Catch-all | Any feedback not fitting other categories |

### Starting a Review

1. Select an asset
2. Click **Request Review** in the metadata panel
3. Select the review cycle type (Modeling, Texturing, etc.)
4. The asset enters "Needs Review" state

### Adding Notes

Reviewers can add notes with optional screenshots:

1. Open the review dialog (**R** or right-click → **Review**)
2. Click **Add Note**
3. Type your feedback
4. Optionally attach a screenshot with draw-over annotations

### Note States

Notes follow a three-state workflow:

```
Open → Addressed → Approved
  ↑_________|        |
            └────────┘
```

| State | Meaning | Who Changes It |
|-------|---------|----------------|
| Open | Note created, awaiting artist | Reviewer creates |
| Addressed | Artist fixed the issue | Artist marks |
| Approved | Reviewer confirms fix | Reviewer marks |

### Review States

The overall asset review state reflects the note status:

| State | Meaning |
|-------|---------|
| Needs Review | Waiting for reviewer feedback |
| In Review | Reviewer has added notes |
| In Progress | Artist is working on fixes |
| Approved | All notes approved |
| Final | Review cycle complete |

### Screenshots and Draw-Overs

Attach visual feedback to notes:

1. In the review dialog, click **Add Screenshot**
2. Choose **Capture Viewport** or **Browse...**
3. Use the draw-over tools to annotate:
   - **Pen** — Freehand drawing
   - **Arrow** — Point to specific areas
   - **Rectangle** — Highlight regions
   - **Text** — Add labels
4. Choose a color (red for problems, green for approved areas)

### Role-Based Permissions

Review actions are controlled by user role:

| Action | Artist | Lead/Supervisor |
|--------|--------|-----------------|
| Request review | Yes | Yes |
| Add notes | Yes | Yes |
| Mark addressed | Yes | Yes |
| Approve notes | No | Yes |
| Mark final | No | Yes |

Set your role in **Settings → User**.

---

## Representation Workflow

Representations track an asset's journey through the pipeline:

```
Model → Lookdev → Rig → Final
```

### Representation Types

| Type | Description | Typical Owner |
|------|-------------|---------------|
| Model | Base geometry, UVs | Modeler |
| Lookdev | Materials, textures | Texture artist |
| Rig | Skeleton, controls | Rigger |
| Final | Production-ready | Lead |

### Setting Representations

1. Select an asset
2. In the metadata panel, click the **Representation** dropdown
3. Select the appropriate type

### Authority Boundaries

Each representation type implies ownership:

- **Model** changes should be approved by modeling lead
- **Lookdev** changes should be approved by texturing lead
- **Rig** changes should be approved by rigging lead

Universal Library tracks this but doesn't enforce it—use your team's approval process.

### Proxy vs Render Designations

For assets with multiple detail levels:

| Designation | Use Case |
|-------------|----------|
| Proxy | Viewport, layout, animation |
| Render | Final render, high detail |

Set via **right-click → Set Designation**.

---

## Version and Variant Management

### Version Lineage

Each asset maintains a version history:

```
Sword v001 → v002 → v003 (current)
```

**Version rules:**
- Versions are **immutable** — once published, they don't change
- New exports create new versions automatically
- Old versions move to cold storage (`_archive/`)

### Creating Versions

Simply export the asset again with the same name and variant:

1. Make changes in Blender
2. Export with **Ctrl+Shift+E**
3. Keep the same name and variant
4. A new version (v002, v003, etc.) is created

### Restoring Old Versions

1. Select the asset
2. Open **Version History** (**V** or metadata panel)
3. Select the version to restore
4. Click **Restore as Current**

This creates a new version that matches the old one—it doesn't overwrite.

### Variants

Variants are parallel versions of the same asset:

```
Armor/
├── Base/      # Default variant
├── Iron/      # Color variant
├── Gold/      # Color variant
└── Diamond/   # Color variant
```

**When to use variants:**
- Color/material variations
- Damage states (pristine, worn, broken)
- Seasonal versions (summer, winter)
- LOD versions (high, medium, low detail)

### Creating Variants

1. In Blender, prepare the variant
2. Export with **Ctrl+Shift+E**
3. Keep the same asset name
4. Change the **Variant** field (e.g., "Gold" instead of "Base")

### Cold Storage Archive

Old versions are archived to keep the library fast:

```
_archive/
└── meshes/
    └── Sword/
        └── Base/
            ├── v001/
            ├── v002/
            └── v003/
```

Archived versions remain accessible through Version History.

---

## Retire and Restore

In Studio and Pipeline modes, delete is replaced with **retire**.

### How Retire Works

1. User clicks **Delete** (or right-click → **Retire**)
2. Asset is moved to `_retired/` folder
3. Database marks asset as retired
4. Asset no longer appears in normal views

**Benefits:**
- Recoverable (unlike permanent delete)
- Audit trail preserved
- Linked scenes can still find the files

### Viewing Retired Assets

1. In the folder panel, enable **Show Retired**
2. Or use the filter dropdown → **Retired**

Retired assets appear with a visual indicator (strikethrough or dimmed).

### Restoring Retired Assets

1. Find the retired asset
2. Right-click → **Restore**
3. Asset returns to its original location

### Audit Trail

In Studio/Pipeline modes, all actions are logged:

```
2024-01-15 14:32:01 | john.doe | RETIRED | Sword/Base
2024-01-15 15:10:22 | jane.smith | RESTORED | Sword/Base
```

View the audit log in **Settings → Maintenance → Audit Log**.

---

## Multi-User Deployment

### Network Storage Setup

For teams, place the library on a shared network location:

```
\\server\assets\universal_library\
├── library/
├── _archive/
├── _retired/
├── reviews/
├── cache/          # Can be local per-user
└── .meta/
    ├── database.db
    └── reviews.db
```

### Database Configuration

Universal Library uses SQLite with WAL (Write-Ahead Logging) mode for concurrent access:

- **WAL mode** — Enabled by default, allows simultaneous readers and one writer
- **Timeout** — 30-second timeout for lock acquisition

**Recommendations:**
- Keep the database on the network share (not local)
- Ensure all users have read/write access
- For large teams (10+), consider periodic database vacuuming

### Local Cache

Thumbnails can be cached locally for performance:

1. Go to **Settings → Storage**
2. Enable **Local Thumbnail Cache**
3. Set cache location (e.g., `C:\Users\you\AppData\Local\UniversalLibrary\cache`)

### Concurrent Access

**What works:**
- Multiple users browsing simultaneously
- Different users editing different assets
- Reading while another user writes

**What to avoid:**
- Two users editing the same asset simultaneously (last write wins)
- Deleting while another user is viewing

Universal Library doesn't lock assets—coordinate with your team for active edits.

---

## Pipeline Integration

### Pipeline Control

Universal Library integrates with [Pipeline Control](https://github.com/CGstuff/Pipeline-Control) for centralized status management.

**Setup:**
1. Set operation mode to **Pipeline** in Universal Library
2. Configure Pipeline Control to read from Universal Library's database
3. Status changes flow from Pipeline Control → Universal Library (read-only)

### Database Schema

External tools can read the shared database:

**Location:** `{library_path}/.meta/database.db`

**Key tables:**
| Table | Purpose |
|-------|---------|
| `assets` | Asset metadata, status, paths |
| `folders` | Folder hierarchy |
| `tags` | Tag definitions |
| `asset_folders` | Asset-to-folder mapping |
| `app_settings` | Configuration including operation_mode |

**Status field values:**
```python
STATUSES = ['none', 'wip', 'review', 'approved', 'deprecated', 'archived']
```

### IPC with Blender

The Blender addon communicates via file-based IPC:

1. Universal Library writes `command.json` with import/export instructions
2. Blender addon monitors for changes
3. Addon executes command and writes `response.json`

**Command location:** `{user_data}/blender_ipc/`

### Extending Universal Library

Universal Library uses an event bus for loose coupling:

```python
from universal_library.events import EventBus

# Subscribe to asset events
def on_asset_created(asset_id: str, name: str):
    print(f"New asset: {name}")

EventBus.subscribe('asset_created', on_asset_created)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for implementation details.

---

## Configuration Reference

### Operation Mode Settings

| Setting | Standalone | Studio | Pipeline |
|---------|------------|--------|----------|
| Status editing | Yes | Yes | No (read-only) |
| Permanent delete | Yes | No | No |
| Retire/Restore | No | Yes | Yes |
| Audit logging | Basic | Full | Full |
| Review workflow | Optional | Full | Full |

### Database Settings

| Key | Default | Description |
|-----|---------|-------------|
| `operation_mode` | `standalone` | Current operation mode |
| `journal_mode` | `wal` | SQLite journal mode |
| `foreign_keys` | `on` | Enforce referential integrity |

### User Roles

| Role | Permissions |
|------|-------------|
| `artist` | Create, edit own, request review |
| `lead` | All artist permissions + approve reviews |
| `supervisor` | All lead permissions + change operation mode |
| `admin` | Full access including maintenance |

---

*For technical implementation details, see [ARCHITECTURE.md](ARCHITECTURE.md).*
