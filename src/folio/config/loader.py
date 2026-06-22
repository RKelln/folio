"""Unified configuration loader.

Loads the project config (folio.yaml) and merges it with built-in defaults.
Resolves paths, validates against the schema, and returns a typed config object.
"""

from __future__ import annotations

import logging
import sys
from importlib import resources
from pathlib import Path

import yaml
from dotenv import load_dotenv

from folio.config.schema import (
    AgentmapConfig,
    ConverterConfig,
    LLMConfig,
    OrgConfig,
    PathsConfig,
    ProcessingConfig,
    ProjectConfig,
    WikiConfig,
)

logger = logging.getLogger(__name__)

_VALID_CONVERTER_TYPES = {"liteparse", "datalab", "marker", "docling", "pandoc", "cascade"}
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
    _defaults_path = resources.files("folio.config") / "defaults.yaml"
    try:
        data = _defaults_path.read_text(encoding="utf-8")
        return yaml.safe_load(data) or {}
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Built-in defaults not found: {_defaults_path}\n"
            f"The folio package may be corrupted. "
            f"Reinstall with: pip install --force-reinstall folio"
        ) from None


def _build_config(data: dict, config_dir: Path | None = None) -> ProjectConfig:
    """Build a ProjectConfig from a merged configuration dict, resolving relative paths."""
    if config_dir is None:
        config_dir = Path.cwd()
    org_data = data.get("org", {})
    org = OrgConfig(
        name=org_data.get("name", "My Organization"),
        abbreviation=org_data.get("abbreviation", "ORG"),
        description=org_data.get("description", ""),
    )

    paths_data = data.get("paths", {})
    def _resolve_path(key: str, fallback: str) -> str:
        p = paths_data.get(key, fallback)
        return str(config_dir / p)
    paths = PathsConfig(
        raw_archive=_resolve_path("raw_archive", "./_raw_archive/"),
        raw_md=_resolve_path("raw_md", "./raw_md/"),
        clean_md=_resolve_path("clean_md", "./clean_md/"),
        rewrite_md=_resolve_path("rewrite_md", "./rewrite_md/"),
        wiki_project=_resolve_path("wiki_project", "./.folio/sage-wiki/"),
    )

    converter_data = data.get("converter", {})
    converter_datalab = converter_data.get("datalab", {})
    converter = ConverterConfig(
        type=converter_data.get("type", "liteparse"),
        datalab_pipeline_id=converter_datalab.get("pipeline_id", ""),
        datalab_api_key_env=converter_datalab.get("api_key_env", "DATALAB_API_KEY"),
        cascade=list(converter_data.get("cascade", [])),
        cascade_thresholds=dict(converter_data.get("cascade_thresholds", {})),
    )

    wiki_data = data.get("wiki", {})
    wiki_sage = wiki_data.get("sage_wiki", {})
    wiki = WikiConfig(
        type=wiki_data.get("type", "sage-wiki"),
        sage_wiki_binary=wiki_sage.get("binary_path", "sage-wiki"),
        sage_wiki_pack=wiki_sage.get("pack", "arts-org"),
    )

    agentmap_data = data.get("agentmap", {})
    agentmap = AgentmapConfig(
        enabled=bool(agentmap_data.get("enabled", False)),
        binary_path=str(agentmap_data.get("binary_path", "agentmap")),
    )

    llm_data = data.get("llm", {})
    llm_models = llm_data.get("models", {})
    llm_pricing = llm_data.get("pricing", {})
    try:
        input_price = float(llm_pricing.get("input_per_million", 0.14))
    except (TypeError, ValueError):
        raise ValueError(
            f"llm.pricing.input_per_million must be a number, "
            f"got: {llm_pricing.get('input_per_million')!r}"
        )
    try:
        output_price = float(llm_pricing.get("output_per_million", 0.28))
    except (TypeError, ValueError):
        raise ValueError(
            f"llm.pricing.output_per_million must be a number, "
            f"got: {llm_pricing.get('output_per_million')!r}"
        )

    llm = LLMConfig(
        provider=llm_data.get("provider", "openai_compatible"),
        base_url=llm_data.get("base_url", "https://api.deepseek.com"),
        api_key_env=llm_data.get("api_key_env", "DEEPSEEK_API_KEY"),
        fast_model=llm_models.get("fast", "deepseek-v4-flash"),
        quality_model=llm_models.get("quality", "deepseek-v4-pro"),
        input_price_per_m=input_price,
        output_price_per_m=output_price,
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
        agentmap=agentmap,
        llm=llm,
        processing=processing,
        classification=data.get("classification", {}),
        headings=data.get("headings", {}),
        rewrite=data.get("rewrite", {}),
        prioritize=data.get("prioritize", {}),
    )


def _validate_agentmap_binary(binary_path: str) -> None:
    """Verify agentmap binary is accessible when enabled."""
    import shutil
    resolved = shutil.which(binary_path)
    if resolved is None:
        raise ValueError(
            f"agentmap is enabled but binary '{binary_path}' not found on PATH.\n"
            f"Install agentmap or set agentmap.enabled: false in folio.yaml."
        )
    logger.info("agentmap binary found: %s", resolved)


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

    if config.converter.type == "cascade":
        cascade = config.converter.cascade
        if len(cascade) < 2:
            raise ValueError(
                "converter.cascade must list at least 2 converter tiers when "
                f"converter.type is 'cascade', got: {cascade}"
            )
        single_types = _VALID_CONVERTER_TYPES - {"cascade"}
        for name in cascade:
            if name not in single_types:
                raise ValueError(
                    f"Invalid converter in converter.cascade: '{name}'. "
                    f"Each tier must be one of: {', '.join(sorted(single_types))} "
                    f"(nested 'cascade' is not allowed)."
                )

    if config.wiki.type not in _VALID_WIKI_TYPES:
        raise ValueError(
            f"Invalid wiki type: '{config.wiki.type}'. "
            f"Must be one of: {', '.join(sorted(_VALID_WIKI_TYPES))}"
        )

    url = config.llm.base_url
    if url.startswith("https://"):
        pass
    elif url.startswith("http://"):
        allowed_prefixes = (
            "http://localhost", "http://127.",
            "http://192.168.", "http://10.",
            "http://172.16.", "http://172.17.", "http://172.18.", "http://172.19.",
            "http://172.20.", "http://172.21.", "http://172.22.", "http://172.23.",
            "http://172.24.", "http://172.25.", "http://172.26.", "http://172.27.",
            "http://172.28.", "http://172.29.", "http://172.30.", "http://172.31.",
        )
        if not url.startswith(allowed_prefixes):
            raise ValueError(
                f"LLM base_url must use https://, or http:// for "
                f"localhost/private IPs. Got: '{url}'"
            )
    else:
        raise ValueError(
            f"LLM base_url must start with https:// or http://, got: '{url}'"
        )

    if config.processing.max_workers < 1:
        raise ValueError(
            f"processing.max_workers must be >= 1, got: {config.processing.max_workers}"
        )

    if config.agentmap.enabled:
        _validate_agentmap_binary(config.agentmap.binary_path)

    if not Path(config.paths.raw_archive).exists():
        logger.warning(
            f"Raw archive directory does not exist: {config.paths.raw_archive}\n"
            f"Run 'folio init' or create this directory before running the pipeline."
        )


def load_config_or_exit(config_path: str | Path) -> ProjectConfig:
    """Load config from *config_path*, printing an error and exiting if not found.

    Use for commands that require configuration (pipeline, rewrite, etc.).
    """
    if not Path(config_path).exists():
        print(
            "folio.yaml not found. This command requires configuration. Run 'folio init' first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return load_project_config(config_path)


def load_config_or_warn(config_path: str | Path) -> ProjectConfig | None:
    """Load config from *config_path* if it exists, else warn and return ``None``.

    Use for commands that can operate with defaults (scan, clean, classify, etc.).
    """
    if not Path(config_path).exists():
        logger.warning("folio.yaml not found. Using defaults.")
        return None
    return load_project_config(config_path)


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
        load_dotenv()
        merged = defaults
        config_dir = Path.cwd()
    else:
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f'Run "folio init" to create one.'
            )
        config_dir = config_path.parent.resolve()
        load_dotenv(config_dir / ".env")
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        # Auto-discover headings.yaml if present
        headings_path = config_dir / "headings.yaml"
        if headings_path.exists():
            with open(headings_path) as f:
                headings_yaml = yaml.safe_load(f) or {}
            user_config["headings"] = headings_yaml
            logger.info("Loaded heading taxonomy from %s", headings_path)
        merged = _deep_merge(defaults, user_config)

    config = _build_config(merged, config_dir)
    _validate(config)
    return config
