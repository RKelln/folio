"""folio canonicalize — version detection and dedup.

Usage:
    folio canonicalize --source DIR                # Analyze and filter canonical files
    folio canonicalize --source DIR --archive-dir DIR  # Move non-canonical to archive
    folio canonicalize --source DIR --llm           # Use LLM for ambiguous resolution
    folio canonicalize --source DIR --dry-run       # Preview without moving files
    folio canonicalize --source DIR --json          # Output result as JSON
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from pathlib import Path

from folio import __version__
from folio.config.loader import load_project_config
from folio.core.canonicalizer import DEFAULT_CANONICALIZE_CONFIG, canonicalize_directory

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio canonicalize",
        description="Detect draft files, resolve submission versions, and "
        "deduplicate near-duplicates in a directory of markdown grant documents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio canonicalize --source clean_md/\n"
            "  folio canonicalize --source clean_md/ --archive-dir .folio/non_canonical/\n"
            "  folio canonicalize --source clean_md/ --llm\n"
            "  folio canonicalize --source clean_md/ --dry-run\n"
            "  folio canonicalize --source clean_md/ --json\n"
        ),
    )

    parser.add_argument(
        "--config", "-c",
        default="folio.yaml",
        help="Path to folio.yaml (default: folio.yaml)",
    )
    parser.add_argument(
        "--source", "-s",
        type=Path,
        required=True,
        help="Directory containing .md files to canonicalize",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        help="Directory to move non-canonical files into (instead of deleting)",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        dest="use_llm",
        help="Use LLM for ambiguous cross-submission resolution",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview canonicalization without moving files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output canonicalization result as JSON",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    src_dir = args.source.resolve()
    if not src_dir.is_dir():
        print(f"Error: Directory not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(src_dir.glob("*.md"))
    if not md_files:
        print(f"Error: No .md files found in {args.source}", file=sys.stderr)
        sys.exit(1)

    config_path = args.config
    if not Path(config_path).exists():
        logger.warning("folio.yaml not found. Using defaults.")
    config = load_project_config(config_path) if Path(config_path).exists() else None

    canon_config = dict(DEFAULT_CANONICALIZE_CONFIG)

    archive_dir = args.archive_dir.resolve() if args.archive_dir else None

    llm_provider = None
    if args.use_llm and config:
        from folio.adapters.llm import get_llm_provider
        try:
            llm_provider = get_llm_provider(config)
        except (ValueError, ImportError, RuntimeError) as exc:
            print(f"Warning: Could not create LLM provider: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            print("  Falling back to heuristic-only mode.", file=sys.stderr)
            args.use_llm = False

    if args.dry_run:
        print(f"Would canonicalize {len(md_files)} files in {src_dir}")
        if args.use_llm:
            print("  LLM resolution: enabled")
        if archive_dir:
            print(f"  Archive dir: {archive_dir}")
        result = canonicalize_directory(
            src_dir, canon_config,
            archive_dir=None,
            dry_run=True,
            use_llm=False,
        )
        canonical = sum(1 for v in result.values() if v["status"] == "canonical")
        non_canonical = sum(1 for v in result.values() if v["status"] == "non_canonical")
        if args.json_output:
            print(json.dumps({
                "files": len(result),
                "canonical": canonical,
                "non_canonical": non_canonical,
                "details": {
                    k: v
                    for k, v in sorted(result.items())
                    if v["status"] == "non_canonical"
                },
                "dry_run": True,
            }, indent=2))
            return
        print(f"  Result: {canonical} canonical, {non_canonical} non-canonical")
        for fname, info in sorted(result.items()):
            if info["status"] == "non_canonical":
                print(f"    {fname}: {info['reason']}")
        return

    result = canonicalize_directory(
        src_dir, canon_config,
        archive_dir=archive_dir,
        dry_run=False,
        use_llm=args.use_llm,
        llm_provider=llm_provider,
    )

    canonical = sum(1 for v in result.values() if v["status"] == "canonical")
    non_canonical = sum(1 for v in result.values() if v["status"] == "non_canonical")

    if args.json_output:
        print(json.dumps({
            "files": len(result),
            "canonical": canonical,
            "non_canonical": non_canonical,
        }, indent=2))
        return
    print(f"Canonicalization complete: {canonical} canonical, {non_canonical} non-canonical")
    if archive_dir and non_canonical:
        print(f"  Non-canonical files moved to: {archive_dir}")


if __name__ == "__main__":
    main()
