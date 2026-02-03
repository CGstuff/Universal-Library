"""
GenericRepository - Entity-type-agnostic repository.

Provides CRUD operations for any registered entity type,
with automatic handling of both core fields and dynamic metadata.
"""

from typing import Dict, Any, List, Optional, Type
from .base_repository import BaseRepository
from .metadata_service import get_metadata_service
from ..core.entity import Entity, EntityRegistry, get_entity_registry


class GenericRepository(BaseRepository):
    """
    Generic repository supporting any registered entity type.

    Features:
    - CRUD operations for any entity type
    - Automatic core/dynamic field separation
    - EAV metadata integration
    - Behavior-aware queries

    Usage:
        repo = GenericRepository('asset')

        # Get entity with all metadata
        entity = repo.get_by_uuid('some-uuid')

        # Save entity (handles core + dynamic split)
        repo.save(entity)

        # Query with dynamic field filter
        entities = repo.find_by_field('bone_count', 50)
    """

    def __init__(self, entity_type: str):
        """
        Initialize repository for specific entity type.

        Args:
            entity_type: Registered entity type name ('asset', etc.)
        """
        super().__init__()
        self._entity_type = entity_type
        self._registry = get_entity_registry()
        self._metadata_service = get_metadata_service()

        # Get entity definition
        self._entity_class = self._registry.get(entity_type)
        if self._entity_class:
            self._definition = self._entity_class.get_definition()
        else:
            self._definition = None

    @property
    def table_name(self) -> Optional[str]:
        """Get database table name for this entity type."""
        return self._definition.table_name if self._definition else None

    @property
    def core_fields(self) -> List[str]:
        """Get list of core fields for this entity type."""
        return self._definition.core_fields if self._definition else []

    def get_by_uuid(self, uuid: str) -> Optional[Entity]:
        """
        Get entity by UUID with all metadata.

        Loads core data from main table and dynamic metadata from EAV.

        Args:
            uuid: Entity UUID

        Returns:
            Entity instance or None if not found
        """
        if not self._definition:
            return None

        conn = self._get_connection()
        cursor = conn.cursor()

        # Load from main table
        cursor.execute(
            f'SELECT * FROM {self._definition.table_name} WHERE uuid = ?',
            (uuid,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        data = dict(row)

        # Load dynamic metadata
        dynamic = self._metadata_service.get_entity_metadata(uuid)
        data.update(dynamic)

        # Create entity instance
        return self._entity_class(data)

    def get_all(self, limit: int = None, offset: int = 0) -> List[Entity]:
        """
        Get all entities of this type.

        Args:
            limit: Maximum number to return
            offset: Number to skip

        Returns:
            List of entity instances
        """
        if not self._definition:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        query = f'SELECT * FROM {self._definition.table_name}'
        params = []

        if limit:
            query += ' LIMIT ? OFFSET ?'
            params = [limit, offset]

        cursor.execute(query, params)

        entities = []
        for row in cursor.fetchall():
            data = dict(row)
            # Load dynamic metadata for each
            uuid = data.get('uuid')
            if uuid:
                dynamic = self._metadata_service.get_entity_metadata(uuid)
                data.update(dynamic)
            entities.append(self._entity_class(data))

        return entities

    def save(self, entity: Entity) -> bool:
        """
        Save entity with automatic core/dynamic field separation.

        Core fields go to main table, dynamic fields go to EAV storage.

        Args:
            entity: Entity instance to save

        Returns:
            True if successful
        """
        if not self._definition:
            return False

        data = entity.to_dict()

        # Separate core vs dynamic fields
        core_data = {}
        dynamic_data = {}

        for key, value in data.items():
            if key in self._definition.core_fields:
                core_data[key] = value
            else:
                # Check if this is a registered dynamic field
                field_def = self._metadata_service.get_field(self._entity_type, key)
                if field_def:
                    dynamic_data[key] = value

        # Save core to main table
        success = self._save_core(entity.uuid, core_data)

        # Save dynamic to EAV
        if success and dynamic_data:
            self._metadata_service.set_entity_metadata(
                entity.uuid,
                self._entity_type,
                dynamic_data
            )

        if success:
            entity.mark_clean()

        return success

    def _save_core(self, uuid: str, data: Dict[str, Any]) -> bool:
        """
        Save core fields to main table.

        Args:
            uuid: Entity UUID
            data: Core field data

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                table = self._definition.table_name

                # Check if exists
                cursor.execute(f'SELECT 1 FROM {table} WHERE uuid = ?', (uuid,))
                exists = cursor.fetchone() is not None

                if exists:
                    # UPDATE - only update provided fields
                    if data:
                        # Filter out uuid from update data
                        update_data = {k: v for k, v in data.items() if k != 'uuid'}
                        if update_data:
                            set_clause = ', '.join([f"{k} = ?" for k in update_data.keys()])
                            values = list(update_data.values()) + [uuid]
                            cursor.execute(
                                f'UPDATE {table} SET {set_clause} WHERE uuid = ?',
                                values
                            )
                else:
                    # INSERT
                    if 'uuid' not in data:
                        data['uuid'] = uuid
                    columns = ', '.join(data.keys())
                    placeholders = ', '.join(['?' for _ in data])
                    cursor.execute(
                        f'INSERT INTO {table} ({columns}) VALUES ({placeholders})',
                        list(data.values())
                    )

                return True

        except Exception as e:
            return False

    def delete(self, uuid: str) -> bool:
        """
        Delete entity and its metadata.

        Args:
            uuid: Entity UUID to delete

        Returns:
            True if successful
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                # Delete from main table
                cursor.execute(
                    f'DELETE FROM {self._definition.table_name} WHERE uuid = ?',
                    (uuid,)
                )

                # Delete dynamic metadata
                self._metadata_service.delete_entity_metadata(uuid)

                return cursor.rowcount > 0

        except Exception as e:
            return False

    def find_by_field(
        self,
        field_name: str,
        value: Any,
        limit: int = None
    ) -> List[Entity]:
        """
        Find entities by field value.

        Works for both core and dynamic fields.

        Args:
            field_name: Field name to search
            value: Value to match
            limit: Maximum results

        Returns:
            List of matching entities
        """
        if not self._definition:
            return []

        # Check if core or dynamic field
        if field_name in self._definition.core_fields:
            return self._find_by_core_field(field_name, value, limit)
        else:
            return self._find_by_dynamic_field(field_name, value, limit)

    def _find_by_core_field(
        self,
        field_name: str,
        value: Any,
        limit: int = None
    ) -> List[Entity]:
        """Find by core field (in main table)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = f'SELECT * FROM {self._definition.table_name} WHERE {field_name} = ?'
        params = [value]

        if limit:
            query += ' LIMIT ?'
            params.append(limit)

        cursor.execute(query, params)

        entities = []
        for row in cursor.fetchall():
            data = dict(row)
            uuid = data.get('uuid')
            if uuid:
                dynamic = self._metadata_service.get_entity_metadata(uuid)
                data.update(dynamic)
            entities.append(self._entity_class(data))

        return entities

    def _find_by_dynamic_field(
        self,
        field_name: str,
        value: Any,
        limit: int = None
    ) -> List[Entity]:
        """Find by dynamic field (in EAV table)."""
        # Get UUIDs matching the dynamic field value
        uuids = self._metadata_service.get_entities_with_field_value(
            self._entity_type,
            field_name,
            value
        )

        if limit:
            uuids = uuids[:limit]

        # Load full entities
        entities = []
        for uuid in uuids:
            entity = self.get_by_uuid(uuid)
            if entity:
                entities.append(entity)

        return entities

    def count(self) -> int:
        """Get total count of entities."""
        if not self._definition:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'SELECT COUNT(*) FROM {self._definition.table_name}')
        return cursor.fetchone()[0]

    def exists(self, uuid: str) -> bool:
        """Check if entity exists."""
        if not self._definition:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f'SELECT 1 FROM {self._definition.table_name} WHERE uuid = ?',
            (uuid,)
        )
        return cursor.fetchone() is not None


def get_generic_repository(entity_type: str) -> GenericRepository:
    """
    Get a GenericRepository for the specified entity type.

    Args:
        entity_type: Entity type name

    Returns:
        GenericRepository instance
    """
    return GenericRepository(entity_type)


__all__ = ['GenericRepository', 'get_generic_repository']
