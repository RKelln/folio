"""Tests for the ``folio convert-bench`` CLI (bead folio-ax5).

These tests are fully offline and must NOT require any real converter library.
A small fake :class:`FakeConverter` stands in for real adapters, and
``folio.cli.convert_bench.resolve_converters`` is monkeypatched so the runner
uses the fakes (or ``None`` for unavailable converters).

Tests call ``main(argv)`` directly, assert exit codes via
``pytest.raises(SystemExit)`` and read output with ``capsys``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from folio.adapters.converters.base import Converter
from folio.cli.convert_bench import main

_GOLDEN = """\
---
funder: OAC
doc_kind: application
---

# Project Narrative

This organization runs community arts programming for emerging artists.

## Budget

| Item | Amount |
| --- | --- |
| Staff | $10,000 |
| Materials | $2,000 |
"""


class FakeConverter(Converter):
    """In-memory converter that echoes a fixed Markdown body (always succeeds)."""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def supported_extensions(self) -> set[str]:
        return {".pdf", ".docx", ".xlsx"}

    def convert(self, source: Path) -> str | None:
        return _GOLDEN


@pytest.fixture
def corpus_dir(tmp_path: Path) -> Path:
    """Build a minimal corpus with golden/rendered pairs and return its root."""
    golden = tmp_path / "golden"
    rendered = tmp_path / "rendered"
    golden.mkdir()
    rendered.mkdir()

    for slug in ("oac-application-01", "oac-budget-01"):
        (golden / f"{slug}.md").write_text(_GOLDEN, encoding="utf-8")
        (rendered / f"{slug}.docx").write_bytes(b"fake-docx")

    return tmp_path


def _fake_resolve_available(spec):
    """resolve_converters replacement: every enabled converter is a fake."""
    return {c.name: FakeConverter() for c in spec.enabled_converters()}


def _fake_resolve_none(spec):
    """resolve_converters replacement: every enabled converter is unavailable."""
    return {c.name: None for c in spec.enabled_converters()}


def _explode(*_args, **_kwargs):
    """Stand-in for run_benchmark that fails the test if ever invoked."""
    raise AssertionError("run_benchmark must not be called during dry-run")


# ---------------------------------------------------------------------------
# help / version
# ---------------------------------------------------------------------------

def test_help(capsys):
    """--help prints usage and exits 0."""
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    combined = "".join(capsys.readouterr()).lower()
    assert "usage:" in combined
    assert "convert-bench" in combined


def test_version(capsys):
    """--version prints a version string and exits 0."""
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "v" in "".join(capsys.readouterr())


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------

def test_dry_run_json(corpus_dir, capsys, monkeypatch):
    """--dry-run --json prints a JSON plan and never runs conversions."""
    monkeypatch.setattr(
        "folio.cli.convert_bench.resolve_converters", _fake_resolve_available
    )
    monkeypatch.setattr("folio.cli.convert_bench.run_benchmark", _explode)

    with pytest.raises(SystemExit) as exc:
        main(["--corpus", str(corpus_dir), "--dry-run", "--json"])
    assert exc.value.code == 0

    data = json.loads(capsys.readouterr().out)
    assert data["dry_run"] is True
    assert data["n_cases"] == 2
    assert len(data["cases"]) == 2
    slugs = {c["slug"] for c in data["cases"]}
    assert slugs == {"oac-application-01", "oac-budget-01"}
    assert len(data["converters"]) > 0
    assert all(c["available"] for c in data["converters"])


def test_dry_run_text(corpus_dir, capsys, monkeypatch):
    """--dry-run (text) prints a readable plan and exits 0."""
    monkeypatch.setattr(
        "folio.cli.convert_bench.resolve_converters", _fake_resolve_available
    )
    monkeypatch.setattr("folio.cli.convert_bench.run_benchmark", _explode)

    with pytest.raises(SystemExit) as exc:
        main(["--corpus", str(corpus_dir), "--dry-run"])
    assert exc.value.code == 0

    out = capsys.readouterr().out
    assert "Dry run" in out
    assert "oac-application-01" in out


# ---------------------------------------------------------------------------
# full run
# ---------------------------------------------------------------------------

def test_full_run_json(corpus_dir, capsys, monkeypatch):
    """Full run --json parses as JSON with converters + doc_results; exit 0."""
    monkeypatch.setattr(
        "folio.cli.convert_bench.resolve_converters", _fake_resolve_available
    )
    with pytest.raises(SystemExit) as exc:
        main(["--corpus", str(corpus_dir), "--json"])
    assert exc.value.code == 0

    data = json.loads(capsys.readouterr().out)
    assert "converters" in data
    assert "doc_results" in data
    assert data["n_cases"] == 2
    assert len(data["doc_results"]) > 0


def test_full_run_text_scorecard(corpus_dir, capsys, monkeypatch):
    """Full run (text) prints the scorecard containing converter names; exit 0."""
    monkeypatch.setattr(
        "folio.cli.convert_bench.resolve_converters", _fake_resolve_available
    )
    with pytest.raises(SystemExit) as exc:
        main(["--corpus", str(corpus_dir), "--converters", "liteparse"])
    assert exc.value.code == 0

    out = capsys.readouterr().out
    assert "Converter" in out
    assert "liteparse" in out


def test_out_writes_report(corpus_dir, tmp_path, capsys, monkeypatch):
    """--out writes a non-empty Markdown report to the given path."""
    monkeypatch.setattr(
        "folio.cli.convert_bench.resolve_converters", _fake_resolve_available
    )
    report = tmp_path / "nested" / "report.md"

    with pytest.raises(SystemExit) as exc:
        main(["--corpus", str(corpus_dir), "--out", str(report)])
    assert exc.value.code == 0

    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert text.strip()
    assert "Converter Benchmark Report" in text
    assert "Report written to" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------

def test_unknown_converter_exits_1(corpus_dir, capsys, monkeypatch):
    """--converters with an unknown name exits 1 with an error message."""
    monkeypatch.setattr(
        "folio.cli.convert_bench.resolve_converters", _fake_resolve_available
    )
    with pytest.raises(SystemExit) as exc:
        main(["--corpus", str(corpus_dir), "--converters", "bogus"])
    assert exc.value.code == 1
    assert "bogus" in "".join(capsys.readouterr())


def test_no_cases_exits_1(capsys, monkeypatch):
    """No discovered cases exits 1 with a clear message."""
    monkeypatch.setattr(
        "folio.cli.convert_bench.discover_cases", lambda *a, **k: []
    )
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 1
    assert "No benchmark cases found" in "".join(capsys.readouterr())


def test_all_converters_unavailable_exits_1(corpus_dir, capsys, monkeypatch):
    """When no requested converter is available the run exits 1."""
    monkeypatch.setattr(
        "folio.cli.convert_bench.resolve_converters", _fake_resolve_none
    )
    with pytest.raises(SystemExit) as exc:
        main(["--corpus", str(corpus_dir), "--json"])
    assert exc.value.code == 1

    data = json.loads(capsys.readouterr().out)
    assert all(not c["available"] for c in data["converters"])
