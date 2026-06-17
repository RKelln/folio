"""folio wiki — sage-wiki maintenance commands.

Usage:
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
import sys
from pathlib import Path

from folio import __version__
from folio.adapters.wiki import get_wiki_backend
from folio.config.loader import load_project_config


def _init_backend(config, project_dir: Path):
    backend = get_wiki_backend(config)
    wiki_config = {
        "version": 1,
        "project": getattr(config.org, "name", "folio"),
        "pack": getattr(config.wiki, "sage_wiki_pack", "arts-org"),
        "sources": [{"path": "raw", "type": "auto", "watch": False}],
        "output": "wiki",
    }
    backend.init(project_dir, wiki_config)
    return backend


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio wiki",
        description="sage-wiki maintenance and diagnostics commands.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
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
        if parsed.subcommand == "lint":
            print(f"  --pass: {parsed.pass_name or '(all)'}")
            print(f"  --fix: {parsed.fix}")
        elif parsed.subcommand == "verify":
            print(f"  --all: {parsed.all}")
            print(f"  --since: {parsed.since or '(not set)'}")
            print(f"  --limit: {parsed.limit or '(not set)'}")
        return

    backend = _init_backend(config, wiki_dir)

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
