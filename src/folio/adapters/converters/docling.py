"""Docling converter — PDF/DOCX/XLSX → Markdown via Docling (Apache 2.0)."""

from __future__ import annotations

import logging
from pathlib import Path

from folio.adapters.converters.base import Converter

logger = logging.getLogger(__name__)


class DoclingConverter(Converter):
    """Convert documents to Markdown using Docling."""

    def __init__(self):
        self._model = None

    @property
    def name(self) -> str:
        return "docling"

    @property
    def supported_extensions(self) -> set[str]:
        return {'.pdf', '.docx', '.pptx', '.xlsx'}

    def _ensure_model(self):
        if self._model is None:
            from docling.document_converter import DocumentConverter
            self._model = DocumentConverter()
        return self._model

    def convert(self, source: Path) -> str | None:
        try:
            converter = self._ensure_model()
            result = converter.convert(str(source))
            return result.document.export_to_markdown()
        except Exception as exc:
            logger.error("Docling conversion failed for %s: %s", source, str(exc)[:200])
            return None
