"""folio guide — agent-facing usage guide and reference.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from folio import __version__

_GUIDE = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                        folio — Agent Usage Guide                            ║
╚══════════════════════════════════════════════════════════════════════════════╝

folio turns an organization's document archive into a searchable knowledge
base that AI agents can query, search, and use to write grants.

QUICK START FOR AGENTS
──────────────────────
  You are dropped into an org library directory. folio auto-discovers
  folio.yaml and .env in the current directory.

  # See what's available
  folio --help

  # See what's in the archive
  folio scan --source ./archive/

  # Estimate costs (always do this first)
  folio pipeline --dry-run

  # Run the full pipeline
  folio pipeline

  # See details for any command
  folio <command> --help

COMMAND REFERENCE
─────────────────
  folio pipeline       Run all 8 processing stages
  folio scan           Scan raw archive, detect funders/years/types
  folio init           Set up a new project config
  folio skills         Generate agent skill files per platform
  folio clean          Deterministic markdown cleanup
  folio classify       Quality scoring and tier assignment
  folio rewrite        LLM re-authoring with tiered prompts
  folio prioritize     Archival priority scoring (1-3) by year groups
  folio canonicalize   Version detection and dedup
  folio ingest         One-off document ingestion (PDF/DOCX/XLSX)
  folio audit          Wiki quality audit (dead links, thin articles, etc.)
  folio guide          This guide

PIPELINE STAGES (in order)
──────────────────────────
  1. scan           Enumerate files, detect funders/years/types/drafts
  2. convert        PDF/DOCX/XLSX → Markdown via configured converter
  3. clean          Remove form chrome, boilerplate, PDF artifacts
  4. canonicalize   Detect drafts, resolve versions, dedup near-duplicates
  5. classify       Score quality, assign processing tier (full/light/minimal)
  6. rewrite        LLM re-authoring with prompts tuned per tier
  7. prioritize     Score archival priority 1-3 within year groups
  8. wiki           Compile markdown into searchable wiki (sage-wiki)

  Run specific stages:  folio pipeline --stages scan,convert,clean
  Skip completed:       folio pipeline --resume          (default)
  Force re-run:         folio pipeline --no-resume
  Preview only:         folio pipeline --dry-run

  Every stage respects --dry-run and --json. Pipeline checkpoints save
  to {paths.rewrite_md}/manifest.json after each stage.

ORG LIBRARY CONVENTION
──────────────────────
  org-library/               # Each org has its own repo
  ├── folio.yaml             # Org config (funders, doc types, paths)
  ├── .env                   # API keys (DEEPSEEK_API_KEY, etc.)
  ├── archive/               # Raw source files (PDF, DOCX, XLSX)
  ├── markdown/              # Final LLM-rewritten output (rewrite_md)
  ├── wiki/                  # Sage-wiki searchable knowledge base
  └── .folio/                # Pipeline intermediates (hidden)
      ├── raw_md/            # Converter output
      ├── clean_md/          # Cleaned markdown
      └── manifest.json      # Pipeline checkpoint state

  folio.yaml is the single source of truth. Every pattern, threshold,
  funder name, and classification rule lives in config. Agents
  customizing for a new org should NEVER edit Python code — only YAML.

CONFIGURATION (folio.yaml)
──────────────────────────
  project:
    name: "My Organization"        # Project name
    description: ""                # Optional description

  org:
    name: "My Organization"        # Full organization name
    abbreviation: "ORG"            # Short code
    description: ""                # Optional description (appears in skills)

  paths:
    raw_archive: ./archive/        # Raw PDF/DOCX/XLSX files
    raw_md: ./.folio/raw_md/       # Converter output
    clean_md: ./.folio/clean_md/   # Cleaned markdown
    rewrite_md: ./markdown/        # Final LLM-rewritten output
    wiki_project: ./wiki/          # Wiki project directory

  funders:                         # Map abbreviation → full name
    TAC: "Toronto Arts Council"
    OAC: "Ontario Arts Council"
    CCA: "Canada Council for the Arts"

  doc_types:                       # Valid document type tags
    - application
    - report
    - budget
    - notification
    - support_material

  llm:
    provider: openai_compatible    # LLM provider (openai_compatible | openai)
    models:
      fast: deepseek-v4-flash      # Fast/cheap model
      quality: deepseek-v4-pro     # Quality model for complex documents
    base_url: https://api.deepseek.com
    pricing:
      input_per_million: 0.14
      output_per_million: 0.28

  converter:
    type: datalab                  # Or: marker, docling, null

  wiki:
    type: sage_wiki                # Or: null
    sage_wiki_pack: arts-org       # Pack name for sage-wiki

  classification:                  # Optional custom classification rules
    skip_rules: [...]
    tier_rules: [...]
    thresholds:
      full_min_content_lines: 40
      light_min_content_lines: 10

  headings:                        # Per-funder canonical heading taxonomy
    TAC:
      Definition: [...]
      "Key Figures": [...]
      Body: [...]
    .../folio.yaml  (truncated)

  Read the full config reference: folio guide --topic config-extended

ONBOARDING A NEW ORGANIZATION
─────────────────────────────
  1. folio init --guided              # Answer 6 questions, generates folio.yaml
     # OR
     folio init --profile canadian-artist-run-centre
     folio init --profile generic      # Minimal starting point

  2. Edit folio.yaml:
     - Add funders (abbreviation → full name)
     - Set doc_types list
     - Verify paths point at correct directories

  3. Verify the archive:
     folio scan --source ./archive/

  4. Estimate costs:
     folio pipeline --dry-run

  5. Run the pipeline:
     folio pipeline

  6. Generate agent skills:
     folio skills --platform opencode
     folio skills --platform claude

  Available profiles:
    canadian-artist-run-centre, canadian-gallery, canadian-festival,
    canadian-theatre, canadian-dance, generic-canadian-arts, generic

COMMON WORKFLOWS / RECIPES
──────────────────────────
  # Process just one file end-to-end
  folio ingest --source grant.pdf --funder TAC --year 2024
  folio clean --file .folio/raw_md/grant.md --dest .folio/clean_md/
  folio classify --file .folio/clean_md/grant.md
  folio rewrite --file .folio/clean_md/grant.md

  # Classify and rewrite a batch
  folio classify --source .folio/clean_md/
  folio rewrite --source .folio/clean_md/ --limit 10 --tier full

  # Audit an existing wiki
  folio audit --wiki-dir ./wiki/

  # Generate skills for multiple platforms
  folio skills --platform opencode --output .opencode/skills/
  folio skills --platform claude --output .claude/skills/

  # Dry-run everything to verify config
  folio pipeline --dry-run --json | jq .total_cost_usd

  # Resume a partial pipeline run
  folio pipeline --resume

  # Re-process only the rewrite stage with a different tier
  folio pipeline --stages rewrite --no-resume

PROCESSING TIERS
────────────────
  full      40+ content lines, good quality → full LLM rewrite with taxonomy
  light     10-39 content lines → light cleanup, preserve structure
  minimal   <10 content lines or form-heavy → metadata-only (frontmatter)

  Tiers are assigned by classify based on configurable rules. You can
  force a tier for rewrite:  folio rewrite --tier full

FILENAME CONVENTION
───────────────────
  FUNDER__Year_Description__Type.md

  Examples:
    TAC__2024__Operating_Grant__application.md
    OAC__2025__Final_Report__report.md
    CCA__2024__Budget_Submission__budget.md

  Double-underscore (__) separates segments. The canonicalizer and
  classifier parse these segments for funder detection, year extraction,
  and document type identification.

JSON OUTPUT MODE
────────────────
  Every command supports --json for machine-readable output:

    folio scan --source ./archive/ --json
    folio classify --source ./clean_md/ --json
    folio pipeline --dry-run --json | jq .

  Use --json to pipe results between commands or into analysis scripts.

ERROR RECOVERY
──────────────
  - Pipeline saves a manifest checkpoint after each stage.
  - Resume with: folio pipeline --resume
  - If a stage fails, fix the issue and re-run. Completed stages skip.
  - Force re-run a stage: folio pipeline --stages rewrite --no-resume
  - Check manifest: cat markdown/manifest.json | jq .stages
"""

_CONFIG_EXTENDED = """
CONFIG REFERENCE (EXTENDED)
───────────────────────────

classification section (all optional, deep-merged with defaults):

  skip_rules:
    - condition:
        type: has_doc_type       # 12 condition types available
        value: draft
      reason: "draft document"

  tier_rules:
    - condition:
        type: and
        conditions:
          - {type: field_gt, field: content_lines, value: 40}
          - {type: field_lt, field: corruption_score, value: 0.5}
      tier: full

  thresholds:
    full_min_content_lines: 40
    light_min_content_lines: 10
    light_max_corruption: 0.3
    max_form_chrome_ratio: 0.3

  form_chrome:                    # Regex patterns marking form fields
    - "(?i)(name of applicant|legal name)"
    - "(?i)(mailing address|postal code)"

  draft_markers:                  # Filename/keyword markers for draft status
    - "draft"
    - "working_copy"

  corruption:                     # Corruption fix toggles
    split_words: true
    single_char_lines: true
    html_entities: true

  word_count_pattern: r'(?m)^\\d+\\s+words?\\s*$'

headings section (per-funder canonical heading taxonomy):

  headings:
    TAC:
      "Program Area": []
      Description: []
      "Key Figures": []
      Budget: []
      "Support Material": []
      "Assessment Summary": []

 12 CONDITION TYPES
 ──────────────────
   Simple:
     has_doc_type VALUE       file has this document type tag
     has_any_type [VALUE...]  file has any of these type tags
     field_gt FIELD VALUE     field > value (e.g. field: content_lines, value: 40)
     field_lt FIELD VALUE     field < value
     field_gte FIELD VALUE    field >= value
     field_lte FIELD VALUE    field <= value
     path_contains [VALUE...] file path contains any substring
     filename_starts_with VAL filename starts with prefix
     has_headings             file contains headings
     has_tables               file contains tables
     true                     always matches

   Compound:
     not_ CONDITION           negate another condition
     and [cond, cond, ...]    all conditions must match
     or  [cond, cond, ...]    any condition must match

LLM PRICING
───────────
  llm:
    models:
      fast: deepseek-v4-flash
      quality: deepseek-v4-pro
    pricing:
      input_per_million: 0.14     # Cost per 1M input tokens
      output_per_million: 0.28    # Cost per 1M output tokens

  Default models (pricing verified from defaults.yaml):
    deepseek-v4-flash:  $0.14 in / $0.28 out
    deepseek-v4-pro:    ~$0.27 in / ~$1.10 out (approximate)

  Set DEEPSEEK_API_KEY or OPENAI_API_KEY in .env (loaded automatically).

CONVERTER OPTIONS
─────────────────
  converter:
    type: datalab          # Proprietary IBM Datalab (requires datalab-python-sdk)
    type: marker           # Open-source marker-pdf (pip install marker-pdf)
    type: docling          # IBM Docling (pip install docling)
    type: "null"           # No conversion (markdown-only pipeline)

WIKI BACKENDS
─────────────
  wiki:
    type: sage_wiki        # Requires sage-wiki binary on PATH
    type: "null"           # No wiki (markdown-only output)

ENVIRONMENT VARIABLES (.env)
────────────────────────────
  DEEPSEEK_API_KEY         Primary LLM API key (DeepSeek)
  OPENAI_API_KEY           Alternative LLM API key (OpenAI-compatible)
  DATALAB_API_KEY          IBM Datalab converter API key
"""

_SELECTIONS: dict[str, str | None] = {
    "config": _CONFIG_EXTENDED,
    "config-extended": _CONFIG_EXTENDED,
    "pipeline": None,
    "orgs": None,
    "recipes": None,
}


def _extract_sections_with_content(text: str) -> list[dict[str, str]]:
    """Split guide text into sections with titles and content."""
    lines = text.split("\n")
    result: list[dict[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in lines:
        m = re.match(r"^([A-Z][A-Z /]+)$", line)
        if m and current_title is None:
            current_title = m.group(1)
            continue
        if m and current_title is not None:
            result.append({"title": current_title, "content": "\n".join(current_lines).strip()})
            current_title = m.group(1)
            current_lines = []
            continue
        if current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        result.append({"title": current_title, "content": "\n".join(current_lines).strip()})

    return result


def _search_text(text: str, keyword: str) -> list[str]:
    """Return lines from text containing keyword (case-insensitive)."""
    keyword_lower = keyword.lower()
    matches = []
    for line in text.split("\n"):
        if keyword_lower in line.lower():
            matches.append(line.strip())
    return matches


def main(argv: list[str] | None = None) -> None:
    topics_available = sorted(_SELECTIONS.keys())

    parser = argparse.ArgumentParser(
        prog="folio guide",
        description="Display the folio agent usage guide and reference.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  folio guide                        # Full guide\n"
            "  folio guide config                 # Configuration reference\n"
            "  folio guide --topic config         # Same as positional\n"
            "  folio guide --topic config-extended\n"
            "  folio guide --topic pipeline\n"
            "  folio guide --search LLM           # Search for keyword\n"
            "  folio guide --dry-run              # List available topics\n"
            "  folio guide --json                 # Structured JSON output\n"
            "  folio guide config --json          # Topic as JSON\n"
            "  folio guide --dry-run --json       # Topic list as JSON\n"
        ),
    )

    parser.add_argument(
        "topic_pos",
        nargs="?",
        metavar="TOPIC",
        help=f"Topic to display ({', '.join(topics_available)})",
    )
    parser.add_argument(
        "--topic", "-t",
        dest="topic",
        help=f"Display a specific topic ({', '.join(topics_available)})",
    )
    parser.add_argument(
        "--search", "-k",
        dest="search_keyword",
        help="Search the guide for a keyword (case-insensitive)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="List available topics without printing full guide content",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output guide structure as structured JSON",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    args = parser.parse_args(argv)

    topic: str | None = args.topic or args.topic_pos

    # --dry-run: list topics only, no full content
    if args.dry_run:
        if args.json_output:
            print(json.dumps({
                "topics": topics_available,
                "dry_run": True,
            }, indent=2))
        else:
            if topic:
                print(f"Available topics: {', '.join(topics_available)}")
                print(f"Selected topic: {topic}")
            else:
                print(f"Available topics: {', '.join(topics_available)}")
        return

    # --search: find keyword in guide text
    if args.search_keyword:
        search_text = _SELECTIONS.get(topic, _GUIDE) if topic and topic in _SELECTIONS else _GUIDE
        if isinstance(search_text, str):
            matches = _search_text(search_text, args.search_keyword)
        else:
            matches = _search_text(_GUIDE, args.search_keyword)

        if args.json_output:
            print(json.dumps({
                "search": args.search_keyword,
                "topic": topic or "full",
                "matches": matches,
            }, indent=2))
        else:
            if matches:
                for line in matches:
                    print(line)
            else:
                print(f"No matches found for '{args.search_keyword}'", file=sys.stderr)
        return

    # --json: structured output (no human-readable text printed)
    if args.json_output:
        result: dict[str, Any] = {}
        result["topics"] = topics_available

        if topic and topic in _SELECTIONS:
            result["topic"] = topic
            section_text = _SELECTIONS[topic]
            if section_text:
                result["sections"] = _extract_sections_with_content(section_text)
            else:
                main_sections = _extract_sections_with_content(_GUIDE)
                result["sections"] = main_sections
                result["note"] = f"Topic '{topic}' is covered in the main guide"
        elif topic:
            print(f"Unknown topic: {topic}", file=sys.stderr)
            print(f"Available topics: {', '.join(topics_available)}", file=sys.stderr)
            sys.exit(1)
        else:
            result["topic"] = "full"
            result["sections"] = _extract_sections_with_content(_GUIDE)

        print(json.dumps(result, indent=2))
        return

    # Human-readable output
    if topic and topic in _SELECTIONS:
        section = _SELECTIONS[topic]
        if section:
            print(section)
        else:
            print(f"Topic '{topic}' is covered in the main guide.")
            print("Run 'folio guide' for the full reference.")
        return

    if topic:
        print(f"Unknown topic: {topic}", file=sys.stderr)
        print(f"Available topics: {', '.join(topics_available)}", file=sys.stderr)
        sys.exit(1)

    print(_GUIDE)


if __name__ == "__main__":
    main()
