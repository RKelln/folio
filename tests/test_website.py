"""Tests for website markdown ingestion."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from folio.config.schema import OrgConfig, PathsConfig
from folio.core.website import (
    _slug_from_url,
    build_website_filename,
    discover_website_files,
    ingest_website,
    parse_scraper_header,
    stage_website_file,
)
from tests.conftest import make_test_config


def _make_test_content(url="https://example.com/page", scraped_at="2025-06-01T12:00:00+00:00", content_hash="abc123def4567890"):
    return (
        f'<!-- source: {url} | scraped: {scraped_at} | hash: {content_hash} -->\n'
        '\n'
        '# Test Page\n'
        '\n'
        'This is the page body content.\n'
    )


def _make_config(raw_md_path, abbreviation="TEST"):
    """Build a test config with specified raw_md path."""
    return make_test_config(
        org=OrgConfig(
            name="Test Organization",
            abbreviation=abbreviation,
            description="A test organization.",
        ),
        paths=PathsConfig(
            raw_archive="./archive/",
            raw_md=str(raw_md_path),
            clean_md=str(raw_md_path.parent / "clean_md"),
            rewrite_md=str(raw_md_path.parent / "rewrite_md"),
            wiki_project=str(raw_md_path.parent / "wiki"),
        ),
    )


# ── discover_website_files ──────────────────────────────────────────────────


class TestDiscoverWebsiteFiles:
    def test_single_file(self, tmp_path):
        f = tmp_path / "page.md"
        f.write_text("content")
        result = discover_website_files(f)
        assert result == [f.resolve()]

    def test_single_file_non_md(self, tmp_path):
        f = tmp_path / "page.txt"
        f.write_text("content")
        result = discover_website_files(f)
        assert result == []

    def test_directory(self, tmp_path):
        (tmp_path / "a.md").write_text("a")
        (tmp_path / "b.md").write_text("b")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.md").write_text("c")
        (tmp_path / "note.txt").write_text("skip")

        result = discover_website_files(tmp_path)
        names = [p.name for p in result]
        assert names == ["a.md", "b.md", "c.md"]

    def test_empty_dir(self, tmp_path):
        result = discover_website_files(tmp_path)
        assert result == []

    def test_nonexistent_path(self, tmp_path):
        result = discover_website_files(tmp_path / "does_not_exist")
        assert result == []

    def test_directory_sorted_output(self, tmp_path):
        (tmp_path / "c.md").write_text("c")
        (tmp_path / "a.md").write_text("a")
        (tmp_path / "b.md").write_text("b")
        result = discover_website_files(tmp_path)
        names = [p.name for p in result]
        assert names == ["a.md", "b.md", "c.md"]


# ── parse_scraper_header ────────────────────────────────────────────────────


class TestParseScraperHeader:
    def test_valid_header(self):
        content = (
            '<!-- source: https://example.com/page | '
            'scraped: 2025-06-01T12:00:00+00:00 | '
            'hash: abc123def4567890 -->\n'
            '# Body\n'
        )
        result = parse_scraper_header(content)
        assert result is not None
        assert result["url"] == "https://example.com/page"
        assert result["scraped_at"] == "2025-06-01T12:00:00+00:00"
        assert result["hash"] == "abc123def4567890"

    def test_missing_header(self):
        content = "# No header\n\nBody content.\n"
        result = parse_scraper_header(content)
        assert result is None

    def test_malformed_header(self):
        content = "<!-- not a scraper header -->\n# Body\n"
        result = parse_scraper_header(content)
        assert result is None

    def test_header_not_first_non_blank_line(self):
        content = "\n\n<!-- source: https://x.com | scraped: 2025-01-01T00:00:00Z | hash: h -->\n# Body\n"
        result = parse_scraper_header(content)
        assert result is not None  # blank lines are skipped

    def test_header_after_visible_text(self):
        content = "# Title\n<!-- source: https://x.com | scraped: 2025-01-01T00:00:00Z | hash: h -->\n"
        result = parse_scraper_header(content)
        assert result is None  # first non-blank line is # Title

    def test_extra_whitespace(self):
        content = (
            '  <!--  source: https://example.com/page  |  '
            'scraped: 2025-06-01T12:00:00+00:00  |  '
            'hash: abc123def4567890  -->\n'
            '# Body\n'
        )
        result = parse_scraper_header(content)
        assert result is not None
        assert result["url"] == "https://example.com/page"

    def test_url_with_special_chars_in_path(self):
        content = (
            '<!-- source: https://example.com/path/to/article?q=1&lang=en | '
            'scraped: 2025-01-01T00:00:00Z | '
            'hash: abc123 -->\n'
        )
        result = parse_scraper_header(content)
        assert result is not None
        # URL up to first whitespace/special - the \S+ matches
        # non-whitespace which includes ? and &
        assert "example.com" in result["url"]

    def test_empty_content(self):
        result = parse_scraper_header("")
        assert result is None

    def test_content_with_only_blank_lines(self):
        result = parse_scraper_header("\n\n\n")
        assert result is None


# ── _slug_from_url ──────────────────────────────────────────────────────────


class TestSlugFromUrl:
    def test_simple_path(self):
        assert _slug_from_url("https://example.com/about") == "about"

    def test_path_with_extension(self):
        assert _slug_from_url("https://example.com/pages/about.html") == "about"

    def test_path_with_trailing_slash(self):
        assert _slug_from_url("https://example.com/about/") == "about"

    def test_deep_path(self):
        assert _slug_from_url("https://example.com/section/sub/page") == "page"

    def test_path_with_special_chars(self):
        slug = _slug_from_url("https://example.com/our-mission & vision")
        assert "_" in slug
        assert " " not in slug

    def test_no_path(self):
        result = _slug_from_url("https://example.com")
        assert result == "example_com"

    def test_no_path_no_host(self):
        result = _slug_from_url("https:///")
        assert result == "webpage"

    def test_empty_url(self):
        result = _slug_from_url("")
        assert result == "webpage"


# ── build_website_filename ──────────────────────────────────────────────────


class TestBuildWebsiteFilename:
    def test_normal_case(self):
        result = build_website_filename("ORG", "2025-06-01T12:00:00+00:00", "about")
        assert result == "ORG__2025-06-01__about__webpage.md"

    def test_special_chars_in_slug(self):
        result = build_website_filename("ORG", "2025-06-01T12:00:00+00:00", "about_us")
        assert result == "ORG__2025-06-01__about_us__webpage.md"

    def test_date_only(self):
        result = build_website_filename("ORG", "2025-06-01", "contact")
        assert result == "ORG__2025-06-01__contact__webpage.md"

    def test_short_abbrev(self):
        result = build_website_filename("A", "2025-01-15T00:00:00Z", "home")
        assert result == "A__2025-01-15__home__webpage.md"


# ── stage_website_file ──────────────────────────────────────────────────────


class TestStageWebsiteFile:
    def test_normal_case(self, tmp_path):
        md_file = tmp_path / "page.md"
        md_file.write_text(_make_test_content())
        raw_md = tmp_path / "raw_md"
        config = _make_config(raw_md)

        result = stage_website_file(md_file, config)
        assert result["status"] == "staged"
        assert result["filename"] == "TEST__2025-06-01__page__webpage.md"
        assert result["source_url"] == "https://example.com/page"
        assert result["scraped_at"] == "2025-06-01T12:00:00+00:00"
        assert Path(result["output_path"]).exists()

        written = Path(result["output_path"]).read_text()
        assert 'funder: "TEST"' in written
        assert 'type: "webpage"' in written
        assert "written: 2025" in written
        assert 'source_url: "https://example.com/page"' in written

    def test_missing_header(self, tmp_path):
        md_file = tmp_path / "bad.md"
        md_file.write_text("# No header\n")
        raw_md = tmp_path / "raw_md"
        config = _make_config(raw_md)

        result = stage_website_file(md_file, config)
        assert result["status"] == "error"
        assert "No scraper comment found" in result["error"]

    def test_dry_run_mode(self, tmp_path):
        md_file = tmp_path / "page.md"
        md_file.write_text(_make_test_content())
        raw_md = tmp_path / "raw_md"
        config = _make_config(raw_md)

        result = stage_website_file(md_file, config, dry_run=True)
        assert result["status"] == "would_stage"
        assert not Path(result["output_path"]).exists()

    def test_name_override(self, tmp_path):
        md_file = tmp_path / "page.md"
        md_file.write_text(_make_test_content(url="https://example.com/some/long/path.html"))
        raw_md = tmp_path / "raw_md"
        config = _make_config(raw_md)

        result = stage_website_file(md_file, config, name_override="custom-slug")
        assert result["status"] == "staged"
        assert "custom_slug" in result["filename"]

    def test_unparseable_scraped_at(self, tmp_path):
        md_file = tmp_path / "bad_date.md"
        md_file.write_text(
            '<!-- source: https://x.com | scraped: not-a-date | hash: abc -->\n# Body\n'
        )
        raw_md = tmp_path / "raw_md"
        config = _make_config(raw_md)

        result = stage_website_file(md_file, config)
        assert result["status"] == "error"
        assert "Cannot extract year" in result["error"]

    def test_frontmatter_replaces_existing(self, tmp_path):
        md_file = tmp_path / "page.md"
        md_file.write_text(
            '---\n'
            'funder: OLD\n'
            'type: old_type\n'
            'written: 2020\n'
            '---\n'
            '\n'
            + _make_test_content()
        )
        raw_md = tmp_path / "raw_md"
        config = _make_config(raw_md)

        result = stage_website_file(md_file, config)
        assert result["status"] == "staged"

        written = Path(result["output_path"]).read_text()
        # Only one frontmatter block
        assert written.count('---') == 2
        assert 'funder: "OLD"' not in written
        assert 'funder: "TEST"' in written
        assert "written: 2025" in written

    def test_unreadable_file(self, tmp_path):
        raw_md = tmp_path / "raw_md"
        config = _make_config(raw_md)
        nonexistent = tmp_path / "nonexistent.md"

        result = stage_website_file(nonexistent, config)
        assert result["status"] == "error"
        assert "Cannot read file" in result["error"]


# ── ingest_website ──────────────────────────────────────────────────────────


class TestIngestWebsite:
    def test_no_md_files(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        result = ingest_website(empty, config_path=str(config_file))
        assert result["status"] == "ok"
        assert result["staging"]["files_found"] == 0
        assert result["staging"]["files_staged"] == 0
        assert "No .md files found" in result.get("warning", "")

    def test_dry_run_integration(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "page1.md").write_text(_make_test_content(url="https://example.com/a"))
        (src / "page2.md").write_text(_make_test_content(url="https://example.com/b"))

        raw_md = tmp_path / "raw_md"
        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        result = ingest_website(src, config_path=str(config_file), stages=[], dry_run=True)
        assert result["status"] == "ok"
        assert result["staging"]["files_found"] == 2
        assert result["staging"]["files_staged"] == 2
        assert result["staging"]["files_skipped"] == 0
        assert result["pipeline"] is None
        assert not list(raw_md.glob("*.md"))

    def test_stages_none_skips_pipeline(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "page1.md").write_text(_make_test_content(url="https://example.com/a"))

        raw_md = tmp_path / "raw_md"
        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        result = ingest_website(src, config_path=str(config_file), stages=[])
        assert result["pipeline"] is None
        assert list(raw_md.glob("*.md"))

    def test_stages_clean_runs_pipeline(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "page1.md").write_text(_make_test_content(url="https://example.com/a"))

        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        result = ingest_website(src, config_path=str(config_file), stages=["clean"])
        assert result["pipeline"] is not None
        pipeline = result["pipeline"]
        assert "stages" in pipeline
        assert "clean" in pipeline["stages"]

    def test_mixed_valid_and_invalid_files(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "valid.md").write_text(_make_test_content(url="https://example.com/a"))
        (src / "invalid.md").write_text("# No scraper header\n")

        raw_md = tmp_path / "raw_md"
        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        result = ingest_website(src, config_path=str(config_file), stages=[])
        assert result["staging"]["files_found"] == 2
        assert result["staging"]["files_staged"] == 1
        assert result["staging"]["files_skipped"] == 1
        assert len(result["staging"]["errors"]) == 1
        assert "invalid.md" in result["staging"]["errors"][0]["file"]

    def test_single_file_with_name_override(self, tmp_path):
        md_file = tmp_path / "page.md"
        md_file.write_text(
            _make_test_content(url="https://example.com/long/path/to/article.html")
        )
        raw_md = tmp_path / "raw_md"
        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        result = ingest_website(md_file, config_path=str(config_file), name="my-article", stages=[])
        assert result["staging"]["files_found"] == 1
        assert result["staging"]["files_staged"] == 1
        staged_file = list(raw_md.glob("*.md"))[0]
        assert "my_article" in staged_file.name

    def test_directory_name_override_ignored(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "page.md").write_text(
            _make_test_content(url="https://example.com/about")
        )
        raw_md = tmp_path / "raw_md"
        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        result = ingest_website(src, config_path=str(config_file), name="should-be-ignored", stages=[])
        staged_file = list(raw_md.glob("*.md"))[0]
        assert "about" in staged_file.name
        assert "should_be_ignored" not in staged_file.name

    @patch("folio.core.website.run_pipeline")
    def test_pipeline_exception_caught(self, mock_run, tmp_path):
        mock_run.side_effect = RuntimeError("Boom")
        src = tmp_path / "source"
        src.mkdir()
        (src / "page.md").write_text(_make_test_content())

        raw_md = tmp_path / "raw_md"
        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        result = ingest_website(src, config_path=str(config_file), stages=["clean"])
        assert result["pipeline"] is not None
        assert result["pipeline"]["status"] == "error"
        assert "Boom" in result["pipeline"]["error"]


# ── CLI tests ───────────────────────────────────────────────────────────────


class TestCLI:
    def test_help(self, capsys):
        from folio.cli.website import main

        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "usage:" in combined.lower() or "usage" in combined
        assert "folio website" in combined

    def test_version(self, capsys):
        from folio.cli.website import main

        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        from folio import __version__
        assert f"v{__version__}" in combined

    def test_missing_source(self, capsys):
        from folio.cli.website import main

        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2
        captured = capsys.readouterr()
        assert "error:" in (captured.out + captured.err).lower()

    def test_nonexistent_source(self, capsys):
        from folio.cli.website import main

        with pytest.raises(SystemExit) as exc:
            main(["--source", "/nonexistent/path"])
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_list_dry_run(self, tmp_path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.md").write_text(
            _make_test_content(url="https://example.com/a", scraped_at="2025-01-01T00:00:00Z")
        )
        (src / "b.md").write_text(
            _make_test_content(url="https://example.com/b", scraped_at="2025-02-01T00:00:00Z")
        )

        from folio.cli.website import main

        main(["--source", str(src), "--list"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["source_url"] == "https://example.com/a"
        assert data[1]["source_url"] == "https://example.com/b"
        assert data[0]["would_stage"] is True

    def test_list_with_bad_files(self, tmp_path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "good.md").write_text(_make_test_content())
        (src / "bad.md").write_text("# No header\n")

        from folio.cli.website import main

        main(["--source", str(src), "--list"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 2
        good = next(e for e in data if "good.md" in e["source_file"])
        bad = next(e for e in data if "bad.md" in e["source_file"])
        assert good["would_stage"] is True
        assert bad["would_stage"] is False
        assert "No scraper comment found" in bad["error"]

    def test_json_output(self, tmp_path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "page.md").write_text(_make_test_content())

        from folio.cli.website import main

        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        main([
            "--config", str(config_file),
            "--source", str(src),
            "--stages", "none",
            "--json",
        ])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "ok"
        assert "staging" in data
        assert data["staging"]["files_staged"] == 1

    def test_unknown_stage(self, tmp_path, capsys):
        from folio.cli.website import main

        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        with pytest.raises(SystemExit) as exc:
            main([
                "--config", str(config_file),
                "--source", str(tmp_path),
                "--stages", "scan,convert",
            ])
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Unknown stage" in captured.err

    def test_stages_none_skips(self, tmp_path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "page.md").write_text(_make_test_content())

        from folio.cli.website import main

        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        main([
            "--config", str(config_file),
            "--source", str(src),
            "--stages", "none",
        ])
        captured = capsys.readouterr()
        assert "Files staged: 1" in captured.out

    def test_name_warning_in_dir_mode(self, tmp_path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "page.md").write_text(_make_test_content())

        from folio.cli.website import main

        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        main([
            "--config", str(config_file),
            "--source", str(src),
            "--name", "my-slug",
            "--stages", "none",
        ])
        captured = capsys.readouterr()
        assert "Warning" in captured.err
        assert "--name is ignored" in captured.err

    def test_dry_run_human_output(self, tmp_path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "page.md").write_text(_make_test_content())

        from folio.cli.website import main

        config_file = tmp_path / "folio.yaml"
        _write_minimal_folio_yaml(config_file, tmp_path)

        main([
            "--config", str(config_file),
            "--source", str(src),
            "--stages", "none",
            "--dry-run",
        ])
        captured = capsys.readouterr()
        assert "Files found: 1" in captured.out
        assert "Files staged: 1" in captured.out

    def test_missing_config_exit(self, tmp_path, capsys):
        src = tmp_path / "source"
        src.mkdir()
        (src / "page.md").write_text(_make_test_content())

        from folio.cli.website import main

        with pytest.raises(SystemExit) as exc:
            main([
                "--config", str(tmp_path / "nonexistent.yaml"),
                "--source", str(src),
            ])
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err


def _write_minimal_folio_yaml(path: Path, work_dir: Path) -> None:
    """Write a minimal folio.yaml for CLI tests."""
    path.write_text(f"""\
project:
  name: Test Project
org:
  name: Test Org
  abbreviation: TEST
paths:
  raw_archive: ./archive/
  raw_md: {work_dir / 'raw_md'}/
  clean_md: {work_dir / 'clean_md'}/
  rewrite_md: {work_dir / 'rewrite_md'}/
  wiki_project: {work_dir / 'wiki'}/
funders:
  TAC: Toronto Arts Council
doc_types:
  - application
  - report
  - webpage
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
""")
