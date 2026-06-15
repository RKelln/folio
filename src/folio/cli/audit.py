"""folio audit — wiki quality audit.

Usage:
    folio audit --wiki-dir DIR                # Audit a compiled wiki
    folio audit --wiki-dir DIR --json         # Output findings as JSON
    folio audit --wiki-dir DIR --section Body  # Check for a specific required section
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio.config.loader import load_project_config
from folio.core.auditor import audit_wiki


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio audit",
        description="Scan a compiled wiki for cleanup candidates: dead links, "
        "thin articles, near-duplicates, missing sections, stale content.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio audit --wiki-dir wiki/\n"
            "  folio audit --wiki-dir wiki/ --json\n"
            "  folio audit --wiki-dir sage_wiki_3/ --json | jq .\n"
        ),
    )

    parser.add_argument(
        "--config", "-c",
        default="folio.yaml",
        help="Path to folio.yaml (default: folio.yaml)",
    )
    parser.add_argument(
        "--wiki-dir",
        type=Path,
        required=True,
        help="Path to compiled wiki directory (containing wiki/concepts/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output audit findings as JSON",
    )
    parser.add_argument(
        "--section",
        action="append",
        dest="required_sections",
        help="Required section to check for (may be specified multiple times)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview what would be audited without running audit",
    )

    args = parser.parse_args(argv)

    wiki_dir = args.wiki_dir.resolve()
    if not wiki_dir.is_dir():
        print(f"Error: Wiki directory not found: {args.wiki_dir}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        md_files = sorted(wiki_dir.rglob("*.md"))
        print(f"Would audit wiki at {wiki_dir}")
        print(f"  Would scan {len(md_files)} .md files")
        return

    config_path = args.config
    audit_cfg = None
    if Path(config_path).exists():
        config = load_project_config(config_path)
        if config.audit:
            audit_cfg = getattr(config, "audit", None)
            if isinstance(audit_cfg, dict):
                pass
            else:
                audit_cfg = None

    if args.required_sections:
        if audit_cfg is None:
            audit_cfg = {}
        audit_cfg["required_sections"] = args.required_sections

    print(f"Auditing wiki at {wiki_dir}...")
    findings = audit_wiki(wiki_dir, audit_cfg)

    if args.json_output:
        print(json.dumps(findings, indent=2, default=str))
        return

    print(f"Articles scanned: {findings.get('articles_scanned', 0)}")
    print()

    issues = findings.get("issues", {})
    total_issues = sum(len(v) for v in issues.values())
    if total_issues == 0:
        print("No issues found.")
        return

    sections_display = [
        ("dead_links", "Dead Links"),
        ("thin_articles", "Thin Articles"),
        ("near_duplicates", "Near Duplicates"),
        ("missing_sections", "Missing Sections"),
        ("suspicious_concepts", "Suspicious Concepts"),
        ("stale_content", "Stale Content"),
    ]

    for key, label in sections_display:
        items = issues.get(key, [])
        if items:
            print(f"{label} ({len(items)}):")
            for item in items[:10]:
                if key == "dead_links":
                    fname = item.get("file", "?")
                    line = item.get("line", "?")
                    target = item.get("target", "?")
                    print(f"  {fname}:{line} → {target}")
                elif key == "thin_articles":
                    fname = item.get("file", "?")
                    lines = item.get("lines", 0)
                    chars = item.get("chars", 0)
                    print(f"  {fname}: {lines} lines, {chars} chars")
                elif key == "near_duplicates":
                    fa = item.get("file_a", "?")
                    fb = item.get("file_b", "?")
                    sim = item.get("similarity", 0)
                    print(f"  {fa} ≈ {fb} ({sim:.2f})")
                elif key == "missing_sections":
                    fname = item.get("file", "?")
                    missing = ", ".join(item.get("missing", []))
                    print(f"  {fname}: missing {missing}")
                elif key == "suspicious_concepts":
                    print(f"  {item.get('file', '?')}: {item.get('subtype', '?')}")
                elif key == "stale_content":
                    print(f"  {item.get('file', '?')}: {item.get('reason', '?')}")
            if len(items) > 10:
                print(f"  ... and {len(items) - 10} more")
            print()

    summary = findings.get("summary", "")
    if summary:
        print(f"Summary: {summary}")


if __name__ == "__main__":
    main()
