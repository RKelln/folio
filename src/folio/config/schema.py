"""Configuration schema and validation using dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OrgConfig:
    name: str = "My Organization"
    abbreviation: str = "ORG"
    description: str = ""

@dataclass
class PathsConfig:
    raw_archive: str = "./_raw_archive/"
    raw_md: str = "./raw_md/"
    clean_md: str = "./clean_md/"
    rewrite_md: str = "./rewrite_md/"
    wiki_project: str = "./.folio/sage-wiki/"

@dataclass
class LLMConfig:
    provider: str = "openai_compatible"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    fast_model: str = "deepseek-v4-flash"
    quality_model: str = "deepseek-v4-pro"
    input_price_per_m: float = 0.14
    output_price_per_m: float = 0.28
    wiki_models: dict[str, str] = field(default_factory=dict)
    wiki_extra_params: dict[str, dict] = field(default_factory=dict)
    wiki_api_params: dict = field(default_factory=dict)

@dataclass
class ConverterConfig:
    type: str = "liteparse"
    datalab_pipeline_id: str = ""
    datalab_api_key_env: str = "DATALAB_API_KEY"
    cascade: list[str] = field(default_factory=list)
    cascade_thresholds: dict = field(default_factory=dict)

@dataclass
class WikiConfig:
    type: str = "sage-wiki"
    sage_wiki_binary: str = "sage-wiki"
    sage_wiki_pack: str = "arts-org"  # default pack, bundled in folio templates/packs (v1.1)
    compiler: dict = field(default_factory=dict)

@dataclass
class AgentmapConfig:
    enabled: bool = False
    binary_path: str = "agentmap"

@dataclass
class ProcessingConfig:
    max_workers: int = 10
    requests_per_second: float = 5.0
    max_retries: int = 3
    resume: bool = True

@dataclass
class ProjectConfig:
    """Top-level folio project configuration."""
    project_name: str = "folio"
    org: OrgConfig = field(default_factory=OrgConfig)
    funders: dict[str, str] = field(default_factory=dict)
    doc_types: list[str] = field(default_factory=lambda: [
        "application", "report", "budget", "notification", "activity_list",
        "staff_board", "support_material", "agreement", "webpage"
    ])
    paths: PathsConfig = field(default_factory=PathsConfig)
    converter: ConverterConfig = field(default_factory=ConverterConfig)
    wiki: WikiConfig = field(default_factory=WikiConfig)
    agentmap: AgentmapConfig = field(default_factory=AgentmapConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    classification: dict = field(default_factory=dict)
    headings: dict = field(default_factory=dict)
    rewrite: dict = field(default_factory=dict)
    prioritize: dict = field(default_factory=dict)
    audit: dict = field(default_factory=dict)
