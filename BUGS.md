# BUGS.md — Issues and Improvements Discovered During Porting

Items discovered while porting from the `llm_wiki` prototype to `folio`.
Priority: **P0** (blocking), **P1** (important), **P2** (nice-to-have), **P3** (future).

## Summary

| Status | Count | Items |
|--------|-------|-------|
| Fixed | 40 | #001–005, #007–011, #018–036, #038–046 |
| Won't Fix | 1 | #016 |
| Deferred | 2 | #012, #014 |
| Open | 4 | #015, #016b, #017, #037 |
| Not ported | 1 | #006 |
| Inconsistent | 1 | #013 |

---

## Prototype Bugs Found

### [#001] `eval()` security risk in classify_files.py
- **Priority**: P0 — **Status**: Fixed
- **What**: `classify_files.py` used Python `eval()` with a restricted namespace for skip/tier rule conditions. Malicious config could execute arbitrary code.
- **Fix**: Replaced with safe condition DSL in `folio/core/classifier.py`. 12 condition types, no code execution. Legacy `parse_legacy_eval_condition()` provided for migration.

### [#002] Hardcoded funders in ingest.py
- **Priority**: P0 — **Status**: Fixed
- **What**: `ingest.py` had `VALID_FUNDERS`, `VALID_DOC_TYPES` hardcoded.
- **Fix**: Now validates against `config.funders` dict and `config.doc_types` list.

### [#003] Hardcoded Datalab pipeline ID
- **Priority**: P0 — **Status**: Fixed
- **What**: `ingest.py` and `datalab_retry.py` had `PIPELINE_ID` hardcoded.
- **Fix**: Now reads from `config.converter.datalab_pipeline_id`.

### [#004] Hardcoded useless headings in clean_md.py
- **Priority**: P1 — **Status**: Fixed
- **What**: `clean_md.py` had `USELESS_HEADINGS` regexes referencing IA-specific patterns.
- **Fix**: All heading-removal patterns now come from config's `useless_headings` list.

### [#005] Hardcoded stale content patterns in audit_wiki.py
- **Priority**: P1 — **Status**: Fixed
- **What**: `audit_wiki.py` hardcoded IA addresses.
- **Fix**: Replaced with configurable `stale_content_patterns` list. Empty by default.

### [#006] Hardcoded topic keywords in find_stats.py
- **Priority**: P2 — **Status**: Not yet ported
- **What**: `find_stats.py` `TOPIC_KEYWORDS` references IA programs (Vector Festival, Terra Firma).
- **Fix**: Make topic keywords configurable when ported.

---

## Architecture Improvements Discovered

### [#007] SequenceMatcher autojunk issue
- **Priority**: P1 — **Status**: Fixed
- **What**: `SequenceMatcher` defaults to `autojunk=True`, silently treating repetitive sequences as "junk."
- **Fix**: All `SequenceMatcher` calls now use `autojunk=False`.

### [#008] SequenceMatcher scaling for large archives
- **Priority**: P2 — **Status**: Mitigated
- **What**: `SequenceMatcher` is O(n²). For 1000+ files, dedup checking all pairs is too slow.
- **Fix**: Auditor uses 3-stage filtering (size banding → Jaccard → truncated quick_ratio). Should eventually use TF-IDF or MinHash.

### [#009] Python 3.14+ requirement too new
- **Priority**: P0 — **Status**: Fixed
- **What**: Prototype required Python >=3.14 (bleeding edge at the time).
- **Fix**: Folio requires >=3.10. Uses `from __future__ import annotations` where needed.

### [#010] No config schema validation in prototype
- **Priority**: P1 — **Status**: Fixed
- **What**: Prototype had no validation of config files. Typos silently produced defaults or crashes.
- **Fix**: `config/schema.py` with dataclass models + `config/loader.py` with validation.

### [#011] No shared error taxonomy
- **Priority**: P2 — **Status**: Fixed
- **What**: Each prototype tool returned different error formats.
- **Fix**: `folio/core/errors.py` defines `FileStatus` and `ProcessingTier` enums used across all modules.

---

## Porting Decisions & Tradeoffs

### [#012] No Pydantic dependency
- **Priority**: P2 — **Status**: Deferred
- **What**: Config validation uses plain dataclasses instead of Pydantic to keep dependencies minimal.
- **Decision**: Stay with dataclasses. Add Pydantic as optional dependency later.

### [#013] `import yaml` vs `from yaml import safe_load`
- **Priority**: P2 — **Status**: Inconsistent
- **What**: Some modules use `import yaml`, others may use different patterns.
- **Decision**: Standardize on `import yaml` with `yaml.safe_load()`.

### [#014] `datalab-python-sdk` is proprietary, not on PyPI
- **Priority**: P2 — **Status**: Documented
- **What**: Datalab SDK is proprietary. Must be installed separately.
- **Decision**: Datalab remains the default but converter is pluggable.

---

## Future Work

### [#015] LLMProvider abstraction doesn't return token counts
- **Priority**: P2 — **Status**: Open
- **What**: `LLMProvider.complete()` returns only the completion text. The rewriter needs token counts for cost tracking and bypasses the provider abstraction, creating its own `OpenAI` client.
- **Fix**: Extend the `LLMProvider` interface to return `(text, usage_metadata)` tuple, or add a `complete_with_usage()` method.

### [#016] agentmap as Python library
- **Priority**: P2 — **Status**: Won't Fix
- **What**: agentmap is a Go binary (~500 lines). Porting to Python would remove one external dependency.
- **Decision**: Keep agentmap as a standalone tool. Folio now has an `agentmap` config toggle with PATH validation. Skills teach the full agentmap workflow (generate → update → check, bulk indexing) when enabled.

### [#016b] French language detection
- **Priority**: P3 — **Status**: Open
- **What**: Canadian arts orgs have French documents (CCA, BCAH). The pipeline doesn't detect language. French documents would get English heading taxonomies applied incorrectly.
- **Fix**: Add language detection pass before heading normalization.

### [#017] Filename convention fragility
- **Priority**: P2 — **Status**: Open
- **What**: Pipeline depends on `FUNDER__Year_Topic__SubTopic.md` naming with `__` separators. Undocumented and fragile.
- **Fix**: Document the convention. Add a filename validation pass. Support alternative naming schemes via config.

---

## Code Review Findings (2026-06-15)

Full review of all 48 source files. 93 findings: 13 critical, 21 high, 28 medium, 31 low.

### Critical (P0)

| # | Issue | Status |
|---|-------|--------|
| 018 | Pipeline `_run_rewrite` calls `rewrite_directory` with wrong signature | Fixed |
| 019 | `prioritizer._validate_priorities` returns wrong types on error | Fixed |
| 020 | `classifier._evaluate_skip_rules` / `_evaluate_tier_rules` silently swallow exceptions | Fixed |
| 021 | Broken retry logic in `rewrite_directory` — `future.result()` cached | Fixed |
| 022 | Manifest mutation race condition in `rewrite_directory` | Fixed |
| 023 | `_call_llm` sends DeepSeek-specific params to all providers | Fixed |
| 024 | Missing null check on `response.usage` in `_call_llm` | Fixed |
| 025 | `rewrite_file` bypasses LLMProvider, reads private attrs | Fixed |
| 026 | `thinking_enabled` None coercion bug | Fixed |
| 027 | `ingester` imports non-existent function `rewrite_documents` | Fixed |

### High (P1)

| # | Issue | Status |
|---|-------|--------|
| 028 | 9 CLI stubs registered as entry points (all print "not yet implemented") | Fixed |
| 029 | Three separate manifest implementations | Fixed |
| 030 | Duplicate rate-limiting implementations | Fixed |
| 031 | Duplicate `_deep_merge` functions | Fixed |
| 032 | `canonicalize_directory` swallows JSON parse errors from LLM | Fixed |
| 033 | `sage_wiki` backend: search/query don't check subprocess success | Fixed |
| 034 | Config `base_url` validation rejects `http://` localhost URLs | Fixed |
| 035 | `frontmatter.update_frontmatter` uses regex on raw YAML text | Fixed |
| 036 | Skills template path uses 4-level `.parent` — breaks when installed | Fixed |

### Medium (P2)

| # | Issue | Status |
|---|-------|--------|
| 037 | `from __future__ import annotations` — inconsistent across codebase | Open |
| 039 | No `--version` flag on any CLI tool | Fixed |
| 040 | No CLI tests | Fixed |
| 041 | `classify.py` config-merging leaks business logic into CLI | Fixed |
| 042 | `skills.py` imports private `_build_context` | Fixed |
| 043 | `canonicalize.py` — broad `except Exception` on LLM provider setup | Fixed |
| 044 | `priority.py` hardcoded dry-run cost estimate | Fixed |

### Low (P3)

| # | Issue | Status |
|---|-------|--------|
| 045 | `scan.py` `--source` arg type inconsistency | Fixed |
| 046 | Missing `from __future__ import annotations` in skills.py, teach.py | Fixed |

---

## Deployment & Phase 5 Findings (2026-06-15)

### [#038] Tier rule evaluation fails with KeyError 'type'
- **Priority**: P2 — **Status**: Fixed
- **What**: ~235 BCAH Vector Festival files hit `KeyError: 'type'` in tier rule evaluation. Nested conditions dicts from parenthesized legacy expressions lacked a `type` key.
- **Fix**: Added recursive guard in `evaluate_rule` — sub-condition dicts with a `conditions` key are evaluated via `evaluate_rule` instead of `evaluate_condition`.

### Phase 5 validation bugs

8 additional bugs found and fixed during IA deployment validation:

| # | Issue | Fix |
|---|-------|-----|
| — | `rewrite_directory` manifest `KeyError: 'files'` crash | `create_manifest()` fallback when manifest file absent |
| — | User rewrite config from `folio.yaml` never merged | `_deep_merge_rewrite()` in rewriter |
| — | Skills template path resolution broken | Fixed `importlib.resources` path to repo root |
| — | CLI summary displays 0/0 (wrong dict keys) | `summary["ok"]` → `summary["success"]` + errors |
| — | `--dest` flag in rewrite CLI not wired | Added `dest` param to `rewrite_directory` |
| — | Prioritizer ignores `config.prioritize` (dataclass path) | Merge rubric/grouping/processing from `config.prioritize` |
| — | `period_start`/`period_end` missing from frontmatter | Added to `DEFAULT_REWRITE_CONFIG` and metadata block |
| — | Skills generation importlib.resources wrong dir | Replaced with repo-root-relative path |

### Recent additions (2026-06-15)

- **Agentmap toggle** — `agentmap` config section with `enabled` bool and `binary_path`. PATH validation when enabled. Conditional rendering in skill templates via `{?key}...{/key}` blocks.
- **Skill template conditionals** — `{?agentmap_enabled}...{/agentmap_enabled}` blocks in `archive-search.md` and `grant-drafting.md`. Content omitted when tool not installed.
- **Next task** — `folio-7dt`: refactor skills to compose tool instructions from per-tool snippet files rather than conditional blocks.
