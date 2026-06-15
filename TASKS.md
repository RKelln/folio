# TASKS.md — folio production build

## Goal

Working production pipeline that InterAccess can run against their archive, producing the same output as the `llm_wiki` prototype, but with **zero hardcoded org-specific values in Python**. An agent can onboard a new org by editing YAML config files.

## Task status

- [ ] **Not started**
- [~] **In progress**
- [x] **Done**

---

## Phase 1: Core pipeline (porting from prototype)

### 1.1 Foundation

- [ ] **Port `frontmatter.py`** from prototype `fm_utils.py`
  - Port all functions: `parse_frontmatter`, `dict_to_frontmatter`, `update_frontmatter`, `strip_existing_frontmatter`, `sanitize_frontmatter`, `extract_year`, `get_file_year`, `normalize_field_aliases`, `normalize_field_values`, `apply_frontmatter`
  - Remove inline `_run_tests()` (they move to `tests/test_frontmatter.py`)
  - Add Pydantic `Frontmatter` model for validation
  - Keep the field alias maps (`_FIELD_ALIASES`, `_TYPE_VALUES`) — they are generic

- [ ] **Implement `errors.py`** — shared error/status taxonomy
  - `FileStatus` enum (ok, skipped_guidelines, skipped_corrupted, skipped_too_small, skipped_cv, skipped_email, skipped_draft, skipped_non_canonical, error_conversion, error_llm, error_parse)
  - `ProcessingTier` enum (skip, minimal, light, full)

- [ ] **Implement `manifest.py`** — JSON manifest read/write
  - `load_manifest(path)` — read existing manifest
  - `save_manifest(path, data)` — write manifest
  - `update_file_status(manifest, filename, **fields)` — update a file entry
  - `manifest_summary(manifest)` — counts by status/tier/funder

### 1.2 Pipeline stages

- [ ] **Port `cleaner.py`** from prototype `clean_md.py`
  - Deterministic cleanup: strip base64 images, normalize whitespace, remove form chrome patterns (from config), promote bold→headings, fix corruption (split words, HTML entities)
  - ALL regex patterns must come from config, not hardcoded
  - Remove `USELESS_HEADINGS` hardcoded TAC reference — make configurable
  - CLI: `--source` (dir), `--out` (dir), `--files` (filter), `--dry-run`, `--json`

- [ ] **Port `canonicalizer.py`** from prototype `canonicalize.py`
  - Filename segment parsing, version suffix scoring, draft suffix detection
  - Content similarity via SequenceMatcher (with configurable thresholds)
  - Optional LLM pass for ambiguous cases
  - CLI: `--dir`, `--archive-dir` (where to move non-canonical), `--config`, `--dry-run`, `--json`

- [ ] **Port `classifier.py`** from prototype `classify_files.py`
  - File quality scoring (form chrome, draft markers, corruption, content density)
  - **Replace `eval()`** with a safe condition DSL — define allowed functions (`has_type`, `has_any_type`, `has_headings`, `has_tables`, `field_gt`, `field_lt`, `path_contains`) and a simple expression parser
  - Tier assignment (skip/minimal/light/full)
  - Funders, doc types, thresholds, skip/tier rules — ALL from config
  - CLI: `--config`, `--source` (dir), `--json` (manifest output), `--dry-run`

- [ ] **Port `rewriter.py`** from prototype `rewrite_md.py`
  - Tiered LLM prompts (full/light/minimal) with template variables
  - Concurrent API calls with rate limiting (configurable max_workers, requests_per_second)
  - Checkpoint/resume via JSON manifest
  - Cost tracking (input/output token counting, cost estimation from config pricing)
  - Heading taxonomy substitution from config
  - Frontmatter field whitelist from config
  - Output sanitization (strip code fences, normalize frontmatter)
  - CLI: `--manifest`, `--files`, `--input-dir`, `--tier`, `--dry-run`, `--resume`, `--model`, `--limit`, `--debug`

- [ ] **Port `prioritizer.py`** from prototype `prioritize_files.py`
  - Group files by year (and optionally funder) from frontmatter
  - Send digests to LLM for comparison, assign priority 1-3
  - Update frontmatter in-place with priority scores
  - Rubric and prompts from config
  - CLI: `--config`, `--source` (dir), `--dry-run`, `--year`, `--limit`, `--json`, `--resume`

- [ ] **Port `ingester.py`** from prototype `ingest.py`
  - Convert PDF/DOCX/XLSX via configured converter
  - Deterministic cleanup + frontmatter injection
  - Save to rewrite_md/ + sync to wiki raw
  - **Remove hardcoded `VALID_FUNDERS` and `VALID_DOC_TYPES`** — validate against project config
  - **Remove hardcoded `PIPELINE_ID`** — use converter config
  - **Remove hardcoded `DEFAULT_WIKI_DIR`** — use paths config
  - CLI: `sources`, `--funder`, `--year`, `--period`, `--types`, `--rewrite`, `--no-wiki`, `--compile`, `--dry-run`

- [ ] **Port `auditor.py`** from prototype `audit_wiki.py`
  - Scan wiki concepts for dead links, thin articles, near-duplicates, stale content
  - **Remove hardcoded address keywords** (Dupont, Lisgar, Ossington) — make configurable
  - CLI: `--wiki` (path), `--json`, `--min-size`

### 1.3 Adapter implementations

- [ ] **Implement sage-wiki backend** (`adapters/wiki/sage_wiki.py`)
  - `init()` — run `sage-wiki init`, write config.yaml with org settings and API keys
  - `add_documents()` — copy/symlink files to wiki raw directory
  - `compile()` — run `sage-wiki compile`
  - `search(query)` — run `sage-wiki search`
  - `query(question)` — run `sage-wiki query`

- [ ] **Implement null wiki backend** (`adapters/wiki/null.py`)
  - All methods are no-ops. `search`/`query` return "wiki not configured" messages.

- [ ] **Implement local filesystem source** (`adapters/sources/local.py`)
  - `list_files()` — recursive glob with extension filter
  - `download()` — copy file to dest

- [ ] **Converter factory** — `adapters/converters/__init__.py`
  - `get_converter(config)` — return the configured converter instance
  - Validates that required dependencies are installed (e.g. `datalab-python-sdk` for datalab converter)

- [ ] **LLM provider factory** — `adapters/llm/__init__.py`
  - `get_llm_provider(config)` — return the configured provider instance

- [ ] **Wiki backend factory** — `adapters/wiki/__init__.py`
  - `get_wiki_backend(config)` — return the configured wiki backend

### 1.4 Config validation

- [ ] **Implement `config/schema.py`** — Pydantic models
  - `ProjectConfig` — top-level model validating all sections
  - `OrgConfig` — name, abbreviation, description
  - `FunderConfig` — dict of abbreviation → full name
  - `PathsConfig` — raw_archive, raw_md, clean_md, rewrite_md, wiki_project
  - `ConverterConfig` — type, datalab/marker/docling/pandoc settings
  - `WikiConfig` — type, sage-wiki binary path, pack
  - `LLMConfig` — provider, base_url, api_key_env, models, pricing
  - `ProcessingConfig` — max_workers, requests_per_second, max_retries, resume
  - `validate_config(raw_dict)` — load, validate, return typed config

### 1.5 Skills generation

- [ ] **Implement `cli/skills.py`** and `core/skills.py`
  - Read org config from `folio.yaml`
  - Load skill templates from `skills/core/` and `skills/templates/`
  - Fill `{placeholders}` from config: org name, funder table, doc type table, paths
  - Write platform-specific output:
    - `--platform opencode` → `.opencode/skills/grant-writing/SKILL.md`
    - `--platform claude` → `.claude/commands/grant-search.md`, `grant-draft.md`
    - `--platform openclaw` → system prompt + tool config
  - Validate that all placeholders were filled (warn on unfilled)

### 1.6 Pipeline orchestrator

- [ ] **Implement `cli/pipeline.py`**
  - Load project config
  - Run stages in order: scan → convert → clean → canonicalize → classify → rewrite → prioritize → wiki compile
  - Each stage can be skipped via `--stages` or enabled/disabled in config
  - Checkpoint state: manifest.json tracks which stage each file completed
  - Resume from last checkpoint
  - `--dry-run` shows cost estimates for each stage
  - Progress bars via tqdm per stage
  - Final report: file counts by status, total cost, wall time

### 1.7 Init and guided setup

- [ ] **Implement `folio init`**
  - `folio init --guided` — interactive Q&A
  - `folio init --profile <name>` — load a pre-built profile
  - `folio init --from-scan scan-report.json` — init from archive scan results
  - Generates `folio.yaml` with all required sections
  - Generates `headings.yaml` with per-funder canonical section headings
  - Optionally runs `folio scan` to verify

- [ ] **Implement pre-built profiles**
  - `profiles/canadian-artist-run-centre.yaml` — OAC, TAC, CCA, BCAH with heading taxonomies
  - `profiles/canadian-gallery.yaml`
  - `profiles/canadian-festival.yaml`
  - `profiles/generic-canadian-arts.yaml`
  - Each profile: funders list, doc types, classification patterns, heading taxonomies

### 1.8 Archive scanner

- [ ] **Implement `scanner.py`** and `cli/scan.py`
  - Scan raw document directory (local or cloud source)
  - Detect funders from filename patterns (regex from config)
  - Detect years from filename patterns
  - Detect document types from filename patterns
  - Count files by extension, funder, year, type
  - Flag likely-draft files
  - Estimate LLM costs (file count × avg tokens × pricing)
  - Estimate Datalab costs (from config pricing)
  - Output: scan report JSON + human-readable summary

---

## Phase 2: Testing

- [ ] **Write `tests/test_frontmatter.py`**
  - Port all tests from `fm_utils._run_tests()`
  - Test all parsing, generation, update, sanitize, normalize functions
  - Test Pydantic validation (valid frontmatter passes, invalid fields rejected)
  - Test field alias normalization edge cases
  - Test empty/malformed frontmatter handling

- [ ] **Write `tests/test_config.py`**
  - Test loading minimal valid config
  - Test loading config with all optional sections
  - Test validation errors on missing required fields
  - Test validation errors on invalid funder names, paths, etc.
  - Test defaults merging

- [ ] **Write `tests/test_classifier.py`**
  - Test condition DSL evaluation (all operators, all functions)
  - Test skip rules against known-bad files
  - Test tier assignment against known file profiles
  - Test that removed eval()-style conditions produce same results as DSL conditions

- [ ] **Write `tests/test_cleaner.py`**
  - Test base64 image stripping
  - Test whitespace normalization
  - Test form chrome removal
  - Test HTML entity decoding
  - Test corruption fix (split words)

- [ ] **Write `tests/test_adapters.py`**
  - Test converter factory returns correct type
  - Test wiki backend factory returns correct type
  - Test LLM provider factory returns correct type
  - Test sage-wiki backend with a mock subprocess

- [ ] **Write integration tests**
  - `tests/integration/test_pipeline.py` — run full pipeline on small fixture archive
  - Verify all stages produce expected output
  - Verify manifest tracks file states correctly
  - Verify costs are tracked

---

## Phase 3: Documentation

- [ ] **Write `docs/pipelines.md`** — pipeline stage documentation
- [ ] **Write `docs/config.md`** — folio.yaml full reference
- [ ] **Write `docs/converters.md`** — converter options and setup
- [ ] **Write `docs/wiki-backends.md`** — wiki backend options and setup
- [ ] **Write `docs/frontmatter.md`** — frontmatter field reference
- [ ] **Write `docs/skills.md`** — skills architecture and generation
- [ ] **Update `README.md`** — complete quickstart with real examples

---

## Phase 4: Polish

- [ ] **Add `--help`** to all CLI tools with realistic usage examples
- [ ] **Add `--version`** flag to all CLI tools (reads from `folio.__version__`)
- [ ] **Add `--config` flag** to all tools (point to folio.yaml, default cwd)
- [ ] **Consistent progress bars** (tqdm) across all long-running operations
- [ ] **Consistent error messages** (use `sys.exit(1)`, messages to stderr)
- [ ] **CI/CD** — GitHub Actions: pytest, ruff lint, mypy typecheck on push

---

## Phase 5: InterAccess deployment

- [ ] **Create InterAccess `folio.yaml`** from prototype configs
  - Merge funders from `classify_config.yaml`
  - Merge heading taxonomies from `rewrite_config.yaml`
  - Merge rubric from `prioritize_config.yaml`
  - Set paths to point at existing `_raw_archive/`, `rewrite_md/`, `sage_wiki_3/`

- [ ] **Test folio pipeline against InterAccess archive**
  - Run `folio pipeline --dry-run` — verify cost estimates match prototype
  - Run `folio pipeline` on a 10-file sample — verify output matches prototype
  - Run `folio pipeline` on full archive — verify all 1,033 files process correctly
  - Compare `rewrite_md/` output byte-for-byte with prototype output

- [ ] **Generate InterAccess skills**
  - Run `folio skills generate --platform opencode`
  - Verify skills match prototype `.opencode/skills/grant-writing/SKILL.md`
  - Run `folio skills generate --platform claude`
  - Run `folio skills generate --platform openclaw`

---

## Summary

| Phase | Tasks | Est. effort |
|-------|-------|-------------|
| 1: Core pipeline | 20 tasks | ~3-5 days of agent work |
| 2: Testing | 6 task groups | ~1-2 days |
| 3: Documentation | 7 docs | ~1 day |
| 4: Polish | 6 tasks | ~0.5 day |
| 5: InterAccess deploy | 3 tasks | ~0.5 day |
