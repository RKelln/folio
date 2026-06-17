"""Datalab converter (default, best quality).

Uses the Datalab pipeline API to convert PDF/DOCX/XLSX to markdown.
Requires DATALAB_API_KEY environment variable and datalab-python-sdk.
"""

from __future__ import annotations

import logging
from pathlib import Path

from folio.adapters.converters.base import Converter

logger = logging.getLogger(__name__)


class DatalabConverter(Converter):
    """Convert documents using the Datalab pipeline API.

    Requires:
        - DATALAB_API_KEY environment variable
        - datalab-python-sdk package (`pip install folio[datalab]`)
    """

    def __init__(self, pipeline_id: str):
        self._pipeline_id = pipeline_id

    @property
    def name(self) -> str:
        return "datalab"

    @property
    def supported_extensions(self) -> set[str]:
        return {'.pdf', '.docx', '.xlsx', '.doc', '.xls'}

    def convert(self, source: Path) -> str | None:
        try:
            import os

            key = os.environ.get('DATALAB_API_KEY')
            if not key:
                logger.error("DATALAB_API_KEY environment variable not set")
                return None

            from datalab_sdk import DatalabClient

            client = DatalabClient(api_key=key)
            execution = client.run_pipeline(
                self._pipeline_id,
                file_path=str(source),
                max_polls=300,
                poll_interval=2,
            )
            result = execution.result()
            if result and result.get('markdown'):
                return result['markdown']
            return None
        except Exception as exc:
            logger.error("Datalab conversion failed for %s: %s", source, str(exc)[:200])
            return None
