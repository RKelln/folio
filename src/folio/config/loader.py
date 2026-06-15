"""Unified configuration loader.

Loads the project config (folio.yaml) and merges it with built-in defaults.
Resolves paths, validates against the schema, and returns a typed config object.
"""

import logging
from pathlib import Path

import yaml

from folio.config.schema import (
    ConverterConfig,
    LLMConfig,
    OrgConfig,
    PathsConfig,
    ProcessingConfig,
    ProjectConfig,
    WikiConfig,
)

logger = logging.getLogger(__name__)

_DEFAULTS_PATH = Path(__file__).resolve().parent / "defaults.yaml"

_VALID_CONVERTER_TYPES = {"datalab", "marker", "docling", "pandoc"}
_VALID_WIKI_TYPES = {"sage-wiki", "null"}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Dicts are merged; scalars/lists are replaced."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_defaults() -> dict:
    """Load built-in defaults from the YAML file shipped with the package."""
    if not _DEFAULTS_PATH.exists():
        raise FileNotFoundError(
            f"Built-in defaults not found: {_DEFAULTS_PATH}\n"
            f"The folio package may be corrupted. Reinstall with: pip install --force-reinstall folio"
        )
    with open(_DEFAULTS_PATH) as f:
        return yaml.safe_load(f) or {}


def _build_config(data: dict) -> ProjectConfig:
    """Build a ProjectConfig from a merged configuration dict (YAML structure)."""
    org_data = data.get("org", {})
    org = OrgConfig(
        name=org_data.get("name", "My Organization"),
        abbreviation=org_data.get("abbreviation", "ORG"),
        description=org_data.get("description", ""),
    )

    paths_data = data.get("paths", {})
    paths = PathsConfig(
        raw_archive=paths_data.get("raw_archive", "./_raw_archive/"),
        raw_md=paths_data.get("raw_md", "./raw_md/"),
        clean_md=paths_data.get("clean_md", "./clean_md/"),
        rewrite_md=paths_data.get("rewrite_md", "./rewrite_md/"),
        wiki_project=paths_data.get("wiki_project", "./wiki/"),
    )

    converter_data = data.get("converter", {})
    converter_datalab = converter_data.get("datalab", {})
    converter = ConverterConfig(
        type=converter_data.get("type", "datalab"),
        datalab_pipeline_id=converter_datalab.get("pipeline_id", ""),
        datalab_api_key_env=converter_datalab.get("api_key_env", "DATALAB_API_KEY"),
    )

    wiki_data = data.get("wiki", {})
    wiki_sage = wiki_data.get("sage_wiki", {})
    wiki = WikiConfig(
        type=wiki_data.get("type", "sage-wiki"),
        sage_wiki_binary=wiki_sage.get("binary_path", "sage-wiki"),
        sage_wiki_pack=wiki_sage.get("pack", "arts-org"),
    )

    llm_data = data.get("llm", {})
    llm_models = llm_data.get("models", {})
    llm_pricing = llm_data.get("pricing", {})
    llm = LLMConfig(
        provider=llm_data.get("provider", "openai_compatible"),
        base_url=llm_data.get("base_url", "https://api.deepseek.com"),
        api_key_env=llm_data.get("api_key_env", "DEEPSEEK_API_KEY"),
        fast_model=llm_models.get("fast", "deepseek-v4-flash"),
        quality_model=llm_models.get("quality", "deepseek-v4-pro"),
        input_price_per_m=float(llm_pricing.get("input_per_million", 0.14)),
        output_price_per_m=float(llm_pricing.get("output_per_million", 0.28)),
    )

    processing_data = data.get("processing", {})
    processing = ProcessingConfig(
        max_workers=int(processing_data.get("max_workers", 10)),
        requests_per_second=float(processing_data.get("requests_per_second", 5.0)),
        max_retries=int(processing_data.get("max_retries", 3)),
        resume=bool(processing_data.get("resume", True)),
    )

    project_data = data.get("project", {})
    return ProjectConfig(
        project_name=project_data.get("name", "folio"),
        org=org,
        funders=data.get("funders", {}),
        doc_types=data.get("doc_types", []),
        paths=paths,
        converter=converter,
        wiki=wiki,
        llm=llm,
        processing=processing,
    )


def _validate(config: ProjectConfig) -> None:
    """Validate a ProjectConfig, raising ValueError for hard errors and logging warnings."""
    if not config.funders:
        logger.warning(
            "No funders configured. Add entries to 'funders' in folio.yaml "
            "to enable funder-aware classification and search."
        )

    if config.converter.type not in _VALID_CONVERTER_TYPES:
        raise ValueError(
            f"Invalid converter type: '{config.converter.type}'. "
            f"Must be one of: {', '.join(sorted(_VALID_CONVERTER_TYPES))}"
        )

    if config.wiki.type not in _VALID_WIKI_TYPES:
        raise ValueError(
            f"Invalid wiki type: '{config.wiki.type}'. "
            f"Must be one of: {', '.join(sorted(_VALID_WIKI_TYPES))}"
        )

    if not config.llm.base_url.startswith("https://"):
        raise ValueError(
            f"LLM base_url must start with https://, got: '{config.llm.base_url}'"
        )

    if config.processing.max_workers < 1:
        raise ValueError(
            f"processing.max_workers must be >= 1, got: {config.processing.max_workers}"
        )

    if not Path(config.paths.raw_archive).exists():
        logger.warning(
            f"Raw archive directory does not exist: {config.paths.raw_archive}\n"
            f"Run 'folio init' or create this directory before running the pipeline."
        )


def load_project_config(config_path: str | Path | None = None) -> ProjectConfig:
    """Load and validate the project configuration.

    When *config_path* is ``None``, returns a ``ProjectConfig`` populated
    entirely from built-in defaults (suitable for inspection or testing).

    When *config_path* is provided, the file is loaded, deep-merged with
    the built-in defaults (user values take precedence), validated, and
    returned as a ``ProjectConfig`` instance.

    Raises:
        FileNotFoundError: The config file or built-in defaults are missing.
        ValueError: The configuration has invalid values.
    """
    defaults = _load_defaults()

    if config_path is None:
        merged = defaults
    else:
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f'Run "folio init" to create one.'
            )
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        merged = _deep_merge(defaults, user_config)

    config = _build_config(merged)
    _validate(config)
    return config
