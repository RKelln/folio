"""folio ingest — one-off document ingestion.

Usage:
    folio ingest --source FILE --funder ABBREV --year 2024
    folio ingest --source FILE --funder ABBREV --year 2024 --doc-types application,report
    folio ingest --source FILE --funder ABBREV --year 2024 --description "My Description"
    folio ingest --source FILE --funder ABBREV --year 2024 --dry-run
    folio ingest --source FILE --funder ABBREV --year 2024 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio import __version__
from folio.config.loader import load_project_config
from folio.core.ingester import ingest_document


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio ingest",
        description="Convert a single PDF/DOCX/XLSX to markdown, apply cleanup, "
        "add frontmatter, and sync to the wiki.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  folio ingest --source grant.pdf --funder TAC --year 2024\n'
            "  folio ingest --source report.docx --funder OAC"
            " --year 2025 --doc-types report,budget\n"
            '  folio ingest --source doc.xlsx --funder CCA --year 2024 --no-wiki\n'
            '  folio ingest --source grant.pdf --funder TAC --year 2024 --dry-run\n'
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
        help="Path to source document (PDF, DOCX, or XLSX)",
    )
    parser.add_argument(
        "--funder",
        required=True,
        help="Funder abbreviation (e.g. TAC, OAC, CCA)",
    )
    parser.add_argument(
        "--year", "-y",
        type=int,
        required=True,
        help="Year the document was written or submitted",
    )
    parser.add_argument(
        "--period",
        help="Grant period (e.g. '2024-2025')",
    )
    parser.add_argument(
        "--doc-types",
        default="application",
        help="Comma-separated document types (default: application)",
    )
    parser.add_argument(
        "--description", "-d",
        help="Optional description for the output filename",
    )
    parser.add_argument(
        "--rewrite",
        action="store_true",
        help="Run LLM rewrite on the output",
    )
    parser.add_argument(
        "--no-wiki",
        action="store_true",
        help="Skip syncing output to the wiki raw directory",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview ingestion without writing files or calling APIs",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output ingestion result as JSON",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    source_path = args.source.resolve()
    if not source_path.exists():
        print(f"Error: Source file not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    config_path = args.config
    if not Path(config_path).exists():
        print("folio.yaml not found. This command requires configuration. Run 'folio init' first.", file=sys.stderr)
        sys.exit(1)

    config = load_project_config(config_path)

    doc_types = [t.strip() for t in args.doc_types.split(",") if t.strip()]

    result = ingest_document(
        source_path=source_path,
        config=config,
        funder=args.funder,
        year=args.year,
        period=args.period,
        doc_types=doc_types,
        description=args.description,
        run_rewrite=args.rewrite,
        sync_wiki=not args.no_wiki,
        dry_run=args.dry_run,
    )

    if args.json_output:
        json_result = {
            "status": result.get("status"),
            "filename": result.get("filename"),
            "output_path": str(result["output_path"]) if result.get("output_path") else None,
            "wiki_status": result.get("wiki_status"),
            "frontmatter_added": result.get("frontmatter_added", False),
            "chars": result.get("chars", 0),
            "warnings": result.get("warnings", []),
            "error": result.get("error"),
            "dry_run": args.dry_run,
        }
        print(json.dumps(json_result, indent=2, default=str))
        return

    status = result.get("status", "unknown")
    if status == "error":
        print(f"Ingest failed: {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)

    print(f"Ingest: {result['status']}")
    if result.get("filename"):
        print(f"  Output: {result['filename']}")
    if result.get("chars"):
        print(f"  Size: {result['chars']:,} chars")
    if result.get("frontmatter_added"):
        print("  Frontmatter: added")
    if result.get("wiki_status"):
        print(f"  Wiki: {result['wiki_status']}")
    for w in result.get("warnings", []):
        print(f"  Warning: {w}")


if __name__ == "__main__":
    main()
