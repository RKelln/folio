"""folio convert — convert PDF/DOCX files to Markdown.

Usage:
    folio convert --source ./archive/ --dest ./out/
    folio convert --source ./archive/ --dest ./out/ --dry-run
    folio convert --source ./archive/ --dest ./out/ --converter liteparse
    folio convert --source ./archive/ --dest ./out/ --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio import __version__
from folio.adapters.converters import get_converter


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio convert",
        description="Convert PDF/DOCX files to Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio convert --source ./archive/ --dest ./.folio/converted/\n"
            "  folio convert --source ./archive/ --dest ./out/ --converter liteparse --dry-run\n"
            "  folio convert --source ./archive/ --dest ./out/ --json\n"
        ),
    )

    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )
    parser.add_argument(
        "--source", "-s",
        type=Path,
        required=True,
        help="Directory containing source files (PDF, DOCX, etc.)",
    )
    parser.add_argument(
        "--dest", "-d",
        type=Path,
        required=True,
        help="Directory for converted Markdown files",
    )
    parser.add_argument(
        "--converter",
        type=str,
        default="liteparse",
        choices=["liteparse", "docling", "datalab", "marker", "pandoc", "cascade"],
        help=(
            "Converter to use: liteparse | docling | datalab | marker | pandoc | "
            "cascade (default: liteparse). 'cascade' is config-driven and must be "
            "set up in folio.yaml — see below."
        ),
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview files to convert without processing",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output result as JSON",
    )

    args = parser.parse_args(argv)

    source = args.source.resolve()
    if not source.is_dir():
        print(f"Error: Source directory not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    dest = args.dest.resolve()

    if args.converter == "cascade":
        print(
            "Error: --converter cascade is config-driven and cannot be built "
            "from the CLI flag alone (it needs an ordered tier list).\n"
            "  Set 'converter.type: cascade' and 'converter.cascade: [...]' in "
            "folio.yaml, then run 'folio pipeline' (which reads config).\n"
            "  The standalone 'folio convert' command only supports single "
            "converters.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        converter = get_converter(args.converter)
    except NotImplementedError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    exts = {ext.lower() for ext in converter.supported_extensions}
    files = sorted(
        f for f in source.iterdir()
        if f.is_file() and f.suffix.lower() in exts
    )

    if not files:
        print(f"No convertible files found in {source}", file=sys.stderr)
        print(f"  Supported extensions: {', '.join(sorted(exts))}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        result = {
            "files": len(files),
            "source": str(source),
            "dest": str(dest),
            "dry_run": True,
            "converter": converter.name,
            "supported_extensions": sorted(exts),
        }
        if args.json_output:
            print(json.dumps(result, indent=2))
            return
        print(f"Would convert {len(files)} files from {source} to {dest} using {converter.name}")
        for f in files:
            print(f"  {f.name}")
        return

    dest.mkdir(parents=True, exist_ok=True)

    success = 0
    failed = 0
    errors: list[str] = []

    for f in files:
        try:
            result = converter.convert_traced(f)
            if result.markdown:
                out_path = dest / (f.stem + ".md")
                out_path.write_text(result.markdown, encoding="utf-8")
                success += 1
                if not args.json_output:
                    print(f"  {f.name} \u2192 {result.tier}")
            else:
                failed += 1
                errors.append(f"{f.name}: converter returned empty result")
        except Exception as exc:
            failed += 1
            errors.append(f"{f.name}: {exc}")

    result = {
        "success": success,
        "failed": failed,
        "errors": errors[:20],
        "source": str(source),
        "dest": str(dest),
        "converter": converter.name,
    }

    if args.json_output:
        print(json.dumps(result, indent=2))
        if failed:
            sys.exit(1)
        return

    print(f"Converted {success} of {len(files)} files using {converter.name}.")
    if failed:
        print(f"Failed: {', '.join(errors[:5])}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more. Use --json for full details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
