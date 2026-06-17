"""Archive scanner.

Scans raw document directories, detects funders/years/document types
from filenames, estimates pipeline costs and processing time.
Produces a scan report for informed pipeline planning.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from folio.adapters.sources import get_source
from folio.config.schema import ProjectConfig
from folio.core.frontmatter import extract_year

DEFAULT_TYPE_PATTERNS = {
    "application": [r'(?<![a-zA-Z])(?:Application|submission|Submitted)(?![a-zA-Z])'],
    "report": [r'(?<![a-zA-Z])(?:Report|report|Annual Update|Mid-Cycle|Final Report)(?![a-zA-Z])'],
    "notification": [r'(?<![a-zA-Z])(?:Notification|Approval|approval|result|Result)(?![a-zA-Z])'],
    "budget": [r'(?<![a-zA-Z])(?:Budget|Financial|CADAC|P\+L|cash flow)(?![a-zA-Z])'],
    "activity_list": [r'(?<![a-zA-Z])(?:Activity List|Activities|Activity Report)(?![a-zA-Z])'],
    "staff_board": [r'(?<![a-zA-Z])(?:Staff|Board|Bios|BoardOfDirectors)(?![a-zA-Z])'],
    "support_material": [r'(?<![a-zA-Z])(?:Support|Promotional|promo|press|Press)(?![a-zA-Z])'],
}

DRAFT_MARKERS = ["draft", "prep", "todo", "working"]

_DATALAB_COST_PER_PAGE = 0.02
_AVG_PAGES_PER_DOC = 3
_FILES_PER_MIN_CONVERSION = 6
_FILES_PER_MIN_LLM = 60

_REWRITE_INPUT_TOKENS = 3000
_REWRITE_OUTPUT_TOKENS = 2500
_PRIORITIZE_INPUT_TOKENS = 200
_PRIORITIZE_OUTPUT_TOKENS = 100
_WIKI_INPUT_TOKENS = 2000
_WIKI_OUTPUT_TOKENS = 1500


def _detect_funder(filepath: str, funders: dict[str, str]) -> str | None:
    """Detect funder abbreviation from filepath (longest match first)."""
    lower = filepath.lower()
    for abbrev in sorted(funders.keys(), key=len, reverse=True):
        if abbrev.lower() in lower:
            return abbrev
    return None


def _detect_year(filename: str) -> int | None:
    return extract_year(filename)


def _detect_type(filepath: str, type_patterns: dict[str, list[str]]) -> list[str]:
    """Detect document types from filepath using regex patterns."""
    found = []
    for doc_type, patterns in type_patterns.items():
        for pattern in patterns:
            if re.search(pattern, filepath):
                found.append(doc_type)
                break
    return found


def _detect_draft(filepath: str) -> bool:
    """Check if filename indicates a draft document."""
    lower = filepath.lower()
    return any(marker in lower for marker in DRAFT_MARKERS)


def _get_type_patterns(config: ProjectConfig) -> dict[str, list[str]]:
    """Get type detection patterns from config or use built-in defaults."""
    raw = getattr(config, "doc_types", None)
    if isinstance(raw, dict):
        return raw
    return DEFAULT_TYPE_PATTERNS


def _cost_per_doc(input_tokens: int, output_tokens: int, config: ProjectConfig) -> float:
    """Compute LLM cost per document in USD."""
    price_in = config.llm.input_price_per_m / 1_000_000
    price_out = config.llm.output_price_per_m / 1_000_000
    return input_tokens * price_in + output_tokens * price_out


def scan_archive(source_path: str, config: ProjectConfig) -> dict:
    """Scan a raw document archive and produce a report.

    Args:
        source_path: Path to raw archive directory or cloud source URI
        config: ProjectConfig from folio config

    Returns:
        Report dict with file counts, funder/year/type breakdowns,
        draft/unrecognized lists, and estimated costs/time.
    """
    source = get_source(source_path)
    files = source.list_files()

    by_extension: dict[str, int] = defaultdict(int)
    by_funder: dict[str, dict] = {}
    by_year: dict[int, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    unrecognized: list[str] = []
    likely_drafts: list[str] = []

    type_patterns = _get_type_patterns(config)
    funders = config.funders or {}

    for ref in files:
        ext = Path(ref.name).suffix.lower()
        by_extension[ext] += 1

        filepath = ref.path

        funder = _detect_funder(filepath, funders)
        year = _detect_year(filepath)
        types = _detect_type(filepath, type_patterns)
        is_draft = _detect_draft(filepath)

        if funder:
            if funder not in by_funder:
                by_funder[funder] = {
                    "count": 0,
                    "full_name": funders.get(funder, funder),
                    "years": set(),
                }
            by_funder[funder]["count"] += 1
            if year:
                by_funder[funder]["years"].add(year)

        if year:
            by_year[year] += 1

        if types:
            for t in types:
                by_type[t] += 1
        else:
            unrecognized.append(ref.name)

        if is_draft:
            likely_drafts.append(ref.name)

    for info in by_funder.values():
        info["years"] = sorted(info["years"])

    total = len(files)
    non_md = total - by_extension.get(".md", 0)

    converter_type = config.converter.type
    conversion_cost_per_doc = (
        _AVG_PAGES_PER_DOC * _DATALAB_COST_PER_PAGE
        if converter_type == "datalab"
        else 0
    )
    conversion_usd = non_md * conversion_cost_per_doc

    llm_rewrite_usd = total * _cost_per_doc(_REWRITE_INPUT_TOKENS, _REWRITE_OUTPUT_TOKENS, config)
    llm_prioritize_usd = total * _cost_per_doc(_PRIORITIZE_INPUT_TOKENS, _PRIORITIZE_OUTPUT_TOKENS, config)
    wiki_compile_usd = total * _cost_per_doc(_WIKI_INPUT_TOKENS, _WIKI_OUTPUT_TOKENS, config)
    total_usd = conversion_usd + llm_rewrite_usd + llm_prioritize_usd + wiki_compile_usd

    max_workers = config.processing.max_workers
    conversion_time = non_md / (_FILES_PER_MIN_CONVERSION * min(max_workers, 3))
    llm_time = total / _FILES_PER_MIN_LLM
    total_time = int(conversion_time + llm_time)

    return {
        "source_path": source_path,
        "total_files": total,
        "by_extension": dict(by_extension),
        "by_funder": by_funder,
        "by_year": dict(by_year),
        "by_type": dict(by_type),
        "unrecognized": unrecognized,
        "likely_drafts": likely_drafts,
        "estimated_costs": {
            "conversion_usd": round(conversion_usd, 2),
            "llm_rewrite_usd": round(llm_rewrite_usd, 2),
            "llm_prioritize_usd": round(llm_prioritize_usd, 2),
            "wiki_compile_usd": round(wiki_compile_usd, 2),
            "total_usd": round(total_usd, 2),
        },
        "estimated_time_minutes": total_time,
    }


def format_scan_report(report: dict) -> str:
    """Format a scan report as a human-readable string."""
    lines: list[str] = []
    lines.append("Archive Scan Report")
    lines.append("───────────────────")
    lines.append(f"Source: {report['source_path']}")

    extensions = report.get("by_extension", {})
    if extensions:
        ext_parts = [
            f"{count} {ext.lstrip('.')}"
            for ext, count in sorted(extensions.items())
        ]
        lines.append(f"Files: {report['total_files']} total ({', '.join(ext_parts)})")
    else:
        lines.append(f"Files: {report['total_files']} total")

    funders = report.get("by_funder", {})
    if funders:
        lines.append("")
        lines.append("Funders detected:")
        for abbrev, info in sorted(funders.items()):
            yrs = info.get("years", [])
            if yrs:
                years_str = f"{yrs[0]}-{yrs[-1]}" if len(yrs) > 1 else str(yrs[0])
            else:
                years_str = "?"
            lines.append(f"  {abbrev} ({info['count']} files, {years_str})")

    types = report.get("by_type", {})
    if types:
        lines.append("")
        lines.append("Document types:")
        for doc_type, count in sorted(types.items()):
            lines.append(f"  {doc_type}: {count}")

    drafts = report.get("likely_drafts", [])
    lines.append("")
    lines.append(f"Likely drafts: {len(drafts)} files")

    unrecognized = report.get("unrecognized", [])
    lines.append(f"Unrecognized: {len(unrecognized)} files")

    costs = report.get("estimated_costs")
    if costs:
        conv = costs.get("conversion_usd", 0)
        converter_label = "Datalab" if conv > 0 else "Free"
        lines.append("")
        lines.append("Estimated costs:")
        lines.append(f"  Conversion: ${conv:.2f} ({converter_label})")
        lines.append(f"  LLM rewrite: ${costs.get('llm_rewrite_usd', 0):.2f}")
        lines.append(f"  LLM prioritize: ${costs.get('llm_prioritize_usd', 0):.2f}")
        lines.append(f"  Wiki compile: ${costs.get('wiki_compile_usd', 0):.2f}")
        lines.append(f"  ─────────────────")
        lines.append(f"  Total: ${costs.get('total_usd', 0):.2f}")

    time_mins = report.get("estimated_time_minutes")
    if time_mins is not None:
        lines.append("")
        lines.append(f"Estimated time: ~{time_mins} minutes")

    return "\n".join(lines)
