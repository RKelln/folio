"""folio install-agent: bootstrap agent config for a platform.

Writes platform-specific agent configuration files (AGENTS.md, CLAUDE.md,
skills, etc.) into an org library directory.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from folio.config.loader import load_project_config
from folio.core.skills import generate_skills


PLATFORM_FILES: dict[str, list[tuple[str, str]]] = {
    "opencode": [
        ("AGENTS.md", "Read `folio guide` for full reference."),
    ],
    "claude": [
        ("CLAUDE.md", "Read `folio guide` for full reference."),
    ],
    "openclaw": [
        ("AGENTS.md", "Read `folio guide` for full reference."),
    ],
}

PLATFORM_SKILLS_DIR: dict[str, str] = {
    "opencode": ".opencode/skills",
    "claude": ".claude/commands",
    "openclaw": "openclaw",
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap agent configuration for a platform",
    )
    parser.add_argument("--config", "-c", default="folio.yaml", help="Path to folio.yaml")
    parser.add_argument(
        "--platform",
        "-p",
        required=True,
        choices=["opencode", "claude", "openclaw", "hermes"],
        help="Target platform",
    )
    parser.add_argument(
        "--no-skills",
        action="store_true",
        help="Skip generating skills (only write AGENTS.md/CLAUDE.md)",
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true", help="Preview without writing files"
    )
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    parser.add_argument("--version", action="version", version="folio 0.1.0")
    args = parser.parse_args(argv)

    project_config = load_project_config(Path(args.config))
    output_dir = Path.cwd()

    files_written: list[str] = []
    warnings: list[str] = []

    bootstrap_files = PLATFORM_FILES.get(args.platform, [])
    skills_dir = PLATFORM_SKILLS_DIR.get(args.platform)

    for filename, default_content in bootstrap_files:
        dest = output_dir / filename
        if not dest.exists() or args.dry_run:
            if not args.dry_run:
                dest.write_text(
                    f"# {filename} for {project_config.org.name}\n\n"
                    f"See AGENTS.md in the folio source for coding conventions.\n\n"
                    f"## Quick Reference\n\n"
                    f"Run `folio guide` for built-in agent reference.\n"
                    f"Run `folio skills --platform {args.platform}` to regenerate skills.\n"
                )
            files_written.append(str(dest))

    if not args.no_skills and not args.dry_run:
        result = generate_skills(project_config, args.platform, output_dir=output_dir)
        files_written.extend(str(p) for p in result.get("files_written", []))
        warnings.extend(result.get("warnings", []))

    if args.json:
        import json
        json.dump({
            "platform": args.platform,
            "files_written": files_written,
            "warnings": warnings,
        }, sys.stdout, indent=2)
        return

    if args.dry_run:
        print(f"Would write {len(bootstrap_files)} bootstrap file(s) for {args.platform}:")
        for f in files_written:
            print(f"  {f}")
        if not args.no_skills:
            print(f"Would also generate skills for {args.platform}")
        return

    print(f"Bootstrap complete for {args.platform}:")
    for f in files_written:
        print(f"  {f}")
    if warnings:
        for w in warnings:
            print(f"  WARNING: {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
