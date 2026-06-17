"""folio — document archive knowledge base tool.

Usage:
    folio pipeline [--config folio.yaml] [--dry-run]
    folio scan [--source ./archive/] [--config folio.yaml]
    folio init [--guided | --profile NAME]
    folio skills [--platform opencode] [--config folio.yaml]

See folio <command> --help for details.
"""

from __future__ import annotations

import sys

from folio import __version__

_COMMANDS = {
    "pipeline": "folio.cli.pipeline",
    "scan": "folio.cli.scan",
    "init": "folio.cli.init",
    "skills": "folio.cli.skills",
    "clean": "folio.cli.clean",
    "classify": "folio.cli.classify",
    "rewrite": "folio.cli.rewrite",
    "prioritize": "folio.cli.prioritize",
    "canonicalize": "folio.cli.canonicalize",
    "ingest": "folio.cli.ingest",
    "audit": "folio.cli.audit",
    "guide": "folio.cli.guide",
    "teach": "folio.cli.teach",
    "convert": "folio.cli.convert",
    "repack": "folio.cli.repack",
    "test-skills": "folio.cli.test_skills",
    "wiki": "folio.cli.wiki",
    "install-agent": "folio.cli.install_agent",
    "validate": "folio.cli.validate",
}


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        print("folio — document archive knowledge base", file=sys.stderr)
        print(file=sys.stderr)
        print("Available commands:", file=sys.stderr)
        for name in sorted(_COMMANDS):
            print(f"  folio {name}", file=sys.stderr)
        print(file=sys.stderr)
        print("Run 'folio <command> --help' for details.", file=sys.stderr)
        sys.exit(0)

    if argv[0] in ("-V", "--version"):
        print(f"folio v{__version__}", file=sys.stderr)
        sys.exit(0)

    command = argv[0]
    if command not in _COMMANDS:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(f"Available: {', '.join(sorted(_COMMANDS))}", file=sys.stderr)
        sys.exit(1)

    module_name = _COMMANDS[command]
    try:
        import importlib
        mod = importlib.import_module(module_name)
    except ImportError as e:
        print(f"Error loading command '{command}': {e}", file=sys.stderr)
        sys.exit(1)

    mod.main(argv[1:])


if __name__ == "__main__":
    main()
