"""Pandoc converter (universal, offline baseline, lowest quality).

Shells out to the ``pandoc`` binary (https://pandoc.org/) to convert documents
to GitHub-flavored Markdown. Pandoc runs entirely offline with no network calls,
API keys, or models, which makes it a reliable baseline for the converter
benchmark.

Pandoc reads a wide range of markup/word-processor formats but does NOT read
binary PDF or spreadsheet (XLSX) formats; those are excluded from
``supported_extensions`` and skipped by the benchmark runner.

Requires the ``pandoc`` executable on ``PATH`` (e.g. ``apt install pandoc``).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from folio.adapters.converters.base import Converter

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 120


class PandocConverter(Converter):
    """Convert documents to Markdown by shelling out to the ``pandoc`` binary.

    Requires:
        - the ``pandoc`` executable available on ``PATH``.

    Output format is GitHub-flavored Markdown (``gfm``) for readable tables.
    Input format is inferred by pandoc from the file extension.
    """

    @property
    def name(self) -> str:
        return "pandoc"

    @property
    def supported_extensions(self) -> set[str]:
        return {
            '.docx',
            '.html',
            '.htm',
            '.odt',
            '.epub',
            '.rtf',
            '.tex',
            '.md',
            '.markdown',
        }

    def convert(self, source: Path) -> str | None:
        binary = shutil.which("pandoc")
        if binary is None:
            logger.error("pandoc binary not found on PATH; cannot convert %s", source)
            return None
        try:
            result = subprocess.run(
                [binary, str(source), "-t", "gfm"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            logger.error("pandoc timed out after %ss converting %s", _TIMEOUT_SECONDS, source)
            return None
        except (FileNotFoundError, OSError) as exc:
            logger.error("pandoc invocation failed for %s: %s", source, str(exc)[:200])
            return None
        if result.returncode != 0:
            logger.error(
                "pandoc exited %d for %s: %s",
                result.returncode,
                source,
                result.stderr.strip()[:200],
            )
            return None
        if not result.stdout:
            logger.error("pandoc returned empty output for %s", source)
            return None
        return result.stdout
