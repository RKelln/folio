"""Tests for the benchmark corpus discovery (folio.core.bench.corpus).

Covers slug parsing (including underscored kinds and malformed slugs),
``read_golden``, and ``discover_cases`` against the REAL committed corpus at
``benchmark/corpus/`` as well as synthetic tmp_path corpora for the
missing-golden skip and missing-directory paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from folio.core.bench.corpus import (
    BenchCase,
    discover_cases,
    parse_slug,
    read_golden,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CORPUS = REPO_ROOT / "benchmark" / "corpus"


class TestParseSlug:
    @pytest.mark.parametrize(
        "slug,expected",
        [
            ("oac-application-01", ("oac", "application", 1)),
            ("oac-budget-01", ("oac", "budget", 1)),
            ("oac-narrative-01", ("oac", "narrative", 1)),
            ("oac-activity_list-01", ("oac", "activity_list", 1)),
            ("oac-staff_board-01", ("oac", "staff_board", 1)),
            ("oac-support_letter-01", ("oac", "support_letter", 1)),
            ("tac-application-12", ("tac", "application", 12)),
        ],
    )
    def test_valid_slugs(self, slug, expected):
        assert parse_slug(slug) == expected

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "oac",
            "oac-application",
            "oac-application-",
            "oac--01",
            "-application-01",
            "oac-application-xx",
            "oac-application-1a",
        ],
    )
    def test_malformed_slugs_raise(self, bad):
        with pytest.raises(ValueError):
            parse_slug(bad)


class TestReadGolden:
    def test_reads_utf8(self, tmp_path):
        f = tmp_path / "g.md"
        f.write_text("---\nfunder: OAC\n---\n# Héllo\n", encoding="utf-8")
        assert read_golden(f) == "---\nfunder: OAC\n---\n# Héllo\n"

    def test_does_not_strip_frontmatter(self, tmp_path):
        f = tmp_path / "g.md"
        f.write_text("---\nx: 1\n---\nbody\n", encoding="utf-8")
        assert read_golden(f).startswith("---")


def _make_corpus(tmp_path, rendered: dict[str, str], golden: list[str]):
    rendered_dir = tmp_path / "rendered"
    golden_dir = tmp_path / "golden"
    rendered_dir.mkdir()
    golden_dir.mkdir()
    for name in rendered:
        (rendered_dir / name).write_bytes(b"x")
    for slug in golden:
        (golden_dir / f"{slug}.md").write_text("---\n---\nbody\n", encoding="utf-8")
    return tmp_path


class TestDiscoverRealCorpus:
    def test_real_corpus_exists(self):
        assert REAL_CORPUS.exists(), "committed corpus must exist for this test"

    def test_finds_known_pairs(self):
        cases = discover_cases(REAL_CORPUS)
        by_key = {(c.slug, c.fmt): c for c in cases}
        assert ("oac-application-01", "pdf") in by_key
        assert ("oac-application-01", "docx") in by_key
        assert ("oac-budget-01", "xlsx") in by_key
        assert ("oac-staff_board-01", "docx") in by_key

    def test_scanned_pdf_maps_to_pdf_scanned(self):
        cases = discover_cases(REAL_CORPUS)
        scanned = [c for c in cases if c.slug == "oac-support_letter-01" and c.is_scanned]
        assert len(scanned) == 1
        assert scanned[0].fmt == "pdf_scanned"
        assert scanned[0].input_path.name == "oac-support_letter-01.scanned.pdf"

    def test_underscored_kinds_parsed(self):
        cases = discover_cases(REAL_CORPUS)
        case = next(c for c in cases if c.slug == "oac-activity_list-01")
        assert case.funder == "oac"
        assert case.doc_kind == "activity_list"
        assert case.index == 1

    def test_all_cases_have_existing_paths(self):
        cases = discover_cases(REAL_CORPUS)
        assert cases
        for c in cases:
            assert isinstance(c, BenchCase)
            assert c.golden_path.exists()
            assert c.input_path.exists()

    def test_cases_sorted_deterministically(self):
        cases = discover_cases(REAL_CORPUS)
        keys = [(c.slug, c.fmt) for c in cases]
        assert keys == sorted(keys)

    def test_count_matches_rendered_files(self):
        cases = discover_cases(REAL_CORPUS)
        rendered = list((REAL_CORPUS / "rendered").iterdir())
        assert len(cases) == len(rendered)


class TestDiscoverSynthetic:
    def test_missing_golden_is_skipped(self, tmp_path, caplog):
        corpus = _make_corpus(
            tmp_path,
            rendered={"oac-application-01.pdf": "", "oac-orphan-09.pdf": ""},
            golden=["oac-application-01"],
        )
        with caplog.at_level("WARNING"):
            cases = discover_cases(corpus)
        slugs = {c.slug for c in cases}
        assert slugs == {"oac-application-01"}

    def test_missing_corpus_dir_returns_empty(self, tmp_path, caplog):
        with caplog.at_level("WARNING"):
            cases = discover_cases(tmp_path / "does-not-exist")
        assert cases == []

    def test_missing_rendered_dir_returns_empty(self, tmp_path):
        (tmp_path / "golden").mkdir()
        assert discover_cases(tmp_path) == []

    def test_all_formats_discovered(self, tmp_path):
        corpus = _make_corpus(
            tmp_path,
            rendered={
                "oac-application-01.pdf": "",
                "oac-application-01.docx": "",
                "oac-budget-01.xlsx": "",
                "oac-support_letter-01.scanned.pdf": "",
            },
            golden=["oac-application-01", "oac-budget-01", "oac-support_letter-01"],
        )
        cases = discover_cases(corpus)
        fmts = {(c.slug, c.fmt, c.is_scanned) for c in cases}
        assert ("oac-application-01", "pdf", False) in fmts
        assert ("oac-application-01", "docx", False) in fmts
        assert ("oac-budget-01", "xlsx", False) in fmts
        assert ("oac-support_letter-01", "pdf_scanned", True) in fmts

    def test_unknown_extension_skipped(self, tmp_path, caplog):
        corpus = _make_corpus(
            tmp_path,
            rendered={"oac-application-01.txt": "", "oac-application-01.pdf": ""},
            golden=["oac-application-01"],
        )
        with caplog.at_level("WARNING"):
            cases = discover_cases(corpus)
        assert {c.fmt for c in cases} == {"pdf"}

    def test_custom_subdir_names(self, tmp_path):
        rendered_dir = tmp_path / "render"
        golden_dir = tmp_path / "gold"
        rendered_dir.mkdir()
        golden_dir.mkdir()
        (rendered_dir / "oac-budget-01.xlsx").write_bytes(b"x")
        (golden_dir / "oac-budget-01.md").write_text("body", encoding="utf-8")
        cases = discover_cases(tmp_path, golden_subdir="gold", rendered_subdir="render")
        assert len(cases) == 1
        assert cases[0].fmt == "xlsx"
