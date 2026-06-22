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
from folio.adapters.converters.cascade import CascadeConverter
from folio.adapters.converters.datalab import DatalabConverter
from folio.adapters.converters.docling import DoclingConverter
from folio.adapters.converters.liteparse import LiteParseConverter
from folio.adapters.converters.pandoc import PandocConverter


def _build_single(name: str, config) -> Converter:
    """Return a single concrete converter for *name* (no cascade dispatch).

    *config* supplies converter-specific settings (e.g. the datalab
    pipeline id). It may be a config object with a ``converter`` attribute
    or a bare string, in which case settings fall back to their defaults.
    """
    if name == 'liteparse':
        return LiteParseConverter()
    if name == 'docling':
        return DoclingConverter()
    if name == 'datalab':
        pipeline_id = getattr(getattr(config, 'converter', None), 'datalab_pipeline_id', '')
        return DatalabConverter(pipeline_id)
    if name == 'marker':
        raise NotImplementedError("Marker converter not yet implemented")
    if name == 'pandoc':
        return PandocConverter()
    raise ValueError(f"Unknown converter type: {name}")


def get_converter(config) -> Converter:
    """Return the configured converter instance.

    Accepts either a converter-type string (e.g. 'liteparse', 'datalab')
    or a config object with a ``converter.type`` attribute. When the type
    is 'cascade', each name in ``converter.cascade`` is built via
    :func:`_build_single` and wrapped in a :class:`CascadeConverter`.
    """
    if config is None:
        return LiteParseConverter()
    if isinstance(config, str):
        return _build_single(config, config)

    converter_cfg = getattr(config, 'converter', None)
    converter_type = getattr(converter_cfg, 'type', 'liteparse')
    if converter_type == 'cascade':
        cascade = getattr(converter_cfg, 'cascade', [])
        thresholds = getattr(converter_cfg, 'cascade_thresholds', {})
        tiers = [_build_single(name, config) for name in cascade]
        return CascadeConverter(tiers, thresholds=thresholds or None)
    return _build_single(converter_type, config)
