"""folio pipeline — run the full document processing pipeline.

Usage:
    folio pipeline                        # Run all stages
    folio pipeline --stages scan,convert  # Run specific stages
    folio pipeline --dry-run              # Estimate only
    folio pipeline --json                 # Output report as JSON
    folio pipeline --no-resume            # Force re-run all stages
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio.config.loader import load_project_config
from folio.core.pipeline import (
    AVAILABLE_STAGES,
    _estimate_pipeline,
    _format_pipeline_report,
    run_pipeline,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio pipeline",
        description="Run the full folio document processing pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Stages (in order): "
            + ", ".join(AVAILABLE_STAGES)
            + "\n\n"
            "Examples:\n"
            '  folio pipeline                              # Run all stages\n'
            '  folio pipeline --stages scan,convert        # Run only scan + convert\n'
            '  folio pipeline --dry-run                    # Preview without execution\n'
            '  folio pipeline --json                       # Output report as JSON\n'
            '  folio pipeline --resume --json | jq .       # JSON format for scripting\n'
        ),
    )

    parser.add_argument(
        "--config", "-c",
        default="folio.yaml",
        help="Path to project config file (default: folio.yaml)",
    )
    parser.add_argument(
        "--stages", "-s",
        default=None,
        help=(
            f"Comma-separated list of stages to run (default: all). "
            f"Choices: {', '.join(AVAILABLE_STAGES)}"
        ),
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Estimate costs and time without executing any stage",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip already-completed stages (default: --resume). Use --no-resume to force re-run.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output pipeline report as JSON",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show per-file progress (default: stage-level only)",
    )

    args = parser.parse_args(argv)

    stages = None
    if args.stages:
        stages = [s.strip() for s in args.stages.split(",") if s.strip()]
        invalid = [s for s in stages if s not in AVAILABLE_STAGES]
        if invalid:
            print(f"Error: Unknown stage(s): {', '.join(invalid)}", file=sys.stderr)
            print(f"  Available: {', '.join(AVAILABLE_STAGES)}", file=sys.stderr)
            sys.exit(1)

    config_path = args.config
    if not Path(config_path).exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        print('  Run "folio init" to create one.', file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        config = load_project_config(config_path)
        report = _estimate_pipeline(config)
    else:
        report = run_pipeline(
            config_path=config_path,
            stages=stages,
            dry_run=False,
            resume=args.resume,
        )

    if args.json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        if args.dry_run:
            print(_format_pipeline_report(report))
        # For live runs, run_pipeline already prints progress;
        # just print the final report at the end if verbose
        if args.verbose:
            print()
            print(_format_pipeline_report(report))


if __name__ == "__main__":
    main()
