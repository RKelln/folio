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
    """Return the configured converter instance.

    Accepts either a converter-type string (e.g. 'docling', 'datalab')
    or a config object with a ``converter.type`` attribute.
    """
    if config is None:
        return DoclingConverter()
    if isinstance(config, str):
        converter_type = config
        pipeline_id = ''
    else:
        converter_type = getattr(getattr(config, 'converter', None), 'type', 'docling')
        pipeline_id = getattr(getattr(config, 'converter', None), 'datalab_pipeline_id', '')
    if converter_type == 'docling':
        return DoclingConverter()
    if converter_type == 'datalab':
        return DatalabConverter(pipeline_id)
    if converter_type == 'marker':
        raise NotImplementedError("Marker converter not yet implemented")
    if converter_type == 'pandoc':
        raise NotImplementedError("Pandoc converter not yet implemented")
    raise ValueError(f"Unknown converter type: {converter_type}")
