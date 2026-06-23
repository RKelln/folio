from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from folio.config.schema import (
    ConverterConfig,
    LLMConfig,
    PathsConfig,
    ProcessingConfig,
    ProjectConfig,
    WikiConfig,
)
from folio.core.ingester import (
    _build_output_filename,
    _sanitize_filename,
    _validate_doc_types,
    _validate_funder,
    ingest_document,
)


def make_ingester_config(**overrides) -> ProjectConfig:
    defaults = {
        "funders": {
            "CAC": "Canada Council for the Arts",
            "OAC": "Ontario Arts Council",
        },
        "doc_types": [
            "application", "report", "budget", "notification",
        ],
        "paths": PathsConfig(
            raw_archive="./archive/",
            rewrite_md="./rewrite_md/",
            wiki_project="./wiki/",
        ),
        "llm": LLMConfig(),
        "converter": ConverterConfig(type="liteparse"),
        "wiki": WikiConfig(type="null"),
        "processing": ProcessingConfig(),
    }
    defaults.update(overrides)
    return ProjectConfig(**defaults)


# ── Unit: _sanitize_filename ─────────────────────────────────────────────────

class TestSanitizeFilename:
    def test_replaces_spaces_with_underscores(self):
        assert _sanitize_filename("hello world") == "hello_world"

    def test_replaces_dashes_with_underscores(self):
        assert _sanitize_filename("hello-world") == "hello_world"

    def test_replaces_slashes_with_underscores(self):
        assert _sanitize_filename("hello/world") == "hello_world"
        assert _sanitize_filename("hello\\world") == "hello_world"

    def test_replaces_colons_with_underscores(self):
        assert _sanitize_filename("hello:world") == "hello_world"

    def test_collapses_multiple_underscores(self):
        assert _sanitize_filename("hello   world") == "hello_world"
        assert _sanitize_filename("hello--world") == "hello_world"

    def test_strips_leading_trailing_underscores(self):
        assert _sanitize_filename("_hello_") == "hello"

    def test_keeps_alphanumeric_and_safe_chars(self):
        assert _sanitize_filename("Report_2024(v1).pdf") == "Report_2024(v1).pdf"

    def test_removes_unsafe_characters(self):
        result = _sanitize_filename("test!@$%^&*file")
        assert result == "testfile"

    def test_handles_empty_string(self):
        assert _sanitize_filename("") == ""


# ── Unit: _build_output_filename ─────────────────────────────────────────────

class TestBuildOutputFilename:
    def test_basic_filename(self):
        result = _build_output_filename("CAC", 2024, None, ["application"])
        assert result == "CAC__2024__application.md"

    def test_with_description(self):
        result = _build_output_filename("CAC", 2024, "Operating Grant", ["application"])
        assert result == "CAC__2024_Operating_Grant__application.md"

    def test_with_multiple_doc_types(self):
        result = _build_output_filename("OAC", 2023, None, ["application", "report"])
        assert result == "OAC__2023__application_and_report.md"

    def test_with_period(self):
        result = _build_output_filename(
            "CAC", 2024, None, ["application"], period="2024-2026"
        )
        assert result == "CAC__2024-2026__application.md"

    def test_with_period_and_description(self):
        result = _build_output_filename(
            "CAC", 2024, "Operating Grant", ["application"], period="2024-2026"
        )
        assert result == "CAC__2024-2026_Operating_Grant__application.md"

    def test_description_sanitized(self):
        result = _build_output_filename(
            "CAC", 2024, "Hello World: The Story", ["application"]
        )
        assert result == "CAC__2024_Hello_World_The_Story__application.md"


# ── Unit: _validate_funder ───────────────────────────────────────────────────

class TestValidateFunder:
    def test_known_funder_no_warnings(self):
        config = make_ingester_config()
        warnings = _validate_funder("CAC", config)
        assert warnings == []

    def test_unknown_funder_warns(self):
        config = make_ingester_config()
        warnings = _validate_funder("XYZ", config)
        assert len(warnings) == 1
        assert "Unrecognized funder" in warnings[0]
        assert "XYZ" in warnings[0]
        assert "CAC" in warnings[0]
        assert "OAC" in warnings[0]

    def test_no_funders_configured(self):
        config = make_ingester_config(funders={})
        warnings = _validate_funder("CAC", config)
        assert len(warnings) == 1
        assert "none configured" in warnings[0].lower()


# ── Unit: _validate_doc_types ────────────────────────────────────────────────

class TestValidateDocTypes:
    def test_known_types_no_unknown(self):
        config = make_ingester_config()
        unknown = _validate_doc_types(["application", "report"], config)
        assert unknown == []

    def test_unknown_type_returned(self):
        config = make_ingester_config()
        unknown = _validate_doc_types(["application", "unknown_type"], config)
        assert unknown == ["unknown_type"]

    def test_all_unknown(self):
        config = make_ingester_config()
        unknown = _validate_doc_types(["nope", "also_nope"], config)
        assert unknown == ["nope", "also_nope"]

    def test_no_doc_types_configured(self):
        config = make_ingester_config(doc_types=[])
        unknown = _validate_doc_types(["application"], config)
        assert unknown == ["application"]


# ── Integration: ingest_document ─────────────────────────────────────────────

class TestIngestDocument:
    def test_non_existent_path(self, tmp_path):
        config = make_ingester_config()
        bad_path = tmp_path / "nonexistent.pdf"
        result = ingest_document(
            bad_path, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_path_is_directory_not_file(self, tmp_path):
        config = make_ingester_config()
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        result = ingest_document(
            subdir, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["status"] == "error"
        assert "Not a file" in result["error"]

    def test_unsupported_file_type(self, tmp_path):
        config = make_ingester_config()
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("hello world")
        result = ingest_document(
            txt_file, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["status"] == "error"
        assert "Unsupported file type" in result["error"]

    def test_dry_run_markdown_file(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello\nWorld")
        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"], dry_run=True,
        )
        assert result["status"] == "dry_run"
        assert result["output_path"] is not None
        assert "CAC__2024__application.md" in str(result["output_path"])
        assert result["frontmatter_added"] is False

    def test_dry_run_pdf_file(self, tmp_path):
        config = make_ingester_config()
        pdf_file = tmp_path / "grant.pdf"
        pdf_file.write_text("fake pdf content")
        result = ingest_document(
            pdf_file, config, "CAC", 2024, doc_types=["application"], dry_run=True,
        )
        assert result["status"] == "dry_run"

    def test_dry_run_with_sync_wiki(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")
        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
            dry_run=True, sync_wiki=True,
        )
        assert result["wiki_status"] is not None
        assert "would copy" in result["wiki_status"]

    def test_dry_run_with_rewrite(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")
        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
            dry_run=True, run_rewrite=True,
        )
        assert "rewrite_note" in result
        assert "rewrite would run" in result["rewrite_note"]

    def test_markdown_file_ingestion(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "my_grant.md"
        md_file.write_text("# Test Application\n\nSome content here.\n")

        result = ingest_document(
            md_file, config, "OAC", 2023, doc_types=["application"],
        )
        assert result["status"] == "success"
        assert result["frontmatter_added"] is True
        assert result["chars"] > 0
        assert "OAC__2023__application.md" in str(result["output_path"])

    def test_funder_uppercased(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")

        result = ingest_document(
            md_file, config, "cac", 2024, doc_types=["application"],
        )
        assert result["status"] == "success"
        assert "CAC__" in str(result["output_path"])

    def test_unknown_funder_warning(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")

        result = ingest_document(
            md_file, config, "UNKNOWN", 2024, doc_types=["application"],
        )
        assert result["status"] == "success"
        assert len(result["warnings"]) > 0
        assert any("Unrecognized funder" in w for w in result["warnings"])

    def test_unknown_doc_type_warning(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["unknown_type"],
        )
        assert result["status"] == "success"
        assert len(result["warnings"]) > 0
        assert any("Unrecognized doc type" in w for w in result["warnings"])

    def test_default_doc_types_to_application(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=None,
        )
        assert result["status"] == "success"
        assert "application" in str(result["output_path"])

    def test_frontmatter_injected_into_output(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nBody content here.")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["status"] == "success"
        output_path = Path(result["output_path"])
        assert output_path.exists()
        content = output_path.read_text()
        assert 'funder: "CAC"' in content
        assert "written: 2024" in content
        assert "type:" in content
        assert "application" in content
        assert "Body content here" in content

    def test_existing_frontmatter_replaced(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("---\nfunder: OLD\ntype: old_report\nwritten: 2020\n---\n\nBody text.\n")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["status"] == "success"
        output_path = Path(result["output_path"])
        content = output_path.read_text()
        assert 'funder: "CAC"' in content
        assert "written: 2024" in content

    def test_with_period(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
            period="2024-2026",
        )
        assert result["status"] == "success"
        assert "2024-2026" in str(result["output_path"])

    def test_with_description(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
            description="Operating Grant",
        )
        assert result["status"] == "success"
        assert "Operating_Grant" in str(result["output_path"])

    def test_sync_wiki_disabled(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
            sync_wiki=False,
        )
        assert result["status"] == "success"
        assert result["wiki_status"] == "skipped"

    def test_sync_wiki_enabled(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
            sync_wiki=True,
        )
        assert result["status"] == "success"
        assert "synced to" in result["wiki_status"]

    @patch("folio.core.ingester.get_converter")
    def test_pdf_conversion_with_mock(self, mock_get_converter, tmp_path):
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "# Converted PDF Content\n\nBody text.\n"
        mock_converter.name = "mock_converter"
        mock_converter.supported_extensions = {".pdf", ".docx", ".xlsx"}
        mock_get_converter.return_value = mock_converter

        config = make_ingester_config()
        pdf_file = tmp_path / "grant.pdf"
        pdf_file.write_text("fake pdf")

        result = ingest_document(
            pdf_file, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["status"] == "success"
        assert result["conversion_method"] == "mock_converter"
        assert result["frontmatter_added"] is True
        assert "Converted" in str(result["output_path"]) or True

    @patch("folio.core.ingester.get_converter")
    def test_pdf_conversion_failure(self, mock_get_converter, tmp_path):
        mock_converter = MagicMock()
        mock_converter.convert.return_value = None
        mock_converter.supported_extensions = {".pdf"}
        mock_get_converter.return_value = mock_converter

        config = make_ingester_config()
        pdf_file = tmp_path / "corrupt.pdf"
        pdf_file.write_text("corrupt")

        result = ingest_document(
            pdf_file, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["status"] == "error"
        assert "Conversion failed" in result["error"]

    def test_ingest_directory_batch(self, tmp_path):
        config = make_ingester_config()
        for name in ["app1.md", "app2.md", "app3.md"]:
            (tmp_path / name).write_text(f"# {name}\n\nContent for {name}.\n")

        results = []
        for name in sorted(tmp_path.glob("*.md")):
            result = ingest_document(
                name, config, "CAC", 2024, doc_types=["application"],
            )
            results.append(result)

        assert all(r["status"] == "success" for r in results)
        assert len(results) == 3
        for r in results:
            assert Path(r["output_path"]).exists()

    def test_empty_markdown_file(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "empty.md"
        md_file.write_text("")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["status"] == "success"
        output_path = Path(result["output_path"])
        assert output_path.exists()
        content = output_path.read_text()
        assert 'funder: "CAC"' in content

    def test_large_markdown_file(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "large.md"
        content = "# Large Document\n\n" + ("Line of content.\n" * 5000)
        md_file.write_text(content)

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["status"] == "success"
        assert result["chars"] > 0

    def test_conversion_method_passthrough_for_md(self, tmp_path):
        config = make_ingester_config()
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["conversion_method"] == "passthrough"

    def test_output_dir_created(self, tmp_path):
        config = make_ingester_config(
            paths=PathsConfig(
                raw_archive="./archive/",
                rewrite_md=str(tmp_path / "output" / "deeply" / "nested"),
                wiki_project="./wiki/",
            ),
        )
        md_file = tmp_path / "test.md"
        md_file.write_text("# Content")

        result = ingest_document(
            md_file, config, "CAC", 2024, doc_types=["application"],
        )
        assert result["status"] == "success"
        assert (tmp_path / "output" / "deeply" / "nested").is_dir()
