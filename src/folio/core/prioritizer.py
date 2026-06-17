"""Archival priority scoring.

Groups files by year, sends digests to an LLM for comparison, assigns
priority 1-3 in frontmatter based on archival value.

Usage::

    from folio.core.prioritizer import prioritize_file, prioritize_directory

    # Evaluate one file in context
    result = prioritize_file(Path("rewrite_md/file.md"), config)

    # Evaluate all files, grouped by year
    manifest = prioritize_directory(Path("rewrite_md"), config, dry_run=True)
"""

from __future__ import annotations

import json
import random
import re
import textwrap
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from folio.core.frontmatter import (
    get_file_year,
    parse_frontmatter,
    update_frontmatter,
)
from folio.core.manifest import load_manifest, recalculate_summary, save_manifest, update_file
from folio.core.throttle import RateLimiter

# ── Default configuration ──────────────────────────────────────────────────────

DEFAULT_PRIORITIZE_CONFIG: dict = {
    "processing": {
        "max_workers": 5,
        "requests_per_second": 3,
        "max_retries": 3,
        "retry_base_delay_seconds": 3,
        "retry_backoff_multiplier": 2.0,
        "source_dir": "rewrite_md",
        "output_dir": "rewrite_md",
        "digest_max_chars": 6000,
        "max_files_per_batch": 60,
        "response_max_tokens": 32000,
    },
    "grouping": {
        "field": "written",
        "by_funder": False,
    },
    "rubric": {
        1: {
            "label": "Essential",
            "description": (
                "Primary, most complete version. Final submitted applications, "
                "approved budgets, complete reports. This is the go-to source "
                "for grant writing and research."
            ),
        },
        2: {
            "label": "Supplemental",
            "description": (
                "Useful reference data that augments priority-1. Supporting "
                "materials, staff/board lists, notification letters, budget breakdowns."
            ),
        },
        3: {
            "label": "Redundant/Low-value",
            "description": (
                "Information substantially duplicated in higher-priority files. "
                "Drafts, internal prep notes, generic boilerplate, corrupted "
                "files with little recoverable content."
            ),
        },
    },
}

# ── Prompt templates (overridable via config) ──────────────────────────────────

SYSTEM_PROMPT = """You are an archival document evaluator for a non-profit organization.
Your job is to compare a group of grant-related documents from the same year
and assign each a priority score based on its archival quality, completeness,
and uniqueness relative to the other documents in the group.

Think step by step before assigning scores:
1. Identify which documents are primary/final versions vs drafts/partials.
2. Note which information appears in multiple documents.
3. Consider what a future grant writer or researcher would most value.

## Priority Rubric

{rubric_text}

Return ONLY a valid JSON object. Do not wrap it in ```json fences."""

USER_PROMPT = """Evaluate these documents from {year}.

For each file, look at the frontmatter (funder, type, dates) and content preview.
Compare files against each other to determine relative priority.

Output a JSON object mapping each filename to its priority and rationale:

{{
  "priorities": {{
    "file_one.md": {{"priority": 1, "rationale": "Final submitted application — most complete version"}},
    "file_two.md": {{"priority": 3, "rationale": "Incomplete draft — all content exists in final version"}}
  }}
}}

Files to evaluate:

{files}"""

SINGLE_USER_PROMPT = """Evaluate this document{funder_context}.

Look at the frontmatter (funder, type, dates) and content preview.
{context_instruction}

Output a JSON object mapping the filename to its priority and rationale:

{{
  "priorities": {{
    "{filename}": {{"priority": 1, "rationale": "Final submitted application — very complete"}}
  }}
}}

File to evaluate:

{files}"""


# ═══════════════════════════════════════════════════════════════════════════════
#  Config resolution
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_config(config) -> dict:
    """Resolve config to a flat dict, supporting both ProjectConfig dataclasses
    and plain dicts. Falls back to DEFAULT_PRIORITIZE_CONFIG for missing keys.
    """
    result = json.loads(json.dumps(DEFAULT_PRIORITIZE_CONFIG))

    if config is None:
        return result

    if isinstance(config, dict):
        result["processing"].update(config.get("processing", {}))
        result["grouping"].update(config.get("grouping", {}))
        result["rubric"].update(config.get("rubric", {}))
        if "llm_model" in config:
            result["llm_model"] = config["llm_model"]
        return result

    if hasattr(config, "processing"):
        proc = config.processing
        result["processing"]["max_workers"] = proc.max_workers
        result["processing"]["requests_per_second"] = proc.requests_per_second
        result["processing"]["max_retries"] = proc.max_retries

    if hasattr(config, "paths"):
        result["processing"]["source_dir"] = config.paths.rewrite_md
        result["processing"]["output_dir"] = config.paths.rewrite_md

    if hasattr(config, "llm"):
        result["llm_model"] = config.llm.quality_model

    if hasattr(config, "prioritize") and isinstance(config.prioritize, dict):
        p = config.prioritize
        if isinstance(p.get("rubric"), dict):
            result["rubric"].update(p["rubric"])
        if isinstance(p.get("grouping"), dict):
            result["grouping"].update(p["grouping"])
        if isinstance(p.get("processing"), dict):
            result["processing"].update(p["processing"])

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Prompt building
# ═══════════════════════════════════════════════════════════════════════════════

def _build_rubric_text(rubric: dict) -> str:
    """Format rubric entries as a text block for prompt injection."""
    lines = []
    for level in sorted(rubric):
        entry = rubric[level]
        lines.append(f"Priority {level} — {entry.get('label', f'Level {level}')}:")
        lines.append(f"  {entry.get('description', '')}")
        lines.append("")
    return "\n".join(lines).strip()


def _build_system_prompt(config: dict) -> str:
    """Build system prompt with rubric text injected."""
    rubric_text = _build_rubric_text(config.get("rubric", {}))
    return SYSTEM_PROMPT.format(rubric_text=rubric_text)


def _build_user_prompt(
    config: dict,
    year_label: str,
    files_text: str,
    *,
    is_single: bool = False,
    filename: str = "",
    funder_context: str = "",
    context_instruction: str = "",
) -> str:
    """Build user prompt for a group or single file."""
    if is_single:
        return SINGLE_USER_PROMPT.format(
            filename=filename,
            funder_context=funder_context,
            context_instruction=context_instruction,
            files=files_text,
        )
    return USER_PROMPT.format(year=year_label, files=files_text)


# ═══════════════════════════════════════════════════════════════════════════════
#  Digest extraction
# ═══════════════════════════════════════════════════════════════════════════════

def _build_digest(filename: str, content: str, max_chars: int) -> str:
    """Extract a representative digest of a markdown file for LLM comparison.

    Includes full frontmatter + first N chars of body, truncated at a
    section boundary if possible.
    """
    if len(content) <= max_chars:
        return content
    truncated = content[:max_chars]
    for marker in ["\n---\n", "\n## ", "\n# "]:
        last = truncated.rfind(marker)
        if last > 0 and len(content[:last]) > max_chars * 0.5:
            return content[:last] + "\n\n[... content truncated ...]\n"
    return truncated + "\n\n[... content truncated ...]\n"


def _format_file_digest(
    filename: str, fm: dict | None, body_preview: str
) -> str:
    """Format a single file's metadata + content preview for the LLM prompt."""
    lines = [f"### {filename}"]
    if fm:
        for key in [
            "funder",
            "type",
            "written",
            "period",
            "period_start",
            "period_end",
            "grant_amount",
        ]:
            val = fm.get(key)
            if val is not None and val != "":
                lines.append(f"- **{key}**: {val}")
    lines.append("")
    preview = textwrap.indent(body_preview.strip(), "    ")
    lines.append(preview)
    lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  File grouping
# ═══════════════════════════════════════════════════════════════════════════════

def _group_files_by_year(
    file_items: list[dict], config: dict
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Group files by year (and optionally funder) for contextual evaluation.

    Args:
        file_items: List of dicts with keys: path, filename, content, fm, body.
        config: Resolved config dict.

    Returns:
        Tuple of (groups_dict, skipped_items).
    """
    grouping_cfg = config.get("grouping", {})
    field = grouping_cfg.get("field", "written")
    by_funder = grouping_cfg.get("by_funder", False)

    groups: dict[str, list[dict]] = defaultdict(list)
    skipped: list[dict] = []

    for item in file_items:
        if item.get("fm") is None:
            skipped.append(item)
            continue
        year = get_file_year(item["fm"], field)
        if year is None:
            year = 0  # unknown year group
        group_key = str(year)
        if by_funder and item["fm"] and item["fm"].get("funder"):
            group_key = f"{year}_{item['fm']['funder']}"
        groups[group_key].append(item)

    return dict(groups), skipped


def _split_large_groups(
    groups: dict[str, list[dict]], max_files: int
) -> dict[str, list[dict]]:
    """Split groups that exceed max_files into sub-batches.

    Splits each oversized group into roughly-even batches so no batch is
    a tiny straggler (e.g. 61 files with max=60 becomes 31+30, not 60+1).
    Files within each batch are randomly sampled from the group.
    """
    if max_files <= 0:
        return groups
    result: dict[str, list[dict]] = {}
    for key, files in groups.items():
        if len(files) <= max_files:
            result[key] = files
        else:
            num_batches = (len(files) + max_files - 1) // max_files
            per_batch = (len(files) + num_batches - 1) // num_batches
            shuffled = list(files)
            random.shuffle(shuffled)
            for b in range(num_batches):
                batch = shuffled[b * per_batch : (b + 1) * per_batch]
                result[f"{key}_batch{b + 1}"] = batch
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Response parsing
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_llm_response(text: str) -> dict | None:
    """Parse LLM JSON response, handling code fences and stray text.

    Returns the parsed JSON dict, or None if parsing fails.
    """
    text = re.sub(r"^```(?:json|yaml)?\s*\n", "", text, count=1)
    text = re.sub(r"\n```\s*$", "", text, count=1)

    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return None

    json_str = text[start : end + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def _validate_priorities(
    parsed: dict | None, expected_filenames: set[str]
) -> tuple[dict[str, int], list[str]]:
    """Validate parsed LLM response and extract filename → priority mapping.

    Returns:
        Tuple of (priorities: dict[str, int], errors: list[str]).
    """
    priorities: dict[str, int] = {}
    errors: list[str] = []

    if not parsed or not isinstance(parsed, dict):
        errors.append('Failed to parse LLM response as JSON with "priorities" key')
        return priorities, errors

    raw_priorities = parsed.get("priorities")
    if not isinstance(raw_priorities, dict):
        errors.append('Response missing or invalid "priorities" key')
        return priorities, errors

    for fname, info in raw_priorities.items():
        if not isinstance(info, dict):
            errors.append(f"Invalid entry for {fname}: {info}")
            continue
        prio = info.get("priority")
        try:
            prio = int(prio)
        except (TypeError, ValueError):
            pass
        if prio in [1, 2, 3]:
            priorities[fname] = prio
        else:
            errors.append(f"Invalid priority '{prio}' for {fname}")

    # Warn about missing expected filenames
    missing = expected_filenames - set(priorities.keys())
    if missing:
        errors.extend(f"No priority assigned for {m}" for m in sorted(missing))

    return priorities, errors


# ═══════════════════════════════════════════════════════════════════════════════
#  Group processing
# ═══════════════════════════════════════════════════════════════════════════════

def _process_group(
    group_key: str,
    files: list[dict],
    config: dict,
    llm_provider,
    model: str = "deepseek-v4-flash",
) -> dict:
    """Send one year group to the LLM and parse the priority response.

    Args:
        group_key: Year group label (e.g. "2024" or "2024_OAC").
        files: List of file dicts with path, filename, content, fm, body.
        config: Resolved config dict.
        llm_provider: LLM provider instance with a ``complete()`` method.
        model: Model name to use.

    Returns:
        Dict with group_key, priorities, errors, token estimates, etc.
    """
    start_time = time.perf_counter()
    proc_cfg = config.get("processing", {})
    digest_max = proc_cfg.get("digest_max_chars", 6000)
    max_tokens = proc_cfg.get("response_max_tokens", 32000)

    digest_parts: list[str] = []
    for item in files:
        content = item.get("content", "")
        digest = _build_digest(item["filename"], content, digest_max)
        fm_block = _format_file_digest(
            item["filename"], item.get("fm"), digest
        )
        digest_parts.append(fm_block)

    files_text = "\n".join(digest_parts)

    year_label = "Unknown year" if group_key == "0" else group_key

    system_prompt = _build_system_prompt(config)
    user_prompt = _build_user_prompt(config, year_label, files_text)

    input_est_tokens = len(system_prompt + user_prompt) // 3

    try:
        response_text = llm_provider.complete(
            system_prompt,
            user_prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=0,
        )
    except Exception:
        elapsed = time.perf_counter() - start_time
        return {
            "group_key": group_key,
            "priorities": {},
            "files_count": len(files),
            "errors": [f"LLM call failed: {traceback.format_exc()}"],
            "input_tokens": input_est_tokens,
            "output_tokens": 0,
            "elapsed_seconds": elapsed,
            "raw_response": None,
        }

    output_est_tokens = len(response_text) // 3
    parsed = _parse_llm_response(response_text)
    expected = {item["filename"] for item in files}
    priorities, errors = _validate_priorities(parsed, expected)

    elapsed = time.perf_counter() - start_time
    return {
        "group_key": group_key,
        "priorities": priorities,
        "files_count": len(files),
        "errors": errors,
        "input_tokens": input_est_tokens,
        "output_tokens": output_est_tokens,
        "elapsed_seconds": elapsed,
        "raw_response": parsed,
    }


def _group_sort_key(item: tuple[str, list]) -> tuple:
    """Sort groups: known years descending, unknown (0) last, then batch order."""
    key = item[0]
    if key == "0":
        return (1, "")
    base_key = key.split("_batch")[0]
    return (0, base_key)


# ═══════════════════════════════════════════════════════════════════════════════
#  Single file API
# ═══════════════════════════════════════════════════════════════════════════════

def prioritize_file(
    filepath: Path,
    config,
    llm_provider=None,
    group_context: list[dict] | None = None,
) -> dict:
    """Evaluate a single file's priority.

    If *group_context* is provided, the file is evaluated alongside those
    peers so the LLM can compare completeness and uniqueness.  If omitted,
    the file is evaluated in isolation against the rubric.

    Args:
        filepath: Path to the markdown file.
        config: A ``ProjectConfig``, config dict, or ``None`` (defaults).
        llm_provider: An ``LLMProvider`` instance. If ``None``, a default
            OpenAI-compatible provider is created from config.
        group_context: Optional list of dicts with keys ``filename``,
            ``content``, ``fm`` representing peer files in the same year group.

    Returns:
        A dict with ``filename``, ``priority``, ``rationale``, ``errors``,
        and token estimates.
    """
    from folio.adapters.llm import get_llm_provider as _get_provider

    resolved = _resolve_config(config)
    if llm_provider is None:
        llm_provider = _get_provider(config)

    model = resolved.get("llm_model", "deepseek-v4-flash")
    digest_max = resolved["processing"].get("digest_max_chars", 6000)
    max_tokens = resolved["processing"].get("response_max_tokens", 32000)
    field = resolved["grouping"].get("field", "written")

    try:
        raw = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {
            "filename": filepath.name,
            "priority": None,
            "rationale": "",
            "errors": [f"Could not read file: {filepath}"],
            "input_tokens": 0,
            "output_tokens": 0,
            "elapsed_seconds": 0,
        }

    fm, body = parse_frontmatter(raw)
    filename = filepath.name
    year = get_file_year(fm, field)
    year_label = str(year) if year else "unknown"

    if group_context:
        # Evaluate alongside peers
        all_files = list(group_context) + [
            {"filename": filename, "content": raw, "fm": fm, "body": body}
        ]
        result = _process_group("single", all_files, resolved, llm_provider, model)
        priority = result["priorities"].get(filename)
        rationale = ""
        if result.get("priorities") and isinstance(
            result.get("raw_response"), dict
        ):
            pdata = result["raw_response"].get("priorities", {}).get(filename, {})
            if isinstance(pdata, dict):
                rationale = pdata.get("rationale", "")
        return {
            "filename": filename,
            "priority": priority,
            "rationale": rationale,
            "errors": result.get("errors", []),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "elapsed_seconds": result.get("elapsed_seconds", 0),
        }

    # Evaluate in isolation
    funder = fm.get("funder", "") if fm else ""
    funder_context = ""
    if funder:
        funder_context = f" from {funder}"

    context_instruction = (
        "This is a single file evaluation. Compare against the rubric criteria "
        "— is this a primary submission, supplemental material, or redundant?"
    )

    digest = _build_digest(filename, raw, digest_max)
    fm_block = _format_file_digest(filename, fm, digest)

    system_prompt = _build_system_prompt(resolved)
    user_prompt = _build_user_prompt(
        resolved,
        year_label,
        fm_block,
        is_single=True,
        filename=filename,
        funder_context=funder_context,
        context_instruction=context_instruction,
    )

    start_time = time.perf_counter()
    input_est = len(system_prompt + user_prompt) // 3

    try:
        response_text = llm_provider.complete(
            system_prompt,
            user_prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=0,
        )
    except Exception:
        elapsed = time.perf_counter() - start_time
        return {
            "filename": filename,
            "priority": None,
            "rationale": "",
            "errors": [f"LLM call failed: {traceback.format_exc()}"],
            "input_tokens": input_est,
            "output_tokens": 0,
            "elapsed_seconds": elapsed,
        }

    output_est = len(response_text) // 3
    parsed = _parse_llm_response(response_text)
    priority = None
    rationale = ""
    errors: list[str] = []

    if parsed and isinstance(parsed, dict):
        pdata = parsed.get("priorities", {}).get(filename, {})
        if isinstance(pdata, dict):
            prio = pdata.get("priority")
            try:
                prio = int(prio)
            except (TypeError, ValueError):
                pass
            if prio in [1, 2, 3]:
                priority = prio
            else:
                errors.append(f"Invalid priority value: {prio}")
            rationale = str(pdata.get("rationale", ""))
        else:
            errors.append("Response missing priority data for file")
    else:
        errors.append("Failed to parse LLM response")

    elapsed = time.perf_counter() - start_time
    return {
        "filename": filename,
        "priority": priority,
        "rationale": rationale,
        "errors": errors,
        "input_tokens": input_est,
        "output_tokens": output_est,
        "elapsed_seconds": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Directory processing
# ═══════════════════════════════════════════════════════════════════════════════

def _scan_files(directory: Path) -> list[dict]:
    """Scan directory for markdown files and parse their frontmatter."""
    items: list[dict] = []
    for fpath in sorted(directory.glob("*.md")):
        try:
            raw = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        fm, body = parse_frontmatter(raw)
        items.append(
            {
                "path": fpath,
                "filename": fpath.name,
                "content": raw,
                "fm": fm,
                "body": body,
            }
        )
    return items


def prioritize_directory(
    directory: Path,
    config,
    dry_run: bool = False,
    year: int | None = None,
    limit: int | None = None,
    resume: bool = True,
) -> dict:
    """Prioritize all files in a directory, grouped by year.

    Scans *directory* for ``.md`` files, groups them by year (and
    optionally by funder), sends each group to the LLM, and writes
    updated files back with priority in frontmatter.

    Args:
        directory: Path to a directory of markdown files.
        config: A ``ProjectConfig``, config dict, or ``None`` (defaults).
        dry_run: If ``True``, preview groups and estimated costs without
            making any API calls.
        year: Restrict processing to a specific year group.
        limit: Process at most this many year groups.
        resume: If ``True``, skip groups already in the manifest.

    Returns:
        A manifest dict with per-file results and a ``summary`` section
        tracking counts, tokens, and elapsed time.
    """
    from folio.adapters.llm import get_llm_provider as _get_provider

    resolved = _resolve_config(config)
    proc_cfg = resolved.get("processing", {})
    model = resolved.get("llm_model", "deepseek-v4-flash")

    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    items = _scan_files(directory)
    if not items:
        return {"files": {}, "summary": {"total_files": 0, "total_groups": 0}}

    groups, skipped = _group_files_by_year(items, resolved)

    # Split large groups
    max_per = proc_cfg.get("max_files_per_batch", 60)
    groups = _split_large_groups(groups, max_per)

    # Filter by year
    if year is not None:
        year_str = str(year)
        groups = {k: v for k, v in groups.items() if year_str in k}
        if not groups:
            return {"files": {}, "summary": {"total_files": 0, "total_groups": 0}}

    # Sort groups
    sorted_items = sorted(groups.items(), key=_group_sort_key, reverse=True)

    # Limit
    if limit is not None and limit > 0:
        sorted_items = sorted_items[:limit]

    total_files = sum(len(v) for _, v in sorted_items)
    manifest_path = directory / "prioritize_progress.json"

    # ── Dry run ────────────────────────────────────────────────────────
    if dry_run:
        digest_max = proc_cfg.get("digest_max_chars", 6000)
        lines: list[str] = []
        lines.append(f"\n  {'─'*80}")
        lines.append("  DRY RUN — no API calls will be made")
        lines.append(f"  {'─'*80}")
        lines.append(
            f"  {'Year':<16} {'Files':>6} {'Est.Chars':>10} "
            f"{'Est.InTok':>10} {'Est.$':>8}"
        )
        lines.append(f"  {'─'*16} {'─'*6} {'─'*10} {'─'*10} {'─'*8}")

        grand_files = 0
        grand_chars = 0
        for group_key, group_files in sorted_items:
            est_chars = (len(group_files) * digest_max) + 2000
            est_tokens = est_chars // 3
            est_cost = est_tokens / 1_000_000 * 0.14
            grand_files += len(group_files)
            grand_chars += est_chars
            display = group_key if group_key != "0" else "unknown"
            lines.append(
                f"  {display:<16} {len(group_files):>6} "
                f"{est_chars:>10,.0f} {est_tokens:>10,} "
                f"${est_cost:>7.4f}"
            )
            for item in group_files:
                existing = "?"
                if item.get("fm"):
                    p = item["fm"].get("priority")
                    if p is not None:
                        existing = str(p)
                lines.append(f"    [{existing}] {item['filename']}")

        grand_tokens = grand_chars // 3
        grand_cost = grand_tokens / 1_000_000 * 0.14
        lines.append(f"  {'─'*16} {'─'*6} {'─'*10} {'─'*10} {'─'*8}")
        lines.append(
            f"  {'TOTAL':<16} {grand_files:>6} "
            f"{grand_chars:>10,.0f} {grand_tokens:>10,} "
            f"${grand_cost:>7.4f}"
        )

        dry_run_report = "\n".join(lines)
        return {
            "files": {},
            "summary": {
                "total_files": total_files,
                "total_groups": len(sorted_items),
                "dry_run": True,
                "dry_run_report": dry_run_report,
            },
        }

    # ── Real run ───────────────────────────────────────────────────────

    llm_provider = _get_provider(config)

    manifest = load_manifest(manifest_path) if resume else {}
    if "completed_groups" not in manifest:
        manifest["completed_groups"] = {}
    if "priority_counts" not in manifest.get("summary", {}):
        manifest["summary"] = {
            "total_files": total_files,
            "total_groups": len(sorted_items),
            "success": 0,
            "error": 0,
            "skipped": len(skipped),
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_elapsed_seconds": 0.0,
            "priority_counts": {"1": 0, "2": 0, "3": 0},
        }

    # Filter out already-completed groups on resume
    to_process: list[tuple[str, list[dict]]] = []
    for group_key, group_files in sorted_items:
        if resume and group_key in manifest.get("completed_groups", {}):
            continue
        to_process.append((group_key, group_files))

    if not to_process:
        return manifest

    summary = manifest["summary"]

    # Rate limiting setup
    max_workers = proc_cfg.get("max_workers", 5)
    req_per_sec = proc_cfg.get("requests_per_second", 3)
    max_retries = proc_cfg.get("max_retries", 3)
    base_delay = proc_cfg.get("retry_base_delay_seconds", 3)
    backoff = proc_cfg.get("retry_backoff_multiplier", 2.0)

    rate_limiter = RateLimiter(req_per_sec)

    def rate_limited_process(
        group_key: str, group_files: list[dict]
    ) -> dict | None:
        rate_limiter.wait()

        for attempt in range(max_retries + 1):
            if attempt > 0:
                delay = base_delay * (backoff ** (attempt - 1))
                time.sleep(delay)
            try:
                result = _process_group(
                    group_key, group_files, resolved, llm_provider, model
                )
                if result["priorities"] or attempt >= max_retries:
                    return result
            except Exception:
                if attempt >= max_retries:
                    return {
                        "group_key": group_key,
                        "priorities": {},
                        "files_count": len(group_files),
                        "errors": [
                            f"Failed after {max_retries + 1} attempts: "
                            f"{traceback.format_exc()}"
                        ],
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "elapsed_seconds": 0,
                    }
        return None

    wall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for group_key, group_files in to_process:
            future = executor.submit(
                rate_limited_process, group_key, group_files
            )
            futures[future] = (group_key, group_files)

        for future in as_completed(futures):
            group_key, group_files = futures[future]
            try:
                result = future.result()
            except Exception:
                result = {
                    "group_key": group_key,
                    "priorities": {},
                    "files_count": len(group_files),
                    "errors": [f"Future failed: {traceback.format_exc()}"],
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "elapsed_seconds": 0,
                }

            if result is None:
                result = {
                    "group_key": group_key,
                    "priorities": {},
                    "files_count": len(group_files),
                    "errors": ["All retries exhausted"],
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "elapsed_seconds": 0,
                }

            updated_count = 0
            for item in group_files:
                fname = item["filename"]
                if fname in result["priorities"]:
                    priority = result["priorities"][fname]
                    new_content = update_frontmatter(
                        item["content"], priority=priority
                    )
                    out_path = item["path"]
                    out_path.write_text(new_content, encoding="utf-8")
                    updated_count += 1
                    summary["priority_counts"][str(priority)] = (
                        summary["priority_counts"].get(str(priority), 0) + 1
                    )

            # Checkpoint
            manifest["completed_groups"][group_key] = {
                "files_count": len(group_files),
                "updated_count": updated_count,
                "priorities": result["priorities"],
                "errors": result.get("errors", []),
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "elapsed_seconds": round(result.get("elapsed_seconds", 0), 2),
            }
            manifest["summary"] = summary
            save_manifest(manifest, manifest_path)

            summary["total_input_tokens"] = summary.get(
                "total_input_tokens", 0
            ) + result.get("input_tokens", 0)
            summary["total_output_tokens"] = summary.get(
                "total_output_tokens", 0
            ) + result.get("output_tokens", 0)
            summary["total_elapsed_seconds"] = summary.get(
                "total_elapsed_seconds", 0.0
            ) + result.get("elapsed_seconds", 0)

            if result.get("errors"):
                summary["error"] = summary.get("error", 0) + 1
            else:
                summary["success"] = summary.get("success", 0) + 1

    summary["wall_seconds"] = time.perf_counter() - wall_start

    # Sync priority data back into the canonical manifest (manifest.json)
    # so recalculate_summary can include prioritize costs and priorities.
    canonical_path = directory / "manifest.json"
    if canonical_path.exists():
        canonical = load_manifest(canonical_path)
        for group_key, group_result in manifest.get("completed_groups", {}).items():
            for fname, priority in group_result.get("priorities", {}).items():
                update_file(canonical, fname, priority=int(priority))
        recalculate_summary(canonical)
        save_manifest(canonical, canonical_path)

    return manifest
