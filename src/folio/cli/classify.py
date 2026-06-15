"""folio classify — file quality scoring and tier assignment.

Usage:
    folio classify --source DIR          # Classify all .md files in directory
    folio classify --file FILE.md        # Classify a single file
    folio classify --source DIR --json   # Output manifest as JSON
    folio classify --source DIR --dry-run  # Preview without writing manifest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio.config.loader import load_project_config
from folio.core.classifier import DEFAULT_CLASSIFY_CONFIG, classify_directory, classify_file


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio classify",
        description="Score and tier markdown files based on content quality, "
        "form chrome, corruption, and organization-specific rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio classify --source clean_md/\n"
            "  folio classify --file TAC__2024__application.md\n"
            "  folio classify --source clean_md/ --json\n"
            "  folio classify --source clean_md/ --dry-run\n"
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
        help="Directory containing .md files to classify",
    )
    parser.add_argument(
        "--file", "-f",
        type=Path,
        help="Single .md file to classify",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview classification without writing manifest",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output classification result as JSON",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Path to write manifest.json (default: DIR/manifest.json)",
    )

    args = parser.parse_args(argv)

    if not args.source and not args.file:
        print("Error: --source or --file is required.", file=sys.stderr)
        print("  folio classify --source DIR", file=sys.stderr)
        print("  folio classify --file FILE.md", file=sys.stderr)
        sys.exit(1)

    config_path = args.config
    config = None
    if Path(config_path).exists():
        config = load_project_config(config_path)

    classify_config = dict(DEFAULT_CLASSIFY_CONFIG)
    if config:
        classify_config["funders"] = config.funders
        if config.classification:
            for key in ("doc_types", "form_chrome", "draft_markers", "corruption",
                         "thresholds", "skip_rules", "tier_rules", "word_count_pattern"):
                if key in config.classification:
                    classify_config[key] = config.classification[key]
        if config.doc_types and "doc_types" not in classify_config:
            classify_config["doc_types"] = {dt: [r'(?i)\b' + dt + r'\b'] for dt in config.doc_types}

    if args.file:
        fpath = args.file.resolve()
        if not fpath.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)

        result = classify_file(fpath, classify_config)

        tier_val = result["tier"].value if hasattr(result["tier"], "value") else str(result["tier"])
        if hasattr(result["status"], "value"):
            status_val = result["status"].value
        else:
            status_val = str(result["status"])

        output = {
            "filename": fpath.name,
            "tier": tier_val,
            "status": status_val,
            "funder": result.get("funder", "unknown"),
            "year": result.get("year"),
            "doc_types": result.get("doc_types", []),
            "reason": result.get("reason", ""),
            "corruption_score": result.get("corruption_score", 0.0),
            "content_lines": result.get("content_lines", 0),
        }

        if args.json_output:
            print(json.dumps(output, indent=2))
            return
        print(f"File: {fpath.name}")
        print(f"  Tier: {tier_val}")
        print(f"  Status: {status_val}")
        print(f"  Funder: {result.get('funder', 'unknown')}")
        print(f"  Year: {result.get('year', 'unknown')}")
        print(f"  Doc types: {', '.join(result.get('doc_types', []))}")
        print(f"  Corruption: {result.get('corruption_score', 0.0):.2f}")
        print(f"  Content lines: {result.get('content_lines', 0)}")
        if result.get("reason"):
            print(f"  Reason: {result['reason']}")
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
        print(f"Would classify {len(md_files)} files in {src_dir}")
        print(f"  Using {len(classify_config.get('skip_rules', []))} skip rules, "
              f"{len(classify_config.get('tier_rules', []))} tier rules")
        for fpath in md_files:
            result = classify_file(fpath, classify_config)
            if hasattr(result["tier"], "value"):
                tier_val = result["tier"].value
            else:
                tier_val = str(result["tier"])
            print(f"  {fpath.name}: {tier_val}")
        return

    manifest = classify_directory(src_dir, classify_config)
    summary = manifest.get("summary", {})

    manifest_path = args.manifest.resolve() if args.manifest else src_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    result = {
        "files": summary.get("total_files", len(md_files)),
        "by_tier": summary.get("by_tier", {}),
        "by_status": summary.get("by_status", {}),
        "by_funder": summary.get("by_funder", {}),
        "manifest_path": str(manifest_path),
    }

    if args.json_output:
        print(json.dumps(result, indent=2))
        return
    print(f"Classified {result['files']} files → {manifest_path}")
    if result["by_tier"]:
        tier_str = ", ".join(f"{t}={c}" for t, c in sorted(result["by_tier"].items()))
        print(f"  Tiers: {tier_str}")
    if result["by_status"]:
        status_str = ", ".join(f"{s}={c}" for s, c in sorted(result["by_status"].items()))
        print(f"  Status: {status_str}")
    if result["by_funder"]:
        funder_str = ", ".join(f"{f}={c}" for f, c in sorted(result["by_funder"].items())[:10])
        print(f"  Funders: {funder_str}")


if __name__ == "__main__":
    main()
