"""Render benchmark results as a plaintext scorecard and a Markdown report.

Two presentation helpers over :class:`folio.core.bench.runner.BenchResults`:

* :func:`scorecard_table` — a compact, fixed-width table for stdout / ``--json``
  siblings, one row per converter.
* :func:`markdown_report` — a human-readable Markdown comparison report that
  feeds the "Choosing a Converter" section of ``docs/converters.md``: a summary
  table, a methodology note, a per-document-type breakdown, and a one-line
  recommendation.

Both helpers preserve the converter ordering from :class:`BenchResults` so the
output is deterministic, and both render unavailable converters explicitly
rather than dropping them.
"""

from __future__ import annotations

from folio.core.bench.runner import BenchResults, ConverterAggregate
from folio.core.bench.spec import BenchSpec

#: Column headers shared by the scorecard and the Markdown summary table.
_COLUMNS = (
    "Converter",
    "Overall",
    "Text",
    "Tables",
    "Struct",
    "Links",
    "Time/pg(s)",
    "Cost/pg",
    "Offline",
    "Pass",
)

_UNAVAILABLE = "n/a"


def _row_cells(agg: ConverterAggregate) -> list[str]:
    """Return the formatted cell strings for one converter row."""
    offline = "yes" if agg.offline else "no"
    cost = f"{agg.cost_per_page:.4f}"
    if not agg.available:
        return [
            agg.name,
            _UNAVAILABLE,
            _UNAVAILABLE,
            _UNAVAILABLE,
            _UNAVAILABLE,
            _UNAVAILABLE,
            _UNAVAILABLE,
            cost,
            offline,
            "unavailable",
        ]
    return [
        agg.name,
        f"{agg.mean_weighted:.3f}",
        f"{agg.mean_text:.3f}",
        f"{agg.mean_tables:.3f}",
        f"{agg.mean_structure:.3f}",
        f"{agg.mean_links_images:.3f}",
        f"{agg.mean_elapsed_per_page_s:.3f}",
        cost,
        offline,
        "PASS" if agg.passed else "FAIL",
    ]


def scorecard_table(results: BenchResults) -> str:
    """Render the results as an aligned fixed-width plaintext table.

    One row per converter (in spec order), with the columns listed in
    :data:`_COLUMNS`. Unavailable converters render their metric columns as
    ``"n/a"`` and a ``"unavailable"`` pass cell. Returns a multi-line string
    with a dashed header separator.
    """
    rows: list[list[str]] = [list(_COLUMNS)]
    rows.extend(_row_cells(agg) for agg in results.converters)

    widths = [max(len(row[i]) for row in rows) for i in range(len(_COLUMNS))]

    def fmt(row: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    lines = [fmt(rows[0]), "  ".join("-" * w for w in widths)]
    lines.extend(fmt(row) for row in rows[1:])
    return "\n".join(lines)


def _md_table(header: list[str], rows: list[list[str]]) -> str:
    """Render a GitHub-flavored Markdown table from a header and string rows."""
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _doc_type_breakdown(results: BenchResults) -> str:
    """Render the per-document-type mean-weighted breakdown as a Markdown table.

    Rows are document kinds (sorted); columns are converters (in spec order);
    cells are the mean weighted score over scored documents of that kind, or
    ``"n/a"`` when a converter scored none of that kind.
    """
    conv_names = [c.name for c in results.converters]
    kinds = sorted({r.doc_kind for r in results.doc_results})

    sums: dict[tuple[str, str], list[float]] = {}
    for r in results.doc_results:
        if r.status == "scored":
            sums.setdefault((r.doc_kind, r.converter), []).append(r.weighted)

    rows: list[list[str]] = []
    for kind in kinds:
        row = [kind]
        for name in conv_names:
            scores = sums.get((kind, name))
            row.append(f"{sum(scores) / len(scores):.3f}" if scores else _UNAVAILABLE)
        rows.append(row)

    header = ["Doc type", *conv_names]
    return _md_table(header, rows)


def _recommendation(results: BenchResults) -> str:
    """Return a one-line recommendation for the best available converter."""
    candidates = [c for c in results.converters if c.available and c.n_scored > 0]
    if not candidates:
        return "**Recommendation:** No converter produced any scored documents."
    best = max(candidates, key=lambda c: c.mean_weighted)
    return (
        f"**Recommendation:** Use `{best.name}` — highest mean weighted score "
        f"({best.mean_weighted:.3f}) among available converters."
    )


def markdown_report(results: BenchResults, spec: BenchSpec) -> str:
    """Render a human-readable Markdown converter-comparison report.

    Sections, in order: a title, a summary table (the same columns as
    :func:`scorecard_table`), a methodology paragraph stating the offline,
    golden-reference approach and the actual per-category weights, a
    per-document-type breakdown table, and a one-line recommendation choosing
    the highest-scoring available converter.

    Args:
        results: The benchmark results to render.
        spec: The benchmark spec (for the corpus location and pass threshold).
    """
    weights = results.weights
    summary_rows = [_row_cells(agg) for agg in results.converters]

    methodology = (
        "This is a fully **offline**, deterministic benchmark. Every converter "
        f"runs over the committed synthetic corpus at `{spec.corpus_dir}` and "
        "each Markdown output is scored against a hand-authored **golden "
        "reference** using standard-library text/table/structure metrics — no "
        "network access and no LLMs. The single overall score is a weighted "
        "blend of four categories: "
        f"text {weights['text']:.2f}, tables {weights['tables']:.2f}, "
        f"structure {weights['structure']:.2f}, "
        f"links/images {weights['links_images']:.2f} "
        "(weights are normalized internally). A converter passes when its mean "
        f"weighted score is at least {spec.pass_threshold:.2f}."
    )

    parts = [
        "# Converter Benchmark Report",
        "",
        f"Evaluated {results.n_converters} converter(s) over {results.n_cases} "
        "corpus case(s).",
        "",
        "## Summary",
        "",
        _md_table(list(_COLUMNS), summary_rows),
        "",
        "## Methodology",
        "",
        methodology,
        "",
        "## Per-document-type breakdown",
        "",
        "Mean weighted score per document kind (rows) and converter (columns).",
        "",
        _doc_type_breakdown(results),
        "",
        "## Recommendation",
        "",
        _recommendation(results),
        "",
    ]
    return "\n".join(parts)
