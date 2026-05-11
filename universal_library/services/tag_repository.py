"""
TagRepository - Hierarchical tag CRUD operations

Pattern: Repository pattern for tag data access.
Tags are hierarchical (dot-separated): Vegetation.Tree.Deciduous.Oak
Parent matching: querying 'Vegetation.Tree' returns assets tagged with any descendant.
"""

from datetime import datetime
from typing import List, Dict, Optional, Any

from .base_repository import BaseRepository


class TagRepository(BaseRepository):
    """
    Repository for hierarchical tag operations.

    Tags form a tree via parent_id. Dot-separated display paths
    are constructed by walking the parent chain.
    """

    DEFAULT_COLORS = [
        '#F44336', '#E91E63', '#9C27B0', '#673AB7',
        '#3F51B5', '#2196F3', '#03A9F4', '#00BCD4',
        '#009688', '#4CAF50', '#8BC34A', '#CDDC39',
        '#FFC107', '#FF9800', '#FF5722', '#795548', '#607D8B',
    ]

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def create(self, name: str, color: Optional[str] = None,
               parent_id: Optional[int] = None) -> Optional[int]:
        """
        Create a single tag node.

        Args:
            name: Leaf name (e.g. 'Oak', NOT the full path)
            color: Hex color code
            parent_id: Parent tag ID or None for root

        Returns:
            Tag ID or None on error
        """
        if not name or not name.strip():
            return None

        name = name.strip()
        color = color or '#607D8B'

        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO tags (name, parent_id, color, created_date)
                    VALUES (?, ?, ?, ?)
                ''', (name, parent_id, color, datetime.now()))
                return cursor.lastrowid
        except Exception:
            return None

    def create_from_path(self, dot_path: str, color: Optional[str] = None) -> Optional[int]:
        """
        Create a tag from a dot-separated path, auto-creating parents.

        Example: 'Vegetation.Tree.Deciduous.Oak' creates up to 4 nodes.
        If intermediate nodes already exist, they are reused.

        Args:
            dot_path: Dot-separated tag path
            color: Color for the leaf tag (parents get default)

        Returns:
            Leaf tag ID or None on error
        """
        parts = [p.strip() for p in dot_path.split('.') if p.strip()]
        if not parts:
            return None

        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                parent_id = None

                for i, part in enumerate(parts):
                    is_leaf = (i == len(parts) - 1)

                    # Check if this node already exists under current parent
                    cursor.execute('''
                        SELECT id FROM tags
                        WHERE name = ? AND (parent_id IS ? OR parent_id = ?)
                    ''', (part, parent_id, parent_id))
                    row = cursor.fetchone()

                    if row:
                        parent_id = row[0]
                    else:
                        tag_color = color if is_leaf else '#607D8B'
                        cursor.execute('''
                            INSERT INTO tags (name, parent_id, color, created_date)
                            VALUES (?, ?, ?, ?)
                        ''', (part, parent_id, tag_color, datetime.now()))
                        parent_id = cursor.lastrowid

                return parent_id
        except Exception:
            return None

    def get_by_id(self, tag_id: int) -> Optional[Dict[str, Any]]:
        """Get tag by ID, including computed full_path."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tags WHERE id = ?', (tag_id,))
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        result['full_path'] = self._build_path(cursor, tag_id)
        return result

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get tag by exact leaf name (case-insensitive). Returns first match."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tags WHERE LOWER(name) = LOWER(?)', (name.strip(),))
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        result['full_path'] = self._build_path(cursor, result['id'])
        return result

    def get_by_path(self, dot_path: str) -> Optional[Dict[str, Any]]:
        """
        Get tag by full dot-separated path.

        Args:
            dot_path: e.g. 'Vegetation.Tree.Deciduous.Oak'

        Returns:
            Tag dict or None
        """
        parts = [p.strip() for p in dot_path.split('.') if p.strip()]
        if not parts:
            return None

        conn = self._get_connection()
        cursor = conn.cursor()
        parent_id = None

        for part in parts:
            cursor.execute('''
                SELECT * FROM tags
                WHERE LOWER(name) = LOWER(?) AND (parent_id IS ? OR parent_id = ?)
            ''', (part, parent_id, parent_id))
            row = cursor.fetchone()
            if not row:
                return None
            parent_id = row['id']

        result = dict(row)
        result['full_path'] = dot_path
        return result

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all tags sorted by name, with full_path."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tags ORDER BY name')
        rows = cursor.fetchall()

        results = []
        for row in rows:
            d = dict(row)
            d['full_path'] = self._build_path(cursor, d['id'])
            results.append(d)

        # Sort by full_path for natural tree ordering
        results.sort(key=lambda t: t['full_path'].lower())
        return results

    def update(self, tag_id: int, name: Optional[str] = None,
               color: Optional[str] = None, parent_id: Optional[int] = -1) -> bool:
        """
        Update a tag. Pass parent_id=-1 to leave unchanged, None to make root.
        """
        updates = {}
        if name is not None:
            updates['name'] = name.strip()
        if color is not None:
            updates['color'] = color
        if parent_id != -1:
            updates['parent_id'] = parent_id

        if not updates:
            return True

        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                set_clause = ', '.join(f"{k} = ?" for k in updates)
                values = list(updates.values()) + [tag_id]
                cursor.execute(f'UPDATE tags SET {set_clause} WHERE id = ?', values)
                return cursor.rowcount > 0
        except Exception:
            return False

    def delete(self, tag_id: int) -> bool:
        """Delete a tag and all descendants (CASCADE via FK)."""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
                return cursor.rowcount > 0
        except Exception:
            return False

    def get_or_create(self, name: str, color: Optional[str] = None) -> Optional[int]:
        """Get existing tag by leaf name or create. For flat compat."""
        existing = self.get_by_name(name)
        if existing:
            return existing['id']
        return self.create(name, color)

    def get_or_create_path(self, dot_path: str, color: Optional[str] = None) -> Optional[int]:
        """Get existing tag by path or create full chain."""
        existing = self.get_by_path(dot_path)
        if existing:
            return existing['id']
        return self.create_from_path(dot_path, color)

    # ------------------------------------------------------------------
    # Hierarchy queries
    # ------------------------------------------------------------------

    def get_children(self, parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get direct children of a tag (or root tags if parent_id is None)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if parent_id is None:
            cursor.execute('SELECT * FROM tags WHERE parent_id IS NULL ORDER BY name')
        else:
            cursor.execute('SELECT * FROM tags WHERE parent_id = ? ORDER BY name', (parent_id,))

        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d['full_path'] = self._build_path(cursor, d['id'])
            results.append(d)
        return results

    def get_descendants(self, tag_id: int) -> List[Dict[str, Any]]:
        """
        Get all descendants of a tag (recursive).
        Uses iterative BFS to avoid deep recursion.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        descendants = []
        queue = [tag_id]

        while queue:
            current = queue.pop(0)
            cursor.execute('SELECT * FROM tags WHERE parent_id = ?', (current,))
            for row in cursor.fetchall():
                d = dict(row)
                d['full_path'] = self._build_path(cursor, d['id'])
                descendants.append(d)
                queue.append(d['id'])

        return descendants

    def get_descendant_ids(self, tag_id: int) -> List[int]:
        """Get all descendant IDs of a tag (recursive). Lightweight."""
        conn = self._get_connection()
        cursor = conn.cursor()

        ids = []
        queue = [tag_id]

        while queue:
            current = queue.pop(0)
            cursor.execute('SELECT id FROM tags WHERE parent_id = ?', (current,))
            for row in cursor.fetchall():
                ids.append(row[0])
                queue.append(row[0])

        return ids

    def get_tree(self) -> List[Dict[str, Any]]:
        """
        Get the full tag tree as nested dicts.

        Returns list of root nodes, each with 'children' list.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tags ORDER BY name')
        all_tags = [dict(row) for row in cursor.fetchall()]

        # Build lookup
        by_id = {}
        for t in all_tags:
            t['children'] = []
            t['full_path'] = ''
            by_id[t['id']] = t

        roots = []
        for t in all_tags:
            pid = t.get('parent_id')
            if pid is None or pid not in by_id:
                roots.append(t)
            else:
                by_id[pid]['children'].append(t)

        # Compute paths
        def set_paths(nodes, prefix=''):
            for n in nodes:
                n['full_path'] = f"{prefix}.{n['name']}" if prefix else n['name']
                set_paths(n['children'], n['full_path'])

        set_paths(roots)
        return roots

    def has_children(self, tag_id: int) -> bool:
        """Check if a tag has any children."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM tags WHERE parent_id = ? LIMIT 1', (tag_id,))
        return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Asset-tag relationships
    # ------------------------------------------------------------------

    def add_tag_to_asset(self, asset_uuid: str, tag_id: int) -> bool:
        """Add a tag to an asset."""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO asset_tags (asset_uuid, tag_id, created_date)
                    VALUES (?, ?, ?)
                ''', (asset_uuid, tag_id, datetime.now()))
                return True
        except Exception:
            return False

    def remove_tag_from_asset(self, asset_uuid: str, tag_id: int) -> bool:
        """Remove a tag from an asset."""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM asset_tags WHERE asset_uuid = ? AND tag_id = ?
                ''', (asset_uuid, tag_id))
                return True
        except Exception:
            return False

    def get_asset_tags(self, asset_uuid: str) -> List[Dict[str, Any]]:
        """Get all tags for an asset, with full_path."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.id, t.name, t.color, t.parent_id
            FROM tags t
            INNER JOIN asset_tags at ON t.id = at.tag_id
            WHERE at.asset_uuid = ?
            ORDER BY t.name
        ''', (asset_uuid,))

        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d['full_path'] = self._build_path(cursor, d['id'])
            results.append(d)

        results.sort(key=lambda t: t['full_path'].lower())
        return results

    def set_asset_tags(self, asset_uuid: str, tag_ids: List[int]) -> bool:
        """Set all tags for an asset (replaces existing)."""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM asset_tags WHERE asset_uuid = ?', (asset_uuid,))
                now = datetime.now()
                for tag_id in tag_ids:
                    cursor.execute('''
                        INSERT INTO asset_tags (asset_uuid, tag_id, created_date)
                        VALUES (?, ?, ?)
                    ''', (asset_uuid, tag_id, now))
                return True
        except Exception:
            return False

    def get_assets_by_tag(self, tag_id: int) -> List[str]:
        """Get asset UUIDs with this exact tag."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT asset_uuid FROM asset_tags WHERE tag_id = ?', (tag_id,))
        return [row[0] for row in cursor.fetchall()]

    def get_assets_by_tag_or_descendants(self, tag_id: int) -> List[str]:
        """
        Get asset UUIDs tagged with this tag OR any of its descendants.
        This is the semantic query: 'Vegetation.Tree' matches 'Vegetation.Tree.Deciduous.Oak'.
        """
        all_ids = [tag_id] + self.get_descendant_ids(tag_id)
        if not all_ids:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(all_ids))
        cursor.execute(f'''
            SELECT DISTINCT asset_uuid FROM asset_tags
            WHERE tag_id IN ({placeholders})
        ''', all_ids)
        return [row[0] for row in cursor.fetchall()]

    def get_assets_by_tags(self, tag_ids: List[int], match_all: bool = False) -> List[str]:
        """
        Get asset UUIDs matching tag criteria.

        Args:
            tag_ids: List of tag IDs to match
            match_all: If True, asset must have ALL tags; if False, ANY tag

        Returns:
            List of asset UUIDs
        """
        if not tag_ids:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(tag_ids))

        if match_all:
            cursor.execute(f'''
                SELECT asset_uuid
                FROM asset_tags
                WHERE tag_id IN ({placeholders})
                GROUP BY asset_uuid
                HAVING COUNT(DISTINCT tag_id) = ?
            ''', (*tag_ids, len(tag_ids)))
        else:
            cursor.execute(f'''
                SELECT DISTINCT asset_uuid
                FROM asset_tags
                WHERE tag_id IN ({placeholders})
            ''', tag_ids)

        return [row[0] for row in cursor.fetchall()]

    def get_tag_usage_counts(self) -> Dict[int, int]:
        """Get usage count for each tag."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tag_id, COUNT(*) as count
            FROM asset_tags
            GROUP BY tag_id
        ''')
        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_tags_with_counts(self) -> List[Dict[str, Any]]:
        """Get all tags with usage counts and full_path."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.id, t.name, t.color, t.parent_id, COUNT(at.asset_uuid) as count
            FROM tags t
            LEFT JOIN asset_tags at ON t.id = at.tag_id
            GROUP BY t.id, t.name, t.color, t.parent_id
            ORDER BY t.name
        ''')

        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d['full_path'] = self._build_path(cursor, d['id'])
            results.append(d)

        results.sort(key=lambda t: t['full_path'].lower())
        return results

    def search_tags(self, query: str) -> List[Dict[str, Any]]:
        """Search tags by name or full path (partial match)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # First search by leaf name
        cursor.execute('SELECT * FROM tags WHERE name LIKE ? ORDER BY name', (f'%{query}%',))
        rows = cursor.fetchall()

        results = []
        seen_ids = set()
        for row in rows:
            d = dict(row)
            d['full_path'] = self._build_path(cursor, d['id'])
            if d['id'] not in seen_ids:
                results.append(d)
                seen_ids.add(d['id'])

        # Also match against full path
        all_tags = self.get_all()
        for tag in all_tags:
            if tag['id'] not in seen_ids and query.lower() in tag['full_path'].lower():
                results.append(tag)
                seen_ids.add(tag['id'])

        results.sort(key=lambda t: t['full_path'].lower())
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_path(self, cursor, tag_id: int) -> str:
        """Build dot-separated path by walking parent chain."""
        parts = []
        current_id = tag_id
        visited = set()

        while current_id is not None:
            if current_id in visited:
                break  # Circular reference guard
            visited.add(current_id)

            cursor.execute('SELECT name, parent_id FROM tags WHERE id = ?', (current_id,))
            row = cursor.fetchone()
            if not row:
                break
            parts.append(row[0])
            current_id = row[1]

        parts.reverse()
        return '.'.join(parts)


__all__ = ['TagRepository']
