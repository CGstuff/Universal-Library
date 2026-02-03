"""
Naming Utilities - Auto-naming and validation for assets

Pattern: Studio naming conventions with configurable patterns
"""

import re
from typing import Optional, Dict, List
from dataclasses import dataclass


@dataclass
class NamingPattern:
    """Naming pattern configuration"""
    pattern: str
    description: str
    example: str


# Default naming patterns per asset type
DEFAULT_PATTERNS: Dict[str, NamingPattern] = {
    'model': NamingPattern(
        pattern="{PREFIX}_{name}",
        description="Pattern for model assets",
        example="MDL_TreeOak"
    ),
    'rig': NamingPattern(
        pattern="{PREFIX}_{name}",
        description="Pattern for rigged assets",
        example="RIG_CharacterHero"
    ),
    'material': NamingPattern(
        pattern="{PREFIX}_{name}",
        description="Pattern for materials",
        example="MAT_WoodPlanks"
    ),
    'prop': NamingPattern(
        pattern="{PREFIX}_{name}",
        description="Pattern for props",
        example="PRP_Chair"
    ),
    'character': NamingPattern(
        pattern="{PREFIX}_{name}",
        description="Pattern for characters",
        example="CHR_Warrior"
    ),
}

# Default prefixes per asset type
DEFAULT_PREFIXES: Dict[str, str] = {
    'model': 'MDL',
    'rig': 'RIG',
    'material': 'MAT',
    'prop': 'PRP',
    'character': 'CHR',
}


class AssetNamer:
    """
    Asset naming utility with configurable patterns

    Features:
    - Auto-generate names from Blender objects
    - Validate names against patterns
    - Suggest fixes for invalid names
    - Support for studio naming conventions

    Usage:
        namer = AssetNamer()
        name = namer.generate_name("TreeOak", "model")
        # Returns "MDL_TreeOak"

        is_valid, message = namer.validate_name("MDL_TreeOak", "model")
        # Returns (True, "")
    """

    def __init__(self, prefixes: Optional[Dict[str, str]] = None):
        """
        Initialize namer with optional custom prefixes

        Args:
            prefixes: Dict mapping asset_type to prefix (e.g., {'model': 'MDL'})
        """
        self._prefixes = prefixes or DEFAULT_PREFIXES.copy()

    def set_prefix(self, asset_type: str, prefix: str):
        """Set prefix for an asset type"""
        self._prefixes[asset_type] = prefix

    def get_prefix(self, asset_type: str) -> str:
        """Get prefix for an asset type"""
        return self._prefixes.get(asset_type, 'AST')

    def generate_name(self, base_name: str, asset_type: str,
                      use_prefix: bool = True) -> str:
        """
        Generate asset name from base name

        Args:
            base_name: The base name (e.g., object name, material name)
            asset_type: Type of asset (model, rig, material, etc.)
            use_prefix: Whether to add the type prefix

        Returns:
            Generated asset name
        """
        # Clean the base name
        clean_name = self._clean_name(base_name)

        if not use_prefix:
            return clean_name

        # Get prefix for asset type
        prefix = self.get_prefix(asset_type)

        # Check if name already has this prefix
        if clean_name.upper().startswith(f"{prefix}_"):
            return clean_name

        return f"{prefix}_{clean_name}"

    def generate_from_objects(self, objects: list, asset_type: str,
                               use_prefix: bool = True) -> str:
        """
        Generate asset name from Blender objects

        Args:
            objects: List of Blender objects
            asset_type: Type of asset
            use_prefix: Whether to add the type prefix

        Returns:
            Generated asset name
        """
        if not objects:
            return self.generate_name("Untitled", asset_type, use_prefix)

        if len(objects) == 1:
            # Single object: use its name
            base_name = objects[0].name
        else:
            # Multiple objects: try to find common parent or root
            base_name = self._find_common_name(objects)
            if not base_name:
                # Fallback to first object or count
                base_name = f"{objects[0].name}_group"

        return self.generate_name(base_name, asset_type, use_prefix)

    def validate_name(self, name: str, asset_type: str) -> tuple:
        """
        Validate asset name against naming conventions

        Args:
            name: Name to validate
            asset_type: Type of asset

        Returns:
            Tuple of (is_valid: bool, message: str)
        """
        if not name:
            return False, "Name cannot be empty"

        # Check for invalid characters
        if not re.match(r'^[a-zA-Z0-9_]+$', name):
            return False, "Name should only contain letters, numbers, and underscores"

        # Check for leading numbers
        if name[0].isdigit():
            return False, "Name should not start with a number"

        # Check prefix
        prefix = self.get_prefix(asset_type)
        expected_prefix = f"{prefix}_"

        if not name.upper().startswith(expected_prefix.upper()):
            return False, f"Name should start with '{expected_prefix}' for {asset_type} assets"

        # Check minimum length after prefix
        name_part = name[len(expected_prefix):]
        if len(name_part) < 2:
            return False, "Name part after prefix should be at least 2 characters"

        return True, ""

    def suggest_fix(self, name: str, asset_type: str) -> str:
        """
        Suggest a fixed name if invalid

        Args:
            name: Original name
            asset_type: Type of asset

        Returns:
            Suggested valid name
        """
        # Clean the name first
        clean = self._clean_name(name)

        # Remove any existing prefix that doesn't match
        for prefix in self._prefixes.values():
            if clean.upper().startswith(f"{prefix}_"):
                clean = clean[len(prefix) + 1:]
                break

        # Generate new name with correct prefix
        return self.generate_name(clean, asset_type, use_prefix=True)

    def _clean_name(self, name: str) -> str:
        """
        Clean a name for use as asset name

        Args:
            name: Raw name (e.g., from Blender object)

        Returns:
            Cleaned name suitable for asset naming
        """
        if not name:
            return "Untitled"

        # Remove Blender's numeric suffix (e.g., ".001")
        name = re.sub(r'\.\d+$', '', name)

        # Replace spaces and hyphens with underscores
        name = re.sub(r'[\s\-]+', '_', name)

        # Remove invalid characters (keep alphanumeric and underscore)
        name = re.sub(r'[^a-zA-Z0-9_]', '', name)

        # Remove leading/trailing underscores
        name = name.strip('_')

        # Remove consecutive underscores
        name = re.sub(r'_+', '_', name)

        # Handle leading numbers
        if name and name[0].isdigit():
            name = 'N' + name

        # Convert to PascalCase for the name part
        parts = name.split('_')
        pascal_parts = []
        for part in parts:
            if part:
                # Only capitalize if not all uppercase (preserve acronyms)
                if part.isupper() and len(part) <= 4:
                    pascal_parts.append(part)
                else:
                    pascal_parts.append(part.capitalize())

        name = ''.join(pascal_parts) if pascal_parts else "Untitled"

        return name

    def _find_common_name(self, objects: list) -> Optional[str]:
        """
        Find a common name among multiple objects

        Args:
            objects: List of Blender objects

        Returns:
            Common name or None
        """
        if not objects:
            return None

        # Try to find a common parent
        parents = set()
        for obj in objects:
            if obj.parent:
                parents.add(obj.parent.name)

        if len(parents) == 1:
            return list(parents)[0]

        # Try to find common prefix in names
        names = [obj.name for obj in objects]
        if not names:
            return None

        # Find common prefix
        prefix = names[0]
        for name in names[1:]:
            while not name.startswith(prefix) and prefix:
                prefix = prefix[:-1]

        # Clean up prefix (remove trailing numbers, underscores, dots)
        prefix = re.sub(r'[._\d]+$', '', prefix)

        if len(prefix) >= 3:
            return prefix

        return None


# Global instance
_asset_namer: Optional[AssetNamer] = None


def get_asset_namer() -> AssetNamer:
    """Get global AssetNamer instance"""
    global _asset_namer
    if _asset_namer is None:
        _asset_namer = AssetNamer()
    return _asset_namer


def set_custom_prefixes(prefixes: Dict[str, str]):
    """Set custom prefixes for the global namer"""
    global _asset_namer
    _asset_namer = AssetNamer(prefixes)


__all__ = [
    'AssetNamer',
    'NamingPattern',
    'DEFAULT_PATTERNS',
    'DEFAULT_PREFIXES',
    'get_asset_namer',
    'set_custom_prefixes'
]
