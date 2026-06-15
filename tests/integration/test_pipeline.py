import json
from pathlib import Path

import pytest

from folio.core.pipeline import AVAILABLE_STAGES
from folio.core.cleaner import clean_markdown, clean_file
from folio.core.frontmatter import (
    parse_frontmatter,
    sanitize_frontmatter,
    update_frontmatter,
    strip_existing_frontmatter,
)
from folio.core.manifest import (
    create_manifest,
    update_file,
    get_file,
    recalculate_summary,
    save_manifest,
    load_manifest,
)
from folio.core.classifier import classify_file, DEFAULT_CLASSIFY_CONFIG


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
            + "\n".join(f"Line {i} with enough content to surpass minimum thresholds for classification."
                        for i in range(30))
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
        tier4 = "---\nfunder: \"CAC\"\ntype: \"budget\"\nwritten: 2024\nperiod: 2024-2025\n---\n\n" + (
            "# Budget\n\n"
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

    def test_save_updates_timestamp(self, tmp_path):
        import time
        manifest = create_manifest("test-project")
        original_updated = manifest["updated"]

        time.sleep(1.5)

        manifest_path = tmp_path / "manifest.json"
        save_manifest(manifest, manifest_path)

        loaded = load_manifest(manifest_path)
        assert loaded["updated"] != original_updated
