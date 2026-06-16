from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from folio.config.loader import _deep_merge, load_project_config
from folio.config.schema import ProjectConfig


class TestLoadMinimalValidConfig:
    def test_load_from_empty_yaml(self, tmp_path):
        config_file = tmp_path / "folio.yaml"
        config_file.write_text("{}")
        config = load_project_config(config_path=str(config_file))
        assert isinstance(config, ProjectConfig)
        assert config.project_name == "My Grant Archive"
        assert config.org.name == "My Organization"
        assert config.org.abbreviation == "ORG"
        assert Path(config.paths.raw_archive).name == "archive"
        assert config.llm.base_url == "https://api.deepseek.com"

    def test_load_defaults_only(self):
        config = load_project_config()
        assert isinstance(config, ProjectConfig)
        assert config.project_name == "My Grant Archive"
        assert config.converter.type == "docling"
        assert config.wiki.type == "sage-wiki"
        assert config.processing.max_workers == 10


class TestFullConfig:
    def test_load_with_all_sections(self, tmp_path):
        yaml_content = """\
project:
  name: "Test Project"
org:
  name: "Test Org"
  abbreviation: "TO"
  description: "A test organization"
funders:
  CCA: "Canada Council for the Arts"
  OAC: "Ontario Arts Council"
doc_types:
  - application
  - report
  - budget
converter:
  type: "marker"
  datalab:
    pipeline_id: "pipe-123"
    api_key_env: "MY_KEY"
wiki:
  type: "null"
  sage_wiki:
    binary_path: "/usr/bin/sage-wiki"
    pack: "custom-pack"
llm:
  provider: "openai_compatible"
  base_url: "https://api.example.com"
  api_key_env: "EXAMPLE_KEY"
  models:
    fast: "fast-model"
    quality: "quality-model"
  pricing:
    input_per_million: 1.5
    output_per_million: 3.0
processing:
  max_workers: 4
  requests_per_second: 2.5
  max_retries: 5
  resume: false
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        config = load_project_config(config_path=str(config_file))

        assert config.project_name == "Test Project"
        assert config.org.name == "Test Org"
        assert config.org.abbreviation == "TO"
        assert config.org.description == "A test organization"

        assert config.funders == {
            "CCA": "Canada Council for the Arts",
            "OAC": "Ontario Arts Council",
        }
        assert config.doc_types == ["application", "report", "budget"]

        assert config.converter.type == "marker"
        assert config.converter.datalab_pipeline_id == "pipe-123"
        assert config.converter.datalab_api_key_env == "MY_KEY"

        assert config.wiki.type == "null"
        assert config.wiki.sage_wiki_binary == "/usr/bin/sage-wiki"
        assert config.wiki.sage_wiki_pack == "custom-pack"

        assert config.llm.provider == "openai_compatible"
        assert config.llm.base_url == "https://api.example.com"
        assert config.llm.api_key_env == "EXAMPLE_KEY"
        assert config.llm.fast_model == "fast-model"
        assert config.llm.quality_model == "quality-model"
        assert config.llm.input_price_per_m == 1.5
        assert config.llm.output_price_per_m == 3.0

        assert config.processing.max_workers == 4
        assert config.processing.requests_per_second == 2.5
        assert config.processing.max_retries == 5
        assert config.processing.resume is False


class TestDefaultsMerging:
    def test_partial_config_gets_defaults(self, tmp_path):
        yaml_content = """\
project:
  name: "Partial Project"
org:
  name: "Partial Org"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        config = load_project_config(config_path=str(config_file))

        assert config.project_name == "Partial Project"
        assert config.org.name == "Partial Org"
        assert config.org.abbreviation == "ORG"
        assert Path(config.paths.raw_archive).name == "archive"
        assert config.llm.base_url == "https://api.deepseek.com"
        assert config.converter.type == "docling"
        assert config.wiki.type == "sage-wiki"
        assert config.processing.max_workers == 10
        assert config.doc_types == [
            "application", "report", "budget", "notification",
            "activity_list", "staff_board", "support_material", "agreement",
        ]

    def test_defaults_not_overwritten_when_section_omitted(self, tmp_path):
        yaml_content = """\
org:
  name: "Only Org"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        config = load_project_config(config_path=str(config_file))

        assert config.project_name == "My Grant Archive"
        assert config.llm.fast_model == "deepseek-v4-flash"
        assert config.llm.quality_model == "deepseek-v4-pro"
        assert config.processing.requests_per_second == 5.0
        assert config.processing.resume is True


class TestMissingRequiredFields:
    def test_empty_config_still_valid(self, tmp_path):
        config_file = tmp_path / "folio.yaml"
        config_file.write_text("")
        config = load_project_config(config_path=str(config_file))
        assert config.org.name == "My Organization"
        assert config.project_name == "My Grant Archive"

    def test_missing_llm_section_uses_defaults(self, tmp_path):
        yaml_content = "org:\n  name: TestOrg\n"
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        config = load_project_config(config_path=str(config_file))
        assert config.llm.base_url == "https://api.deepseek.com"
        assert config.llm.provider == "openai_compatible"


class TestInvalidValues:
    def test_invalid_base_url_not_http(self, tmp_path):
        yaml_content = """\
llm:
  base_url: "ftp://api.example.com"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        with pytest.raises(ValueError, match="must start with https:// or http://"):
            load_project_config(config_path=str(config_file))

    def test_invalid_base_url_http_public(self, tmp_path):
        yaml_content = """\
llm:
  base_url: "http://api.example.com"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        with pytest.raises(ValueError, match="must use https://"):
            load_project_config(config_path=str(config_file))

    def test_valid_base_url_http_localhost(self, tmp_path):
        yaml_content = """\
llm:
  base_url: "http://localhost:8080"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        config = load_project_config(config_path=str(config_file))
        assert config.llm.base_url == "http://localhost:8080"

    def test_valid_base_url_http_127(self, tmp_path):
        yaml_content = """\
llm:
  base_url: "http://127.0.0.1:9000"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        config = load_project_config(config_path=str(config_file))
        assert config.llm.base_url == "http://127.0.0.1:9000"

    def test_valid_base_url_http_private_10(self, tmp_path):
        yaml_content = """\
llm:
  base_url: "http://10.0.0.1/v1"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        config = load_project_config(config_path=str(config_file))
        assert config.llm.base_url == "http://10.0.0.1/v1"

    def test_negative_max_workers(self, tmp_path):
        yaml_content = """\
processing:
  max_workers: -1
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            load_project_config(config_path=str(config_file))

    def test_zero_max_workers(self, tmp_path):
        yaml_content = """\
processing:
  max_workers: 0
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            load_project_config(config_path=str(config_file))

    def test_invalid_converter_type(self, tmp_path):
        yaml_content = """\
converter:
  type: "invalid_converter"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        with pytest.raises(ValueError, match="Invalid converter type"):
            load_project_config(config_path=str(config_file))

    def test_invalid_wiki_type(self, tmp_path):
        yaml_content = """\
wiki:
  type: "mediawiki"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        with pytest.raises(ValueError, match="Invalid wiki type"):
            load_project_config(config_path=str(config_file))

    def test_invalid_pricing_non_numeric(self, tmp_path):
        yaml_content = """\
llm:
  pricing:
    input_per_million: "cheap"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        with pytest.raises(ValueError, match="must be a number"):
            load_project_config(config_path=str(config_file))


class TestFunderConfig:
    def test_load_funders(self, tmp_path):
        yaml_content = """\
funders:
  CCA: "Canada Council for the Arts"
  OAC: "Ontario Arts Council"
  TAC: "Toronto Arts Council"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        config = load_project_config(config_path=str(config_file))
        assert config.funders == {
            "CCA": "Canada Council for the Arts",
            "OAC": "Ontario Arts Council",
            "TAC": "Toronto Arts Council",
        }

    def test_funders_abbreviations_as_keys(self, tmp_path):
        yaml_content = """\
funders:
  SSHRC: "Social Sciences and Humanities Research Council"
  NSF: "National Science Foundation"
"""
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        config = load_project_config(config_path=str(config_file))
        assert "SSHRC" in config.funders
        assert "NSF" in config.funders

    def test_empty_funders_is_valid(self, tmp_path):
        yaml_content = "funders: {}\n"
        config_file = tmp_path / "folio.yaml"
        config_file.write_text(yaml_content)
        config = load_project_config(config_path=str(config_file))
        assert config.funders == {}


class TestLoadFromFilePath:
    def test_load_from_path_object(self, tmp_path):
        config_file = tmp_path / "myconfig.yaml"
        config_file.write_text("project:\n  name: PathTest\n")
        config = load_project_config(config_path=config_file)
        assert config.project_name == "PathTest"

    def test_load_from_string_path(self, tmp_path):
        config_file = tmp_path / "myconfig.yaml"
        config_file.write_text("project:\n  name: StringPathTest\n")
        config = load_project_config(config_path=str(config_file))
        assert config.project_name == "StringPathTest"

    def test_missing_config_file_raises(self, tmp_path):
        missing_path = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_project_config(config_path=str(missing_path))


class TestDeepMerge:
    def test_nested_dicts_merge(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 20, "z": 30}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3}

    def test_scalar_values_overridden(self):
        base = {"a": 1, "b": "old"}
        override = {"a": 2, "c": "new"}
        result = _deep_merge(base, override)
        assert result == {"a": 2, "b": "old", "c": "new"}

    def test_new_keys_added(self):
        base = {"existing": True}
        override = {"new_key": "value"}
        result = _deep_merge(base, override)
        assert result == {"existing": True, "new_key": "value"}

    def test_list_values_replaced_not_merged(self):
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = _deep_merge(base, override)
        assert result == {"items": [4, 5]}

    def test_deeply_nested_merge(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"c": 10}}}
        result = _deep_merge(base, override)
        assert result == {"a": {"b": {"c": 10, "d": 2}}}

    def test_empty_override_leaves_base_unchanged(self):
        base = {"a": 1, "b": {"c": 2}}
        result = _deep_merge(base, {})
        assert result == {"a": 1, "b": {"c": 2}}
        assert result is not base

    def test_override_none_value(self):
        base = {"a": "old"}
        override = {"a": None}
        result = _deep_merge(base, override)
        assert result == {"a": None}
