"""folio corpus — synthetic PII-free grant corpus pipeline.

Generate golden Markdown from a spec, render to DOCX/XLSX/PDF, strip authoring
metadata, and run the PII safety gate. Also provides a standalone ``scan``
subcommand usable as a pre-commit / CI gate.

Usage:
    folio corpus [subcommand] [options]

Subcommands:
    generate   Generate corpus from spec, render formats, PII gate (default)
    scan       Run PII scan over files/directories

Gate policy (critical — see ``GATE_FAILING_KINDS``):
    The synthetic corpus DELIBERATELY contains Faker emails/phones/$ amounts,
    so a "zero findings" gate is wrong. By default, the gate FAILS only on
    findings of kind ``denylisted_name`` or ``unscannable`` (the signals of
    REAL PII / unreadable files). Structural findings (email, phone, sin, ssn,
    postal_code, currency) are COUNTED and shown but do NOT fail.
    Use ``--strict`` to fail on ANY finding (for scanning anonymized REAL docs).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from tqdm import tqdm

from folio import __version__
from folio.adapters.renderers import available_formats, get_renderer
from folio.core.corpus.generator import generate_corpus, write_golden
from folio.core.corpus.metadata import strip_metadata
from folio.core.corpus.pii_scan import (
    PIIReport,
    load_denylist,
    scan_file,
    scan_paths,
)
from folio.core.corpus.spec import ALLOWED_FORMATS, load_corpus_spec

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Gate policy — module-level constant so the policy is obvious.
# --------------------------------------------------------------------------- #

#: Finding kinds that cause the default (non-strict) PII gate to FAIL.
#: The synthetic corpus intentionally contains Faker-generated emails, phone
#: numbers and ``$`` amounts — those structural findings are expected content,
#: not PII. Only ``denylisted_name`` (a real person's name matched from the
#: denylist) and ``unscannable`` (a file whose text could not be extracted)
#: are treated as genuine gate failures.
GATE_FAILING_KINDS: frozenset[str] = frozenset({"denylisted_name", "unscannable"})

#: File suffixes the PII scanner can extract text from. Used when the ``scan``
#: subcommand recurses into directories.
SCANNABLE_SUFFIXES: frozenset[str] = frozenset({
    ".md", ".markdown", ".txt", ".html", ".htm", ".csv",
    ".pdf", ".docx", ".xlsx",
})

#: Mapping from corpus spec format name to output file extension.  ``md`` is
#: handled via ``write_golden``; the remainder are handled via renderers.
_FORMAT_EXT: dict[str, str] = {
    "docx": ".docx",
    "xlsx": ".xlsx",
    "pdf": ".pdf",
    "pdf_scanned": ".scanned.pdf",
}


# ---- helpers -----------------------------------------------------------------

def _render_extension(fmt: str) -> str:
    """Return the file extension for a rendered format (empty string for ``md``)."""
    return _FORMAT_EXT.get(fmt, f".{fmt}")


def _gate_result(
    reports: list[PIIReport], strict: bool
) -> tuple[bool, list[PIIReport]]:
    """Return ``(passed, failed_reports)`` according to the gate policy.

    ``strict`` causes EVERY finding to fail; otherwise only findings whose
    ``kind`` is in :data:`GATE_FAILING_KINDS` fail.
    """
    failing_kinds: frozenset[str] | None = None if strict else GATE_FAILING_KINDS
    failed: list[PIIReport] = []
    for report in reports:
        for finding in report.findings:
            if failing_kinds is None or finding.kind in failing_kinds:
                failed.append(report)
                break
    return len(failed) == 0, failed


def _collect_files(paths: list[Path]) -> list[Path]:
    """Collect scannable files from *paths*, recursing into directories."""
    out: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix.lower() in SCANNABLE_SUFFIXES:
            out.append(p)
        elif p.is_dir():
            for dirpath, _dirnames, filenames in os.walk(p):
                for fn in filenames:
                    fp = Path(dirpath) / fn
                    if fp.suffix.lower() in SCANNABLE_SUFFIXES:
                        out.append(fp)
    return sorted(out)


def _print_gate_report(
    reports: list[PIIReport],
    failed: list[PIIReport],
    *,
    strict: bool,
) -> None:
    """Print the human-readable PII gate report to stdout.

    Shared by the ``generate`` and ``scan`` paths so the report format stays
    consistent. Prints the scanned count, total findings, strict mode, the
    failing kinds (non-strict only), and a per-file/per-finding
    ``[FAIL]``/``[OK]`` breakdown for any offending files. Generation-specific
    stats (documents generated, files written, formats skipped) are printed by
    the caller, not here.
    """
    total_findings = sum(len(r.findings) for r in reports)
    print(f"Scanned {len(reports)} file(s).")
    print(f"Total findings: {total_findings}")
    print(f"Strict mode: {'yes' if strict else 'no'}")
    if not strict:
        print(f"Failing kinds: {', '.join(sorted(GATE_FAILING_KINDS))}")
    print()
    if failed:
        print("GATE FAILED — offending files:")
        for r in failed:
            print(f"  {r.path}")
            for fd in r.findings:
                failing = strict or fd.kind in GATE_FAILING_KINDS
                marker = "FAIL" if failing else "OK  "
                print(f"    [{marker}] {fd.kind}: {fd.match}")
    else:
        print("GATE PASSED")


# ---- generate ----------------------------------------------------------------

def _cmd_generate(args: argparse.Namespace) -> None:
    # Generate-specific args are normalized onto the namespace in main() (the
    # generate subparser may not have run when ``folio corpus`` is invoked with
    # no subcommand), so they can be read directly here.
    _spec = args.spec
    _out = args.out
    _seed = args.seed
    _funder = args.funder
    _formats = args.formats
    _strict = args.strict
    _denylist = args.denylist

    # 1 — load spec ...........................................................
    try:
        spec = load_corpus_spec(_spec)
    except FileNotFoundError as exc:
        print(f"Error: corpus spec not found: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: invalid corpus spec: {exc}", file=sys.stderr)
        sys.exit(1)

    # 2 — apply overrides .....................................................
    if _seed is not None:
        spec.seed = _seed
    if _funder is not None:
        spec.funder = _funder
    if _out is not None:
        spec.output_dir = str(_out)

    if _formats is not None:
        requested = [f.strip() for f in _formats.split(",") if f.strip()]
        bad = [f for f in requested if f not in ALLOWED_FORMATS]
        if bad:
            print(
                f"Error: unknown format(s): {', '.join(repr(b) for b in bad)}. "
                f"Allowed: {', '.join(sorted(ALLOWED_FORMATS))}",
                file=sys.stderr,
            )
            sys.exit(1)
        for doc in spec.documents:
            doc.formats = list(requested)

    # 3 — dry-run .............................................................
    if args.dry_run:
        avail = set(available_formats())
        per_doc: list[dict] = []
        for doc in spec.documents:
            fmts = []
            for fmt in doc.formats:
                fmts.append({
                    "format": fmt,
                    "available": fmt == "md" or fmt in avail,
                })
            per_doc.append({
                "kind": doc.kind,
                "count": doc.count,
                "formats": fmts,
            })
        plan = {
            "spec": spec.to_dict(),
            "total_outputs": spec.total_outputs(),
            "available_formats": sorted(avail),
            "output_dir": str(Path(spec.output_dir).resolve()),
            "documents": per_doc,
            "dry_run": True,
        }

        if args.json_output:
            print(json.dumps(plan, indent=2, default=str))
            sys.exit(0)

        print("Dry run — no files will be written.")
        print(f"Spec:      seed={spec.seed}, funder={spec.funder}, "
              f"profile={spec.profile}")
        print(f"Output dir:  {plan['output_dir']}")
        print(f"Total files: {spec.total_outputs()}")
        print(f"Available renderers: {', '.join(sorted(avail)) or '(none)'}")
        print()
        for entry in per_doc:
            fmt_strs = []
            for f in entry["formats"]:
                tag = f["format"] if f["available"] else f"{f['format']} (SKIP)"
                fmt_strs.append(tag)
            print(f"  {entry['kind']} x{entry['count']}  ->  "
                  f"[{', '.join(fmt_strs)}]")
        sys.exit(0)

    # 4 — load denylist (once, up front) ......................................
    denylist = None
    try:
        denylist = load_denylist(_denylist)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error loading PII denylist: {exc}", file=sys.stderr)
        sys.exit(1)

    # 5 — generate golden Markdown ............................................
    try:
        docs = generate_corpus(spec)
    except (ValueError, RuntimeError) as exc:
        print(f"Error generating corpus: {exc}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(spec.output_dir)
    avail = set(available_formats())

    # Build a mapping from doc index → formats from the spec (GoldenDoc has
    # no ``formats`` attribute — the formats live on DocSpec entries).
    doc_formats: dict[int, list[str]] = {}
    idx = 0
    for ds in spec.documents:
        for _ in range(ds.count):
            doc_formats[idx] = list(ds.formats)
            idx += 1

    files_written: list[str] = []
    files_skipped: list[dict] = []

    # 6 — write golden + render derived formats ...............................
    for i, doc in enumerate(
        tqdm(docs, desc="Generating corpus", unit="doc")
    ):
        fmt_list = doc_formats[i]

        # a) golden .md
        try:
            md_path = write_golden(doc, out_dir)
        except OSError as exc:
            print(f"Error writing golden {doc.slug}: {exc}", file=sys.stderr)
            sys.exit(1)
        files_written.append(str(md_path))

        # b) derived formats
        for fmt in fmt_list:
            if fmt == "md":
                continue

            ext = _render_extension(fmt)

            if fmt not in avail:
                msg = f"Renderer for {fmt!r} not available — skipping"
                logger.warning(msg)
                files_skipped.append({
                    "slug": doc.slug,
                    "format": fmt,
                    "reason": "renderer unavailable",
                })
                if not args.json_output:
                    tqdm.write(f"  WARNING: {msg} ({doc.slug})")
                continue

            try:
                renderer = get_renderer(fmt)
            except ValueError as exc:
                logger.warning("Cannot get renderer for %s: %s", fmt, exc)
                files_skipped.append({
                    "slug": doc.slug,
                    "format": fmt,
                    "reason": str(exc),
                })
                if not args.json_output:
                    tqdm.write(f"  WARNING: {exc} ({doc.slug})")
                continue

            rendered_dir = out_dir / "rendered"
            rendered_dir.mkdir(parents=True, exist_ok=True)
            out_path = rendered_dir / f"{doc.slug}{ext}"

            try:
                renderer.render(doc.markdown, doc.frontmatter, out_path)
            except (RuntimeError, OSError) as exc:
                print(
                    f"Error rendering {doc.slug} as {fmt}: {exc}",
                    file=sys.stderr,
                )
                sys.exit(1)

            try:
                strip_metadata(out_path)
            except (RuntimeError, OSError) as exc:
                print(
                    f"Error stripping metadata from {out_path}: {exc}",
                    file=sys.stderr,
                )
                sys.exit(1)

            files_written.append(str(out_path))

    # 7 — PII gate ............................................................
    reports = scan_paths(files_written, denylist=denylist)
    passed, failed = _gate_result(reports, _strict)

    # 8 — report ..............................................................
    if args.json_output:
        print(json.dumps({
            "passed": passed,
            "output_dir": str(out_dir.resolve()),
            "files_written": files_written,
            "files_skipped": files_skipped,
            "gate": {
                "passed": passed,
                "strict": _strict,
                "failing_kinds": (sorted(GATE_FAILING_KINDS) if not _strict
                                  else ["<all>"]),
                "total_files_scanned": len(reports),
                "reports": [
                    {
                        "path": r.path,
                        "clean": r.clean,
                        "findings": [
                            {"kind": fd.kind, "match": fd.match,
                             "line": fd.line, "context": fd.context}
                            for fd in r.findings
                        ],
                    }
                    for r in reports
                ],
            },
        }, indent=2))
    else:
        print()  # blank line after tqdm
        _print_gate_report(reports, failed, strict=_strict)

        print()
        if files_skipped:
            print(f"Formats skipped (unavailable): {len(files_skipped)}")
            for s in files_skipped:
                print(f"  {s['slug']} -> {s['format']}: {s['reason']}")

        print(f"\n  Documents generated: {len(docs)}")
        print(f"  Files written:       {len(files_written)}")

    sys.exit(0 if passed else 1)


# ---- scan --------------------------------------------------------------------

def _cmd_scan(args: argparse.Namespace) -> None:
    paths = args.paths

    # 1 — collect files .......................................................
    files = _collect_files(paths)

    if not files:
        print("No scannable files found.", file=sys.stderr)
        sys.exit(1)

    # 2 — dry-run .............................................................
    if args.dry_run:
        if args.json_output:
            print(json.dumps({
                "dry_run": True,
                "files": [str(p) for p in files],
                "count": len(files),
            }, indent=2))
        else:
            print(f"Would scan {len(files)} file(s):")
            for fp in files:
                print(f"  {fp}")
        sys.exit(0)

    # 3 — load denylist .......................................................
    try:
        denylist = load_denylist(args.denylist)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error loading PII denylist: {exc}", file=sys.stderr)
        sys.exit(1)

    # 4 — scan ................................................................
    reports = [
        scan_file(fp, denylist=denylist)
        for fp in tqdm(
            files, desc="Scanning", unit="file", disable=args.json_output
        )
    ]
    passed, failed = _gate_result(reports, args.strict)

    # 5 — report ..............................................................
    if args.json_output:
        print(json.dumps({
            "passed": passed,
            "strict": args.strict,
            "failing_kinds": (sorted(GATE_FAILING_KINDS) if not args.strict
                              else ["<all>"]),
            "total_files": len(files),
            "reports": [
                {
                    "path": r.path,
                    "clean": r.clean,
                    "findings": [
                        {"kind": fd.kind, "match": fd.match,
                         "line": fd.line, "context": fd.context}
                        for fd in r.findings
                    ],
                }
                for r in reports
            ],
        }, indent=2))
    else:
        _print_gate_report(reports, failed, strict=args.strict)

    sys.exit(0 if passed else 1)


# ---- main --------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="folio corpus",
        description="Generate and PII-gate a synthetic grant corpus for "
        "benchmarking and golden-reference testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio corpus                                               # Default generate\n"
            "  folio corpus generate --out ./corpus --seed 42             # Overrides\n"
            "  folio corpus generate --formats md,docx --strict           # Strict gate\n"
            "  folio corpus generate --dry-run --json                     # Preview as JSON\n"
            "  folio corpus scan ./corpus/                                # PII-gate\n"
            "  folio corpus scan --strict --denylist list.yaml ./out/     # Strict scan\n"
            "\n"
            "Gate policy (default, non-strict):\n"
            "  FAILS on: denylisted_name, unscannable\n"
            "  COUNTS but does NOT fail on: email, phone, sin, ssn, postal_code, currency\n"
            "  Use --strict to fail on ANY finding."
        ),
    )

    # --dry-run and --json on the main parser so they work without a
    # subcommand (defaults to generate).  Also added to subparsers for
    # explicit ``generate --dry-run`` / ``scan --dry-run`` usage.
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview plan without writing or scanning (defaults to generate)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON (dry-run plan, generation manifest, or scan report)",
    )

    subparsers = parser.add_subparsers(
        dest="subcommand", title="subcommands",
    )

    # ---- generate ----
    gen = subparsers.add_parser(
        "generate",
        help="Generate synthetic corpus from spec, render formats, run PII gate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gen.add_argument(
        "--spec",
        type=Path,
        help="Path to corpus-spec.yaml (default: bundled template)",
    )
    gen.add_argument(
        "--out",
        type=Path,
        help="Override output directory from spec",
    )
    gen.add_argument(
        "--seed",
        type=int,
        help="Override RNG seed",
    )
    gen.add_argument(
        "--funder",
        type=str,
        help="Override funder abbreviation",
    )
    gen.add_argument(
        "--formats",
        type=str,
        help="Comma-separated list overriding every doc's formats "
        "(e.g. 'md,docx,pdf'). Validate against allowed set.",
    )
    gen.add_argument(
        "--strict",
        action="store_true",
        help="Fail gate on ANY PII finding",
    )
    gen.add_argument(
        "--denylist",
        type=Path,
        help="Override PII name denylist YAML",
    )
    gen.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview plan without writing or scanning",
    )
    gen.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON (dry-run plan or generation manifest + gate result)",
    )

    # ---- scan ----
    scn = subparsers.add_parser(
        "scan",
        help="Run PII scan over files/directories (pre-commit / CI gate)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    scn.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Files or directories to scan (dirs recurse for known extensions)",
    )
    scn.add_argument(
        "--strict",
        action="store_true",
        help="Fail on ANY PII finding",
    )
    scn.add_argument(
        "--denylist",
        type=Path,
        help="Override PII name denylist YAML",
    )
    scn.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Print what would be scanned without scanning",
    )
    scn.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output scan report as JSON",
    )

    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    # Default subcommand: "generate". When no subcommand was given, the
    # generate subparser never ran, so seed its defaults explicitly on the
    # namespace so the handler can read them directly (no getattr fallbacks).
    if args.subcommand is None:
        args.subcommand = "generate"
        args.spec = None
        args.out = None
        args.seed = None
        args.funder = None
        args.formats = None
        args.strict = False
        args.denylist = None

    if args.subcommand == "generate":
        _cmd_generate(args)
    elif args.subcommand == "scan":
        _cmd_scan(args)


if __name__ == "__main__":
    main()
