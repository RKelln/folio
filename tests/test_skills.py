"""Tests for folio skills generation — build_context, generate_skills, and template filling.

Covers:
- build_context() with minimal, full, and IA library configs
- _fill_template() placeholder substitution and warnings
- generate_skills() for all 4 platforms
- OpenCode-specific output structure
- CLI integration for `folio skills`
- End-to-end IA library skills generation
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import pytest

from folio.config.schema import (
    AgentmapConfig,
    LLMConfig,
    ProjectConfig,
    WikiConfig,
)
from tests.conftest import make_test_config

from folio.core.skills import (
    _CORE_DIR,
    _PLACEHOLDER_RE,
    _check_placeholders,
    _fill_template,
    build_context,
    generate_skills,
)

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

_DEFAULT_IA_DIR = Path(__file__).resolve().parents[2] / "ia-library"
IA_DIR = Path(os.environ.get("IA_LIBRARY_PATH", _DEFAULT_IA_DIR))
IA_CONFIG_EXISTS = IA_DIR.exists() and (IA_DIR / "folio.yaml").exists()


def _load_ia_config() -> ProjectConfig:
    from folio.config.loader import load_project_config
    return load_project_config(IA_DIR / "folio.yaml")


# ══════════════════════════════════════════════════════════════════════
# build_context()
# ══════════════════════════════════════════════════════════════════════

class TestBuildContext:
    """Context dict construction from project config."""

    @pytest.fixture
    def ctx(self):
        return build_context(make_test_config())

    def test_org_fields(self, ctx):
        assert ctx["org_name"] == "Test Organization"
        assert ctx["org_abbreviation"] == "TEST"
        assert ctx["org_slug"] == "test-organization"
        assert ctx["org_description"] == "A test organization."

    def test_paths(self, ctx):
        assert ctx["rewrite_md_path"] == "./markdown/"
        assert ctx["wiki_path"] == "./.folio/sage-wiki/"
        assert ctx["raw_archive_path"] == "./archive/"

    def test_funder_table(self, ctx):
        ft = ctx["funder_table"]
        assert "| OAC | Ontario Arts Council |" in ft
        assert "| TAC | Toronto Arts Council |" in ft

    def test_funder_abbrev_first_sorted(self, ctx):
        assert ctx["funder_abbrev"] == "OAC"

    def test_doc_type_table(self, ctx):
        dt = ctx["doc_type_table"]
        for t in ("application", "report", "budget"):
            assert f"| {t} |" in dt

    def test_wiki_disabled(self, ctx):
        assert ctx["wiki_enabled"] is False
        assert ctx["wiki_enabled_str"] == "false"

    def test_wiki_enabled(self):
        ctx = build_context(make_test_config(wiki=WikiConfig(type="sage-wiki")))
        assert ctx["wiki_enabled"] is True
        assert ctx["wiki_enabled_str"] == "true"

    def test_agentmap_disabled(self, ctx):
        assert ctx["agentmap_enabled"] == "false"

    def test_agentmap_enabled(self):
        ctx = build_context(make_test_config(agentmap=AgentmapConfig(enabled=True)))
        assert ctx["agentmap_enabled"] == "true"

    def test_tool_sections_always_has_file_search(self, ctx):
        assert "File search" in ctx["tool_sections"]

    def test_tool_sections_no_wiki_when_disabled(self, ctx):
        assert "sage-wiki (cross-document synthesis)" not in ctx["tool_sections"]

    def test_tool_sections_wiki_when_enabled(self):
        ctx = build_context(make_test_config(wiki=WikiConfig(type="sage-wiki")))
        assert "sage-wiki" in ctx["tool_sections"]

    def test_tool_sections_no_agentmap_when_disabled(self, ctx):
        assert "agentmap (section-level search)" not in ctx["tool_sections"]

    def test_tool_sections_agentmap_when_enabled(self):
        ctx = build_context(make_test_config(agentmap=AgentmapConfig(enabled=True)))
        assert "agentmap" in ctx["tool_sections"]

    def test_combined_workflow_when_both_enabled(self):
        ctx = build_context(make_test_config(
            wiki=WikiConfig(type="sage-wiki"),
            agentmap=AgentmapConfig(enabled=True),
        ))
        assert "Combined workflow" in ctx["tool_sections"]

    def test_no_combined_workflow_when_only_wiki(self):
        ctx = build_context(make_test_config(wiki=WikiConfig(type="sage-wiki")))
        assert "Combined workflow" not in ctx["tool_sections"]

    def test_funder_concept_rows(self, ctx):
        rows = ctx["funder_concept_rows"]
        assert "OAC grants" in rows
        assert "TAC grants" in rows
        assert "wiki/concepts/" in rows

    def test_empty_funders_defaults_abbrev(self):
        ctx = build_context(make_test_config(funders={}))
        assert ctx["funder_abbrev"] == "FUNDER"

    def test_agentmap_step_when_enabled(self):
        ctx = build_context(make_test_config(agentmap=AgentmapConfig(enabled=True)))
        assert "agentmap search" in ctx["agentmap_step"]

    def test_agentmap_step_when_disabled(self):
        ctx = build_context(make_test_config(agentmap=AgentmapConfig(enabled=False)))
        assert ctx["agentmap_step"] == ""

    # ── IA library integration ──

    @pytest.mark.skipif(not IA_CONFIG_EXISTS, reason="IA library not available")
    def test_ia_required_keys(self):
        ctx = build_context(_load_ia_config())
        required = [
            "org_name", "org_abbreviation", "org_slug", "org_description",
            "funder_table", "funder_rows", "doc_type_table", "doc_type_rows",
            "funder_concept_rows", "funder_abbrev",
            "rewrite_md_path", "wiki_path", "raw_archive_path",
            "agentmap_enabled", "agentmap_binary",
            "wiki_enabled", "wiki_enabled_str",
            "tool_sections", "agentmap_step", "api_key_env",
        ]
        for key in required:
            assert key in ctx, f"Missing key: {key}"

    @pytest.mark.skipif(not IA_CONFIG_EXISTS, reason="IA library not available")
    def test_ia_org_identity(self):
        ctx = build_context(_load_ia_config())
        assert ctx["org_name"] == "InterAccess"
        assert ctx["org_abbreviation"] == "IA"
        assert ctx["org_slug"] == "interaccess"

    @pytest.mark.skipif(not IA_CONFIG_EXISTS, reason="IA library not available")
    def test_ia_five_funders(self):
        ctx = build_context(_load_ia_config())
        ft = ctx["funder_table"]
        for abbr in ("CCA", "OAC", "TAC", "BCAH"):
            assert abbr in ft

    @pytest.mark.skipif(not IA_CONFIG_EXISTS, reason="IA library not available")
    def test_ia_paths_are_local(self):
        ctx = build_context(_load_ia_config())
        assert "markdown" in ctx["rewrite_md_path"]
        assert "sage-wiki" in ctx["wiki_path"]

    @pytest.mark.skipif(not IA_CONFIG_EXISTS, reason="IA library not available")
    def test_ia_wiki_and_agentmap_enabled(self):
        ctx = build_context(_load_ia_config())
        assert ctx["wiki_enabled"] is True
        assert ctx["agentmap_enabled"] == "true"

    @pytest.mark.skipif(not IA_CONFIG_EXISTS, reason="IA library not available")
    def test_ia_all_tool_sections_present(self):
        ctx = build_context(_load_ia_config())
        sections = ctx["tool_sections"]
        assert "File search" in sections
        assert "sage-wiki" in sections
        assert "agentmap" in sections
        assert "Combined workflow" in sections


# ══════════════════════════════════════════════════════════════════════
# _fill_template()
# ══════════════════════════════════════════════════════════════════════

class TestFillTemplate:
    """Placeholder substitution in skill templates."""

    def test_fills_known(self, tmp_path):
        tmpl = tmp_path / "test.md"
        tmpl.write_text("Hello {name}, welcome to {org}!")
        result = _fill_template(tmpl, {"name": "Alice", "org": "folio"})
        assert result == "Hello Alice, welcome to folio!"

    def test_leaves_unknown_placeholders(self, tmp_path, caplog):
        tmpl = tmp_path / "test.md"
        tmpl.write_text("Missing: {missing_key}")
        with caplog.at_level(logging.WARNING):
            result = _fill_template(tmpl, {})
        assert "{missing_key}" in result
        assert "Unfilled placeholders" in caplog.text
        assert "missing_key" in caplog.text

    def test_preserves_json_braces(self, tmp_path):
        tmpl = tmp_path / "test.md"
        tmpl.write_text('JSON: {"key": "{value}"} env {VAR}')
        result = _fill_template(tmpl, {"value": "actual", "VAR": "env_val"})
        assert 'JSON: {"key": "actual"} env env_val' in result

    def test_empty_context_warns(self, tmp_path, caplog):
        tmpl = tmp_path / "test.md"
        tmpl.write_text("{a} {b} {c}")
        with caplog.at_level(logging.WARNING):
            result = _fill_template(tmpl, {})
        assert result == "{a} {b} {c}"
        assert "Unfilled placeholders" in caplog.text

    def test_all_core_templates_fill_clean(self, caplog, tmp_path):
        """Every core template must fill all placeholders against a full config."""
        ctx = build_context(make_test_config(
            wiki=WikiConfig(type="sage-wiki"),
            agentmap=AgentmapConfig(enabled=True),
        ))
        with caplog.at_level(logging.WARNING):
            for md in sorted(_CORE_DIR.glob("*.md")):
                result = _fill_template(md, ctx)
                unfilled = set(_PLACEHOLDER_RE.findall(result))
                assert not unfilled, (
                    f"{md.name} has unfilled placeholders: {unfilled}"
                )


# ══════════════════════════════════════════════════════════════════════
# generate_skills()
# ══════════════════════════════════════════════════════════════════════

class TestGenerateSkills:
    """Platform dispatch and output structure."""

    @pytest.fixture
    def cfg(self):
        return make_test_config()

    def test_unknown_platform_raises(self, cfg):
        with pytest.raises(ValueError, match="Unknown platform"):
            generate_skills(cfg, "mythical")

    def test_opencode_writes_one_file(self, cfg, tmp_path):
        result = generate_skills(cfg, "opencode", tmp_path)
        assert len(result["files_written"]) == 1
        assert result["warnings"] == []
        file_path = result["files_written"][0]
        assert file_path.exists()
        assert file_path.name == "SKILL.md"

    def test_opencode_correct_path(self, cfg, tmp_path):
        result = generate_skills(cfg, "opencode", tmp_path)
        path = result["files_written"][0]
        parts = path.relative_to(tmp_path).parts
        assert parts == (".opencode", "skills", "grant-writing", "SKILL.md")

    def test_claude_writes_two_files(self, cfg, tmp_path):
        result = generate_skills(cfg, "claude", tmp_path)
        assert len(result["files_written"]) == 2

    def test_claude_file_names(self, cfg, tmp_path):
        result = generate_skills(cfg, "claude", tmp_path)
        names = {p.name for p in result["files_written"]}
        assert names == {"grant-search.md", "grant-draft.md"}

    def test_claude_search_prefix(self, cfg, tmp_path):
        result = generate_skills(cfg, "claude", tmp_path)
        search = [p for p in result["files_written"] if p.name == "grant-search.md"][0]
        assert search.read_text().startswith("# /grant-search")

    def test_claude_draft_prefix(self, cfg, tmp_path):
        result = generate_skills(cfg, "claude", tmp_path)
        draft = [p for p in result["files_written"] if p.name == "grant-draft.md"][0]
        assert draft.read_text().startswith("# /grant-draft")

    def test_openclaw_writes_two_files(self, cfg, tmp_path):
        result = generate_skills(cfg, "openclaw", tmp_path)
        assert len(result["files_written"]) == 2

    def test_openclaw_file_names(self, cfg, tmp_path):
        result = generate_skills(cfg, "openclaw", tmp_path)
        names = {p.name for p in result["files_written"]}
        assert names == {"system-prompt.md", "tools.yaml"}

    def test_hermes_writes_one_file(self, cfg, tmp_path):
        result = generate_skills(cfg, "hermes", tmp_path)
        assert len(result["files_written"]) == 1
        assert result["files_written"][0].name == "SKILL.md"

    def test_hermes_content_structure(self, cfg, tmp_path):
        result = generate_skills(cfg, "hermes", tmp_path)
        content = result["files_written"][0].read_text()
        assert content.startswith("---")
        assert "name: grant-writing" in content
        assert "description:" in content
        assert "Archive Search" in content
        assert "Grant Drafting" in content
        assert "Grant Writing Craft" in content

    def test_hermes_no_unfilled_placeholders(self, tmp_path):
        cfg = make_test_config(
            wiki=WikiConfig(type="sage-wiki"),
            agentmap=AgentmapConfig(enabled=True),
        )
        result = generate_skills(cfg, "hermes", tmp_path)
        content = result["files_written"][0].read_text()
        braces = [b for b in re.findall(r"\{[a-z_]+\}", content)
                  if re.match(r"^\{[a-z_]+[a-z]\}$", b)]
        assert not braces, f"Unfilled placeholders: {braces}"

    def test_hermes_correct_path(self, cfg, tmp_path):
        result = generate_skills(cfg, "hermes", tmp_path)
        path = result["files_written"][0]
        parts = path.relative_to(tmp_path).parts
        assert parts == ("hermes", "skills", "grant-writing", "SKILL.md")


# ══════════════════════════════════════════════════════════════════════
# _check_placeholders()
# ══════════════════════════════════════════════════════════════════════

class TestCheckPlaceholders:
    """Warning collection for unfilled template placeholders."""

    def test_no_warnings_when_clean(self):
        warnings: list[str] = []
        _check_placeholders("Hello world", "test.md", warnings)
        assert warnings == []

    def test_single_unfilled_placeholder(self):
        warnings: list[str] = []
        _check_placeholders("Hello {name}, welcome!", "test.md", warnings)
        assert len(warnings) == 1
        assert "test.md" in warnings[0]
        assert "name" in warnings[0]

    def test_multiple_unfilled_placeholders(self):
        warnings: list[str] = []
        _check_placeholders("Hello {name}, the {org} is at {place}.", "out/test.md", warnings)
        assert len(warnings) == 1
        msg = warnings[0]
        assert "name" in msg
        assert "org" in msg
        assert "place" in msg

    def test_deduplicates_same_placeholder(self):
        warnings: list[str] = []
        _check_placeholders("{x} {x} {x}", "file.md", warnings)
        assert len(warnings) == 1
        assert warnings[0].count("x") == 1  # deduplicated

    def test_matches_underscore_keys(self):
        warnings: list[str] = []
        _check_placeholders("Unfilled: {some_key} {another_key}", "file.md", warnings)
        assert len(warnings) == 1
        assert "some_key" in warnings[0]
        assert "another_key" in warnings[0]


# ══════════════════════════════════════════════════════════════════════
# OpenCode output quality
# ══════════════════════════════════════════════════════════════════════

class TestOpenCodeGeneration:
    """OpenCode SKILL.md content and structure."""

    @pytest.fixture
    def cfg(self):
        return make_test_config(
            wiki=WikiConfig(type="sage-wiki"),
            agentmap=AgentmapConfig(enabled=True),
        )

    @pytest.fixture
    def skill_content(self, cfg, tmp_path):
        result = generate_skills(cfg, "opencode", tmp_path)
        return result["files_written"][0].read_text()

    def test_starts_with_yaml_frontmatter(self, skill_content):
        assert skill_content.startswith("---")

    def test_frontmatter_fields(self, skill_content):
        assert "name: grant-writing" in skill_content
        assert "compatibility: opencode" in skill_content

    def test_description_mentions_org(self, skill_content):
        assert "Test Organization" in skill_content

    def test_description_has_repository(self, skill_content):
        assert "repository: Test Project" in skill_content

    def test_includes_all_three_layers(self, skill_content):
        assert "Archive Search" in skill_content
        assert "Grant Drafting" in skill_content
        assert "Grant Writing Craft" in skill_content

    def test_funder_table_rendered(self, skill_content):
        assert "Ontario Arts Council" in skill_content
        assert "Toronto Arts Council" in skill_content

    def test_no_raw_placeholder_braces(self, skill_content):
        braces = [b for b in re.findall(r"\{[a-z_]+\}", skill_content)
                  if re.match(r"^\{[a-z_]+[a-z]\}$", b)]
        assert not braces, f"Unfilled placeholders: {braces}"

    def test_wiki_tool_present(self, skill_content):
        assert "sage-wiki" in skill_content

    def test_agentmap_tool_present(self, skill_content):
        assert "agentmap" in skill_content

    def test_combined_workflow_present(self, skill_content):
        assert "Combined workflow" in skill_content

    def test_paths_resolved_not_raw(self, skill_content):
        assert "{rewrite_md_path}" not in skill_content
        assert "{wiki_path}" not in skill_content
        assert "{funder_table}" not in skill_content

    def test_wiki_disabled_hides_sage_wiki(self, tmp_path):
        cfg = make_test_config(wiki=WikiConfig(type="null"))
        result = generate_skills(cfg, "opencode", tmp_path)
        content = result["files_written"][0].read_text()
        # The _tool-sage-wiki section should not appear, but the librarian
        # template may mention sage-wiki in general context
        assert "### sage-wiki (cross-document synthesis)" not in content

    def test_agentmap_disabled_hides_agentmap(self, tmp_path):
        cfg = make_test_config(agentmap=AgentmapConfig(enabled=False))
        result = generate_skills(cfg, "opencode", tmp_path)
        content = result["files_written"][0].read_text()
        # The _tool-agentmap section should not appear, but the headings.yaml
        # reference may mention agentmap in passing
        assert "### agentmap (section-level search)" not in content


# ══════════════════════════════════════════════════════════════════════
# CLI integration
# ══════════════════════════════════════════════════════════════════════

class TestSkillsCLI:
    """`folio skills` CLI behavior beyond smoke tests."""

    def test_dry_run_output(self, capsys):
        from folio.cli.skills import main
        main(["--platform", "opencode", "--dry-run"])
        captured = capsys.readouterr()
        assert "Would generate" in captured.out

    def test_dry_run_json_keys(self, capsys):
        from folio.cli.skills import main
        main(["--platform", "opencode", "--dry-run", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["dry_run"] is True
        assert "keys" in data or "context_keys" in data

    def test_generate_json_output(self, tmp_path, capsys):
        from folio.cli.skills import main
        # Need a config file for skills CLI
        config_path = tmp_path / "folio.yaml"
        config_path.write_text("""\
project:
  name: Test
org:
  name: Test Org
  abbreviation: TO
paths:
  raw_archive: ./archive/
  raw_md: ./.folio/converted/
  clean_md: ./.folio/cleaned/
  rewrite_md: ./markdown/
  wiki_project: ./.folio/sage-wiki/
funders:
  TAC: Toronto Arts Council
doc_types:
  - application
llm:
  provider: openai_compatible
  base_url: https://api.example.com
  models:
    fast: fast
    quality: pro
  pricing:
    input_per_million: 0.14
    output_per_million: 0.28
converter:
  type: marker
wiki:
  type: "null"
""")
        main(["--platform", "opencode", "--json", "--output", str(tmp_path),
              "--config", str(config_path)])
        data = json.loads(capsys.readouterr().out)
        assert "files_written" in data
        assert "warnings" in data

    def test_writes_skill_file(self, tmp_path):
        from folio.cli.skills import main
        config_path = tmp_path / "folio.yaml"
        config_path.write_text("""\
project:
  name: Test
org:
  name: Test Org
  abbreviation: TO
paths:
  raw_archive: ./archive/
  raw_md: ./.folio/converted/
  clean_md: ./.folio/cleaned/
  rewrite_md: ./markdown/
  wiki_project: ./.folio/sage-wiki/
funders:
  TAC: Toronto Arts Council
doc_types:
  - application
llm:
  provider: openai_compatible
  base_url: https://api.example.com
  models:
    fast: fast
    quality: pro
  pricing:
    input_per_million: 0.14
    output_per_million: 0.28
converter:
  type: marker
wiki:
  type: "null"
""")
        main(["--platform", "opencode", "--output", str(tmp_path),
              "--config", str(config_path)])
        skill = tmp_path / ".opencode" / "skills" / "grant-writing" / "SKILL.md"
        assert skill.exists()

    def test_with_minimal_config_file(self, tmp_path):
        config_path = tmp_path / "folio.yaml"
        config_path.write_text("""\
project:
  name: My Project
org:
  name: My Org
  abbreviation: MO
paths:
  raw_archive: ./archive/
  raw_md: ./.folio/converted/
  clean_md: ./.folio/cleaned/
  rewrite_md: ./markdown/
  wiki_project: ./.folio/sage-wiki/
funders:
  TAC: Toronto Arts Council
doc_types:
  - application
llm:
  provider: openai_compatible
  base_url: https://api.example.com
  models:
    fast: test-fast
    quality: test-pro
  pricing:
    input_per_million: 0.14
    output_per_million: 0.28
converter:
  type: marker
wiki:
  type: "null"
""")
        from folio.cli.skills import main
        output_dir = tmp_path / "out"
        main(["--platform", "opencode", "--output", str(output_dir),
              "--config", str(config_path)])
        skill = output_dir / ".opencode" / "skills" / "grant-writing" / "SKILL.md"
        assert skill.exists()
        content = skill.read_text()
        assert "My Org" in content

    def test_unknown_platform_exits_1(self, capsys):
        from folio.cli.skills import main
        with pytest.raises(SystemExit) as exc:
            main(["--platform", "mythical"])
        assert exc.value.code in (1, 2)  # argparse may exit 2 for invalid choice

    def test_claude_writes_two_files(self, tmp_path):
        from folio.cli.skills import main
        config_path = tmp_path / "folio.yaml"
        config_path.write_text("""\
project:
  name: Test
org:
  name: Test Org
  abbreviation: TO
paths:
  raw_archive: ./archive/
  raw_md: ./.folio/converted/
  clean_md: ./.folio/cleaned/
  rewrite_md: ./markdown/
  wiki_project: ./.folio/sage-wiki/
funders:
  TAC: Toronto Arts Council
doc_types:
  - application
llm:
  provider: openai_compatible
  base_url: https://api.example.com
  models:
    fast: fast
    quality: pro
  pricing:
    input_per_million: 0.14
    output_per_million: 0.28
converter:
  type: marker
wiki:
  type: "null"
""")
        main(["--platform", "claude", "--output", str(tmp_path),
              "--config", str(config_path)])
        assert (tmp_path / ".claude" / "commands" / "grant-search.md").exists()
        assert (tmp_path / ".claude" / "commands" / "grant-draft.md").exists()

    @pytest.mark.parametrize("platform", ["opencode", "claude", "openclaw", "hermes"])
    def test_all_platforms_run_without_error(self, platform, tmp_path):
        from folio.cli.skills import main
        config_path = tmp_path / "folio.yaml"
        config_path.write_text("""\
project:
  name: Test
org:
  name: Test Org
  abbreviation: TO
paths:
  raw_archive: ./archive/
  raw_md: ./.folio/converted/
  clean_md: ./.folio/cleaned/
  rewrite_md: ./markdown/
  wiki_project: ./.folio/sage-wiki/
funders:
  TAC: Toronto Arts Council
doc_types:
  - application
llm:
  provider: openai_compatible
  base_url: https://api.example.com
  models:
    fast: fast
    quality: pro
  pricing:
    input_per_million: 0.14
    output_per_million: 0.28
converter:
  type: marker
wiki:
  type: "null"
""")
        main(["--platform", platform, "--output", str(tmp_path),
              "--config", str(config_path)])


# ══════════════════════════════════════════════════════════════════════
# IA library end-to-end
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not IA_CONFIG_EXISTS, reason="IA library not available")
class TestIALibrarySkills:
    """End-to-end skills generation from the real InterAccess library."""

    def test_opencode_from_ia_config(self, tmp_path):
        result = generate_skills(_load_ia_config(), "opencode", tmp_path)
        content = result["files_written"][0].read_text()

        assert content.startswith("---")
        assert "name: grant-writing" in content
        assert "compatibility: opencode" in content

        assert "InterAccess" in content
        assert "IA" in content

        for funder in ("Ontario Arts Council", "Toronto Arts Council",
                       "Canada Council for the Arts", "Canadian Heritage"):
            assert funder in content

        for layer in ("Archive Search", "Grant Drafting", "Grant Writing Craft"):
            assert layer in content

        for tool in ("File search", "sage-wiki", "agentmap", "Combined workflow"):
            assert tool in content

        assert "markdown" in content
        assert "sage-wiki" in content

    def test_no_unfilled_placeholders(self, tmp_path):
        result = generate_skills(_load_ia_config(), "opencode", tmp_path)
        content = result["files_written"][0].read_text()
        braces = [b for b in re.findall(r"\{[a-z_]+\}", content)
                  if re.match(r"^\{[a-z_]+[a-z]\}$", b)]
        assert not braces, f"Unfilled placeholders: {braces}"

    def test_claude_from_ia_config(self, tmp_path):
        result = generate_skills(_load_ia_config(), "claude", tmp_path)
        assert len(result["files_written"]) == 2

        search = [p for p in result["files_written"] if p.name == "grant-search.md"][0]
        draft = [p for p in result["files_written"] if p.name == "grant-draft.md"][0]

        assert search.read_text().startswith("# /grant-search")
        assert draft.read_text().startswith("# /grant-draft")
        assert "InterAccess" in search.read_text()
        assert "InterAccess" in draft.read_text()

    def test_openclaw_from_ia_config(self, tmp_path):
        result = generate_skills(_load_ia_config(), "openclaw", tmp_path)
        assert len(result["files_written"]) == 2
        assert {p.name for p in result["files_written"]} == {"system-prompt.md", "tools.yaml"}

    def test_hermes_from_ia_config(self, tmp_path):
        result = generate_skills(_load_ia_config(), "hermes", tmp_path)
        content = result["files_written"][0].read_text()
        assert content.startswith("---")
        assert "name: grant-writing" in content
        assert "description:" in content
        assert "license: MIT" in content
        assert "InterAccess" in content
        assert "sage-wiki" in content
        assert "agentmap" in content
        assert "Archive Search" in content
        assert "Grant Drafting" in content
        assert "Grant Writing Craft" in content

    def test_generate_to_ia_library_in_place(self):
        """Generate opencode skills directly into the IA library directory."""
        from folio.cli.skills import main
        import shutil

        output_dir = IA_DIR / "test_output_opencode"
        output_dir.mkdir(exist_ok=True)
        try:
            main(["--platform", "opencode", "--output", str(output_dir),
                  "--config", str(IA_DIR / "folio.yaml")])
            skill = (output_dir / ".opencode" / "skills"
                     / "grant-writing" / "SKILL.md")
            assert skill.exists()
            content = skill.read_text()
            assert "InterAccess" in content
            assert "Archive Search" in content
        finally:
            shutil.rmtree(output_dir)


# ══════════════════════════════════════════════════════════════════════
# Cross-platform consistency
# ══════════════════════════════════════════════════════════════════════

class TestCrossPlatformConsistency:
    """All platforms should produce valid output for the same config."""

    @pytest.fixture
    def full_cfg(self):
        return make_test_config(
            wiki=WikiConfig(type="sage-wiki"),
            agentmap=AgentmapConfig(enabled=True),
        )

    def test_all_platforms_fill_org_name(self, full_cfg, tmp_path):
        for platform in ("opencode", "claude", "openclaw", "hermes"):
            result = generate_skills(full_cfg, platform, tmp_path / platform)
            all_text = " ".join(p.read_text() for p in result["files_written"])
            assert "Test Organization" in all_text, (
                f"Org name not found in {platform} output"
            )

    @pytest.mark.skipif(not IA_CONFIG_EXISTS, reason="IA library not available")
    def test_all_platforms_from_ia_config(self, tmp_path):
        config = _load_ia_config()
        for platform in ("opencode", "claude", "openclaw", "hermes"):
            out = tmp_path / platform
            result = generate_skills(config, platform, out)
            assert len(result["files_written"]) >= 1, (
                f"{platform} generated no files"
            )
            for fp in result["files_written"]:
                assert fp.exists()
                assert fp.stat().st_size > 0, f"{fp} is empty"

    def test_all_platforms_warnings_empty_with_full_config(self, tmp_path):
        cfg = make_test_config(
            wiki=WikiConfig(type="sage-wiki"),
            agentmap=AgentmapConfig(enabled=True),
        )
        for platform in ("opencode", "claude", "openclaw", "hermes"):
            out = tmp_path / platform
            result = generate_skills(cfg, platform, out)
            assert result["warnings"] == [], (
                f"{platform} has unexpected warnings: {result['warnings']}"
            )
