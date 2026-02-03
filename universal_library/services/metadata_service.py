"""
MetadataService - Schema-driven dynamic metadata management.

Handles:
- Entity type registration and lookup
- Metadata field definitions (schema-driven)
- Dynamic metadata storage (EAV pattern)
- Field validation and type coercion
"""

import json
from typing import Dict, Any, List, Optional
from .base_repository import BaseRepository


class MetadataService(BaseRepository):
    """
    Manages schema-driven dynamic metadata.

    Features:
    - Entity type registry in database
    - Field definitions with UI hints
    - EAV storage for dynamic entity metadata
    - Category-based field grouping

    Usage:
        meta = get_metadata_service()

        # Register a new field
        meta.register_field('asset', 'skin_cluster_count', 'Skin Clusters',
                           field_type='integer', category='rig')

        # Get fields for entity type
        fields = meta.get_fields_for_type('asset', category='rig')

        # Get/set entity metadata
        data = meta.get_entity_metadata(uuid)
        meta.set_entity_metadata(uuid, 'asset', {'skin_cluster_count': 5})
    """

    # =========================================================================
    # Entity Type Management
    # =========================================================================

    def register_entity_type(
        self,
        name: str,
        table_name: str,
        behaviors: List[str] = None,
        icon_name: str = None,
        icon_color: str = None
    ) -> Optional[int]:
        """
        Register an entity type in the database.

        Args:
            name: Entity type name ('asset', 'task', etc.)
            table_name: Database table name
            behaviors: List of behavior names
            icon_name: Optional icon name
            icon_color: Optional icon color

        Returns:
            Entity type ID or None if failed
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                behaviors_json = json.dumps(behaviors or [])

                cursor.execute('''
                    INSERT INTO entity_types (name, table_name, behaviors, icon_name, icon_color)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        table_name = excluded.table_name,
                        behaviors = excluded.behaviors,
                        icon_name = excluded.icon_name,
                        icon_color = excluded.icon_color
                ''', (name, table_name, behaviors_json, icon_name, icon_color))

                # Get the ID
                cursor.execute('SELECT id FROM entity_types WHERE name = ?', (name,))
                row = cursor.fetchone()
                return row[0] if row else None

        except Exception as e:
            return None

    def get_entity_type(self, name: str) -> Optional[Dict[str, Any]]:
        """Get entity type by name."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM entity_types WHERE name = ?', (name,))
        row = cursor.fetchone()

        if row:
            result = dict(row)
            result['behaviors'] = json.loads(result.get('behaviors', '[]'))
            return result
        return None

    def get_entity_type_id(self, name: str) -> Optional[int]:
        """Get entity type ID by name."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT id FROM entity_types WHERE name = ?', (name,))
        row = cursor.fetchone()
        return row[0] if row else None

    def list_entity_types(self) -> List[Dict[str, Any]]:
        """List all registered entity types."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM entity_types ORDER BY name')
        results = []
        for row in cursor.fetchall():
            result = dict(row)
            result['behaviors'] = json.loads(result.get('behaviors', '[]'))
            results.append(result)
        return results

    # =========================================================================
    # Field Definition Management
    # =========================================================================

    def register_field(
        self,
        entity_type: str,
        field_name: str,
        display_name: str,
        field_type: str = 'string',
        ui_widget: str = 'text',
        category: str = 'general',
        sort_order: int = 100,
        default_value: str = None,
        validation_rules: Dict = None,
        is_required: bool = False,
        is_searchable: bool = False,
        show_in_card: bool = False,
        show_in_details: bool = True
    ) -> Optional[int]:
        """
        Register a new metadata field.

        Args:
            entity_type: Entity type name ('asset', etc.)
            field_name: Internal field name ('bone_count')
            display_name: UI display name ('Bone Count')
            field_type: 'string', 'integer', 'real', 'boolean', 'json'
            ui_widget: 'text', 'number', 'checkbox', 'dropdown', 'multiline'
            category: Field category ('mesh', 'rig', 'animation', 'custom')
            sort_order: Display order within category
            default_value: Default value as string
            validation_rules: Dict of validation rules (e.g., {"min": 0, "max": 100})
            is_required: Whether field is required
            is_searchable: Whether field is searchable
            show_in_card: Whether to show in card view
            show_in_details: Whether to show in details panel

        Returns:
            Field ID or None if failed
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                # Get entity type ID
                entity_type_id = self.get_entity_type_id(entity_type)
                if not entity_type_id:
                    return None

                validation_json = json.dumps(validation_rules) if validation_rules else None

                cursor.execute('''
                    INSERT INTO metadata_fields
                    (entity_type_id, field_name, display_name, field_type,
                     ui_widget, category, sort_order, default_value,
                     validation_rules, is_required, is_searchable,
                     show_in_card, show_in_details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entity_type_id, field_name) DO UPDATE SET
                        display_name = excluded.display_name,
                        field_type = excluded.field_type,
                        ui_widget = excluded.ui_widget,
                        category = excluded.category,
                        sort_order = excluded.sort_order,
                        default_value = excluded.default_value,
                        validation_rules = excluded.validation_rules,
                        is_required = excluded.is_required,
                        is_searchable = excluded.is_searchable,
                        show_in_card = excluded.show_in_card,
                        show_in_details = excluded.show_in_details
                ''', (
                    entity_type_id, field_name, display_name, field_type,
                    ui_widget, category, sort_order, default_value,
                    validation_json, int(is_required), int(is_searchable),
                    int(show_in_card), int(show_in_details)
                ))

                return cursor.lastrowid

        except Exception as e:
            return None

    def get_fields_for_type(
        self,
        entity_type: str,
        category: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get all field definitions for an entity type.

        Args:
            entity_type: Entity type name
            category: Optional category filter

        Returns:
            List of field definition dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = '''
            SELECT mf.* FROM metadata_fields mf
            JOIN entity_types et ON mf.entity_type_id = et.id
            WHERE et.name = ?
        '''
        params = [entity_type]

        if category:
            query += ' AND mf.category = ?'
            params.append(category)

        query += ' ORDER BY mf.sort_order, mf.display_name'
        cursor.execute(query, params)

        results = []
        for row in cursor.fetchall():
            result = dict(row)
            if result.get('validation_rules'):
                result['validation_rules'] = json.loads(result['validation_rules'])
            results.append(result)

        return results

    def get_field(self, entity_type: str, field_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific field definition."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT mf.* FROM metadata_fields mf
            JOIN entity_types et ON mf.entity_type_id = et.id
            WHERE et.name = ? AND mf.field_name = ?
        ''', (entity_type, field_name))

        row = cursor.fetchone()
        if row:
            result = dict(row)
            if result.get('validation_rules'):
                result['validation_rules'] = json.loads(result['validation_rules'])
            return result
        return None

    def get_field_categories(self, entity_type: str) -> List[str]:
        """Get all categories for an entity type."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT DISTINCT mf.category FROM metadata_fields mf
            JOIN entity_types et ON mf.entity_type_id = et.id
            WHERE et.name = ?
            ORDER BY mf.category
        ''', (entity_type,))

        return [row[0] for row in cursor.fetchall()]

    def delete_field(self, entity_type: str, field_name: str) -> bool:
        """Delete a field definition (and all its values)."""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    DELETE FROM metadata_fields
                    WHERE id IN (
                        SELECT mf.id FROM metadata_fields mf
                        JOIN entity_types et ON mf.entity_type_id = et.id
                        WHERE et.name = ? AND mf.field_name = ?
                    )
                ''', (entity_type, field_name))

                return cursor.rowcount > 0

        except Exception as e:
            return False

    # =========================================================================
    # Entity Metadata Storage (EAV)
    # =========================================================================

    def get_entity_metadata(self, entity_uuid: str) -> Dict[str, Any]:
        """
        Get all dynamic metadata for an entity.

        Args:
            entity_uuid: Entity UUID

        Returns:
            Dictionary of field_name -> value
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT mf.field_name, mf.field_type,
                   em.value_text, em.value_int, em.value_real, em.value_json
            FROM entity_metadata em
            JOIN metadata_fields mf ON em.field_id = mf.id
            WHERE em.entity_uuid = ?
        ''', (entity_uuid,))

        result = {}
        for row in cursor.fetchall():
            field_name = row[0]
            field_type = row[1]

            # Extract value based on type
            if field_type == 'integer':
                result[field_name] = row[3]
            elif field_type == 'real':
                result[field_name] = row[4]
            elif field_type == 'boolean':
                result[field_name] = bool(row[3]) if row[3] is not None else None
            elif field_type == 'json':
                result[field_name] = json.loads(row[5]) if row[5] else None
            else:  # string
                result[field_name] = row[2]

        return result

    def set_entity_metadata(
        self,
        entity_uuid: str,
        entity_type: str,
        metadata: Dict[str, Any],
        conn: Any = None
    ) -> bool:
        """
        Set dynamic metadata for an entity.

        Args:
            entity_uuid: Entity UUID
            entity_type: Entity type name
            metadata: Dictionary of field_name -> value
            conn: Optional external connection (for participating in existing transaction)

        Returns:
            True if successful
        """
        if conn is not None:
            # Use provided connection (caller manages transaction)
            return self._set_entity_metadata_with_conn(entity_uuid, entity_type, metadata, conn)

        try:
            with self._transaction() as conn:
                return self._set_entity_metadata_with_conn(entity_uuid, entity_type, metadata, conn)
        except Exception as e:
            return False

    def _set_entity_metadata_with_conn(
        self,
        entity_uuid: str,
        entity_type: str,
        metadata: Dict[str, Any],
        conn: Any
    ) -> bool:
        """Internal method to set metadata using provided connection."""
        try:
            cursor = conn.cursor()

            for field_name, value in metadata.items():
                # Get field definition
                cursor.execute('''
                    SELECT mf.id, mf.field_type FROM metadata_fields mf
                    JOIN entity_types et ON mf.entity_type_id = et.id
                    WHERE et.name = ? AND mf.field_name = ?
                ''', (entity_type, field_name))

                row = cursor.fetchone()
                if not row:
                    # Field not registered - skip silently
                    continue

                field_id, field_type = row

                # Prepare value columns
                value_text = value_int = value_real = value_json = None

                if value is None:
                    pass  # All nulls
                elif field_type == 'integer':
                    value_int = int(value)
                elif field_type == 'real':
                    value_real = float(value)
                elif field_type == 'boolean':
                    value_int = 1 if value else 0
                elif field_type == 'json':
                    value_json = json.dumps(value)
                else:  # string
                    value_text = str(value)

                # Upsert
                cursor.execute('''
                    INSERT INTO entity_metadata
                    (entity_type, entity_uuid, field_id, value_text, value_int, value_real, value_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entity_uuid, field_id) DO UPDATE SET
                        value_text = excluded.value_text,
                        value_int = excluded.value_int,
                        value_real = excluded.value_real,
                        value_json = excluded.value_json,
                        modified_date = CURRENT_TIMESTAMP
                ''', (entity_type, entity_uuid, field_id, value_text, value_int, value_real, value_json))

            return True

        except Exception as e:
            return False

    def delete_entity_metadata(self, entity_uuid: str) -> bool:
        """Delete all metadata for an entity."""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM entity_metadata WHERE entity_uuid = ?',
                    (entity_uuid,)
                )
                return True
        except Exception as e:
            return False

    def get_entities_with_field_value(
        self,
        entity_type: str,
        field_name: str,
        value: Any
    ) -> List[str]:
        """
        Find entities with a specific field value.

        Args:
            entity_type: Entity type name
            field_name: Field name
            value: Value to search for

        Returns:
            List of entity UUIDs
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get field info
        field = self.get_field(entity_type, field_name)
        if not field:
            return []

        field_type = field['field_type']

        # Build query based on type
        if field_type == 'integer' or field_type == 'boolean':
            column = 'value_int'
            search_value = int(value) if field_type == 'boolean' else value
        elif field_type == 'real':
            column = 'value_real'
            search_value = value
        elif field_type == 'json':
            column = 'value_json'
            search_value = json.dumps(value)
        else:
            column = 'value_text'
            search_value = str(value)

        cursor.execute(f'''
            SELECT em.entity_uuid FROM entity_metadata em
            JOIN metadata_fields mf ON em.field_id = mf.id
            JOIN entity_types et ON mf.entity_type_id = et.id
            WHERE et.name = ? AND mf.field_name = ? AND em.{column} = ?
        ''', (entity_type, field_name, search_value))

        return [row[0] for row in cursor.fetchall()]


# Singleton instance
_metadata_service: Optional[MetadataService] = None


def get_metadata_service() -> MetadataService:
    """Get global MetadataService singleton instance."""
    global _metadata_service
    if _metadata_service is None:
        _metadata_service = MetadataService()
    return _metadata_service


__all__ = ['MetadataService', 'get_metadata_service']
