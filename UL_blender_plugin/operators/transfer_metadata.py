"""
Transfer UAL Metadata operator.

Stamps the active object's UAL metadata onto every other selected object,
making them all members of the same asset family. This is a metadata-only
operation — no file save, no DB write. The next "new version" export
picks up the newly-stamped objects automatically.

Workflows this enables:
- Custom mesh as proxy (build a cube, transfer metadata from source asset,
  Save Proxy works because the cube now carries the asset's identity)
- Add new meshes to an existing asset without re-importing everything
  from source (import asset, build new geo, transfer metadata, save as
  new version)
- Re-link orphaned objects whose metadata was accidentally cleared
- Bulk ingest legacy geometry by tagging seed + transferring to siblings

Convention: ACTIVE = source, OTHER SELECTED = targets. Matches Blender's
standard "join to active" / "parent to active" idioms.

Conflict policy (per design decision 1b): if any target object already
belongs to a *different* asset (different `ual_asset_id`), the operator
shows a soft-confirmation dialog requiring an explicit "overwrite" tick
before stamping those. Untagged and same-asset targets are stamped
unconditionally.
"""

import logging

import bpy
from bpy.props import BoolProperty
from bpy.types import Operator

from ..utils.metadata_handler import (
    has_ual_metadata, read_ual_metadata, store_ual_metadata,
)

logger = logging.getLogger(__name__)


class UAL_OT_transfer_metadata_from_active(Operator):
    """Mark selected objects as part of the active object's UAL asset.

    Stamps every selected object with the active object's `ual_*` properties.
    No file save, no DB write — only changes the in-Blender metadata. Save
    as a new version afterwards to bake the new family membership.
    """

    bl_idname = "ual.transfer_metadata_from_active"
    bl_label = "Transfer UAL Metadata from Active"
    bl_description = (
        "Stamp the active object's UAL identity onto every other selected "
        "object so they all belong to the same asset. Useful for custom "
        "proxies, adding new meshes to an asset, or re-linking objects "
        "whose metadata was cleared."
    )
    bl_options = {'REGISTER', 'UNDO'}

    overwrite_conflicts: BoolProperty(
        name="Overwrite conflicting metadata",
        description=(
            "Some selected objects already belong to a DIFFERENT asset. "
            "Tick to overwrite them too (no undo for the metadata itself "
            "beyond Blender's UNDO stack)."
        ),
        default=False,
    )

    @classmethod
    def poll(cls, context):
        active = context.active_object
        if active is None or not has_ual_metadata(active):
            return False
        # Need at least one selected object OTHER than the active.
        return any(o is not active for o in context.selected_objects)

    def _classify_targets(self, context):
        """Split selected (excluding active) into three buckets:
            - untagged: no UAL metadata at all
            - same_asset: already belongs to active's asset (no-op)
            - conflicting: belongs to a DIFFERENT asset (needs confirmation)
        """
        active = context.active_object
        active_meta = read_ual_metadata(active) or {}
        active_asset_id = active_meta.get('asset_id')

        untagged, same_asset, conflicting = [], [], []
        for obj in context.selected_objects:
            if obj is active:
                continue
            if not has_ual_metadata(obj):
                untagged.append(obj)
                continue
            obj_meta = read_ual_metadata(obj) or {}
            if obj_meta.get('asset_id') == active_asset_id:
                same_asset.append(obj)
            else:
                conflicting.append(obj)
        return untagged, same_asset, conflicting

    def invoke(self, context, event):
        """Show the confirmation dialog ONLY when there are conflicts.

        No conflicts → run immediately. This keeps the common case
        (stamp a fresh cube as a proxy for an asset) fast — one click,
        no popup.
        """
        _untagged, _same, conflicting = self._classify_targets(context)
        if not conflicting:
            # Reset the overwrite flag so a previous run doesn't leak state.
            self.overwrite_conflicts = False
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        untagged, same_asset, conflicting = self._classify_targets(context)
        active = context.active_object
        active_meta = read_ual_metadata(active) or {}
        active_name = active_meta.get('asset_name', '?') or '?'
        active_version = active_meta.get('version_label', '') or ''

        header = layout.box()
        title = f"Source: {active_name}"
        if active_version:
            title += f"  {active_version}"
        header.label(text=title, icon='OBJECT_DATA')

        if untagged:
            header.label(
                text=f"{len(untagged)} object(s) will be stamped",
                icon='CHECKMARK',
            )
        if same_asset:
            header.label(
                text=f"{len(same_asset)} object(s) already belong here",
                icon='LINKED',
            )
        if conflicting:
            warn = layout.box()
            row = warn.row()
            row.alert = True
            row.label(
                text=f"{len(conflicting)} object(s) belong to a DIFFERENT asset",
                icon='ERROR',
            )
            warn.label(
                text="Stamping overwrites their existing metadata.",
            )
            warn.prop(self, "overwrite_conflicts")

    def execute(self, context):
        active = context.active_object
        if active is None or not has_ual_metadata(active):
            self.report({'ERROR'}, "Active object has no UAL metadata.")
            return {'CANCELLED'}

        meta = read_ual_metadata(active)
        if not meta:
            self.report({'ERROR'}, "Failed to read active object's UAL metadata.")
            return {'CANCELLED'}

        untagged, same_asset, conflicting = self._classify_targets(context)

        # Decide which conflicting objects to actually overwrite.
        to_overwrite = conflicting if self.overwrite_conflicts else []
        skipped_conflicting = [] if self.overwrite_conflicts else conflicting

        targets = untagged + to_overwrite
        for obj in targets:
            try:
                store_ual_metadata(
                    obj,
                    uuid=meta.get('uuid', ''),
                    version_group_id=meta.get('version_group_id', ''),
                    version=meta.get('version', 1),
                    version_label=meta.get('version_label', 'v001'),
                    asset_name=meta.get('asset_name', ''),
                    asset_type=meta.get('asset_type', 'model'),
                    representation_type=meta.get('representation_type', 'none'),
                    imported=meta.get('imported', True),
                    asset_id=meta.get('asset_id', ''),
                    variant_name=meta.get('variant_name', 'Base'),
                    link_mode=meta.get('link_mode', 'APPEND'),
                )
            except (AttributeError, ReferenceError) as e:
                logger.warning(
                    "transfer_metadata: failed to stamp '%s': %s", obj.name, e
                )

        # Compose a status report that surfaces every bucket so the user
        # can verify what actually happened.
        parts = [f"Stamped {len(targets)}"]
        if same_asset:
            parts.append(f"{len(same_asset)} already matched")
        if skipped_conflicting:
            parts.append(
                f"{len(skipped_conflicting)} conflicting skipped — "
                "re-run with Overwrite ticked to include them"
            )
        self.report({'INFO'}, " · ".join(parts))
        return {'FINISHED'}


classes = (UAL_OT_transfer_metadata_from_active,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except (RuntimeError, ValueError):
            pass


__all__ = [
    'UAL_OT_transfer_metadata_from_active',
    'register',
    'unregister',
]
