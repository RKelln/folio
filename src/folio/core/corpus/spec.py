"""Loader, schema, and validator for the synthetic-corpus spec.

This is a **standalone** spec — deliberately separate from ``folio.yaml`` /
``ProjectConfig``. It describes *which* synthetic grant documents to generate,
*how many* of each, and *in which formats*. The spec is consumed by the corpus
generator (``folio.core.corpus.generator``) and the ``folio corpus`` CLI.

Design mirrors ``folio.config.loader`` (dataclass + YAML load + validate) but
keeps its own dataclasses so the corpus tooling has no dependency on the
project config. The bundled default lives at
``folio/templates/corpus/corpus-spec.yaml`` and is fully commented.

Public API (imported by generator.py and cli/corpus.py):

* :class:`DocSpec`
* :class:`CorpusSpec`
* :func:`load_corpus_spec`
* :func:`validate_spec`
* :data:`ALLOWED_KINDS`
* :data:`ALLOWED_FORMATS`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

#: Document *kinds* the corpus generator knows how to author. A spec entry
#: whose ``kind`` is outside this set is rejected by :func:`validate_spec`.
ALLOWED_KINDS: set[str] = {
    "application",
    "narrative",
    "budget",
    "activity_list",
    "staff_board",
    "support_letter",
}

#: Output *formats* a document may be rendered to. ``md`` is the authored
#: golden source; the rest are derived renders. ``pdf_scanned`` is an
#: image-only (rasterized) PDF used to exercise OCR paths.
ALLOWED_FORMATS: set[str] = {
    "md",
    "docx",
    "xlsx",
    "pdf",
    "pdf_scanned",
}


@dataclass
class DocSpec:
    """One line item in a corpus spec: a document kind and how to emit it.

    Attributes:
        kind: One of :data:`ALLOWED_KINDS` (e.g. ``"application"``).
        count: How many distinct synthetic documents of this kind to generate.
            Must be ``>= 1``.
        formats: Output formats to render for each generated document. Each
            entry must be in :data:`ALLOWED_FORMATS`. Defaults to ``["md"]``.
    """

    kind: str
    count: int = 1
    formats: list[str] = field(default_factory=lambda: ["md"])

    def to_dict(self) -> dict:
        """Return a plain, JSON-serializable dict for this document spec."""
        return {
            "kind": self.kind,
            "count": self.count,
            "formats": list(self.formats),
        }


@dataclass
class CorpusSpec:
    """Top-level synthetic-corpus specification.

    Attributes:
        seed: Deterministic RNG seed. The same seed must always reproduce the
            same corpus. Must be an ``int`` (``bool`` is not accepted).
        profile: folio profile name the corpus is modeled on (used to pick
            heading taxonomies / vocabulary). See
            ``folio/templates/profiles/``.
        funder: Funder abbreviation the documents target (e.g. ``"OAC"``,
            ``"TAC"``, ``"CCA"``, ``"BCAH"``). Must be a non-empty string.
        output_dir: Directory (relative to the org library) where generated
            documents are written. Defaults to ``"benchmark/corpus"``.
        documents: The list of :class:`DocSpec` entries to generate. Must be
            non-empty for a usable spec.
    """

    seed: int = 1234
    profile: str = "canadian-artist-run-centre"
    funder: str = "OAC"
    output_dir: str = "benchmark/corpus"
    documents: list[DocSpec] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a plain, JSON-serializable dict (for ``--json`` / manifests)."""
        return {
            "seed": self.seed,
            "profile": self.profile,
            "funder": self.funder,
            "output_dir": self.output_dir,
            "documents": [doc.to_dict() for doc in self.documents],
        }

    def total_outputs(self) -> int:
        """Total number of output files: ``sum(count * len(formats))``."""
        return sum(doc.count * len(doc.formats) for doc in self.documents)


def _default_spec_path() -> Path:
    """Resolve the bundled default ``corpus-spec.yaml`` shipped with folio."""
    return Path(str(resources.files("folio.templates") / "corpus" / "corpus-spec.yaml"))


def _build_spec(data: dict) -> CorpusSpec:
    """Build a :class:`CorpusSpec` from a parsed YAML mapping.

    Values are passed through *without coercion* so that :func:`validate_spec`
    can report type problems (e.g. a non-int seed) instead of crashing here.

    Raises:
        ValueError: ``data`` is not a mapping, or ``documents`` is not a list.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"corpus spec must be a YAML mapping, got {type(data).__name__}"
        )

    raw_documents = data.get("documents", [])
    if not isinstance(raw_documents, list):
        raise ValueError(
            f"'documents' must be a list, got {type(raw_documents).__name__}"
        )

    documents: list[DocSpec] = []
    for entry in raw_documents:
        if not isinstance(entry, dict):
            raise ValueError(
                f"each document entry must be a mapping, got {type(entry).__name__}"
            )
        formats = entry.get("formats", ["md"])
        if isinstance(formats, str):
            formats = [formats]
        documents.append(
            DocSpec(
                kind=entry.get("kind", ""),
                count=entry.get("count", 1),
                formats=list(formats) if isinstance(formats, list) else formats,
            )
        )

    spec = CorpusSpec(documents=documents)
    if "seed" in data:
        spec.seed = data["seed"]
    if "profile" in data:
        spec.profile = data["profile"]
    if "funder" in data:
        spec.funder = data["funder"]
    if "output_dir" in data:
        spec.output_dir = data["output_dir"]
    return spec


def validate_spec(spec: CorpusSpec) -> list[str]:
    """Validate a :class:`CorpusSpec`, returning human-readable error strings.

    An empty list means the spec is valid. This function never raises; callers
    that want hard failure (such as :func:`load_corpus_spec`) join the returned
    errors and raise ``ValueError`` themselves.

    Checks performed:
        * ``seed`` is an ``int`` (and not a ``bool``).
        * ``documents`` is non-empty.
        * each document ``kind`` is in :data:`ALLOWED_KINDS`.
        * each document ``format`` is in :data:`ALLOWED_FORMATS`.
        * each document ``count`` is an ``int`` ``>= 1``.
        * ``funder`` is a non-empty string.
    """
    errors: list[str] = []

    if isinstance(spec.seed, bool) or not isinstance(spec.seed, int):
        errors.append(f"seed must be an integer, got: {spec.seed!r}")

    if not isinstance(spec.funder, str) or not spec.funder.strip():
        errors.append(f"funder must be a non-empty string, got: {spec.funder!r}")

    if not spec.documents:
        errors.append("documents must contain at least one entry")

    for i, doc in enumerate(spec.documents):
        label = f"documents[{i}]"

        if doc.kind not in ALLOWED_KINDS:
            errors.append(
                f"{label}: invalid kind {doc.kind!r}; "
                f"must be one of {', '.join(sorted(ALLOWED_KINDS))}"
            )

        if isinstance(doc.count, bool) or not isinstance(doc.count, int):
            errors.append(f"{label}: count must be an integer, got: {doc.count!r}")
        elif doc.count < 1:
            errors.append(f"{label}: count must be >= 1, got: {doc.count}")

        if not isinstance(doc.formats, list) or not doc.formats:
            errors.append(f"{label}: formats must be a non-empty list, got: {doc.formats!r}")
        else:
            for fmt in doc.formats:
                if fmt not in ALLOWED_FORMATS:
                    errors.append(
                        f"{label}: invalid format {fmt!r}; "
                        f"must be one of {', '.join(sorted(ALLOWED_FORMATS))}"
                    )

    return errors


def load_corpus_spec(path: str | Path | None = None) -> CorpusSpec:
    """Load and validate a corpus spec from YAML.

    Args:
        path: Path to a ``corpus-spec.yaml``. When ``None`` (the default), the
            bundled template at ``folio/templates/corpus/corpus-spec.yaml`` is
            loaded.

    Returns:
        A validated :class:`CorpusSpec`.

    Raises:
        FileNotFoundError: The spec file does not exist.
        ValueError: The file is not valid YAML, is not a mapping, or fails
            :func:`validate_spec`.
    """
    spec_path = _default_spec_path() if path is None else Path(path)

    if not spec_path.exists():
        raise FileNotFoundError(f"Corpus spec not found: {spec_path}")

    with open(spec_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    spec = _build_spec(data)

    errors = validate_spec(spec)
    if errors:
        joined = "\n  - ".join(errors)
        raise ValueError(f"Invalid corpus spec ({spec_path}):\n  - {joined}")

    return spec
