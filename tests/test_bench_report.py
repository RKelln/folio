"""Tests for the benchmark report rendering (folio.core.bench.report).

Builds a small ``BenchResults`` by running ``run_benchmark`` with in-memory
fake converters (reusing ``FakeConverter`` from the runner tests) over the real
committed corpus, then asserts on the plaintext scorecard and Markdown report
content. Exact elapsed times are never asserted on (non-deterministic).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from folio.core.bench.corpus import BenchCase, discover_cases, read_golden
from folio.core.bench.report import markdown_report, scorecard_table
from folio.core.bench.runner import (
    BenchResults,
    ConverterAggregate,
    DocResult,
    run_benchmark,
)
from folio.core.bench.scorer import CategoryScores
from folio.core.bench.spec import BenchSpec, CategoryWeights, ConverterSpec
from tests.test_bench_runner import _ALL_EXTS, FakeConverter

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CORPUS = REPO_ROOT / "benchmark" / "corpus"


@pytest.fixture(scope="module")
def cases() -> list[BenchCase]:
    discovered = discover_cases(REAL_CORPUS)
    assert discovered
    return discovered


@pytest.fixture(scope="module")
def golden_by_input(cases: list[BenchCase]) -> dict[Path, str]:
    return {c.input_path: read_golden(c.golden_path) for c in cases}


@pytest.fixture(scope="module")
def spec() -> BenchSpec:
    return BenchSpec(
        converters=[
            ConverterSpec(name="echo"),
            ConverterSpec(name="poor"),
            ConverterSpec(name="gone"),
        ],
        pass_threshold=0.7,
    )


@pytest.fixture(scope="module")
def results(spec, cases, golden_by_input) -> BenchResults:
    converters = {
        "echo": FakeConverter("echo", _ALL_EXTS, golden_by_input, "echo"),
        "poor": FakeConverter("poor", _ALL_EXTS, golden_by_input, "poor"),
        "gone": None,
    }
    return run_benchmark(spec, cases, converters=converters)


class TestScorecardTable:
    def test_contains_headers(self, results):
        table = scorecard_table(results)
        for header in ("Converter", "Overall", "Tables", "Time/pg(s)", "Cost/pg", "Pass"):
            assert header in table

    def test_contains_each_converter(self, results):
        table = scorecard_table(results)
        assert "echo" in table
        assert "poor" in table
        assert "gone" in table

    def test_unavailable_rendered(self, results):
        table = scorecard_table(results)
        assert "unavailable" in table
        assert "n/a" in table

    def test_is_multiline_aligned(self, results):
        table = scorecard_table(results)
        lines = table.splitlines()
        assert len(lines) >= 2 + len(results.converters)
        assert set(lines[1]) <= {"-", " "}


class TestMarkdownReport:
    def test_has_title(self, results, spec):
        md = markdown_report(results, spec)
        assert md.startswith("# ")
        assert "Converter Benchmark Report" in md

    def test_has_methodology_with_weights(self, results, spec):
        md = markdown_report(results, spec)
        assert "## Methodology" in md
        assert "offline" in md.lower()
        assert "golden" in md.lower()
        w = results.weights
        assert f"{w['text']:.2f}" in md
        assert f"{w['tables']:.2f}" in md
        assert f"{w['structure']:.2f}" in md
        assert f"{w['links_images']:.2f}" in md

    def test_has_summary_table(self, results, spec):
        md = markdown_report(results, spec)
        assert "## Summary" in md
        assert "| Converter |" in md
        assert "| Overall |" in md.replace(" | ", " | ") or "Overall" in md

    def test_has_per_doc_type_section(self, results, spec):
        md = markdown_report(results, spec)
        assert "## Per-document-type breakdown" in md
        assert "Doc type" in md
        for kind in {r.doc_kind for r in results.doc_results}:
            assert kind in md

    def test_has_recommendation(self, results, spec):
        md = markdown_report(results, spec)
        assert "Recommendation:" in md
        assert "echo" in md

    def test_recommendation_picks_highest_available(self, results, spec):
        md = markdown_report(results, spec)
        rec_line = next(
            line for line in md.splitlines() if "Recommendation:" in line
        )
        assert "echo" in rec_line
        assert "gone" not in rec_line


def test_report_with_no_scored_converters():
    spec = BenchSpec(converters=[ConverterSpec(name="gone")], pass_threshold=0.7)
    agg = ConverterAggregate(
        "gone", False, True, 0.0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False
    )
    results = BenchResults(0, 1, CategoryWeights().to_dict(), 0.7, [agg], [])
    md = markdown_report(results, spec)
    assert "No converter produced any scored documents" in md
    table = scorecard_table(results)
    assert "gone" in table and "unavailable" in table


def test_doc_type_breakdown_na_for_unscored_kind():
    scores = CategoryScores(1.0, 1.0, 1.0, 1.0)
    doc = DocResult("echo", "oac-budget-01", "budget", "xlsx", "scored", scores, 1.0, 0.1, 1, 0.0)
    agg_echo = ConverterAggregate(
        "echo", True, True, 0.0, 1, 0, 0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.1, 0.1, 0.0, True
    )
    agg_other = ConverterAggregate(
        "other", True, True, 0.0, 0, 1, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False
    )
    results = BenchResults(
        1, 2, CategoryWeights().to_dict(), 0.7, [agg_echo, agg_other], [doc]
    )
    spec = BenchSpec(
        converters=[ConverterSpec(name="echo"), ConverterSpec(name="other")]
    )
    md = markdown_report(results, spec)
    assert "budget" in md
    assert "n/a" in md


def _agg(name: str, mean_weighted: float, coverage: float, *, available: bool = True):
    overall = mean_weighted * coverage
    return ConverterAggregate(
        name=name,
        available=available,
        offline=True,
        cost_per_page=0.0,
        n_scored=3 if coverage else 0,
        n_failed=0,
        n_unsupported=0,
        mean_weighted=mean_weighted,
        coverage=coverage,
        overall=overall,
        mean_text=mean_weighted,
        mean_tables=mean_weighted,
        mean_structure=mean_weighted,
        mean_links_images=mean_weighted,
        total_elapsed_s=0.1,
        mean_elapsed_per_page_s=0.1,
        total_cost=0.0,
        passed=overall >= 0.7,
    )


def test_recommendation_prefers_coverage_weighted_overall():
    # High quality but low coverage (pandoc-like) must NOT beat a moderate-quality
    # full-coverage converter (liteparse-like) on the headline recommendation.
    high_quality_low_coverage = _agg("pan", 0.97, 0.3)   # overall ~0.29
    moderate_full_coverage = _agg("lite", 0.85, 1.0)     # overall 0.85
    results = BenchResults(
        10, 2, CategoryWeights().to_dict(), 0.7,
        [high_quality_low_coverage, moderate_full_coverage], [],
    )
    spec = BenchSpec(converters=[ConverterSpec(name="pan"), ConverterSpec(name="lite")])
    md = markdown_report(results, spec)
    assert "Use `lite`" in md
    assert "Use `pan`" not in md


def test_summary_has_overall_and_quality_columns():
    results = BenchResults(
        10, 1, CategoryWeights().to_dict(), 0.7, [_agg("lite", 0.85, 1.0)], [],
    )
    table = scorecard_table(results)
    assert "Overall" in table
    assert "Quality" in table
