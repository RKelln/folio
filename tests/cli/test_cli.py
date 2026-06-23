"""Comprehensive CLI tests for all folio entry points.

Tests the `main(argv)` pattern used by every folio CLI module.
"""

from __future__ import annotations

import importlib
import json
import os

import pytest

from folio import __version__

CLI_MODULES = {
    "clean": "folio.cli.clean",
    "classify": "folio.cli.classify",
    "rewrite": "folio.cli.rewrite",
    "prioritize": "folio.cli.prioritize",
    "canonicalize": "folio.cli.canonicalize",
    "ingest": "folio.cli.ingest",
    "audit": "folio.cli.audit",
    "scan": "folio.cli.scan",
    "pipeline": "folio.cli.pipeline",
    "init": "folio.cli.init",
    "skills": "folio.cli.skills",
    "guide": "folio.cli.guide",
    "teach": "folio.cli.teach",
    "convert": "folio.cli.convert",
    "repack": "folio.cli.repack",
    "test-skills": "folio.cli.test_skills",
    "wiki": "folio.cli.wiki",
    "install-agent": "folio.cli.install_agent",
    "validate": "folio.cli.validate",
}


# ---------------------------------------------------------------------------
# 1. test_help
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(CLI_MODULES))
def test_cli_help(name, capsys):
    """Each CLI's main(['--help']) prints usage info and exits 0."""
    mod = importlib.import_module(CLI_MODULES[name])

    with pytest.raises(SystemExit) as exc:
        mod.main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert any(
        keyword in combined
        for keyword in ("usage:", "folio", "teach", "show this help")
    ), f"No usage info found in output for {name}"


# ---------------------------------------------------------------------------
# 2. test_version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(CLI_MODULES))
def test_cli_version(name, capsys):
    """Each CLI's main(['--version']) prints version and exits 0."""
    mod = importlib.import_module(CLI_MODULES[name])

    with pytest.raises(SystemExit) as exc:
        mod.main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert f"v{__version__}" in combined, f"Version not found in output for {name}"


# ---------------------------------------------------------------------------
# 3. test_missing_required_args
# ---------------------------------------------------------------------------

REQUIRED_ARG_CLIS = [
    # (module_name, expected_exit_code, expected_stderr_fragment)
    # argparse required=True args exit with code 2
    ("ingest", 2, None),
    ("scan", 2, None),
    ("canonicalize", 2, None),
    ("audit", 2, None),
    ("skills", 2, None),
    ("convert", 2, None),
    ("test-skills", 2, None),
]


@pytest.mark.parametrize("name,exit_code,_fragment", REQUIRED_ARG_CLIS)
def test_missing_required_args(name, exit_code, _fragment, capsys):
    """CLIs with required args error to stderr and exit non-zero when given []."""
    mod = importlib.import_module(CLI_MODULES[name])

    with pytest.raises(SystemExit) as exc:
        mod.main([])
    assert exc.value.code == exit_code
    captured = capsys.readouterr()
    assert captured.err or captured.out, f"No output for {name}"
    error_text = captured.err + captured.out
    assert len(error_text.strip()) > 0, f"Expected error message for {name}"


# ---------------------------------------------------------------------------
# 4. test_dry_run
# ---------------------------------------------------------------------------

@pytest.fixture
def source_dir_with_md(tmp_path):
    """Create a temp source directory containing a minimal .md file."""
    src = tmp_path / "source"
    src.mkdir()
    (src / "test.md").write_text("# Test\n\nSome content here.\n", encoding="utf-8")
    return src


@pytest.fixture
def empty_dir(tmp_path):
    """Create an empty temp directory."""
    d = tmp_path / "empty"
    d.mkdir()
    return d


def test_dry_run_clean(source_dir_with_md, capsys):
    """clean --dry-run prints 'Would clean' and exits cleanly."""
    from folio.cli.clean import main

    main(["--dry-run", "--source", str(source_dir_with_md)])
    captured = capsys.readouterr()
    assert "Would clean" in captured.out


def test_dry_run_clean_nonexistent(capsys):
    """clean --dry-run with nonexistent dir exits 1 with error."""
    from folio.cli.clean import main

    with pytest.raises(SystemExit) as exc:
        main(["--dry-run", "--source", "/nonexistent/path"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_dry_run_classify(source_dir_with_md, capsys):
    """classify --dry-run prints 'Would classify' and exits cleanly."""
    from folio.cli.classify import main

    main(["--dry-run", "--source", str(source_dir_with_md)])
    captured = capsys.readouterr()
    assert "Would classify" in captured.out


def test_dry_run_classify_nonexistent(capsys):
    """classify --dry-run with nonexistent dir exits 1 with error."""
    from folio.cli.classify import main

    with pytest.raises(SystemExit) as exc:
        main(["--dry-run", "--source", "/nonexistent/path"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_dry_run_scan(empty_dir, capsys):
    """scan --dry-run prints 'Would scan' and exits cleanly."""
    from folio.cli.scan import main

    main(["--dry-run", "--source", str(empty_dir)])
    captured = capsys.readouterr()
    assert "Would scan" in captured.out


def test_dry_run_scan_nonexistent(capsys):
    """scan --dry-run with nonexistent dir exits 1 with error."""
    from folio.cli.scan import main

    with pytest.raises(SystemExit) as exc:
        main(["--dry-run", "--source", "/nonexistent/path"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_dry_run_rewrite(source_dir_with_md, minimal_folio_yaml, capsys):
    """rewrite --dry-run prints 'Would rewrite' when config and dir exist."""
    from folio.cli.rewrite import main

    main([
        "--dry-run", "--source", str(source_dir_with_md),
        "--config", str(minimal_folio_yaml / "folio.yaml"),
    ])
    captured = capsys.readouterr()
    assert "Would rewrite" in captured.out


def test_dry_run_rewrite_no_config(source_dir_with_md, capsys):
    """rewrite --dry-run exits 1 when config file is missing."""
    from folio.cli.rewrite import main

    with pytest.raises(SystemExit) as exc:
        main(["--dry-run", "--source", str(source_dir_with_md)])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "folio.yaml" in captured.err


# ---------------------------------------------------------------------------
# 5. test_dispatcher
# ---------------------------------------------------------------------------

def test_dispatcher_empty_help(capsys):
    """main([]) prints help to stderr and exits 0."""
    from folio.cli.main import main

    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "folio" in captured.err
    assert "Available commands:" in captured.err


def test_dispatcher_dash_help(capsys):
    """main(['--help']) prints help to stderr and exits 0."""
    from folio.cli.main import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "folio" in captured.err


def test_dispatcher_dash_h(capsys):
    """main(['-h']) prints help to stderr and exits 0."""
    from folio.cli.main import main

    with pytest.raises(SystemExit) as exc:
        main(["-h"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "folio" in captured.err


def test_dispatcher_version(capsys):
    """main(['--version']) prints version to stderr and exits 0."""
    from folio.cli.main import main

    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert f"v{__version__}" in captured.err


def test_dispatcher_dash_v(capsys):
    """main(['-V']) prints version to stderr and exits 0."""
    from folio.cli.main import main

    with pytest.raises(SystemExit) as exc:
        main(["-V"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert f"v{__version__}" in captured.err


def test_dispatcher_unknown_command(capsys):
    """main(['nonexistent']) exits 1 with error message."""
    from folio.cli.main import main

    with pytest.raises(SystemExit) as exc:
        main(["nonexistent"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Unknown command" in captured.err
    assert "nonexistent" in captured.err


# ---------------------------------------------------------------------------
# 6. test_json_output
# ---------------------------------------------------------------------------

def test_json_output_clean_dry_run(source_dir_with_md, capsys):
    """clean --dry-run --json produces valid JSON with expected keys."""
    from folio.cli.clean import main

    main(["--dry-run", "--json", "--source", str(source_dir_with_md)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "files" in data
    assert "dry_run" in data
    assert data["dry_run"] is True


def test_json_output_scan(empty_dir, capsys):
    """scan --json on empty dir produces valid JSON."""
    from folio.cli.scan import main

    main(["--json", "--source", str(empty_dir)])
    captured = capsys.readouterr()
    out = captured.out
    json_start = out.find("{")
    assert json_start >= 0, f"No JSON object found in output: {out!r}"
    data = json.loads(out[json_start:])
    assert "total_files" in data
    assert "by_extension" in data


def test_json_output_guide_topic_config(capsys):
    """guide --json --topic config produces valid JSON with topic key."""
    from folio.cli.guide import main

    main(["--json", "--topic", "config"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "topic" in data
    assert data["topic"] == "config"
    assert "sections" in data


def test_json_output_guide_full(capsys):
    """guide --json (no topic) produces valid JSON for full guide."""
    from folio.cli.guide import main

    main(["--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "topic" in data
    assert data["topic"] == "full"
    assert "sections" in data


# ---------------------------------------------------------------------------
# 7. test_guide
# ---------------------------------------------------------------------------

def test_guide_topic_config(capsys):
    """guide --topic config outputs config reference text."""
    from folio.cli.guide import main

    main(["--topic", "config"])
    captured = capsys.readouterr()
    assert "CONFIG REFERENCE" in captured.out


def test_guide_topic_unknown(capsys):
    """guide --topic nonexistent exits 1 with error on stderr."""
    from folio.cli.guide import main

    with pytest.raises(SystemExit) as exc:
        main(["--topic", "nonexistent_topic"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Unknown topic" in captured.err


def test_guide_dry_run(capsys):
    """guide --dry-run prints topic list and does not output full guide."""
    from folio.cli.guide import main

    main(["--dry-run"])
    captured = capsys.readouterr()
    assert "Available topics" in captured.out
    assert "QUICK START FOR AGENTS" not in captured.out


def test_guide_full(capsys):
    """guide with no args prints full guide."""
    from folio.cli.guide import main

    main([])
    captured = capsys.readouterr()
    assert "QUICK START FOR AGENTS" in captured.out
    assert "PIPELINE STAGES" in captured.out


# ---------------------------------------------------------------------------
# 8. test_guide_positional_arg
# ---------------------------------------------------------------------------

def test_guide_positional_topic(capsys):
    """guide config (positional arg, no --topic) shows config reference."""
    from folio.cli.guide import main

    main(["config"])
    captured = capsys.readouterr()
    assert "CONFIG REFERENCE" in captured.out


def test_guide_positional_unknown(capsys):
    """guide nonexistent (positional) exits 1 with error on stderr."""
    from folio.cli.guide import main

    with pytest.raises(SystemExit) as exc:
        main(["nonexistent_topic"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Unknown topic" in captured.err


# ---------------------------------------------------------------------------
# 9. test_guide_search
# ---------------------------------------------------------------------------

def test_guide_search_with_results(capsys):
    """guide --search LLM prints matching lines."""
    from folio.cli.guide import main

    main(["--search", "LLM"])
    captured = capsys.readouterr()
    assert captured.out.strip(), "Expected search results to stdout"
    assert "LLM" in captured.out


def test_guide_search_no_results(capsys):
    """guide --search with nonexistent keyword prints error to stderr."""
    from folio.cli.guide import main

    main(["--search", "xyznonexistentzzz"])
    captured = capsys.readouterr()
    assert "No matches found" in captured.err


def test_guide_search_with_topic(capsys):
    """guide --topic config --search converter prints matches from topic text."""
    from folio.cli.guide import main

    main(["--topic", "config", "--search", "converter"])
    captured = capsys.readouterr()
    assert captured.out.strip(), "Expected search results from config topic"


def test_guide_search_json(capsys):
    """guide --search LLM --json produces structured JSON with matches list."""
    from folio.cli.guide import main

    main(["--search", "LLM", "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "search" in data
    assert data["search"] == "LLM"
    assert "matches" in data
    assert isinstance(data["matches"], list)
    assert len(data["matches"]) > 0


# ---------------------------------------------------------------------------
# 10. test_guide_dry_run_json
# ---------------------------------------------------------------------------

def test_guide_dry_run_json(capsys):
    """guide --dry-run --json produces JSON topic list."""
    from folio.cli.guide import main

    main(["--dry-run", "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "topics" in data
    assert "dry_run" in data
    assert data["dry_run"] is True
    assert isinstance(data["topics"], list)
    assert len(data["topics"]) > 0


def test_guide_dry_run_with_search_warns(capsys):
    """guide --dry-run --search warns that search is ignored."""
    from folio.cli.guide import main

    main(["--dry-run", "--search", "LLM"])
    captured = capsys.readouterr()
    assert "ignores --search" in captured.err
    assert "Available topics" in captured.out


# ---------------------------------------------------------------------------
# 11. test_init
# ---------------------------------------------------------------------------

def test_init_dry_run_profile(capsys):
    """init --profile canadian-artist-run-centre --dry-run prints preview."""
    from folio.cli.init import main

    main(["--profile", "canadian-artist-run-centre", "--dry-run"])
    captured = capsys.readouterr()
    assert "Dry run" in captured.out
    assert "Files that would be created" in captured.out
    assert "folio.yaml" in captured.out
    assert "My Artist-Run Centre" in captured.out


def test_init_json_output(tmp_path, capsys):
    """init --profile generic --json produces structured JSON output."""
    from folio.cli.init import main

    output_file = tmp_path / "folio.yaml"
    main(["--profile", "generic", "--json", "--output", str(output_file)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "files_written" in data
    assert "profile" in data
    assert data["profile"] == "generic"
    assert "warnings" in data


def test_init_dry_run_json(tmp_path, capsys):
    """init --dry-run --json produces JSON preview without writing files."""
    from folio.cli.init import main

    output_file = tmp_path / "folio.yaml"
    main(["--profile", "generic", "--dry-run", "--json", "--output", str(output_file)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "files_written" in data
    assert "config_values" in data
    assert "dry_run" in data
    assert data["dry_run"] is True


def test_init_dry_run_guided(capsys):
    """init --guided --dry-run prints preview without interactive prompts."""
    from folio.cli.init import main

    main(["--guided", "--dry-run"])
    captured = capsys.readouterr()
    assert "Dry run" in captured.out
    assert "Cannot preview guided setup" in captured.out


def test_init_no_mode(capsys):
    """init with no mode options exits 1 with error."""
    from folio.cli.init import main

    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err
    assert "Choose at least one mode" in captured.err


# ---------------------------------------------------------------------------
# 12. test_convert
# ---------------------------------------------------------------------------

@pytest.fixture
def source_dir_with_pdf(tmp_path):
    """Create a temp source directory containing a dummy .pdf file."""
    src = tmp_path / "source"
    src.mkdir()
    (src / "test.pdf").write_text("dummy PDF content", encoding="utf-8")
    return src


def test_convert_dry_run(source_dir_with_pdf, tmp_path, capsys):
    """convert --dry-run prints 'Would convert' and exits cleanly."""
    from folio.cli.convert import main

    dest = tmp_path / "out"
    main([
        "--dry-run", "--source", str(source_dir_with_pdf),
        "--dest", str(dest),
    ])
    captured = capsys.readouterr()
    assert "Would convert" in captured.out


def test_convert_dry_run_json(source_dir_with_pdf, tmp_path, capsys):
    """convert --dry-run --json produces valid JSON with expected keys."""
    from folio.cli.convert import main

    dest = tmp_path / "out"
    main([
        "--dry-run", "--json", "--source", str(source_dir_with_pdf),
        "--dest", str(dest),
    ])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "files" in data
    assert "dry_run" in data
    assert data["dry_run"] is True


def test_convert_no_files(empty_dir, tmp_path, capsys):
    """convert with no convertible files exits 1 with error."""
    from folio.cli.convert import main

    dest = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        main(["--source", str(empty_dir), "--dest", str(dest)])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "No convertible files" in captured.err


def test_convert_nonexistent_source(capsys):
    """convert with nonexistent source dir exits 1 with error."""
    from folio.cli.convert import main

    with pytest.raises(SystemExit) as exc:
        main(["--source", "/nonexistent/path", "--dest", "/tmp/out"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


# ---------------------------------------------------------------------------
# 13. test_validate
# ---------------------------------------------------------------------------

@pytest.fixture
def source_dir_with_valid_md(tmp_path):
    """Create a temp source directory with valid markdown files."""
    src = tmp_path / "validate_source"
    src.mkdir()
    content = """---
funder: "OAC"
type: application
written: 2024
---
# Project Description

This is a substantial project description that has enough content to pass validation checks.
It describes the project in detail with multiple paragraphs of meaningful text.

## Goals

- Goal one with meaningful content
- Goal two with additional details
- Goal three explaining the objectives

## Budget

The budget for this project includes items for staffing, materials, and overhead costs.
"""
    for i in range(3):
        (src / f"OAC__2024_test_file_{i}__application.md").write_text(content, encoding="utf-8")
    return src


def test_validate_source(source_dir_with_valid_md, capsys):
    """validate --source runs checks and prints results."""
    from folio.cli.validate import main

    main(["--source", str(source_dir_with_valid_md)])
    captured = capsys.readouterr()
    assert "Files scanned" in captured.out
    assert "Files passing" in captured.out


def test_validate_sample(source_dir_with_valid_md, capsys):
    """validate --sample 1 limits to one file."""
    from folio.cli.validate import main

    main(["--source", str(source_dir_with_valid_md), "--sample", "1"])
    captured = capsys.readouterr()
    assert "Files scanned: 1" in captured.out


def test_validate_tier_filter(source_dir_with_valid_md, minimal_folio_yaml, capsys):
    """validate --tier full attempts to filter by tier (manifest not found, returns no files)."""
    from folio.cli.validate import main

    main([
        "--source", str(source_dir_with_valid_md),
        "--config", str(minimal_folio_yaml / "folio.yaml"),
        "--tier", "full",
    ])
    captured = capsys.readouterr()
    assert "Files scanned: 0" in captured.out


def test_validate_json_output(source_dir_with_valid_md, capsys):
    """validate --json produces valid JSON with expected keys."""
    from folio.cli.validate import main

    main(["--source", str(source_dir_with_valid_md), "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "source_dir" in data
    assert "files_scanned" in data
    assert "files_passing" in data
    assert "files_with_issues" in data
    assert "validations" in data


def test_validate_nonexistent_source(capsys):
    """validate with nonexistent source dir exits 1 with error."""
    from folio.cli.validate import main

    with pytest.raises(SystemExit) as exc:
        main(["--source", "/nonexistent/validate/path"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_validate_dry_run(source_dir_with_valid_md, capsys):
    """validate --dry-run prints preview without running checks."""
    from folio.cli.validate import main

    main(["--dry-run", "--source", str(source_dir_with_valid_md)])
    captured = capsys.readouterr()
    assert "Would check" in captured.out


def test_validate_dry_run_json(source_dir_with_valid_md, capsys):
    """validate --dry-run --json produces JSON with dry_run True."""
    from folio.cli.validate import main

    main(["--dry-run", "--json", "--source", str(source_dir_with_valid_md)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["dry_run"] is True
    assert "files" in data
    assert data["files"] == 3


def test_validate_all_verbose(source_dir_with_valid_md, capsys):
    """validate --all prints per-file issue summaries."""
    from folio.cli.validate import main

    main(["--source", str(source_dir_with_valid_md), "--all"])
    captured = capsys.readouterr()
    for i in range(3):
        assert f"OAC__2024_test_file_{i}__application.md" in captured.out


def test_validate_all_verbose_json(source_dir_with_valid_md, capsys):
    """validate --all --json produces structured per-file results."""
    from folio.cli.validate import main

    main(["--source", str(source_dir_with_valid_md), "--all", "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "source_dir" in data
    assert "files_scanned" in data
    assert data["files_scanned"] == 3


# ---------------------------------------------------------------------------
# 14. test_wiki
# ---------------------------------------------------------------------------


def test_wiki_dry_run_status(minimal_folio_yaml, capsys):
    """wiki status --dry-run previews without executing."""
    from folio.cli.wiki import main

    orig = os.getcwd()
    try:
        os.chdir(str(minimal_folio_yaml))
        main(["--dry-run", "status"])
    finally:
        os.chdir(orig)
    captured = capsys.readouterr()
    assert "would execute" in captured.out.lower() or "dry-run" in captured.out.lower()
    assert "status" in captured.out


def test_wiki_dry_run_doctor(minimal_folio_yaml, capsys):
    """wiki doctor --dry-run previews without executing."""
    from folio.cli.wiki import main

    orig = os.getcwd()
    try:
        os.chdir(str(minimal_folio_yaml))
        main(["--dry-run", "doctor"])
    finally:
        os.chdir(orig)
    captured = capsys.readouterr()
    assert "doctor" in captured.out


def test_wiki_dry_run_lint(minimal_folio_yaml, capsys):
    """wiki lint --dry-run previews lint pass."""
    from folio.cli.wiki import main

    orig = os.getcwd()
    try:
        os.chdir(str(minimal_folio_yaml))
        main(["--dry-run", "lint", "--pass", "consistency"])
    finally:
        os.chdir(orig)
    captured = capsys.readouterr()
    assert "lint" in captured.out
    assert "consistency" in captured.out


def test_wiki_dry_run_coverage(minimal_folio_yaml, capsys):
    """wiki coverage --dry-run previews coverage check."""
    from folio.cli.wiki import main

    orig = os.getcwd()
    try:
        os.chdir(str(minimal_folio_yaml))
        main(["--dry-run", "coverage"])
    finally:
        os.chdir(orig)
    captured = capsys.readouterr()
    assert "coverage" in captured.out


def test_wiki_dry_run_diff(minimal_folio_yaml, capsys):
    """wiki diff --dry-run previews pending changes."""
    from folio.cli.wiki import main

    orig = os.getcwd()
    try:
        os.chdir(str(minimal_folio_yaml))
        main(["--dry-run", "diff"])
    finally:
        os.chdir(orig)
    captured = capsys.readouterr()
    assert "diff" in captured.out


def test_wiki_dry_run_verify(minimal_folio_yaml, capsys):
    """wiki verify --dry-run previews trust verification."""
    from folio.cli.wiki import main

    orig = os.getcwd()
    try:
        os.chdir(str(minimal_folio_yaml))
        main(["--dry-run", "verify", "--all", "--limit", "10"])
    finally:
        os.chdir(orig)
    captured = capsys.readouterr()
    assert "verify" in captured.out
    assert "all" in captured.out


def test_wiki_json_output(minimal_folio_yaml, capsys):
    """wiki status --json produces valid JSON via dry-run."""
    from folio.cli.wiki import main

    orig = os.getcwd()
    try:
        os.chdir(str(minimal_folio_yaml))
        main(["--json", "--dry-run", "status"])
    finally:
        os.chdir(orig)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "subcommand" in data
    assert data["subcommand"] == "status"


def test_wiki_json_dry_run(minimal_folio_yaml, capsys):
    """wiki doctor --dry-run --json produces valid JSON with dry_run True."""
    from folio.cli.wiki import main

    orig = os.getcwd()
    try:
        os.chdir(str(minimal_folio_yaml))
        main(["--json", "--dry-run", "doctor"])
    finally:
        os.chdir(orig)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["dry_run"] is True
    assert data["subcommand"] == "doctor"


def test_wiki_no_subcommand(capsys):
    """wiki with no subcommand exits 1 with help on stderr."""
    from folio.cli.wiki import main

    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 1


def test_wiki_missing_config(capsys):
    """wiki with nonexistent config exits 1 with error."""
    from folio.cli.wiki import main

    with pytest.raises(SystemExit) as exc:
        main(["--config", "/nonexistent/config.yaml", "status"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err


# ---------------------------------------------------------------------------
# 15. test_repack
# ---------------------------------------------------------------------------

@pytest.fixture
def nested_source_dir(tmp_path):
    """Create a nested source directory with files for repack testing."""
    src = tmp_path / "nested_source"
    sub = src / "OAC" / "2023"
    sub.mkdir(parents=True)
    (sub / "Application.docx").write_text("fake docx", encoding="utf-8")
    (sub / "Budget.xlsx").write_text("fake xlsx", encoding="utf-8")
    return src


def test_repack_dry_run(nested_source_dir, tmp_path, capsys):
    """repack --dry-run previews repacking without writing files."""
    from folio.cli.repack import main

    dest = tmp_path / "flat_archive"
    main(["--source", str(nested_source_dir), "--dest", str(dest), "--dry-run"])
    captured = capsys.readouterr()
    assert "Would repack" in captured.out or "Files found" in captured.out


def test_repack_json_output(nested_source_dir, tmp_path, capsys):
    """repack --json produces valid JSON with expected keys."""
    from folio.cli.repack import main

    dest = tmp_path / "flat_archive"
    main(["--source", str(nested_source_dir), "--dest", str(dest), "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "total" in data
    assert "items" in data
    assert "success" in data


def test_repack_nonexistent_source(capsys):
    """repack with nonexistent source dir exits 1 with error."""
    from folio.cli.repack import main

    with pytest.raises(SystemExit) as exc:
        main(["--source", "/nonexistent/repack/path", "--dest", "/tmp/dest"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_repack_with_funder_override(nested_source_dir, tmp_path, capsys):
    """repack --funder override applies override to all files."""
    from folio.cli.repack import main

    dest = tmp_path / "flat_archive"
    main([
        "--source", str(nested_source_dir),
        "--dest", str(dest),
        "--funder", "TAC",
        "--dry-run",
    ])
    captured = capsys.readouterr()
    assert "Would repack" in captured.out or "Files found" in captured.out


def test_repack_dry_run_json(nested_source_dir, tmp_path, capsys):
    """repack --dry-run --json produces JSON with dry_run info."""
    from folio.cli.repack import main

    dest = tmp_path / "flat_archive"
    main(["--source", str(nested_source_dir), "--dest", str(dest), "--dry-run", "--json"])
    captured = capsys.readouterr()
    out = captured.out
    json_start = out.find("{")
    assert json_start >= 0, f"No JSON object found in output: {out!r}"
    data = json.loads(out[json_start:])
    assert "total" in data
    assert data["total"] >= 0


# ---------------------------------------------------------------------------
# 16. test_install_agent
# ---------------------------------------------------------------------------


def test_install_agent_json(minimal_folio_yaml, capsys):
    """install-agent --json produces valid JSON with expected keys."""
    from folio.cli.install_agent import main

    main([
        "--config", str(minimal_folio_yaml / "folio.yaml"),
        "--platform", "opencode",
        "--json",
    ])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "platform" in data
    assert data["platform"] == "opencode"
    assert "files_written" in data
    assert "warnings" in data


def test_install_agent_platform_opencode(minimal_folio_yaml, capsys):
    """install-agent --platform opencode writes agent files."""
    from folio.cli.install_agent import main

    # Run in the tmp_path to avoid polluting cwd
    orig_cwd = os.getcwd()
    try:
        os.chdir(str(minimal_folio_yaml))
        main(["--platform", "opencode", "--no-skills"])
    finally:
        os.chdir(orig_cwd)
    captured = capsys.readouterr()
    assert "Bootstrap complete" in captured.out
    assert (minimal_folio_yaml / "AGENTS.md").exists()


def test_install_agent_dry_run(minimal_folio_yaml, capsys):
    """install-agent --dry-run previews without writing files."""
    from folio.cli.install_agent import main

    orig_cwd = os.getcwd()
    try:
        os.chdir(str(minimal_folio_yaml))
        main(["--platform", "opencode", "--dry-run"])
    finally:
        os.chdir(orig_cwd)
    captured = capsys.readouterr()
    assert "Would write" in captured.out
    assert not (minimal_folio_yaml / "AGENTS.md").exists()


def test_install_agent_dry_run_json(minimal_folio_yaml, capsys):
    """install-agent --dry-run --json produces JSON with platform and dry_run info."""
    from folio.cli.install_agent import main

    main([
        "--config", str(minimal_folio_yaml / "folio.yaml"),
        "--platform", "claude",
        "--dry-run",
        "--json",
    ])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "platform" in data
    assert data["platform"] == "claude"


def test_install_agent_no_config(capsys):
    """install-agent without config exits 1 with error."""
    from folio.cli.install_agent import main

    with pytest.raises(SystemExit) as exc:
        main(["--platform", "opencode"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err
