"""Datalab converter (default, best quality).

Uses the Datalab pipeline API to convert PDF/DOCX/XLSX to markdown.
Requires DATALAB_API_KEY environment variable and datalab-python-sdk.
"""

from pathlib import Path

from folio.adapters.converters.base import Converter


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
        import os

        key = os.environ.get('DATALAB_API_KEY')
        if not key:
            raise RuntimeError('DATALAB_API_KEY not set')

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
