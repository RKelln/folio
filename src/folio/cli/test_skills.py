"""CLI for agentic testing of folio skills.

Usage:
  folio test-skills --scenarios tests/agent_scenarios/ia_scenarios.yaml --mode manual
  folio test-skills --scenarios tests/agent_scenarios/ia_scenarios.yaml --mode agent
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio import __version__
from folio.core.orchestrator import (
    format_report,
    load_scenarios,
    run_agent,
    run_manual,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Test folio skills by dispatching agent tasks against an org library.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  folio test-skills --scenarios tests/agent_scenarios/ia_scenarios.yaml --mode manual
  folio test-skills --scenarios scenarios.yaml --mode agent --timeout 600
  folio test-skills --scenarios scenarios.yaml --mode manual --json --dry-run
""",
    )
    parser.add_argument(
        "--scenarios",
        required=True,
        type=Path,
        help="Path to scenario YAML file",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to folio.yaml (default: auto-detect from cwd)",
    )
    parser.add_argument(
        "--mode",
        choices=["manual", "agent"],
        default="manual",
        help="Test mode: manual (print prompts) or agent (dispatch subagents)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".folio/test_skills_output"),
        help="Directory for output files",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout per scenario in seconds (agent mode only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load scenarios and validate without running",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    if not args.scenarios.exists():
        print(f"Error: scenarios file not found: {args.scenarios}", file=sys.stderr)
        sys.exit(1)

    scenarios = load_scenarios(args.scenarios)

    if args.dry_run:
        if args.json:
            data = {
                "dry_run": True,
                "scenario_count": len(scenarios),
                "scenario_ids": [s.id for s in scenarios],
                "scenario_names": [s.name for s in scenarios],
            }
            print(json.dumps(data, indent=2))
        else:
            print(f"Would test {len(scenarios)} scenarios:")
            for s in scenarios:
                print(f"  [{s.id}] {s.name}")
        return

    config_path = args.config or Path("folio.yaml")
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "manual":
        results = run_manual(scenarios, config_path, output_dir)
    else:
        results = run_agent(scenarios, config_path, output_dir, args.timeout)

    if args.json:
        serializable = [
            {
                "scenario_id": r.scenario_id,
                "status": r.status,
                "checks": r.checks,
                "errors": r.errors,
                "output_preview": r.output[:500] if r.output else "",
            }
            for r in results
        ]
        print(json.dumps({"mode": args.mode, "results": serializable}, indent=2))
    else:
        print(format_report(results, verbose=True))

    failed = sum(1 for r in results if r.status == "fail")
    errored = sum(1 for r in results if r.status == "error")
    if failed or errored:
        sys.exit(1)


if __name__ == "__main__":
    main()
