"""folio skills — generate agent skills from project config.

Produces platform-specific skill files (OpenCode, Claude Code,
OpenClaw, Hermes) from the project configuration and the
platform-agnostic skill templates in skills/core/.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from folio import __version__


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="folio skills",
        description="Generate agent skills from project config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio skills --platform opencode\n"
            "  folio skills --platform claude\n"
            "  folio skills --platform opencode --dry-run\n"
            "  folio skills --platform opencode --json\n"
        ),
    )
    parser.add_argument(
        "--platform",
        required=True,
        choices=["opencode", "claude", "openclaw", "hermes"],
        help="Target platform",
    )
    parser.add_argument(
        "--config",
        default="folio.yaml",
        help="Path to folio.yaml (default: folio.yaml)",
    )
    parser.add_argument(
        "--output",
        default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )
    args = parser.parse_args(argv)

    from folio.config import load_project_config
    from folio.core.skills import generate_skills

    config_path = args.config
    if args.dry_run and not Path(config_path).exists():
        config = load_project_config(None)
    else:
        config = load_project_config(config_path)

    if args.dry_run:
        import json

        from folio.core.skills import build_context

        ctx = build_context(config)
        result = {
            "platform": args.platform,
            "context_keys": sorted(ctx.keys()),
            "dry_run": True,
        }
        if args.json:
            print(json.dumps(result, indent=2))
            return
        print(f"Would generate skills for platform: {args.platform}")
        print(f"Context keys available: {', '.join(sorted(ctx.keys()))}")
        return

    result = generate_skills(config, args.platform, Path(args.output))

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "files_written": [str(f) for f in result["files_written"]],
                    "warnings": result.get("warnings", []),
                },
                indent=2,
            )
        )
        return

    for f in result["files_written"]:
        print(f"  Wrote: {f}")
    for w in result.get("warnings", []):
        print(f"  Warning: {w}")


if __name__ == "__main__":
    main()
