<p align="center">
  <img src="assets/Icon.png" alt="Universal Library" width="128" height="128">
</p>

<h1 align="center">Universal Library</h1>

<p align="center">
  <strong>A professional 3D asset manager built for Blender</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue.svg" alt="GPL-3.0 License"></a>
  <img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/PyQt6-6.5+-green.svg" alt="PyQt6">
  <img src="https://img.shields.io/badge/Blender-4.5+-orange.svg" alt="Blender 4.5+">
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="GETTING_STARTED.md">Getting Started</a> •
  <a href="STUDIO_GUIDE.md">Studio Guide</a> •
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

## What is Universal Library?

A standalone desktop app for organizing and managing 3D assets. Store meshes, materials, rigs, and other Blender assets in a searchable library with version history, variants, and review workflows. Works for solo artists as a personal asset browser or scales to multi-user studio setups.

## Features

- **High Performance** — Handles thousands of assets with virtual scrolling and async thumbnail loading
- **Full Blend Fidelity** — Native .blend storage preserves everything Blender can do
- **Version History** — Immutable versions with cold storage archive for old versions
- **Variants** — Multiple variants per asset (armor sets, color variations, seasonal props)
- **Representations** — Model → Lookdev → Rig workflow with proxy/render designations
- **Review System** — Notes, screenshots, draw-over annotations, and multi-stage review cycles
- **Smart Organization** — Folders, tags, favorites, search, and multi-folder assignment
- **Operation Modes** — Standalone (solo), Studio (multi-user), Pipeline (external control)
- **Blender Integration** — One-click capture and import via bundled addon
- **Retire System** — Soft-delete with restore capability (Studio/Pipeline mode)
- **Metadata Panel** — Technical info, tags, folders, status, and import options
- **Multiple Views** — Grid, list, and tree views with customizable card sizes
- **Current References** — Auto-updating proxy files for consistent scene linking
- **Modern UI** — Dark/light themes, DPI-aware scaling, responsive layout
- **Asset Types** — Mesh, material, rig, light, camera, collection, curve, grease pencil, scene

## Installation

### Option 1: Download Release (Recommended)

1. Download the latest release from [Releases](https://github.com/CGstuff/Universal-Library/releases)
2. Extract to your preferred location
3. Run `UniversalLibrary.exe`
4. On first launch, set your library storage path

The portable release includes everything needed—no Python installation required.

### Option 2: Run from Source

```bash
# Clone the repository
git clone https://github.com/CGstuff/Universal-Library.git
cd Universal-Library

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python run.py
```

**Requirements:**
- Python 3.9 or higher
- PyQt6 6.5+

### Blender Addon

The Blender addon is bundled with Universal Library. To install:

1. Open Universal Library
2. Go to **Settings → Blender Integration**
3. Click **Install Addon**
4. Select your Blender executable

Or manually copy `UL_blender_plugin/` to your Blender addons folder.

## Building Portable Version

To build a standalone executable:

```bash
# Install PyInstaller
pip install pyinstaller

# Build using the spec file
pyinstaller build_spec.spec

# Output will be in dist/UniversalLibrary/
```

The build creates a portable folder that can be distributed without requiring Python.

## Architecture

Universal Library uses a layered architecture:

```
┌─────────────────────────────────────────────┐
│                  PyQt6 UI                   │
│         (Widgets, Views, Dialogs)           │
├─────────────────────────────────────────────┤
│               Service Layer                 │
│    (DatabaseService, ThumbnailService)      │
├─────────────────────────────────────────────┤
│             Repository Layer                │
│  (AssetRepository, FolderRepository, etc.)  │
├─────────────────────────────────────────────┤
│          SQLite + File Storage              │
│       (WAL mode, file-based assets)         │
└─────────────────────────────────────────────┘
```

For detailed technical documentation, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Storage Structure

```
your-library/
├── library/           # Active/latest versions
│   ├── meshes/
│   ├── materials/
│   ├── rigs/
│   └── ...
├── _archive/          # Version history (cold storage)
├── _retired/          # Soft-deleted assets
├── reviews/           # Screenshots and draw-overs
├── cache/             # Thumbnails and previews
└── .meta/             # Databases and config
    ├── database.db    # Main asset metadata
    └── reviews.db     # Review notes and sessions
```

## Documentation

- **[Getting Started](GETTING_STARTED.md)** — First-time setup, capturing and importing assets
- **[Studio Guide](STUDIO_GUIDE.md)** — Multi-user deployment, review workflows, operation modes
- **[Architecture](ARCHITECTURE.md)** — Technical design, patterns, database schema
- **[Changelog](CHANGELOG.md)** — Version history and release notes
- **[Contributing](CONTRIBUTING.md)** — How to contribute to the project

## Pipeline Integration

Universal Library is part of a larger pipeline ecosystem:

```
                    Pipeline Control
                     (orchestrator)
                          │
       ┌──────────────────┼──────────────────┐
       │                  │                  │
  Shot Library      Action Library    Universal Library
  (per-project)        (global)          (This Repo)
                                        Global assets
                                   meshes/materials/rigs
```

- **Pipeline Control** — Orchestrates status across all libraries
- **Shot Library** — Per-project shots and playblasts
- **Action Library** — Global animation and pose library

In **Pipeline Mode**, asset status is read-only and controlled by Pipeline Control.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Author

Created by [CGstuff](https://github.com/CGstuff)
