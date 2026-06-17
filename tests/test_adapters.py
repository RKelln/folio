from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from folio.adapters.converters import DatalabConverter, DoclingConverter, get_converter
from folio.adapters.llm import OpenAICompatibleProvider, get_llm_provider
from folio.adapters.sources import DocumentSource, get_source
from folio.adapters.sources.local import LocalSource
from folio.adapters.wiki import (
    NullWikiBackend,
    SageWikiBackend,
    get_wiki_backend,
)
from folio.config.schema import ConverterConfig, LLMConfig, ProjectConfig, WikiConfig


def _make_config(**kwargs):
    return ProjectConfig(**kwargs)


def _make_converter_config(converter_type="docling", pipeline_id=""):
    return ProjectConfig(converter=ConverterConfig(type=converter_type, datalab_pipeline_id=pipeline_id))


def _make_wiki_config(wiki_type="sage-wiki"):
    return ProjectConfig(wiki=WikiConfig(type=wiki_type))


def _make_llm_config(base_url="https://api.example.com", api_key_env="MY_KEY"):
    return ProjectConfig(llm=LLMConfig(base_url=base_url, api_key_env=api_key_env))


class TestConverterFactory:
    def test_default_with_none_config(self):
        converter = get_converter(None)
        assert isinstance(converter, DoclingConverter)
        assert converter.name == "docling"

    def test_docling(self):
        converter = get_converter(_make_converter_config("docling"))
        assert isinstance(converter, DoclingConverter)
        assert converter.name == "docling"

    def test_datalab(self):
        converter = get_converter(_make_converter_config("datalab"))
        assert isinstance(converter, DatalabConverter)
        assert converter.name == "datalab"

    def test_marker_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="Marker converter not yet implemented"):
            get_converter(_make_converter_config("marker"))

    def test_pandoc_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="Pandoc converter not yet implemented"):
            get_converter(_make_converter_config("pandoc"))

    @pytest.mark.parametrize("bogus_type", ["fake", "nonexistent", "unknown_converter"])
    def test_invalid_converter_type_raises_valueerror(self, bogus_type):
        with pytest.raises(ValueError, match="Unknown converter type"):
            get_converter(_make_converter_config(bogus_type))


class TestWikiBackendFactory:
    def test_default_with_none_config(self):
        backend = get_wiki_backend(None)
        assert isinstance(backend, NullWikiBackend)

    @patch("shutil.which", return_value="/usr/bin/sage-wiki")
    def test_sage_wiki(self, _mock_which):
        backend = get_wiki_backend(_make_wiki_config("sage-wiki"))
        assert isinstance(backend, SageWikiBackend)

    def test_null(self):
        backend = get_wiki_backend(_make_wiki_config("null"))
        assert isinstance(backend, NullWikiBackend)

    @pytest.mark.parametrize("bogus_type", ["mediawiki", "confluence", "notion"])
    def test_unknown_wiki_type_returns_null_backend(self, bogus_type):
        backend = get_wiki_backend(_make_wiki_config(bogus_type))
        assert isinstance(backend, NullWikiBackend)


class TestLLMProviderFactory:
    def test_default_with_none_config(self):
        provider = get_llm_provider(None)
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_default_without_llm_attr(self):
        provider = get_llm_provider(_make_config())
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_with_base_url_and_api_key_env(self):
        config = _make_llm_config(
            base_url="https://custom-api.example.com/v1",
            api_key_env="CUSTOM_API_KEY",
        )
        provider = get_llm_provider(config)
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider._base_url == "https://custom-api.example.com/v1"
        assert provider._api_key == ""


class TestSourceFactory:
    def test_local_path_returns_local_source(self):
        source = get_source("/tmp/documents")
        assert isinstance(source, LocalSource)
        assert isinstance(source, DocumentSource)

    def test_relative_path_returns_local_source(self):
        source = get_source("./archive")
        assert isinstance(source, LocalSource)

    def test_gdrive_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="Google Drive source not yet implemented"):
            get_source("gdrive://folder-id/abc123")

    def test_dropbox_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="Dropbox source not yet implemented"):
            get_source("dropbox://path/to/folder")


class TestNullWikiBackend:
    @pytest.fixture
    def null_backend(self):
        return NullWikiBackend()

    def test_init_does_nothing(self, null_backend, tmp_path):
        null_backend.init(tmp_path, {})
        assert tmp_path.exists()

    def test_add_documents_does_nothing(self, null_backend, tmp_path):
        null_backend.add_documents([tmp_path / "doc1.md", tmp_path / "doc2.md"])

    def test_compile_does_nothing(self, null_backend):
        null_backend.compile()

    def test_search_returns_placeholder(self, null_backend):
        result = null_backend.search("grant funding")
        assert isinstance(result, str)
        assert "Wiki not configured" in result

    def test_query_returns_placeholder(self, null_backend):
        result = null_backend.query("What is our total OAC funding?")
        assert isinstance(result, str)
        assert "Wiki not configured" in result

    def test_search_returns_nonempty_string(self, null_backend):
        result = null_backend.search("anything")
        assert len(result) > 0

    def test_query_returns_nonempty_string(self, null_backend):
        result = null_backend.query("anything")
        assert len(result) > 0


class TestLocalSource:
    def test_construct_with_string_path(self):
        source = LocalSource("/tmp/docs")
        assert source._source_path == Path("/tmp/docs").resolve()

    def test_construct_with_path_object(self):
        source = LocalSource(Path("/tmp/docs"))
        assert source._source_path == Path("/tmp/docs").resolve()

    def test_list_files_empty_for_nonexistent_dir(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist"
        source = LocalSource(nonexistent)
        assert source.list_files() == []

    def test_list_files_empty_for_empty_dir(self, tmp_path):
        empty = tmp_path / "empty_dir"
        empty.mkdir()
        source = LocalSource(empty)
        assert source.list_files() == []

    def test_list_files_finds_markdown(self, tmp_path):
        d = tmp_path / "docs"
        d.mkdir()
        (d / "readme.md").write_text("# Hello")
        source = LocalSource(d)
        refs = source.list_files()
        assert len(refs) == 1
        assert refs[0].name == "readme.md"

    def test_list_files_finds_pdf(self, tmp_path):
        d = tmp_path / "docs"
        d.mkdir()
        (d / "report.pdf").write_text("fake pdf")
        source = LocalSource(d)
        refs = source.list_files()
        assert len(refs) == 1
        assert refs[0].name == "report.pdf"

    def test_list_files_ignores_unsupported_extensions(self, tmp_path):
        d = tmp_path / "docs"
        d.mkdir()
        (d / "notes.txt").write_text("text")
        (d / "image.png").write_text("png")
        source = LocalSource(d)
        refs = source.list_files()
        assert len(refs) == 0

    def test_list_files_includes_subdirectories(self, tmp_path):
        d = tmp_path / "docs"
        d.mkdir()
        sub = d / "sub"
        sub.mkdir()
        (d / "root.md").write_text("root")
        (sub / "child.docx").write_text("child")
        source = LocalSource(d)
        refs = sorted(source.list_files(), key=lambda r: r.name)
        assert len(refs) == 2
        assert refs[0].name == "child.docx"
        assert refs[1].name == "root.md"

    def test_download_copies_file(self, tmp_path):
        d = tmp_path / "docs"
        d.mkdir()
        src_file = d / "report.docx"
        src_file.write_text("contract content")
        source = LocalSource(d)
        refs = source.list_files()
        assert len(refs) == 1

        dest = tmp_path / "out" / "copied.docx"
        result = source.download(refs[0], dest)
        assert result == dest
        assert dest.read_text() == "contract content"


class TestDatalabConverterProperties:
    def test_name_property(self):
        converter = DatalabConverter("pipe-123")
        assert converter.name == "datalab"

    def test_supported_extensions(self):
        converter = DatalabConverter("")
        exts = converter.supported_extensions
        assert ".pdf" in exts
        assert ".docx" in exts
        assert ".xlsx" in exts
        assert ".doc" in exts
        assert ".xls" in exts
