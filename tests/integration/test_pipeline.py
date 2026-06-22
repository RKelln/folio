from __future__ import annotations

import json
from pathlib import Path

import pytest

from folio.adapters.converters.base import Converter
from folio.core.classifier import DEFAULT_CLASSIFY_CONFIG, classify_file
from folio.core.cleaner import clean_file
from folio.core.frontmatter import (
    parse_frontmatter,
    sanitize_frontmatter,
    strip_existing_frontmatter,
    update_frontmatter,
)
from folio.core.manifest import (
    create_manifest,
    get_file,
    load_manifest,
    recalculate_summary,
    save_manifest,
    update_file,
)
from folio.core.pipeline import AVAILABLE_STAGES

_RICH_MD = "# Annual Report 2023\n" + "\n".join(
    f"In fiscal year segment {i}, the organization delivered programming "
    f"to artists and audiences across the region."
    for i in range(20)
)
_SPARSE_MD = "# Title\nA single short paragraph of content."


class _StubConverter(Converter):
    """Minimal in-memory converter for pipeline tests.

    Relies on the base ``convert_traced`` so a non-cascade run reports
    ``tier == name`` and ``cost_usd == estimate_cost()``.
    """

    def __init__(self, name: str, markdown: str | None, cost: float):
        self._name = name
        self._markdown = markdown
        self._cost = cost

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_extensions(self) -> set[str]:
        return {".pdf"}

    def convert(self, source):
        return self._markdown

    def estimate_cost(self, source) -> float:
        return self._cost


class TestPipelineStageList:
    def test_available_stages_contains_expected(self):
        expected = {"scan", "convert", "clean", "canonicalize", "classify",
                     "rewrite", "prioritize", "wiki"}
        assert set(AVAILABLE_STAGES) == expected

    def test_available_stages_are_ordered(self):
        assert AVAILABLE_STAGES == [
            "scan", "convert", "clean", "canonicalize", "classify",
            "rewrite", "prioritize", "wiki",
        ]


class TestCleanFrontmatterPipeline:
    DIRTY_MD = """   \t\t
---
written: "2024"
funder: "OAC"
type: "application"
grant_amount: "$50,538"
period: 2024-2026
---

# To enter the application please fill in the form

**Project Description**

This is the body text with some bad   \t   whitespace.

<!-- image -->

![Image](data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==)

Some more   text with   extra spaces.

&#169; copyright symbol.

# FOR OFFICE USE ONLY   \t

Final section text here.

   \t
"""

    def test_clean_then_frontmatter_deterministic(self, tmp_path):
        source_file = tmp_path / "source.md"
        source_file.write_text(self.DIRTY_MD)

        source_dir = tmp_path / "raw_md"
        source_dir.mkdir()
        (source_dir / "dirty.md").write_text(self.DIRTY_MD)

        dest_dir = tmp_path / "clean_md"
        dest_dir.mkdir()

        clean_file(source_dir, dest_dir)

        cleaned_files = list(dest_dir.glob("*.md"))
        assert len(cleaned_files) == 1

        cleaned_text = cleaned_files[0].read_text()

        assert "base64" not in cleaned_text
        assert "![Image](data:image" not in cleaned_text
        assert "<!-- image -->" not in cleaned_text

        assert "# FOR OFFICE USE ONLY" not in cleaned_text
        assert "To enter the application" not in cleaned_text
        assert "fill in the form" not in cleaned_text

        assert "\t" not in cleaned_text
        assert "bad   whitespace" not in cleaned_text
        assert "  \t" not in cleaned_text

        fm, body = parse_frontmatter(cleaned_text)
        assert fm is not None
        assert fm.get("funder") == "OAC"
        assert fm.get("written") == "2024"
        assert fm.get("type") == "application"

        assert "Project Description" in cleaned_text
        assert "### Project Description" in cleaned_text

        assert cleaned_text.endswith("\n")

    def test_sanitize_frontmatter_preserves_canonical(self):
        input_text = """---
funder: "OAC"
written: 2024
type: "application"
---

Body text here.
"""
        result = sanitize_frontmatter(input_text)
        fm, body = parse_frontmatter(result)
        assert fm is not None
        assert fm["funder"] == "OAC"
        assert fm["written"] == 2024
        assert "Body text here." in body

    def test_sanitize_frontmatter_normalizes_aliases(self):
        input_text = """---
year_written: 2023
doc_type: "report"
funder: "OAC"
---

Report body.
"""
        result = sanitize_frontmatter(input_text)
        fm, body = parse_frontmatter(result)
        assert fm is not None
        assert "written" in fm
        assert fm["written"] == 2023
        assert "year_written" not in fm
        assert "type" in fm
        assert "doc_type" not in fm

    def test_sanitize_frontmatter_handles_code_fenced(self):
        input_text = """```yaml
---
funder: "OAC"
written: 2022
---
```
# Greetings
Hello world.
"""
        result = sanitize_frontmatter(input_text)
        fm, body = parse_frontmatter(result)
        assert fm is not None
        assert fm["funder"] == "OAC"
        assert "# Greetings" in result

    def test_sanitize_frontmatter_no_frontmatter(self):
        input_text = "# Just a heading\n\nSome content."
        result = sanitize_frontmatter(input_text)
        assert result == input_text + "\n"


class TestMultiFileBatchClassification:
    def make_file(self, dir_path: Path, name: str, frontmatter: str, body: str):
        content = frontmatter + "\n" + body
        (dir_path / name).write_text(content)

    def test_different_files_get_different_results(self, tmp_path):
        clean_dir = tmp_path / "clean_md"
        clean_dir.mkdir()

        tier1 = "---\nfunder: \"OAC\"\ntype: \"report\"\nwritten: 2023\n---\n\n" + (
            "# Annual Report\n\n"
            + "Summary of activities for the fiscal year.\n"
            + "\n".join(
                f"Line {i} with enough content to surpass minimum thresholds for classification."
                for i in range(30)
            )
        )
        tier2 = "---\nfunder: \"OAC\"\ntype: \"application\"\nwritten: 2024\n---\n\n" + (
            "# Grant Application\n\n"
            + "**Project Description**\n\n"
            + "\n".join(f"Line {i} of application narrative describing the project in detail."
                        for i in range(30))
            + "\n\n<!-- image -->\n\n<!-- image -->\n\n<!-- image -->\n\n"
            + "<!-- image -->\n\n<!-- image -->\n\n<!-- image -->\n\n"
        )
        tier3 = "---\nfunder: \"OAC\"\ntype: \"draft\"\nwritten: 2025\n---\n\n" + (
            "# Draft\n\n"
            + "Short\n"
        )
        tier4 = (
            "---\nfunder: \"CAC\"\ntype: \"budget\"\nwritten: 2024\nperiod: 2024-2025\n---\n\n"
            + "# Budget\n\n"
            + "\n".join(f"| Item {i} | Cost {i} | Notes |" for i in range(1, 40))
        )
        tier5 = "---\nfunder: \"CAC\"\ntype: \"support_material\"\nwritten: 2024\n---\n\n" + (
            "# Support Materials\n\n"
            + "\n".join(f"Supporting document line {i} with substantial content for classification."
                        for i in range(25))
        )

        self.make_file(clean_dir, "OAC__2023_Annual_Report.md",
                       tier1[:tier1.index("\n\n") + 1], tier1)
        self.make_file(clean_dir, "OAC__2024_Grant__Application.md",
                       tier2[:tier2.index("\n\n") + 1], tier2)
        self.make_file(clean_dir, "OAC__draft_notes.md",
                       tier3[:tier3.index("\n\n") + 1], tier3)
        self.make_file(clean_dir, "CAC__2024_Operating_Budget.md",
                       tier4[:tier4.index("\n\n") + 1], tier4)
        self.make_file(clean_dir, "CAC__support_material.md",
                       tier5[:tier5.index("\n\n") + 1], tier5)

        all_files = sorted(clean_dir.glob("*.md"))
        assert len(all_files) == 5

        config = dict(DEFAULT_CLASSIFY_CONFIG)
        config["funders"] = {"OAC": "Ontario Arts Council", "CAC": "Canada Council"}

        results = {}
        for fpath in all_files:
            results[fpath.name] = classify_file(fpath, config)

        assert len(results) == 5

        for fname, result in results.items():
            assert "tier" in result
            assert "status" in result
            assert "funder" in result
            assert "doc_types" in result
            assert "content_lines" in result
            assert "corruption_score" in result

        funders = {r["funder"] for r in results.values()}
        assert "OAC" in funders
        assert "CAC" in funders

        tiers = {str(r["tier"]) for r in results.values()}
        assert len(tiers) >= 1


class TestFrontmatterRoundtrip:
    def test_parse_update_parse_cycle(self, tmp_path):
        original = """---
funder: "OAC"
type: "application"
written: 2024
---

# Original Body

Content here.
"""

        fm, body = parse_frontmatter(original)
        assert fm is not None
        assert fm["funder"] == "OAC"
        assert fm["written"] == 2024
        assert "priority" not in fm

        updated = update_frontmatter(original, priority=2, status="final")

        fm2, body2 = parse_frontmatter(updated)
        assert fm2 is not None
        assert fm2["funder"] == "OAC"
        assert fm2["written"] == 2024
        assert fm2["priority"] == 2
        assert fm2["status"] == "final"

        assert "Original Body" in body2

        updated2 = update_frontmatter(updated, priority=1)

        fm3, _ = parse_frontmatter(updated2)
        assert fm3["priority"] == 1

    def test_update_frontmatter_no_existing(self, tmp_path):
        no_fm = "# Just a heading\n\nBody text."

        updated = update_frontmatter(no_fm, funder="OAC", written=2023)

        fm, body = parse_frontmatter(updated)
        assert fm is not None
        assert fm["funder"] == "OAC"
        assert fm["written"] == 2023
        assert "Just a heading" in body

    def test_strip_existing_frontmatter(self, tmp_path):
        with_fm = """---
funder: "OAC"
---

# Heading

Body.
"""
        stripped = strip_existing_frontmatter(with_fm)
        assert "---" not in stripped
        assert "funder" not in stripped
        assert "# Heading" in stripped
        assert "Body." in stripped


class TestManifestCRUD:
    def test_create_manifest(self):
        manifest = create_manifest("test-project")
        assert manifest["project"] == "test-project"
        assert "generated" in manifest
        assert "updated" in manifest
        assert manifest["files"] == {}
        assert manifest["summary"]["total_files"] == 0
        assert manifest["summary"]["by_status"] == {}
        assert manifest["summary"]["by_tier"] == {}
        assert manifest["summary"]["by_funder"] == {}
        assert manifest["summary"]["total_cost_usd"] == 0.0

    def test_update_and_get_file(self):
        manifest = create_manifest("test-project")

        update_file(manifest, "doc1.md", status="ok", tier="minimal", funder="OAC")
        update_file(manifest, "doc2.md", status="pending", tier="full", funder="CAC")
        update_file(manifest, "doc3.md", status="error_conversion")

        assert get_file(manifest, "doc1.md") == {
            "status": "ok",
            "tier": "minimal",
            "funder": "OAC",
        }
        assert get_file(manifest, "doc2.md") == {
            "status": "pending",
            "tier": "full",
            "funder": "CAC",
        }
        assert get_file(manifest, "doc3.md") == {
            "status": "error_conversion",
        }
        assert get_file(manifest, "nonexistent.md") is None

        update_file(manifest, "doc1.md", priority=1, cost_usd=0.05)
        entry = get_file(manifest, "doc1.md")
        assert entry["status"] == "ok"
        assert entry["tier"] == "minimal"
        assert entry["funder"] == "OAC"
        assert entry["priority"] == 1
        assert entry["cost_usd"] == 0.05

    def test_recalculate_summary(self):
        manifest = create_manifest("test-project")

        update_file(manifest, "doc1.md", status="ok", tier="minimal", funder="OAC",
                     rewrite_cost_usd=0.01)
        update_file(manifest, "doc2.md", status="ok", tier="full", funder="OAC",
                     rewrite_cost_usd=0.03)
        update_file(manifest, "doc3.md", status="skipped_draft", tier="skip",
                     funder="CAC")
        update_file(manifest, "doc4.md", status="ok", tier="light", funder="CAC",
                     rewrite_cost_usd=0.02)

        recalculate_summary(manifest)

        summary = manifest["summary"]
        assert summary["total_files"] == 4
        assert summary["by_status"]["ok"] == 3
        assert summary["by_status"]["skipped_draft"] == 1
        assert summary["by_tier"]["minimal"] == 1
        assert summary["by_tier"]["full"] == 1
        assert summary["by_tier"]["light"] == 1
        assert summary["by_tier"]["skip"] == 1
        assert summary["by_funder"]["OAC"] == 2
        assert summary["by_funder"]["CAC"] == 2
        assert abs(summary["total_cost_usd"] - 0.06) < 0.001

    def test_save_and_load_manifest(self, tmp_path):
        manifest = create_manifest("test-project")

        update_file(manifest, "doc1.md", status="ok", tier="minimal", funder="OAC",
                     rewrite_cost_usd=0.01)
        update_file(manifest, "doc2.md", status="ok", tier="full", funder="CAC",
                     rewrite_cost_usd=0.03)

        recalculate_summary(manifest)

        manifest_path = tmp_path / "manifest.json"
        save_manifest(manifest, manifest_path)

        assert manifest_path.exists()

        raw_json = json.loads(manifest_path.read_text())
        assert raw_json["project"] == "test-project"
        assert len(raw_json["files"]) == 2

        loaded = load_manifest(manifest_path)
        assert loaded["project"] == "test-project"
        assert len(loaded["files"]) == 2
        assert get_file(loaded, "doc1.md")["funder"] == "OAC"
        assert get_file(loaded, "doc2.md")["funder"] == "CAC"
        assert loaded["summary"]["total_files"] == 2
        assert loaded["summary"]["by_funder"]["OAC"] == 1
        assert loaded["summary"]["by_funder"]["CAC"] == 1

    def test_load_manifest_missing_file(self, tmp_path):
        manifest = load_manifest(tmp_path / "nonexistent.json")
        assert manifest["project"] == "folio"
        assert manifest["files"] == {}
        assert manifest["summary"]["total_files"] == 0

    def test_file_entry_conversion_fields_roundtrip(self, tmp_path):
        manifest = create_manifest("test-project")
        update_file(
            manifest, "doc.md",
            status="ok", converter_tier="datalab", conversion_cost_usd=0.06,
        )

        manifest_path = tmp_path / "manifest.json"
        save_manifest(manifest, manifest_path)
        loaded = load_manifest(manifest_path)

        entry = get_file(loaded, "doc.md")
        assert entry["converter_tier"] == "datalab"
        assert entry["conversion_cost_usd"] == 0.06

    def test_file_entry_conversion_fields_backcompat(self):
        manifest = create_manifest("test-project")
        update_file(manifest, "old.md", status="ok", tier="full")

        entry = get_file(manifest, "old.md")
        assert entry.get("converter_tier") is None
        assert entry.get("conversion_cost_usd", 0.0) == 0.0

    def test_conversion_cost_contributes_to_summary_total(self):
        manifest = create_manifest("test-project")
        update_file(
            manifest, "doc.md",
            status="ok", conversion_cost_usd=0.06, rewrite_cost_usd=0.01,
        )

        recalculate_summary(manifest)

        assert abs(manifest["summary"]["total_cost_usd"] - 0.07) < 1e-6

    def test_save_updates_timestamp(self, tmp_path):
        import time
        manifest = create_manifest("test-project")
        original_updated = manifest["updated"]

        time.sleep(1.5)

        manifest_path = tmp_path / "manifest.json"
        save_manifest(manifest, manifest_path)

        loaded = load_manifest(manifest_path)
        assert loaded["updated"] != original_updated


# ---------------------------------------------------------------------------
# Full pipeline integration tests
# ---------------------------------------------------------------------------


class TestPipelineEndToEnd:
    """Integration tests for the full folio pipeline end-to-end."""

    FOLIO_YAML_TEMPLATE = """\
project:
  name: Integration Test
org:
  name: Test Org
  abbreviation: TEST
paths:
  raw_archive: {raw_archive}
  raw_md: {raw_md}
  clean_md: {clean_md}
  rewrite_md: {rewrite_md}
  wiki_project: {wiki_project}
funders:
  OAC: Ontario Arts Council
  TAC: Toronto Arts Council
doc_types:
  - application
  - report
  - budget
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

    SAMPLE_MD_CONTENT = """---
funder: "OAC"
type: application
written: 2024
---

# Project Description

This is a substantial project description with detailed narrative content about the organization's
programming plans for the upcoming fiscal year. The project involves community engagement, artist
development, and public outreach activities that serve diverse audiences.

## Goals

- Increase community participation in arts programming
- Develop new partnerships with local organizations
- Expand outreach to underserved communities

## Budget

The total budget for this project is $50,000 allocated across staffing, materials, venue costs,
and artist fees. Staff costs account for approximately 40% of the total budget with the remainder
going to direct project expenses.

## Timeline

The project will run from January through December 2024 with quarterly milestones and a final
report due in January 2025.

## Evaluation

Success will be measured through attendance numbers, participant surveys, and partnership
agreements. We expect to reach 500 community members through our programming.
"""

    def _create_test_archive(self, tmp_path):
        """Create a mini archive with markdown files and folio.yaml."""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()

        for i in range(3):
            fname = f"OAC__2024_Grant_Application_{i + 1}.md"
            (archive_dir / fname).write_text(self.SAMPLE_MD_CONTENT, encoding="utf-8")

        config = tmp_path / "folio.yaml"
        config.write_text(self.FOLIO_YAML_TEMPLATE.format(
            raw_archive=str(archive_dir),
            raw_md=str(tmp_path / ".folio" / "converted"),
            clean_md=str(tmp_path / ".folio" / "cleaned"),
            rewrite_md=str(tmp_path / "markdown"),
            wiki_project=str(tmp_path / ".folio" / "sage-wiki"),
        ))
        return config

    def test_full_pipeline_dry_run_report_structure(self, tmp_path):
        """Full pipeline --dry-run produces a report with all 8 stages."""
        from folio.config.loader import load_project_config
        from folio.core.pipeline import _estimate_pipeline

        config_path = self._create_test_archive(tmp_path)
        config = load_project_config(config_path)

        report = _estimate_pipeline(config)

        assert "project" in report
        assert report["project"] == "Test Org"
        assert "started" in report
        assert "completed" in report
        assert "stages" in report
        assert "total_cost_usd" in report
        assert "total_time_seconds" in report

        stages = report["stages"]
        expected_stages = {"scan", "convert", "clean", "canonicalize",
                           "classify", "rewrite", "prioritize", "wiki"}
        assert set(stages.keys()) == expected_stages

        for stage_name in expected_stages:
            stage_data = stages[stage_name]
            assert "status" in stage_data, f"Missing status in {stage_name}"
            assert "files" in stage_data, f"Missing files in {stage_name}"
            assert "cost_usd" in stage_data, f"Missing cost_usd in {stage_name}"
            assert "time_seconds" in stage_data, f"Missing time_seconds in {stage_name}"

        assert report["total_cost_usd"] >= 0
        assert report["total_time_seconds"] >= 0

    def test_pipeline_json_output(self, tmp_path, capsys):
        """Pipeline --dry-run --json produces valid JSON."""
        from folio.cli.pipeline import main

        config_path = self._create_test_archive(tmp_path)
        main(["--config", str(config_path), "--dry-run", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert "project" in data
        assert "stages" in data
        assert len(data["stages"]) == 8
        assert "total_cost_usd" in data
        assert "total_time_seconds" in data

    def test_pipeline_dry_run_text_output(self, tmp_path, capsys):
        """Pipeline --dry-run prints human-readable text report."""
        from folio.cli.pipeline import main

        config_path = self._create_test_archive(tmp_path)
        main(["--config", str(config_path), "--dry-run"])
        captured = capsys.readouterr()
        output = captured.out

        assert "folio pipeline" in output
        for stage in ("scan", "convert", "clean", "canonicalize",
                       "classify", "rewrite", "prioritize", "wiki"):
            assert stage in output.lower(), f"Stage {stage} not in output"
        assert "Pipeline complete" in output

    def test_pipeline_specific_stages(self, tmp_path, capsys):
        """Pipeline --stages scan,clean runs only those stages."""
        from folio.cli.pipeline import main

        config_path = self._create_test_archive(tmp_path)
        main(["--config", str(config_path), "--stages", "scan,clean", "--dry-run", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert "scan" in data["stages"]
        assert "clean" in data["stages"]

    def test_pipeline_dry_run_includes_all_stages(self, tmp_path, capsys):
        """Pipeline --dry-run always estimates all 8 stages (stages filter ignored in dry-run)."""
        from folio.cli.pipeline import main

        config_path = self._create_test_archive(tmp_path)
        main(["--config", str(config_path), "--stages", "scan,clean", "--dry-run", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert len(data["stages"]) == 8

    def test_pipeline_invalid_stage_name(self, tmp_path, capsys):
        """Pipeline --stages with invalid name exits 1."""
        from folio.cli.pipeline import main

        config_path = self._create_test_archive(tmp_path)
        with pytest.raises(SystemExit) as exc:
            main(["--config", str(config_path), "--stages", "scan,nonexistent"])
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Unknown stage" in captured.err

    def test_pipeline_stages_dry_run_cost_estimation(self, tmp_path):
        """Each pipeline stage in dry-run has a cost_usd and time_seconds."""
        from folio.config.loader import load_project_config
        from folio.core.pipeline import _estimate_pipeline

        config_path = self._create_test_archive(tmp_path)
        config = load_project_config(config_path)

        report = _estimate_pipeline(config)
        stages = report["stages"]

        assert isinstance(stages["rewrite"]["cost_usd"], (int, float))
        assert isinstance(stages["rewrite"]["time_seconds"], (int, float))

    def test_pipeline_dry_run_creates_no_files(self, tmp_path):
        """Pipeline --dry-run does not create any files in target directories."""
        from folio.config.loader import load_project_config
        from folio.core.pipeline import _estimate_pipeline

        config_path = self._create_test_archive(tmp_path)
        config = load_project_config(config_path)

        markdown_dir = tmp_path / "markdown"
        converted_dir = tmp_path / ".folio" / "converted"

        _estimate_pipeline(config)

        assert not list(markdown_dir.glob("*.md")) if markdown_dir.exists() else True
        assert not list(converted_dir.glob("*.md")) if converted_dir.exists() else True

    def test_run_pipeline_dry_run(self, tmp_path, capsys):
        """run_pipeline with dry_run=True works end-to-end."""
        from folio.core.pipeline import run_pipeline

        config_path = self._create_test_archive(tmp_path)

        report = run_pipeline(
            config_path=config_path,
            stages=None,
            dry_run=True,
            resume=True,
        )

        assert "project" in report
        assert "stages" in report
        assert len(report["stages"]) == 8
        assert "total_cost_usd" in report
        assert "total_time_seconds" in report
        assert report["total_time_seconds"] >= 0

    def test_pipeline_resume_behavior(self, tmp_path):
        """Test resume: manifest with some complete stages skips them."""
        from folio.config.loader import load_project_config
        from folio.core.manifest import create_manifest, save_manifest
        from folio.core.pipeline import run_pipeline

        config_path = self._create_test_archive(tmp_path)
        config = load_project_config(config_path)

        rewrite_dir = tmp_path / "markdown"
        rewrite_dir.mkdir(parents=True, exist_ok=True)

        manifest = create_manifest("Test Org")
        manifest["stages"] = {
            "scan": {"status": "complete", "files": 3, "cost_usd": 0.0, "time_seconds": 1.0},
            "convert": {"status": "complete", "files": 3, "cost_usd": 0.0, "time_seconds": 2.0},
            "clean": {"status": "complete", "files": 3, "cost_usd": 0.0, "time_seconds": 0.5},
        }
        manifest_path = rewrite_dir / "manifest.json"
        save_manifest(manifest, manifest_path)

        report = run_pipeline(
            config_path=config_path,
            stages=None,
            dry_run=True,
            resume=True,
        )

        assert "scan" in report["stages"]
        assert "convert" in report["stages"]
        assert "clean" in report["stages"]

        scan = report["stages"]["scan"]
        assert scan["status"] == "complete"
        assert scan["files"] == 3

    def test_pipeline_with_real_markdown_files(self, tmp_path):
        """Pipeline dry-run with realistic markdown files in archive."""
        from folio.config.loader import load_project_config
        from folio.core.pipeline import _estimate_pipeline

        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()

        content1 = """---
funder: "OAC"
type: application
written: 2024
---

# Core Operating Grant Application

## Organization Profile

The organization was founded in 1995 and has since served the local arts community
through exhibitions, workshops, and public programming. We maintain a staff of 5
full-time employees and operate a 2000 sq ft gallery space.

## Project Narrative

This application requests $25,000 to support our 2024-2025 programming season.
The funds will be used to mount 6 exhibitions, host 12 workshops, and publish
a quarterly arts journal.

## Budget Summary

Revenue: $150,000 (grants: $75,000, earned: $50,000, donations: $25,000)
Expenses: $145,000 (staff: $70,000, programming: $45,000, admin: $30,000)
Surplus: $5,000

## Evaluation Framework

We measure success through attendance, participant surveys, artist fees paid,
and community partnerships established.
"""
        content2 = """---
funder: "TAC"
type: report
written: 2023
---

# Final Grant Report: Community Arts Initiative

## Project Overview

This report summarizes activities undertaken with the TAC grant awarded in
January 2023. The $15,000 grant supported a series of 8 community workshops
and 2 public exhibitions.

## Activities Completed

- 8 community workshops with 120 total participants
- 2 public exhibitions with 450 visitors
- 3 artist talks with 60 attendees each
- 1 publication distributed to 200 households

## Budget Reconciliation

Total grant: $15,000
Spent: $14,750
  - Artist fees: $6,000
  - Materials: $3,500
  - Venue rental: $2,750
  - Promotion: $1,500
  - Administration: $1,000

## Outcomes and Impact

The project exceeded participation targets by 20%. Participant surveys indicated
95% satisfaction rate. Three new community partnerships were established.
"""
        content3 = """---
funder: "OAC"
type: budget
written: 2025
---

# 2025 Operating Budget Projection

## Revenue Projections

| Source | Amount |
|--------|--------|
| OAC Operating | $30,000 |
| TAC Project | $15,000 |
| Earned Revenue | $40,000 |
| Donations | $20,000 |
| Total | $105,000 |

## Expense Projections

| Category | Amount |
|----------|--------|
| Staff Salaries | $55,000 |
| Artist Fees | $15,000 |
| Venue Costs | $12,000 |
| Marketing | $8,000 |
| Materials | $7,000 |
| Admin | $8,000 |
| Total | $105,000 |

## Notes

This budget assumes flat funding from OAC and a 5% increase in earned revenue
from ticket sales and workshop fees. Contingency reserve of 3% is built into
each line item.
"""

        (archive_dir / "OAC__2024_Core_Operating_Grant__Application.md").write_text(content1)
        (archive_dir / "TAC__2023_Final_Report__Report.md").write_text(content2)
        (archive_dir / "OAC__2025_Operating_Budget__Budget.md").write_text(content3)

        config = tmp_path / "folio.yaml"
        config.write_text(self.FOLIO_YAML_TEMPLATE.format(
            raw_archive=str(archive_dir),
            raw_md=str(tmp_path / ".folio" / "converted"),
            clean_md=str(tmp_path / ".folio" / "cleaned"),
            rewrite_md=str(tmp_path / "markdown"),
            wiki_project=str(tmp_path / ".folio" / "sage-wiki"),
        ))

        project_config = load_project_config(config)
        report = _estimate_pipeline(project_config)

        assert report["project"] == "Test Org"
        assert len(report["stages"]) == 8

        scan_stage = report["stages"]["scan"]
        assert scan_stage["status"] == "ok"
        assert scan_stage["files"] >= 0


class TestConvertStageManifest:
    """Convert stage records the winning converter tier and per-file cost."""

    def _make_archive(self, tmp_path, names):
        archive = tmp_path / "archive"
        archive.mkdir()
        for n in names:
            (archive / n).write_text("dummy", encoding="utf-8")

        config = tmp_path / "folio.yaml"
        config.write_text(TestPipelineEndToEnd.FOLIO_YAML_TEMPLATE.format(
            raw_archive=str(archive),
            raw_md=str(tmp_path / ".folio" / "converted"),
            clean_md=str(tmp_path / ".folio" / "cleaned"),
            rewrite_md=str(tmp_path / "markdown"),
            wiki_project=str(tmp_path / ".folio" / "sage-wiki"),
        ))
        return config

    def test_cascade_records_winning_tier_and_accumulated_cost(self, tmp_path, monkeypatch):
        import folio.adapters.converters as conv_pkg
        from folio.adapters.converters.cascade import CascadeConverter
        from folio.core.pipeline import run_pipeline

        tier0 = _StubConverter("tier0", _SPARSE_MD, 0.01)
        tier1 = _StubConverter("tier1", _RICH_MD, 0.06)
        cascade = CascadeConverter([tier0, tier1])
        monkeypatch.setattr(conv_pkg, "get_converter", lambda cfg: cascade)

        config_path = self._make_archive(tmp_path, ["doc_0.pdf", "doc_1.pdf"])
        report = run_pipeline(
            config_path=config_path, stages=["convert"], dry_run=False, resume=True
        )

        manifest = load_manifest(tmp_path / "markdown" / "manifest.json")
        entry = get_file(manifest, "doc_0.md")
        assert entry is not None
        assert entry["converter_tier"] == "tier1"
        assert entry["conversion_cost_usd"] == pytest.approx(0.07)

        convert_stage = report["stages"]["convert"]
        assert convert_stage["converted"] == 2
        assert convert_stage["cost_usd"] == pytest.approx(0.14)

    def test_non_cascade_records_single_converter_name(self, tmp_path, monkeypatch):
        import folio.adapters.converters as conv_pkg
        from folio.core.pipeline import run_pipeline

        single = _StubConverter("solo", _RICH_MD, 0.03)
        monkeypatch.setattr(conv_pkg, "get_converter", lambda cfg: single)

        config_path = self._make_archive(tmp_path, ["a.pdf", "b.pdf", "c.pdf"])
        report = run_pipeline(
            config_path=config_path, stages=["convert"], dry_run=False, resume=True
        )

        manifest = load_manifest(tmp_path / "markdown" / "manifest.json")
        entry = get_file(manifest, "a.md")
        assert entry is not None
        assert entry["converter_tier"] == "solo"
        assert entry["conversion_cost_usd"] == pytest.approx(0.03)

        assert report["stages"]["convert"]["cost_usd"] == pytest.approx(0.09)
