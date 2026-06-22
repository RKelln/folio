"""Tests for the ``folio corpus`` CLI (Round C of bead folio-4v7).

Tests call ``main(argv)`` directly, assert exit codes via
``pytest.raises(SystemExit)``, and use ``capsys`` / ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from folio.cli.corpus import main
from folio.core.corpus.pii_scan import load_denylist

# ---------------------------------------------------------------------------
# 1. --help and --version
# ---------------------------------------------------------------------------

def test_help(capsys):
    """--help prints usage info and exits 0."""
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "usage:" in combined
    assert "folio corpus" in combined


def test_generate_help(capsys):
    """generate --help prints usage and exits 0."""
    with pytest.raises(SystemExit) as exc:
        main(["generate", "--help"])
    assert exc.value.code == 0


def test_scan_help(capsys):
    """scan --help prints usage and exits 0."""
    with pytest.raises(SystemExit) as exc:
        main(["scan", "--help"])
    assert exc.value.code == 0


def test_version(capsys):
    """--version prints version and exits 0."""
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "v" in (captured.out + captured.err)


# ---------------------------------------------------------------------------
# 2. dry-run
# ---------------------------------------------------------------------------

def test_dry_run_default_subcommand(capsys):
    """folio corpus (no subcommand) defaults to generate dry-run."""
    with pytest.raises(SystemExit) as exc:
        main(["--dry-run"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "Dry run" in captured.out
    assert "no files will be written" in captured.out.lower()


def test_dry_run_json(capsys):
    """--dry-run --json prints valid JSON with a non-empty plan, writes NO files."""
    with pytest.raises(SystemExit) as exc:
        main(["--dry-run", "--json"])
    assert exc.value.code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["dry_run"] is True
    assert isinstance(data["spec"], dict)
    assert data["total_outputs"] > 0
    assert len(data["documents"]) > 0
    assert "available_formats" in data
    assert "output_dir" in data


def test_dry_run_json_generate_subcommand(capsys):
    """generate --dry-run --json produces same result."""
    with pytest.raises(SystemExit) as exc:
        main(["generate", "--dry-run", "--json"])
    assert exc.value.code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["dry_run"] is True
    assert data["total_outputs"] > 0


def test_dry_run_scan(capsys, tmp_path):
    """scan --dry-run lists files that would be scanned."""
    md = tmp_path / "test.md"
    md.write_text("# Hello", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["scan", "--dry-run", str(tmp_path)])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "Would scan" in captured.out


def test_dry_run_scan_json(capsys, tmp_path):
    """scan --dry-run --json returns JSON plan."""
    md = tmp_path / "test.md"
    md.write_text("# Hello", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["scan", "--dry-run", "--json", str(tmp_path)])
    assert exc.value.code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["dry_run"] is True
    assert len(data["files"]) >= 1


# ---------------------------------------------------------------------------
# 3. generate --out <tmp> --formats md
# ---------------------------------------------------------------------------

def test_generate_md_only(tmp_path, capsys):
    """generate --out <tmp> --formats md writes golden .md files; gate passes."""
    out = tmp_path / "corpus"
    with pytest.raises(SystemExit) as exc:
        main(["generate", "--out", str(out), "--formats", "md"])
    assert exc.value.code == 0

    captured = capsys.readouterr()
    assert "GATE PASSED" in captured.out

    golden_dir = out / "golden"
    assert golden_dir.is_dir()
    mds = list(golden_dir.glob("*.md"))
    assert len(mds) > 0
    for md_file in mds:
        content = md_file.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "funder:" in content


def test_generate_md_only_json(tmp_path, capsys):
    """generate --json emits valid manifest with files_written."""
    out = tmp_path / "corpus"
    with pytest.raises(SystemExit) as exc:
        main(["generate", "--out", str(out), "--formats", "md", "--json"])
    assert exc.value.code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["passed"] is True
    assert len(data["files_written"]) > 0
    assert data["gate"]["passed"] is True


def test_generate_seed_override(tmp_path, capsys):
    """--seed changes the spec seed."""
    out = tmp_path / "corpus"
    with pytest.raises(SystemExit) as exc:
        main([
            "generate", "--out", str(out), "--formats", "md",
            "--seed", "9999",
        ])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "GATE PASSED" in captured.out


def test_generate_funder_override(tmp_path, capsys):
    """--funder changes the funder (must exist in profile headings)."""
    out = tmp_path / "corpus"
    with pytest.raises(SystemExit) as exc:
        main([
            "generate", "--out", str(out), "--formats", "md",
            "--funder", "TAC",
        ])
    assert exc.value.code == 0


# ---------------------------------------------------------------------------
# 4. unknown --formats
# ---------------------------------------------------------------------------

def test_unknown_formats_exits_nonzero(capsys):
    """--formats with an invalid format exits non-zero with clear message."""
    with pytest.raises(SystemExit) as exc:
        main(["generate", "--formats", "md,badfmt"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "badfmt" in (captured.out + captured.err)


# ---------------------------------------------------------------------------
# 5. scan subcommand
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_md(tmp_path) -> Path:
    """A clean markdown file with no PII."""
    path = tmp_path / "clean.md"
    path.write_text("# Narrative\n\nThis is a sample narrative with no PII.\n",
                    encoding="utf-8")
    return path


@pytest.fixture
def denylisted_md(tmp_path) -> Path:
    """A markdown file containing a name from the bundled denylist."""
    names = load_denylist()
    if not names:
        pytest.skip("Bundled denylist is empty")
    path = tmp_path / "denylisted.md"
    path.write_text(f"# Report\n\nSubmitted by {names[0]}.\n", encoding="utf-8")
    return path


@pytest.fixture
def dollar_amount_md(tmp_path) -> Path:
    """A markdown file with a $ amount (structural PII, not denylisted)."""
    path = tmp_path / "dollar.md"
    path.write_text("# Budget\n\nRequest Amount: $25,000\n", encoding="utf-8")
    return path


def test_scan_clean_exits_0(clean_md):
    """Scan on a clean file exits 0."""
    with pytest.raises(SystemExit) as exc:
        main(["scan", str(clean_md)])
    assert exc.value.code == 0


def test_scan_denylisted_exits_1(denylisted_md, capsys):
    """Scan on a file containing a denylisted name exits 1."""
    with pytest.raises(SystemExit) as exc:
        main(["scan", str(denylisted_md)])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "GATE FAILED" in captured.out


def test_scan_dollar_non_strict_exits_0(dollar_amount_md):
    """Non-strict scan on a $ amount file exits 0 (currency counted, not failed)."""
    with pytest.raises(SystemExit) as exc:
        main(["scan", str(dollar_amount_md)])
    assert exc.value.code == 0


def test_scan_dollar_strict_exits_1(dollar_amount_md, capsys):
    """Strict scan on a $ amount file exits 1."""
    with pytest.raises(SystemExit) as exc:
        main(["scan", "--strict", str(dollar_amount_md)])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "GATE FAILED" in captured.out


def test_scan_strict_clean_exits_0(clean_md):
    """Strict scan on a truly clean file exits 0."""
    with pytest.raises(SystemExit) as exc:
        main(["scan", "--strict", str(clean_md)])
    assert exc.value.code == 0


def test_scan_directory(tmp_path, capsys):
    """Scan a directory with .md files."""
    (tmp_path / "a.md").write_text("# A\n\nClean content.\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n\nAlso clean.\n", encoding="utf-8")
    (tmp_path / "ignored.bin").write_text("binary", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["scan", str(tmp_path)])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "Scanned" in captured.out


def test_scan_no_scannable_files(tmp_path, capsys):
    """Scan on a path with no scannable files exits 1 with message."""
    d = tmp_path / "empty"
    d.mkdir()
    with pytest.raises(SystemExit) as exc:
        main(["scan", str(d)])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "No scannable" in (captured.out + captured.err)


def test_scan_json_output(clean_md, capsys):
    """scan --json emits valid JSON with report."""
    with pytest.raises(SystemExit) as exc:
        main(["scan", "--json", str(clean_md)])
    assert exc.value.code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["passed"] is True
    assert "reports" in data


def test_scan_denylisted_json(denylisted_md, capsys):
    """scan --json on denylisted file exits 1 with findings in JSON."""
    with pytest.raises(SystemExit) as exc:
        main(["scan", "--json", str(denylisted_md)])
    assert exc.value.code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["passed"] is False


# ---------------------------------------------------------------------------
# 6. --denylist override
# ---------------------------------------------------------------------------

def test_custom_denylist_scan(tmp_path, capsys):
    """--denylist with a custom file detects names from it."""
    denylist_path = tmp_path / "custom-denylist.yaml"
    denylist_path.write_text(
        "names:\n  - Custom Person\n  - Another Name\n", encoding="utf-8"
    )
    f = tmp_path / "target.md"
    f.write_text("Report by Custom Person.\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        main(["scan", "--denylist", str(denylist_path), str(f)])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "GATE FAILED" in captured.out


# ---------------------------------------------------------------------------
# 7. SystemExit convention
# ---------------------------------------------------------------------------

def test_main_signals_exit():
    """main() with no args defaults to generate, exits via SystemExit."""
    with pytest.raises(SystemExit) as exc:
        main(["--dry-run"])
    assert exc.value.code == 0


# ---------------------------------------------------------------------------
# 8. Edge case: no documents in a programmatic spec
# ---------------------------------------------------------------------------

def test_generate_empty_spec_exits_nonzero(tmp_path, capsys):
    """A spec with zero documents exits with error."""
    spec_path = tmp_path / "empty-spec.yaml"
    spec_path.write_text(
        yaml.dump({
            "seed": 42,
            "profile": "canadian-artist-run-centre",
            "funder": "OAC",
            "output_dir": "benchmark/corpus",
            "documents": [],
        }),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc:
        main(["generate", "--spec", str(spec_path)])
    assert exc.value.code == 1
