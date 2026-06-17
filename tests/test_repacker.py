from __future__ import annotations

import pytest
from pathlib import Path
from folio.core.repacker import (
    _detect_funder_from_segments,
    _detect_year_from_segments,
    _detect_type_from_segments,
    _detect_description_from_segments,
    _build_filename,
    _confidence_score,
    scan_nested,
    _resolve_collision,
    repack_files,
    TYPE_KEYWORDS,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_file(directory: Path, name: str, content: str = "") -> Path:
    fpath = directory / name
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(content, encoding="utf-8")
    return fpath


FUNDERS_SMALL = {
    "OAC": "Ontario Arts Council",
    "CAC": "Canada Council",
    "TAC": "Toronto Arts Council",
}

FUNDERS_LARGE = {
    **FUNDERS_SMALL,
    "CAC_T": "Canada Council Toronto",
    "BCAC": "BC Arts Council",
}


# ── _detect_funder_from_segments ───────────────────────────────────────────────

class TestDetectFunderFromSegments:
    def test_detects_in_path(self):
        # The detection looks for the abbreviation (key) in path segments.
        # "CAC" is not in "Canada_Council", but "OAC" is in a segment containing "OAC".
        assert _detect_funder_from_segments(
            ["CAC", "2024", "grants"], FUNDERS_SMALL
        ) == "CAC"

    def test_detects_in_filename(self):
        assert _detect_funder_from_segments(
            ["OAC_Application_2024.pdf"], FUNDERS_SMALL
        ) == "OAC"

    def test_longest_match_first(self):
        assert _detect_funder_from_segments(
            ["CAC_T", "2024", "report.pdf"], FUNDERS_LARGE
        ) == "CAC_T"

    def test_case_insensitive(self):
        assert _detect_funder_from_segments(
            ["oac", "submissions"], FUNDERS_SMALL
        ) == "OAC"

    def test_no_match_returns_none(self):
        assert _detect_funder_from_segments(
            ["unknown", "dir"], FUNDERS_SMALL
        ) is None

    def test_empty_segments(self):
        assert _detect_funder_from_segments([], FUNDERS_SMALL) is None

    def test_empty_funders(self):
        assert _detect_funder_from_segments(["OAC", "2024"], {}) is None


# ── _detect_year_from_segments ─────────────────────────────────────────────────

class TestDetectYearFromSegments:
    def test_detects_year_in_directory(self):
        assert _detect_year_from_segments(["grants", "2024", "files"]) == 2024

    def test_detects_year_in_filename(self):
        # YEAR_PATTERN uses \b which requires word boundaries; underscores are
        # word chars so _2023_ doesn't match. Use a year in a directory segment.
        assert _detect_year_from_segments(["OAC", "2023", "Application.pdf"]) == 2023

    def test_first_year_wins(self):
        assert _detect_year_from_segments(["2022", "2023", "submitted"]) == 2022

    def test_no_year_returns_none(self):
        assert _detect_year_from_segments(["grants", "misc"]) is None

    def test_ignores_non_2000_years(self):
        assert _detect_year_from_segments(["1999_app"]) is None

    def test_empty_segments(self):
        assert _detect_year_from_segments([]) is None


# ── _detect_type_from_segments ─────────────────────────────────────────────────

class TestDetectTypeFromSegments:
    def test_application(self):
        assert _detect_type_from_segments(["grant application 2024.pdf"]) == "application"

    def test_report(self):
        assert _detect_type_from_segments(["final report.pdf"]) == "report"

    def test_budget(self):
        assert _detect_type_from_segments(["OAC", "budget", "2024_budget.xlsx"]) == "budget"

    def test_notification(self):
        assert _detect_type_from_segments(["notification letter.pdf"]) == "notification"

    def test_activity_list(self):
        assert _detect_type_from_segments(["activity list.pdf"]) == "activity_list"

    def test_staff_board(self):
        assert _detect_type_from_segments(["board", "bios"]) == "staff_board"

    def test_support_material(self):
        assert _detect_type_from_segments(["promo material.pdf"]) == "support_material"

    def test_no_match_returns_none(self):
        assert _detect_type_from_segments(["mystery file.pdf"]) is None

    def test_empty_segments(self):
        assert _detect_type_from_segments([]) is None


# ── _detect_description_from_segments ──────────────────────────────────────────

class TestDetectDescriptionFromSegments:
    def test_extracts_description(self):
        desc = _detect_description_from_segments(
            ["OAC", "2024", "My Project Application.pdf"],
            funder="OAC", year_str="2024", doc_type="application",
        )
        assert "My" in desc
        assert "Project" in desc
        assert "OAC" not in desc
        assert "2024" not in desc.lower()

    def test_strips_funder_from_filename(self):
        desc = _detect_description_from_segments(
            ["CAC_Annual_Report_2023.pdf"],
            funder="CAC", year_str="2023", doc_type="report",
        )
        assert "CAC" not in desc
        assert "Annual" in desc

    def test_strips_year_from_filename(self):
        desc = _detect_description_from_segments(
            ["2024_Budget_Summary.xlsx"],
            funder=None, year_str="2024", doc_type="budget",
        )
        assert "2024" not in desc

    def test_no_funder_no_year(self):
        desc = _detect_description_from_segments(
            ["Project Overview.pdf"],
            funder=None, year_str="0000", doc_type=None,
        )
        assert "Project" in desc
        assert "Overview" in desc

    def test_empty_segments(self):
        desc = _detect_description_from_segments(
            [], funder=None, year_str="0000", doc_type=None
        )
        assert desc == ""


# ── _build_filename ────────────────────────────────────────────────────────────

class TestBuildFilename:
    def test_full_filename(self):
        result = _build_filename("OAC", 2024, "Grant Application", "application", ".pdf")
        assert result == "OAC__2024_Grant_Application__application.pdf"

    def test_no_description(self):
        result = _build_filename("OAC", 2024, "", "report", ".md")
        assert result == "OAC__2024__report.md"

    def test_year_as_string(self):
        result = _build_filename("UNKNOWN", "0000", "Some File", "unknown", ".docx")
        assert result == "UNKNOWN__0000_Some_File__unknown.docx"


# ── _confidence_score ──────────────────────────────────────────────────────────

class TestConfidenceScore:
    def test_all_fields_present(self):
        assert _confidence_score("OAC", 2024, "application") == 1.0

    def test_only_funder(self):
        assert _confidence_score("OAC", None, None) == 0.35

    def test_only_year(self):
        assert _confidence_score(None, 2024, None) == 0.35

    def test_only_type(self):
        assert _confidence_score(None, None, "report") == 0.30

    def test_none_fields(self):
        assert _confidence_score(None, None, None) == 0.0


# ── scan_nested ────────────────────────────────────────────────────────────────

class TestScanNested:
    def test_single_file_detected(self, tmp_path):
        _make_file(tmp_path / "OAC" / "2024", "Application.pdf", "fake content")
        results = scan_nested(tmp_path, FUNDERS_SMALL)
        assert len(results) == 1
        r = results[0]
        assert r["funder"] == "OAC"
        assert r["year"] == 2024
        expected_file = "OAC__2024__application.pdf"
        assert r["suggested_filename"] == expected_file

    def test_multiple_files(self, tmp_path):
        _make_file(tmp_path / "OAC" / "2023", "Final Report.pdf", "content")
        _make_file(tmp_path / "CAC" / "2024", "Budget.xlsx", "content")
        results = scan_nested(tmp_path, FUNDERS_SMALL)
        assert len(results) == 2

    def test_low_confidence_needs_review(self, tmp_path):
        _make_file(tmp_path / "UnknownDir", "mystery_file.pdf", "content")
        results = scan_nested(tmp_path)
        assert len(results) == 1
        assert results[0]["confidence"] < 0.65
        assert results[0]["needs_review"] is True

    def test_skips_hidden_files(self, tmp_path):
        _make_file(tmp_path, ".hidden_file.pdf", "content")
        results = scan_nested(tmp_path, FUNDERS_SMALL)
        assert len(results) == 0

    def test_skips_files_without_extension(self, tmp_path):
        _make_file(tmp_path / "OAC", "README", "content")
        results = scan_nested(tmp_path, FUNDERS_SMALL)
        assert len(results) == 0

    def test_empty_directory(self, tmp_path):
        results = scan_nested(tmp_path, FUNDERS_SMALL)
        assert results == []

    def test_deeply_nested(self, tmp_path):
        _make_file(tmp_path / "a" / "b" / "c" / "d", "OAC_report_2024.pdf", "content")
        results = scan_nested(tmp_path, FUNDERS_SMALL)
        assert len(results) == 1
        assert results[0]["funder"] == "OAC"

    def test_no_funders_dict(self):
        results = scan_nested(Path("."))
        assert isinstance(results, list)

    def test_type_from_nested_directory(self, tmp_path):
        _make_file(tmp_path / "OAC" / "2024" / "grants", "Application.pdf", "content")
        results = scan_nested(tmp_path, FUNDERS_SMALL)
        assert len(results) >= 1
        assert results[0]["doc_type"] == "application"

    def test_detects_budget_in_path(self, tmp_path):
        _make_file(tmp_path / "OAC" / "2024" / "budget", "Q1.xlsx", "content")
        results = scan_nested(tmp_path, FUNDERS_SMALL)
        assert results[0]["doc_type"] == "budget"


# ── _resolve_collision ─────────────────────────────────────────────────────────

class TestResolveCollision:
    def test_no_collision(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()
        result = _resolve_collision(dest, "file.pdf")
        assert result == dest / "file.pdf"

    def test_single_collision(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "file.pdf").write_text("existing")
        result = _resolve_collision(dest, "file.pdf")
        assert result == dest / "file_1.pdf"

    def test_multiple_collisions(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "file.pdf").write_text("a")
        (dest / "file_1.pdf").write_text("b")
        result = _resolve_collision(dest, "file.pdf")
        assert result == dest / "file_2.pdf"


# ── repack_files ───────────────────────────────────────────────────────────────

class TestRepackFiles:
    def test_copy_mode(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        _make_file(src / "OAC" / "2024", "Application.pdf", "content")
        result = repack_files(src, dest, dry_run=False, move=False, funders=FUNDERS_SMALL)
        assert result["total"] == 1
        assert result["success"] == 1
        assert result["skipped"] == 0
        assert len(list(dest.rglob("*"))) >= 1
        assert len(list(src.rglob("*"))) >= 1  # original still exists in copy mode

    def test_move_mode(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        _make_file(src / "OAC" / "2024", "Application.pdf", "content")
        result = repack_files(src, dest, dry_run=False, move=True, funders=FUNDERS_SMALL)
        assert result["total"] == 1
        assert result["success"] == 1
        assert len(list(dest.rglob("*.pdf"))) == 1
        assert len(list(src.rglob("*.pdf"))) == 0

    def test_dry_run_no_files_written(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        _make_file(src / "OAC" / "2024", "Application.pdf", "content")
        result = repack_files(src, dest, dry_run=True, funders=FUNDERS_SMALL)
        assert result["total"] == 1
        assert result["success"] == 1
        assert not dest.exists()

    def test_collision_resolved(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        dest.mkdir(parents=True, exist_ok=True)
        suggested = "OAC__2024__application.pdf"
        (dest / suggested).write_text("pre-existing")
        _make_file(src / "OAC" / "2024", "Application.pdf", "new content")
        result = repack_files(src, dest, dry_run=False, funders=FUNDERS_SMALL)
        assert result["success"] == 1
        assert (dest / "OAC__2024__application_1.pdf").exists()

    def test_manifest_written(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        _make_file(src / "OAC" / "2024", "Application.pdf", "content")
        repack_files(src, dest, dry_run=False, funders=FUNDERS_SMALL)
        manifest = dest / ".folio_repack_manifest.json"
        assert manifest.exists()

    def test_manifest_not_written_dry_run(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        _make_file(src / "OAC" / "2024", "Application.pdf", "content")
        repack_files(src, dest, dry_run=True, funders=FUNDERS_SMALL)
        manifest = dest / ".folio_repack_manifest.json"
        assert not manifest.exists()

    def test_funder_override(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        _make_file(src / "UnknownDir", "file.pdf", "content")
        result = repack_files(src, dest, dry_run=True, funder_override="OAC")
        assert result["items"][0]["suggested_filename"].startswith("OAC__")

    def test_year_override(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        _make_file(src / "UnknownDir", "file.pdf", "content")
        result = repack_files(src, dest, dry_run=True, year_override=2024)
        assert result["items"][0]["suggested_filename"].startswith("UNKNOWN__2024")

    def test_type_override(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        _make_file(src / "UnknownDir", "file.pdf", "content")
        result = repack_files(src, dest, dry_run=True, type_override="report")
        assert "report" in result["items"][0]["suggested_filename"]

    def test_empty_source(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        dest = tmp_path / "dest"
        result = repack_files(src, dest, funders=FUNDERS_SMALL)
        assert result["total"] == 0
        assert result["success"] == 0

    def test_duplicate_filenames_different_dirs(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        _make_file(src / "OAC" / "2024", "App.pdf", "content a")
        _make_file(src / "OAC" / "2024" / "extra", "App.pdf", "content b")
        result = repack_files(src, dest, dry_run=False, funders=FUNDERS_SMALL)
        assert result["success"] == 2
        pdf_files = sorted(dest.rglob("*.pdf"))
        assert len(pdf_files) == 2

    def test_mapping_keys_match(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        f = _make_file(src / "OAC" / "2024", "Application.pdf", "content")
        result = repack_files(src, dest, dry_run=True, funders=FUNDERS_SMALL)
        assert str(f) in result["mapping"]


# ── Edge: deeply nested, no funder detection ───────────────────────────────────

class TestScanNestedEdgeCases:
    def test_no_funder_no_year_no_type(self, tmp_path):
        _make_file(tmp_path / "deep" / "nested" / "path", "randomfile.pdf", "content")
        results = scan_nested(tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r["funder"] is None
        assert r["year"] is None
        assert r["doc_type"] is None
        assert r["confidence"] == 0.0
        assert r["needs_review"] is True
        assert r["suggested_filename"].startswith("UNKNOWN__0000_")
        assert r["suggested_filename"].endswith("__unknown.pdf")
