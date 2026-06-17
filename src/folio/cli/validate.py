"""folio validate — deterministic file quality validation.

Usage:
    folio validate --source ./markdown/              # Validate all files
    folio validate --source ./markdown/ --sample 10  # Random sample of 10
    folio validate --source ./markdown/ --tier full   # Only full-tier files
    folio validate --source ./markdown/ --all         # All checks, verbose
    folio validate --source ./markdown/ --json        # JSON output
    folio validate --source ./markdown/ --approve FILE  # Mark file as validated
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from folio import __version__
from folio.config.loader import load_project_config
from folio.core.manifest import load_manifest, save_manifest, update_file
from folio.core.validator import validate_directory, validate_file

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio validate",
        description="Validate markdown files for frontmatter, content quality, "
        "file size, headings, and placeholders. No LLM calls.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio validate --source ./markdown/\n"
            "  folio validate --source ./markdown/ --sample 10\n"
            "  folio validate --source ./markdown/ --tier full\n"
            "  folio validate --source ./markdown/ --all\n"
            "  folio validate --source ./markdown/ --approve OAC__2024_App__Final.md\n"
            "  folio validate --source ./markdown/ --json | jq .\n"
        ),
    )

    parser.add_argument(
        "--config", "-c",
        default="folio.yaml",
        help="Path to folio.yaml (default: folio.yaml)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Directory containing markdown files to validate",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Randomly sample N files from the directory",
    )
    parser.add_argument(
        "--tier",
        choices=["full", "light", "minimal"],
        default=None,
        help="Only validate files matching this processing tier (requires manifest)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_verbose",
        help="Show all issues per file (verbose output)",
    )
    parser.add_argument(
        "--approve",
        type=str,
        default=None,
        dest="approve_file",
        help="Mark a specific file as validated in the manifest",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output validation results as JSON",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview what would be validated without running checks",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    source = args.source.resolve()
    if not source.is_dir():
        print(f"Error: Source directory not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(source.glob("*.md"))

    if args.dry_run:
        checks = [
            "frontmatter",
            "content_quality",
            "file_size",
            "headings_compliance",
            "placeholders",
        ]
        result = {
            "source": str(source),
            "files": len(md_files),
            "checks": checks,
            "sample": args.sample,
            "tier": args.tier,
            "dry_run": True,
        }
        if args.json_output:
            print(json.dumps(result, indent=2))
            return
        print(f"Source: {source}")
        print(f"Markdown files found: {len(md_files)}")
        if args.sample and args.sample < len(md_files):
            print(f"Would sample: {args.sample}")
        if args.tier:
            print(f"Would filter by tier: {args.tier}")
        print(f"Would check: {', '.join(checks)}.")
        print("Add --json for machine output.")
        return

    config_path = args.config
    config = None
    if Path(config_path).exists():
        config = load_project_config(config_path)
    else:
        logger.warning("folio.yaml not found. Using built-in defaults.")
        config = load_project_config(None)

    if args.approve_file:
        if not Path(config_path).exists():
            print("Error: --approve requires a folio.yaml config", file=sys.stderr)
            sys.exit(1)
        manifest_path = source.parent / ".folio" / "manifest.json"
        manifest = load_manifest(manifest_path)
        update_file(manifest, args.approve_file, validated=True, validation_errors=[])
        save_manifest(manifest, manifest_path)
        print(f"Marked '{args.approve_file}' as validated in manifest.")
        return

    if args.all_verbose:
        for fpath in md_files:
            result = validate_file(fpath, config)
            status = "PASS" if not result["issues"] else f"{len(result['issues'])} issues"
            print(f"\n── {fpath.name} ({status})")
            if result["issues"]:
                for issue in result["issues"]:
                    itype = issue.get("issue_type", "?")
                    msg = issue.get("message", str(issue))
                    print(f"   [{itype}] {msg}")
        return

    result = validate_directory(
        source,
        config,
        sample=args.sample,
        tier=args.tier,
    )

    if args.json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    print(f"Source: {result['source_dir']}")
    print(f"Files scanned: {result['files_scanned']}")
    print(f"Files passing: {result['files_passing']}")
    print(f"Files with issues: {result['files_with_issues']}")
    print()

    validations = result.get("validations", {})
    if not validations:
        print("No issues found.")
        return

    for issue_type in sorted(validations):
        items = validations[issue_type]
        print(f"{issue_type} ({len(items)}):")
        for item in items[:10]:
            fname = item.get("file", "?")
            msg = item.get("message", str(item))
            print(f"  {fname}: {msg}")
        if len(items) > 10:
            print(f"  ... and {len(items) - 10} more")
        print()

    summary = result.get("summary", "")
    if summary:
        print(f"Summary: {summary}")


if __name__ == "__main__":
    main()
