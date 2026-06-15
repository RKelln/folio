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

- [x] **Port `frontmatter.py`** from prototype `fm_utils.py` — all 10 public + 2 private functions ported
- [x] **Implement `errors.py`** — `FileStatus` (14 members) + `ProcessingTier` (4 members) enums
- [x] **Implement `manifest.py`** — `create/load/save_manifest`, `update/get_file`, `get_files_by_status`, `recalculate_summary`, `manifest_summary_text`

### 1.2 Pipeline stages

- [x] **Port `cleaner.py`** — all cleaning ops ported, form chrome/useless_headings config-driven, new split-word/single-char line/bare-digit removal, `clean_markdown(text, config)` + `clean_file(source, dest, config)`
- [x] **Port `canonicalizer.py`** — filename segment parsing, version/draft suffix scoring, SequenceMatcher with `autojunk=False`, duplicate detection with 3-stage filtering, optional LLM pass
- [x] **Port `classifier.py`** — safe condition DSL (12 condition types, no eval), legacy eval parser for migration, `classify_file` + `classify_directory`, verified against real 1255-file archive
- [x] **Port `rewriter.py`** — tiered prompts, concurrent with rate limiting, checkpoint/resume, cost tracking, heading taxonomy substitution, frontmatter whitelist, FIXME counter, undersized file handling
- [x] **Port `prioritizer.py`** — file grouping by year, batch splitting, LLM comparison, frontmatter update, checkpoint/resume, dry-run preview
- [x] **Port `ingester.py`** — removed ALL hardcoded values (VALID_FUNDERS, VALID_DOC_TYPES, PIPELINE_ID, DEFAULT_WIKI_DIR), now reads from config
- [x] **Port `auditor.py`** — dead links, thin articles, near-duplicates, missing sections, stale content (config-driven, no hardcoded addresses)

### 1.3 Adapter implementations

- [x] **Implement sage-wiki backend** — init, add_documents, compile, search, query via subprocess
- [x] **Implement null wiki backend** — all no-ops with descriptive messages
- [x] **Implement local filesystem source** — list_files (recursive glob), download (copy)
- [x] **Converter factory** — `get_converter(config)`, validates deps
- [x] **LLM provider factory** — `get_llm_provider(config)`
- [x] **Wiki backend factory** — `get_wiki_backend(config)`

### 1.4 Config validation

- [x] **Implement `config/schema.py`** — 7 dataclasses (ProjectConfig, OrgConfig, PathsConfig, LLMConfig, ConverterConfig, WikiConfig, ProcessingConfig)
- [x] **Implement `config/loader.py`** — deep-merge with defaults, YAML→dataclass mapping, validation (converter type, wiki type, https:// check, max_workers)

### 1.5 Skills generation

- [x] **Implement `core/skills.py`** and `cli/skills.py` — 4 platform generators (opencode, claude, openclaw, hermes), placeholder substitution, context builder from ProjectConfig

### 1.6 Pipeline orchestrator

- [x] **Implement `core/pipeline.py`** and `cli/pipeline.py` — 8-stage pipeline, checkpoint/resume via manifest, per-stage progress/cost/time, formatted report, dry-run mode

### 1.7 Init and guided setup

- [x] **Implement `core/init.py`** and `cli/init.py` — guided mode (6 Q&A), profile loading, scan-based init, minimal init, deep-merge with defaults, `.env` key writing
- [x] **Implement pre-built profiles** — 7 profiles: canadian-artist-run-centre, canadian-gallery, canadian-festival, canadian-theatre, canadian-dance, generic-canadian-arts, generic

### 1.8 Archive scanner

- [x] **Implement `scanner.py`** and `cli/scan.py` — file enumeration, funder/year/type/draft detection, cost estimation (conversion + LLM), time estimation, human-readable report

---

## Phase 2: Testing ✅ COMPLETE

- [x] **Write `tests/test_frontmatter.py`** (77 tests)
- [x] **Write `tests/test_config.py`** (30 tests)
- [x] **Write `tests/test_classifier.py`** (117 tests)
- [x] **Write `tests/test_cleaner.py`** (74 tests)
- [x] **Write `tests/test_adapters.py`** (42 tests)
- [x] **Write integration tests** — `tests/integration/test_pipeline.py` (17 tests)

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

| Phase | Tasks | Status |
|-------|-------|--------|
| 1: Core pipeline | 20 tasks | ✅ Done |
| 2: Testing | 6 task groups (354 tests) | ✅ Done |
| 3: Documentation | 7 docs | ⬜ Not started |
| 4: Polish | 6 tasks | ⬜ Not started |
| 5: InterAccess deploy | 3 tasks | ⬜ Not started |
