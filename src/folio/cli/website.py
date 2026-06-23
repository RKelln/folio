"""folio website — ingest pre-scraped website markdown into the document pipeline.

Usage:
    folio website --source ./pages/
    folio website --source page.md --name about-us
    folio website --source ./pages/ --stages clean,classify
    folio website --source ./pages/ --stages none
    folio website --source ./pages/ --dry-run
    folio website --source ./pages/ --json
    folio website --source ./pages/ --list
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from folio import __version__
from folio.config.loader import load_config_or_exit
from folio.core.website import (
    WEBSITE_STAGES,
    _slug_from_url,
    discover_website_files,
    ingest_website,
    parse_scraper_header,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio website",
        description="Ingest pre-scraped website markdown into the document pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio website --source ./ia_pages/\n"
            "  folio website --source page.md --name about-us\n"
            "  folio website --source ./pages/ --stages clean,classify\n"
            "  folio website --source ./pages/ --stages none\n"
            "  folio website --source ./pages/ --dry-run\n"
            "  folio website --source ./pages/ --list\n"
            "  folio website --source ./pages/ --json\n"
        ),
    )

    parser.add_argument(
        "--config", "-c",
        default="folio.yaml",
        type=Path,
        help="Path to folio.yaml (default: folio.yaml)",
    )
    parser.add_argument(
        "--source", "-s",
        type=Path,
        required=True,
        help="Single .md file or directory containing scraped pages",
    )
    parser.add_argument(
        "--name",
        help="Override filename slug (single-file mode only)",
    )
    parser.add_argument(
        "--stages",
        help=(
            "Comma-separated pipeline stages to run. "
            "Default: clean,canonicalize,classify,rewrite,prioritize,wiki. "
            'Use "none" to skip pipeline entirely.'
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Preview files and metadata, no side effects",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview staging and cost estimates without writing files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as structured JSON",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    source_path = args.source.resolve() if args.source else None
    if source_path is None or not source_path.exists():
        print(f"Error: Source not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    if not source_path.is_file() and not source_path.is_dir():
        print(f"Error: Source must be a file or directory: {args.source}", file=sys.stderr)
        sys.exit(1)

    if args.name and source_path.is_dir():
        print("Warning: --name is ignored in directory mode (using URL slug per file)", file=sys.stderr)

    if args.list:
        _do_list(source_path, args.name if source_path.is_file() else None)
        return

    config_path = args.config
    config = load_config_or_exit(config_path)

    stages = _parse_stages(args.stages)

    result = ingest_website(
        source=source_path,
        config=config,
        config_path=config_path,
        name=args.name if source_path.is_file() else None,
        stages=stages,
        dry_run=args.dry_run,
    )

    if args.json_output:
        _print_json(result)
        return

    _print_human(result, args.dry_run, config=config, stages=stages)


def _parse_stages(stages_str: str | None) -> list[str] | None:
    """Parse --stages flag into a validated list of stage names.

    Returns:
        None for default (all 6 stages).
        Empty list for skip pipeline (--stages none).
        List of stage names otherwise.
    """
    if stages_str is None:
        return None

    if stages_str.strip().lower() == "none":
        return []

    names = [s.strip() for s in stages_str.split(",") if s.strip()]
    for name in names:
        if name not in WEBSITE_STAGES:
            print(
                f"Error: Unknown stage '{name}'. "
                f"Valid stages: {', '.join(WEBSITE_STAGES)}",
                file=sys.stderr,
            )
            sys.exit(1)

    return names


def _do_list(source: Path, name_hint: str | None = None) -> None:
    """Print JSON array of file metadata (--list mode)."""
    files = discover_website_files(source)
    results = []
    for f in files:
        entry: dict = {
            "source_file": str(f),
            "source_url": None,
            "scraped_at": None,
            "url_slug": None,
            "would_stage": False,
            "error": None,
        }
        try:
            content = f.read_text(encoding='utf-8', errors='replace')
            header = parse_scraper_header(content)
            if header is None:
                entry["error"] = "No scraper comment found"
            else:
                entry["source_url"] = header["url"]
                entry["scraped_at"] = header["scraped_at"]
                if name_hint:
                    slug = name_hint
                    slug = re.sub(r'[^a-zA-Z0-9]', '_', slug)
                    while '__' in slug:
                        slug = slug.replace('__', '_')
                    slug = slug.strip('_') or 'webpage'
                    entry["url_slug"] = slug
                else:
                    entry["url_slug"] = _slug_from_url(header["url"])
                entry["would_stage"] = True
        except OSError as exc:
            entry["error"] = f"Cannot read file: {exc}"
        results.append(entry)

    print(json.dumps(results, indent=2, default=str))


def _print_json(result: dict) -> None:
    """Print result dict as JSON."""
    serializable = {
        "status": result.get("status"),
        "source_dir": result.get("source_dir"),
        "staging": {
            "files_found": result["staging"]["files_found"],
            "files_staged": result["staging"]["files_staged"],
            "files_skipped": result["staging"]["files_skipped"],
            "errors": result["staging"]["errors"],
            "results": [
                {
                    "file": r["source_file"],
                    "status": r["status"],
                    "output_path": r.get("output_path"),
                    "error": r.get("error"),
                }
                for r in result["staging"].get("staging_results", [])
            ],
        },
        "pipeline": result.get("pipeline"),
    }
    if result.get("warning"):
        serializable["warning"] = result["warning"]
    print(json.dumps(serializable, indent=2, default=str))


def _print_human(result: dict, dry_run: bool, config=None, stages: list[str] | None = None) -> None:
    """Print human-readable summary."""
    staging = result["staging"]
    org_name = config.org.name if config else "folio"

    print(f"folio website — {org_name}")
    print(f"Source: {result.get('source_dir', '?')}")
    print(f"Files found: {staging['files_found']}")
    print(f"Files staged: {staging['files_staged']}")
    if staging['files_skipped'] > 0:
        print(f"Files skipped: {staging['files_skipped']} (missing scraper metadata)")
    if staging.get("errors"):
        for err in staging["errors"]:
            print(f"  Error: {err['file']}: {err['error']}", file=sys.stderr)

    if staging['files_found'] == 0:
        print("Warning: No .md files found")
        return

    pipeline = result.get("pipeline")
    if pipeline is None:
        if dry_run:
            if stages is None:
                stages_to_show = WEBSITE_STAGES
            elif len(stages) == 0:
                stages_to_show = []
            else:
                stages_to_show = stages
            if stages_to_show:
                print("---")
                print(f"Pipeline stages would run: {', '.join(stages_to_show)}")
        return

    print("---")
    pstages = pipeline.get("stages", {})
    total = len(pstages)
    for i, (stage_name, stage_data) in enumerate(pstages.items()):
        num = i + 1
        status = stage_data.get("status", "?")
        elapsed = stage_data.get("time_seconds", 0)

        if status == "ok":
            files = stage_data.get("files", stage_data.get("converted", 0))
            cost = stage_data.get("cost_usd", 0)
            line = f"Stage {num}/{total}: {stage_name} — {files} files"
            if elapsed >= 0.5:
                line += f" ({elapsed:.1f}s)"
            elif elapsed > 0:
                line += f" ({elapsed * 1000:.0f}ms)"
            if cost > 0:
                line += f" (${cost:.2f})"
            print(line)
        elif status == "skipped":
            print(f"Stage {num}/{total}: {stage_name} — skipped")
        elif status == "warning":
            print(f"Stage {num}/{total}: {stage_name} — warning: {stage_data.get('warning', '')}")
        else:
            print(f"Stage {num}/{total}: {stage_name} — error: {stage_data.get('error', 'Unknown error')}")

    total_cost = pipeline.get("total_cost_usd", 0)
    total_time = pipeline.get("total_time_seconds", 0)
    print(f"  Total cost: ${total_cost:.2f}")
    if total_time >= 60:
        print(f"  Total time: {total_time / 60:.1f}m")
    else:
        print(f"  Total time: {total_time:.1f}s")


if __name__ == "__main__":
    main()
