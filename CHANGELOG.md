# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.4.0] — System health checks & wiki compilation — 2026-06-29

The `folio doctor` command debuts as a comprehensive system health checker,
alongside a standalone `folio wiki compile` subcommand for direct wiki
recompilation. Several stability fixes shore up the config pipeline and
canonicalizer.

### Added

- **`folio doctor` — system health check command.** Runs a full diagnostic
  sweep: validates `folio.yaml` completeness (org name, funders, doc types,
  wiki/converter settings), checks API keys and `.env` presence, verifies
  converter/SDK availability (cascade tiers checked individually), confirms
  `sage-wiki` and `agentmap` binaries are on PATH, inspects the `wiki/`
  symlink integrity, audits pipeline directory state (file counts across
  stages), and delegates to `sage-wiki doctor` for deep wiki validation.
  Supports `--dry-run`, `--json`, and `--version` like all folio commands.
- **`folio wiki compile` subcommand** — recompiles the wiki from `markdown/`
  sources without invoking the full pipeline. Handles config initialization,
  raw symlink refresh, pack install/apply, and root `wiki/` symlink creation.
- **Config completeness validation in `folio doctor`** — warns when org name
  is unchanged from default, funders or doc types are empty, wiki type is
  invalid, or converter type is unrecognized.
- **Agentmap binary check in `folio doctor`** — verifies `agentmap` is on
  PATH when `agentmap.enabled: true` in config.
- **`.env` file check in `folio doctor`** — warns when `.env` is missing.
- **AGENTS.md module table consistency tests** — two automated tests ensure
  every file path in the module table exists and the `cli/` group row covers
  all `_COMMANDS` entries. CLI_MODULES in tests now imports directly from
  `main.py` (single source of truth).
- **Expanded `.gitignore` on `folio init`** — now excludes archive files,
  runtime artifacts, and pipeline state files by default.

### Fixed

- **Wiki config clobbering bug** — `folio wiki doctor`, `folio wiki status`,
  and all other `folio wiki *` subcommands no longer overwrite sage-wiki's
  `config.yaml` with a bare skeleton. The `_init_backend` function now
  preserves an existing config and writes `api`/`models`/`embed` sections
  when creating a fresh one.
- **`folio doctor` symlink check resolved wrong directory** — the `wiki/`
  symlink check now resolves relative to the config file's directory rather
  than the current working directory.
- **Sage-wiki binary check reads from config** — `folio doctor` now uses
  `config.wiki.sage_wiki_binary` instead of hardcoding `"sage-wiki"`.
- **Canonicalizer excludes webpages from all phases**, not just dedup. Moves
  `.non_canonical` output from `markdown/` to `.folio/non_canonical/`.
- **Sage-wiki install command fixed in docs** — corrected to
  `go install github.com/xoai/sage-wiki/cmd/sage-wiki@latest` (missing
  `/cmd/sage-wiki` in the import path).
- **Pipeline PID-based concurrency lock** prevents parallel pipeline runs.
- **Throttle test timing assertion** relaxed to de-flake CI.

### Infrastructure

- `CLI_MODULES` in `test_cli.py` now imports from `folio.cli.main._COMMANDS`
  (DRY — single command registry).
- 4 regression tests for wiki config preservation.
- 5 new tests for `folio doctor` (dry-run, json, missing config, full run,
  json output validation).
- 2 AGENTS.md module table sync tests.

## [v0.3.1] — Bug fixes — 2026-06-24

### Fixed
- Per-file rewrite path now correctly writes rewritten output to `rewrite_md` and tracks LLM costs for all statuses, not just success
- Prioritizer no longer crashes on rubric key type mismatch when config merges integer keys with JSON-serialized string keys

## [v0.3.0] — Per-file pipeline processing — 2026-06-24

`folio website ingest` now processes only the newly staged pages instead of
re-running the full archive through every pipeline stage.

### Added
- `run_pipeline(files=...)` parameter — limits pipeline stages to specific filenames. When set, the resume check is bypassed and each stage processes only the given files.

### Fixed
- `folio website ingest` no longer re-runs pipeline stages across the entire archive when staging new pages. Staged filenames are passed through automatically.
- Pipeline resume check correctly identifies completed stages instead of always re-running them.

### Infrastructure
- CI now uses `uv sync --extra dev` to match the project's PEP 508 optional dependencies format.

## [v0.2.1] — Bug fixes — 2026-06-23

### Fixed
- Content duplication in rewritten markdown when body was longer than frontmatter
- Pipeline resume now correctly skips completed stages

### Infrastructure
- Release workflow bumps `__version__` in `__init__.py` alongside `pyproject.toml`

## [v0.2.0] — Website Ingestion & Cascade Converter — 2026-06-24

This release adds website markdown ingestion, a cascade converter system with
benchmarking, a synthetic document corpus generator, and the arts-org sage-wiki
knowledge pack v1.1 with webpage-aware concepts.

### Added

- **`folio website` command** — ingest pre-scraped website markdown into the
  document pipeline. Discovers `.md` files in a directory, parses scraper
  headers (source URL, timestamp), stages into the archive with org-prefixed
  filenames, and runs the full pipeline. Supports `--list` (preview metadata),
  `--name` (override slug), `--stages` (select pipeline stages), `--dry-run`,
  and `--json` output.
- **Arts-org sage-wiki pack v1.1** — reusable knowledge pack shipped in
  `templates/packs/arts-org/`. 23 entity types (6 new: event, workshop,
  call_for_submissions, residency, festival, news_announcement) and 19 relation
  types (5 new: speaks_at, teaches, part_of, submitted_to, announces). 6 LLM
  prompt templates including 2 new webpage-tuned prompts
  (`extract-webpage-concepts.md`, `summarize-webpage.md`). Auto-installed and
  applied during `folio pipeline` wiki stage.
- **Cascade converter** — automatically selects the best available PDF/DOCX
  converter (Pandoc, Docling, Marker, LiteParse, Datalab fallback). Records
  winning tier and per-file conversion cost in the manifest. Configurable via
  `converters.cascade_order` and `converters.cascade_tiers` in `folio.yaml`.
- **`folio convert-bench` CLI** — reproducible converter benchmarking.
  Compares offline (Pandoc) and cascade converters against golden markdown
  using deterministic, offline fidelity scoring across text, tables, structure,
  and links/images categories. Emits a plaintext scorecard and Markdown
  comparison report. Includes real PDF page counts via `pdfinfo`.
- **`folio corpus` CLI** — generate and scan synthetic PII-free benchmark
  corpora. Renders goldens (DOCX, PDF, XLSX) from markdown using deterministic
  formatters. Scans outputs for accidental PII leakage. Shipped with a default
  corpus spec and PII denylist.
- **LiteParse converter** — new offline-first converter for plaintext, DOCX
  (via python-docx), and basic PDF text extraction. No external binaries
  required. Configured as the default converter.
- **`sanitize_slug()`** public utility in `core.website` for canonicalizing
  strings into filename-safe slugs.

### Changed

- **`ingest_website()` API** — removed redundant `config` parameter. Function
  now loads its own config from `config_path`, consistent with `run_pipeline()`
  and `ingest_document()`. Callers no longer need to pre-load config.
- **PandocConverter** upgraded from stub to full implementation with offline
  fidelity scoring support and page-count tracking.
- **Manifest** now records converter tier and per-file conversion cost in USD.
- **Config** supports cascade converter wiring: `converters.type: cascade`,
  `cascade_order`, `cascade_tiers`, and `sage_wiki.pack` for the knowledge pack.
- **`folio guide`** updated with website command, cascade converter config, and
  correct sage-wiki config structure.

### Fixed

- **Pack prompt files excluded from pip-installed packages** — `**/*.md` added
  to `setuptools.package-data` for `folio.templates`.
- **Duplicate slug sanitization** — 3 identical inline regex blocks extracted
  into shared `sanitize_slug()` function.
- **Deferred import** of `run_pipeline` moved to module level in `core.website`.
- **Hardcoded pack name** replaced with config-driven `config.wiki.sage_wiki_pack`.
- **Missing subprocess timeout** on sage-wiki pack install/apply calls.
- **Benchmark Overall score** now coverage-weights result by category weights.
- **Ruff configuration** fixed to unblock CI; mypy errors resolved.

### Infrastructure

- Added `**/*.md` to setuptools package-data for template pack prompts.
- Added `pdfinfo` as optional dependency for page-count tracking in benchmarks.
- Added 1694 tests (up from previous release), including 9 new `sanitize_slug`
  tests and comprehensive test suites for cascade converter, benchmark CLI,
  corpus generator, and website ingestion.

## v0.1.1 — Cleanup & Polish — 2026-06-17

Bugfix and cleanup release removing org-specific naming, stale documentation, and
a broken flag in the release command.

### Fixed
- `uv build --check` replaced with `uv build` in release command (`--check` does not exist)
- Conflicting `--generate-notes` flag removed from `gh release create` in release command

### Changed
- `IA_LIBRARY_PATH` env var renamed to `LIBRARY_PATH` (folio is art-org agnostic)
- All `IA_*` variable names, function names, and test names replaced with `LIBRARY_*`
- Default fallback directory for tests changed from `ia-library` to `org-library`
- `.gitignore` org-library ignore pattern updated to `org-library/`
- `docs/INFO.md` renamed to `docs/README.md` for consistency

### Infrastructure
- Removed 1,851 lines of stale implementation docs (PLAN.md, TASKS.md, HANDOFF.md, CLAUDE.md)
- 1088 tests passing, 16 skipped

## v0.1.0 — Initial Release — 2026-06-17

folio turns an arts organization's document archive into a searchable knowledge
base that AI coding agents can use to write grants, answer questions, and
understand organizational patterns.

No code changes — just YAML config.

### Quick start

```bash
git clone https://github.com/RKelln/folio
uv tool install --editable ./folio

mkdir my-org && cd my-org
folio init --guided
folio scan
folio pipeline --dry-run
folio pipeline
```

### How it works

folio processes a raw document archive through 8 pipeline stages:

1. **scan** — enumerate files, detect funders, years, document types, and drafts
2. **convert** — PDF/DOCX/XLSX → Markdown via docling, datalab, marker-pdf, or pandoc
3. **clean** — remove form chrome, boilerplate, and PDF artifacts
4. **canonicalize** — detect drafts, resolve versions, deduplicate near-duplicates
5. **classify** — score quality, assign processing tier (full / light / minimal)
6. **rewrite** — LLM re-authoring with tiered prompts and per-funder heading taxonomies
7. **prioritize** — score archival priority (1–3) within year groups
8. **wiki** — compile markdown into a searchable sage-wiki knowledge base

The pipeline saves checkpoint state after each stage — interrupted runs resume
where they left off. Every command supports `--dry-run` for cost preview and
`--json` for structured output.

### 19 CLI commands

| Command | Purpose |
|---------|---------|
| `folio pipeline` | Run all 8 stages end-to-end |
| `folio scan` | Preview archive contents, costs, and estimated time |
| `folio init` | Guided setup with 8+ built-in profiles for Canadian arts orgs |
| `folio convert` | Convert PDF/DOCX/XLSX → markdown |
| `folio clean` | Deterministic markdown cleanup |
| `folio classify` | Quality scoring and tier assignment (12 condition types) |
| `folio rewrite` | LLM re-authoring with tiered prompts |
| `folio prioritize` | Archival priority scoring with concurrent processing |
| `folio canonicalize` | Version detection and content-hash deduplication |
| `folio ingest` | One-off document ingestion with auto frontmatter |
| `folio audit` | Wiki quality audit (dead links, thin articles, duplicates, staleness) |
| `folio validate` | Validate output against config (frontmatter, headings, placeholders) |
| `folio repack` | Migrate nested directories to flat folio filename convention |
| `folio wiki` | Wiki management (init, compile, search, query, status, lint, verify) |
| `folio skills` | Generate agent skills for opencode, claude, openclaw, and hermes |
| `folio guide` | Built-in agent reference with keyword search and JSON output |
| `folio install-agent` | Write AGENTS.md and skills files into a project |
| `folio teach` | Interactive tutorial (coming soon) |
| `folio test-skills` | Scenario-based agent skill validation |

### LLM provider support

folio uses OpenAI-compatible APIs and works with any provider:

| Provider | Example `base_url` | Env var |
|----------|-------------------|---------|
| DeepSeek | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |
| OpenAI | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| Groq | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| Ollama (local) | `http://localhost:11434/v1` | (none required) |

Configure model IDs, base URL, and pricing in `folio.yaml`. Cost is ~$4–12 for
a typical 1000-file archive with tiered processing.

### Installation

```bash
git clone https://github.com/RKelln/folio
uv tool install --editable ./folio
```

Requires Python 3.10+. See [docs/installation.md](docs/installation.md) for
platform-specific dependency setup (converters, sage-wiki, agentmap).

### What's under the hood

- **1,104 tests** across 10 new test modules, 76% coverage (up from 39%)
- **Thread-safe** adapter layer with locking on lazy-initialized clients
- **Pluggable architecture** — converters, wiki backends, LLM providers, and sources can be swapped via YAML
- **Self-documenting CLI** — every command has `--help`, `--dry-run`, and `--json`
- **Agent-native** — designed to be run by AI coding agents with structured output, no interactive prompts, and deterministic exit codes
