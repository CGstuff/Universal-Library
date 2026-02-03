# Getting Started with Universal Library

This guide walks you through setting up Universal Library and managing your first assets.

## Table of Contents

- [First Launch](#first-launch)
- [Understanding the Interface](#understanding-the-interface)
- [Capturing Your First Asset](#capturing-your-first-asset)
- [Importing Assets](#importing-assets)
- [Organizing Assets](#organizing-assets)
- [Working with Versions](#working-with-versions)
- [Tips and Best Practices](#tips-and-best-practices)

---

## First Launch

### Setting Your Library Path

When you first launch Universal Library, you'll be prompted to set your library storage path. This is where all your assets, versions, and metadata will be stored.

**Choosing a location:**

- **Local drive** — Best for solo work, fastest performance
- **Network drive** — Required for multi-user/studio setups (see [Studio Guide](STUDIO_GUIDE.md))
- **External drive** — Good for portable libraries

The setup wizard will create the necessary folder structure:

```
your-library/
├── library/           # Active assets
├── _archive/          # Version history
├── reviews/           # Screenshots
├── cache/             # Thumbnails
└── .meta/             # Databases
```

### Interface Overview

Once configured, you'll see the main interface:

```
┌─────────────────────────────────────────────────────────────────┐
│  [Search]                    [View] [Filter] [Settings]         │
├───────────────┬─────────────────────────────┬───────────────────┤
│               │                             │                   │
│   Folders     │      Asset Grid/List        │   Metadata Panel  │
│               │                             │                   │
│   - All       │  ┌───┐ ┌───┐ ┌───┐ ┌───┐   │   Name: Sword     │
│   - Favorites │  │   │ │   │ │   │ │   │   │   Type: mesh      │
│   - Recent    │  └───┘ └───┘ └───┘ └───┘   │   Version: v003   │
│   - Props     │                             │   Tags: weapon    │
│   - ...       │  ┌───┐ ┌───┐ ┌───┐ ┌───┐   │                   │
│               │  │   │ │   │ │   │ │   │   │   [Import]        │
│               │  └───┘ └───┘ └───┘ └───┘   │                   │
└───────────────┴─────────────────────────────┴───────────────────┘
```

---

## Capturing Your First Asset

### Step 1: Set Up Blender Addon

1. In Universal Library, go to **Settings → Blender Integration**
2. Click **Install Addon**
3. Select your Blender executable (e.g., `blender.exe`)
4. The addon will be automatically installed to Blender

Alternatively, manually copy `UL_blender_plugin/` to:
- **Windows:** `%APPDATA%\Blender Foundation\Blender\4.x\scripts\addons\`
- **macOS:** `~/Library/Application Support/Blender/4.x/scripts/addons/`
- **Linux:** `~/.config/blender/4.x/scripts/addons/`

### Step 2: Enable the Addon in Blender

1. Open Blender
2. Go to **Edit → Preferences → Add-ons**
3. Search for "Universal Library"
4. Enable the addon

### Step 3: Export Your Asset

1. Select the object(s) you want to save
2. Press **Ctrl+Shift+E** (or find **Universal Library → Export** in the 3D View menu)
3. Fill in the export dialog:
   - **Name** — Asset name (e.g., "Medieval Sword")
   - **Type** — Asset type (mesh, material, rig, etc.)
   - **Variant** — Variant name (defaults to "Base")
   - **Description** — Optional notes
4. Click **Export**

The addon will:
- Generate a thumbnail from the current viewport
- Export the .blend file with full fidelity
- Register the asset in Universal Library's database

### Naming Conventions

**Recommended naming:**
- Use descriptive names: `Medieval_Sword`, `Oak_Tree_Large`
- For variants: `Armor_Iron`, `Armor_Gold`, `Armor_Diamond`
- Avoid special characters: `< > : " / \ | ? *`

---

## Importing Assets

### Quick Import (Double-Click)

Double-click any asset card to import it into your current Blender scene with default settings.

### Import with Options

Right-click an asset card or use the **Import** button in the metadata panel:

**Import Methods:**
- **Link** — References the asset (smaller file, updates when source changes)
- **Append** — Copies the asset into your file (independent copy)
- **Instance** — Creates an instance of a linked collection (best for props)

**When to use each:**
| Method | File Size | Updates | Best For |
|--------|-----------|---------|----------|
| Link | Small | Yes | WIP assets, shared resources |
| Append | Large | No | Final renders, standalone files |
| Instance | Small | Yes | Scattering props, environments |

### Current Reference Files

Universal Library can create `.current.blend` proxy files that always point to the latest version:

```
library/meshes/Sword/Base/
├── Sword.v001.blend
├── Sword.v002.blend
├── Sword.v003.blend        # Latest version
└── Sword.current.blend     # Always links to v003
```

**Benefits:**
- Link to `Sword.current.blend` in your scene
- When v004 is published, your scene auto-updates
- No need to manually relink after new versions

Enable this in **Settings → Storage → Create Current Reference Files**.

---

## Organizing Assets

### Folders

Create folders to organize assets by project, category, or workflow stage:

1. Right-click in the folder panel
2. Select **New Folder**
3. Enter a name

**Multi-folder assignment:**
Assets can belong to multiple folders. Right-click an asset and select **Assign to Folders** to add it to additional categories.

### Tags

Tags provide flexible, cross-cutting organization:

1. Select an asset
2. In the metadata panel, click **+ Add Tag**
3. Enter a tag name or select from existing tags

**Tag examples:**
- By project: `project_viking`, `project_scifi`
- By status: `hero`, `background`, `needs_fix`
- By usage: `exterior`, `interior`, `vegetation`

### Favorites

Star assets you use frequently:
- Click the star icon on the asset card
- Or right-click → **Add to Favorites**

Access favorites from the **Favorites** virtual folder.

### Search

Use the search bar to find assets:

- **Simple search:** `sword` — finds assets with "sword" in the name
- **Type filter:** Click the filter dropdown to limit by asset type
- **Tag filter:** Select tags from the filter panel

---

## Working with Versions

### Creating New Versions

When you update an asset and export again with the same name and variant, Universal Library automatically creates a new version:

```
v001 → v002 → v003
```

Previous versions are preserved in the `_archive/` folder.

### Version History

To view all versions of an asset:

1. Select the asset
2. Click **Version History** in the metadata panel (or press **V**)
3. The dialog shows all versions with thumbnails and dates

From here you can:
- **Preview** any version
- **Restore** an old version as the current version
- **Compare** versions side-by-side

### Cold Storage

Older versions are automatically moved to cold storage (`_archive/`) to keep the active library fast. This happens transparently—you can still access archived versions through the Version History dialog.

---

## Tips and Best Practices

### Asset Capture

1. **Clean viewport** — Hide UI elements before capturing for cleaner thumbnails
2. **Good lighting** — Use studio lighting or HDRIs for consistent previews
3. **Apply transforms** — Apply scale and rotation before exporting
4. **Name descriptively** — Future you will thank present you

### Organization

1. **Folder by project** — Create top-level folders for each project
2. **Tag liberally** — Tags are cheap and searchable
3. **Use variants** — Same asset, different colors/materials? Make variants
4. **Review regularly** — Archive or retire assets you no longer need

### Performance

1. **SSD storage** — Put your library on an SSD for best performance
2. **Network considerations** — For network drives, enable WAL mode (default)
3. **Thumbnail cache** — Let the cache warm up on first load

### Backup

1. **Database backups** — Go to **Settings → Maintenance → Backup Database**
2. **File backups** — Your library folder contains everything—back it up regularly
3. **Cloud sync** — If using cloud sync, exclude `.meta/` to avoid database conflicts

---

## Next Steps

- **[Studio Guide](STUDIO_GUIDE.md)** — Multi-user setup, review workflows, operation modes
- **[Architecture](ARCHITECTURE.md)** — Technical details for developers
- **[Changelog](CHANGELOG.md)** — What's new in each version

---

*Having issues? Check [GitHub Issues](https://github.com/CGstuff/Universal-Library/issues) or open a new one.*
