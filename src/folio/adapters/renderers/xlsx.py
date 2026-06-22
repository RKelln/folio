"""XLSX renderer — golden Markdown pipe tables → spreadsheet via openpyxl.

Each pipe table in the Markdown becomes a worksheet. When a heading (e.g.
``### Revenue``) precedes a table, that heading names the sheet; otherwise the
sheet is named ``Sheet1`` (then ``Sheet2`` ...). Cells keep ``$#,###`` strings
as text and have ``**bold**`` markers stripped. Workbook authoring properties
(creator, lastModifiedBy, title, subject, keywords) are cleared before save.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from folio.adapters.renderers.base import MdTable, Renderer, parse_markdown

logger = logging.getLogger(__name__)

# Characters Excel forbids in a worksheet title.
_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
_MAX_SHEET_NAME = 31


class XlsxRenderer(Renderer):
    """Render Markdown pipe tables to a ``.xlsx`` file using openpyxl."""

    name = "openpyxl"
    output_format = "xlsx"

    def available(self) -> bool:
        try:
            import openpyxl  # type: ignore[import-not-found]  # noqa: F401

            return True
        except ImportError as exc:
            logger.warning("XlsxRenderer unavailable: openpyxl not importable (%s)", exc)
            return False

    def render(self, markdown: str, meta: dict, out_path: Path) -> Path:
        try:
            import openpyxl  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "openpyxl not installed; cannot render .xlsx. "
                "Install with: pip install openpyxl"
            ) from exc

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        tables = [b for b in parse_markdown(markdown) if isinstance(b, MdTable)]

        workbook = openpyxl.Workbook()
        # openpyxl always starts with one empty sheet; reuse it for the first
        # table and remove it only if there are no tables to write.
        default_sheet = workbook.active
        used_names: set[str] = set()

        for idx, table in enumerate(tables):
            title = self._sheet_title(table.section, idx, used_names)
            sheet = default_sheet if idx == 0 else workbook.create_sheet()
            sheet.title = title
            used_names.add(title)
            for row in table.rows:
                sheet.append(list(row))

        if not tables:
            logger.warning(
                "XlsxRenderer: no pipe tables found in markdown for %s; "
                "writing an empty workbook",
                out_path,
            )

        self._clear_properties(workbook)
        workbook.save(str(out_path))
        return out_path

    @staticmethod
    def _sheet_title(section: str | None, idx: int, used: set[str]) -> str:
        """Derive a valid, unique worksheet title from a section heading."""
        base = section.strip() if section else ""
        base = _INVALID_SHEET_CHARS.sub(" ", base).strip()
        if not base:
            base = f"Sheet{idx + 1}"
        base = base[:_MAX_SHEET_NAME]
        title = base
        suffix = 2
        while title in used:
            tail = f"_{suffix}"
            title = base[: _MAX_SHEET_NAME - len(tail)] + tail
            suffix += 1
        return title

    @staticmethod
    def _clear_properties(workbook) -> None:
        """Blank out workbook authoring properties before saving."""
        props = workbook.properties
        # NB: openpyxl re-applies its default creator ("openpyxl") when the
        # field is None, so we clear with empty strings (which persist as
        # absent on reload) rather than None.
        for attr in (
            "creator",
            "lastModifiedBy",
            "last_modified_by",
            "title",
            "subject",
            "keywords",
            "description",
            "category",
            "identifier",
        ):
            try:
                setattr(props, attr, "")
            except (ValueError, TypeError, AttributeError) as exc:
                logger.warning("Could not clear xlsx property %s: %s", attr, exc)
