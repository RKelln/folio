"""Execute converters over the benchmark corpus, time them, aggregate scores.

The runner is the orchestration stage of the offline converter benchmark. It
ties together the already-landed foundation:

* :mod:`folio.core.bench.spec`   — which converters to run and how to weight
  the four scoring categories.
* :mod:`folio.core.bench.corpus` — the (golden, rendered-input) case pairs.
* :mod:`folio.core.bench.scorer` — deterministic per-category fidelity scores.
* :mod:`folio.adapters.converters` — the pluggable ``Converter`` adapters.

For every enabled converter the runner attempts each corpus case: it skips
inputs whose extension the converter does not support, times the actual
``convert()`` call with :func:`time.perf_counter`, scores any output against
its golden reference, and rolls the per-document results up into one
:class:`ConverterAggregate` per converter. Quality scores are fully
deterministic; only wall-clock timings vary between runs.

Public API (imported by :mod:`folio.core.bench.report` and ``cli/bench.py``):

* :class:`DocResult`
* :class:`ConverterAggregate`
* :class:`BenchResults`
* :func:`weighted_score`
* :func:`estimate_pages`
* :func:`resolve_converters`
* :func:`run_benchmark`
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

from folio.adapters.converters import Converter, get_converter
from folio.core.bench.corpus import BenchCase, read_golden
from folio.core.bench.scorer import CategoryScores, score_document
from folio.core.bench.spec import BenchSpec, CategoryWeights

logger = logging.getLogger(__name__)

#: Heuristic word budget per "page" for the dependency-free page estimate.
_WORDS_PER_PAGE = 500


@dataclass
class DocResult:
    """Outcome of running one converter against one corpus case.

    Attributes:
        converter: Converter name (matches :class:`ConverterSpec.name`).
        slug: Corpus slug, e.g. ``"oac-application-01"``.
        doc_kind: Document kind parsed from the slug, e.g. ``"budget"``.
        fmt: Input format — ``pdf``/``docx``/``xlsx``/``pdf_scanned``.
        status: ``"scored"``, ``"failed"`` or ``"unsupported"``.
        scores: Per-category scores, or ``None`` unless ``status == "scored"``.
        weighted: Aggregate weighted score in ``[0, 1]`` (``0.0`` unless scored).
        elapsed_s: Wall-clock ``convert()`` time in seconds (``0.0`` if not run).
        pages: Deterministic page estimate (always ``>= 1``).
        cost: ``cost_per_page * pages`` for the converter.
    """

    converter: str
    slug: str
    doc_kind: str
    fmt: str
    status: str
    scores: CategoryScores | None
    weighted: float
    elapsed_s: float
    pages: int
    cost: float

    def to_dict(self) -> dict:
        """Return a plain, JSON-serializable dict for this document result."""
        return {
            "converter": self.converter,
            "slug": self.slug,
            "doc_kind": self.doc_kind,
            "fmt": self.fmt,
            "status": self.status,
            "scores": self.scores.to_dict() if self.scores is not None else None,
            "weighted": self.weighted,
            "elapsed_s": self.elapsed_s,
            "pages": self.pages,
            "cost": self.cost,
        }


@dataclass
class ConverterAggregate:
    """Roll-up of one converter's results across the whole corpus.

    Means are computed over *scored* documents only; a converter with no scored
    documents has ``0.0`` means and ``passed == False``.

    Attributes:
        name: Converter name.
        available: ``False`` when the converter could not be resolved (e.g. an
            unimplemented adapter); such converters contribute no documents.
        offline: Whether the converter runs fully offline (from the spec).
        cost_per_page: Estimated USD cost per page (from the spec).
        n_scored: Number of documents scored successfully.
        n_failed: Number of documents where ``convert()`` returned ``None``/raised.
        n_unsupported: Number of documents whose format the converter rejected.
        mean_weighted: Mean weighted score over scored documents.
        mean_text: Mean text-category score over scored documents.
        mean_tables: Mean tables-category score over scored documents.
        mean_structure: Mean structure-category score over scored documents.
        mean_links_images: Mean links/images-category score over scored documents.
        total_elapsed_s: Total wall-clock convert time over scored documents.
        mean_elapsed_per_page_s: Mean ``elapsed_s / pages`` over scored documents.
        total_cost: Total estimated cost over scored documents.
        passed: ``True`` iff ``n_scored > 0`` and ``mean_weighted`` meets the
            spec's ``pass_threshold``.
    """

    name: str
    available: bool
    offline: bool
    cost_per_page: float
    n_scored: int
    n_failed: int
    n_unsupported: int
    mean_weighted: float
    mean_text: float
    mean_tables: float
    mean_structure: float
    mean_links_images: float
    total_elapsed_s: float
    mean_elapsed_per_page_s: float
    total_cost: float
    passed: bool

    def to_dict(self) -> dict:
        """Return a plain, JSON-serializable dict for this aggregate."""
        return {
            "name": self.name,
            "available": self.available,
            "offline": self.offline,
            "cost_per_page": self.cost_per_page,
            "n_scored": self.n_scored,
            "n_failed": self.n_failed,
            "n_unsupported": self.n_unsupported,
            "mean_weighted": self.mean_weighted,
            "mean_text": self.mean_text,
            "mean_tables": self.mean_tables,
            "mean_structure": self.mean_structure,
            "mean_links_images": self.mean_links_images,
            "total_elapsed_s": self.total_elapsed_s,
            "mean_elapsed_per_page_s": self.mean_elapsed_per_page_s,
            "total_cost": self.total_cost,
            "passed": self.passed,
        }


@dataclass
class BenchResults:
    """The complete result of a benchmark run.

    Attributes:
        n_cases: Number of corpus cases evaluated.
        n_converters: Number of enabled converters considered.
        weights: The configured :class:`CategoryWeights` as a plain dict.
        pass_threshold: The spec's pass threshold in ``[0, 1]``.
        converters: One :class:`ConverterAggregate` per enabled converter, in
            spec order.
        doc_results: Every :class:`DocResult`, grouped by converter then case.
    """

    n_cases: int
    n_converters: int
    weights: dict
    pass_threshold: float
    converters: list[ConverterAggregate]
    doc_results: list[DocResult]

    def to_dict(self) -> dict:
        """Return a plain, JSON-serializable dict for the whole run."""
        return {
            "n_cases": self.n_cases,
            "n_converters": self.n_converters,
            "weights": self.weights,
            "pass_threshold": self.pass_threshold,
            "converters": [c.to_dict() for c in self.converters],
            "doc_results": [d.to_dict() for d in self.doc_results],
        }


def _clamp01(value: float) -> float:
    """Clamp ``value`` to the closed interval ``[0, 1]``."""
    return max(0.0, min(1.0, value))


def weighted_score(scores: CategoryScores, weights: CategoryWeights) -> float:
    """Combine per-category scores into one weighted score in ``[0, 1]``.

    The dot product of the category scores with the *normalized* weights (so
    the result stays in ``[0, 1]`` regardless of how the raw weights are
    scaled). The result is clamped defensively.
    """
    norm = weights.normalized()
    combined = (
        scores.text * norm.text
        + scores.tables * norm.tables
        + scores.structure * norm.structure
        + scores.links_images * norm.links_images
    )
    return _clamp01(combined)


def estimate_pages(case: BenchCase) -> int:
    """Estimate the page count of a case from its golden reference length.

    Deterministic and dependency-free: counts whitespace-delimited words in the
    golden Markdown and divides by :data:`_WORDS_PER_PAGE`, with a floor of one
    page. The PDF itself is never parsed (no new dependencies), so the estimate
    is identical on every run and is used for time-per-page and cost figures.
    """
    text = read_golden(case.golden_path)
    word_count = len(text.split())
    return max(1, math.ceil(word_count / _WORDS_PER_PAGE))


def resolve_converters(spec: BenchSpec) -> dict[str, Converter | None]:
    """Resolve each enabled converter name to an instance (or ``None``).

    For every converter in :meth:`BenchSpec.enabled_converters` this calls
    :func:`folio.adapters.converters.get_converter`. A converter that is not
    implemented (raises ``NotImplementedError``, e.g. ``marker``) or unknown
    (raises ``ValueError``) maps to ``None`` and is reported as unavailable.
    Missing third-party libraries are *not* detected here — they surface later
    as ``convert()`` returning ``None`` per the ``Converter`` contract.

    Args:
        spec: The benchmark spec.

    Returns:
        Mapping of converter name to a :class:`Converter` instance or ``None``.
    """
    resolved: dict[str, Converter | None] = {}
    for conv_spec in spec.enabled_converters():
        try:
            resolved[conv_spec.name] = get_converter(conv_spec.name)
        except (NotImplementedError, ValueError) as exc:
            logger.warning("Converter %r unavailable: %s", conv_spec.name, exc)
            resolved[conv_spec.name] = None
    return resolved


def _run_case(
    conv_name: str,
    converter: Converter,
    case: BenchCase,
    weights: CategoryWeights,
    pages: int,
    cost: float,
) -> DocResult:
    """Run one converter against one case and return its :class:`DocResult`."""

    def build(
        status: str,
        scores: CategoryScores | None,
        weighted: float,
        elapsed_s: float,
    ) -> DocResult:
        return DocResult(
            converter=conv_name,
            slug=case.slug,
            doc_kind=case.doc_kind,
            fmt=case.fmt,
            status=status,
            scores=scores,
            weighted=weighted,
            elapsed_s=elapsed_s,
            pages=pages,
            cost=cost,
        )

    suffix = case.input_path.suffix.lower()
    if suffix not in converter.supported_extensions:
        return build("unsupported", None, 0.0, 0.0)

    start = time.perf_counter()
    try:
        output = converter.convert(case.input_path)
    except Exception:
        logger.exception(
            "Converter %r raised converting %s", conv_name, case.input_path
        )
        output = None
    elapsed_s = time.perf_counter() - start

    if output is None:
        return build("failed", None, 0.0, elapsed_s)

    scores = score_document(read_golden(case.golden_path), output)
    return build("scored", scores, weighted_score(scores, weights), elapsed_s)


def _mean(values: list[float]) -> float:
    """Return the arithmetic mean of ``values`` (``0.0`` for an empty list)."""
    return sum(values) / len(values) if values else 0.0


def _aggregate(
    conv_spec_name: str,
    offline: bool,
    cost_per_page: float,
    available: bool,
    results: list[DocResult],
    pass_threshold: float,
) -> ConverterAggregate:
    """Roll a converter's per-document results into a :class:`ConverterAggregate`."""
    scored = [r for r in results if r.status == "scored"]
    n_scored = len(scored)
    mean_weighted = _mean([r.weighted for r in scored])
    return ConverterAggregate(
        name=conv_spec_name,
        available=available,
        offline=offline,
        cost_per_page=cost_per_page,
        n_scored=n_scored,
        n_failed=sum(1 for r in results if r.status == "failed"),
        n_unsupported=sum(1 for r in results if r.status == "unsupported"),
        mean_weighted=mean_weighted,
        mean_text=_mean([r.scores.text for r in scored if r.scores is not None]),
        mean_tables=_mean([r.scores.tables for r in scored if r.scores is not None]),
        mean_structure=_mean(
            [r.scores.structure for r in scored if r.scores is not None]
        ),
        mean_links_images=_mean(
            [r.scores.links_images for r in scored if r.scores is not None]
        ),
        total_elapsed_s=sum(r.elapsed_s for r in scored),
        mean_elapsed_per_page_s=_mean([r.elapsed_s / r.pages for r in scored]),
        total_cost=sum(r.cost for r in scored),
        passed=n_scored > 0 and mean_weighted >= pass_threshold,
    )


def run_benchmark(
    spec: BenchSpec,
    cases: list[BenchCase],
    converters: dict[str, Converter | None] | None = None,
    progress: bool = False,
) -> BenchResults:
    """Run every enabled converter over every case and aggregate the scores.

    Args:
        spec: The benchmark spec (drives converter selection and weights).
        cases: The corpus cases to evaluate (from
            :func:`folio.core.bench.corpus.discover_cases`).
        converters: Optional pre-resolved name → instance mapping. Defaults to
            :func:`resolve_converters` and is injectable so tests can supply
            in-memory fakes. A ``None`` value marks a converter unavailable.
        progress: When ``True``, wrap the per-converter case loop in a ``tqdm``
            progress bar.

    Returns:
        A :class:`BenchResults` with one aggregate per enabled converter and a
        flat list of every :class:`DocResult`. Quality scores are deterministic;
        only wall-clock timings vary between runs.
    """
    if converters is None:
        converters = resolve_converters(spec)

    weights = spec.weights
    enabled = spec.enabled_converters()
    doc_results: list[DocResult] = []
    aggregates: list[ConverterAggregate] = []

    for conv_spec in enabled:
        instance = converters.get(conv_spec.name)
        if instance is None:
            aggregates.append(
                _aggregate(
                    conv_spec.name,
                    conv_spec.offline,
                    conv_spec.cost_per_page,
                    available=False,
                    results=[],
                    pass_threshold=spec.pass_threshold,
                )
            )
            continue

        iterable: list[BenchCase] = cases
        if progress:
            from tqdm import tqdm

            iterable = tqdm(cases, desc=conv_spec.name, unit="doc")

        converter_results: list[DocResult] = []
        for case in iterable:
            pages = estimate_pages(case)
            result = _run_case(
                conv_spec.name,
                instance,
                case,
                weights,
                pages,
                conv_spec.cost_per_page * pages,
            )
            converter_results.append(result)
            doc_results.append(result)

        aggregates.append(
            _aggregate(
                conv_spec.name,
                conv_spec.offline,
                conv_spec.cost_per_page,
                available=True,
                results=converter_results,
                pass_threshold=spec.pass_threshold,
            )
        )

    return BenchResults(
        n_cases=len(cases),
        n_converters=len(enabled),
        weights=weights.to_dict(),
        pass_threshold=spec.pass_threshold,
        converters=aggregates,
        doc_results=doc_results,
    )
