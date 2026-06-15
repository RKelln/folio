"""folio init — initialize a new folio project.

Usage:
    folio init --guided                    # Interactive guided setup
    folio init --profile canadian-artist-run-centre  # Use a pre-built profile
    folio init --from-scan scan-report.yaml          # Build config from scan results
    folio init --name "My Org" --funders OAC,TAC      # Quick non-interactive setup
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from folio.core.init import AVAILABLE_PROFILES, init_project


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio init",
        description="Initialize a new folio project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Available profiles: "
            + ", ".join(AVAILABLE_PROFILES)
            + "\n\n"
            "Examples:\n"
            "  folio init --guided                     # Interactive setup\n"
            "  folio init --profile canadian-artist-run-centre  # Use a profile\n"
            "  folio init --from-scan scan-results.yaml  # From scan report\n"
            "  folio init --name \"My Org\" --funders OAC,TAC,CCA  # Quick setup\n"
        ),
    )

    parser.add_argument(
        "--guided", "-g",
        action="store_true",
        help="Interactive guided setup (asks questions and writes folio.yaml)",
    )
    parser.add_argument(
        "--profile", "-p",
        choices=AVAILABLE_PROFILES,
        help="Use a pre-built profile (see list in epilog)",
    )
    parser.add_argument(
        "--from-scan",
        type=Path,
        dest="from_scan",
        help="Build config from a previous folio scan report (YAML or JSON)",
    )
    parser.add_argument(
        "--name",
        help="Organization name (used with --profile or --from-scan)",
    )
    parser.add_argument(
        "--funders",
        help="Comma-separated funder abbreviations (e.g. OAC,TAC,CCA)",
    )
    parser.add_argument(
        "--raw-archive",
        help="Path to raw document archive directory",
    )
    parser.add_argument(
        "--output", "-o",
        default="folio.yaml",
        help="Output config file path (default: folio.yaml)",
    )

    args = parser.parse_args(argv)

    if not any([args.guided, args.profile, args.from_scan]):
        print("Error: Choose at least one mode option.", file=sys.stderr)
        print("", file=sys.stderr)
        print("  --guided        Interactive guided setup", file=sys.stderr)
        print("  --profile NAME  Use a pre-built profile", file=sys.stderr)
        print("  --from-scan PATH Build config from scan results", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"Available profiles: {', '.join(AVAILABLE_PROFILES)}", file=sys.stderr)
        sys.exit(1)

    funders = None
    if args.funders:
        funders = {f.strip(): f.strip() for f in args.funders.split(",") if f.strip()}

    result = init_project(
        output_path=Path(args.output),
        profile=args.profile,
        guided=args.guided,
        from_scan=args.from_scan,
        org_name=args.name,
        funders=funders,
        raw_archive=args.raw_archive,
    )

    print(f"Configuration written to {result['config_path']}")
    if result.get("profile"):
        print(f"Profile: {result['profile']}")
    for w in result.get("warnings", []):
        print(f"Warning: {w}")
    print()
    print("Next steps:")
    print("  1. Edit folio.yaml to customize your funders and settings")
    print("  2. Run 'folio scan' to preview your archive")
    print("  3. Run 'folio pipeline --dry-run' to estimate costs")
    print("  4. Run 'folio pipeline' to process your archive")


if __name__ == "__main__":
    main()
