"""Comprehensive CLI tests for all folio entry points.

Tests the `main(argv)` pattern used by every folio CLI module.
"""

from __future__ import annotations

import importlib
import json
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
}


# ---------------------------------------------------------------------------
# 1. test_help
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(CLI_MODULES))
def test_cli_help(name, capsys):
    """Each CLI's main(['--help']) prints usage info and exits 0."""
    mod = importlib.import_module(CLI_MODULES[name])

    if name == "teach":
        mod.main(["--help"])
        captured = capsys.readouterr()
        assert "teach" in captured.out.lower() or "teach" in captured.err.lower()
        return

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

    if name == "teach":
        mod.main(["--version"])
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert f"v{__version__}" in combined
        return

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


@pytest.fixture
def minimal_folio_yaml(tmp_path):
    """Write a minimal folio.yaml to tmp_path and return the tmp_path."""
    config = tmp_path / "folio.yaml"
    config.write_text("""
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
""")
    return tmp_path


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
