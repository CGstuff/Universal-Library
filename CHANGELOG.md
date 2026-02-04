# Changelog

All notable changes to Universal Library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Asset dependency tracking
- Batch export from Blender

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

[Unreleased]: https://github.com/CGstuff/Universal-Library/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/CGstuff/Universal-Library/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/CGstuff/Universal-Library/releases/tag/v1.0.0
