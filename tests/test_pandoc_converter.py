from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from folio.adapters.converters import PandocConverter, get_converter

CORPUS_DOCX = Path("benchmark/corpus/rendered/oac-staff_board-01.docx")
_PANDOC_AVAILABLE = shutil.which("pandoc") is not None


class TestPandocConverterProperties:
    def test_name(self):
        assert PandocConverter().name == "pandoc"

    def test_supported_extensions_includes_expected(self):
        exts = PandocConverter().supported_extensions
        for ext in {'.docx', '.html', '.htm', '.odt', '.epub', '.rtf', '.tex', '.md', '.markdown'}:
            assert ext in exts

    def test_pdf_and_xlsx_not_supported(self):
        exts = PandocConverter().supported_extensions
        assert ".pdf" not in exts
        assert ".xlsx" not in exts


class TestPandocConverterFactory:
    def test_get_converter_returns_pandoc(self):
        converter = get_converter("pandoc")
        assert isinstance(converter, PandocConverter)
        assert converter.name == "pandoc"

    def test_marker_still_raises(self):
        with pytest.raises(NotImplementedError, match="Marker converter not yet implemented"):
            get_converter("marker")


class TestPandocConverterFailurePaths:
    def test_missing_file_returns_none(self):
        result = PandocConverter().convert(Path("does-not-exist.docx"))
        assert result is None

    def test_returns_none_when_pandoc_unavailable(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        result = PandocConverter().convert(CORPUS_DOCX)
        assert result is None


@pytest.mark.integration
@pytest.mark.skipif(not _PANDOC_AVAILABLE, reason="pandoc binary not installed")
class TestPandocConverterIntegration:
    def test_converts_real_docx(self):
        assert CORPUS_DOCX.exists(), f"corpus file missing: {CORPUS_DOCX}"
        result = PandocConverter().convert(CORPUS_DOCX)
        assert isinstance(result, str)
        assert result.strip()
        assert "Staff" in result or "|" in result
