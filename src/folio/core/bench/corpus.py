"""Discover golden/rendered benchmark case pairs from the synthetic corpus.

The committed corpus (``benchmark/corpus/``, produced by ``folio corpus``) is
laid out as::

    <corpus_dir>/golden/<slug>.md          # authored golden Markdown reference
    <corpus_dir>/rendered/<slug>.<ext>      # converter inputs derived from it

where ``<slug>`` is ``<funder>-<kind>-<NN>`` (kind may contain underscores,
e.g. ``oac-activity_list-01``) and ``<ext>`` is one of ``pdf``, ``docx``,
``xlsx``, or ``scanned.pdf`` (image-only PDF for OCR paths).

This module pairs each rendered input with its golden reference so the runner
can convert the input and the scorer can compare against the golden. It is
deterministic and offline.

Public API (imported by runner.py and cli/bench.py):

* :class:`BenchCase`
* :func:`parse_slug`
* :func:`read_golden`
* :func:`discover_cases`
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: Maps a rendered-file extension to ``(fmt, is_scanned)``. Order matters at
#: the call site: the multi-dotted ``.scanned.pdf`` must be tested before the
#: plain ``.pdf`` so it is not mis-classified.
_SUFFIX_FORMATS: tuple[tuple[str, str, bool], ...] = (
    (".scanned.pdf", "pdf_scanned", True),
    (".pdf", "pdf", False),
    (".docx", "docx", False),
    (".xlsx", "xlsx", False),
)


@dataclass
class BenchCase:
    """One (golden, rendered-input) pair to benchmark.

    Attributes:
        slug: The corpus slug, e.g. ``"oac-application-01"``.
        funder: Lowercase funder token parsed from the slug, e.g. ``"oac"``.
        doc_kind: Document kind parsed from the slug, e.g. ``"activity_list"``.
        index: Trailing numeric index parsed from the slug, e.g. ``1``.
        golden_path: Path to the golden ``<slug>.md`` reference.
        input_path: Path to the rendered converter input.
        fmt: Input format — ``"pdf"``, ``"docx"``, ``"xlsx"`` or
            ``"pdf_scanned"``.
        is_scanned: ``True`` for image-only ``.scanned.pdf`` inputs.
    """

    slug: str
    funder: str
    doc_kind: str
    index: int
    golden_path: Path
    input_path: Path
    fmt: str
    is_scanned: bool


def parse_slug(slug: str) -> tuple[str, str, int]:
    """Parse a corpus slug into ``(funder, kind, index)``.

    The slug format is ``<funder>-<kind>-<NN>``. The funder is the token before
    the first ``-``; the index is the trailing ``-NN`` (all digits); the kind
    is everything in between and may itself contain underscores (but not
    dashes), e.g. ``oac-activity_list-01`` -> ``("oac", "activity_list", 1)``.

    Raises:
        ValueError: ``slug`` is malformed (fewer than three ``-``-separated
            parts, an empty funder or kind, or a non-numeric index).
    """
    parts = slug.split("-")
    if len(parts) < 3:
        raise ValueError(f"malformed slug {slug!r}: expected <funder>-<kind>-<NN>")

    funder = parts[0]
    index_token = parts[-1]
    kind = "-".join(parts[1:-1])

    if not funder:
        raise ValueError(f"malformed slug {slug!r}: empty funder")
    if not kind:
        raise ValueError(f"malformed slug {slug!r}: empty kind")
    if not index_token.isdigit():
        raise ValueError(
            f"malformed slug {slug!r}: index {index_token!r} is not numeric"
        )

    return funder, kind, int(index_token)


def read_golden(path: Path) -> str:
    """Read a golden Markdown file as UTF-8 text.

    The returned text is verbatim — YAML frontmatter is **not** stripped; that
    is the scorer's responsibility.
    """
    return Path(path).read_text(encoding="utf-8")


def _classify_input(name: str) -> tuple[str, str, bool] | None:
    """Return ``(slug, fmt, is_scanned)`` for a rendered filename, or ``None``.

    ``None`` means the filename does not match any known rendered-input suffix
    and should be skipped.
    """
    for suffix, fmt, is_scanned in _SUFFIX_FORMATS:
        if name.endswith(suffix):
            return name[: -len(suffix)], fmt, is_scanned
    return None


def discover_cases(
    corpus_dir: str | Path,
    golden_subdir: str = "golden",
    rendered_subdir: str = "rendered",
) -> list[BenchCase]:
    """Discover all (golden, rendered-input) pairs under ``corpus_dir``.

    Every file in ``<corpus_dir>/<rendered_subdir>`` is matched to its golden
    reference at ``<corpus_dir>/<golden_subdir>/<slug>.md``. Inputs with an
    unrecognized extension, a malformed slug, or a missing golden reference are
    skipped with a logged warning rather than raising. A missing corpus or
    rendered directory yields an empty list (with a warning).

    Args:
        corpus_dir: Root of the corpus.
        golden_subdir: Name of the golden-references subdirectory.
        rendered_subdir: Name of the rendered-inputs subdirectory.

    Returns:
        Cases sorted deterministically by ``(slug, fmt)``.
    """
    corpus_path = Path(corpus_dir)
    rendered_dir = corpus_path / rendered_subdir
    golden_dir = corpus_path / golden_subdir

    if not rendered_dir.is_dir():
        logger.warning("Rendered directory not found, no cases discovered: %s", rendered_dir)
        return []

    cases: list[BenchCase] = []
    for entry in rendered_dir.iterdir():
        if not entry.is_file():
            continue

        classified = _classify_input(entry.name)
        if classified is None:
            logger.warning("Skipping rendered file with unknown format: %s", entry.name)
            continue
        slug, fmt, is_scanned = classified

        try:
            funder, kind, index = parse_slug(slug)
        except ValueError as exc:
            logger.warning("Skipping rendered file with bad slug %s: %s", entry.name, exc)
            continue

        golden_path = golden_dir / f"{slug}.md"
        if not golden_path.is_file():
            logger.warning(
                "Skipping %s: no golden reference at %s", entry.name, golden_path
            )
            continue

        cases.append(
            BenchCase(
                slug=slug,
                funder=funder,
                doc_kind=kind,
                index=index,
                golden_path=golden_path,
                input_path=entry,
                fmt=fmt,
                is_scanned=is_scanned,
            )
        )

    cases.sort(key=lambda c: (c.slug, c.fmt))
    return cases
