"""Loader, schema, and validator for the offline converter-benchmark spec.

This is a **standalone** spec — deliberately separate from ``folio.yaml`` /
``ProjectConfig``. It describes *which* converters to benchmark, *how* their
outputs are weighted across scoring categories, and the aggregate score that
counts as "passing". The spec is consumed by the benchmark runner
(``folio.core.bench.runner``) and the ``folio bench`` CLI.

Design mirrors ``folio.core.corpus.spec`` (standalone dataclasses + YAML load +
``validate_spec`` + bundled-default-via-importlib.resources) so the benchmark
tooling has no dependency on the project config. The bundled default lives at
``folio/templates/bench/bench-spec.yaml`` and is fully commented.

Public API (imported by runner.py, scorer.py and cli/bench.py):

* :class:`ConverterSpec`
* :class:`CategoryWeights`
* :class:`BenchSpec`
* :data:`DEFAULT_CONVERTERS`
* :func:`validate_spec`
* :func:`load_bench_spec`
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from importlib import resources
from pathlib import Path

import yaml


@dataclass
class ConverterSpec:
    """One converter to benchmark.

    Attributes:
        name: Converter identifier (e.g. ``"liteparse"``, ``"pandoc"``). Must
            be a non-empty string; the runner uses it to select the adapter.
        enabled: Whether this converter runs by default. Disabled converters
            stay in the spec for documentation but are skipped unless a CLI
            flag re-enables them.
        offline: ``True`` if the converter runs entirely locally with no
            network access. ``False`` marks a hosted/API converter.
        cost_per_page: Estimated USD cost per rendered page. ``0.0`` for free
            local converters; ``> 0`` for paid hosted ones. Must be ``>= 0``.
    """

    name: str
    enabled: bool = True
    offline: bool = True
    cost_per_page: float = 0.0

    def to_dict(self) -> dict:
        """Return a plain, JSON-serializable dict for this converter."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "offline": self.offline,
            "cost_per_page": self.cost_per_page,
        }


#: Default converter line-up shipped with folio. Offline/free converters are
#: enabled; the paid hosted (``datalab``) and the heavier optional
#: (``marker``) converters ship disabled so the default benchmark is fully
#: offline and free. ``BenchSpec`` copies these per-instance so mutating one
#: spec's converters never leaks into another.
DEFAULT_CONVERTERS: list[ConverterSpec] = [
    ConverterSpec(name="liteparse", enabled=True, offline=True, cost_per_page=0.0),
    ConverterSpec(name="docling", enabled=True, offline=True, cost_per_page=0.0),
    ConverterSpec(name="pandoc", enabled=True, offline=True, cost_per_page=0.0),
    ConverterSpec(name="datalab", enabled=False, offline=False, cost_per_page=0.003),
    ConverterSpec(name="marker", enabled=False, offline=True, cost_per_page=0.0),
]


def _default_converters() -> list[ConverterSpec]:
    """Return fresh copies of :data:`DEFAULT_CONVERTERS` for a new spec."""
    return [replace(c) for c in DEFAULT_CONVERTERS]


_WEIGHT_FIELDS = ("text", "tables", "structure", "links_images")


@dataclass
class CategoryWeights:
    """Relative weights for the four scoring categories.

    Weights need not sum to 1; :meth:`normalized` rescales them. Each weight
    must be a non-negative number and at least one must be positive.

    Attributes:
        text: Weight for textual fidelity (the bulk of most documents).
        tables: Weight for tabular reconstruction (budgets, rosters).
        structure: Weight for heading/section structure.
        links_images: Weight for link and image preservation.
    """

    text: float = 0.4
    tables: float = 0.25
    structure: float = 0.25
    links_images: float = 0.10

    def normalized(self) -> CategoryWeights:
        """Return a copy with weights divided by their sum.

        Raises:
            ValueError: The weights sum to zero (or less), so normalization is
                undefined.
        """
        total = self.text + self.tables + self.structure + self.links_images
        if total <= 0:
            raise ValueError("CategoryWeights cannot be normalized: sum must be > 0")
        return CategoryWeights(
            text=self.text / total,
            tables=self.tables / total,
            structure=self.structure / total,
            links_images=self.links_images / total,
        )

    def to_dict(self) -> dict:
        """Return a plain, JSON-serializable dict for these weights."""
        return {
            "text": self.text,
            "tables": self.tables,
            "structure": self.structure,
            "links_images": self.links_images,
        }


@dataclass
class BenchSpec:
    """Top-level offline-benchmark specification.

    Attributes:
        corpus_dir: Directory (relative to the org library) holding the
            committed synthetic corpus produced by ``folio corpus``.
        golden_subdir: Subdirectory of ``corpus_dir`` with the golden
            Markdown references.
        rendered_subdir: Subdirectory of ``corpus_dir`` with the rendered
            converter inputs (pdf/docx/xlsx/scanned-pdf).
        converters: The :class:`ConverterSpec` entries to benchmark. Must be
            non-empty.
        weights: :class:`CategoryWeights` used to aggregate per-category
            scores into a single weighted score.
        pass_threshold: Aggregate weighted score in ``[0, 1]`` at or above
            which a converter's result is considered "passing".
    """

    corpus_dir: str = "benchmark/corpus"
    golden_subdir: str = "golden"
    rendered_subdir: str = "rendered"
    converters: list[ConverterSpec] = field(default_factory=_default_converters)
    weights: CategoryWeights = field(default_factory=CategoryWeights)
    pass_threshold: float = 0.7

    def to_dict(self) -> dict:
        """Return a plain, JSON-serializable dict (for ``--json`` / reports)."""
        return {
            "corpus_dir": self.corpus_dir,
            "golden_subdir": self.golden_subdir,
            "rendered_subdir": self.rendered_subdir,
            "converters": [c.to_dict() for c in self.converters],
            "weights": self.weights.to_dict(),
            "pass_threshold": self.pass_threshold,
        }

    def enabled_converters(self) -> list[ConverterSpec]:
        """Return only the converters whose ``enabled`` flag is true."""
        return [c for c in self.converters if c.enabled]


def _default_spec_path() -> Path:
    """Resolve the bundled default ``bench-spec.yaml`` shipped with folio.

    Tries importlib.resources first (works for installed packages) and falls
    back to a path relative to this module (works in an editable/source tree),
    mirroring ``folio.core.corpus.spec._default_spec_path``.
    """
    try:
        traversable = resources.files("folio.templates") / "bench" / "bench-spec.yaml"
        candidate = Path(str(traversable))
        if candidate.exists():
            return candidate
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    # parents[2] == folio package root (bench -> core -> folio).
    return Path(__file__).resolve().parents[2] / "templates" / "bench" / "bench-spec.yaml"


def _build_spec(data: dict) -> BenchSpec:
    """Build a :class:`BenchSpec` from a parsed YAML mapping.

    Values are passed through *without coercion* so that :func:`validate_spec`
    can report type problems instead of crashing here.

    Raises:
        ValueError: ``data`` is not a mapping, or ``converters`` / ``weights``
            have the wrong container type.
    """
    if not isinstance(data, dict):
        raise ValueError(f"bench spec must be a YAML mapping, got {type(data).__name__}")

    spec = BenchSpec()

    for key in ("corpus_dir", "golden_subdir", "rendered_subdir", "pass_threshold"):
        if key in data:
            setattr(spec, key, data[key])

    if "weights" in data:
        raw_weights = data["weights"]
        if not isinstance(raw_weights, dict):
            raise ValueError(
                f"'weights' must be a mapping, got {type(raw_weights).__name__}"
            )
        defaults = CategoryWeights()
        spec.weights = CategoryWeights(
            text=raw_weights.get("text", defaults.text),
            tables=raw_weights.get("tables", defaults.tables),
            structure=raw_weights.get("structure", defaults.structure),
            links_images=raw_weights.get("links_images", defaults.links_images),
        )

    if "converters" in data:
        raw_converters = data["converters"]
        if not isinstance(raw_converters, list):
            raise ValueError(
                f"'converters' must be a list, got {type(raw_converters).__name__}"
            )
        converters: list[ConverterSpec] = []
        for entry in raw_converters:
            if not isinstance(entry, dict):
                raise ValueError(
                    f"each converter entry must be a mapping, got {type(entry).__name__}"
                )
            converters.append(
                ConverterSpec(
                    name=entry.get("name", ""),
                    enabled=entry.get("enabled", True),
                    offline=entry.get("offline", True),
                    cost_per_page=entry.get("cost_per_page", 0.0),
                )
            )
        spec.converters = converters

    return spec


def _is_number(value: object) -> bool:
    """Return ``True`` if ``value`` is a real number (``bool`` excluded)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_spec(spec: BenchSpec) -> list[str]:
    """Validate a :class:`BenchSpec`, returning human-readable error strings.

    An empty list means the spec is valid. This function never raises; callers
    that want hard failure (such as :func:`load_bench_spec`) join the returned
    errors and raise ``ValueError`` themselves.

    Checks performed:
        * ``corpus_dir`` / ``golden_subdir`` / ``rendered_subdir`` are
          non-empty strings.
        * ``pass_threshold`` is a number in ``[0, 1]``.
        * every weight is a non-negative number and their sum is ``> 0``.
        * ``converters`` is non-empty.
        * each converter ``name`` is a non-empty string and ``cost_per_page``
          is a number ``>= 0``.
    """
    errors: list[str] = []

    for attr in ("corpus_dir", "golden_subdir", "rendered_subdir"):
        value = getattr(spec, attr)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{attr} must be a non-empty string, got: {value!r}")

    if not _is_number(spec.pass_threshold):
        errors.append(f"pass_threshold must be a number, got: {spec.pass_threshold!r}")
    elif not (0.0 <= spec.pass_threshold <= 1.0):
        errors.append(
            f"pass_threshold must be in [0, 1], got: {spec.pass_threshold!r}"
        )

    weight_total = 0.0
    for wattr in _WEIGHT_FIELDS:
        value = getattr(spec.weights, wattr)
        if not _is_number(value):
            errors.append(f"weight {wattr!r} must be a number, got: {value!r}")
        elif value < 0:
            errors.append(f"weight {wattr!r} must be >= 0, got: {value!r}")
        else:
            weight_total += value
    if weight_total <= 0:
        errors.append("weights must sum to a positive number")

    if not spec.converters:
        errors.append("converters must contain at least one entry")

    for i, conv in enumerate(spec.converters):
        label = f"converters[{i}]"
        if not isinstance(conv.name, str) or not conv.name.strip():
            errors.append(f"{label}: name must be a non-empty string, got: {conv.name!r}")
        if not _is_number(conv.cost_per_page):
            errors.append(
                f"{label}: cost_per_page must be a number, got: {conv.cost_per_page!r}"
            )
        elif conv.cost_per_page < 0:
            errors.append(
                f"{label}: cost_per_page must be >= 0, got: {conv.cost_per_page!r}"
            )

    return errors


def load_bench_spec(path: str | Path | None = None) -> BenchSpec:
    """Load and validate a benchmark spec from YAML.

    Args:
        path: Path to a ``bench-spec.yaml``. When ``None`` (the default), the
            bundled template at ``folio/templates/bench/bench-spec.yaml`` is
            loaded.

    Returns:
        A validated :class:`BenchSpec`.

    Raises:
        FileNotFoundError: The spec file does not exist.
        ValueError: The file is not valid YAML, is not a mapping, or fails
            :func:`validate_spec`.
    """
    spec_path = _default_spec_path() if path is None else Path(path)

    if not spec_path.exists():
        raise FileNotFoundError(f"Bench spec not found: {spec_path}")

    with open(spec_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    spec = _build_spec(data)

    errors = validate_spec(spec)
    if errors:
        joined = "\n  - ".join(errors)
        raise ValueError(f"Invalid bench spec ({spec_path}):\n  - {joined}")

    return spec
