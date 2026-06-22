"""Format renderers (golden Markdown → DOCX/XLSX/PDF/scanned-PDF).

Renderers are the inverse of converters: they turn the synthetic corpus's
deterministic golden Markdown into binary artifacts whose formatting mirrors a
real grant archive. Each renderer reports ``available()`` so callers can skip a
format gracefully (with a logged warning) when an optional tool/dependency is
absent — output is never produced silently or partially.

Public API:
    get_renderer(output_format)  -> Renderer   (raises ValueError if unknown)
    available_formats()          -> list[str]  (formats whose renderer is ready)
    Renderer (ABC), DocxRenderer, XlsxRenderer, PdfRenderer, ScannedPdfRenderer
"""

from __future__ import annotations

from folio.adapters.renderers.base import Renderer
from folio.adapters.renderers.docx import DocxRenderer
from folio.adapters.renderers.pdf import PdfRenderer, ScannedPdfRenderer
from folio.adapters.renderers.xlsx import XlsxRenderer

__all__ = [
    "Renderer",
    "DocxRenderer",
    "XlsxRenderer",
    "PdfRenderer",
    "ScannedPdfRenderer",
    "get_renderer",
    "available_formats",
]

# Canonical mapping of output format -> renderer class.
_RENDERERS: dict[str, type[Renderer]] = {
    "docx": DocxRenderer,
    "xlsx": XlsxRenderer,
    "pdf": PdfRenderer,
    "pdf_scanned": ScannedPdfRenderer,
}


def get_renderer(output_format: str) -> Renderer:
    """Return a renderer instance for ``output_format``.

    Args:
        output_format: One of ``"docx"``, ``"xlsx"``, ``"pdf"``,
            ``"pdf_scanned"``.

    Returns:
        A fresh Renderer instance.

    Raises:
        ValueError: If ``output_format`` is not a known format.
    """
    try:
        return _RENDERERS[output_format]()
    except KeyError as exc:
        known = ", ".join(sorted(_RENDERERS))
        raise ValueError(
            f"Unknown output format: {output_format!r}. Known formats: {known}."
        ) from exc


def available_formats() -> list[str]:
    """Return the formats whose renderer's ``available()`` is True.

    Each renderer is instantiated and queried; unavailable formats are omitted
    (the renderer logs a warning explaining what is missing).
    """
    return [fmt for fmt, cls in _RENDERERS.items() if cls().available()]
