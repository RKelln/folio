"""folio convert-bench — offline converter quality benchmark.

Run every enabled document converter over the committed synthetic corpus,
score each Markdown output against its golden reference, and print a
side-by-side scorecard. Optionally write a full Markdown comparison report.

The benchmark is fully **offline** and deterministic: it ties together the
landed bench foundation — :mod:`folio.core.bench.spec` (which converters and
weights), :mod:`folio.core.bench.corpus` (golden/rendered case pairs),
:mod:`folio.core.bench.runner` (convert + score + aggregate) and
:mod:`folio.core.bench.report` (scorecard + Markdown report).

Usage:
    folio convert-bench [options]

Examples:
    folio convert-bench                                  # Score all enabled converters
    folio convert-bench --json                           # Machine-readable results
    folio convert-bench --dry-run                        # Preview the plan, run nothing
    folio convert-bench --dry-run --json                 # Preview plan as JSON
    folio convert-bench --converters liteparse,pandoc    # Only these converters
    folio convert-bench --corpus ./benchmark/corpus      # Override the corpus dir
    folio convert-bench --out docs/converter-report.md   # Also write a Markdown report

Exit codes:
    0   The benchmark ran and at least one converter was available.
    1   The spec was invalid, no benchmark cases were found, an unknown
        converter was requested, or no requested converter was available
        (nothing could be benchmarked).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from folio import __version__
from folio.core.bench.corpus import discover_cases
from folio.core.bench.report import markdown_report, scorecard_table
from folio.core.bench.runner import resolve_converters, run_benchmark
from folio.core.bench.spec import load_bench_spec


def _build_parser() -> argparse.ArgumentParser:
    """Construct the ``folio convert-bench`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="folio convert-bench",
        description="Benchmark document converters against golden references "
        "(offline, deterministic).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio convert-bench                          # Score all enabled converters\n"
            "  folio convert-bench --json                   # Machine-readable results\n"
            "  folio convert-bench --dry-run                # Preview the plan, run nothing\n"
            "  folio convert-bench --dry-run --json         # Preview plan as JSON\n"
            "  folio convert-bench --converters lite,pandoc # Only these converters\n"
            "  folio convert-bench --corpus ./corpus        # Override the corpus dir\n"
            "  folio convert-bench --out report.md          # Also write a Markdown report\n"
            "\n"
            "Exit codes:\n"
            "  0  Benchmark ran and at least one converter was available.\n"
            "  1  Invalid spec, no cases found, unknown converter requested,\n"
            "     or no requested converter was available (nothing benchmarkable)."
        ),
    )
    parser.add_argument(
        "--spec",
        type=Path,
        help="Path to bench-spec.yaml (default: bundled template)",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        help="Override the corpus directory from the spec",
    )
    parser.add_argument(
        "--converters",
        type=str,
        help="Comma-separated subset of converters to run "
        "(validated against the spec's enabled converters)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Write the Markdown comparison report to this file",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview the plan (cases + converter availability) without converting",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON (dry-run plan or full results)",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``folio convert-bench``.

    Loads the bench spec, applies ``--corpus`` / ``--converters`` overrides,
    discovers corpus cases, then either prints a dry-run plan or runs the
    benchmark and prints the scorecard (and an optional Markdown report). See
    the module docstring for exit-code semantics.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # 1 — load spec ...........................................................
    try:
        spec = load_bench_spec(args.spec)
    except FileNotFoundError as exc:
        print(f"Error: bench spec not found: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: invalid bench spec: {exc}", file=sys.stderr)
        sys.exit(1)

    # 2 — apply overrides .....................................................
    if args.corpus is not None:
        spec.corpus_dir = str(args.corpus)

    if args.converters is not None:
        requested = [c.strip() for c in args.converters.split(",") if c.strip()]
        enabled_names = {c.name for c in spec.enabled_converters()}
        unknown = [name for name in requested if name not in enabled_names]
        if unknown:
            print(
                f"Error: unknown converter(s): {', '.join(repr(u) for u in unknown)}. "
                f"Enabled: {', '.join(sorted(enabled_names))}",
                file=sys.stderr,
            )
            sys.exit(1)
        wanted = set(requested)
        spec.converters = [c for c in spec.converters if c.name in wanted]

    # 3 — discover cases ......................................................
    cases = discover_cases(
        spec.corpus_dir, spec.golden_subdir, spec.rendered_subdir
    )
    if not cases:
        print(
            f"No benchmark cases found under {spec.corpus_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 4 — dry-run .............................................................
    if args.dry_run:
        resolved = resolve_converters(spec)
        case_infos = [
            {
                "slug": case.slug,
                "doc_kind": case.doc_kind,
                "fmt": case.fmt,
                "input": str(case.input_path),
            }
            for case in cases
        ]
        converter_infos = [
            {
                "name": conv.name,
                "available": resolved.get(conv.name) is not None,
                "offline": conv.offline,
                "cost_per_page": conv.cost_per_page,
            }
            for conv in spec.enabled_converters()
        ]
        plan = {
            "spec": spec.to_dict(),
            "corpus_dir": spec.corpus_dir,
            "n_cases": len(cases),
            "cases": case_infos,
            "converters": converter_infos,
            "dry_run": True,
        }

        if args.json_output:
            print(json.dumps(plan, indent=2, default=str))
            sys.exit(0)

        print("Dry run — no conversions will be performed.")
        print(f"Corpus dir:  {spec.corpus_dir}")
        print(f"Cases:       {len(cases)}")
        print(f"Pass thresh: {spec.pass_threshold}")
        print()
        print("Converters:")
        for entry in converter_infos:
            avail = "available" if entry["available"] else "UNAVAILABLE"
            offline = "offline" if entry["offline"] else "hosted"
            print(
                f"  {entry['name']:<12} {avail:<12} {offline:<8} "
                f"${entry['cost_per_page']:.4f}/pg"
            )
        print()
        print("Cases:")
        for case_entry in case_infos:
            print(
                f"  {case_entry['slug']:<28} {case_entry['doc_kind']:<16} "
                f"{case_entry['fmt']}"
            )
        sys.exit(0)

    # 5 — run benchmark .......................................................
    converters = resolve_converters(spec)
    results = run_benchmark(
        spec, cases, converters, progress=not args.json_output
    )

    # 6 — output ..............................................................
    if args.json_output:
        print(json.dumps(results.to_dict(), indent=2, default=str))
    else:
        print(scorecard_table(results))

    if args.out is not None:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown_report(results, spec), encoding="utf-8")
        if not args.json_output:
            print(f"\nReport written to {out_path}")

    # 7 — exit code ...........................................................
    any_available = any(agg.available for agg in results.converters)
    sys.exit(0 if any_available else 1)


if __name__ == "__main__":
    main()
