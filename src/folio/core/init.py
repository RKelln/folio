from __future__ import annotations

import copy
import sys
from importlib import resources
from pathlib import Path

import yaml

from folio.config.loader import _deep_merge

AVAILABLE_PROFILES = [
    "canadian-artist-run-centre",
    "canadian-gallery",
    "canadian-festival",
    "canadian-theatre",
    "canadian-dance",
    "generic-canadian-arts",
    "generic",
]

_BUILTIN_DEFAULTS = resources.files("folio.config") / "defaults.yaml"
_PROFILES_BASE = resources.files("folio.templates") / "profiles"


def init_project(
    output_path: Path = Path("folio.yaml"),
    profile: str | None = None,
    guided: bool = False,
    from_scan: Path | None = None,
    org_name: str | None = None,
    funders: dict[str, str] | None = None,
    doc_types: list[str] | None = None,
    raw_archive: str | None = None,
    dry_run: bool = False,
) -> dict:
    if guided:
        if dry_run:
            return {
                "config_path": str(output_path.resolve()),
                "profile": profile,
                "warnings": ["Cannot preview guided setup with --dry-run. Run without --dry-run to use interactive mode."],
                "merged_config": {},
            }
        user_config = _guided_setup()
    elif profile:
        user_config = _load_profile(profile)
        if org_name:
            user_config.setdefault("org", {})["name"] = org_name
        if funders:
            user_config["funders"] = funders
        if raw_archive:
            user_config.setdefault("paths", {})["raw_archive"] = raw_archive
    elif from_scan:
        user_config = _build_config_from_scan(from_scan)
        if org_name:
            user_config.setdefault("org", {})["name"] = org_name
    else:
        user_config = _minimal_config(
            org_name=org_name,
            funders=funders,
            doc_types=doc_types,
            raw_archive=raw_archive,
        )

    merged = _merge_with_defaults(user_config)

    warnings: list[str] = []
    if not merged.get("funders"):
        warnings.append("No funders configured. Add entries to 'funders' in folio.yaml.")

    if not dry_run:
        _write_yaml(output_path, merged)
        _write_gitignore()

    return {
        "config_path": str(output_path.resolve()),
        "profile": profile,
        "warnings": warnings,
        "merged_config": merged,
    }


def _guided_setup() -> dict:
    print("folio init — guided setup")
    print("===========================")
    print()

    org_name = _ask("What's your organization's name?") or "My Organization"
    org_description = _ask("Brief description (optional):") or ""

    raw_archive = _ask("What folder contains your grant documents?") or "./_raw_archive/"

    funders_raw = _ask("What funders do you apply to? (comma-separated abbreviations)")
    funders: dict[str, str] = {}
    if funders_raw:
        for abbrev in funders_raw.split(","):
            abbrev = abbrev.strip()
            if abbrev:
                funders[abbrev] = abbrev

    doc_types_raw = _ask(
        "What document types do you have? (comma-separated, or press Enter for defaults)"
    )
    if doc_types_raw:
        doc_types = [t.strip() for t in doc_types_raw.split(",") if t.strip()]
    else:
        doc_types = [
            "application", "report", "budget", "notification",
            "activity_list", "staff_board", "support_material", "agreement",
        ]
        print(f"  Using defaults: {', '.join(doc_types)}")

    api_key = _ask(
        "What's your DeepSeek API key? (or press Enter to set later via .env)"
    )
    if api_key and api_key.strip():
        print("  API key will be written to .env")
        _write_env_key(api_key.strip())
    else:
        print("  Skipped. Set DEEPSEEK_API_KEY in .env before running the pipeline.")

    print()
    print("Configuration summary:")
    print(f"  Organization: {org_name}")
    if org_description:
        print(f"  Description: {org_description}")
    print(f"  Raw archive: {raw_archive}")
    if funders:
        print(f"  Funders: {', '.join(funders)}")
    print(f"  Document types: {', '.join(doc_types)}")
    print()

    confirmed = _ask("Write folio.yaml? (Y/n)") or "y"
    if confirmed.lower() not in ("y", "yes", ""):
        print("Aborted.")
        sys.exit(0)

    return {
        "project": {
            "name": f"{org_name} Grant Archive",
        },
        "org": {
            "name": org_name,
            "abbreviation": _abbreviate(org_name),
            "description": org_description,
        },
        "funders": funders,
        "doc_types": doc_types,
        "paths": {
            "raw_archive": raw_archive,
        },
    }


def _load_profile(profile_name: str) -> dict:
    profile_path = _PROFILES_BASE / f"{profile_name}.yaml"
    try:
        return yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        print(f"Profile '{profile_name}' not found at {profile_path}")
        print(f"Available profiles: {', '.join(AVAILABLE_PROFILES)}")
        sys.exit(1)


def _build_config_from_scan(scan_path: Path) -> dict:
    if not scan_path.exists():
        print(f"Scan report not found: {scan_path}")
        sys.exit(1)

    with open(scan_path) as f:
        scan = yaml.safe_load(f) or {}

    config: dict = {"project": {"name": "My Grant Archive"}, "org": {"name": "My Organization", "abbreviation": "ORG"}}

    funders = scan.get("by_funder", {})
    if funders:
        config["funders"] = {
            abbrev: info.get("full_name", abbrev)
            for abbrev, info in funders.items()
        }

    types = scan.get("by_type", {})
    if types:
        config["doc_types"] = list(types.keys())

    source = scan.get("source_path", "")
    if source:
        config.setdefault("paths", {})["raw_archive"] = source

    return config


def _merge_with_defaults(user_config: dict) -> dict:
    try:
        data = _BUILTIN_DEFAULTS.read_text(encoding="utf-8")
        defaults = yaml.safe_load(data) or {}
    except FileNotFoundError:
        print(f"Built-in defaults not found: {_BUILTIN_DEFAULTS}")
        sys.exit(1)

    return _deep_merge(copy.deepcopy(defaults), user_config)


def _minimal_config(
    org_name: str | None = None,
    funders: dict[str, str] | None = None,
    doc_types: list[str] | None = None,
    raw_archive: str | None = None,
) -> dict:
    name = org_name or "My Organization"
    return {
        "project": {
            "name": f"{name} Grant Archive",
        },
        "org": {
            "name": name,
            "abbreviation": _abbreviate(name),
        },
        "funders": funders or {},
        "doc_types": doc_types or [],
        "paths": {
            "raw_archive": raw_archive or "./_raw_archive/",
        },
    }


def _write_yaml(output_path: Path, config: dict) -> None:
    with open(output_path, "w") as f:
        f.write("# folio project configuration\n")
        f.write("# Generated by `folio init`\n")
        f.write("# Edit this file to customize your pipeline.\n")
        f.write("\n")
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _write_gitignore() -> None:
    gitignore = Path(".gitignore")
    if gitignore.exists():
        return
    gitignore.write_text(
        "# Secrets\n"
        ".env\n"
        "\n"
        "# Raw source documents (PDFs/DOCX — not version-controlled)\n"
        "archive/\n"
        "\n"
        "# Pipeline intermediates — regenerable via `folio pipeline`\n"
        ".folio/converted/\n"
        ".folio/cleaned/\n"
        ".folio/non_canonical/\n"
        ".folio/pipeline.lock\n"
        ".folio/manifest.json\n"
        ".folio/prioritize_progress.json\n"
        "\n"
        "# Runtime / agent artifacts\n"
        ".opencode/\n"
        ".sage/\n"
        "hermes/\n"
    )


def _write_env_key(api_key: str) -> None:
    env_path = Path(".env")
    existing = ""
    if env_path.exists():
        existing = env_path.read_text()

    if "DEEPSEEK_API_KEY" in existing:
        print("  .env already contains DEEPSEEK_API_KEY. Skipping.")
        return

    if existing and not existing.endswith("\n"):
        existing += "\n"
    env_path.write_text(f"{existing}DEEPSEEK_API_KEY={api_key}\n")


def _ask(prompt: str) -> str:
    try:
        return input(f"{prompt} ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)


def _abbreviate(name: str) -> str:
    words = name.split()
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0].upper() for w in words if w[0].isalpha())
