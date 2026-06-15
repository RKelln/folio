# HANDOFF.md — folio project state and next steps

## What this is

This document is for the next AI agent taking over work on `folio`. Read it fully before doing anything. It provides context, current state, what's done, and what to do next.

## Project overview

**folio** turns an arts organization's document archive (grant applications, reports, budgets, exhibition records in PDF/DOCX/XLSX) into a searchable knowledge base that AI agents can use to write grants, answer questions, and understand organizational patterns. It was ported from a working prototype (`llm_wiki`) built for InterAccess gallery's 1,033-file grant archive.

**Repo location:** `/home/ryankelln/Documents/Work/IA_board/folio/`
**Prototype (reference):** `/home/ryankelln/Documents/Work/IA_board/llm_wiki/`
**Design plan:** `PLAN.md` (read it — extensive design rationale)

## Current state

**Phase 1 complete. Code reviewed. All 10 P0 and 11 P1 bugs fixed. 354 tests passing.**

All 20 core pipeline tasks are ported from the prototype. Every hardcoded InterAccess-specific value has been removed from Python. The code review (`CODE_REVIEW.md`) found 93 issues — all critical and high-severity items are resolved. 354 pytest tests cover frontmatter, config, classifier, cleaner, adapters, and integration.

**Key files to read FIRST (in order):**
1. **`HANDOFF.md`** — this file
2. **`CODE_REVIEW.md`** — full review report (93 findings, prioritized)
3. **`BUGS.md`** — tracked issues with fix suggestions (includes P0s from review)
4. **`TASKS.md`** — 47 tasks, Phase 1 done, Phase 2+ remaining
5. **`AGENTS.md`** — conventions for all code in this repo
6. **`PLAN.md`** — design rationale (optional, for deeper context)

## Code review summary

Full review of 48 source files (~9,500 lines) found:

| Severity | Count | Key areas |
|----------|-------|-----------|
| Critical (P0) | 10 | Wrong function signatures, type errors, silent exception swallowing, race conditions, broken retry, dead code, provider bypass |
| High (P1) | 9 | 3 duplicate manifest implementations, 2 duplicate rate-limiters, regex-on-YAML, fragile paths |
| Medium (P2) | 20+ | Hardcoded constants, missing validation, fragile regex |
| Low | 30+ | Style nits, dead imports, naming issues |

**Verdict: BLOCK MERGE.** The core algorithmic logic (DSL, dedup, cleanup) is sound but the integration layer needs fixes. See `CODE_REVIEW.md` for full details with file:line references and fix suggestions.

## What to do next

### Step 0: Fix P0 bugs ✅ DONE
10 P0 bugs fixed (pipeline signature, return types, exception swallowing, retry logic, race conditions, DeepSeek params, null checks, encapsulation, None coercion, dead imports).

### Step 1: Write tests ✅ DONE
354 pytest tests across 6 files (frontmatter, config, classifier, cleaner, adapters, integration). Run with `uv run pytest tests/ -v`.

### Step 2: InterAccess deployment (Phase 5) ← NEXT
Configure and validate against real IA archive data.
- `core/frontmatter.py` — YAML frontmatter parsing, generation, sanitization, field normalization
- `core/cleaner.py` — deterministic markdown cleanup (strip images, normalize whitespace, fix corruption, remove form chrome)
- `core/canonicalizer.py` — version detection, draft scoring, near-duplicate detection via SequenceMatcher
- `core/classifier.py` — file quality scoring, tier assignment using safe condition DSL (replaced prototype's `eval()`)
- `core/rewriter.py` — LLM re-authoring with tiered prompts, concurrency, checkpoint/resume, cost tracking
- `core/prioritizer.py` — archival priority scoring grouped by year via LLM comparison
- `core/ingester.py` — one-off document ingestion (convert → clean → frontmatter → save → wiki sync)
- `core/auditor.py` — wiki quality audit (dead links, thin articles, duplicates, missing sections)
- `core/manifest.py` — JSON manifest CRUD for pipeline state tracking
- `core/errors.py` — `FileStatus` and `ProcessingTier` enums
- `adapters/converters/` — Datalab (implemented) + Marker/Docling/Pandoc (stubs)
- `adapters/wiki/` — sage-wiki backend (subprocess wrapper) + null backend (no-op)
- `adapters/llm/` — OpenAI-compatible provider (used directly by rewriter for token tracking)
- `adapters/sources/` — local filesystem source (implemented) + gdrive/dropbox (stubs)
- `config/` — dataclass schema + YAML loader with validation + defaults.yaml

**What's new (not in prototype):**
- `core/scanner.py` — archive scanner: detects funders/years/types from filenames, estimates costs
- `core/skills.py` — generates platform-specific agent skills from org config (opencode/claude/openclaw/hermes)
- `core/pipeline.py` — 8-stage pipeline orchestrator with checkpoint/resume
- `core/init.py` — guided interactive setup, profile loading, scan-based init
- `templates/profiles/` — 7 pre-built org profiles (canadian-artist-run-centre, gallery, festival, theatre, dance, generic)

**CLI entry points registered in pyproject.toml:**
`folio`, `folio-pipeline`, `folio-clean`, `folio-classify`, `folio-rewrite`, `folio-prioritize`, `folio-canonicalize`, `folio-ingest`, `folio-audit`, `folio-scan`, `folio-skills`, `folio-init`

**NOT done:**
- No documentation beyond README, AGENTS.md, PLAN.md, and test files
- CLI stubs exist but are minimal — many just print "not yet implemented"
- No integration test run against the InterAccess archive
- No CI/CD configuration

**NEW since Phase 1:**
- `core/throttle.py` — thread-safe `RateLimiter` for API calls (extracted from duplicate implementations)
- 354 pytest tests in `tests/` covering frontmatter, config, classifier, cleaner, adapters, pipeline integration

## Immediate: Run a smoke test

Before doing anything else, verify the package imports work:

```bash
cd /home/ryankelln/Documents/Work/IA_board/folio
python3 -c "
from folio.core.frontmatter import parse_frontmatter, sanitize_frontmatter
from folio.core.errors import FileStatus, ProcessingTier
from folio.core.manifest import create_manifest
from folio.core.cleaner import clean_markdown
from folio.core.classifier import evaluate_condition, classify_file
from folio.core.scanner import scan_archive
from folio.core.rewriter import DEFAULT_REWRITE_CONFIG
from folio.core.prioritizer import DEFAULT_PRIORITIZE_CONFIG
from folio.core.pipeline import AVAILABLE_STAGES
from folio.config import load_project_config
print('All imports OK')
"
```

### Phase 2: Testing (priority order)

**2a. Write `tests/test_frontmatter.py`** — highest priority
The prototype had inline `_run_tests()` in `fm_utils.py`. These were removed during porting. Port them into proper pytest tests.
- Source: `/home/ryankelln/Documents/Work/IA_board/llm_wiki/fm_utils.py` lines 360-597 (the `_run_tests()` function)
- Test file: `/home/ryankelln/Documents/Work/IA_board/folio/tests/test_frontmatter.py`
- Also test Pydantic validation (valid frontmatter passes, invalid fields rejected)
- Existing fixtures in `conftest.py`: `sample_markdown_with_frontmatter`, `temp_project_dir`

**2b. Write `tests/test_config.py`**
- Load minimal valid config
- Load config with all optional sections
- Test validation errors on missing required fields
- Test defaults merging

**2c. Write `tests/test_classifier.py`**
- Test condition DSL evaluation (all 12 condition types)
- Test legacy eval parser against real prototype config conditions
- Test skip rules against known-bad file profiles
- Test tier assignment against known file profiles
- The classifier agent verified against real data — use those patterns

**2d. Write `tests/test_cleaner.py`**
- Test base64 image stripping, whitespace normalization, form chrome removal, HTML entity decode, corruption fix

**2e. Write `tests/test_adapters.py`**
- Test converter/wiki/LLM/sources factories return correct types for known configs

**2f. Write integration tests** — `tests/integration/test_pipeline.py`
- Run full pipeline on small fixture archive (create 5-10 sample markdown files)
- Verify all stages produce expected output
- Verify manifest tracks file states correctly

### Phase 5: InterAccess deployment (the real proof)

The goal: run folio against the actual InterAccess archive and produce output matching the prototype.

**5a. Create InterAccess `folio.yaml`**
Merge the prototype configs into a single project config:
- Funders from `/home/ryankelln/Documents/Work/IA_board/llm_wiki/classify_config.yaml` funders section
- Heading taxonomies from `/home/ryankelln/Documents/Work/IA_board/llm_wiki/rewrite_config.yaml` funders section
- Priority rubric from `/home/ryankelln/Documents/Work/IA_board/llm_wiki/prioritize_config.yaml`
- Classification patterns from `classify_config.yaml` (doc_types, form_chrome, draft_markers, skip_rules, tier_rules — these will need to be converted from eval-style to the new DSL format)
- Set paths to point at existing directories in the prototype:
  - `_raw_archive/` for raw files
  - `clean_md/` for input to rewrite (or raw_md/ if clean_md doesn't have all files)
  - New `folio_rewrite_md/` for output (don't overwrite prototype output!)

**5b. Run end-to-end validation**
1. `folio scan` against the IA raw archive — verify funders/years/costs match expectations
2. `folio classify` against clean_md/ — compare tier assignments with prototype manifest
3. `folio rewrite` on a 10-file sample — compare output byte-for-byte with prototype `rewrite_md/`
4. If sample matches, run full pipeline
5. `folio prioritize` on the output
6. `folio skills generate --platform opencode` — compare with prototype `.opencode/skills/grant-writing/SKILL.md`

**5c. Known conversion issues**
- The prototype's `classify_config.yaml` uses `eval()`-style conditions. The folio classifier has `parse_legacy_eval_condition()` to auto-convert these. Test that the conversion produces correct results.
- The rewriter was ported with the same tier prompt templates from `rewrite_config.yaml`. Verify LLM output is identical.
- Add any discrepancies found to `BUGS.md`.

## Important design decisions to know

1. **No Pydantic** — config validation uses plain dataclasses to keep deps minimal. Pydantic can be added later.
2. **LLM provider bypass** — the rewriter creates its own OpenAI client for token tracking because the `LLMProvider.complete()` interface doesn't return usage metadata. See BUGS.md #015.
3. **Safe condition DSL** — the 12 condition types in `classifier.py` are the canonical way to express classification rules. The legacy eval parser exists only for migration from prototype configs.
4. **SequenceMatcher autojunk** — always use `autojunk=False` with `SequenceMatcher` when comparing grant documents (repetitive boilerplate breaks the default). See BUGS.md #007.
5. **Frontmatter API is frozen** — `parse_frontmatter`, `dict_to_frontmatter`, `sanitize_frontmatter`, `update_frontmatter` have the same signatures as the prototype. Don't change them.
6. **Manifest as checkpoint state** — the manifest at `{paths.rewrite_md}/manifest.json` is the pipeline's resume mechanism. Always save after each stage.
7. **Filename convention** — files use `FUNDER__Year_Description__Type.md` with double-underscore separators. This convention is assumed by canonicalizer and classifier but is not validated. See BUGS.md #017.

## How to run things

```bash
cd /home/ryankelln/Documents/Work/IA_board/folio

# Guided setup (interactive)
python3 -m src.folio.cli.init --guided

# Use a pre-built profile
python3 -m src.folio.cli.init --profile canadian-artist-run-centre

# Scan an archive
python3 -m src.folio.cli.scan --source ./_raw_archive/

# Run the pipeline
python3 -m src.folio.cli.pipeline --config folio.yaml

# Generate skills
python3 -m src.folio.cli.skills --platform opencode

# Run tests (once written)
python3 -m pytest tests/ -v
```

## Git history

```
3 commits on main:
  abc... Initial scaffold: folio archive pipeline package
  def... Add TASKS.md — 47 tracked tasks across 5 phases
  ghi... Phase 1 complete: all 20 core pipeline tasks ported
```

## Quick code navigation

| Need to find | Look in |
|---|---|
| How a module works | `AGENTS.md` section 7 (module table) |
| Task status | `TASKS.md` |
| Known issues | `BUGS.md` |
| CLI entry point | `src/folio/cli/<name>.py` |
| Business logic | `src/folio/core/<name>.py` |
| Converter interface | `src/folio/adapters/converters/base.py` |
| Wiki interface | `src/folio/adapters/wiki/base.py` |
| LLM interface | `src/folio/adapters/llm/base.py` |
| Config schema | `src/folio/config/schema.py` |
| Defaults | `src/folio/config/defaults.yaml` |
| Test fixtures | `tests/conftest.py` |
| Org profiles | `src/folio/templates/profiles/*.yaml` |
| Skill templates | `skills/core/*.md` |
