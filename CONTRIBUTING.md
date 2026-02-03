# Contributing to Universal Library

Thank you for your interest in contributing to Universal Library! This document provides guidelines for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

---

## Code of Conduct

This project follows a simple code of conduct:

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

---

## Getting Started

### Types of Contributions

We welcome:

- **Bug fixes** — Found something broken? Fix it!
- **Feature implementations** — Check the issues for requested features
- **Documentation** — Improve docs, add examples, fix typos
- **UI/UX improvements** — Better layouts, accessibility, themes
- **Performance optimizations** — Make it faster
- **Blender addon enhancements** — Better integration, new features

### Before You Start

1. Check [existing issues](https://github.com/CGstuff/Universal-Library/issues) to avoid duplicates
2. For large changes, open an issue first to discuss the approach
3. Fork the repository and create a feature branch

---

## Development Setup

### Prerequisites

- Python 3.9 or higher
- Git
- A code editor (VS Code, PyCharm, etc.)

### Setup Steps

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/Universal-Library.git
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

# Install development dependencies
pip install pytest pytest-qt black mypy

# Run the application
python run.py
```

### Project Structure Overview

```
universal_library/
├── config.py          # Configuration and constants
├── main.py            # Application entry point
├── services/          # Business logic (start here for backend changes)
├── widgets/           # UI components (start here for UI changes)
├── models/            # Qt data models
├── views/             # Custom views and delegates
├── events/            # Event bus system
└── themes/            # Theming system

UL_blender_plugin/     # Blender addon (separate project structure)
```

---

## Making Changes

### Branch Naming

Use descriptive branch names:

```
feature/add-batch-export
fix/thumbnail-loading-crash
docs/improve-getting-started
refactor/simplify-event-bus
```

### Commit Messages

Write clear, descriptive commit messages:

```
Add batch export feature for multiple assets

- Implement multi-select export dialog
- Add progress indicator for batch operations
- Update Blender addon to handle batch commands
```

**Good:**
- `Fix thumbnail cache not clearing on asset delete`
- `Add dark mode support for review dialog`
- `Improve search performance for large libraries`

**Bad:**
- `fix bug`
- `update code`
- `WIP`

### Keep Changes Focused

- One feature or fix per pull request
- Avoid mixing unrelated changes
- If you find other issues while working, create separate PRs

---

## Code Style

### Python Style

We follow PEP 8 with some adjustments:

```python
# Use type hints
def get_asset(self, uuid: str) -> Optional[Asset]:
    """
    Get asset by UUID.

    Args:
        uuid: The asset's unique identifier

    Returns:
        Asset object if found, None otherwise
    """
    return self._assets.get(uuid)

# Use descriptive names
thumbnail_cache_size_mb = 100  # Good
tcs = 100  # Bad

# Group imports
import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget

from .config import Config
from .services import get_database_service
```

### Formatting

Run Black before committing:

```bash
black universal_library/
black UL_blender_plugin/
```

### Type Checking

Run mypy to catch type errors:

```bash
mypy universal_library/
```

### Documentation

- Add docstrings to public functions and classes
- Use Google-style docstrings
- Keep inline comments minimal—prefer clear code

```python
def create_variant(self, asset_uuid: str, variant_name: str) -> str:
    """
    Create a new variant of an existing asset.

    Args:
        asset_uuid: UUID of the source asset
        variant_name: Name for the new variant (e.g., "Gold", "Damaged")

    Returns:
        UUID of the newly created variant

    Raises:
        ValueError: If variant name already exists for this asset
    """
```

---

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=universal_library

# Run specific test file
pytest tests/test_database_service.py

# Run tests matching a pattern
pytest -k "test_asset"
```

### Writing Tests

```python
import pytest
from universal_library.services import AssetRepository

class TestAssetRepository:
    @pytest.fixture
    def repo(self, tmp_path):
        """Create a test repository with temporary database."""
        db_path = tmp_path / "test.db"
        return AssetRepository(db_path)

    def test_create_asset(self, repo):
        """Test creating a new asset."""
        asset = repo.create(
            name="Test Asset",
            asset_type="mesh",
            folder_id=1
        )
        assert asset.name == "Test Asset"
        assert asset.uuid is not None

    def test_get_nonexistent_asset(self, repo):
        """Test getting an asset that doesn't exist."""
        result = repo.get_by_uuid("nonexistent-uuid")
        assert result is None
```

### Test Coverage

Aim for good coverage on:
- Service layer methods
- Repository CRUD operations
- Event bus signal emission
- Critical UI workflows

---

## Pull Request Process

### Before Submitting

1. **Test your changes** — Run the test suite
2. **Format code** — Run Black
3. **Check types** — Run mypy
4. **Update docs** — If you changed behavior, update documentation
5. **Write a clear description** — Explain what and why

### PR Template

```markdown
## Summary

Brief description of changes.

## Changes

- Added X
- Fixed Y
- Updated Z

## Testing

- [ ] Ran pytest
- [ ] Tested manually in the application
- [ ] Tested with Blender addon (if applicable)

## Screenshots

(If UI changes, include before/after screenshots)

## Related Issues

Fixes #123
```

### Review Process

1. Submit your PR
2. Maintainers will review and provide feedback
3. Address feedback with additional commits
4. Once approved, your PR will be merged

### After Merge

- Delete your feature branch
- Pull the latest main branch
- Celebrate!

---

## Reporting Issues

### Bug Reports

Include:

1. **Summary** — Brief description of the bug
2. **Steps to reproduce** — Exact steps to trigger the bug
3. **Expected behavior** — What should happen
4. **Actual behavior** — What actually happens
5. **Environment** — OS, Python version, Universal Library version
6. **Screenshots/logs** — If applicable

### Feature Requests

Include:

1. **Problem** — What problem does this solve?
2. **Proposed solution** — How should it work?
3. **Alternatives** — Other approaches considered
4. **Additional context** — Mockups, examples, related features

---

## Questions?

- Open a [GitHub Discussion](https://github.com/CGstuff/Universal-Library/discussions)
- Check existing issues and discussions first

Thank you for contributing!
