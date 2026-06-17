"""folio teach — interactive tutorial."""

from __future__ import annotations

import argparse
import json

from folio import __version__


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio teach",
        description="Interactive tutorial for folio (coming soon).",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview without side effects",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output result as JSON",
    )

    args = parser.parse_args(argv)

    if args.json_output:
        print(json.dumps({
            "status": "not_implemented",
            "dry_run": args.dry_run,
        }, indent=2))
        return

    if args.dry_run:
        print("folio teach — would run interactive tutorial (not yet implemented)")
        return

    print("folio teach — not yet implemented")


if __name__ == "__main__":
    main()
