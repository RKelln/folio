"""folio clean — deterministic markdown cleanup.

Usage:
    folio clean --source DIR --dest DIR         # Clean all .md files in directory
    folio clean --file FILE.md [--dest OUT.md]  # Clean a single file
    folio clean --source DIR --dry-run          # Preview without writing
    folio clean --json                          # Output as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio import __version__
from folio.config.loader import load_project_config
from folio.core.cleaner import clean_file, clean_markdown


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio clean",
        description="Deterministic markdown cleanup — removes form chrome, "
        "boilerplate, and PDF artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio clean --source raw_md/ --dest clean_md/\n"
            "  folio clean --file doc.md --dest clean/doc.md\n"
            "  folio clean --source raw_md/ --dry-run\n"
            "  folio clean --file doc.md --json\n"
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
        help="Source directory containing .md files",
    )
    parser.add_argument(
        "--dest", "-d",
        type=Path,
        help="Destination directory for cleaned output",
    )
    parser.add_argument(
        "--file", "-f",
        type=Path,
        help="Single .md file to clean (output to stdout unless --dest is set)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview without writing files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output result as JSON",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    if not args.source and not args.file:
        print("Error: --source or --file is required.", file=sys.stderr)
        print("  folio clean --source DIR --dest DIR", file=sys.stderr)
        print("  folio clean --file FILE.md", file=sys.stderr)
        sys.exit(1)

    config_path = args.config
    config = load_project_config(config_path) if Path(config_path).exists() else None

    cleaner_config = config.classification if config and hasattr(config, "classification") else {}
    if not isinstance(cleaner_config, dict):
        cleaner_config = {}

    if args.file:
        src = args.file.resolve()
        if not src.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)

        dest = args.dest.resolve() if args.dest else None

        if args.dry_run:
            content = src.read_text(encoding="utf-8", errors="replace")
            cleaned = clean_markdown(content, cleaner_config)
            result = {
                "source": str(src),
                "orig_chars": len(content),
                "cleaned_chars": len(cleaned),
                "chars_removed": len(content) - len(cleaned),
                "dry_run": True,
            }
            if args.json_output:
                print(json.dumps(result, indent=2))
                return
            print(f"Would clean: {src.name}")
            orig = len(content)
            new = len(cleaned)
            print(f"  {orig} → {new} chars ({orig - new} removed)")
            return

        content = src.read_text(encoding="utf-8", errors="replace")
        cleaned = clean_markdown(content, cleaner_config)

        if dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(cleaned, encoding="utf-8")
            result = {
                "source": str(src),
                "dest": str(dest),
                "orig_chars": len(content),
                "cleaned_chars": len(cleaned),
                "chars_removed": len(content) - len(cleaned),
            }
        else:
            result = {
                "source": str(src),
                "orig_chars": len(content),
                "cleaned_chars": len(cleaned),
                "chars_removed": len(content) - len(cleaned),
                "content": cleaned,
            }

        if args.json_output:
            print(json.dumps(result, indent=2))
            return
        if dest:
            print(f"Cleaned: {src.name} → {dest}")
            orig = len(content)
            new = len(cleaned)
            print(f"  {orig} → {new} chars ({orig - new} removed)")
        else:
            print(cleaned)
        return

    src_dir = args.source.resolve()
    if not src_dir.is_dir():
        print(f"Error: Source directory not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(src_dir.glob("*.md"))
    if not md_files:
        print(f"Error: No .md files found in {args.source}", file=sys.stderr)
        sys.exit(1)

    dest_dir = args.dest.resolve() if args.dest else src_dir

    if args.dry_run:
        total_orig = 0
        total_cleaned = 0
        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8", errors="replace")
            cleaned = clean_markdown(content, cleaner_config)
            total_orig += len(content)
            total_cleaned += len(cleaned)
        result = {
            "files": len(md_files),
            "orig_chars": total_orig,
            "cleaned_chars": total_cleaned,
            "chars_removed": total_orig - total_cleaned,
            "dry_run": True,
        }
        if args.json_output:
            print(json.dumps(result, indent=2))
            return
        print(f"Would clean {len(md_files)} files")
        removed = total_orig - total_cleaned
        print(
            f"  {total_orig:,} → {total_cleaned:,}"
            f" chars ({removed:,} removed)"
        )
        return

    clean_file(src_dir, dest_dir, cleaner_config)

    result = {
        "files": len(md_files),
        "source": str(src_dir),
        "dest": str(dest_dir),
    }
    if args.json_output:
        print(json.dumps(result, indent=2))
        return
    print(f"Cleaned {len(md_files)} files → {dest_dir}")


if __name__ == "__main__":
    main()
