"""Tests for the benchmark runner (folio.core.bench.runner).

Uses in-memory fake converters (implementing the ``Converter`` ABC) so no
third-party converter libraries are required. Cases come from the REAL
committed corpus at ``benchmark/corpus/`` via ``discover_cases``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from folio.adapters.converters import Converter
from folio.core.bench.corpus import BenchCase, discover_cases, read_golden
from folio.core.bench.runner import (
    BenchResults,
    ConverterAggregate,
    DocResult,
    estimate_pages,
    resolve_converters,
    run_benchmark,
    weighted_score,
)
from folio.core.bench.scorer import CategoryScores
from folio.core.bench.spec import BenchSpec, CategoryWeights, ConverterSpec

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CORPUS = REPO_ROOT / "benchmark" / "corpus"

_ALL_EXTS = {".pdf", ".docx", ".xlsx"}


class FakeConverter(Converter):
    """Configurable in-memory converter for tests.

    ``mode`` controls the output:
        * ``"echo"`` — returns the golden verbatim (near-perfect score).
        * ``"poor"`` — returns a fixed unrelated string (low score).
        * ``"null"`` — always returns ``None`` (failure).
    """

    def __init__(
        self,
        name: str,
        extensions: set[str],
        golden_by_input: dict[Path, str],
        mode: str = "echo",
    ):
        self._name = name
        self._exts = set(extensions)
        self._golden_by_input = golden_by_input
        self._mode = mode

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_extensions(self) -> set[str]:
        return set(self._exts)

    def convert(self, source: Path) -> str | None:
        if self._mode == "raise":
            raise RuntimeError("boom")
        if self._mode == "null":
            return None
        golden = self._golden_by_input.get(source)
        if golden is None:
            return None
        if self._mode == "echo":
            return golden
        return "completely unrelated placeholder body text\n"


@pytest.fixture(scope="module")
def cases() -> list[BenchCase]:
    discovered = discover_cases(REAL_CORPUS)
    assert discovered, "real corpus must yield cases"
    return discovered


@pytest.fixture(scope="module")
def golden_by_input(cases: list[BenchCase]) -> dict[Path, str]:
    return {c.input_path: read_golden(c.golden_path) for c in cases}


def _spec(*names: str, pass_threshold: float = 0.7) -> BenchSpec:
    return BenchSpec(
        converters=[ConverterSpec(name=n) for n in names],
        pass_threshold=pass_threshold,
    )


class TestWeightedScore:
    def test_all_ones_is_one(self):
        scores = CategoryScores(1.0, 1.0, 1.0, 1.0)
        assert weighted_score(scores, CategoryWeights()) == pytest.approx(1.0)

    def test_default_weights_text_only(self):
        scores = CategoryScores(text=1.0, tables=0.0, structure=0.0, links_images=0.0)
        assert weighted_score(scores, CategoryWeights()) == pytest.approx(0.4)

    def test_unnormalized_weights_are_normalized(self):
        scores = CategoryScores(text=1.0, tables=0.0, structure=0.0, links_images=0.0)
        weights = CategoryWeights(text=2.0, tables=2.0, structure=2.0, links_images=2.0)
        assert weighted_score(scores, weights) == pytest.approx(0.25)

    def test_result_in_unit_interval(self):
        scores = CategoryScores(0.3, 0.6, 0.9, 0.5)
        value = weighted_score(scores, CategoryWeights())
        assert 0.0 <= value <= 1.0


class TestEstimatePages:
    def test_at_least_one(self, cases: list[BenchCase]):
        for case in cases:
            assert estimate_pages(case) >= 1

    def test_deterministic(self, cases: list[BenchCase]):
        case = cases[0]
        assert estimate_pages(case) == estimate_pages(case)

    def test_longer_golden_has_more_pages(self, cases: list[BenchCase]):
        by_kind = {c.doc_kind: c for c in cases}
        if "narrative" in by_kind and "budget" in by_kind:
            assert estimate_pages(by_kind["narrative"]) >= estimate_pages(
                by_kind["budget"]
            )


class TestResolveConverters:
    def test_marker_is_unavailable(self):
        spec = _spec("marker")
        resolved = resolve_converters(spec)
        assert resolved["marker"] is None

    def test_unknown_is_unavailable(self):
        spec = _spec("does-not-exist")
        resolved = resolve_converters(spec)
        assert resolved["does-not-exist"] is None

    def test_known_offline_converter_resolves(self):
        spec = _spec("pandoc")
        resolved = resolve_converters(spec)
        assert isinstance(resolved["pandoc"], Converter)


class TestRunBenchmark:
    def test_echo_scores_and_passes(self, cases, golden_by_input):
        spec = _spec("echo")
        converters = {"echo": FakeConverter("echo", _ALL_EXTS, golden_by_input, "echo")}
        results = run_benchmark(spec, cases, converters=converters)

        agg = results.converters[0]
        assert agg.available is True
        assert agg.n_scored == len(cases)
        assert agg.n_failed == 0
        assert agg.n_unsupported == 0
        assert agg.mean_weighted >= 0.9
        assert agg.passed is True
        assert all(r.status == "scored" for r in results.doc_results)

    def test_null_converter_all_failed(self, cases, golden_by_input):
        spec = _spec("nullc")
        converters = {"nullc": FakeConverter("nullc", _ALL_EXTS, golden_by_input, "null")}
        results = run_benchmark(spec, cases, converters=converters)

        agg = results.converters[0]
        assert agg.n_failed == len(cases)
        assert agg.n_scored == 0
        assert agg.mean_weighted == 0.0
        assert agg.passed is False
        assert all(r.status == "failed" for r in results.doc_results)
        assert all(r.scores is None for r in results.doc_results)

    def test_unsupported_format(self, cases, golden_by_input):
        spec = _spec("xlsxonly")
        converters = {
            "xlsxonly": FakeConverter("xlsxonly", {".xlsx"}, golden_by_input, "echo")
        }
        results = run_benchmark(spec, cases, converters=converters)

        statuses = {r.fmt: r.status for r in results.doc_results}
        agg = results.converters[0]
        assert agg.n_unsupported > 0
        assert any(r.status == "unsupported" for r in results.doc_results)
        assert statuses.get("xlsx") == "scored"
        for r in results.doc_results:
            if r.fmt in {"pdf", "docx", "pdf_scanned"}:
                assert r.status == "unsupported"
                assert r.elapsed_s == 0.0

    def test_poor_scores_below_echo(self, cases, golden_by_input):
        spec = _spec("echo", "poor")
        converters = {
            "echo": FakeConverter("echo", _ALL_EXTS, golden_by_input, "echo"),
            "poor": FakeConverter("poor", _ALL_EXTS, golden_by_input, "poor"),
        }
        results = run_benchmark(spec, cases, converters=converters)
        echo, poor = results.converters
        assert poor.n_scored == len(cases)
        assert poor.mean_weighted < echo.mean_weighted

    def test_pass_flag_matches_formula(self, cases, golden_by_input):
        spec = _spec("echo", "poor", "gone", pass_threshold=0.7)
        converters = {
            "echo": FakeConverter("echo", _ALL_EXTS, golden_by_input, "echo"),
            "poor": FakeConverter("poor", _ALL_EXTS, golden_by_input, "poor"),
            "gone": None,
        }
        results = run_benchmark(spec, cases, converters=converters)
        for agg in results.converters:
            assert agg.passed == (
                agg.n_scored > 0 and agg.mean_weighted >= results.pass_threshold
            )

    def test_unavailable_converter(self, cases, golden_by_input):
        spec = _spec("echo", "gone")
        converters = {
            "echo": FakeConverter("echo", _ALL_EXTS, golden_by_input, "echo"),
            "gone": None,
        }
        results = run_benchmark(spec, cases, converters=converters)
        by_name = {c.name: c for c in results.converters}
        gone = by_name["gone"]
        assert gone.available is False
        assert gone.n_scored == 0
        assert gone.passed is False
        assert all(r.converter != "gone" for r in results.doc_results)

    def test_raising_converter_is_failed_and_logged(self, cases, golden_by_input, caplog):
        spec = _spec("kaboom")
        converters = {
            "kaboom": FakeConverter("kaboom", _ALL_EXTS, golden_by_input, "raise")
        }
        with caplog.at_level("ERROR"):
            results = run_benchmark(spec, cases, converters=converters)
        agg = results.converters[0]
        assert agg.n_failed == len(cases)
        assert agg.n_scored == 0
        assert all(r.status == "failed" for r in results.doc_results)
        assert "kaboom" in caplog.text

    def test_progress_flag(self, cases, golden_by_input):
        spec = _spec("echo")
        converters = {"echo": FakeConverter("echo", _ALL_EXTS, golden_by_input, "echo")}
        results = run_benchmark(spec, cases, converters=converters, progress=True)
        assert results.converters[0].n_scored == len(cases)

    def test_results_metadata(self, cases, golden_by_input):
        spec = _spec("echo", pass_threshold=0.7)
        converters = {"echo": FakeConverter("echo", _ALL_EXTS, golden_by_input, "echo")}
        results = run_benchmark(spec, cases, converters=converters)
        assert results.n_cases == len(cases)
        assert results.n_converters == 1
        assert results.pass_threshold == 0.7
        assert results.weights == CategoryWeights().to_dict()

    def test_default_converters_resolved_when_none(self, cases):
        spec = _spec("marker")
        results = run_benchmark(spec, cases, converters=None)
        assert results.converters[0].available is False

    def test_determinism(self, cases, golden_by_input):
        spec = _spec("echo", "poor")
        converters = {
            "echo": FakeConverter("echo", _ALL_EXTS, golden_by_input, "echo"),
            "poor": FakeConverter("poor", _ALL_EXTS, golden_by_input, "poor"),
        }
        first = run_benchmark(spec, cases, converters=converters)
        second = run_benchmark(spec, cases, converters=converters)
        assert [r.weighted for r in first.doc_results] == [
            r.weighted for r in second.doc_results
        ]
        assert [c.mean_weighted for c in first.converters] == [
            c.mean_weighted for c in second.converters
        ]

    def test_to_dict_json_serializable(self, cases, golden_by_input):
        spec = _spec("echo", "gone")
        converters = {
            "echo": FakeConverter("echo", _ALL_EXTS, golden_by_input, "echo"),
            "gone": None,
        }
        results = run_benchmark(spec, cases, converters=converters)
        encoded = json.dumps(results.to_dict())
        decoded = json.loads(encoded)
        assert decoded["n_cases"] == len(cases)
        assert isinstance(decoded["converters"], list)
        assert isinstance(decoded["doc_results"], list)

    def test_doc_result_to_dict_shape(self, cases, golden_by_input):
        spec = _spec("echo")
        converters = {"echo": FakeConverter("echo", _ALL_EXTS, golden_by_input, "echo")}
        results = run_benchmark(spec, cases, converters=converters)
        d = results.doc_results[0].to_dict()
        assert set(d) == {
            "converter",
            "slug",
            "doc_kind",
            "fmt",
            "status",
            "scores",
            "weighted",
            "elapsed_s",
            "pages",
            "cost",
        }
        assert isinstance(d["scores"], dict)


def test_dataclasses_are_constructible():
    scores = CategoryScores(1.0, 1.0, 1.0, 1.0)
    doc = DocResult("c", "s", "k", "pdf", "scored", scores, 1.0, 0.1, 1, 0.0)
    agg = ConverterAggregate(
        "c", True, True, 0.0, 1, 0, 0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.1, 0.1, 0.0, True
    )
    res = BenchResults(1, 1, CategoryWeights().to_dict(), 0.7, [agg], [doc])
    assert res.to_dict()["converters"][0]["name"] == "c"
