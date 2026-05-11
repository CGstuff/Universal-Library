# Changelog

All notable changes to Universal Library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Asset dependency tracking
- Batch export from Blender

---

## [1.2.0] - 2026-05-11

### Added

**3D Asset Preview**
- In-app OpenGL 4.6 viewport for previewing mesh and rig assets, with orbit camera, grid, directional lighting
- `ThumbnailPanel` now has a 2D/3D toggle plus an "enlarge" button on the asset metadata panel
- `EnlargedViewerDialog` — larger, resizable, non-modal viewer with its own toolbar
- Diffuse texture rendering (decoded via `QImage`, supports PNG / JPEG / WEBP including the `EXT_texture_webp` glTF extension)
- Multi-object scene graph traversal — node transforms preserved so multi-mesh assets render at authored positions
- Skinned mesh rendering with linear blend skinning, up to 64 joints per rig
- Animation playback timeline: action picker, scrubber, play/pause, loop toggle
- Frame counter with frames-vs-seconds display toggle
- Playback FPS picker (changes playback rate; frame count stays constant)
- Playback speed combo (0.25× – 4×)
- Light direction popup (azimuth + elevation sliders, persisted)
- Background color picker in Settings → Appearance (persisted, applies live to every open viewport)

**Version Diff in Lineage**
- Per-version diff engine (`services/version_diff.py`) for poly count, materials, bones, vertex groups, textures, dimensions, etc.
- Persistent diff section in the version history preview panel with selectable baseline
- Optional inline diff rows under each version in the lineage tree, colored by change type
- Per-asset-type field registry — add new fields without touching either surface
- Pre-export warning in Blender for accidental partial re-exports (catches the "forgot to select all parts" case)

**Glb Compression Pipeline**
- WEBP texture export in place of preserved-source-format default (~5–15× smaller per texture)
- Texture downscale to 1024² max for preview (additional ~4–16× win on 4K+ assets)
- Draco mesh compression with `DracoPy` decoder in the in-app loader (~5–10× geometry win)
- Combined effect: a typical 55 MB rig export now ships as ~1.3 MB

**Blender Export — Animation Workflow**
- Custom action picker dialog in the Blender export operator — pick exactly which animations belong to a rig
- New `gltf_action_filter` user extension: bypasses Blender's "active action + NLA only" limitation for the picked set, without touching the user's NLA
- Rig export now ships armature + bound meshes + picked animations (replaces the previous static rest-pose-only export)
- Saved `.blend` file in the library preserves picked actions explicitly via `libraries.write` data blocks
- Adaptive hook supports both Blender 3.x / 4.2 (`GatherActionHookParameters`) and 4.4+ (`ActionsData`) param shapes

### Changed
- Blender import (Edit / Link) now pulls all actions from the library `.blend` and marks them with `use_fake_user`, so they survive the user's working-file saves
- `ThumbnailPanel` viewport is now constructed synchronously before main window show — GL context initializes during the initial paint pass, eliminating the mid-session flicker on first 3D click

### Removed
- Review system: review cycles, review notes, drawover canvas, screenshot attachments, user service, asset audit log
- Studio / Pipeline mode user-management features
- Reviewer role permissions and review state tracking

### Fixed
- `AssetRepository.delete()` no longer leaves SQLite foreign keys disabled when an exception occurs mid-delete
- Removed dead duplicate `add()` method in `AssetRepository`


---

## [1.1.0] - 2026-02-04

### Changed

**Virtual Folders**
- Replaced physical folder system with virtual folders
- Folders are now database-only organizational containers
- Moving assets between folders no longer moves files on disk
- Ensures linked/instanced assets never have broken paths
- Drag-and-drop folder nesting now uses database operations

**Thumbnail Versioning**
- Thumbnails now use versioned filenames: `thumbnail.v001.png`, `thumbnail.v002.png`
- Added `thumbnail.current.png` as stable reference for latest version (same pattern as `.current.blend`)
- Each version retains its own thumbnail when archived
- Version picker shows correct thumbnail per version
- Auto-refresh works via mtime watching on `thumbnail.current.png`

### Fixed
- Fixed folder memberships not persisting when creating new versions
- Fixed assets disappearing from folder view after refresh (SQLite WAL stale reads)
- Fixed `refresh_asset()` wiping folder/tag enrichment data

---

## [1.0.0] - 2025-01-31

### Added

**Core Features**
- Asset management for meshes, materials, rigs, lights, cameras, collections, curves, grease pencils, and scenes
- Full Blend fidelity — native .blend storage preserves everything Blender can do
- Version control with immutable version history
- Variant system for asset variations (color, damage states, etc.)
- Multi-folder assignment for flexible organization
- Tag-based categorization
- Favorites and recent assets

**User Interface**
- Grid, list, and tree view modes
- Customizable card sizes (100-400px)
- Dark and light themes
- DPI-aware scaling
- Virtual scrolling for large libraries
- Async thumbnail loading with caching
- Metadata panel with import options
- Folder tree with virtual folders (All, Favorites, Recent, etc.)

**Review System**
- Review cycles (Modeling, Texturing, Rigging, Lookdev, etc.)
- Three-state note workflow (Open → Addressed → Approved)
- Screenshot attachments with draw-over annotations
- Role-based permissions (Artist, Lead, Supervisor)
- Review state tracking per asset

**Operation Modes**
- Standalone mode for solo artists
- Studio mode for multi-user environments
- Pipeline mode for Pipeline Control integration
- Retire/restore system (Studio/Pipeline modes)
- Audit trail for collaborative work

**Blender Integration**
- One-click export from Blender
- Link, append, and instance import modes
- Current reference proxy files for auto-updating links
- Automatic thumbnail generation
- Material preservation (Blender nodes)

**Storage**
- Organized folder structure by asset type
- Cold storage archive for version history
- Retired assets folder for soft deletes
- SQLite with WAL mode for concurrent access
- Separate reviews database

**Settings**
- Library path configuration
- Appearance customization
- Blender executable configuration
- Backup and maintenance tools

### Technical

- PyQt6-based desktop application
- Model/View architecture with virtual scrolling
- Event bus for decoupled communication
- Repository pattern for data access
- Service layer for business logic
- Schema versioning and migrations

---

## Version History Format

### Types of Changes

- **Added** — New features
- **Changed** — Changes to existing functionality
- **Deprecated** — Features to be removed in future versions
- **Removed** — Removed features
- **Fixed** — Bug fixes
- **Security** — Security-related changes

---

[Unreleased]: https://github.com/CGstuff/Universal-Library/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/CGstuff/Universal-Library/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/CGstuff/Universal-Library/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/CGstuff/Universal-Library/releases/tag/v1.0.0
