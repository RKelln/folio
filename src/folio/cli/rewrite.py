"""folio rewrite — LLM re-authoring with tiered prompts.

Usage:
    folio rewrite --source DIR                        # Rewrite all files in directory
    folio rewrite --file FILE.md                      # Rewrite a single file
    folio rewrite --source DIR --tier full            # Force tier for all files
    folio rewrite --source DIR --limit 10             # Process first 10 files only
    folio rewrite --source DIR --dry-run              # Estimate without API calls
    folio rewrite --source DIR --json                 # Output summary as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio import __version__
from folio.config.loader import load_project_config
from folio.core.rewriter import rewrite_directory, rewrite_file


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio rewrite",
        description="Re-author markdown files using LLM with tiered prompts "
        "(full/light/minimal) based on content quality.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio rewrite --source clean_md/\n"
            "  folio rewrite --file TAC__2024__application.md --tier full\n"
            "  folio rewrite --source clean_md/ --limit 5\n"
            "  folio rewrite --source clean_md/ --dry-run\n"
            "  folio rewrite --source clean_md/ --json\n"
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
        help="Directory containing .md files to rewrite",
    )
    parser.add_argument(
        "--file", "-f",
        type=Path,
        help="Single .md file to rewrite",
    )
    parser.add_argument(
        "--dest", "-d",
        type=Path,
        help="Destination directory for rewritten output (default: from config)",
    )
    parser.add_argument(
        "--tier",
        choices=["full", "light", "minimal"],
        help="Processing tier (default: auto-detect from manifest or classify)",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        help="Process only the first N files",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Rewrite all files even if already present in manifest",
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
        help="Output rewrite summary as JSON",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Path to manifest.json for tier/status lookup (default: rewrite_md/manifest.json)",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    if not args.source and not args.file:
        print("Error: --source or --file is required.", file=sys.stderr)
        print("  folio rewrite --source DIR", file=sys.stderr)
        print("  folio rewrite --file FILE.md", file=sys.stderr)
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

        tier = args.tier or "full"

        if args.dry_run:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            est_chars = len(content)
            est_tokens = int(est_chars / 3.5)
            result = {
                "filename": fpath.name,
                "tier": tier,
                "estimated_input_tokens": est_tokens,
                "estimated_output_tokens": min(est_tokens, 64000),
                "dry_run": True,
            }
            if args.json_output:
                print(json.dumps(result, indent=2))
                return
            print(f"Would rewrite: {fpath.name}")
            print(f"  Tier: {tier}")
            print(f"  Estimated input: ~{est_tokens:,} tokens")
            return

        result = rewrite_file(fpath, config, tier=tier)

        if args.json_output:
            print(json.dumps({
                "filename": fpath.name,
                "tier": tier,
                "status": result.get("status", "unknown"),
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "cost_usd": result.get("cost_usd", 0),
                "elapsed_seconds": result.get("elapsed_seconds", 0),
                "error": result.get("error"),
            }, indent=2))
            return
        status = result.get("status", "unknown")
        print(f"Rewrite: {fpath.name} → {status}")
        inp = result.get("input_tokens", 0)
        out = result.get("output_tokens", 0)
        print(f"  Tokens: {inp:,} in / {out:,} out")
        print(f"  Cost: ${result.get('cost_usd', 0):.4f}")
        print(f"  Time: {result.get('elapsed_seconds', 0):.1f}s")
        if result.get("error"):
            print(f"  Error: {result['error']}")
        return

    src_dir = args.source.resolve()
    if not src_dir.is_dir():
        print(f"Error: Directory not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(src_dir.glob("*.md"))
    if not md_files:
        print(f"Error: No .md files found in {args.source}", file=sys.stderr)
        sys.exit(1)

    manifest_path = args.manifest
    if not manifest_path:
        output_dir = Path(config.paths.rewrite_md)
        manifest_path = output_dir / "manifest.json"

    if args.dry_run:
        print(f"Would rewrite {len(md_files)} files in {src_dir}")
        print(f"  Tier: {args.tier or 'auto (from manifest/classifier)'}")
        print(f"  Limit: {args.limit or 'all'}")
        total_chars = sum(f.stat().st_size for f in md_files if f.is_file())
        est_tokens = int(total_chars / 3.5)
        est_cost_input = est_tokens / 1_000_000 * config.llm.input_price_per_m
        output_ppm = config.llm.output_price_per_m
        est_cost_output = est_tokens / 1_000_000 * output_ppm
        result = {
            "files": len(args.limit or md_files),
            "total_chars": total_chars,
            "estimated_tokens": est_tokens,
            "estimated_cost_usd": round(est_cost_input + est_cost_output, 2),
            "tier": args.tier or "auto",
            "dry_run": True,
        }
        if args.json_output:
            print(json.dumps(result, indent=2))
            return
        print(f"  Estimated tokens: ~{est_tokens:,}")
        print(f"  Estimated cost: ${est_cost_input + est_cost_output:.2f}")
        return

    summary = rewrite_directory(
        src_dir,
        config,
        manifest_path=manifest_path,
        tier=args.tier,
        limit=args.limit,
        resume=not args.no_resume,
        dry_run=False,
        dest=args.dest,
    )

    if args.json_output:
        print(json.dumps(summary, indent=2, default=str))
        return
    ok = summary.get("success", 0) + summary.get("local_metadata", 0) + summary.get("corrupted", 0)
    failed = summary.get("error", 0) + summary.get("empty", 0)
    total_cost = summary.get("total_cost_usd", 0)
    print(f"Rewrite complete: {ok} ok, {failed} failed")
    print(f"  Total cost: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
