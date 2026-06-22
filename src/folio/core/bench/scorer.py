"""Deterministic, offline scoring metrics for the converter benchmark.

Pure functions that compare a converter's *candidate* Markdown against a
*golden* Markdown reference and return per-category fidelity scores. Every
metric is deterministic, total (never raises on empty/malformed input), uses
the Python standard library only (``difflib`` + ``re`` — no network, no extra
dependencies), and is clamped to the closed interval ``[0, 1]`` where ``1.0``
means perfect recovery and ``0.0`` means none.

Categories (all in ``[0, 1]``):

* **text** — body-text fidelity via :func:`difflib.SequenceMatcher` ratio over
  whitespace-tokenized, normalized text.
* **tables** — GitHub pipe-table recovery: cell-text F1 blended with row-count
  recovery.
* **structure** — heading reading-order similarity blended with list-item
  recovery.
* **links_images** — recall of Markdown links/images present in the golden.

Converters never reproduce YAML frontmatter, so :func:`score_document` strips a
leading frontmatter block from *both* inputs before scoring.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")
_LIST_RE = re.compile(r"^\s*([-*+]|\d+\.)\s+")
_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\([^)]*\)")


def _clamp(value: float) -> float:
    """Clamp ``value`` to the closed interval ``[0, 1]``."""
    return max(0.0, min(1.0, value))


@dataclass
class CategoryScores:
    """Per-category fidelity scores, each a float in ``[0, 1]``."""

    text: float
    tables: float
    structure: float
    links_images: float

    def to_dict(self) -> dict:
        """Return a plain, JSON-serializable mapping of the four categories."""
        return {
            "text": self.text,
            "tables": self.tables,
            "structure": self.structure,
            "links_images": self.links_images,
        }


def strip_frontmatter(md: str) -> str:
    """Remove a leading YAML frontmatter block delimited by ``---`` lines.

    Only a block at the very start of the document is removed (from the opening
    ``---`` to the next ``---``). Returns the body unchanged if no opening
    delimiter is present or the block is never closed.
    """
    if not md:
        return md
    lines = md.splitlines()
    if not lines or lines[0].strip() != "---":
        return md
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            body = "\n".join(lines[index + 1 :])
            return body.lstrip("\n")
    return md


def normalize_text(md: str) -> str:
    """Lowercase ``md``, collapse all whitespace runs to single spaces, strip."""
    if not md:
        return ""
    return re.sub(r"\s+", " ", md).strip().lower()


def score_text(golden: str, candidate: str) -> float:
    """Body-text fidelity in ``[0, 1]``.

    Computes a :func:`difflib.SequenceMatcher` ratio over the whitespace
    tokens of the normalized text. Identical bodies score ``1.0``; an empty
    candidate against non-empty golden scores ``0.0``; two empty bodies score
    ``1.0``.
    """
    golden_tokens = normalize_text(golden).split()
    candidate_tokens = normalize_text(candidate).split()
    if not golden_tokens and not candidate_tokens:
        return 1.0
    if not candidate_tokens:
        return 0.0
    return _clamp(SequenceMatcher(None, golden_tokens, candidate_tokens).ratio())


def _parse_table(md: str) -> tuple[list[str], int]:
    """Return ``(cells, row_count)`` for GitHub pipe tables in ``md``.

    Cells are normalized; the ``---`` separator row and empty edge cells are
    dropped. ``row_count`` counts non-separator pipe rows.
    """
    cells: list[str] = []
    row_count = 0
    for line in md.splitlines():
        if "|" not in line:
            continue
        parts = [cell.strip() for cell in line.split("|")]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        if not parts:
            continue
        if all(_SEPARATOR_CELL_RE.match(cell) for cell in parts):
            continue
        row_count += 1
        cells.extend(normalize_text(cell) for cell in parts if cell)
    return cells, row_count


def _multiset_overlap(golden: list[str], candidate: list[str]) -> int:
    """Return the size of the multiset intersection of two cell/token lists."""
    return sum((Counter(golden) & Counter(candidate)).values())


def score_tables(golden: str, candidate: str) -> float:
    """GitHub pipe-table recovery in ``[0, 1]``.

    Blends cell-recovery F1 (precision/recall over the normalized cell-text
    multiset) with row-count recovery. When the golden has no tables, returns
    ``1.0`` if the candidate also has none, otherwise a penalty trending toward
    ``0`` as spurious table rows accumulate.
    """
    golden_cells, golden_rows = _parse_table(golden)
    candidate_cells, candidate_rows = _parse_table(candidate)

    if golden_rows == 0:
        if candidate_rows == 0:
            return 1.0
        return _clamp(1.0 / (1.0 + candidate_rows))

    matched = _multiset_overlap(golden_cells, candidate_cells)
    precision = matched / len(candidate_cells) if candidate_cells else 0.0
    recall = matched / len(golden_cells) if golden_cells else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    row_recovery = min(candidate_rows, golden_rows) / max(candidate_rows, golden_rows)

    return _clamp(0.7 * f1 + 0.3 * row_recovery)


def _parse_headings(md: str) -> list[tuple[int, str]]:
    """Return ordered ``(level, normalized text)`` tuples for ATX headings."""
    headings: list[tuple[int, str]] = []
    for line in md.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            headings.append((len(match.group(1)), normalize_text(match.group(2))))
    return headings


def _count_list_items(md: str) -> int:
    """Return the number of ordered/unordered Markdown list items in ``md``."""
    return sum(1 for line in md.splitlines() if _LIST_RE.match(line))


def score_structure(golden: str, candidate: str) -> float:
    """Document-structure fidelity in ``[0, 1]``.

    Blends heading reading-order similarity (a :func:`difflib.SequenceMatcher`
    ratio over ordered ``(level, text)`` tuples, so reordered headings score
    below a perfect match) with list-item recovery. When the golden has neither
    headings nor lists, returns ``1.0`` iff the candidate also has none.
    """
    golden_headings = _parse_headings(golden)
    candidate_headings = _parse_headings(candidate)
    golden_lists = _count_list_items(golden)
    candidate_lists = _count_list_items(candidate)

    has_headings = bool(golden_headings)
    has_lists = golden_lists > 0

    if not has_headings and not has_lists:
        spurious = len(candidate_headings) + candidate_lists
        if spurious == 0:
            return 1.0
        return _clamp(1.0 / (1.0 + spurious))

    components: list[tuple[float, float]] = []
    if has_headings:
        heading_sim = SequenceMatcher(None, golden_headings, candidate_headings).ratio()
        components.append((0.7, heading_sim))
    if has_lists:
        list_recovery = min(candidate_lists, golden_lists) / max(candidate_lists, golden_lists)
        components.append((0.3, list_recovery))

    total_weight = sum(weight for weight, _ in components)
    blended = sum(weight * value for weight, value in components) / total_weight
    return _clamp(blended)


def score_links_images(golden: str, candidate: str) -> float:
    """Recall of Markdown links and images in ``[0, 1]``.

    Counts inline links ``[..](..)`` and images ``![..](..)`` in the golden and
    returns the fraction also present in the candidate (multiset recall, capped
    at ``1.0``). Returns ``1.0`` when the golden contains none.
    """
    golden_refs = _IMAGE_RE.findall(golden) + _LINK_RE.findall(golden)
    candidate_refs = _IMAGE_RE.findall(candidate) + _LINK_RE.findall(candidate)

    golden_norm = [normalize_text(ref) for ref in golden_refs]
    candidate_norm = [normalize_text(ref) for ref in candidate_refs]

    if not golden_norm:
        return 1.0
    matched = _multiset_overlap(golden_norm, candidate_norm)
    return _clamp(matched / len(golden_norm))


def score_document(golden: str, candidate: str) -> CategoryScores:
    """Score a candidate against a golden across all four categories.

    Strips a leading YAML frontmatter block from *both* inputs (converters
    never reproduce frontmatter) and returns a :class:`CategoryScores`, each
    field clamped to ``[0, 1]``.
    """
    golden_body = strip_frontmatter(golden)
    candidate_body = strip_frontmatter(candidate)
    return CategoryScores(
        text=score_text(golden_body, candidate_body),
        tables=score_tables(golden_body, candidate_body),
        structure=score_structure(golden_body, candidate_body),
        links_images=score_links_images(golden_body, candidate_body),
    )
