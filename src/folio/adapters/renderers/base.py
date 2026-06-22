"""Abstract renderer interface and shared Markdown parsing.

PURPOSE
    Renderers are the inverse of converters: they take the deterministic golden
    Markdown of a synthetic corpus document plus a metadata dict and emit a
    binary artifact (DOCX/XLSX/PDF) whose *formatting* mirrors a real grant
    archive. The Round C corpus CLI depends on this contract.

DESIGN
    Renderers accept primitives (``markdown: str``, ``meta: dict``,
    ``out_path: Path``) rather than a generator type, so the renderer layer
    stays fully decoupled from corpus generation. Each renderer reports whether
    its required tools/deps are present via ``available()`` so callers can skip
    formats gracefully (never silently) when a tool is missing.

SHARED PARSING
    ``parse_markdown`` is the single, canonical line-by-line parser for the
    Markdown subset the corpus emits (ATX headings, paragraphs, and GitHub pipe
    tables). It lives here so DOCX and XLSX renderers share one implementation
    rather than each re-deriving table parsing (AGENTS.md strict-DRY rule).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

# A pipe-table separator cell is only dashes/colons (optionally padded).
_SEP_CELL = re.compile(r"^\s*:?-+:?\s*$")
# ATX heading: 1-6 leading '#', a space, then the heading text.
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass
class MdHeading:
    """A Markdown ATX heading (``#``..``######``)."""

    level: int
    text: str


@dataclass
class MdParagraph:
    """A run of non-blank, non-heading, non-table text joined by spaces."""

    text: str


@dataclass
class MdTable:
    """A GitHub pipe table.

    Attributes:
        rows: All rows including the header row at index 0; the ``| --- |``
            separator row is consumed and never included.
        section: The text of the nearest preceding heading, used by the XLSX
            renderer for worksheet naming. None when no heading preceded it.
    """

    rows: list[list[str]] = field(default_factory=list)
    section: str | None = None


MdBlock = MdHeading | MdParagraph | MdTable


def _strip_cell(cell: str) -> str:
    """Trim whitespace and remove ``**bold**`` markers from a table cell."""
    return cell.strip().replace("**", "")


def _split_row(line: str) -> list[str]:
    """Split a pipe-table row into cells, dropping the outer empty fields.

    ``| a | b |`` -> ``["a", "b"]``. Leading/trailing pipes produce empty edge
    fields which are removed; interior empties are preserved.
    """
    parts = line.split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [_strip_cell(p) for p in parts]


def _is_separator_row(line: str) -> bool:
    """True when every cell of a pipe row is a ``---``/``:--:`` separator."""
    if "|" not in line:
        return False
    cells = [c for c in line.split("|") if c.strip() != ""]
    return bool(cells) and all(_SEP_CELL.match(c) for c in cells)


def parse_markdown(markdown: str) -> list[MdBlock]:
    """Parse the corpus Markdown subset into an ordered list of blocks.

    Recognises ATX headings, GitHub pipe tables (a header row immediately
    followed by a ``| --- |`` separator row), and paragraphs. Anything else is
    accumulated into the current paragraph. The parser is intentionally small
    and dependency-free; it is not a general Markdown implementation.

    Args:
        markdown: The golden Markdown source.

    Returns:
        An ordered list of MdHeading / MdParagraph / MdTable blocks.
    """
    lines = markdown.splitlines()
    blocks: list[MdBlock] = []
    para: list[str] = []
    current_section: str | None = None
    i = 0
    n = len(lines)

    def flush_para() -> None:
        if para:
            blocks.append(MdParagraph(text=" ".join(para).strip()))
            para.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped == "":
            flush_para()
            i += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_para()
            level = len(heading.group(1))
            text = heading.group(2).replace("**", "").strip()
            current_section = text
            blocks.append(MdHeading(level=level, text=text))
            i += 1
            continue

        # Pipe table: a row containing '|' followed by a separator row.
        if "|" in stripped and i + 1 < n and _is_separator_row(lines[i + 1]):
            flush_para()
            header = _split_row(line)
            rows: list[list[str]] = [header]
            i += 2  # skip header + separator
            while i < n and "|" in lines[i] and lines[i].strip() != "":
                if _is_separator_row(lines[i]):
                    i += 1
                    continue
                rows.append(_split_row(lines[i]))
                i += 1
            blocks.append(MdTable(rows=rows, section=current_section))
            continue

        para.append(stripped)
        i += 1

    flush_para()
    return blocks


class Renderer(ABC):
    """Render golden Markdown to a binary corpus artifact.

    Implementations declare two class attributes — ``name`` (human-readable)
    and ``output_format`` (one of ``"docx"``, ``"xlsx"``, ``"pdf"``,
    ``"pdf_scanned"``) — and implement ``available`` and ``render``.
    """

    name: str
    output_format: str

    @abstractmethod
    def available(self) -> bool:
        """Return True when every required tool/dependency is present.

        Must check importability of Python deps and PATH presence of external
        tools without raising. Callers use this to skip a format gracefully.
        """
        ...

    @abstractmethod
    def render(self, markdown: str, meta: dict, out_path: Path) -> Path:
        """Render ``markdown`` to ``out_path`` and return the written path.

        Args:
            markdown: The golden Markdown source.
            meta: Document metadata; renderers MUST NOT write authoring
                metadata (author/etc.) into the artifact.
            out_path: Destination path (its parent is created if needed).

        Returns:
            The path written.

        Raises:
            RuntimeError: On failure. Implementations must never leave a partial
                or empty file behind silently.
        """
        ...
