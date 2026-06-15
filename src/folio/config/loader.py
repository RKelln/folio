"""Unified configuration loader.

Loads the project config (folio.yaml) and merges it with built-in defaults.
Resolves paths, validates against the schema, and returns a typed config object.
"""

from pathlib import Path

import yaml


def load_project_config(config_path: str | Path | None = None) -> dict:
    """Load and validate the project configuration.

    Searches for folio.yaml in the current working directory if no
    path is given. Merges with built-in defaults.

    Returns a validated configuration dict.
    """
    if config_path is None:
        config_path = Path.cwd() / 'folio.yaml'

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f'Config file not found: {config_path}\n'
            f'Run "folio init" to create one.'
        )

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    # TODO: merge with defaults, validate via Pydantic schema
    return config
