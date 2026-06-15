# PLAN.md — Production-Grade llm_wiki: Design & Migration Plan

## 1. What Was Built (Prototype Summary)

The `llm_wiki` prototype transforms a raw archive of grant documents (PDFs, DOCX, XLSX) into a clean, searchable knowledge base that AI coding agents can use to draft new grants, find precedent, and answer organizational questions. It was developed against InterAccess gallery's 1,033-file archive and processed the full set for ~$2.65 in LLM costs.

### Pipeline stages

```
_raw_archive/ (PDFs, DOCX, XLSX)
  │
  ├─ [external conversion: Datalab or other] → raw_md/
  │
  ├─ clean_md.py      Deterministic cleanup (strip images, normalize whitespace,
  │   (412 lines)      fix corruption, remove form chrome, promote bold→headings)
  │                    → clean_md/
  │
  ├─ canonicalize.py  Filter to canonical versions before expensive LLM work:
  │   (696 lines)      removes drafts, superseded submissions, near-duplicates
  │                    using SequenceMatcher scoring + optional LLM for edge cases
  │                    → clean_md/ (minus non-canonical files)
  │
  ├─ classify_files.py Score each file by content quality, assign tier
  │   (531 lines)      (skip/minimal/light/full) using configurable rules with
  │                    eval() expressions. Skips guidelines, CVs, emails,
  │                    raw financial dumps, corrupted files.
  │                    → manifest.json
  │
  ├─ rewrite_md.py    LLM re-authoring via DeepSeek API. Tiered prompts:
  │   (1014 lines)     - full: complete re-authoring with canonical headings
  │                    - light: fix headings, remove chrome, keep content
  │                    - minimal: metadata only, no content changes
  │                    Concurrent (10 workers), checkpoint/resume, cost tracking.
  │                    → rewrite_md/ (LLM-rewritten, YAML frontmatter added)
  │
  ├─ prioritize_files.py LLM evaluates files grouped by year, assigns priority 1-3
  │   (785 lines)        in frontmatter for search/filter ranking
  │                      → rewrite_md/ (updated with priority field)
  │
  ├─ Misc utilities: check_fm.py, find_long_paras.py, datalab_retry.py,
  │   find_pdf.py, find_budget_tables.py, find_stats.py, audit_wiki.py
  │
  ├─ select_for_import.py  Copy priority 1-2 docs to wiki raw directory
  │   (70 lines)            (priority 3 CADAC/statistical forms excluded)
  │
  ├─ sage-wiki compile  LLM-compiled knowledge wiki (Go binary, not Python)
  │   3 passes:          Pass 1: summarize each doc → wiki/summaries/
  │                      Pass 2: extract cross-document concepts → manifest
  │                      Pass 3: write concept articles → wiki/concepts/
  │                      → sage_wiki_3/wiki/
  │
  └─ Agentic wiki cleanup  audit_wiki.py → delete noise → stub missing concepts
                           → flesh out key articles → fix timelines → recompile
```

### One-off ingestion path

```
ingest.py (547 lines)
  PDF/DOCX/XLSX/MD → Datalab convert → deterministic cleanup →
  frontmatter injection → save to rewrite_md/ + wiki sync
  One command for newly-written documents.
```

### Key architectural patterns

1. **Config-driven**: classification rules, heading taxonomies, priority rubrics, LLM prompts, funder lists — all in YAML. An agent onboarding a new org should only edit YAML.
2. **Checkpoint/resume**: Both `rewrite_md.py` and `prioritize_files.py` save JSON checkpoints for crash recovery.
3. **Composable**: Tools accept `--files` for chaining (file list or comma-separated names), `--json` for structured output, `--dry-run` for previews.
4. **Self-documenting**: All tools have `--help` with examples. Docstrings cover purpose, inputs, outputs.
5. **Minimal dependencies**: pyyaml, openai, python-dotenv, tqdm, datalab-python-sdk. Under 6 packages.
6. **Frontmatter as API**: YAML frontmatter (`funder`, `type`, `written`, `period`, `grant_amount`, `priority`, `errors`) on every document enables machine querying without a database.
7. **Three views of the same data**: `rewrite_md/` (raw text + frontmatter), `agentmap` (heading-level search), sage-wiki (cross-document synthesis). Each serves different query patterns.

### Agent usage pattern

Agents search with two tools:
- **sage-wiki** (`search`, `query`): cross-document synthesis, concept exploration, Q&A with citations
- **agentmap** (`search`, `headings`): fuzzy heading matching within individual documents, NAV block navigation

Workflow: wiki for precedent → agentmap for exact passages → read file at NAV offsets for verbatim text.

### What works well

- The config-driven design is real — most org-specific behavior IS in YAML
- Cost is genuinely low ($2.65 for 1,033 files, ~$0.0026/file)
- Checkpoint/resume prevents lost work on long LLM runs
- Frontmatter conventions are well-thought-out (field aliases, type value normalization, period normalization)
- The three-tier rewrite approach (minimal/light/full) correctly balances cost vs quality
- The `arts-org` pack shows the pack concept works for sage-wiki customization
- Agent skills (.opencode, .claude) provide real workflows that work

---

## 2. What's Wrong / Needs Fixing

### 2.1 Hardcoded InterAccess-specific values in Python code

These violate the config-driven principle. An agent onboarding a new org should never need to edit Python:

| File | Line(s) | What's hardcoded |
|------|---------|------------------|
| `ingest.py` | 49 | `VALID_FUNDERS = frozenset({'TAC', 'OAC', 'CCA', 'BCAH'})` |
| `ingest.py` | 51-55 | `VALID_DOC_TYPES` list |
| `ingest.py` | 42 | `PIPELINE_ID` (Datalab pipeline) |
| `ingest.py` | 44 | `DEFAULT_WIKI_DIR = 'sage_wiki_3'` |
| `clean_md.py` | 57-58 | `USELESS_HEADINGS` regexes reference "Toronto Arts Council" |
| `audit_wiki.py` | ~237 | `find_stale_content` hardcodes IA addresses (Dupont, Lisgar, Ossington) |
| `find_stats.py` | 50-79 | `TOPIC_KEYWORDS` reference IA programs (Vector Festival, Terra Firma) |
| `datalab_retry.py` | 29 | `PIPELINE_ID = 'pl_b-mZV9v283iM'` (overridable via flag but bad default) |

### 2.2 `eval()` for classification rules

`classify_files.py` uses Python `eval()` with a restricted namespace for skip/tier rule conditions. This is:
- A security concern if someone can write to the config
- Fragile — exceptions are caught silently, making broken rules appear as non-matches
- Unnecessary — a small expression DSL or pre-defined condition functions would be safer

### 2.3 No proper packaging

- `pyproject.toml` has no `[project.scripts]` entry points — tools are run as loose `python3 script.py`
- No `pip install` experience — you must clone the repo and `uv sync`
- Python 3.14 requirement is bleeding edge and excludes most users
- No version pinning or lockfile

### 2.4 No formal frontmatter schema

Frontmatter fields are documented in README and `fm_utils.py` but:
- No schema validation when writing frontmatter
- No type checking (grant_amount should be a quoted string, written should be an int)
- Field aliases are handled ad-hoc in `fm_utils.py` but not formally defined as a schema
- The LLM is told about allowed fields in a text block (rewrite_config.yaml), not a machine-readable schema

### 2.5 Fragile filename convention pipeline dependency

The entire pipeline depends on filenames encoding funder, year, and document type with `__` separators (e.g. `TAC__2020_TAC_grant__TAC_2020_FINAL.md`). This convention:
- Is not documented in a single spec
- Varies across tools (some use `__`, some use `_`)
- Breaks silently when filenames don't match conventions
- Makes the pipeline hard to use with arbitrary filenames

### 2.6 No testing framework

- Only inline `_run_tests()` functions in `fm_utils.py` and `cli_utils.py`
- No pytest, no CI/CD, no integration tests
- The test harness (`test_harness.py`) is for evaluating wiki quality, not testing pipeline correctness

### 2.7 External tool coupling

- **sage-wiki**: Go binary, not installable via Python. Users must install Go and compile or download releases.
- **agentmap**: Another external binary with no Python SDK. Must be separately installed.
- **Datalab**: Proprietary PDF conversion service with SDK. Requires an API key from a specific vendor.
- No abstraction layer around any of these — swapping one requires code changes.

### 2.8 No unified project config

Each tool loads its own config independently (`classify_config.yaml`, `rewrite_config.yaml`, `prioritize_config.yaml`, `canonicalize_config.yaml`). There's no:
- Project-level config that points to tool configs
- Shared funder list (must be duplicated across configs)
- Single entry point for an agent to customize the whole pipeline

### 2.9 Mixed concerns in directory structure

- `rewrite_md/` is both intermediate and final output (prioritize adds to it, but it's also the final archive)
- `clean_md/` serves as input to classify, canonicalize source, and rewrite source — roles conflict
- No clear separation between stages, intermediates, and outputs

### 2.10 Missing adapter/extension points

- No pluggable converter interface (Datalab is hard-wired except for one `--pipeline-id` flag)
- No pluggable wiki backend interface (sage-wiki is assumed everywhere)
- No pluggable LLM provider (DeepSeek-specific pricing, `reasoning_effort` parameter, etc.)

### 2.11 Other issues

- `datalab-python-sdk` is not on public PyPI — it's a proprietary package
- No progress persistence across sessions (if you kill a run, you lose progress on `clean_md.py`)
- Error handling is inconsistent — some tools use exceptions, some return None, some print to stderr
- No structured logging — all output is `print()` with tqdm for progress
- `canonicalize.py` uses Python's `SequenceMatcher` which is O(n²) and slow on large corpuses
- The `errors: -1` convention (mark document for removal) is overloaded — it means both "empty body" and "should be removed"

---

## 3. What the New Repo Should Look Like

### 3.1 Design goals

1. **Installable**: `pip install llm-wiki` or `uv add llm-wiki`. Entry points for every tool.
2. **Org-agnostic**: Zero org-specific values in Python code. Everything in config.
3. **Pluggable converters**: Datalab default, but Marker, docling, pandoc, or custom converter can be swapped via config.
4. **Pluggable wiki backends**: sage-wiki default, but the interface is defined so other wiki tools can be plugged in.
5. **Pluggable LLM providers**: OpenAI-compatible API is the baseline. DeepSeek-specific features (thinking, reasoning_effort) are opt-in.
6. **Configurable by agents**: One project config YAML, one command to set up. Agents edit YAML, never Python.
7. **Maintainable by agents**: Clear pipeline stages, consistent error handling, resumable at any stage.
8. **Well-tested**: pytest test suite, CI/CD pipeline, integration tests for full pipeline runs.

### 3.2 Repository structure

```
llm-wiki/
├── README.md                   # User-facing: install, quickstart, what it does
├── AGENTS.md                   # Agent-facing: conventions, how to customize for a new org
├── PLAN.md                     # This file (design rationale, migration notes)
├── CHANGELOG.md
├── LICENSE
│
├── pyproject.toml              # Proper Python package with [project.scripts] entry points
├── requirements.lock / uv.lock
│
├── src/
│   └── llm_wiki/
│       ├── __init__.py
│       │
│       ├── cli/                # CLI entry points (one per tool)
│       │   ├── __init__.py
│       │   ├── clean.py        # llm-wiki clean
│       │   ├── classify.py     # llm-wiki classify
│       │   ├── rewrite.py      # llm-wiki rewrite
│       │   ├── prioritize.py   # llm-wiki prioritize
│       │   ├── canonicalize.py # llm-wiki canonicalize
│       │   ├── ingest.py       # llm-wiki ingest
│       │   ├── audit.py        # llm-wiki audit
│       │   ├── convert.py      # llm-wiki convert (standalone conversion)
│       │   └── pipeline.py     # llm-wiki pipeline (orchestrates full run)
│       │
│       ├── core/               # Business logic (no CLI coupling)
│       │   ├── __init__.py
│       │   ├── cleaner.py      # Deterministic markdown cleanup
│       │   ├── classifier.py   # File quality classification
│       │   ├── rewriter.py     # LLM re-authoring engine
│       │   ├── prioritizer.py  # Priority scoring engine
│       │   ├── canonicalizer.py # Version detection & dedup
│       │   ├── ingester.py     # Document ingestion logic
│       │   ├── auditor.py      # Wiki audit logic
│       │   ├── frontmatter.py  # Frontmatter parsing, generation, validation
│       │   ├── manifest.py     # Manifest file read/write/schema
│       │   └── errors.py       # Shared error/status types (enum)
│       │
│       ├── adapters/           # Pluggable external integrations
│       │   ├── __init__.py
│       │   ├── converters/     # PDF/DOCX/XLSX → Markdown converters
│       │   │   ├── __init__.py
│       │   │   ├── base.py     # Abstract Converter interface
│       │   │   ├── datalab.py  # Datalab converter (default)
│       │   │   ├── marker.py   # Marker-pdf converter
│       │   │   ├── docling.py  # Docling converter
│       │   │   └── pandoc.py   # Pandoc converter
│       │   ├── wiki/           # Wiki backend integrations
│       │   │   ├── __init__.py
│       │   │   ├── base.py     # Abstract WikiBackend interface
│       │   │   ├── sage_wiki.py # sage-wiki backend (default)
│       │   │   └── null.py     # No-op backend for testing
│       │   └── llm/            # LLM provider abstraction
│       │       ├── __init__.py
│       │       ├── base.py     # Abstract LLMProvider interface
│       │       └── openai_compatible.py  # OpenAI-compatible provider (covers DeepSeek, OpenAI, etc.)
│       │
│       ├── config/             # Configuration loading & validation
│       │   ├── __init__.py
│       │   ├── loader.py       # Unified config loader (reads project config + tool configs)
│       │   ├── schema.py       # Pydantic models for config validation
│       │   └── defaults.yaml   # Built-in defaults (merged with user config)
│       │
│       └── templates/          # Default prompt templates & rubric text
│           ├── rewrite.md      # Default re-authoring guide (NORMALIZE_REWRITE.md equivalent)
│           └── classify.yaml   # Default classification rules
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures (sample docs, mock API responses)
│   ├── test_cleaner.py
│   ├── test_classifier.py
│   ├── test_rewriter.py
│   ├── test_prioritizer.py
│   ├── test_canonicalizer.py
│   ├── test_frontmatter.py
│   ├── test_config.py
│   ├── test_adapters.py
│   ├── fixtures/               # Test fixture data (sample PDFs, markdown files)
│   └── integration/            # Full pipeline integration tests
│       └── test_pipeline.py
│
├── skills/                     # Agent skills (org-agnostic by default)
│   ├── opencode/
│   │   └── grant-writing/
│   │       └── SKILL.md       # Generic version — funder names come from wiki AGENTS.md
│   └── claude/
│       ├── grant-search.md
│       └── grant-draft.md
│
├── packs/                      # Org-type packs (shipped with tool)
│   └── arts-org/               # Sage-wiki pack for arts organizations
│       ├── pack.yaml
│       ├── prompts/
│       └── README.md
│
└── docs/
    ├── pipelines.md            # Pipeline stage documentation
    ├── config.md               # Configuration reference
    ├── converters.md           # Converter plugin guide
    ├── wiki-backends.md        # Wiki backend plugin guide
    └── frontmatter.md          # Frontmatter field reference
```

### 3.3 Package entry points

```toml
# pyproject.toml
[project.scripts]
llm-wiki = "llm_wiki.cli.pipeline:main"
llm-wiki-clean = "llm_wiki.cli.clean:main"
llm-wiki-classify = "llm_wiki.cli.classify:main"
llm-wiki-rewrite = "llm_wiki.cli.rewrite:main"
llm-wiki-prioritize = "llm_wiki.cli.prioritize:main"
llm-wiki-canonicalize = "llm_wiki.cli.canonicalize:main"
llm-wiki-ingest = "llm_wiki.cli.ingest:main"
llm-wiki-audit = "llm_wiki.cli.audit:main"
llm-wiki-convert = "llm_wiki.cli.convert:main"
```

### 3.4 Project configuration

A single `llm-wiki.yaml` in the project root ties everything together:

```yaml
# llm-wiki.yaml — project-level configuration
# This is the ONLY file an agent needs to create/customize for a new org.

project:
  name: "my-org-grant-archive"
  description: "Grant archive for My Organization"

# ── Organization identity ────────────────────────────────────────
org:
  name: "My Organization"         # Full org name
  abbreviation: "MYO"             # Short code

# ── Funders ──────────────────────────────────────────────────────
funders:
  "OAC": "Ontario Arts Council"
  "TAC": "Toronto Arts Council"
  "CCA": "Canada Council for the Arts"

# ── Document types ───────────────────────────────────────────────
doc_types: [application, report, budget, notification, activity_list,
            staff_board, support_material, agreement, notes, planning]

# ── Paths ────────────────────────────────────────────────────────
paths:
  raw_archive: "./_raw_archive/"   # Source PDFs/DOCX/XLSX
  raw_md: "./raw_md/"              # Raw markdown (after conversion)
  clean_md: "./clean_md/"          # Deterministically cleaned
  rewrite_md: "./rewrite_md/"      # LLM-rewritten (final archive)
  wiki_project: "./wiki/"          # Sage-wiki project directory

# ── Pipeline settings ────────────────────────────────────────────
pipeline:
  # Which stages to run (orchestrator mode)
  stages: [convert, clean, canonicalize, classify, rewrite, prioritize]

  # Classification rules (can be a separate file or inline)
  classification: "classify_config.yaml"

  # Rewrite settings
  rewrite:
    heading_taxonomy: "headings.yaml"   # Per-funder canonical headings
    rules_file: "rewrite_rules.md"      # Custom re-authoring guide

  # Priority settings
  prioritize:
    rubric: "priority_rubric.yaml"

# ── Converter ────────────────────────────────────────────────────
converter:
  type: "datalab"                 # datalab | marker | docling | pandoc
  datalab:
    pipeline_id: "pl_xxxxxxxx"
    api_key_env: "DATALAB_API_KEY"

# ── Wiki backend ─────────────────────────────────────────────────
wiki:
  type: "sage-wiki"               # sage-wiki | null (none)
  sage_wiki:
    binary_path: "sage-wiki"      # On PATH, or absolute path
    pack: "arts-org"              # Pack to apply (optional)

# ── LLM provider ─────────────────────────────────────────────────
llm:
  provider: "openai_compatible"
  base_url: "https://api.deepseek.com"
  api_key_env: "DEEPSEEK_API_KEY"
  models:
    fast: "deepseek-v4-flash"
    quality: "deepseek-v4-pro"
  pricing:                        # Per 1M tokens (for cost estimation)
    input: 0.14
    cached_input: 0.0028          # Provider-specific, omit if not supported
    output: 0.28

# ── Processing settings ──────────────────────────────────────────
processing:
  max_workers: 10
  requests_per_second: 5
  max_retries: 3
  resume: true                    # Enable checkpoint/resume
```

Agents onboard a new org by:
1. Creating `llm-wiki.yaml` and filling in funders, doc types, and org info
2. Creating `headings.yaml` with per-funder canonical section headings
3. Optionally creating a custom rules file, rubric, etc.
4. Running `llm-wiki pipeline` or individual stage commands

### 3.5 Pluggable interfaces

#### Converter interface

```python
# src/llm_wiki/adapters/converters/base.py

from abc import ABC, abstractmethod
from pathlib import Path

class Converter(ABC):
    """Convert a document (PDF, DOCX, XLSX) to markdown."""

    @abstractmethod
    def name(self) -> str:
        """Human-readable converter name."""
        ...

    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """File extensions this converter handles."""
        ...

    @abstractmethod
    def convert(self, source: Path) -> str | None:
        """Convert a file to markdown. Returns markdown string or None on failure."""
        ...
```

#### Wiki backend interface

```python
# src/llm_wiki/adapters/wiki/base.py

from abc import ABC, abstractmethod
from pathlib import Path

class WikiBackend(ABC):
    """Interface for wiki compilation and querying tools."""

    @abstractmethod
    def init(self, project_dir: Path, config: dict) -> None:
        """Initialize a new wiki project."""
        ...

    @abstractmethod
    def add_documents(self, source_paths: list[Path]) -> None:
        """Add documents to the wiki's raw directory."""
        ...

    @abstractmethod
    def compile(self) -> None:
        """Compile the wiki (generate summaries, concepts, articles)."""
        ...

    @abstractmethod
    def search(self, query: str) -> str:
        """Search the compiled wiki."""
        ...

    @abstractmethod
    def query(self, question: str) -> str:
        """Ask a question and get a synthesized answer."""
        ...
```

#### LLM provider interface

```python
# src/llm_wiki/adapters/llm/base.py

from abc import ABC, abstractmethod

class LLMProvider(ABC):
    """Interface for LLM API calls."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str,
                 model: str | None = None, max_tokens: int | None = None,
                 **extra_params) -> str:
        """Send a prompt and return the completion text."""
        ...
```

### 3.6 Frontmatter schema (Pydantic)

```python
from pydantic import BaseModel, Field, field_validator
from enum import Enum

class DocType(str, Enum):
    APPLICATION = "application"
    REPORT = "report"
    BUDGET = "budget"
    NOTIFICATION = "notification"
    ACTIVITY_LIST = "activity_list"
    STAFF_BOARD = "staff_board"
    SUPPORT_MATERIAL = "support_material"
    AGREEMENT = "agreement"
    NOTES = "notes"
    PLANNING = "planning"

class Frontmatter(BaseModel):
    """Validated YAML frontmatter for a grant document."""

    funder: str | None = None
    type: list[DocType] | DocType | None = None
    written: int | None = Field(None, ge=1990, le=2099)
    period: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    grant_amount: str | None = None
    priority: int | None = Field(None, ge=1, le=3)
    errors: int = 0

    @field_validator('grant_amount')
    @classmethod
    def must_be_quoted_string(cls, v):
        if v is not None and not isinstance(v, str):
            raise ValueError('grant_amount must be a string (e.g. "$50,000")')
        return v
```

### 3.7 Safer classification DSL (replacing eval)

Replace `eval()` conditions with a structured expression format:

```yaml
# Instead of:
#   condition: "has_type('guidelines') and corruption_score > 0.5"

# Use:
skip_rules:
  - conditions:
      - type: has_doc_type
        value: "guidelines"
      - type: field_gt
        field: corruption_score
        value: 0.5
    match: all                          # all | any
    reason: "Funder guidelines with high corruption"
```

Or implement a tiny safe expression evaluator that only allows predefined functions (`has_type`, `has_any_type`, `has_headings`, `has_tables`, etc.) and numeric comparisons — no arbitrary Python.

### 3.8 Error taxonomy

```python
# src/llm_wiki/core/errors.py

from enum import Enum

class FileStatus(str, Enum):
    """Status of a file in the pipeline."""
    OK = "ok"
    SKIPPED_GUIDELINES = "skipped_guidelines"
    SKIPPED_CORRUPTED = "skipped_corrupted"
    SKIPPED_TOO_SMALL = "skipped_too_small"
    SKIPPED_CV = "skipped_cv"
    SKIPPED_EMAIL = "skipped_email"
    SKIPPED_DRAFT = "skipped_draft"
    SKIPPED_NON_CANONICAL = "skipped_non_canonical"
    ERROR_CONVERSION = "error_conversion"
    ERROR_LLM = "error_llm"
    ERROR_PARSE = "error_parse"
    WARNING_CORRUPTION = "warning_corruption"

class ProcessingTier(str, Enum):
    """Classification tier for LLM re-authoring."""
    SKIP = "skip"
    MINIMAL = "minimal"
    LIGHT = "light"
    FULL = "full"
```

All tools use these enums in their output. The manifest tracks status per-file.

### 3.9 Manifest schema

Standardized JSON manifest used throughout the pipeline:

```json
{
  "project": "my-org-grant-archive",
  "generated": "2026-06-15T10:00:00Z",
  "files": {
    "OAC__2024_Application__final.md": {
      "status": "ok",
      "tier": "full",
      "funder": "OAC",
      "written": 2024,
      "type": ["application"],
      "content_lines": 350,
      "corruption_score": 0.02,
      "priority": 1,
      "errors": 0,
      "rewrite_cost_usd": 0.003
    }
  }
}
```

### 3.10 Pipeline orchestrator

A single `llm-wiki pipeline` command that runs all stages:

```bash
# Run full pipeline
llm-wiki pipeline --config my-org.yaml

# Run specific stages
llm-wiki pipeline --stages clean,classify,rewrite

# Dry run (estimate costs, preview what would happen)
llm-wiki pipeline --dry-run

# Resume from last checkpoint
llm-wiki pipeline --resume
```

The orchestrator:
1. Loads project config
2. Determines which stages to run
3. Runs each stage, collecting manifest data
4. Reports progress, costs, errors
5. Writes a final `pipeline-report.json` with per-file and aggregate statistics

---

## 4. Migration Plan (from prototype to production)

### Phase 1: Extract & package (no behavior changes)

1. **Create the new repo structure** with `src/` layout
2. **Move core logic** into `src/llm_wiki/core/` — extract functions from the prototype scripts into modules without changing behavior
3. **Create CLI wrappers** in `src/llm_wiki/cli/` that call the core modules (preserving existing CLI flags)
4. **Set up `pyproject.toml`** with proper entry points, Python 3.10+ requirement, test dependencies
5. **Add basic pytest tests** for `frontmatter.py` and `classifier.py` (the most complex logic)
6. **Keep the prototype as-is** — the new repo lives alongside, not replacing it

### Phase 2: Fix hardcoded values (API-preserving changes)

1. **Move ALL hardcoded InterAccess values to config**
   - `VALID_FUNDERS` → `llm-wiki.yaml` funders section
   - `VALID_DOC_TYPES` → `llm-wiki.yaml` doc_types
   - `PIPELINE_ID` → `llm-wiki.yaml` converter.datalab.pipeline_id
   - `USELESS_HEADINGS` → `classify_config.yaml`
   - `find_stale_content` addresses → `audit_config.yaml`
   - `TOPIC_KEYWORDS` → `find_stats_config.yaml`
2. **Add config validation** with Pydantic — fail fast with clear error messages
3. **Add `--config` flag** to all tools pointing to `llm-wiki.yaml`

### Phase 3: Pluggable adapters (new capabilities)

1. **Implement `Converter` interface** with Datalab as the default implementation
2. **Implement `WikiBackend` interface** with sage-wiki as the default
3. **Implement `LLMProvider` interface** with OpenAI-compatible as the default
4. **Add Marker converter** as an alternative (installed via optional dependency)
5. **Add a `null` wiki backend** for users who only want markdown, not a wiki

### Phase 4: Replace eval() and add safety

1. **Implement a structured condition DSL** for classification rules
2. **Parse existing YAML configs** and convert eval() conditions to the DSL
3. **Add validation** that all DSL conditions reference known fields/functions
4. **Add a migration helper** that converts old eval-based configs to the new DSL

### Phase 5: Pipeline orchestrator & project init

1. **Implement `llm-wiki init`** that scaffolds a project directory with config files
2. **Implement `llm-wiki pipeline`** orchestrator
3. **Add `llm-wiki status`** to show pipeline state (which stages done, file counts, costs)
4. **Add `llm-wiki config validate`** to check configs for errors

### Phase 6: Documentation, skills & testing

1. **Write `AGENTS.md`** for the new repo (agent conventions, customization guide)
2. **Write `README.md`** for users (install, quickstart, examples)
3. **Port agent skills** to be org-agnostic (use `{org_name}`, `{wiki_dir}` placeholders)
4. **Write integration tests** that run the full pipeline on a small fixture archive
5. **Set up CI/CD** with pytest, linting, and type checking

---

## 5. File Mapping (prototype → new repo)

| Prototype File | New Location | Notes |
|---|---|---|
| `fm_utils.py` | `src/llm_wiki/core/frontmatter.py` | Add Pydantic validation |
| `cli_utils.py` | `src/llm_wiki/cli/__init__.py` (shared helpers) | |
| `clean_md.py` | `src/llm_wiki/core/cleaner.py` + `cli/clean.py` | |
| `classify_files.py` | `src/llm_wiki/core/classifier.py` + `cli/classify.py` | Replace eval() |
| `classify_config.yaml` | `src/llm_wiki/templates/classify.yaml` | Default template |
| `rewrite_md.py` | `src/llm_wiki/core/rewriter.py` + `cli/rewrite.py` | |
| `rewrite_config.yaml` | Config merged into `llm-wiki.yaml` + `headings.yaml` | |
| `prioritize_files.py` | `src/llm_wiki/core/prioritizer.py` + `cli/prioritize.py` | |
| `prioritize_config.yaml` | Config merged into `llm-wiki.yaml` | |
| `canonicalize.py` | `src/llm_wiki/core/canonicalizer.py` + `cli/canonicalize.py` | |
| `canonicalize_config.yaml` | Config merged into `llm-wiki.yaml` | |
| `ingest.py` | `src/llm_wiki/core/ingester.py` + `cli/ingest.py` | Remove hardcoded funders |
| `datalab_retry.py` | `src/llm_wiki/adapters/converters/datalab.py` | Merge into converter |
| `audit_wiki.py` | `src/llm_wiki/core/auditor.py` + `cli/audit.py` | |
| `check_fm.py` | Merge into `frontmatter.py` + `cli/check.py` | |
| `find_pdf.py` | `src/llm_wiki/core/find_source.py` | |
| `find_long_paras.py` | Merge into `cleaner.py` | |
| `find_budget_tables.py` | Merge into `classifier.py` | |
| `find_stats.py` | `src/llm_wiki/core/stats.py` (optional) | Make org-agnostic |
| `select_for_import.py` | Merge into wiki backend adapter | |
| `NORMALIZE_REWRITE.md` | `src/llm_wiki/templates/rewrite.md` | Default template |
| `SAGE_WIKI.md` | `docs/wiki-backends.md` | Documentation |
| `AGENT_FIXER.md` | `docs/troubleshooting.md` | Documentation |
| `.opencode/skills/` | `skills/opencode/` | Make org-agnostic |
| `.claude/commands/` | `skills/claude/` | Make org-agnostic |
| `packs/arts-org/` | `packs/arts-org/` | Keep as-is |

---

## 6. Design Decisions & Tradeoffs

### 6.1 sage-wiki as default, but not required

sage-wiki is the default wiki backend because:
- It works well for this use case (the InterAccess prototype proved it)
- It produces plain markdown files that agents can read with normal tools
- It has a pack system for sharing ontologies
- It's a standalone Go binary with no Python dependency

But the `WikiBackend` interface means:
- Users who don't want a wiki can use the `null` backend (markdown files only)
- Users can plug in other wiki tools if they emerge
- The Python tooling doesn't depend on sage-wiki being installed

### 6.2 Datalab as default converter, pluggable

Datalab produced the best results for this specific domain (grant forms with complex tables). But:
- It requires a proprietary SDK and API key
- It costs money ($0.02–0.05 per page)
- Not all arts orgs will want to pay for it

By making converters pluggable, Marker (free, local) can be the default for cost-sensitive users, with Datalab as the "premium" option for quality.

### 6.3 YAML frontmatter instead of a database

The prototype's choice of YAML frontmatter as the data layer is correct for this problem:
- Files are self-describing (no database needed)
- Agents can search with grep, rg, or Python (no query language)
- The wiki can index frontmatter fields directly
- Files can be moved, copied, backed up with standard tools

We keep this pattern. Adding a database would be over-engineering.

### 6.4 Backward compatibility

The new repo is a fresh start. We don't maintain backward compatibility with the prototype's:
- Directory structure
- Internal config format
- Python API (there isn't one — it's all CLI)

But we DO maintain compatibility with:
- The YAML frontmatter format (so existing `rewrite_md/` files work)
- The filename convention (as one supported convention, not the only one)
- The agent workflow (sage-wiki search + agentmap headings + read files)

### 6.5 Python version

Lower the requirement from 3.14 to 3.10:
- 3.10 is the oldest version still in common use that supports all needed features
- 3.14 is a preview release (October 2026 expected) — excluding 99% of users
- Use `from __future__ import annotations` for newer typing syntax on 3.10

---

## 7. Usability & Adoption (What the Plan Misses)

The sections above cover technical architecture. But for real-world adoption by non-technical arts orgs and viability as a service offering, the following are equally critical.

### 7.1 Problem: Arts orgs have zero technical staff

The typical user is an executive director, program manager, or grant writer. They can use Google Docs and maybe Excel. They cannot:
- Clone a git repo
- Install Python or uv
- Edit YAML files
- Run CLI commands
- Manage API keys
- Debug pipeline failures

**The current plan requires all of these.** Even with the best `AGENTS.md`, the onboarding friction is too high for this audience. The tool needs to be self-service for non-technical users, with the agent/service layer handling the heavy lifting.

### 7.2 The onboarding experience gap

The current plan has `llm-wiki init` scaffolding config files. This is insufficient. The real onboarding workflow needs to be:

```
1. User points the tool at their document folder (or Google Drive)
2. Tool scans everything and produces a "What We Found" report:
   - "We found 847 documents: 512 PDFs, 201 DOCX, 134 XLSX"
   - "We detected 4 funders: OAC (203 docs), TAC (156 docs), CCA (89 docs), BCAH (52 docs)"
   - "Documents span 2010–2025"
   - "We flagged 47 likely-draft documents for review"
   - "Estimated pipeline cost: $2.10"
3. User confirms or tweaks: "Yes, those are our funders. Add SOCAN too."
4. Tool runs the pipeline with progress visible
5. Tool produces a shareable "Archive is ready" report
```

**Specific features needed:**

#### Archive scanner (`llm-wiki scan`)
```bash
llm-wiki scan ./my-documents/
# Output:
#   Scanned: 847 files (512 pdf, 201 docx, 134 xlsx)
#   Detected funders: OAC (203), TAC (156), CCA (89), BCAH (52)
#   Year range: 2010 – 2025
#   Likely drafts: 47 (show list?)
#   Unrecognized: 132 files (show list?)
#   Estimated LLM cost: $2.10 – $3.50
#   Estimated wall time: 45 minutes
#
#   Next step: llm-wiki init --from-scan scan-report.json
```

The scanner uses the same regex patterns from `classify_config.yaml` but runs them against raw filenames (before conversion) to give an early assessment. It doesn't need API keys or dependencies beyond filesystem access.

#### Guided init (`llm-wiki init --guided`)
An interactive setup that asks non-technical questions:
```
llm-wiki init --guided

Welcome to llm-wiki! Let's set up your grant archive.

What's your organization's name? [InterAccess]
What folder contains your grant documents? [./my-docs/]
  Scanning... found 847 documents.

What funders do you apply to? (comma-separated)
  [OAC, TAC, CCA, BCAH]

  I found these funders in your documents: OAC, TAC, CCA, BCAH, SOCAN
  Use these? [Y/n]

What's your DeepSeek API key? (or enter later)
  [sk-...]

Configuration written to llm-wiki.yaml.
Next step: llm-wiki pipeline --dry-run   (preview without cost)
         llm-wiki pipeline               (run the full pipeline)
```

#### Pre-built org profiles
Instead of configuring funders, doc types, and heading taxonomies from scratch, the tool ships with profiles for common Canadian arts org types:

```yaml
# Built-in profile: canadian-artist-run-centre
# Activates with: llm-wiki init --profile canadian-artist-run-centre
funders:
  OAC: Ontario Arts Council
  TAC: Toronto Arts Council
  CCA: Canada Council for the Arts
  BCAH: Canadian Heritage
  SOCAN: SOCAN Foundation
  FACTOR: FACTOR
doc_types: [application, report, budget, notification, activity_list,
            staff_board, support_material, agreement]
# Pre-configured heading taxonomies for OAC/TAC/CCA/BCAH application forms
```

Profiles to ship:
| Profile | Typical funders |
|---|---|
| `canadian-artist-run-centre` | OAC, TAC, CCA, BCAH, SOCAN |
| `canadian-gallery` | OAC, TAC, CCA, BCAH, private foundations |
| `canadian-festival` | BCAH, CCA, OAC, TAC, FACTOR, SOCAN |
| `canadian-theatre` | CCA, OAC, TAC, BCAH |
| `canadian-dance` | CCA, OAC, TAC, BCAH |
| `generic-canadian-arts` | (empty — manual config, but with Canadian funder hints) |
| `generic` | (fully empty — for non-Canadian orgs) |

Each profile also pre-configures the sage-wiki `arts-org` pack and reasonable defaults for classification, canonicalization, and priority rubrics. An org in Toronto applying to OAC/TAC/CCA gets a working setup in one command.

### 7.3 Web dashboard

A CLI tool is fine for agents and developers. For an executive director or grant writer, it's unusable. A lightweight local web UI bridges this gap:

```
llm-wiki serve
# Opens http://localhost:8900
```

**Dashboard pages:**

1. **Status** — pipeline progress, file counts per stage, last run time, errors
2. **Costs** — LLM spend this month, per-pipeline cost, projected costs for re-run
3. **Browse** — search and view documents in `rewrite_md/`, filter by funder/year/type/priority
4. **Search** — simple search box that queries both the wiki and raw markdown (backed by sage-wiki search + agentmap)
5. **Ingest** — drag-and-drop new documents for ingestion (calls `llm-wiki ingest` behind the scenes)
6. **Pipeline** — "Start Pipeline" button with dry-run preview, stage selection, progress bar
7. **Config** — web form to edit funders, doc types, and basic settings (no YAML editing)

**Architecture:**
- Backend: FastAPI or Flask serving the dashboard, calling llm-wiki's core modules directly (no subprocess calls)
- Frontend: Minimal HTML/CSS with htmx or Alpine.js (no React build step, no npm)
- Authentication: Optional password or API key for service mode
- Runs locally by default (localhost only), with optional `--host 0.0.0.0` for remote access

**Why a web dashboard matters for your service offering:**
- You can check an org's pipeline status remotely (with their permission)
- Non-technical users can see progress without asking you "is it done yet?"
- The "Ingest" page means they can add new documents themselves without calling you
- The search page means they can start using the archive before they learn agent skills
- It's the difference between "we paid someone to set up some technical thing" and "we have a grant archive we use daily"

### 7.4 Service mode

For your service offering, you need to manage multiple orgs. The tool should support a "service mode" that connects to a lightweight coordination service you host:

```bash
# Org side (one-time setup)
llm-wiki service register --org "InterAccess" --key "ia-2026-xxxx"

# Your side
llm-wiki service dashboard    # Web UI showing all orgs
llm-wiki service orgs         # List registered orgs
llm-wiki service status ia    # Check InterAccess pipeline status
llm-wiki service trigger ia pipeline  # Remote-trigger a pipeline run
```

**Service mode features:**
- **Health monitoring**: Know when an org's pipeline failed, when their API key expired, when they haven't ingested new docs in 6 months
- **Cost tracking**: Aggregate LLM spend across all orgs, per-org breakdown, alerts on unusual costs
- **Remote assistance**: View an org's pipeline output, error logs, and config from your dashboard
- **Version management**: Know which version of llm-wiki each org is running, push updates
- **Usage analytics**: Which orgs search most, which funders get the most attention, which document types are most ingested
- **Billing**: Track your service hours/retainer against each org

**Architecture decisions for service mode:**
- The service coordination layer is a separate, closed-source component (the value-add)
- llm-wiki itself stays fully open source and works standalone
- Service mode is an opt-in flag: `llm-wiki --service-url https://service.llm-wiki.io`
- Communication is pull-based (org tool checks in) not push-based (no open ports needed)
- All data stays on the org's machine; the service only receives status metadata (file counts, costs, errors, not document contents)

**Business model alignment:**
- Open source tool = free, anyone can use it
- Service dashboard = your value-add (setup, monitoring, training, support)
- Orgs can self-serve if they have technical staff; they pay you if they don't
- The tool getting better makes your service more valuable (virtuous cycle)
- Pre-built profiles reduce your onboarding time per org from days to hours

### 7.5 Cloud storage integration

Most arts orgs don't have their documents on a local filesystem. They're in Google Drive, Dropbox, or SharePoint. The tool needs to pull from these sources:

```bash
# Google Drive
llm-wiki scan gdrive://folder-id
llm-wiki pipeline --source gdrive://folder-id

# Dropbox
llm-wiki scan dropbox://path/to/folder

# Local folder (current behavior)
llm-wiki scan ./my-docs/
```

**Implementation approach:**
- Cloud connectors are optional dependencies (`llm-wiki[gdrive]`, `llm-wiki[dropbox]`)
- Each connector implements a `DocumentSource` interface that lists and downloads files
- Files are cached locally during pipeline processing (in `_raw_archive/`)
- API credentials are stored in `llm-wiki.yaml` (or pulled from env vars)

```python
class DocumentSource(ABC):
    """Abstract source of documents (local filesystem, cloud storage, etc.)."""

    @abstractmethod
    def list_files(self) -> list[FileRef]:
        """List all available files with metadata (name, size, modified)."""
        ...

    @abstractmethod
    def download(self, ref: FileRef, dest: Path) -> Path:
        """Download a file to local storage. Returns path to downloaded file."""
        ...
```

**Why this matters for adoption:**
- The #1 onboarding friction is "how do I get my documents into the tool?"
- Arts orgs have messy archives scattered across cloud services
- "Just point it at your Google Drive folder" is a 10-second setup
- Without this, you spend hours helping each org export/download/organize their files

### 7.6 Built-in training: `llm-wiki teach`

The training component of your service can be partially productized into the tool itself:

```bash
llm-wiki teach
```

Launches an interactive tutorial that walks the user through:
1. **"Find a past application"** — guided search for their first grant
2. **"Extract a stat"** — find demographics or budget figures
3. **"Draft a section"** — compose a grant section using precedent
4. **"Ingest a new document"** — add a freshly-written grant

Each lesson uses the org's actual data (not sample data) and produces real output. By the end of the tutorial, the user has successfully performed the 4 core workflows with their own archive.

**Tutorial format:**
- Terminal-based (works over SSH for remote training sessions)
- Each step has a clear "what you're doing" explanation, then a task, then verification
- Completion badges/progress (gamification for engagement)
- Generates a "cheat sheet" PDF with the commands they used — they can refer back to it

**Why this matters for your service:**
- Training is the hardest part to scale — you can only do so many 1:1 sessions
- A self-guided tutorial means orgs can onboard themselves or refresh their knowledge
- You can still sell "advanced training" (custom heading taxonomies, complex funder research)
- The tutorial doubles as documentation that's always in sync with the current version

### 7.7 Cost transparency

Arts orgs are budget-conscious. Every API call must show its cost before it runs:

```
$ llm-wiki pipeline --dry-run

Pipeline preview for "InterAccess Grant Archive"
─────────────────────────────────────────────────
Stage           Files    Est. Cost    Est. Time
convert         500 pdf  $10.00       25 min   (Datalab)
clean           847 md   $0.00        <1 min
canonicalize    847 md   $0.00        2 min
classify        800 md   $0.00        <1 min
rewrite         750 md   $2.10        30 min   (DeepSeek)
prioritize      750 md   $0.45        8 min    (DeepSeek)
wiki compile    750 md   $3.80        45 min   (DeepSeek + OpenAI embed)
─────────────────────────────────────────────────
TOTAL                    $16.35       ~110 min

Note: Datalab costs are estimates based on page counts.
      Actual costs may vary. No API calls will be made in dry-run mode.

Run without --dry-run to start: llm-wiki pipeline
```

Cost tracking over time:
```
$ llm-wiki costs

LLM Costs — InterAccess Grant Archive
─────────────────────────────────────
Month         Pipeline    Wiki     Total
June 2026     $2.10       $3.80    $5.90
May 2026      $0.00       $0.45    $0.45   (wiki recompile only)
April 2026    $0.00       $0.00    $0.00
─────────────────────────────────────
All time:     $6.35
```

### 7.8 One-click deployment

The tool should be installable without Python knowledge:

**Option A: Docker**
```bash
docker run -v ./my-docs:/docs -v ./archive:/archive llmwiki/llm-wiki pipeline
```

**Option B: pipx (recommended for non-technical users)**
```bash
pipx install llm-wiki
llm-wiki init --guided
```

**Option C: curl installer**
```bash
curl -fsSL https://get.llm-wiki.io | bash
# Installs uv, Python, and llm-wiki in an isolated environment
# Prompts for API keys, then launches guided init
```

**Option D: GitHub Codespaces / cloud dev environment**
One-click button in README that opens a pre-configured environment with everything installed. The user just needs to upload documents and provide API keys.

### 7.9 The org's wiki AGENTS.md as the linchpin

The prototype has `sage_wiki_3/wiki/AGENTS.md` — a small file that maps common grant-writing questions to specific concept files. This is the most underappreciated piece of the whole system. For the new tool:

- `llm-wiki init` should auto-generate a draft `wiki/AGENTS.md` from the detected funders and document types
- The wiki compile step should update it with actual concept file paths
- Agent skills should reference `wiki/AGENTS.md` as their first stop for org-specific context
- The service offering should include "tune your AGENTS.md" as a deliverable

A well-written `wiki/AGENTS.md` makes the difference between "we have a wiki somewhere" and "agents can answer questions instantly."

---

## 8. Agent Skills & Always-On Assistant Architecture

The pipeline produces the archive. The skills teach agents how to use it. The assistant is the delivery mechanism. These three layers are distinct but must be designed together.

### 8.1 What exists: a 3-layer skills architecture

The prototype has 1,350 lines of agent instruction content across 4 files, forming three layers:

```
Layer 3: Grant Writing Craft    grant_writing_prompt.md  (600 lines)
         ├── Two-pass workflow (fact draft → narrative rewrite)
         ├── Section-level rules (Context, Past Cycle, Diversity, etc.)
         ├── Tone, juror test, anti-patterns
         ├── Character count management
         └── Quick reference checklist

Layer 2: Drafting               grant-draft.md           (163 lines)
         ├── Funder-specific tone guide (OAC/TAC/CCA/BCAH)
         ├── Section-by-section drafting instructions
         ├── Annotated output format with sources
         └── "Search first, then draft" workflow

Layer 1: Archive Search          SKILL.md                 (380 lines)
         ├── Two-tool search model (sage-wiki + agentmap)
         ├── 7 common grant-writing workflows
         ├── Wiki directory structure
         ├── Document types, funders, priority levels
         └── Frontmatter field reference

         grant-search.md         (207 lines)
         └── Same search patterns, different format (Claude slash command)
```

**Layer 1** teaches the agent *how to find* information. **Layer 2** teaches it *how to assemble* found information into grant text. **Layer 3** teaches it *how to write* effective grant applications — this is the domain expertise distilled from years of real grant writing.

### 8.2 The grant_writing_prompt.md is the crown jewel

This 600-line document is the most valuable asset in the repo. It encodes real expertise:

- **Two-pass workflow**: Pass 1 collects every fact from the archive with source traceability. Pass 2 rewrites for narrative quality, tone, and juror appeal — but every number stays exact and traceable.
- **Scaffolding approach**: Before writing, the agent builds a internal criteria map and 3-sentence core argument. Every section must advance that argument.
- **The Juror Test**: "Would a juror who has never heard of my organization understand this paragraph?"
- **15 anti-patterns**: Catalogue mode, corporate-speak, hedging, burying the lead, under-using available space, etc.
- **Section-specific guidance**: Every section of a grant application has its own rules, from Context through Goals.
- **Confirmation system**: `[CONFIRM: ...]` markers let the agent flag uncertainties for human review without slowing down the draft.
- **Character count management**: `count_chars.py` integrates with the writing workflow to track limits.

This document is almost entirely org-agnostic. The only InterAccess-specific content is in the examples (which are clearly marked as examples). For the new repo, this should be in `skills/grant-writing.md` alongside the search/draft skills, with `{org_name}` placeholders.

### 8.3 Current skills are platform-specific; they need to be platform-agnostic

| File | Platform | Format |
|------|----------|--------|
| `SKILL.md` | OpenCode | YAML frontmatter + markdown |
| `grant-search.md` | Claude Code | Slash command |
| `grant-draft.md` | Claude Code | Slash command |
| `grant_writing_prompt.md` | Universal | Markdown (referenced by SKILL.md) |

The content is excellent, but it's locked to two specific coding agent platforms. For an always-on assistant (OpenClaw, Hermes Agent, or any chatbot-style deployment), the skills need to be:

1. **Platform-agnostic** — the instruction content is separated from the platform format
2. **Composable** — an assistant can load all three layers, or just Layer 1 (search-only assistant), or Layer 3 (grant-writing craft for a human-assisted workflow)
3. **Configurable** — funder names, org name, directory paths, and preferred tone are templated from the project config (`llm-wiki.yaml`)
4. **Versioned** — skills improve over time; assistants should know which version they're using

### 8.4 Proposed skills directory structure

```
skills/
├── README.md                        # What skills are, how to deploy them
│
├── core/                            # Platform-agnostic instruction content
│   ├── archive-search.md            # Layer 1: How to search the archive
│   ├── grant-drafting.md            # Layer 2: How to draft from search results
│   └── grant-writing-craft.md       # Layer 3: The 600-line writing guide
│
├── platforms/                       # Platform-specific wrappers
│   ├── opencode/
│   │   └── grant-writing/
│   │       └── SKILL.md             # Wraps core/ with OpenCode YAML format
│   ├── claude/
│   │   ├── grant-search.md          # Wraps core/archive-search.md
│   │   └── grant-draft.md           # Wraps core/grant-drafting.md
│   ├── openclaw/                    # NEW: OpenClaw assistant config
│   │   ├── system-prompt.md         # Full system prompt loading all 3 layers
│   │   └── tools.yaml               # Tool definitions (sage-wiki, agentmap, files)
│   └── hermes/                      # NEW: Hermes Agent config
│       └── agent.yaml
│
└── templates/                       # Org-specific customization points
    ├── funders.md                    # {funder_table} — auto-generated from config
    ├── organization.md               # {org_context} — auto-generated from config
    └── wiki-agents.md                # Template for wiki/AGENTS.md
```

The `core/` files use `{placeholders}` that get filled from `llm-wiki.yaml`:

```markdown
# core/archive-search.md (excerpt)

## Your organization's archive

- **Markdown files**: `{rewrite_md_path}` — all documents with YAML frontmatter
- **Wiki**: `{wiki_path}` — compiled concepts, summaries, ontology graph
- **Search tools**: sage-wiki (cross-document synthesis) + agentmap (section-level)

## Funders

{funder_table}

## Document types

{doc_type_table}
```

When an org runs `llm-wiki skills generate`, it produces platform-specific skill files with the org's actual funders, paths, and wiki structure filled in.

### 8.5 Always-on assistant design

An always-on assistant (OpenClaw, Hermes, or a custom chat interface) differs from a coding agent:

| Aspect | Coding agent (OpenCode, Claude) | Always-on assistant |
|--------|-------------------------------|---------------------|
| Invocation | Triggered by slash command or comment | Always available in chat |
| Context | Fresh each invocation | Persistent conversation |
| User | Technical (knows CLI, git) | Non-technical (executive director, grant writer) |
| Task scope | "Find past OAC apps" → returns results | "Draft my OAC application" → multi-turn workflow |
| State | Stateless | Stateful — remembers what was searched earlier |
| Tools | Full filesystem access, bash, Python | Limited to search tools + file read |

The assistant needs:

1. **A system prompt** that loads all 3 skill layers, plus org context from `wiki/AGENTS.md`
2. **Tool access** to sage-wiki search/query and agentmap search/headings
3. **A conversation loop** that can do multi-turn grant drafting:
   ```
   User: "I need to write my OAC operating grant."
   Assistant: "Let me find your past OAC applications first. [searches]
              I found applications from 2022-2025. Which sections do you want help with?"
   User: "Start with the organizational context section."
   Assistant: [searches for org descriptions across past apps]
              [drafts a section grounded in precedent]
              [shows sources]
              "Here's a draft. The character limit for this section is 7,500."
   ```
4. **Clear boundary awareness**: The assistant drafts, but a human submits. It never claims finality — it always leaves `[CONFIRM]` markers and a confirmation list.

### 8.6 Skills as the bridge between pipeline and assistant

The pipeline produces data. The assistant consumes it. The skills are the instruction manual for the assistant. This is the relationship:

```
llm-wiki pipeline        →  rewrite_md/ + wiki/     (data)
llm-wiki skills generate →  skills/<platform>/       (instructions, auto-filled with org data)
Assistant loads          →  skills/ + wiki/AGENTS.md (context + instructions + data)
```

A new org's onboarding flow would be:

```bash
# 1. Run the pipeline
llm-wiki pipeline

# 2. Generate skills for the assistant platform(s) you use
llm-wiki skills generate --platform openclaw  # produces system prompt + tool config
llm-wiki skills generate --platform opencode  # produces .opencode/skills/
llm-wiki skills generate --platform hermes    # produces hermes agent config

# 3. Deploy to your assistant
cp skills/platforms/openclaw/* ~/.openclaw/agents/grant-writer/
```

### 8.7 What the skills need to be production-ready

The current skills have InterAccess-specific content baked in. For the new repo:

| Issue | Fix |
|-------|-----|
| Hardcoded funder names (OAC, TAC, CCA, BCAH) | `{funder_table}` placeholder, filled from `llm-wiki.yaml` |
| Hardcoded directory paths (`sage_wiki_3/`, `rewrite_md/`) | `{wiki_path}`, `{rewrite_md_path}` from config |
| Hardcoded org name ("InterAccess") | `{org_name}` from config |
| Platform-specific formats (OpenCode YAML, Claude slash command) | Core content in `core/`, platform wrappers in `platforms/` |
| No versioning | Skills get a version number; `llm-wiki skills generate` stamps it |
| grant_writing_prompt.md is referenced but not formally part of skill loading | Promoted to `core/grant-writing-craft.md`, loaded as Layer 3 |
| Funder tone guide mentions specific funders | Generalized: "each funder has a tone — check `wiki/AGENTS.md` for funder-specific guidance" |

### 8.8 The assistant IS the product

For most arts orgs, the assistant is the only interface they'll ever use. They won't run `sage-wiki search` or `agentmap headings`. They'll type:

> "What was our last TAC grant amount?"

And the assistant will search, find, and answer. The pipeline and skills exist to make that answer accurate.

This has implications for the product design:
- The web dashboard should include a chat interface (the assistant, embedded)
- The service offering should include setting up and configuring the assistant
- Training should focus on "how to talk to the assistant" — not on CLI tools
- The `llm-wiki teach` tutorial should be delivered through the assistant itself

### 8.9 Skills for specific admin tasks (beyond grant writing)

The grant-writing skills are the most developed, but an always-on assistant could help with other admin tasks if skills exist:

| Skill | What it does | Status |
|-------|-------------|--------|
| `grant-search` | Search archive for precedent | Exists (Layer 1) |
| `grant-draft` | Compose grant sections | Exists (Layer 2) |
| `grant-write` | Full grant writing workflow | Exists (Layer 3) |
| `board-report` | Summarize recent activity for board | Not built |
| `budget-review` | Compare budget actuals against plan | Not built |
| `artist-bio` | Extract artist bios from exhibition docs | Not built |
| `funding-calendar` | Track grant deadlines from archive | Not built |
| `impact-stats` | Compile demographic/attendance stats | Not built |
| `org-history` | Answer "what year did we..." questions | Not built (wiki does this partially) |

These are natural extensions. The skills architecture should make it easy to add new capabilities by writing a new `core/<skill>.md` file, without touching pipeline code.

---

## 9. Revised Migration Plan

### Phase 1: Core pipeline + skills (what we build now)

This phase produces a working, pip-installable tool that can process an archive end-to-end and produce agent-usable output. Everything after this can be built by agents on demand.

1. **Extract & package** the prototype into a proper Python package with `src/` layout and CLI entry points
2. **Fix hardcoded values** — move ALL InterAccess-specific config out of Python into YAML
3. **Pluggable adapters** — Converter, WikiBackend, LLMProvider interfaces with defaults (Datalab, sage-wiki, DeepSeek)
4. **Replace eval()** with safe condition DSL in classify
5. **Pipeline orchestrator** (`llm-wiki pipeline`) with checkpoint/resume and cost tracking
6. **Skills platform** — extract the 1,350 lines of agent instructions into platform-agnostic core files with `{placeholders}`, implement `llm-wiki skills generate`
7. **Pre-built profiles** — `canadian-artist-run-centre` and a few others, so a new org can `llm-wiki init --profile canadian-artist-run-centre` and get working config instantly
8. **Archive scanner** (`llm-wiki scan`) — scan raw files, detect funders/years/types, estimate costs
9. **Guided init** (`llm-wiki init --guided`) — interactive setup
10. **pytest test suite** for frontmatter, classifier, config validation

**Phase 1 exit criteria:** InterAccess can run `llm-wiki pipeline` against their archive and get the same output the prototype produces, with no hardcoded InterAccess values in Python. An agent dropped into a new org's repo can run `llm-wiki init --profile canadian-artist-run-centre`, edit one YAML file, and run the pipeline.

### Phase 2: Usability (agents build as needed)

These improve the experience for non-technical users but aren't needed for the system to work. Each can be built by an agent when an org needs it.

1. **Web dashboard** (`llm-wiki serve`) — FastAPI + htmx, status/browse/search/ingest pages, embedded chat
2. **One-click deployment** — Docker image, pipx recipe, curl installer
3. **Cost transparency** — `--dry-run` cost estimates, `llm-wiki costs` history
4. **`llm-wiki teach`** — interactive tutorial delivered through the assistant

### Phase 3: Cloud & service (when you're scaling)

These are for when you have 3+ orgs and need to manage them efficiently.

1. **Cloud storage connectors** — Google Drive, Dropbox
2. **Service mode** — multi-org monitoring, remote management, health alerts
3. **Service coordination layer** — separate repo, your value-add

### Phase 4: Additional skills (organic)

New admin skills as demand emerges: board-report, funding-calendar, impact-stats, artist-bio. Each is a `skills/core/<task>.md` file — agents can write new ones without touching pipeline code.

---

## 10. Revised Directory Structure (final)

```
llm-wiki/
├── src/
│   └── llm_wiki/
│       ├── cli/              # CLI entry points
│       │   ├── clean.py, classify.py, rewrite.py, prioritize.py
│       │   ├── canonicalize.py, ingest.py, audit.py
│       │   ├── scan.py        # NEW: archive scanner
│       │   ├── skills.py      # NEW: skills generation
│       │   ├── teach.py       # NEW: interactive tutorial
│       │   └── pipeline.py    # Pipeline orchestrator
│       │
│       ├── core/             # Business logic (no CLI coupling)
│       │   ├── cleaner.py, classifier.py, rewriter.py
│       │   ├── prioritizer.py, canonicalizer.py
│       │   ├── ingester.py, auditor.py, scanner.py
│       │   ├── frontmatter.py, manifest.py, errors.py
│       │   └── skills.py      # NEW: skills generation logic
│       │
│       ├── adapters/         # Pluggable integrations
│       │   ├── converters/   # PDF → MD: datalab, marker, docling, pandoc
│       │   ├── wiki/         # Wiki backends: sage_wiki, null
│       │   ├── llm/          # LLM providers: openai_compatible
│       │   └── sources/      # Document sources: local, gdrive, dropbox
│       │
│       ├── config/           # Config loading & validation (Pydantic)
│       ├── templates/        # Default prompts, rules, profiles, packs
│       ├── web/              # Web dashboard (FastAPI + htmx + chat)
│       └── service/          # Service mode client
│
├── skills/                   # Agent skills (platform-agnostic core + wrappers)
│   ├── README.md
│   ├── core/                 # Platform-agnostic instruction content
│   │   ├── archive-search.md
│   │   ├── grant-drafting.md
│   │   └── grant-writing-craft.md
│   ├── platforms/            # Platform-specific wrappers
│   │   ├── opencode/
│   │   ├── claude/
│   │   ├── openclaw/
│   │   └── hermes/
│   └── templates/            # Org-specific fill-in templates
│
├── tests/
├── docs/
│   ├── pipelines.md
│   ├── config.md
│   ├── converters.md
│   ├── wiki-backends.md
│   ├── frontmatter.md
│   └── skills.md
└── docker/
```

---

## 11. Open Questions (final)

1. **agentmap integration**: Currently an external Go binary. Bundle as optional dependency via `pip install llm-wiki[agentmap]`, or reimplement heading extraction + fuzzy matching as a Python library within llm-wiki (~500 lines of Go to port). The Python port removes a binary dependency and makes pip-install complete.

2. **sage-wiki pack registry**: Publish the `arts-org` pack to the sage-wiki registry so it's installable via `sage-wiki pack install arts-org`, or bundle it in this repo as `llm-wiki/templates/packs/`?

3. **Licensing**: MIT for the tool. Service coordination layer: AGPL to discourage cloud competitors, or MIT to maximize adoption?

4. **Multi-tenancy**: Standalone mode for single org, service mode for multi-org. Both first-class.

5. **Web dashboard scope**: Status + browse + search + ingest + chat in first iteration. Full pipeline management stays CLI-only initially.

6. **Cloud storage auth flow**: Start with service account keys for Google Drive, add OAuth later.

7. **Service pricing model**: Per-org monthly ($50–200/mo) with setup fee ($500–2000). Standard arts org SaaS model.

8. **Docs-only mode**: First-class mode for orgs that only want markdown pipeline without wiki: `llm-wiki pipeline --no-wiki`.

9. **Translation/multilingual**: French document support for Canadian arts orgs. Detect language, route to French heading taxonomy. Phase 6+.

10. **Assistant platform priority**: OpenClaw vs Hermes vs custom? Build the core skills platform-agnostic, then implement platform wrappers. Start with whichever the first paying customer uses.

11. **Chat interface in dashboard vs separate assistant**: Should the dashboard include a built-in chat (simpler, single interface) or delegate to an external assistant (OpenClaw/Hermes)? Recommend: both. Dashboard has a basic chat powered by the same skills. External assistant integration is for orgs that already use one.

---

## 12. Summary

The prototype works. For $2.65 in LLM costs and 1,350 lines of agent instruction content, it turned InterAccess's 1,033-file archive into a wiki that agents can search and draft from.

The production plan has two tiers:

**Tier 1 — Build now (core pipeline + skills):** A pip-installable Python package with pluggable converters/wiki/LLM backends, safe classification DSL, pipeline orchestrator with checkpoint/resume, and a skills platform that generates platform-agnostic agent instructions from org config. This is what makes the system work for InterAccess (first customer) and what agents need to onboard new orgs by editing YAML, not Python.

**Tier 2 — Agents build as needed (usability, cloud, service):** Web dashboard, cloud storage connectors, service mode, training tools. Each can be built by an agent when an org needs it. The core is solid enough that the rest is scaffolding.

The key insight from the prototype is that this works because of three things working together:
1. **Clean markdown with YAML frontmatter** — self-describing files, no database
2. **Two search tools** — wiki for synthesis, agentmap for exact passages
3. **Well-written agent instructions** — 1,350 lines teaching agents how to search, draft, and write grants

Everything else — the web dashboards, the cloud connectors, the service coordination — is delivery mechanism. The core is right.
