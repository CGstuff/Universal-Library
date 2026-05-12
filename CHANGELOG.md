# Changelog

All notable changes to Universal Library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Asset dependency tracking
- Batch export from Blender

---

## [1.2.1] - 2026-05-13

Post-`1.2.0` work covering everything since the `1.2.0` tag: texture portability, four new addon-side workflow features (header launcher, scale reference, attribution metadata, collection preservation), a guided bug-hunt across the new 3D viewport / Blender exporter / import path, plus a major refactor that kills the proxy-swap crash.

### Added

**Texture Portability**
- Textures referenced by exported materials are temporarily packed into the library `.blend` before save, then unpacked from the user's working file after — the saved asset is self-contained while the user's working file stays untouched
- After Blender's `libraries.load` (Edit / Link import), all imported textures are packed locally. Avoids Blender's silent image-name dedup that would otherwise leave imported materials pointing at the user's local external paths, breaking on other machines
- Net result: an asset exported on one PC opens correctly on any other PC, with no source-file shipping required

**Always-Visible UL Header Button **
- Compact split button in Blender's 3D View header (location configurable — topbar / status bar / hidden also supported)
- Main click launches the desktop app via `ual.browse_library`; dropdown arrow opens a quick-action menu (Open Desktop App / Export Selected / Export Collection / Settings)
- Sits inline with View / Select / Add / Object via `VIEW3D_MT_editor_menus`, so it lives between the menus and the Global/Local dropdown (AnimToolBox-style spot)
- Persisted via QSettings; relocates live when the location pref changes (no addon reload)

**Scale Reference Silhouette **
- Toggleable 1.8 m human silhouette drawn in the Blender 3D viewport via `SpaceView3D.draw_handler` — no scene datablocks, no outliner clutter
- Bbox-aware placement: stands to the right of the active object's world bbox with proportional breathing room; feet planted on world Z = 0 so flying assets don't make the reference float
- Rig-aware: when an armature is the active object, the bbox unions the armature + every mesh bound to it (Armature modifier or parenting) — same resolver the rig export uses, so the on-screen check matches what'll actually be saved
- Configurable height + lockable position (silhouette pins in place even as selection changes; unlock resumes auto-follow)
- Mirrored in the desktop app's 3D preview viewport: textured-quad billboard in `AssetViewport`, billboarded against camera-right + world Z so it stays upright on orbit
- Single shared PNG asset between Blender addon and app
- Auto-reposition on active-object change via `msgbus.subscribe_rna`; toggle visible in the N-panel ("Scale Reference" sub-panel of "Asset Library") and the `EnlargedViewerDialog` toolbar in the app

**Attribution Metadata **
- Three first-class fields on every asset: `license`, `copyright`, `author`. Two new DB columns (`author` was already present); schema migration bumps version 17 → 18
- Single source of truth in **Blender addon preferences** (Preferences → Universal Library → Attribution Defaults):
  - License dropdown with 7 standard codes (CC0, CC-BY, CC-BY-SA, CC-BY-NC, MIT, GPL-3.0, Proprietary) + Custom text override
  - Copyright + Author free-text fields
  - Mirrored to `attribution_defaults.json` in AppData for cross-process inspection
- Per-export override in the Blender export dialog: default-OFF "Override" checkbox; grayed-out inheritance view when off, editable dropdown + line edits when on. Overrides apply to this export only and never modify the defaults
- App metadata panel: **read-only** display with hint *"Set at export. Re-export from Blender to change."* — attribution is immutable by design (mutable attribution is theater, not provenance metadata)

**Mesh Export — Collection Preservation**
- Optional `preserve_collections` checkbox in the export dialog (mesh asset type only; rigs always preserve collections for bone widgets)
- When checked, the same collection-saving loop that runs for rigs also runs for meshes, so kitbash sets and multi-folder organizations survive an INSTANCE-mode re-import

**Rig Export — Armature-Collection Warning**
- Soft warning in the export dialog when the armature is in the Scene Collection root while at least one bound mesh is in a sub-collection
- Detected via `users_collection` comparison against `scene.collection` (a prior naive truthy check missed this — `users_collection` always contains at least the scene root)
- Plain-language explanation of why this breaks INSTANCE imports plus how to fix (move armature into a sub-collection)

### Changed
- **Representation-swap module rewritten** to carry filepath strings everywhere instead of live `bpy.types.Library` references. Library refs are now resolved at the moment of use via `_resolve_lib_by_filepath()`. Every helper that touched `lib.filepath` / `lib.reload()` was rewritten in this style; `find_ual_libraries` / `swap_to_representation` / `restore_to_original` / `get_swap_info` / `get_libraries_for_objects` / `_build_library_uuid_map` all updated
- Addon now runs an orphan-image sweep on register and on every `.blend` load, cleaning up `_UL_PREVIEW_*` temp images left behind by crashed / aborted exports
- `export_to_library.py` logging migrated from raw `print("[UL] ...")` to a module-level `logger` with `debug/info/warning/exception` levels — the default console is now quiet during exports, full detail still available with debug logging enabled
- glTF addon's Python-level info prints (e.g. "Draco mesh compression is available") suppressed during the `bpy.ops.export_scene.gltf` call via Python-level `redirect_stdout`/`redirect_stderr`
- `build.bat` post-build addon-version restore replaced — instead of rewriting `bl_info` to a hardcoded `(1, 0, 0)`, the build now runs `git checkout` to revert `UL_blender_plugin/__init__.py` to its HEAD state. `version.txt` is no longer tracked (gitignored, build-time output)

### Fixed
- **`ReferenceError: StructRNA of type Library has been removed`** crash when swapping to a proxy / render / nothing representation. Root cause: holding `bpy.types.Library` refs across operations that can invalidate them (depsgraph eval, indirect-lib purge, `lib.reload()` itself). Fixed by the representation-swap rewrite above; missing libraries now skip with a warning instead of crashing
- `EnlargedViewerDialog` now uses `Qt.WA_DeleteOnClose` and the parent `MetadataPanel` clears its reference on the dialog's `destroyed` signal. Previously every close-X-then-reopen-different-asset leaked the entire viewer (including its GL context)
- Skinned mesh bounding-box used the wrong axis swap (`(x, z, -y)` instead of the matrix's actual `(x, -z, y)`), causing the auto-frame camera to look at a mirror-of-Z point. Tall standing rigs were framed with the head offset toward the top of the viewport
- `AssetRepository.delete()` — revised. The previous "fix" wrapped the delete in `PRAGMA foreign_keys = OFF/ON`, but SQLite ignores that pragma inside an active transaction (it's a documented no-op). The actual mechanism that makes the delete work is the explicit child-first ordering (`asset_tags` → `asset_folders` → `assets`). Removed the misleading pragma calls; kept the working order with a comment so the next reader doesn't redo the investigation
- Importers (`import_helpers.py`) now log full tracebacks via `logger.exception(...)` instead of silently returning `False` — previously every import-time failure was invisible to logs and untraceable in field reports
- `requirements.txt` now lists `numpy`, `PyOpenGL`, and `DracoPy` (previously unstated dependencies — fresh installs would silently fail to render 3D)

### Documented (Known Limitations)
- C-level Draco encoder still prints to stdout during glTF export — Python-level suppression catches the addon's own info lines but not the bundled C library's status output. Cosmetic only; doesn't affect the saved `.glb`
- glTF loader: `bufferView.byteStride` is not honored — external glTFs that interleave attributes (three.js, game engines, Khronos samples) load with corrupted vertex data. Production Blender exports verified safe (no interleaved buffers). Fix path documented inline (`np.lib.stride_tricks.as_strided`)
- glTF loader: `accessor.normalized` is not honored — affects glTFs that store quantized normals as `int8/uint16` with `normalized: true`. Production exports verified safe (0 normalized accessors found across all library `.glb` files)
- glTF loader: `accessor.sparse` is not honored — used only for shape-key animations, which are an explicit non-goal for 1.2
- Animation `_sample_channel` doesn't honor CUBICSPLINE's 3-slot-per-keyframe packing at the clamp / single-keyframe paths — verified Blender exports use STEP / LINEAR only (0 CUBICSPLINE samplers across 60 samplers in production)


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

[Unreleased]: https://github.com/CGstuff/Universal-Library/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/CGstuff/Universal-Library/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/CGstuff/Universal-Library/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/CGstuff/Universal-Library/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/CGstuff/Universal-Library/releases/tag/v1.0.0
