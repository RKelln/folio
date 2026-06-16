"""folio scan — archive scanner.

Scans raw documents, detects funders/years/types, estimates costs.

Usage:
    folio scan --source ./archive/          # Scan a local archive directory
    folio scan --source ./archive/ --json   # Output scan report as JSON
    folio scan --source ./archive/ --output report.json  # Save report to file
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio import __version__
from folio.config.loader import load_project_config
from folio.core.scanner import scan_archive


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio scan",
        description="Scan a raw document archive to detect funders, years, "
        "document types, draft files, and estimate pipeline costs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio scan --source ./archive/\n"
            "  folio scan --source ./archive/ --dry-run\n"
            "  folio scan --source ./archive/ --json\n"
            "  folio scan --source ./archive/ --output scan-report.json\n"
            "  folio scan --source ./archive/ --json | jq .estimated_costs\n"
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
        help="Path to raw archive directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output scan report as JSON",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Save scan report to file (JSON format)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview scan source without running scan",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    source_path = args.source
    if not source_path.is_dir():
        print(f"Error: Source directory not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(f"Would scan {source_path}")
        return

    config_path = args.config
    if args.json_output or args.output:
        config_exists = Path(config_path).exists()
        config = (
            load_project_config(config_path) if config_exists
            else load_project_config(None)
        )
    else:
        if not Path(config_path).exists():
            print(f"Warning: Config file not found: {config_path}", file=sys.stderr)
            print('  Running with default config. Run "folio init" to customize.', file=sys.stderr)
            print(file=sys.stderr)
        config_exists = Path(config_path).exists()
        config = (
            load_project_config(config_path) if config_exists
            else load_project_config(None)
        )

    print(f"Scanning {source_path}...")
    report = scan_archive(str(source_path), config)

    if args.output:
        output_data = dict(report)
        for k, v in output_data.get("by_funder", {}).items():
            if isinstance(v, dict) and "years" in v:
                output_data["by_funder"][k]["years"] = list(v["years"])
        args.output.write_text(json.dumps(output_data, indent=2, default=str), encoding="utf-8")
        print(f"Scan report saved to {args.output}")

    if args.json_output and not args.output:
        output_data = dict(report)
        for k, v in output_data.get("by_funder", {}).items():
            if isinstance(v, dict) and "years" in v:
                output_data["by_funder"][k]["years"] = list(v["years"])
        print(json.dumps(output_data, indent=2, default=str))
        return

    if args.output and not args.json_output:
        pass

    total = report.get("total_files", 0)
    by_ext = report.get("by_extension", {})
    by_funder = report.get("by_funder", {})
    by_year = report.get("by_year", {})
    by_type = report.get("by_type", {})
    est = report.get("estimated_costs", {})

    print(f"\nFiles found: {total}")
    print()

    if by_ext:
        print("By extension:")
        for ext, count in sorted(by_ext.items(), key=lambda x: -x[1]):
            print(f"  {ext or '(none)'}: {count}")
        print()

    if by_funder:
        print("By funder:")
        for abbrev, info in sorted(by_funder.items()):
            years_str = ", ".join(str(y) for y in info.get("years", []))
            print(f"  {abbrev} ({info.get('full_name', abbrev)}): {info.get('count', 0)} files "
                  f"[{years_str}]")
        print()

    if by_year:
        print("By year:")
        for year, count in sorted(by_year.items()):
            print(f"  {year}: {count}")
        print()

    if by_type:
        print("By type:")
        for dtype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"  {dtype}: {count}")
        print()

    unrecognized = report.get("unrecognized", [])
    if unrecognized:
        print(f"Unrecognized files ({len(unrecognized)}):")
        for f in unrecognized[:10]:
            print(f"  {f}")
        if len(unrecognized) > 10:
            print(f"  ... and {len(unrecognized) - 10} more")
        print()

    drafts = report.get("likely_drafts", [])
    if drafts:
        print(f"Likely drafts ({len(drafts)}):")
        for f in drafts[:10]:
            print(f"  {f}")
        if len(drafts) > 10:
            print(f"  ... and {len(drafts) - 10} more")
        print()

    print("Estimated costs:")
    print(f"  Conversion: ${est.get('conversion_usd', 0):.2f}")
    print(f"  LLM rewrite: ${est.get('llm_rewrite_usd', 0):.2f}")
    print(f"  LLM prioritize: ${est.get('llm_prioritize_usd', 0):.2f}")
    print(f"  Wiki compile: ${est.get('wiki_compile_usd', 0):.2f}")
    print(f"  Total: ${est.get('total_usd', 0):.2f}")

    est_time = report.get("estimated_time_minutes", 0)
    if est_time:
        hours = int(est_time // 60)
        mins = int(est_time % 60)
        if hours:
            print(f"  Estimated time: {hours}h {mins}m")
        else:
            print(f"  Estimated time: {mins}m")


if __name__ == "__main__":
    main()
