"""LiteParse converter (default — fast, local, non-LLM).

Uses LiteParse (https://developers.llamaindex.ai/liteparse/), an open-source
Rust-based parser with spatial layout, OCR, and Markdown rendering. It runs
entirely on the local machine with no cloud calls, LLMs, or API keys, which
makes it a good default for bulk archive conversion.

Requires the ``liteparse`` package (``pip install folio[liteparse]``).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from folio.adapters.converters.base import Converter

logger = logging.getLogger(__name__)


class LiteParseConverter(Converter):
    """Convert documents to Markdown using LiteParse.

    Requires:
        - liteparse package (``pip install folio[liteparse]``)
        - Optional: Tesseract data on disk for OCR of scanned documents
          (set ``TESSDATA_PREFIX`` for offline/air-gapped environments).
    """

    def __init__(self):
        self._parser = None
        self._parser_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "liteparse"

    @property
    def supported_extensions(self) -> set[str]:
        return {'.pdf', '.docx', '.xlsx', '.pptx', '.png', '.jpg', '.jpeg'}

    def _ensure_parser(self):
        if self._parser is None:
            with self._parser_lock:
                if self._parser is None:
                    from liteparse import LiteParse

                    self._parser = LiteParse(
                        output_format="markdown",
                        image_mode="placeholder",
                        extract_links=True,
                    )
        return self._parser

    def convert(self, source: Path) -> str | None:
        try:
            parser = self._ensure_parser()
            result = parser.parse(str(source))
            text = getattr(result, "text", None)
            if text:
                return text
            logger.error("LiteParse returned empty result for %s", source)
            return None
        except Exception as exc:
            logger.error("LiteParse conversion failed for %s: %s", source, str(exc)[:200])
            return None
