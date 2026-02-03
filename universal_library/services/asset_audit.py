"""
AssetAudit - Audit logging for asset lifecycle operations.

Tracks who did what and when for compliance and accountability.
This is a STUDIO MODE ONLY feature - no logging occurs in Solo Mode.

Actions tracked:
- create: New asset created
- version_create: New version of existing asset
- update_metadata: Name, tags, description changed
- status_change: wip → review → approved → final
- approve: Asset marked approved
- finalize: Asset marked as final/published
- archive: Asset moved to archive
- restore: Asset restored from archive
- delete: Asset permanently deleted
- import: Asset imported into Blender
- export: Asset exported from Blender
- thumbnail_update: Thumbnail regenerated
- variant_create: New variant created
- promote_latest: Version promoted to latest
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any


class AssetAudit:
    """
    Asset-level audit logging (Studio Mode only).

    Provides a complete audit trail of who did what and when
    for compliance and accountability purposes.
    """

    def __init__(self, connection: sqlite3.Connection):
        """
        Initialize with database connection.

        Args:
            connection: SQLite connection to library database
        """
        self._connection = connection
        self._user_service = None  # Lazy-loaded to avoid circular imports

    def _get_user_service(self):
        """Lazy-load user service to avoid circular imports."""
        if self._user_service is None:
            try:
                from .user_service import get_user_service
                self._user_service = get_user_service()
            except ImportError:
                return None
        return self._user_service

    def _is_enabled(self) -> bool:
        """
        Check if audit logging is enabled.

        Returns True only when Studio Mode is active.
        """
        user_service = self._get_user_service()
        if user_service is None:
            return False
        return user_service.is_studio_mode()

    def _get_current_user_info(self) -> Dict[str, str]:
        """Get current user info for audit logging."""
        user_service = self._get_user_service()
        if user_service is None:
            return {'username': '', 'display_name': '', 'role': ''}

        return {
            'username': user_service.get_current_username(),
            'display_name': user_service.get_current_display_name(),
            'role': user_service.get_current_role(),
        }

    def log_action(
        self,
        asset_uuid: str,
        action: str,
        actor: str = None,
        actor_role: str = None,
        actor_display_name: str = None,
        version_group_id: str = None,
        version_label: str = None,
        variant_name: str = 'Base',
        action_category: str = None,
        details: dict = None,
        previous_value: str = None,
        new_value: str = None,
        source: str = 'desktop',
        session_id: str = None
    ) -> Optional[int]:
        """
        Log an asset action to the audit trail.

        Only logs if Studio Mode is enabled.

        Args:
            asset_uuid: UUID of the asset
            action: Action type (create, update, approve, etc.)
            actor: Username (auto-filled from current user if None)
            actor_role: Role of actor (auto-filled if None)
            actor_display_name: Display name (auto-filled if None)
            version_group_id: Version group for grouping versions
            version_label: Version label (v001, v002, etc.)
            variant_name: Variant name (Base, Damaged, etc.)
            action_category: Category (lifecycle, metadata, status, access)
            details: Additional details as dict (stored as JSON)
            previous_value: Value before change (for updates)
            new_value: Value after change (for updates)
            source: Source of action (desktop, blender, api)
            session_id: Optional session ID to group related actions

        Returns:
            Log entry ID or None if logging is disabled/failed
        """
        if not self._is_enabled():
            return None  # Skip logging in Solo Mode

        # Auto-fill user info if not provided
        if actor is None or actor_role is None or actor_display_name is None:
            user_info = self._get_current_user_info()
            actor = actor or user_info['username']
            actor_role = actor_role or user_info['role']
            actor_display_name = actor_display_name or user_info['display_name']

        # Infer action category if not provided
        if action_category is None:
            action_category = self._infer_category(action)

        # Serialize details to JSON
        details_json = json.dumps(details) if details else None

        try:
            cursor = self._connection.cursor()
            cursor.execute('''
                INSERT INTO asset_audit_log (
                    asset_uuid, version_group_id, version_label, variant_name,
                    action, action_category,
                    actor, actor_role, actor_display_name,
                    details, previous_value, new_value,
                    source, session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                asset_uuid, version_group_id, version_label, variant_name,
                action, action_category,
                actor, actor_role, actor_display_name,
                details_json, previous_value, new_value,
                source, session_id
            ))
            self._connection.commit()
            return cursor.lastrowid
        except Exception as e:
            return None

    def _infer_category(self, action: str) -> str:
        """Infer action category from action type."""
        lifecycle_actions = {'create', 'version_create', 'archive', 'restore', 'delete', 'variant_create'}
        metadata_actions = {'update_metadata', 'thumbnail_update'}
        status_actions = {'status_change', 'approve', 'finalize', 'promote_latest'}
        access_actions = {'import', 'export'}

        if action in lifecycle_actions:
            return 'lifecycle'
        elif action in metadata_actions:
            return 'metadata'
        elif action in status_actions:
            return 'status'
        elif action in access_actions:
            return 'access'
        return 'other'

    def get_asset_history(
        self,
        asset_uuid: str,
        limit: int = 100,
        include_version_group: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get complete history for an asset.

        Args:
            asset_uuid: UUID of the asset
            limit: Maximum entries to return
            include_version_group: If True, includes history for all versions

        Returns:
            List of audit log entries, newest first
        """
        cursor = self._connection.cursor()

        if include_version_group:
            # Get version_group_id for this asset
            cursor.execute('''
                SELECT version_group_id FROM assets WHERE uuid = ?
            ''', (asset_uuid,))
            row = cursor.fetchone()
            version_group_id = row[0] if row else None

            if version_group_id:
                # Get history for all versions in group
                cursor.execute('''
                    SELECT * FROM asset_audit_log
                    WHERE asset_uuid = ? OR version_group_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (asset_uuid, version_group_id, limit))
            else:
                cursor.execute('''
                    SELECT * FROM asset_audit_log
                    WHERE asset_uuid = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (asset_uuid, limit))
        else:
            cursor.execute('''
                SELECT * FROM asset_audit_log
                WHERE asset_uuid = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (asset_uuid, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_user_activity(
        self,
        actor: str,
        limit: int = 50,
        action_filter: str = None,
        days: int = None
    ) -> List[Dict[str, Any]]:
        """
        Get all activity by a specific user.

        Args:
            actor: Username to filter by
            limit: Maximum entries to return
            action_filter: Optional action type filter
            days: Optional limit to last N days

        Returns:
            List of audit log entries
        """
        cursor = self._connection.cursor()

        query = 'SELECT * FROM asset_audit_log WHERE actor = ?'
        params = [actor]

        if action_filter:
            query += ' AND action = ?'
            params.append(action_filter)

        if days:
            cutoff = datetime.now() - timedelta(days=days)
            query += ' AND timestamp >= ?'
            params.append(cutoff.isoformat())

        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_recent_activity(
        self,
        limit: int = 100,
        action_filter: str = None,
        category_filter: str = None,
        days: int = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent activity across all assets.

        Args:
            limit: Maximum entries to return
            action_filter: Optional action type filter
            category_filter: Optional category filter
            days: Optional limit to last N days

        Returns:
            List of audit log entries with asset info
        """
        cursor = self._connection.cursor()

        query = '''
            SELECT a.*, assets.name as asset_name, assets.asset_type
            FROM asset_audit_log a
            LEFT JOIN assets ON a.asset_uuid = assets.uuid
            WHERE 1=1
        '''
        params = []

        if action_filter:
            query += ' AND a.action = ?'
            params.append(action_filter)

        if category_filter:
            query += ' AND a.action_category = ?'
            params.append(category_filter)

        if days:
            cutoff = datetime.now() - timedelta(days=days)
            query += ' AND a.timestamp >= ?'
            params.append(cutoff.isoformat())

        query += ' ORDER BY a.timestamp DESC LIMIT ?'
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_activity_summary(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get summary statistics for dashboard.

        Args:
            days: Number of days to include in summary

        Returns:
            Dictionary with summary stats:
            - total_actions: Total number of actions
            - actions_by_user: Dict of username -> count
            - actions_by_type: Dict of action -> count
            - actions_by_category: Dict of category -> count
            - most_active_assets: List of (asset_uuid, count)
        """
        cursor = self._connection.cursor()
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        # Total actions
        cursor.execute('''
            SELECT COUNT(*) FROM asset_audit_log
            WHERE timestamp >= ?
        ''', (cutoff_str,))
        total_actions = cursor.fetchone()[0]

        # Actions by user
        cursor.execute('''
            SELECT actor, COUNT(*) as count FROM asset_audit_log
            WHERE timestamp >= ?
            GROUP BY actor
            ORDER BY count DESC
        ''', (cutoff_str,))
        actions_by_user = {row[0]: row[1] for row in cursor.fetchall()}

        # Actions by type
        cursor.execute('''
            SELECT action, COUNT(*) as count FROM asset_audit_log
            WHERE timestamp >= ?
            GROUP BY action
            ORDER BY count DESC
        ''', (cutoff_str,))
        actions_by_type = {row[0]: row[1] for row in cursor.fetchall()}

        # Actions by category
        cursor.execute('''
            SELECT action_category, COUNT(*) as count FROM asset_audit_log
            WHERE timestamp >= ? AND action_category IS NOT NULL
            GROUP BY action_category
            ORDER BY count DESC
        ''', (cutoff_str,))
        actions_by_category = {row[0]: row[1] for row in cursor.fetchall()}

        # Most active assets
        cursor.execute('''
            SELECT asset_uuid, COUNT(*) as count FROM asset_audit_log
            WHERE timestamp >= ?
            GROUP BY asset_uuid
            ORDER BY count DESC
            LIMIT 10
        ''', (cutoff_str,))
        most_active_assets = [(row[0], row[1]) for row in cursor.fetchall()]

        return {
            'total_actions': total_actions,
            'actions_by_user': actions_by_user,
            'actions_by_type': actions_by_type,
            'actions_by_category': actions_by_category,
            'most_active_assets': most_active_assets,
            'days': days,
        }

    def get_audit_log_for_export(
        self,
        asset_uuid: str = None,
        actor: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get audit log entries formatted for CSV export.

        Args:
            asset_uuid: Optional filter by asset
            actor: Optional filter by user
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)

        Returns:
            List of entries with flattened structure for CSV
        """
        cursor = self._connection.cursor()

        query = '''
            SELECT
                a.id,
                a.timestamp,
                a.asset_uuid,
                a.version_label,
                a.variant_name,
                a.action,
                a.action_category,
                a.actor,
                a.actor_role,
                a.actor_display_name,
                a.source,
                a.details,
                a.previous_value,
                a.new_value,
                assets.name as asset_name
            FROM asset_audit_log a
            LEFT JOIN assets ON a.asset_uuid = assets.uuid
            WHERE 1=1
        '''
        params = []

        if asset_uuid:
            query += ' AND a.asset_uuid = ?'
            params.append(asset_uuid)

        if actor:
            query += ' AND a.actor = ?'
            params.append(actor)

        if start_date:
            query += ' AND a.timestamp >= ?'
            params.append(start_date)

        if end_date:
            query += ' AND a.timestamp <= ?'
            params.append(end_date)

        query += ' ORDER BY a.timestamp DESC'

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


# Singleton instance
_asset_audit_instance: Optional[AssetAudit] = None


def get_asset_audit(connection: sqlite3.Connection = None) -> Optional[AssetAudit]:
    """
    Get the AssetAudit singleton instance.

    Args:
        connection: SQLite connection (required on first call)

    Returns:
        AssetAudit instance or None if no connection
    """
    global _asset_audit_instance
    if _asset_audit_instance is None and connection is not None:
        _asset_audit_instance = AssetAudit(connection)
    return _asset_audit_instance


def reset_asset_audit():
    """Reset the singleton (for testing)."""
    global _asset_audit_instance
    _asset_audit_instance = None


__all__ = ['AssetAudit', 'get_asset_audit', 'reset_asset_audit']
