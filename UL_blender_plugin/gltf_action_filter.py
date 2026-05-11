"""
glTF action filter — Blender user extension for the io_scene_gltf2 addon.

When our preview .glb export runs for a rig asset, we want to ship *only* the
actions attached to that specific armature — not "every action in the .blend
that could possibly target an armature with these bone names" (which is what
Blender's `ACTIONS` mode would otherwise do).

Blender's gltf addon has no `actions_to_export=[...]` parameter. It does,
however, fire a `gather_actions_hook` user extension hook per object during
ACTIONS export mode, passing a mutable parameters object holding the gathered
action list. See:

    io_scene_gltf2/blender/exp/animation/gltf2_blender_gather_action.py:698

We register an extension that reads a module-level filter dict. When our
armature is in it, the action list is filtered to allowed actions only.
When the dict is empty (default), the hook is a no-op — unrelated gltf
exports the user runs are unaffected.

Usage at the call site:

    from .gltf_action_filter import gltf_action_filter_session

    with gltf_action_filter_session(armature, ["WalkCycle", "Run"]):
        bpy.ops.export_scene.gltf(filepath=..., export_animation_mode='ACTIONS', ...)

NEVER touches user state — no NLA edits, no animation_data swaps, no
bpy.data mutations. Crash recovery is trivial since the only state is a
module-level dict in this addon's memory.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, Iterable, Set


# Module-level filter state.
# Maps `armature.name` -> set of action names allowed to be exported for it.
# Empty by default. Populated only inside `gltf_action_filter_session`.
_active_filter: Dict[str, Set[str]] = {}


def set_filter(armature_name: str, action_names: Iterable[str]) -> None:
    """Set the allowed-actions filter for an armature.

    Pass an empty iterable to export zero actions (the rig still gets exported
    at rest pose with full skinning data — just no animation tracks).
    """
    _active_filter[armature_name] = set(action_names)


def clear_filter() -> None:
    """Drop every active filter. The hook becomes a no-op until set_filter
    is called again. Safe to call multiple times."""
    _active_filter.clear()


@contextmanager
def gltf_action_filter_session(armature, action_names: Iterable[str]):
    """Context manager around a gltf export call.

    Sets the filter for this armature on entry, always clears on exit (even
    if the export raises). Use around `bpy.ops.export_scene.gltf(...)`.
    """
    try:
        if armature is not None:
            set_filter(armature.name, action_names)
        yield
    finally:
        clear_filter()


class _gltfActionFilterExtension:
    """User extension for io_scene_gltf2.

    Blender's gltf addon iterates `bpy.context.preferences.addons`, imports
    each addon's top-level module, and looks for `glTF2ExportUserExtension`
    (single class) or `glTF2ExportUserExtensions` (list). It instantiates
    the class once per gltf export, then dispatches hooks like
    `gather_actions_hook` when defined.

    Hook signature is `hook(blender_object, params, export_settings)`. The
    `params` object's class differs across Blender versions:

        Blender 3.x - 4.2:  GatherActionHookParameters
            .blender_actions  list[Action]
            .blender_tracks   dict[action_name -> track_name | None]
            .action_on_type   dict[action_name -> 'OBJECT' | 'SHAPEKEY']

        Blender 4.4+:       ActionsData
            (different attribute names — discovered at runtime)

    The hook discovers the list attribute dynamically so it works across
    versions without us having to maintain a version table.
    """

    # One-shot per-session diagnostic for unknown shapes.
    _shape_warned = False

    def gather_actions_hook(self, blender_object, params, export_settings):
        """Trim the gathered action list to actions allowed for this armature."""
        if not _active_filter:
            return  # Inactive — no-op for unrelated exports

        obj_name = getattr(blender_object, 'name', None)
        if obj_name is None or obj_name not in _active_filter:
            return  # This object isn't a target of our filter

        allowed = _active_filter[obj_name]

        # Try each known shape in order. The first one that succeeds wins.
        if (_try_filter_list_attribute(params, allowed)
                or _try_filter_actions_container(params, allowed)):
            return

        # No handler matched — dump diagnostics (once per session) so we
        # know what to add next time Blender changes the shape.
        if not _gltfActionFilterExtension._shape_warned:
            _gltfActionFilterExtension._shape_warned = True
            _log_unknown_shape(params)


def _try_filter_list_attribute(params, allowed) -> bool:
    """Blender 3.x - 4.2: params.blender_actions / actions_to_export is a
    flat list of Action objects. We can replace it directly.
    """
    for name in ('blender_actions', 'actions_to_export'):
        v = getattr(params, name, None)
        if isinstance(v, list):
            kept = [a for a in v if getattr(a, 'name', None) in allowed]
            setattr(params, name, kept)
            kept_names = {a.name for a in kept}
            # Parallel dicts keyed by action name — keep in sync
            for dict_attr in ('blender_tracks', 'action_on_type', 'tracks'):
                d = getattr(params, dict_attr, None)
                if isinstance(d, dict):
                    setattr(
                        params, dict_attr,
                        {k: val for k, val in d.items() if k in kept_names},
                    )
            return True
    return False


def _try_filter_actions_container(params, allowed) -> bool:
    """Blender 4.4+ shape: params is an ActionsData wrapper, with `actions`
    holding either a plain list, a dict {key -> Action-like}, or a custom
    container we mutate in place.

    Some Blender versions key the dict by the Action object itself; others
    key by (action, slot) tuples or by names. We accept any shape where the
    *value* looks like an Action (`hasattr(v, 'name')`) — or whose first
    tuple member does.
    """
    actions = getattr(params, 'actions', None)
    if actions is None:
        return False

    # List form
    if isinstance(actions, list):
        kept = [a for a in actions if _allowed_value(a, allowed)]
        # In-place mutation preserves the wrapper class' invariants
        actions[:] = kept
        return True

    # Dict form
    if isinstance(actions, dict):
        to_remove = [
            k for k, v in list(actions.items())
            if not _allowed_value(v, allowed) and not _allowed_value(k, allowed)
        ]
        for k in to_remove:
            try:
                del actions[k]
            except Exception:
                pass
        return True

    return False


def _allowed_value(v, allowed) -> bool:
    """Return True if v (or its first tuple member) is an Action whose name
    is in the allowed set. Handles direct Action, tuples of (Action, ...),
    or anything with a `.name` attribute matching."""
    if v is None:
        return False
    # Tuple/list — common when keying by (action, slot, target)
    if isinstance(v, (tuple, list)) and v:
        return _allowed_value(v[0], allowed)
    name = getattr(v, 'name', None)
    return name in allowed if name else False


def _log_unknown_shape(params):
    """One-shot diagnostic: print everything we can about an unknown params
    object so we can teach the filter the new shape next time."""
    attrs = [a for a in dir(params) if not a.startswith('_')]
    print(
        f"[gltf_action_filter] unknown params shape "
        f"({type(params).__name__}); attributes: {attrs}"
    )
    # Probe a few likely-candidate attributes
    for name in ('actions', 'blender_actions', 'actions_to_export', 'data'):
        v = getattr(params, name, None)
        if v is not None:
            print(
                f"[gltf_action_filter]   .{name} = "
                f"{type(v).__name__} (len={len(v) if hasattr(v, '__len__') else 'n/a'})"
            )
            # Sample a value if dict/list
            try:
                if isinstance(v, dict):
                    first_key = next(iter(v))
                    first_val = v[first_key]
                    print(
                        f"[gltf_action_filter]   .{name} first entry: "
                        f"key={type(first_key).__name__}({first_key!r}) "
                        f"val={type(first_val).__name__}"
                    )
                elif isinstance(v, list) and v:
                    print(
                        f"[gltf_action_filter]   .{name} first item: "
                        f"{type(v[0]).__name__}"
                    )
            except Exception:
                pass


# ----------------------------------------------------------------------
# Blender auto-discovery surface
# ----------------------------------------------------------------------

# Blender's io_scene_gltf2 addon looks for this name on each enabled addon's
# top-level module. We re-export it from `UL_blender_plugin/__init__.py` so
# the discovery there picks it up.
glTF2ExportUserExtension = _gltfActionFilterExtension


__all__ = [
    'glTF2ExportUserExtension',
    'gltf_action_filter_session',
    'set_filter',
    'clear_filter',
]
