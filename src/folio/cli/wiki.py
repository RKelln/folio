"""folio wiki — sage-wiki maintenance commands.

Usage:
    folio wiki compile      # (Re)compile the wiki from markdown/ sources
    folio wiki status       # Show wiki stats
    folio wiki doctor       # Validate wiki config
    folio wiki lint         # Run lint passes (--pass NAME, --fix)
    folio wiki coverage     # Compilation coverage
    folio wiki diff         # Pending changes
    folio wiki verify       # Trust verification (--all, --since, --limit)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from folio import __version__
from folio.adapters.wiki import get_wiki_backend
from folio.config.loader import load_project_config

logger = logging.getLogger(__name__)


def _build_wiki_llm_config(config) -> dict:
    """Build api, models, embed sections for sage-wiki config from folio config."""
    result = {}
    llm = getattr(config, "llm", None)
    if not llm or not hasattr(llm, "provider"):
        return result
    fetch_model = getattr(llm, "fast_model", None)
    write_model = getattr(llm, "quality_model", None)
    api_key = os.environ.get(llm.api_key_env, "")
    if api_key:
        os.environ.setdefault(llm.api_key_env, api_key)
    result["api"] = {
        "provider": "openai-compatible" if "deepseek" in str(llm.base_url) else llm.provider,
        "base_url": llm.base_url,
        "api_key": f"${{{llm.api_key_env}}}",
    }
    result["models"] = {
        "summarize": fetch_model or write_model or "deepseek-chat",
        "extract": fetch_model or write_model or "deepseek-chat",
        "write": write_model or fetch_model or "deepseek-chat",
        "lint": fetch_model or write_model or "deepseek-chat",
        "query": write_model or fetch_model or "deepseek-chat",
    }
    result["embed"] = {"provider": "auto"}
    return result


def _init_backend(config, project_dir: Path):
    backend = get_wiki_backend(config)

    # Preserve existing config.yaml if present (pipeline may have written a full one)
    config_file = project_dir / "config.yaml"
    if config_file.exists():
        backend._project_dir = project_dir
        return backend

    wiki_config = {
        "version": 1,
        "project": getattr(config.org, "name", "folio"),
        "pack": getattr(config.wiki, "sage_wiki_pack", "arts-org"),
        "sources": [{"path": "raw", "type": "auto", "watch": False}],
        "output": "wiki",
    }
    wiki_config.update(_build_wiki_llm_config(config))
    backend.init(project_dir, wiki_config)
    return backend


def _do_compile(config, wiki_dir: Path, backend) -> None:
    """Full wiki (re)compile: init config, install pack, compile, symlink."""
    rewrite_dir = Path(config.paths.rewrite_md)
    pack_name = getattr(config.wiki, "sage_wiki_pack", "arts-org")

    # Re-init to ensure raw symlink is fresh and config is up to date
    print(f"  Initializing wiki project at {wiki_dir}...")
    wiki_config = {
        "version": 1,
        "project": config.org.name,
        "pack": pack_name,
        "sources": [{"path": "raw", "type": "auto", "watch": False}],
        "output": "wiki",
    }
    wiki_config.update(_build_wiki_llm_config(config))
    backend.init(wiki_dir, wiki_config, source_dir=rewrite_dir)

    # Install and apply the pack from folio's templates
    pack_dir = Path(__file__).resolve().parent.parent / "templates" / "packs" / pack_name
    if pack_dir.is_dir():
        try:
            subprocess.run(
                ["sage-wiki", "pack", "install", str(pack_dir)],
                cwd=str(wiki_dir),
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
            )
            subprocess.run(
                ["sage-wiki", "pack", "apply", pack_name, "--mode", "merge"],
                cwd=str(wiki_dir),
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
            )
        except FileNotFoundError:
            logger.warning("sage-wiki binary not found — pack install/apply skipped")
        except subprocess.CalledProcessError as e:
            logger.warning("Failed to install/apply pack %s: %s", pack_name, e.stderr.strip() if e.stderr else str(e))

    if rewrite_dir.is_dir():
        md_files = list(rewrite_dir.glob("*.md"))
        if md_files:
            print(f"  Wiki linked to {len(md_files)} documents in {rewrite_dir}")

    print("  Compiling wiki...")
    backend.compile()
    print("  Wiki compiled successfully")

    compiled_wiki = wiki_dir / "wiki"
    if compiled_wiki.is_dir():
        public_link = Path("wiki")
        if public_link.is_symlink() or public_link.exists():
            public_link.unlink()
        public_link.symlink_to(compiled_wiki, target_is_directory=True)
        print(f"  Wiki output → {public_link}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio wiki",
        description="sage-wiki maintenance and diagnostics commands.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio wiki compile\n"
            "  folio wiki status\n"
            "  folio wiki doctor\n"
            "  folio wiki lint --pass consistency --fix\n"
            "  folio wiki coverage --json\n"
            "  folio wiki diff\n"
            "  folio wiki verify --all\n"
            "  folio wiki verify --since 2025-01-01 --limit 50\n"
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
        help="Preview command without executing",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Maintenance command")

    status_parser = subparsers.add_parser("status", help="Show wiki statistics")
    status_parser.add_argument("--config", "-c", default="folio.yaml", help=argparse.SUPPRESS)

    doctor_parser = subparsers.add_parser("doctor", help="Validate wiki configuration")
    doctor_parser.add_argument("--config", "-c", default="folio.yaml", help=argparse.SUPPRESS)

    lint_parser = subparsers.add_parser("lint", help="Run lint passes against wiki")
    lint_parser.add_argument("--config", "-c", default="folio.yaml", help=argparse.SUPPRESS)
    lint_parser.add_argument(
        "--pass",
        dest="pass_name",
        default=None,
        help="Run a specific lint pass by name",
    )
    lint_parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to auto-fix lint issues",
    )

    coverage_parser = subparsers.add_parser("coverage", help="Show compilation coverage")
    coverage_parser.add_argument("--config", "-c", default="folio.yaml", help=argparse.SUPPRESS)

    diff_parser = subparsers.add_parser("diff", help="Show pending wiki changes")
    diff_parser.add_argument("--config", "-c", default="folio.yaml", help=argparse.SUPPRESS)

    verify_parser = subparsers.add_parser("verify", help="Verify wiki trust/records")
    verify_parser.add_argument("--config", "-c", default="folio.yaml", help=argparse.SUPPRESS)
    verify_parser.add_argument(
        "--all",
        action="store_true",
        help="Verify all records",
    )
    verify_parser.add_argument(
        "--since",
        default=None,
        help="Verify records changed since date (ISO format)",
    )
    verify_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of records to verify",
    )

    compile_parser = subparsers.add_parser("compile", help="(Re)compile the wiki from markdown sources")
    compile_parser.add_argument("--config", "-c", default="folio.yaml", help=argparse.SUPPRESS)

    parsed, remainder = parser.parse_known_args(argv)

    if parsed.subcommand is None:
        parser.print_help(file=sys.stderr)
        sys.exit(1)

    config_path = parsed.config
    if not Path(config_path).exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        print("Run 'folio init' to create one.", file=sys.stderr)
        sys.exit(1)

    config = load_project_config(config_path)
    wiki_dir = Path(config.paths.wiki_project)

    if parsed.dry_run:
        result = {"subcommand": parsed.subcommand, "wiki_dir": str(wiki_dir), "dry_run": True}
        if parsed.subcommand == "lint":
            result["pass_name"] = parsed.pass_name
            result["fix"] = parsed.fix
        elif parsed.subcommand == "verify":
            result["all"] = parsed.all
            result["since"] = parsed.since
            result["limit"] = parsed.limit
        if parsed.json_output:
            print(json.dumps(result, indent=2))
            return
        print(f"Dry run — would execute: sage-wiki {parsed.subcommand}")
        if parsed.subcommand == "compile":
            print(f"  Would compile from: {Path(config.paths.rewrite_md)}")
            print(f"  Wiki dir: {wiki_dir}")
        elif parsed.subcommand == "lint":
            print(f"  --pass: {parsed.pass_name or '(all)'}")
            print(f"  --fix: {parsed.fix}")
        elif parsed.subcommand == "verify":
            print(f"  --all: {parsed.all}")
            print(f"  --since: {parsed.since or '(not set)'}")
            print(f"  --limit: {parsed.limit or '(not set)'}")
        return

    backend = _init_backend(config, wiki_dir)

    if parsed.subcommand == "compile":
        _do_compile(config, wiki_dir, backend)
        return

    if parsed.subcommand == "status":
        output = backend.status()
    elif parsed.subcommand == "doctor":
        output = backend.doctor()
    elif parsed.subcommand == "lint":
        output = backend.lint(pass_name=parsed.pass_name, fix=parsed.fix)
    elif parsed.subcommand == "coverage":
        output = backend.coverage()
    elif parsed.subcommand == "diff":
        output = backend.diff()
    elif parsed.subcommand == "verify":
        output = backend.verify(all=parsed.all, since=parsed.since, limit=parsed.limit)
    else:
        print(f"Unknown subcommand: {parsed.subcommand}", file=sys.stderr)
        sys.exit(1)

    if parsed.json_output:
        try:
            data = json.loads(output)
            print(json.dumps(data, indent=2))
        except (json.JSONDecodeError, TypeError):
            print(json.dumps({"output": output}, indent=2))
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
