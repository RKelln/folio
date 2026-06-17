"""folio repack — nested-to-flat migration helper.

Walks a messy nested directory tree and copies (or moves) files to a flat
destination following the folio naming convention.

Usage:
    folio repack --source "./Old Grants/" --dest ./archive/ --dry-run
    folio repack --source ./downloads/ --dest ./archive/ --move
    folio repack --source ./messy/ --dest ./archive/ --funder OAC --year 2023
    folio repack --source ./messy/ --dest ./archive/ --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from folio import __version__
from folio.config.loader import load_project_config
from folio.core.repacker import repack_files

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio repack",
        description=(
            "Reorganize files from a nested directory tree into a flat "
            "archive/ following the folio naming convention: "
            "FUNDER__Year_Description__Type.ext"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  folio repack --source "./Old Grants/" --dest ./archive/ --dry-run\n'
            "  folio repack --source ./downloads/ --dest ./archive/ --move\n"
            "  folio repack --source ./messy/ --dest ./archive/ --funder OAC --year 2023\n"
            "  folio repack --source ./messy/ --dest ./archive/ --type application\n"
            "  folio repack --source ./messy/ --dest ./archive/ --json\n"
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
        help="Source directory tree to walk",
    )
    parser.add_argument(
        "--dest", "-d",
        type=Path,
        default=Path("./archive/"),
        help="Destination directory for repacked files (default: ./archive/)",
    )
    parser.add_argument(
        "--funder",
        type=str,
        help="Override funder abbreviation for all files",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Override year for all files",
    )
    parser.add_argument(
        "--type",
        type=str,
        dest="doc_type",
        help="Override document type for all files",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying (default: copy)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview repack without writing files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    source_dir = args.source
    if not source_dir.is_dir():
        print(f"Error: Source directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    funders: dict[str, str] = {}
    config_path = Path(args.config)
    if config_path.exists():
        try:
            config = load_project_config(config_path)
            funders = config.funders
        except Exception as e:
            logger.warning("Could not load config: %s. Proceeding without funder list.", e)

    if args.dry_run:
        print(f"[dry-run] Would repack files from {source_dir} to {args.dest}")

    result = repack_files(
        source_dir=source_dir,
        dest_dir=args.dest,
        dry_run=args.dry_run,
        move=args.move,
        funders=funders,
        funder_override=args.funder,
        year_override=args.year,
        type_override=args.doc_type,
    )

    if args.json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    items = result["items"]
    total = result["total"]
    needs_review = [i for i in items if i.get("needs_review")]
    confident = total - len(needs_review)
    skipped = result.get("skipped", 0)

    print()
    print(f"Files found: {total}")
    print(f"  Confident: {confident}")
    print(f"  Needs review: {len(needs_review)}")
    if skipped:
        print(f"  Failed: {skipped}")
    print()

    if needs_review:
        print("Needs review (low confidence):")
        for item in needs_review:
            src_name = Path(item["old_path"]).name
            print(
                f"  {src_name} -> {item['suggested_filename']} "
                f"(confidence: {item.get('confidence', '?')})"
            )
        print()

    per_funder: dict[str, int] = {}
    per_type: dict[str, int] = {}
    per_year: dict[int, int] = {}
    for item in items:
        f = item.get("funder") or "UNKNOWN"
        per_funder[f] = per_funder.get(f, 0) + 1
        t = item.get("doc_type") or "unknown"
        per_type[t] = per_type.get(t, 0) + 1
        y = item.get("year")
        if y:
            per_year[y] = per_year.get(y, 0) + 1

    if per_funder:
        print("By funder:")
        for f, count in sorted(per_funder.items()):
            print(f"  {f}: {count}")
        print()

    if per_year:
        print("By year:")
        for y, count in sorted(per_year.items()):
            print(f"  {y}: {count}")
        print()

    if per_type:
        print("By type:")
        for t, count in sorted(per_type.items()):
            print(f"  {t}: {count}")
        print()

    if args.dry_run:
        print("Dry run complete. No files were written.")
        print("Run without --dry-run to execute.")
    elif args.move:
        print(f"Moved {result['success']} files to {args.dest}")
    else:
        print(f"Copied {result['success']} files to {args.dest}")

    if not args.dry_run:
        manifest_path = args.dest / ".folio_repack_manifest.json"
        print(f"Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
