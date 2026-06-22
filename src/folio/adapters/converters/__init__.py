"""Document converters (PDF, DOCX, XLSX → Markdown).

Pluggable interface with implementations for:
- LiteParse (default — fast, local, non-LLM, Rust-based)
- Datalab (proprietary, best quality for grant forms)
- Docling (IBM, open source)
- Marker (open source, local)
- Pandoc (universal, lowest quality)
"""

from __future__ import annotations

from folio.adapters.converters.base import Converter
from folio.adapters.converters.datalab import DatalabConverter
from folio.adapters.converters.docling import DoclingConverter
from folio.adapters.converters.liteparse import LiteParseConverter


def get_converter(config) -> Converter:
    """Return the configured converter instance.

    Accepts either a converter-type string (e.g. 'liteparse', 'datalab')
    or a config object with a ``converter.type`` attribute.
    """
    if config is None:
        return LiteParseConverter()
    if isinstance(config, str):
        converter_type = config
        pipeline_id = ''
    else:
        converter_type = getattr(getattr(config, 'converter', None), 'type', 'liteparse')
        pipeline_id = getattr(getattr(config, 'converter', None), 'datalab_pipeline_id', '')
    if converter_type == 'liteparse':
        return LiteParseConverter()
    if converter_type == 'docling':
        return DoclingConverter()
    if converter_type == 'datalab':
        return DatalabConverter(pipeline_id)
    if converter_type == 'marker':
        raise NotImplementedError("Marker converter not yet implemented")
    if converter_type == 'pandoc':
        raise NotImplementedError("Pandoc converter not yet implemented")
    raise ValueError(f"Unknown converter type: {converter_type}")
