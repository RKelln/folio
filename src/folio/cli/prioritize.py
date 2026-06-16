"""folio prioritize — archival priority scoring.

Usage:
    folio prioritize --source DIR               # Score all files grouped by year
    folio prioritize --file FILE.md             # Score a single file
    folio prioritize --source DIR --year 2024   # Process a specific year only
    folio prioritize --source DIR --limit 5     # Process first 5 groups
    folio prioritize --source DIR --dry-run     # Preview without API calls
    folio prioritize --source DIR --json        # Output summary as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio import __version__
from folio.config.loader import load_project_config
from folio.core.prioritizer import prioritize_directory, prioritize_file


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio prioritize",
        description="Score archival priority (1-3) for grant documents using "
        "LLM comparison within year groups.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio prioritize --source rewrite_md/\n"
            "  folio prioritize --file TAC__2024__application.md\n"
            "  folio prioritize --source rewrite_md/ --year 2024\n"
            "  folio prioritize --source rewrite_md/ --dry-run\n"
            "  folio prioritize --source rewrite_md/ --json\n"
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
        help="Directory containing rewritten .md files",
    )
    parser.add_argument(
        "--file", "-f",
        type=Path,
        help="Single .md file to prioritize",
    )
    parser.add_argument(
        "--year", "-y",
        type=int,
        help="Process only files from a specific year group",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        help="Process only the first N groups",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview file list and estimated costs without API calls",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output priority scoring summary as JSON",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Score all files even if already present in manifest",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    if not args.source and not args.file:
        print("Error: --source or --file is required.", file=sys.stderr)
        print("  folio prioritize --source DIR", file=sys.stderr)
        print("  folio prioritize --file FILE.md", file=sys.stderr)
        sys.exit(1)

    config_path = args.config
    if not Path(config_path).exists():
        print("folio.yaml not found. This command requires configuration. Run 'folio init' first.", file=sys.stderr)
        sys.exit(1)

    config = load_project_config(config_path)

    if args.file:
        fpath = args.file.resolve()
        if not fpath.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)

        if args.dry_run:
            result = {
                "filename": fpath.name,
                "dry_run": True,
            }
            if args.json_output:
                print(json.dumps(result, indent=2))
                return
            print(f"Would prioritize: {fpath.name}")
            return

        result = prioritize_file(fpath, config)

        if args.json_output:
            output = {
                "filename": fpath.name,
                "priority": result.get("priority"),
                "rationale": result.get("rationale", ""),
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "elapsed_seconds": result.get("elapsed_seconds", 0),
                "errors": result.get("errors", []),
            }
            print(json.dumps(output, indent=2))
            return
        print(f"Priority: {fpath.name}")
        print(f"  Score: {result.get('priority', 'N/A')}")
        if result.get("rationale"):
            print(f"  Rationale: {result['rationale'][:200]}")
        if result.get("errors"):
            for e in result["errors"]:
                print(f"  Error: {e}")
        return

    src_dir = args.source.resolve()
    if not src_dir.is_dir():
        print(f"Error: Directory not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(src_dir.glob("*.md"))
    if not md_files:
        print(f"Error: No .md files found in {args.source}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(f"Would prioritize {len(md_files)} files in {src_dir}")
        if args.year:
            print(f"  Year filter: {args.year}")
        if args.limit:
            print(f"  Limit: {args.limit} groups")
        try:
            total_chars = sum(f.stat().st_size for f in md_files if f.is_file())
            est_tokens = int(total_chars / 3.5)
            input_ppm = config.llm.input_price_per_m
            output_ppm = config.llm.output_price_per_m
            est_cost = est_tokens / 1_000_000 * input_ppm + est_tokens / 1_000_000 * output_ppm
        except (AttributeError, KeyError):
            est_cost = len(md_files) * 0.002
        print(f"  Estimated cost: ~${est_cost:.2f}")
        return

    result = prioritize_directory(
        src_dir,
        config,
        dry_run=False,
        year=args.year,
        limit=args.limit,
        resume=not args.no_resume,
    )

    if args.json_output:
        print(json.dumps(result, indent=2, default=str))
        return
    ok = result.get("ok", result.get("files", 0))
    print(f"Prioritization complete: {ok} files scored")
    if result.get("total_cost_usd"):
        print(f"  Total cost: ${result['total_cost_usd']:.4f}")


if __name__ == "__main__":
    main()
