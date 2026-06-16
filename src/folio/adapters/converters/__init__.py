"""Document converters (PDF, DOCX, XLSX → Markdown).

Pluggable interface with implementations for:
- Datalab (proprietary, best quality for grant forms)
- Marker (open source, local)
- Docling (IBM, open source)
- Pandoc (universal, lowest quality)
"""

from __future__ import annotations

from folio.adapters.converters.base import Converter
from folio.adapters.converters.datalab import DatalabConverter
from folio.adapters.converters.docling import DoclingConverter


def get_converter(config) -> Converter:
    """Return the configured converter instance."""
    if config is None:
        return DoclingConverter()
    converter_type = 'docling'
    if hasattr(config.converter, 'type'):
        converter_type = getattr(config.converter, 'type', 'docling')
    if converter_type == 'docling':
        return DoclingConverter()
    if converter_type == 'datalab':
        pipeline_id = getattr(config.converter, 'datalab_pipeline_id', '')
        return DatalabConverter(pipeline_id)
    if converter_type == 'marker':
        raise NotImplementedError("Marker converter not yet implemented")
    if converter_type == 'pandoc':
        raise NotImplementedError("Pandoc converter not yet implemented")
    raise ValueError(f"Unknown converter type: {converter_type}")
