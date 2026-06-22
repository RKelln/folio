"""Shared test fixtures for the folio test suite."""
from __future__ import annotations

import pytest

from folio.config.schema import (
    AgentmapConfig,
    LLMConfig,
    OrgConfig,
    PathsConfig,
    ProjectConfig,
    WikiConfig,
)

MINIMAL_FOLIO_YAML = """\
project:
  name: Test Project
org:
  name: Test Org
  abbreviation: TEST
paths:
  raw_archive: ./archive/
  raw_md: ./.folio/raw_md/
  clean_md: ./.folio/clean_md/
  rewrite_md: ./markdown/
  wiki_project: ./wiki/
funders:
  TAC: Toronto Arts Council
doc_types:
  - application
  - report
llm:
  provider: openai_compatible
  models:
    fast: test-model-fast
    quality: test-model-pro
  base_url: https://api.example.com
  pricing:
    input_per_million: 0.14
    output_per_million: 0.28
converter:
  type: marker
wiki:
  type: "null"
"""


@pytest.fixture
def minimal_folio_yaml(tmp_path):
    """Write a minimal folio.yaml to tmp_path and return the tmp_path."""
    config = tmp_path / "folio.yaml"
    config.write_text(MINIMAL_FOLIO_YAML)
    return tmp_path


@pytest.fixture
def sample_markdown_with_frontmatter() -> str:
    """A markdown document with a YAML frontmatter block, for parser tests."""
    return (
        "---\n"
        "funder: OAC\n"
        "type: application\n"
        "written: 2024\n"
        "---\n\n"
        "# OAC Operating Grant Application 2024\n\n"
        "Body content for the sample application.\n"
    )


def make_test_config(**overrides) -> ProjectConfig:
    """Build a minimal ProjectConfig with optional overrides."""
    defaults = {
        "project_name": "Test Project",
        "org": OrgConfig(
            name="Test Organization",
            abbreviation="TEST",
            description="A test organization.",
        ),
        "funders": {"OAC": "Ontario Arts Council", "TAC": "Toronto Arts Council"},
        "doc_types": ["application", "report", "budget"],
        "paths": PathsConfig(
            raw_archive="./archive/",
            rewrite_md="./markdown/",
            wiki_project="./.folio/sage-wiki/",
        ),
        "wiki": WikiConfig(type="null"),
        "agentmap": AgentmapConfig(enabled=False, binary_path="agentmap"),
        "llm": LLMConfig(),
    }
    defaults.update(overrides)
    return ProjectConfig(**defaults)
