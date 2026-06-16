"""Shared pytest fixtures for folio tests."""

from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture
def sample_markdown_with_frontmatter():
    return """---
funder: "OAC"
type: "application"
written: 2024
grant_amount: "$50,538"
---

# OAC Operating Grant Application 2024

Body text here.
"""


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a minimal folio project directory structure."""
    (tmp_path / '_raw_archive').mkdir()
    (tmp_path / 'raw_md').mkdir()
    (tmp_path / 'clean_md').mkdir()
    (tmp_path / 'rewrite_md').mkdir()
    return tmp_path
