from __future__ import annotations

import pytest
from pathlib import Path

from folio.core.scanner import (
    _detect_funder,
    _detect_year,
    _detect_type,
    _detect_draft,
    _get_type_patterns,
    _cost_per_doc,
    scan_archive,
    format_scan_report,
    DEFAULT_TYPE_PATTERNS,
    DRAFT_MARKERS,
)
from folio.config.schema import ProjectConfig, LLMConfig, ConverterConfig, ProcessingConfig


def make_scanner_config(**overrides) -> ProjectConfig:
    defaults = {
        "funders": {
            "CAC": "Canada Council for the Arts",
            "OAC": "Ontario Arts Council",
            "BCAC": "BC Arts Council",
            "TAC": "Toronto Arts Council",
        },
        "doc_types": {
            "application": [r"(?i)application", r"grant"],
            "report": [r"(?i)report", r"final_report"],
            "budget": [r"(?i)budget", r"cadac", r"financial"],
            "notification": [r"(?i)notification", r"approval", r"result"],
        },
        "llm": LLMConfig(input_price_per_m=0.14, output_price_per_m=0.28),
        "converter": ConverterConfig(type="docling"),
        "processing": ProcessingConfig(max_workers=10),
    }
    defaults.update(overrides)
    return ProjectConfig(**defaults)


# ── Unit: _detect_funder ─────────────────────────────────────────────────────

class TestDetectFunder:
    def test_detects_funder_in_filename(self):
        result = _detect_funder("CAC__2024_Grant__Application.md", {"CAC": "Canada Council"})
        assert result == "CAC"

    def test_detects_funder_in_directory_path(self):
        result = _detect_funder("subdir/OAC__Report.md", {"OAC": "Ontario Arts Council"})
        assert result == "OAC"

    def test_longest_match_first(self):
        funders = {"CAC": "Canada Council", "CAC_T": "Canada Council Toronto"}
        result = _detect_funder("CAC_T__2024.md", funders)
        assert result == "CAC_T"

    def test_case_insensitive_matching(self):
        funders = {"CAC": "Canada Council"}
        result = _detect_funder("cac__report.pdf", funders)
        assert result == "CAC"

    def test_no_match_returns_none(self):
        result = _detect_funder("random_file.md", {"CAC": "Canada Council"})
        assert result is None

    def test_empty_funders_returns_none(self):
        result = _detect_funder("CAC__Report.md", {})
        assert result is None

    def test_partial_match_works(self):
        funders = {"BCA": "BC Arts"}
        result = _detect_funder("BCAC__Report.md", funders)
        assert result == "BCA"


# ── Unit: _detect_year ───────────────────────────────────────────────────────

class TestDetectYear:
    def test_2024_as_standalone_string(self):
        assert _detect_year("2024") == 2024

    def test_year_in_hyphenated_filename(self):
        assert _detect_year("CAC-2024-Grant-Application") == 2024

    def test_year_with_spaces(self):
        assert _detect_year("Report 2023 final") == 2023

    def test_year_in_date(self):
        assert _detect_year("2024-03-15") == 2024

    def test_no_year_returns_none(self):
        assert _detect_year("CAC_Grant_Application.md") is None

    def test_non_20xx_year_returns_none(self):
        assert _detect_year("report_1999.md") is None

    def test_none_input_returns_none(self):
        assert _detect_year(None) is None


# ── Unit: _detect_type ───────────────────────────────────────────────────────

class TestDetectType:
    def test_detects_application(self):
        result = _detect_type("CAC__2024_Grant__Application.md", DEFAULT_TYPE_PATTERNS)
        assert "application" in result

    def test_detects_report(self):
        result = _detect_type("Final_Report_2024.pdf", DEFAULT_TYPE_PATTERNS)
        assert "report" in result

    def test_detects_multiple_types(self):
        result = _detect_type("OAC__Budget_Report_2024.xlsx", DEFAULT_TYPE_PATTERNS)
        assert "budget" in result
        assert "report" in result

    def test_detects_notification(self):
        result = _detect_type("CAC__Notification_2024.docx", DEFAULT_TYPE_PATTERNS)
        assert "notification" in result

    def test_detects_activity_list(self):
        result = _detect_type("Activity List 2024.pdf", DEFAULT_TYPE_PATTERNS)
        assert "activity_list" in result

    def test_detects_staff_board(self):
        result = _detect_type("Staff_Board_Bios_2024.md", DEFAULT_TYPE_PATTERNS)
        assert "staff_board" in result

    def test_no_match_returns_empty(self):
        result = _detect_type("mystery_file_2024.md", DEFAULT_TYPE_PATTERNS)
        assert result == []

    def test_matches_exact_case_in_defaults(self):
        result = _detect_type("OAC__Application_2024.pdf", DEFAULT_TYPE_PATTERNS)
        assert "application" in result

    def test_uses_custom_patterns_from_config(self):
        custom = {"custom_type": [r"XYZ"]}
        result = _detect_type("something_XYZ_2024.md", custom)
        assert "custom_type" in result


# ── Unit: _detect_draft ──────────────────────────────────────────────────────

class TestDetectDraft:
    def test_draft_in_filename(self):
        assert _detect_draft("draft_application.md") is True

    def test_prep_in_filename(self):
        assert _detect_draft("prep_notes_2024.md") is True

    def test_todo_in_filename(self):
        assert _detect_draft("TODO_report.docx") is True

    def test_working_in_filename(self):
        assert _detect_draft("working_draft_v2.pdf") is True

    def test_not_draft(self):
        assert _detect_draft("Final_Report_2024.md") is False

    def test_case_insensitive(self):
        assert _detect_draft("DRAFT_v1.md") is True
        assert _detect_draft("Working_Copy.pdf") is True


# ── Unit: _get_type_patterns ─────────────────────────────────────────────────

class TestGetTypePatterns:
    def test_uses_config_doc_types_when_dict(self):
        config = make_scanner_config(doc_types={"custom": [r"pattern"]})
        result = _get_type_patterns(config)
        assert result == {"custom": [r"pattern"]}

    def test_falls_back_to_defaults_when_not_dict(self):
        config = make_scanner_config(doc_types=None)
        result = _get_type_patterns(config)
        assert result == DEFAULT_TYPE_PATTERNS

    def test_handles_missing_doc_types(self):
        config = ProjectConfig(funders={}, doc_types=[])
        result = _get_type_patterns(config)
        assert result == DEFAULT_TYPE_PATTERNS


# ── Unit: _cost_per_doc ─────────────────────────────────────────────────────

class TestCostPerDoc:
    def test_basic_calculation(self):
        config = make_scanner_config()
        cost = _cost_per_doc(1000, 1000, config)
        assert cost == pytest.approx(0.00042, abs=0.0001)

    def test_zero_tokens(self):
        config = make_scanner_config()
        cost = _cost_per_doc(0, 0, config)
        assert cost == 0.0


# ── Integration: scan_archive ────────────────────────────────────────────────

class TestScanArchive:
    def test_discovers_files_by_type(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "OAC__2024_Grant__Application.md").write_text("# Application")
        (archive / "CAC__Final_Report_2023.pdf").write_text("dummy")
        (archive / "BCAC_Budget_2022.xlsx").write_text("dummy")
        (archive / "random_file.txt").write_text("dummy")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert report["total_files"] == 3
        assert ".md" in report["by_extension"]
        assert ".pdf" in report["by_extension"]
        assert ".xlsx" in report["by_extension"]
        assert ".txt" not in report["by_extension"]

    def test_funder_detection_from_filenames(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "CAC__2024_Grant__Application.md").write_text("# App")
        (archive / "OAC__2024_Report.md").write_text("# Report")
        (archive / "BCAC__2023_Budget.xlsx").write_text("dummy")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert "CAC" in report["by_funder"]
        assert "OAC" in report["by_funder"]
        assert "BCAC" in report["by_funder"]
        assert report["by_funder"]["CAC"]["count"] == 1
        assert report["by_funder"]["CAC"]["full_name"] == "Canada Council for the Arts"

    def test_funder_detection_from_directory_paths(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "CAC").mkdir()
        (archive / "CAC" / "application_2024.md").write_text("# App")
        (archive / "OAC").mkdir()
        (archive / "OAC" / "report_2023.pdf").write_text("dummy")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert "CAC" in report["by_funder"]
        assert "OAC" in report["by_funder"]
        assert report["by_funder"]["CAC"]["count"] == 1

    def test_year_detection(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "CAC-2024-Grant.md").write_text("# 2024")
        (archive / "CAC-2023-Report.md").write_text("# 2023")
        (archive / "CAC_NoYear_App.md").write_text("# no year")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert report["by_year"] == {2024: 1, 2023: 1}
        assert report["by_funder"]["CAC"]["years"] == [2023, 2024]

    def test_document_type_detection(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "CAC__Application_2024.md").write_text("# App")
        (archive / "OAC__Final_Report_2023.md").write_text("# Report")
        (archive / "BCAC__Budget_2024.xlsx").write_text("dummy")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert report["by_type"]["application"] == 1
        assert report["by_type"]["report"] == 1
        assert report["by_type"]["budget"] == 1

    def test_draft_detection(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "draft_application.md").write_text("# draft")
        (archive / "Final_Report.pdf").write_text("final")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert "draft_application.md" in report["likely_drafts"]
        assert "Final_Report.pdf" not in report["likely_drafts"]

    def test_unrecognized_file_types(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "mystery_document.md").write_text("nothing")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert "mystery_document.md" in report["unrecognized"]

    def test_empty_directory(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert report["total_files"] == 0
        assert report["by_extension"] == {}
        assert report["by_funder"] == {}
        assert report["by_year"] == {}

    def test_directory_with_no_supported_files(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "notes.txt").write_text("text file")
        (archive / "image.png").write_text("image file")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert report["total_files"] == 0

    def test_mixed_file_types(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "app.pdf").write_text("pdf")
        (archive / "report.docx").write_text("docx")
        (archive / "budget.xlsx").write_text("xlsx")
        (archive / "notes.md").write_text("md")
        (archive / "old.doc").write_text("doc")
        (archive / "legacy.xls").write_text("xls")
        (archive / "image.png").write_text("png")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert report["total_files"] == 6
        assert report["by_extension"] == {
            ".pdf": 1, ".docx": 1, ".xlsx": 1, ".md": 1, ".doc": 1, ".xls": 1,
        }

    def test_report_structure_keys(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "CAC__2024_Application.md").write_text("# App")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        expected_keys = {
            "source_path", "total_files", "by_extension", "by_funder",
            "by_year", "by_type", "unrecognized", "likely_drafts",
            "estimated_costs", "estimated_time_minutes",
        }
        assert set(report.keys()) == expected_keys

    def test_estimated_costs_structure(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "CAC__2024_Application.md").write_text("# App")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        costs = report["estimated_costs"]
        assert "conversion_usd" in costs
        assert "llm_rewrite_usd" in costs
        assert "llm_prioritize_usd" in costs
        assert "wiki_compile_usd" in costs
        assert "total_usd" in costs
        assert isinstance(costs["total_usd"], float)

    def test_estimated_time_is_int(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "CAC__2024_Application.md").write_text("# App")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)
        assert isinstance(report["estimated_time_minutes"], int)

    def test_datalab_converter_cost(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "doc.pdf").write_text("pdf")

        config = make_scanner_config(converter=ConverterConfig(type="datalab"))
        report = scan_archive(str(archive), config)
        assert report["estimated_costs"]["conversion_usd"] > 0

    def test_multiple_files_same_funder_aggregated(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "CAC-2023-App.md").write_text("# 2023")
        (archive / "CAC-2024-App.md").write_text("# 2024")
        (archive / "CAC-2022-Report.md").write_text("# 2022")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert report["by_funder"]["CAC"]["count"] == 3
        assert report["by_funder"]["CAC"]["years"] == [2022, 2023, 2024]

    def test_file_with_no_funder_no_year_no_type(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "some_file.md").write_text("content")

        config = make_scanner_config()
        report = scan_archive(str(archive), config)

        assert report["total_files"] == 1
        assert "some_file.md" in report["unrecognized"]
        assert report["by_funder"] == {}


# ── format_scan_report ───────────────────────────────────────────────────────

class TestFormatScanReport:
    def test_basic_report(self):
        report = {
            "source_path": "/tmp/archive",
            "total_files": 3,
            "by_extension": {".md": 2, ".pdf": 1},
            "by_funder": {
                "CAC": {"count": 2, "full_name": "Canada Council", "years": [2023, 2024]},
                "OAC": {"count": 1, "full_name": "Ontario Arts Council", "years": [2024]},
            },
            "by_year": {2023: 1, 2024: 2},
            "by_type": {"application": 2, "report": 1},
            "unrecognized": [],
            "likely_drafts": ["draft_one.md"],
            "estimated_costs": {
                "conversion_usd": 0.00,
                "llm_rewrite_usd": 0.01,
                "llm_prioritize_usd": 0.01,
                "wiki_compile_usd": 0.02,
                "total_usd": 0.04,
            },
            "estimated_time_minutes": 5,
        }
        result = format_scan_report(report)

        assert "Archive Scan Report" in result
        assert "Files: 3 total" in result
        assert "Funders detected:" in result
        assert "CAC (2 files, 2023-2024)" in result
        assert "OAC (1 files, 2024)" in result
        assert "Document types:" in result
        assert "application: 2" in result
        assert "Likely drafts: 1 files" in result
        assert "Unrecognized: 0 files" in result
        assert "Estimated costs:" in result
        assert "Total: $0.04" in result
        assert "Estimated time: ~5 minutes" in result

    def test_report_empty_wiki(self):
        report = {
            "source_path": "/tmp/empty",
            "total_files": 0,
            "by_extension": {},
            "by_funder": {},
            "by_year": {},
            "by_type": {},
            "unrecognized": [],
            "likely_drafts": [],
        }
        result = format_scan_report(report)
        assert "Files: 0 total" in result
        assert "Funders detected:" not in result
        assert "Document types:" not in result

    def test_report_no_costs_no_time(self):
        report = {
            "source_path": "/tmp/archive",
            "total_files": 1,
            "by_extension": {".md": 1},
            "by_funder": {},
            "by_year": {},
            "by_type": {},
            "unrecognized": [],
            "likely_drafts": [],
        }
        result = format_scan_report(report)
        assert "Estimated costs:" not in result
        assert "Estimated time:" not in result

    def test_report_single_year_in_funder(self):
        report = {
            "source_path": "/tmp",
            "total_files": 1,
            "by_extension": {".md": 1},
            "by_funder": {
                "CAC": {"count": 1, "full_name": "Canada Council", "years": [2024]},
            },
            "by_year": {},
            "by_type": {},
            "unrecognized": [],
            "likely_drafts": [],
        }
        result = format_scan_report(report)
        assert "CAC (1 files, 2024)" in result

    def test_report_no_extensions(self):
        report = {
            "source_path": "/tmp",
            "total_files": 1,
            "by_extension": {},
            "by_funder": {},
            "by_year": {},
            "by_type": {},
            "unrecognized": [],
            "likely_drafts": [],
        }
        result = format_scan_report(report)
        assert "Files: 1 total" in result

    def test_report_with_datalab_cost(self):
        report = {
            "source_path": "/tmp",
            "total_files": 2,
            "by_extension": {".pdf": 2},
            "by_funder": {},
            "by_year": {},
            "by_type": {},
            "unrecognized": [],
            "likely_drafts": [],
            "estimated_costs": {
                "conversion_usd": 0.12,
                "llm_rewrite_usd": 0.01,
                "llm_prioritize_usd": 0.00,
                "wiki_compile_usd": 0.01,
                "total_usd": 0.14,
            },
            "estimated_time_minutes": 10,
        }
        result = format_scan_report(report)
        assert "Conversion: $0.12 (Datalab)" in result
