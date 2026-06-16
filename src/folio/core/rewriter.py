"""LLM re-authoring engine.

Tiered prompts (full/light/minimal) sent to an LLM provider to produce
clean archival markdown with YAML frontmatter. Supports concurrency,
checkpoint/resume, and cost tracking.

Usage::

    from folio.core.rewriter import rewrite_file, rewrite_directory

    result = rewrite_file(Path("clean_md/doc.md"), config, tier="full")
    summary = rewrite_directory(Path("clean_md"), config, manifest_path=...)
"""

from __future__ import annotations

import os
import re
import textwrap
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from folio.core.errors import FileStatus, ProcessingTier
from folio.core.throttle import RateLimiter
from folio.core.frontmatter import (
    apply_frontmatter,
    dict_to_frontmatter,
    parse_frontmatter,
    sanitize_frontmatter,
    strip_existing_frontmatter,
    update_frontmatter,
)
from folio.core.manifest import create_manifest, load_manifest, save_manifest, update_file, recalculate_summary
from folio.core.throttle import RateLimiter

# ── Tier alias mapping ─────────────────────────────────────────────────────────

_TIER_ALIASES: dict[str, str] = {
    "full_rewrite": "full",
    "full": "full",
    "light_cleanup": "light",
    "light": "light",
    "minimal": "minimal",
    "min": "minimal",
}

_TIER_REVERSE: dict[str, str] = {"full": "full_rewrite", "light": "light_cleanup", "minimal": "minimal"}


def _normalize_tier(tier: str) -> str:
    """Normalize tier name aliases to canonical short form (full/light/minimal)."""
    return _TIER_ALIASES.get(tier, tier)


def _to_processing_tier(tier: str) -> ProcessingTier:
    """Map a short tier name to a ProcessingTier enum."""
    normalized = _normalize_tier(tier)
    return {
        "full": ProcessingTier.FULL,
        "light": ProcessingTier.LIGHT,
        "minimal": ProcessingTier.MINIMAL,
    }.get(normalized, ProcessingTier.MINIMAL)


def _tier_value(tier: str | ProcessingTier) -> str:
    """Ensure tier is a plain string."""
    if hasattr(tier, "value"):
        return tier.value
    return str(tier)


# ── Config merging ─────────────────────────────────────────────────────────────

def _deep_merge_rewrite(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Dicts are merged; scalars/lists replaced."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_rewrite(result[key], value)
        else:
            result[key] = value
    return result


# ── Default tier prompts ──────────────────────────────────────────────────────

_DEFAULT_TIER_SYSTEM_PROMPTS: dict[str, str] = {
    "full": textwrap.dedent("""\
        You are an archival document cleaner. Read the original document below, then produce a clean markdown version suitable for permanent archival and reference.

        {heading_taxonomy}

        {frontmatter_instructions}

        - After the frontmatter, add a title (#) if there isn't one already, based on the content.
        - Fix heading hierarchy for logical depth (generally ## for major sections, ### for subsections).
        - Remove: `<!-- image -->` placeholders, form instructions, writing tips, character limit and word count notes, checkbox UI, compliance boilerplate, page numbers, signature blocks, empty sections, duplicate application headers and draft markers (e.g. "TODO").
        - Preserve all factual data: names, dates, dollar amounts, statistics, URLs.
        - Use YYYY-MM-DD format for precise dates.
        - Fix text corruption (spli t wor ds → split words), decode HTML entities (&#124; → |, &#8211; → –), but preserve intentional stylized spellings.
        - Convert stray bold text to headings where appropriate.
        - Do not add your own Notes, Observations or Commentary. Do not add any new content.
        - For application forms: use the canonical section headings provided above. Normalize heading text to the canonical form regardless of what the original uses.

        **Corrupted sources:** If the original is too corrupted for clean recovery (garbled numbers, damaged tables), still produce your best version, never leave the body empty.
        ALWAYS flag specific irrecoverable items with `<!-- FIXME: what is wrong -->`. Only flag actual data corruption (garbled text, damaged numbers, truncated content). Do NOT flag archival cleanup of blank pages, empty form templates, or boilerplate — those are correct omissions, not corruption.
        Do NOT add any other notes or commentary about the corruption — ONLY the FIXME flags in the content where issues are found.

        If you believe this document has no archival value (blank form, navigation-only page, entirely corrupted beyond recovery), set `errors: -1` in the frontmatter (so it can be dealt with). Continue to produce a cleaned version of the document body as best you can.

        Do NOT summarize answers or lose information.
    """),
    "light": textwrap.dedent("""\
        You are an archival document cleaner. Read the original document below, then produce a clean markdown version suitable for permanent archival and reference.

        {frontmatter_instructions}

        - After the frontmatter, add a title (#) if there isn't one already, based on the content.
        - Fix heading hierarchy for logical depth (generally ## for major sections, ### for subsections).
        - Remove: `<!-- image -->` placeholders, form instructions, writing tips, character limit and word count notes, checkbox UI, compliance boilerplate, page numbers, signature blocks, empty sections, duplicate application headers and draft markers (e.g. "TODO").
        - Preserve all factual data: names, dates, dollar amounts, statistics, URLs.
        - Use YYYY-MM-DD format for precise dates.
        - Fix text corruption (spli t wor ds → split words), decode HTML entities (&#124; → |, &#8211; → –), but preserve intentional stylized spellings.
        - Convert stray bold text to headings where appropriate.
        - Do not add your own Notes, Observations or Commentary. Do not add any new content.

        **Corrupted sources:** If the original is too corrupted for clean recovery (garbled numbers, damaged tables), still produce your best version, never leave the body empty.
        ALWAYS flag specific irrecoverable items with `<!-- FIXME: what is wrong -->`. Only flag actual data corruption (garbled text, damaged numbers, truncated content). Do NOT flag archival cleanup of blank pages, empty form templates, or boilerplate — those are correct omissions, not corruption.
        Do NOT add any other notes or commentary about the corruption — ONLY the FIXME flags in the content where issues are found.

        If you believe this document has no archival value (blank form, navigation-only page, entirely corrupted beyond recovery), set `errors: -1` in the frontmatter (so it can be dealt with). Continue to produce a cleaned version of the document body as best you can.

        Do NOT rephrase or summarize answers. Do NOT add new content. Just clean, organize, and add metadata.
    """),
    "minimal": textwrap.dedent("""\
        You are an archival metadata annotator. Read the document below. Do NOT modify the body content. Only:

        {frontmatter_instructions}

        - After the frontmatter, add a title (#) if there isn't one already, based on the content.
        - Remove any `<!-- image -->` placeholders.
        - Use YYYY-MM-DD format for precise dates.
        - Fix text corruption (spli t wor ds → split words), decode HTML entities (&#124; → |, &#8211; → –), but preserve intentional stylized spellings.

        If you believe this document has no archival value (blank form, navigation-only page, entirely corrupted beyond recovery), set `errors: -1` in the frontmatter (so it can be dealt with). Continue to produce a cleaned version of the document body as best you can.

        Return the document with only these frontmatter additions and minor fixes. Do not change any body text, headings, or structure.
    """),
}

_DEFAULT_TIER_USER_PROMPTS: dict[str, str] = {
    "full": """Re-author this document into clean archival markdown:\n\n{content}\n\n{metadata_block}""",
    "light": """Clean this document into clean archival markdown:\n\n{content}\n\n{metadata_block}""",
    "minimal": """Annotate this document with metadata (do not modify content):\n\n{content}\n\n{metadata_block}""",
}

_DEFAULT_TIER_SETTINGS: dict[str, dict[str, Any]] = {
    "full": {
        "enabled": True,
        "model": None,
        "thinking": True,
        "reasoning_effort": "high",
        "est_seconds_per_file": 55,
        "rules_file": None,
    },
    "light": {
        "enabled": True,
        "model": None,
        "thinking": True,
        "reasoning_effort": "low",
        "est_seconds_per_file": 50,
        "rules_file": None,
    },
    "minimal": {
        "enabled": True,
        "model": None,
        "thinking": False,
        "reasoning_effort": None,
        "est_seconds_per_file": 20,
        "rules_file": None,
    },
}


def _get_tier_config(rewrite_config: dict, tier: str) -> dict[str, Any]:
    """Resolve full tier config: user overrides merged onto defaults."""
    normalized = _normalize_tier(tier)
    defaults = _DEFAULT_TIER_SETTINGS.get(normalized, _DEFAULT_TIER_SETTINGS["minimal"])
    overrides = rewrite_config.get("tiers", {}).get(normalized, {})
    merged: dict[str, Any] = dict(defaults)
    merged.update(overrides)
    merged.setdefault("system_prompt", _DEFAULT_TIER_SYSTEM_PROMPTS.get(normalized, ""))
    merged.setdefault("user_prompt", _DEFAULT_TIER_USER_PROMPTS.get(normalized, ""))
    return merged


# ── Default rewrite config ────────────────────────────────────────────────────

DEFAULT_REWRITE_CONFIG: dict[str, Any] = {
    "processing": {
        "max_workers": 10,
        "requests_per_second": 5,
        "max_retries": 3,
        "resume": True,
        "skip_existing": True,
        "output_dir": "rewrite_md",
        "max_input_tokens": 500000,
        "max_output_tokens": 384000,
    },
    "frontmatter": {
        "date_format": "YYYY",
        "fields": {
            "funder": {
                "description": "Funding body, use abbreviation if possible: {funders}",
                "type": "string",
            },
            "type": {
                "description": "Document type: application, report, notification, budget, activity_list, staff_board, support_material, agreement",
                "type": "string",
            },
            "written": {
                "description": "Year the document was authored or submitted (e.g. 2024). Format: YYYY or YYYY-MM-DD.",
                "type": "integer",
            },
            "period": {
                "description": 'Year or range the document covers (e.g. 2025 or "2025–2027"). Use this for year-level precision.',
                "type": "string",
            },
            "period_start": {
                "description": "Start date when a precise range is available (e.g. 2019-04-02). Use with period_end instead of period.",
                "type": "date",
            },
            "period_end": {
                "description": "End date when a precise range is available (e.g. 2019-09-15). Use with period_start instead of period.",
                "type": "date",
            },
            "grant_amount": {
                "description": 'Grant dollar amount if mentioned in the document (e.g. "$51,000")',
                "type": "string",
            },
            "priority": {
                "description": "Archival priority score 1-3 (1=Essential, 2=Supplemental, 3=Redundant).",
                "type": "integer",
            },
            "errors": {
                "description": "Count of errors/corruption issues. 0 = clean, >0 = # of errors, -1 = do not archive.",
                "type": "integer",
            },
        },
    },
    "undersized_thresholds": {
        "min_content_chars": 2000,
    },
    "tiers": {
        "full": _DEFAULT_TIER_SETTINGS["full"] | {
            "system_prompt": _DEFAULT_TIER_SYSTEM_PROMPTS["full"],
            "user_prompt": _DEFAULT_TIER_USER_PROMPTS["full"],
        },
        "light": _DEFAULT_TIER_SETTINGS["light"] | {
            "system_prompt": _DEFAULT_TIER_SYSTEM_PROMPTS["light"],
            "user_prompt": _DEFAULT_TIER_USER_PROMPTS["light"],
        },
        "minimal": _DEFAULT_TIER_SETTINGS["minimal"] | {
            "system_prompt": _DEFAULT_TIER_SYSTEM_PROMPTS["minimal"],
            "user_prompt": _DEFAULT_TIER_USER_PROMPTS["minimal"],
        },
    },
    "funders": {},
}


# ── Heading taxonomy ───────────────────────────────────────────────────────────

def _build_heading_taxonomy(funders_config: dict, funder_key: str | None = None) -> str:
    """Format the funder heading taxonomy for prompt injection.

    Args:
        funders_config: Dict mapping funder abbreviations to their info dicts.
            Each info dict may have ``display`` (str) and ``headings`` (dict of
            canonical → list of alternatives).
        funder_key: If provided, only include this funder's taxonomy.

    Returns:
        Markdown string with canonical headings per funder.
    """
    parts = ["## Canonical Section Headings", ""]
    parts.append("Use these consistent section headings. Normalize to the canonical")
    parts.append("form (left) regardless of what the original uses.")
    parts.append("")

    keys_to_show = [funder_key] if funder_key and funder_key in funders_config else sorted(funders_config.keys())

    for key in keys_to_show:
        info = funders_config.get(key)
        if not isinstance(info, dict):
            continue
        headings = info.get("headings", {})
        if not headings:
            continue
        display = info.get("display", key)
        parts.append(f"### {display}")
        parts.append("")
        for canonical, alternatives in headings.items():
            alt_str = ", ".join(f'"{a}"' for a in alternatives)
            parts.append(f"- **{canonical}** ← {alt_str}")
        parts.append("")

    return "\n".join(parts)


# ── Frontmatter instructions ──────────────────────────────────────────────────

_FRONTMATTER_TEMPLATE = textwrap.dedent("""\
    ## Frontmatter Rules

    Every output document must have YAML frontmatter delimited by `---` on its own line before and after.

    {frontmatter_fields_table}

    - **Examine any existing frontmatter.** It may be empty, incomplete, or have wrong values. It is a starting point, not the final answer.
    - **For each field above, search the document body AND the filename for the correct value.** The filename encodes funder, year, and document type (e.g. `TAC__2020_TAC_grant__TAC_2020_FINAL.md` → funder: TAC, year: 2020). Document title and header text often contain year and type information.
    - **Add ANY missing field you can determine.** If you cannot find a value, leave the field out — do not guess or invent values.
    - **Correct existing fields if they are wrong.** If the frontmatter says `written: 2019` but the body clearly refers to a 2020 grant cycle, fix it.
    - **Never add fields outside the whitelist above.** Only the fields listed in the table are permitted.
    - **Date format:** Use `{date_format}`. For ranges, use the `period` field (e.g. `"2025–2027"`).
""")


def _build_frontmatter_instructions(fields: dict, funders_list: str, date_format: str = "YYYY") -> str:
    """Build the frontmatter instructions block injected into prompts.

    Args:
        fields: Dict of field name → dict with ``description`` and ``type`` keys.
        funders_list: Comma-separated string of valid funder abbreviations.
        date_format: Date format string (default "YYYY").

    Returns:
        Markdown string with the frontmatter rules and field whitelist table.
    """
    table_lines = ["| Field | Description |", "|-------|-------------|"]
    for name, info in fields.items():
        if not isinstance(info, dict):
            continue
        desc = info.get("description", "")
        desc = desc.replace("{funders}", funders_list)
        table_lines.append(f"| `{name}` | {desc} |")
    table = "\n".join(table_lines)

    instructions = _FRONTMATTER_TEMPLATE.replace("{frontmatter_fields_table}", table)
    instructions = instructions.replace("{date_format}", date_format)
    return instructions.strip()


# ── Metadata block ────────────────────────────────────────────────────────────

def _build_metadata_block(entry: dict) -> str:
    """Format key facts from a file entry for injection into LLM prompts.

    Args:
        entry: Dict with keys like ``filename``, ``funder``, ``doc_types``,
            ``written``, ``year_written``, ``period``, ``year_intended_start``,
            ``year_intended_end``.

    Returns:
        Markdown string with the metadata block.
    """
    lines = ["## Key Facts (from file metadata — fill any missing fields from the document body)", ""]
    fname = entry.get("filename", "")
    if fname:
        lines.append(f"- Filename: {fname}")

    funder = entry.get("funder")
    if funder:
        lines.append(f"- Funder: {funder}")
    else:
        lines.append("- Funder: [MISSING — find in document]")

    types = entry.get("doc_types", [])
    if types and types != ["unknown"]:
        lines.append(f"- Document type: {', '.join(types)}")

    yw = entry.get("year_written") or entry.get("written")
    if yw:
        lines.append(f"- Year written: {yw}")
    else:
        lines.append("- Year written: [MISSING — find in document]")

    ys = entry.get("year_intended_start") or entry.get("period_start")
    ye = entry.get("year_intended_end") or entry.get("period_end")
    period = entry.get("period")
    if period:
        lines.append(f"- Period: {period}")
    elif ys and ye:
        if ys == ye:
            lines.append(f"- Year: {ys}")
        else:
            lines.append(f"- Period: {ys}–{ye}")
    else:
        lines.append("- Period: [MISSING — find in document]")

    ps = entry.get("period_start")
    if ps:
        lines.append(f"- Period start: {ps}")
    pe = entry.get("period_end")
    if pe:
        lines.append(f"- Period end: {pe}")

    lines.append("- Grant amount: [MISSING — find in document if mentioned]")
    lines.append("")
    lines.append("(Frontmatter is generated from your response — ensure all determinable fields are populated.)")
    return "\n".join(lines)


# ── Frontmatter extraction from entry ─────────────────────────────────────────

def _entry_to_fm_fields(entry: dict) -> dict:
    """Build frontmatter field dict from a manifest/classify entry."""
    fields: dict[str, Any] = {}
    if entry.get("funder"):
        fields["funder"] = entry["funder"]
    types = entry.get("doc_types", [])
    if types and types != ["unknown"]:
        fields["type"] = types
    yw = entry.get("year_written") or entry.get("written")
    if yw:
        fields["written"] = yw
    period = entry.get("period")
    if period:
        fields["period"] = period
    else:
        ys = entry.get("year_intended_start") or entry.get("period_start")
        ye = entry.get("year_intended_end") or entry.get("period_end")
        if ys and ye:
            if ys == ye:
                fields["period"] = ys
            else:
                fields["period"] = f"{ys}–{ye}"

    ps = entry.get("period_start")
    if ps:
        fields["period_start"] = ps
    pe = entry.get("period_end")
    if pe:
        fields["period_end"] = pe
    return fields


# ── Prompt building ───────────────────────────────────────────────────────────

def _build_prompts(
    tier_config: dict,
    content: str,
    metadata_block: str,
    heading_taxonomy: str,
    frontmatter_instructions: str,
) -> dict[str, str]:
    """Build system and user prompts from templates with placeholder substitution."""
    system = tier_config["system_prompt"]
    system = system.replace("{heading_taxonomy}", heading_taxonomy)
    system = system.replace("{frontmatter_instructions}", frontmatter_instructions)

    rules_file = tier_config.get("rules_file")
    if rules_file and os.path.exists(rules_file):
        with open(rules_file) as f:
            rules_text = f.read().strip()
        if rules_text:
            system = system.rstrip() + "\n\n" + rules_text

    user = tier_config["user_prompt"]
    user = user.replace("{content}", content)
    user = user.replace("{metadata_block}", metadata_block)

    return {"system": system.strip(), "user": user.strip()}


# ── Local metadata-only processing ────────────────────────────────────────────

def _add_metadata_only(content: str, entry: dict) -> str:
    """Add frontmatter to a small file locally, no API call."""
    fm = dict_to_frontmatter(**_entry_to_fm_fields(entry))

    content = re.sub(r"<!-- image -->\s*", "", content)
    content = strip_existing_frontmatter(content)
    content = content.strip()

    title = entry.get("filename", "Untitled").replace(".md", "")
    title = title.replace("_", " ").replace("  ", " ")

    lines = content.split("\n")
    if len(title) > 100:
        for line in lines:
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break

    if lines and lines[0].startswith("# "):
        return f"{fm}\n\n{content}\n"
    else:
        return f"{fm}\n\n# {title}\n\n{content}\n"


# ── LLM provider ──────────────────────────────────────────────────────────────

def _create_provider(config: Any):
    """Create an LLM provider from config.

    Args:
        config: May be a ``ProjectConfig`` dataclass or a dict with
            ``base_url`` and ``api_key_env`` keys.
    """
    from folio.adapters.llm.openai_compatible import OpenAICompatibleProvider

    if hasattr(config, "llm"):
        base_url = config.llm.base_url
        api_key_env = config.llm.api_key_env
    else:
        base_url = config.get("base_url", "https://api.deepseek.com")
        api_key_env = config.get("api_key_env", "DEEPSEEK_API_KEY")

    return OpenAICompatibleProvider(base_url=base_url, api_key_env=api_key_env)


def _call_llm(
    provider,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 64000,
    temperature: float = 0,
    reasoning_effort: str | None = None,
    thinking_enabled: bool | None = None,
) -> dict:
    """Call the LLM API via provider and return response text + token usage.

    Returns:
        Dict with keys ``text``, ``input_tokens``, ``output_tokens``, ``total_tokens``.
    """
    text, usage = provider.complete_with_usage(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        thinking_enabled=thinking_enabled,
    )
    return {
        "text": text,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
    }


# ── Single-file processing ────────────────────────────────────────────────────

def _process_single(
    filepath: Path,
    config: Any,
    rewrite_config: dict,
    tier: str,
    provider=None,
    force_api: bool = False,
) -> dict:
    """Process a single file through the LLM pipeline.

    This is the internal core logic shared by ``rewrite_file`` and
    ``rewrite_directory``.

    Args:
        filepath: Path to the source ``.md`` file.
        config: ``ProjectConfig`` or dict with LLM config.
        rewrite_config: Rewrite configuration dict (tier prompts, thresholds, etc.).
        tier: Canonical short tier name (full/light/minimal).
        provider: Pre-created LLM provider. Created from config if None.
        force_api: If True, send to LLM even if file is undersized.

    Returns:
        A result dict with keys: ``filepath``, ``filename``, ``tier``,
        ``status``, ``input_tokens``, ``output_tokens``, ``rewritten``,
        ``rewritten_path``, ``error``, ``cost_usd``.
    """
    start_time = time.perf_counter()
    fname = filepath.name

    result: dict[str, Any] = {
        "filepath": str(filepath),
        "filename": fname,
        "tier": tier,
        "status": "pending",
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "elapsed_seconds": 0,
        "error": None,
    }

    try:
        if not filepath.exists():
            result["status"] = "skipped"
            result["error"] = "File not found"
            result["elapsed_seconds"] = time.perf_counter() - start_time
            return result

        content = filepath.read_text(encoding="utf-8", errors="replace")

        proc_cfg = rewrite_config.get("processing", {})
        max_input = proc_cfg.get("max_input_tokens", 500000)
        content_chars = int(max_input * 3.5)
        if len(content) > content_chars:
            content = content[:content_chars] + "\n\n[... content truncated for token limit ...]\n"

        min_chars = rewrite_config.get("undersized_thresholds", {}).get("min_content_chars", 2000)
        if len(content) < min_chars and not force_api:
            rewritten = _add_metadata_only(content, {"filename": fname})
            result["status"] = "local_metadata"
            result["input_tokens"] = len(content.split())
            result["output_tokens"] = len(rewritten.split())
            result["rewritten"] = rewritten
            result["elapsed_seconds"] = time.perf_counter() - start_time
            return result

        tier_config = _get_tier_config(rewrite_config, tier)
        if not tier_config.get("enabled", True):
            result["status"] = "skipped"
            result["error"] = f"Tier '{tier}' disabled in config"
            result["elapsed_seconds"] = time.perf_counter() - start_time
            return result

        if provider is None:
            provider = _create_provider(config)

        # Build frontmatter instructions
        fm_cfg = rewrite_config.get("frontmatter", {})
        date_fmt = fm_cfg.get("date_format", "YYYY")
        fm_fields = fm_cfg.get("fields", {})
        funders_config = rewrite_config.get("funders", {})
        funders_list = ", ".join(sorted(funders_config.keys())) if funders_config else ""

        frontmatter_instructions = _build_frontmatter_instructions(fm_fields, funders_list, date_fmt)

        # Build heading taxonomy
        heading_taxonomy = _build_heading_taxonomy(funders_config)

        # Build metadata block (minimal — from filename)
        metadata_block = _build_metadata_block({"filename": fname})

        prompts = _build_prompts(tier_config, content, metadata_block, heading_taxonomy, frontmatter_instructions)

        model = tier_config.get("model")
        if not model:
            if hasattr(config, "llm"):
                model = config.llm.fast_model
            else:
                model = config.get("model", "deepseek-v4-flash")

        reasoning = tier_config.get("reasoning_effort")
        thinking_raw = tier_config.get("thinking")
        thinking = None
        if thinking_raw is not None:
            if isinstance(thinking_raw, bool):
                thinking = thinking_raw
            elif isinstance(thinking_raw, str):
                thinking = thinking_raw.lower() != "disabled"
            else:
                thinking = None

        response = _call_llm(
            provider,
            model,
            prompts["system"],
            prompts["user"],
            max_tokens=proc_cfg.get("max_output_tokens", 384000),
            reasoning_effort=reasoning,
            thinking_enabled=thinking,
        )

        result["status"] = "success"
        result["input_tokens"] = response["input_tokens"]
        result["output_tokens"] = response["output_tokens"]

        rewritten = sanitize_frontmatter(response["text"])

        # If LLM didn't produce valid frontmatter, insert deterministically
        check_fm, _ = parse_frontmatter(rewritten)
        if check_fm is None:
            fm_str = dict_to_frontmatter(**_entry_to_fm_fields({"filename": fname}))
            rewritten = apply_frontmatter(rewritten, fm_str)

        fixme_count = rewritten.count("<!-- FIXME:")
        if fixme_count > 0:
            result["status"] = "corrupted"
        rewritten = update_frontmatter(rewritten, errors=fixme_count)

        _, body = parse_frontmatter(rewritten)
        if not body or not body.strip():
            result["status"] = "empty"
            rewritten = update_frontmatter(rewritten, errors=-1)

        result["rewritten"] = rewritten

        # Calculate cost
        input_price = 0.14
        output_price = 0.28
        if hasattr(config, "llm"):
            input_price = config.llm.input_price_per_m
            output_price = config.llm.output_price_per_m
        elif isinstance(config, dict):
            pricing = config.get("api", {}).get("pricing_usd", {})
            input_price = pricing.get("input_per_million", 0.14)
            output_price = pricing.get("output_per_million", 0.28)
        result["cost_usd"] = (
            response["input_tokens"] / 1_000_000 * input_price
            + response["output_tokens"] / 1_000_000 * output_price
        )

        result["elapsed_seconds"] = time.perf_counter() - start_time
        return result

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["elapsed_seconds"] = time.perf_counter() - start_time
        return result


# ── Public API ────────────────────────────────────────────────────────────────

def rewrite_file(
    filepath: Path,
    config: Any,
    tier: str = "full",
    llm_provider=None,
    rewrite_config: dict | None = None,
) -> dict:
    """Rewrite a single file through the LLM pipeline.

    Args:
        filepath: Path to the source ``.md`` file.
        config: ``ProjectConfig`` dataclass or a dict with LLM configuration.
        tier: Processing tier name (``"full"``, ``"light"``, ``"minimal"``,
            or their aliases).
        llm_provider: Optional ``LLMProvider`` instance. If provided, overrides
            the default provider construction from config.
        rewrite_config: Rewrite configuration dict. Uses ``DEFAULT_REWRITE_CONFIG``
            if not provided.

    Returns:
        A result dict with keys: ``filepath``, ``filename``, ``tier``, ``status``,
        ``input_tokens``, ``output_tokens``, ``rewritten`` (the output markdown
        string), ``cost_usd``, ``elapsed_seconds``, ``error`` (if any).
    """
    if rewrite_config is None:
        rewrite_config = dict(DEFAULT_REWRITE_CONFIG)

    # Merge user's rewrite config from ProjectConfig, if present
    if isinstance(config, dict) and "rewrite" in config:
        user_rewrite = config.get("rewrite", {})
    elif hasattr(config, "rewrite"):
        user_rewrite = config.rewrite
    else:
        user_rewrite = {}
    if user_rewrite:
        rewrite_config = _deep_merge_rewrite(rewrite_config, user_rewrite)

    tier_norm = _normalize_tier(tier)
    provider = None

    if llm_provider is not None:
        provider = llm_provider

    return _process_single(filepath, config, rewrite_config, tier_norm, provider=provider, force_api=True)


def rewrite_directory(
    directory: Path,
    config: Any,
    manifest_path: Path | None = None,
    tier: str | None = None,
    limit: int | None = None,
    resume: bool = True,
    dry_run: bool = False,
    rewrite_config: dict | None = None,
    provider=None,
    dest: Path | None = None,
) -> dict:
    """Rewrite all files in a directory, using manifest for tier selection and resume.

    Args:
        directory: Path to a directory containing ``.md`` files.
        config: ``ProjectConfig`` dataclass or a dict with LLM configuration.
        manifest_path: Path to a manifest JSON file (from ``classify_directory``).
            If provided, tier and metadata are read from the manifest; files
            already marked ``ok`` are skipped for resume.
        tier: Override tier for all files. If ``None``, tier is read from
            the manifest or defaults to ``"minimal"``.
        limit: Process only the first N files.
        resume: If True (default), skip files already present in the manifest
            with status ``ok`` or ``success``.
        dry_run: If True, print a summary without making any API calls.
        rewrite_config: Rewrite configuration dict. Uses ``DEFAULT_REWRITE_CONFIG``
            if not provided.
        provider: Pre-created LLM provider. Created from config if None.
        dest: Destination directory for rewritten output. Overrides the
            ``output_dir`` from rewrite config.

    Returns:
        A summary dict with counts by status and cost totals.
    """
    if rewrite_config is None:
        rewrite_config = dict(DEFAULT_REWRITE_CONFIG)

    # Merge user's rewrite config from ProjectConfig, if present
    if isinstance(config, dict) and "rewrite" in config:
        user_rewrite = config.get("rewrite", {})
    elif hasattr(config, "rewrite"):
        user_rewrite = config.rewrite
    else:
        user_rewrite = {}
    if user_rewrite:
        rewrite_config = _deep_merge_rewrite(rewrite_config, user_rewrite)

    proc_cfg = rewrite_config.get("processing", {})
    output_dir = dest.resolve() if dest else Path(proc_cfg.get("output_dir", "rewrite_md"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load manifest if provided
    manifest: dict[str, Any] = {}
    manifest_entries: dict[str, dict] = {}
    if manifest_path is not None:
        if manifest_path.exists():
            manifest = load_manifest(manifest_path)
        else:
            manifest = create_manifest()
        manifest_entries = manifest.get("files", {})

    # Collect file entries
    md_files = sorted(directory.glob("*.md"))
    entries: list[dict] = []

    for fpath in md_files:
        fname = fpath.name
        manifest_entry = manifest_entries.get(fname, {})

        # Determine tier
        file_tier = _normalize_tier(tier) if tier else None
        if file_tier is None:
            manifest_tier = manifest_entry.get("tier", "minimal")
            if hasattr(manifest_tier, "value"):
                manifest_tier = manifest_tier.value
            file_tier = _normalize_tier(manifest_tier)

        if file_tier == "skip":
            continue

        # Resume: skip files already in manifest with ok/success status
        if resume:
            m_status = manifest_entry.get("status", "")
            if hasattr(m_status, "value"):
                m_status = m_status.value
            if m_status in ("ok", "success"):
                # Also verify output file exists
                if (output_dir / fname).exists():
                    continue

        # Skip existing files if configured
        if proc_cfg.get("skip_existing") and (output_dir / fname).exists():
            continue

        entries.append({
            "filepath": str(fpath),
            "filename": fname,
            "tier": file_tier,
            "funder": manifest_entry.get("funder"),
            "doc_types": manifest_entry.get("doc_types", []),
            "year_written": manifest_entry.get("year_written"),
            "written": manifest_entry.get("written"),
            "period": manifest_entry.get("period"),
            "year_intended_start": manifest_entry.get("year_intended_start"),
            "year_intended_end": manifest_entry.get("year_intended_end"),
            "period_start": manifest_entry.get("period_start"),
            "period_end": manifest_entry.get("period_end"),
            "size_kb": fpath.stat().st_size / 1024 if fpath.exists() else 0,
        })

    if limit and limit > 0:
        entries = entries[:limit]

    # Dry run
    if dry_run:
        return _dry_run_summary(entries, config, rewrite_config, output_dir)

    if not entries:
        print("  No files to process (all already complete or skipped).", flush=True)
        return {
            "total_files": 0,
            "success": 0,
            "local_metadata": 0,
            "corrupted": 0,
            "empty": 0,
            "error": 0,
            "skipped": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "wall_seconds": 0.0,
        }

    # Create provider if not provided
    if provider is None:
        provider = _create_provider(config)

    req_per_sec = proc_cfg.get("requests_per_second", 5)
    rate_limiter = RateLimiter(req_per_sec)
    manifest_lock = threading.Lock()

    def _rate_limited_process(entry: dict) -> dict:
        filepath = Path(entry["filepath"])
        result = None
        for attempt in range(max_retries + 1):
            if attempt > 0:
                time.sleep(2 * (2 ** (attempt - 1)))
            rate_limiter.wait()
            try:
                result = _process_single(filepath, config, rewrite_config, entry["tier"], provider=provider)
            except Exception:
                result = None
            if result and result.get("status") in ("success", "local_metadata", "skipped", "corrupted", "empty"):
                break
        if result is None:
            result = {
                "filepath": str(filepath),
                "filename": entry["filename"],
                "tier": entry["tier"],
                "status": "error",
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "elapsed_seconds": 0,
                "error": "Failed after retries",
            }
        return result

    # Concurrent processing
    max_workers = proc_cfg.get("max_workers", 10)
    max_retries = proc_cfg.get("max_retries", 3)

    summary: dict[str, Any] = {
        "total_files": len(entries),
        "success": 0,
        "local_metadata": 0,
        "corrupted": 0,
        "empty": 0,
        "error": 0,
        "skipped": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "wall_seconds": 0.0,
        "total_elapsed_seconds": 0.0,
    }

    try:
        from tqdm import tqdm as _tqdm
    except ImportError:
        _tqdm = None

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_rate_limited_process, entry): entry for entry in entries}

        pbar = None
        if _tqdm:
            pbar = _tqdm(total=len(entries), desc="Re-authoring", unit="file", ncols=100, mininterval=0.5)
        else:
            print(f"  Processing {len(entries)} files...", flush=True)

        for future in as_completed(futures):
            entry = futures[future]
            try:
                result = future.result()
            except Exception:
                result = {
                    "filepath": entry["filepath"],
                    "filename": entry["filename"],
                    "tier": entry["tier"],
                    "status": "error",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "elapsed_seconds": 0,
                    "error": "Failed after retries",
                }

            # Save rewritten content
            if result.get("rewritten"):
                out_path = output_dir / result["filename"]
                out_path.write_text(result["rewritten"], encoding="utf-8")
                result["rewritten_path"] = str(out_path)

            # Update manifest if we have one
            if manifest_path is not None:
                with manifest_lock:
                    update_file(manifest, result["filename"],
                        status=FileStatus.OK if result["status"] in ("success", "local_metadata") else FileStatus.ERROR_LLM,
                        tier=_to_processing_tier(result.get("tier", "minimal")),
                        rewrite_input_tokens=result.get("input_tokens", 0),
                        rewrite_output_tokens=result.get("output_tokens", 0),
                        rewrite_cost_usd=result.get("cost_usd", 0.0),
                        rewrite_status=result.get("status", "error"),
                      )
                    recalculate_summary(manifest)
                    save_manifest(manifest, manifest_path)

            # Update summary
            status_key = result.get("status", "error")
            summary[status_key] = summary.get(status_key, 0) + 1
            summary["total_input_tokens"] += result.get("input_tokens", 0)
            summary["total_output_tokens"] += result.get("output_tokens", 0)
            summary["total_cost_usd"] += result.get("cost_usd", 0.0)
            summary["total_elapsed_seconds"] += result.get("elapsed_seconds", 0)

            if pbar:
                status_char = status_key[:1].upper() if status_key else "?"
                pbar.set_postfix_str(
                    f"{status_char} {summary['total_cost_usd']:.3f}$ {result.get('elapsed_seconds', 0):.0f}s"
                )
                pbar.update(1)
            elif not _tqdm:
                print(f"    [{status_key}] {result['filename']}", flush=True)

        if pbar:
            pbar.close()

    summary["wall_seconds"] = time.perf_counter() - wall_start
    return summary


def _dry_run_summary(
    entries: list[dict],
    config: Any,
    rewrite_config: dict,
    output_dir: Path,
) -> dict:
    """Preview what would be processed without making API calls."""
    proc_cfg = rewrite_config.get("processing", {})

    input_price = 0.14
    output_price = 0.28
    if hasattr(config, "llm"):
        input_price = config.llm.input_price_per_m
        output_price = config.llm.output_price_per_m

    by_tier: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_tier[e["tier"]].append(e)

    tier_ratios: dict[str, float] = {"full": 0.6, "light": 0.8, "minimal": 0.8}
    max_workers = proc_cfg.get("max_workers", 10)

    lines = [
        f"\n{'─' * 80}",
        f"  DRY RUN — no API calls will be made",
        f"  {Path.cwd() / output_dir}  ({len(entries)} files)",
        f"{'─' * 80}",
        f"  {'Tier':<12} {'Files':>6} {'KB':>8} {'In $':>8} {'Out $':>8} {'Total $':>8} {'Serial':>8} {'//{max_workers}':>8}",
        f"  {'─' * 12} {'─' * 6} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8}",
    ]

    grand_in = grand_out = 0.0
    grand_serial = 0
    grand_kb = 0.0
    for tier_name, tier_entries in sorted(by_tier.items()):
        total_kb = sum(e.get("size_kb", 0) for e in tier_entries)
        grand_kb += total_kb
        est_in_tokens = total_kb * 1024 / 3.5
        est_out_tokens = est_in_tokens * tier_ratios.get(tier_name, 0.8)
        est_in_cost = est_in_tokens / 1_000_000 * input_price
        est_out_cost = est_out_tokens / 1_000_000 * output_price
        grand_in += est_in_cost
        grand_out += est_out_cost

        tier_cfg = _get_tier_config(rewrite_config, tier_name)
        est_sec = tier_cfg.get("est_seconds_per_file", 30)
        count = len(tier_entries)
        serial_min = count * est_sec / 60
        grand_serial += serial_min
        parallel_min = count / max_workers * est_sec / 60
        lines.append(
            f"  {tier_name:<12} {count:>6} {total_kb:>7.0f}K ${est_in_cost:>7.4f} ${est_out_cost:>7.4f} ${est_in_cost + est_out_cost:>7.4f} {serial_min:>6.0f}m {parallel_min:>6.0f}m"
        )

    lines.append(f"  {'─' * 12} {'─' * 6} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8}")
    lines.append(
        f"  {'TOTAL':<12} {len(entries):>6} {grand_kb:>7.0f}K ${grand_in:>7.4f} ${grand_out:>7.4f} ${grand_in + grand_out:>7.4f} {grand_serial:>6.0f}m {grand_serial / max_workers:>6.0f}m"
    )
    lines.append(f"\n  (input: ${input_price}/M tokens, output: ${output_price}/M tokens, {max_workers} workers)")

    if output_dir.exists():
        existing = set(f.name for f in output_dir.iterdir() if f.is_file())
        new_count = sum(1 for e in entries if e["filename"] not in existing)
        lines.append(f"  {new_count} new files (vs {len(existing)} already in {output_dir}/)")
    lines.append("")

    print("\n".join(lines), flush=True)

    return {
        "total_files": len(entries),
        "dry_run": True,
        "by_tier": {k: len(v) for k, v in by_tier.items()},
        "estimated_cost_usd": grand_in + grand_out,
    }


# ── Utility: print summary ────────────────────────────────────────────────────

def print_summary(summary: dict, config: Any | None = None, prefix: str = "  ") -> str:
    """Format a processing summary as a human-readable string.

    Args:
        summary: Summary dict from ``rewrite_directory``.
        config: ``ProjectConfig`` for pricing. Optional.
        prefix: String prefix for each line.

    Returns:
        Formatted multi-line string.
    """
    total = summary.get("total_files", 0)
    success = summary.get("success", 0)
    local = summary.get("local_metadata", 0)
    corrupted = summary.get("corrupted", 0)
    empty = summary.get("empty", 0)
    errors = summary.get("error", 0)
    skipped = summary.get("skipped", 0)
    in_tok = summary.get("total_input_tokens", 0)
    out_tok = summary.get("total_output_tokens", 0)
    cost = summary.get("total_cost_usd", 0.0)
    wall = summary.get("wall_seconds", 0.0)

    lines = [
        f"  {'=' * 60}",
        f"  Rewrite Summary — {total} files",
        f"  {'=' * 60}",
        f"  Success:         {success:>6}",
        f"  Local metadata:  {local:>6}",
        f"  Corrupted:       {corrupted:>6}",
        f"  Empty (remove):  {empty:>6}",
        f"  Errors:          {errors:>6}",
        f"  Skipped:         {skipped:>6}",
        f"",
        f"  Input tokens:    {in_tok:>10,}",
        f"  Output tokens:   {out_tok:>10,}",
        f"  Cost:             ${cost:>9.4f}",
        f"  Wall time:        {wall:>8.1f}s",
    ]
    return "\n".join(lines)
