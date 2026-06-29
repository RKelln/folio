"""folio doctor — system health check command.

Runs comprehensive health checks across the folio installation:
config validation, binary availability, API keys, wiki health,
symlink integrity, and pipeline state consistency.

Usage:
    folio doctor                   # Run all health checks
    folio doctor --json            # Output results as JSON
    folio doctor --dry-run         # Preview without executing
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

from folio import __version__
from folio.config.loader import load_project_config

logger = logging.getLogger(__name__)


def _check(name: str, status: str, message: str) -> dict:
    return {"name": name, "status": status, "message": message}


def _check_config(config_path: str) -> dict:
    """Validate folio.yaml exists and loads."""
    if not Path(config_path).exists():
        return _check("config", "error", f"Config file not found: {config_path}")
    try:
        load_project_config(config_path)
    except Exception as exc:
        return _check("config", "error", f"Failed to parse {config_path}: {exc}")
    return _check("config", "ok", f"Config file loaded: {config_path}")


def _check_api_keys(config) -> dict:
    """Verify required API key env vars are set."""
    llm = getattr(config, "llm", None)
    if llm is None or not hasattr(llm, "api_key_env"):
        return _check("api", "warn", "No LLM provider configured")

    key_env = llm.api_key_env
    if os.environ.get(key_env):
        return _check("api", "ok", f"{key_env} is set")
    return _check("api", "warn", f"{key_env} not set — LLM features will fail")


def _check_converter(config) -> dict:
    """Check converter binary or SDK availability."""
    conv_type = getattr(config.converter, "type", "liteparse") if hasattr(config, "converter") else "liteparse"

    if conv_type == "liteparse":
        try:
            import liteparse  # noqa: F401
            return _check("converter", "ok", "liteparse available (Python SDK)")
        except ImportError:
            return _check("converter", "error", "liteparse not installed (uv pip install liteparse)")
    elif conv_type == "pandoc":
        if shutil.which("pandoc"):
            return _check("converter", "ok", "pandoc on PATH")
        return _check("converter", "error", "pandoc not found on PATH")
    elif conv_type == "datalab":
        try:
            import datalab  # noqa: F401
            return _check("converter", "ok", "datalab SDK available")
        except ImportError:
            return _check("converter", "error", "datalab SDK not installed")
    elif conv_type == "docling":
        try:
            import docling  # noqa: F401
            return _check("converter", "ok", "docling available")
        except ImportError:
            return _check("converter", "error", "docling not installed")
    elif conv_type == "marker":
        try:
            import marker  # noqa: F401
            return _check("converter", "ok", "marker available")
        except ImportError:
            return _check("converter", "error", "marker not installed")
    elif conv_type == "cascade":
        return _check("converter", "ok", f"cascade converter ({', '.join(getattr(config.converter, 'cascade', []))})")
    return _check("converter", "warn", f"Unknown converter type: {conv_type}")


def _check_sage_wiki_binary(config) -> dict:
    """Check sage-wiki binary is on PATH."""
    wiki_type = getattr(config.wiki, "type", "null") if hasattr(config, "wiki") else "null"
    if wiki_type == "null":
        return _check("sage-wiki", "info", "wiki backend is null — sage-wiki not required")

    binary = shutil.which("sage-wiki")
    if binary:
        return _check("sage-wiki", "ok", f"sage-wiki on PATH: {binary}")
    return _check("sage-wiki", "error", "sage-wiki not found on PATH (go install github.com/xoai/sage-wiki/cmd/sage-wiki@latest)")


def _check_symlinks(config) -> list[dict]:
    """Verify root symlinks are intact."""
    results = []
    wiki_type = getattr(config.wiki, "type", "null") if hasattr(config, "wiki") else "null"

    if wiki_type == "sage-wiki":
        public_link = Path("wiki")
        wiki_path = Path(config.paths.wiki_project) / "wiki"
        if public_link.is_symlink():
            target = public_link.readlink()
            if wiki_path == target or target.name == "wiki":
                results.append(_check("symlink: wiki", "ok", f"wiki/ -> {target}"))
            else:
                results.append(_check("symlink: wiki", "warn", f"wiki/ -> {target} (expected -> {wiki_path})"))
        elif public_link.exists():
            results.append(_check("symlink: wiki", "warn", "wiki/ exists but is not a symlink"))
        else:
            results.append(_check("symlink: wiki", "warn", "wiki/ not found (run folio wiki compile)"))

    return results


def _check_pipeline_state(config) -> list[dict]:
    """Check pipeline directory consistency."""
    results = []
    paths = config.paths

    dirs = [
        ("raw_archive", Path(paths.raw_archive)),
        ("raw_md", Path(paths.raw_md)),
        ("clean_md", Path(paths.clean_md)),
        ("rewrite_md", Path(paths.rewrite_md)),
    ]

    for name, d in dirs:
        if d.is_dir():
            file_count = sum(1 for p in d.iterdir() if p.is_file())
            results.append(_check(f"dir: {name}", "ok", f"{d} exists ({file_count} files)"))
        else:
            results.append(_check(f"dir: {name}", "warn", f"{d} does not exist (create with folio init)"))

    # Pipeline parity checks
    raw_archive = Path(paths.raw_archive)
    raw_md = Path(paths.raw_md)
    clean_md = Path(paths.clean_md)
    rewrite_md = Path(paths.rewrite_md)

    if raw_archive.is_dir() and raw_md.is_dir():
        archive_count = sum(1 for p in raw_archive.rglob("*") if p.is_file())
        raw_md_count = sum(1 for p in raw_md.glob("*.md"))
        if archive_count > 0 and raw_md_count == 0:
            results.append(_check("pipeline", "warn", f"raw_archive/ has {archive_count} files but raw_md/ is empty — run folio pipeline"))
        elif archive_count > 0 and raw_md_count > 0 and raw_md_count < archive_count:
            results.append(_check("pipeline", "ok", f"raw_archive/ {archive_count} files → raw_md/ {raw_md_count} files (some unconverted)"))

    if raw_md.is_dir() and clean_md.is_dir():
        raw_md_count = sum(1 for p in raw_md.glob("*.md"))
        clean_md_count = sum(1 for p in clean_md.glob("*.md"))
        if raw_md_count > 0 and clean_md_count == 0:
            results.append(_check("pipeline", "warn", f"raw_md/ has {raw_md_count} files but clean_md/ is empty — run folio pipeline"))
        elif raw_md_count > 0 and clean_md_count > 0 and clean_md_count < raw_md_count:
            results.append(_check("pipeline", "ok", f"clean_md/ {clean_md_count} files (of {raw_md_count} in raw_md/)"))

    if clean_md.is_dir() and rewrite_md.is_dir():
        clean_md_count = sum(1 for p in clean_md.glob("*.md"))
        rewrite_md_count = sum(1 for p in rewrite_md.glob("*.md"))
        if clean_md_count > 0 and rewrite_md_count == 0:
            results.append(_check("pipeline", "warn", f"clean_md/ has {clean_md_count} files but rewrite_md/ is empty — run folio pipeline"))

    return results


def _run_wiki_doctor(config) -> list[dict]:
    """Delegate to sage-wiki doctor if backend is sage-wiki."""
    wiki_type = getattr(config.wiki, "type", "null") if hasattr(config, "wiki") else "null"
    if wiki_type != "sage-wiki":
        return []

    from folio.adapters.wiki import get_wiki_backend

    wiki_dir = Path(config.paths.wiki_project)
    results = []

    try:
        backend = get_wiki_backend(config)
    except Exception as exc:
        return [_check("wiki doctor", "error", f"Failed to init wiki backend: {exc}")]

    config_file = wiki_dir / "config.yaml"
    if config_file.exists():
        backend._project_dir = wiki_dir
    else:
        return [_check("wiki doctor", "warn", f"No sage-wiki config at {config_file} — run folio wiki compile")]

    try:
        output = backend.doctor()
    except Exception as exc:
        return [_check("wiki doctor", "error", f"sage-wiki doctor failed: {exc}")]

    if output.strip():
        results.append(_check("wiki doctor", "ok", "sage-wiki doctor ran"))
        for line in output.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            status = "ok"
            if line.startswith("[WARN]"):
                status = "warn"
            elif line.startswith("[ERROR]") or line.startswith("[FATAL]"):
                status = "error"
            elif line.startswith("[INFO]"):
                status = "info"
            results.append(_check("wiki:", status, line))
    else:
        results.append(_check("wiki doctor", "warn", "sage-wiki doctor returned no output"))

    return results


def _run_all_checks(config, config_path: str) -> list[dict]:
    """Run all health checks and return a flat list of results."""
    checks = []

    # 1. Config
    checks.append(_check_config(config_path))
    if checks[-1]["status"] == "error":
        return checks  # can't continue without valid config

    # 2. API keys
    checks.append(_check_api_keys(config))

    # 3. Converter
    checks.append(_check_converter(config))

    # 4. Sage-wiki binary
    checks.append(_check_sage_wiki_binary(config))

    # 5. Symlinks
    checks.extend(_check_symlinks(config))

    # 6. Pipeline directory state
    checks.extend(_check_pipeline_state(config))

    # 7. Wiki doctor (sub-doctor)
    checks.extend(_run_wiki_doctor(config))

    return checks


def _compute_summary(checks: list[dict]) -> dict:
    """Count checks by status."""
    summary = {"ok": 0, "warn": 0, "error": 0, "info": 0}
    for c in checks:
        summary[c["status"]] = summary.get(c["status"], 0) + 1
    return summary


def _format_output(checks: list[dict], json_output: bool = False) -> str:
    """Format check results as text or JSON."""
    if json_output:
        return json.dumps({"checks": checks, "summary": _compute_summary(checks)}, indent=2)

    lines = []
    lines.append("folio doctor — system health check")
    lines.append("=" * 36)
    lines.append("")

    wiki_lines = []
    has_wiki_section = False

    for c in checks:
        if c["name"].startswith("wiki:"):
            wiki_lines.append(c)
            has_wiki_section = True
        elif c["name"] == "wiki doctor":
            has_wiki_section = True
            wiki_lines.append(c)
        else:
            tag = {"ok": "OK", "warn": "WARN", "error": "ERROR", "info": "INFO"}.get(c["status"], c["status"].upper())
            lines.append(f"  [{tag:5s}] {c['name']}: {c['message']}")

    if has_wiki_section:
        lines.append("")
        lines.append("--- wiki sub-doctor ---")
        for c in wiki_lines:
            if c["name"] == "wiki doctor":
                tag = {"ok": "OK", "warn": "WARN", "error": "ERROR", "info": "INFO"}.get(c["status"], c["status"].upper())
                lines.append(f"  [{tag:5s}] {c['message']}")
            else:
                status = c["status"]
                if status == "ok":
                    prefix = "  [OK]   "
                elif status == "warn":
                    prefix = "  [WARN] "
                elif status == "error":
                    prefix = "  [ERROR]"
                elif status == "info":
                    prefix = "  [INFO] "
                else:
                    prefix = f"  [{status.upper():5s}] "
                lines.append(f"{prefix}{c['message']}")

    lines.append("")
    summary = _compute_summary(checks)
    lines.append(f"Summary: {summary['ok']} OK, {summary['warn']} WARN, {summary['error']} ERROR, {summary['info']} INFO")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio doctor",
        description="Run system health checks across the folio installation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio doctor              # Run all health checks\n"
            "  folio doctor --json       # Output as JSON\n"
            "  folio doctor --dry-run    # Preview checks without running\n"
        ),
    )

    parser.add_argument(
        "--config", "-c",
        default="folio.yaml",
        help="Path to folio.yaml (default: folio.yaml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview checks without executing",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    if args.dry_run:
        checks_preview = [
            "config: validate folio.yaml exists and parses",
            "api: check required env vars are set",
            "converter: verify converter binary/SDK availability",
            "sage-wiki: check binary on PATH",
            "symlinks: verify root symlinks (wiki/)",
            "pipeline: check directory consistency across stages",
            "wiki doctor: delegate to sage-wiki doctor subchecks",
        ]
        if args.json_output:
            print(json.dumps({"dry_run": True, "checks": checks_preview}, indent=2))
        else:
            print("folio doctor — dry run")
            print("=" * 22)
            print()
            print("Would run the following checks:")
            for c in checks_preview:
                print(f"  - {c}")
            print()
            print("No checks executed (--dry-run).")
        return

    config_path = args.config

    if not Path(config_path).exists():
        checks = [_check_config(config_path)]
        print(_format_output(checks, json_output=args.json_output), end="")
        sys.exit(1)

    try:
        config = load_project_config(config_path)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        logger.error("Failed to load config '%s': %s", config_path, exc)
        checks = [_check_config(config_path)]
        print(_format_output(checks, json_output=args.json_output), end="")
        sys.exit(1)

    checks = _run_all_checks(config, config_path)
    print(_format_output(checks, json_output=args.json_output), end="")


if __name__ == "__main__":
    main()
