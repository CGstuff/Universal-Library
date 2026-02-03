"""
Representation Swap Operators - Swap linked library assets between representations.

Moved from Shot Library to Universal Library addon - UL is the SSOT for the library,
so representation logic lives here.

Finds Universal Asset Library links and temporarily swaps them to
.proxy.blend, .render.blend, or .nothing.blend for playblast/lookdev rendering.

Detection: a Blender library is recognized as a UAL library if EITHER:
- Its filepath contains a known representation suffix (.current, .proxy, .render, .nothing)
- A .current.blend sibling exists on disk (linked via the regular .blend)

Convention:
- .current.blend  -> the default link target (always latest version)
- .proxy.blend    -> lightweight proxy version (for playblasts)
- .render.blend   -> high-quality render version (for lookdev)
- .nothing.blend  -> empty file to hide assets and free memory

Save/Restore:
- Before any representation swap, original library paths are saved to a
  scene custom property (JSON).  "First swap wins" - subsequent swaps
  (proxy -> nothing) do NOT overwrite the saved originals.
- Restore reads saved paths and relocates libraries back, preserving any
  version picker choice the user made in the UL addon.

This module has zero coupling to the Universal Library database.
It relies purely on the file naming convention.

Uses lib.filepath + lib.reload() for swaps.  bpy.ops.wm.lib_relocate
crashes Blender at the C level (BKE_key_from_id null-ptr during ID remap)
when relocating from a simpler proxy file back to the full asset.
"""

import bpy
import json
import re
from bpy.types import Operator
from bpy.props import EnumProperty
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# File suffixes used by Universal Asset Library
CURRENT_SUFFIX = ".current"
PROXY_SUFFIX = ".proxy"
RENDER_SUFFIX = ".render"
NOTHING_SUFFIX = ".nothing"

REPRESENTATION_SUFFIXES = (CURRENT_SUFFIX, PROXY_SUFFIX, RENDER_SUFFIX, NOTHING_SUFFIX)

# Matches version directories like v001, v002, v0001, etc.
_VERSION_DIR_RE = re.compile(r'^v\d{3,}$')

# Matches versioned filename pattern: Sword.v001.blend or Sword.v001.current.blend
_VERSION_FILENAME_RE = re.compile(r'\.(v\d{3,})(?:\.|$)')

# Scene custom property key for saved original paths
_ORIG_PATHS_KEY = "ual_repr_original_paths"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _extract_version_from_stem(stem: str) -> Optional[str]:
    """
    Extract version label from a versioned filename stem.

    Examples:
        'Sword.v002' -> 'v002'
        'Sword.v002.current' -> 'v002'
        'Sword' -> None
    """
    match = _VERSION_FILENAME_RE.search(stem)
    return match.group(1) if match else None


def _get_base_name_from_stem(stem: str) -> str:
    """
    Extract base asset name from a versioned filename stem.

    Examples:
        'Sword.v002' -> 'Sword'
        'Sword.v002.current' -> 'Sword'
        'Sword.v002.proxy' -> 'Sword'
        'Sword' -> 'Sword'
    """
    return re.sub(r'\.(v\d{3,}).*$', '', stem)


def _get_version_from_library_users(lib) -> Optional[str]:
    """
    Get version label from objects using this library.

    Reads ual_version_label custom property from instance empties or
    linked objects that reference this library.

    Args:
        lib: bpy.types.Library reference

    Returns:
        Version label (e.g., 'v002') or None if not found
    """
    for obj in bpy.data.objects:
        # Check instance empties (LINK+INSTANCE mode)
        if obj.instance_collection and obj.instance_collection.library == lib:
            version = obj.get('ual_version_label')
            if version:
                return version
        # Check directly linked objects
        if obj.library == lib:
            version = obj.get('ual_version_label')
            if version:
                return version
    return None


# ---------------------------------------------------------------------------
# Save / Load / Clear original paths (scene custom property, JSON)
# ---------------------------------------------------------------------------

def _save_original_paths(ual_libs):
    """
    Save current library filepaths to scene[_ORIG_PATHS_KEY] as JSON.

    Keyed by the library's CURRENT absolute filepath (unique per library
    before swap). Value is the original filepath to restore to.

    First-swap-wins: if a filepath key already exists in the dict, it was
    saved during a previous swap and we keep the original value.

    FIX: When library is pointing to .current.blend, detect the actual
    version from object metadata and save the versioned file path instead.
    """
    scene = bpy.context.scene
    existing = _load_original_paths()

    changed = False
    for lib, base_stem, rep_dir in ual_libs:
        abs_path = Path(bpy.path.abspath(lib.filepath))
        abs_path_str = str(abs_path)

        if abs_path_str not in existing:
            original_path = abs_path_str

            # If currently pointing to .current.blend, use versioned file from metadata
            if abs_path.stem.endswith('.current'):
                version_label = _get_version_from_library_users(lib)
                if version_label:
                    # Build versioned path: Sword.v002.blend
                    versioned = rep_dir / f"{base_stem}.{version_label}.blend"
                    if versioned.exists():
                        original_path = str(versioned)

            existing[abs_path_str] = original_path
            changed = True

    if changed:
        scene[_ORIG_PATHS_KEY] = json.dumps(existing)


def _update_saved_key(old_filepath: str, new_filepath: str):
    """
    After a swap, update the saved dict key from old filepath to new filepath.

    The value (original filepath) stays the same - this just tracks that
    the library has moved from old_filepath to new_filepath.
    """
    scene = bpy.context.scene
    existing = _load_original_paths()

    if old_filepath in existing:
        original = existing.pop(old_filepath)
        existing[new_filepath] = original
        scene[_ORIG_PATHS_KEY] = json.dumps(existing)


def _load_original_paths() -> Dict[str, str]:
    """
    Read saved original paths from scene custom property.

    Returns:
        Dict mapping current_filepath -> original_filepath.
        Empty dict if nothing saved.
    """
    scene = bpy.context.scene
    raw = scene.get(_ORIG_PATHS_KEY)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _clear_original_paths(filepaths=None):
    """
    Clear saved original paths.

    Args:
        filepaths: Optional list/set of filepath keys to clear.
                   If None, clears everything.
    """
    scene = bpy.context.scene

    if filepaths is None:
        if _ORIG_PATHS_KEY in scene:
            del scene[_ORIG_PATHS_KEY]
        return

    existing = _load_original_paths()
    if not existing:
        return

    for fp in filepaths:
        existing.pop(fp, None)

    if existing:
        scene[_ORIG_PATHS_KEY] = json.dumps(existing)
    else:
        if _ORIG_PATHS_KEY in scene:
            del scene[_ORIG_PATHS_KEY]


# ---------------------------------------------------------------------------
# Pre-computed library-to-UUID mapping (for UUID filtering)
# ---------------------------------------------------------------------------

def _build_library_uuid_map() -> Dict['bpy.types.Library', Set[str]]:
    """
    Build mapping of library -> set of UUIDs that use it.

    Must be called BEFORE any swaps, as lib.reload() can invalidate
    obj.data.library references.

    Only considers INSTANCE objects (empties with instance_collection).
    """
    lib_to_uuids = defaultdict(set)

    for obj in bpy.data.objects:
        obj_uuid = obj.get('ual_uuid')
        if not obj_uuid:
            continue

        # Skip linked objects - they have UUIDs copied from the library file
        if obj.library:
            continue

        # Only process instance empties (objects with instance_collection)
        if not obj.instance_collection:
            continue

        col = obj.instance_collection

        # Collect all libraries this instance uses
        libs_used = set()

        if col.library:
            libs_used.add(col.library)

        for col_obj in col.all_objects:
            if col_obj.library:
                libs_used.add(col_obj.library)
            if col_obj.data and hasattr(col_obj.data, 'library') and col_obj.data.library:
                libs_used.add(col_obj.data.library)

        for lib in libs_used:
            lib_to_uuids[lib].add(obj_uuid)

    return dict(lib_to_uuids)


# ---------------------------------------------------------------------------
# Archive-to-library directory mapping
# ---------------------------------------------------------------------------

def _find_rep_dir(abs_path: Path, stem: str) -> Optional[Path]:
    """
    Find the directory containing representation files (.current.blend etc.)
    for a given library path.

    Handles two cases:
    1. The library's own directory has a .current.blend sibling -> return that dir
    2. The library is in _archive/.../vNNN/ -> navigate up to _archive, swap
       to library/, and check for .current.blend there
    """
    parent = abs_path.parent
    base_name = _get_base_name_from_stem(stem)

    # Case 1: Any representation file exists as a sibling in the same directory
    for suffix in (CURRENT_SUFFIX, PROXY_SUFFIX, RENDER_SUFFIX):
        rep_sibling = parent / f"{base_name}{suffix}.blend"
        if rep_sibling.exists():
            return parent

    # Case 2: We're in an archive path like _archive/meshes/Sword/Base/v001/
    for i, part in enumerate(parent.parts):
        if part == "_archive":
            prefix = Path(*parent.parts[:i]) if i > 0 else Path(parent.anchor)
            suffix_parts = list(parent.parts[i + 1:])

            # Remove version directory (vNNN) if it's the last part
            if suffix_parts and _VERSION_DIR_RE.match(suffix_parts[-1]):
                suffix_parts = suffix_parts[:-1]

            library_dir = prefix / "library"
            if suffix_parts:
                library_dir = library_dir.joinpath(*suffix_parts)

            # Check for representation files in library dir
            current_in_lib = library_dir / f"{base_name}{CURRENT_SUFFIX}.blend"
            if current_in_lib.exists():
                return library_dir

            for suffix in (PROXY_SUFFIX, RENDER_SUFFIX):
                rep_file = library_dir / f"{base_name}{suffix}.blend"
                if rep_file.exists():
                    return library_dir

            break

    return None


# ---------------------------------------------------------------------------
# Nothing blend generation
# ---------------------------------------------------------------------------

def _ensure_nothing_blend(rep_dir: Path, base_stem: str, asset_name: str = None) -> Path:
    """
    Ensure a .nothing.blend file exists in rep_dir.

    If missing, generates a minimal .blend with an empty collection/object
    named to match the original asset (critical for lib.reload() to work).
    """
    nothing_path = rep_dir / f"{base_stem}{NOTHING_SUFFIX}.blend"
    if nothing_path.exists():
        return nothing_path

    datablock_name = asset_name or base_stem
    _generate_nothing_blend(nothing_path, datablock_name)
    return nothing_path


def _generate_nothing_blend(target_path: Path, asset_name: str):
    """
    Generate a minimal .blend file with an empty collection and object.

    CRITICAL: The names must match the original asset's datablock names.
    When lib.reload() is called, Blender matches datablocks by NAME.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)

    col = bpy.data.collections.new(asset_name)
    obj = bpy.data.objects.new(asset_name, None)  # Empty object

    try:
        data_blocks = {col, obj}
        bpy.data.libraries.write(
            str(target_path),
            data_blocks,
            fake_user=True,
        )
    except Exception:
        raise
    finally:
        bpy.data.objects.remove(obj)
        bpy.data.collections.remove(col)


# ---------------------------------------------------------------------------
# Object-to-library mapping (for selected-only mode)
# ---------------------------------------------------------------------------

def get_libraries_for_objects(objects) -> Set:
    """
    Map selected objects to their linked library references.

    Uses multiple strategies to find the library:
    1. Instance collection library (LINK+INSTANCE mode)
    2. Direct library / override library
    3. Data block library (mesh/curve/etc.)
    4. Collection membership
    5. UAL metadata fallback
    """
    libs = set()

    for obj in objects:
        found = False

        # Strategy 1: Instance collection library
        if obj.instance_collection and obj.instance_collection.library:
            libs.add(obj.instance_collection.library)
            found = True

        # Strategy 2: Direct library or override library
        if obj.library:
            libs.add(obj.library)
            found = True
        elif obj.override_library and obj.override_library.reference and obj.override_library.reference.library:
            libs.add(obj.override_library.reference.library)
            found = True

        # Strategy 3: Data block library
        if obj.data:
            if hasattr(obj.data, 'library') and obj.data.library:
                libs.add(obj.data.library)
                found = True
            elif hasattr(obj.data, 'override_library') and obj.data.override_library:
                ref = obj.data.override_library.reference
                if ref and hasattr(ref, 'library') and ref.library:
                    libs.add(ref.library)
                    found = True

        # Strategy 4: Collection membership
        if not found:
            for col in obj.users_collection:
                if col.library:
                    libs.add(col.library)
                    found = True
                    break

        # Strategy 5: UAL metadata fallback
        if not found:
            asset_name = obj.get("ual_asset_name")
            if asset_name:
                for lib in bpy.data.libraries:
                    lib_path = Path(bpy.path.abspath(lib.filepath))
                    lib_stem = lib_path.stem
                    for suffix in REPRESENTATION_SUFFIXES:
                        if lib_stem.endswith(suffix):
                            lib_stem = lib_stem[:-len(suffix)]
                            break
                    lib_base_name = _get_base_name_from_stem(lib_stem)
                    if lib_stem == asset_name or lib_base_name == asset_name:
                        libs.add(lib)
                        break

    return libs


# ---------------------------------------------------------------------------
# Core: find UAL libraries
# ---------------------------------------------------------------------------

def find_ual_libraries(filter_libs=None) -> List[Tuple]:
    """
    Find all Blender libraries that belong to Universal Asset Library.

    Detects libraries linked via any UAL representation file:
    - .current.blend, .proxy.blend, .render.blend, .nothing.blend
    - regular .blend (when a .current.blend sibling exists on disk)

    Returns:
        List of (bpy.types.Library, base_stem, rep_dir) tuples.
    """
    ual_libs = []

    for lib in bpy.data.libraries:
        if filter_libs is not None and lib not in filter_libs:
            continue

        abs_path = Path(bpy.path.abspath(lib.filepath))
        stem = abs_path.stem

        matched = False
        for suffix in REPRESENTATION_SUFFIXES:
            if stem.endswith(suffix):
                stem_without_suffix = stem[: -len(suffix)]
                base_stem = _get_base_name_from_stem(stem_without_suffix)
                rep_dir = abs_path.parent
                ual_libs.append((lib, base_stem, rep_dir))
                matched = True
                break

        if not matched:
            base_stem = _get_base_name_from_stem(stem)
            rep_dir = _find_rep_dir(abs_path, stem)
            if rep_dir is not None:
                ual_libs.append((lib, base_stem, rep_dir))

    return ual_libs


# ---------------------------------------------------------------------------
# Core: swap to representation
# ---------------------------------------------------------------------------

def swap_to_representation(representation: str, filter_libs=None, filter_uuids=None, skip_shared=False) -> Tuple[int, int, List[str]]:
    """
    Swap UAL library links to a different representation.

    Handles proxy, render, and nothing (NOT 'current' - use restore_to_original
    instead). Saves original paths before first swap ("first swap wins").

    Args:
        representation: 'proxy', 'render', or 'nothing'
        filter_libs: Optional set of bpy.types.Library references.
        filter_uuids: Optional set of UUID strings.
        skip_shared: If True, skip libraries shared by UUIDs not in filter_uuids.

    Returns:
        Tuple of (swapped_count, skipped_count, warnings_list)
    """
    suffix_map = {
        'proxy': PROXY_SUFFIX,
        'render': RENDER_SUFFIX,
        'nothing': NOTHING_SUFFIX,
    }
    target_suffix = suffix_map.get(representation)
    if not target_suffix:
        return (0, 0, [f"Unknown representation: {representation}"])

    ual_libs = find_ual_libraries(filter_libs=filter_libs)

    if not ual_libs:
        return (0, 0, ["No UAL libraries found"])

    _save_original_paths(ual_libs)

    swapped = 0
    skipped = 0
    warnings = []
    used_targets = set()
    nothing_counter = {}

    lib_uuid_map = None
    if filter_uuids:
        lib_uuid_map = _build_library_uuid_map()

    for lib, base_stem, rep_dir in ual_libs:
        abs_path = Path(bpy.path.abspath(lib.filepath))
        abs_path_str = str(abs_path)

        # UUID filtering
        if filter_uuids and lib_uuid_map is not None:
            lib_uuids = lib_uuid_map.get(lib, set())
            matching = lib_uuids.intersection(filter_uuids)
            if not matching:
                skipped += 1
                continue

            other_uuids = lib_uuids - filter_uuids
            if other_uuids:
                if skip_shared:
                    warnings.append(f"{base_stem}: skipped - library shared by {len(other_uuids) + len(matching)} instances")
                    skipped += 1
                    continue
                else:
                    warnings.append(f"{base_stem}: library shared by {len(other_uuids) + len(matching)} instances - all will be affected")

        # Determine target path
        if representation == 'nothing':
            counter_key = str(rep_dir / base_stem)
            count = nothing_counter.get(counter_key, 0)
            if count == 0:
                nothing_stem = base_stem
            else:
                nothing_stem = f"{base_stem}._ul{count}"
            nothing_counter[counter_key] = count + 1
            try:
                target_path = _ensure_nothing_blend(rep_dir, nothing_stem, asset_name=base_stem)
            except Exception as e:
                msg = f"Failed to create nothing.blend for {base_stem}: {e}"
                warnings.append(msg)
                skipped += 1
                continue
        else:
            target_path = rep_dir / f"{base_stem}{target_suffix}.blend"

        if not target_path.exists():
            skipped += 1
            continue

        target_str = str(target_path)
        if target_str in used_targets:
            skipped += 1
            continue

        if abs_path == target_path:
            used_targets.add(target_str)
            continue

        old_name = lib.name
        try:
            lib.filepath = str(target_path)
            lib.reload()
            swapped += 1
            used_targets.add(target_str)
            _update_saved_key(abs_path_str, target_str)
        except Exception as e:
            msg = f"Failed to swap {base_stem}: {e}"
            warnings.append(msg)

    return (swapped, skipped, warnings)


# ---------------------------------------------------------------------------
# Restore to original paths
# ---------------------------------------------------------------------------

def restore_to_original(filter_libs=None, filter_uuids=None, skip_shared=False) -> Tuple[int, int, List[str]]:
    """
    Restore libraries to their original paths (before any representation swap).

    Reads saved paths from scene custom property. Each library is matched by
    its CURRENT filepath (the key in the saved dict).

    Returns:
        Tuple of (restored_count, skipped_count, warnings_list)
    """
    saved_paths = _load_original_paths()

    ual_libs = find_ual_libraries(filter_libs=filter_libs)
    if not ual_libs:
        return (0, 0, ["No UAL libraries found"])

    restored = 0
    skipped = 0
    warnings = []
    restored_keys = []
    nothing_temps = []

    lib_uuid_map = None
    if filter_uuids:
        lib_uuid_map = _build_library_uuid_map()

    for lib, base_stem, rep_dir in ual_libs:
        lib_name = lib.name
        abs_path = Path(bpy.path.abspath(lib.filepath))
        abs_path_str = str(abs_path)

        # UUID filtering
        if filter_uuids and lib_uuid_map is not None:
            lib_uuids = lib_uuid_map.get(lib, set())
            matching = lib_uuids.intersection(filter_uuids)
            if not matching:
                skipped += 1
                continue

            other_uuids = lib_uuids - filter_uuids
            if other_uuids:
                if skip_shared:
                    warnings.append(f"{base_stem}: skipped - library shared by {len(other_uuids) + len(matching)} instances")
                    skipped += 1
                    continue

        orig_path_str = saved_paths.get(abs_path_str)

        if not orig_path_str:
            skipped += 1
            continue

        target_path = Path(orig_path_str)

        if abs_path_str == orig_path_str:
            restored_keys.append(abs_path_str)
            continue

        if not target_path.exists():
            msg = f"Original file missing for {base_stem}: {target_path}"
            warnings.append(msg)
            skipped += 1
            continue

        stem = abs_path.stem
        if stem.endswith(NOTHING_SUFFIX) and "._ul" in stem:
            nothing_temps.append(abs_path)

        try:
            lib.filepath = str(target_path)
            lib.reload()
            restored += 1
            restored_keys.append(abs_path_str)
        except Exception as e:
            msg = f"Failed to restore {base_stem}: {e}"
            warnings.append(msg)

    if restored_keys:
        _clear_original_paths(restored_keys)

    # Clean up temp nothing files
    for temp_path in nothing_temps:
        try:
            temp_path.unlink()
        except Exception:
            pass

    return (restored, skipped, warnings)


# ---------------------------------------------------------------------------
# Swap info (for panel display)
# ---------------------------------------------------------------------------

def get_swap_info(filter_libs=None) -> Dict[str, dict]:
    """
    Get information about available representation swaps for UAL libraries.

    Returns:
        Dict mapping library name -> {
            'current_path': str,
            'has_proxy': bool,
            'has_render': bool,
            'has_nothing': bool,
            'active_representation': str,
            'base_stem': str,
            'rep_dir': str,
        }
    """
    info = {}
    for lib, base_stem, rep_dir in find_ual_libraries(filter_libs=filter_libs):
        abs_path = Path(bpy.path.abspath(lib.filepath))
        stem = abs_path.stem

        # Detect active representation
        if stem.endswith(NOTHING_SUFFIX):
            active = 'nothing'
        elif stem.endswith(PROXY_SUFFIX):
            active = 'proxy'
        elif stem.endswith(RENDER_SUFFIX):
            active = 'render'
        elif stem.endswith(CURRENT_SUFFIX):
            active = 'current'
        else:
            active = 'original'

        proxy_path = rep_dir / f"{base_stem}{PROXY_SUFFIX}.blend"
        render_path = rep_dir / f"{base_stem}{RENDER_SUFFIX}.blend"
        nothing_path = rep_dir / f"{base_stem}{NOTHING_SUFFIX}.blend"

        info[lib.name] = {
            'current_path': lib.filepath,
            'has_proxy': proxy_path.exists(),
            'has_render': render_path.exists(),
            'has_nothing': nothing_path.exists(),
            'active_representation': active,
            'base_stem': base_stem,
            'rep_dir': str(rep_dir),
        }
    return info


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

REPRESENTATION_ITEMS = [
    ('proxy', "Proxy", "Lightweight proxy (.proxy.blend)"),
    ('render', "Render", "High-quality render (.render.blend)"),
    ('nothing', "Nothing", "Hide asset - swap to empty file to free memory"),
]


class UAL_OT_swap_representation(Operator):
    """Swap all linked UAL assets to a different representation"""
    bl_idname = "ual.swap_representation"
    bl_label = "Swap Representation"
    bl_description = "Switch all linked library assets between proxy, render, and nothing"
    bl_options = {'REGISTER', 'UNDO'}

    representation: EnumProperty(
        name="Representation",
        items=REPRESENTATION_ITEMS,
        default='proxy',
    )

    def execute(self, context):
        swapped, skipped, warnings = swap_to_representation(self.representation)

        if warnings and swapped == 0:
            self.report({'WARNING'}, "; ".join(warnings))
            return {'CANCELLED'}

        label = self.representation.capitalize()
        if skipped:
            self.report({'INFO'}, f"Swapped {swapped} to {label} ({skipped} skipped)")
        elif swapped:
            self.report({'INFO'}, f"Swapped {swapped} libraries to {label}")
        else:
            self.report({'INFO'}, f"All libraries already on {label}")

        if swapped:
            context.view_layer.update()

        return {'FINISHED'}


class UAL_OT_swap_representation_selected(Operator):
    """Swap selected objects' linked UAL assets to a different representation"""
    bl_idname = "ual.swap_representation_selected"
    bl_label = "Swap Representation (Selected)"
    bl_description = "Switch selected objects' linked libraries between proxy, render, and nothing"
    bl_options = {'REGISTER', 'UNDO'}

    representation: EnumProperty(
        name="Representation",
        items=REPRESENTATION_ITEMS,
        default='proxy',
    )

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        # Collect UUIDs from selected objects
        selected_uuids = set()
        for obj in context.selected_objects:
            if 'ual_uuid' in obj:
                selected_uuids.add(obj['ual_uuid'])

        if not selected_uuids:
            # Fallback: if no UUIDs, use library-based filtering
            libs = get_libraries_for_objects(context.selected_objects)
            if not libs:
                self.report({'WARNING'}, "No UAL libraries found for selected objects")
                return {'CANCELLED'}
            swapped, skipped, warnings = swap_to_representation(
                self.representation, filter_libs=libs
            )
        else:
            swapped, skipped, warnings = swap_to_representation(
                self.representation, filter_uuids=selected_uuids, skip_shared=True
            )

        if warnings and swapped == 0:
            self.report({'WARNING'}, "; ".join(warnings))
            return {'CANCELLED'}

        label = self.representation.capitalize()
        if skipped:
            self.report({'INFO'}, f"Swapped {swapped} to {label} ({skipped} skipped)")
        elif swapped:
            self.report({'INFO'}, f"Swapped {swapped} libraries to {label}")
        else:
            self.report({'INFO'}, f"Selected libraries already on {label}")

        if swapped:
            context.view_layer.update()

        return {'FINISHED'}


class UAL_OT_restore_representation(Operator):
    """Restore all linked UAL assets to their original paths"""
    bl_idname = "ual.restore_representation"
    bl_label = "Restore Original"
    bl_description = "Restore all linked libraries to the paths they had before any representation swap"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        restored, skipped, warnings = restore_to_original()

        if warnings and restored == 0:
            self.report({'WARNING'}, "; ".join(warnings))
            return {'CANCELLED'}

        if skipped:
            self.report({'INFO'}, f"Restored {restored} libraries ({skipped} skipped)")
        elif restored:
            self.report({'INFO'}, f"Restored {restored} libraries")
        else:
            self.report({'INFO'}, "All libraries already at original paths")

        if restored:
            context.view_layer.update()

        return {'FINISHED'}


class UAL_OT_restore_representation_selected(Operator):
    """Restore selected objects' linked UAL assets to their original paths"""
    bl_idname = "ual.restore_representation_selected"
    bl_label = "Restore Original (Selected)"
    bl_description = "Restore selected objects' linked libraries to the paths they had before any representation swap"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        selected_uuids = set()
        for obj in context.selected_objects:
            if 'ual_uuid' in obj:
                selected_uuids.add(obj['ual_uuid'])

        if not selected_uuids:
            libs = get_libraries_for_objects(context.selected_objects)
            if not libs:
                self.report({'WARNING'}, "No UAL libraries found for selected objects")
                return {'CANCELLED'}
            restored, skipped, warnings = restore_to_original(filter_libs=libs)
        else:
            restored, skipped, warnings = restore_to_original(filter_uuids=selected_uuids, skip_shared=True)

        if warnings and restored == 0:
            self.report({'WARNING'}, "; ".join(warnings))
            return {'CANCELLED'}

        if skipped:
            self.report({'INFO'}, f"Restored {restored} libraries ({skipped} skipped)")
        elif restored:
            self.report({'INFO'}, f"Restored {restored} libraries")
        else:
            self.report({'INFO'}, "Selected libraries already at original paths")

        if restored:
            context.view_layer.update()

        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    UAL_OT_swap_representation,
    UAL_OT_swap_representation_selected,
    UAL_OT_restore_representation,
    UAL_OT_restore_representation_selected,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


def clear_representation_state(filepaths=None):
    """
    Clear saved representation swap state.

    Call this when the asset context changes (e.g., after switching variants)
    to ensure representation swaps work correctly with the new asset.

    Args:
        filepaths: Optional list/set of filepath strings to clear.
                   If None, clears ALL saved state (use with caution in
                   scenes with multiple asset families).
    """
    _clear_original_paths(filepaths)


__all__ = [
    'swap_to_representation',
    'restore_to_original',
    'get_swap_info',
    'get_libraries_for_objects',
    'find_ual_libraries',
    'clear_representation_state',
    'UAL_OT_swap_representation',
    'UAL_OT_swap_representation_selected',
    'UAL_OT_restore_representation',
    'UAL_OT_restore_representation_selected',
    'register',
    'unregister',
]
