# BUGS.md — Issues and Improvements Discovered During Porting

Items discovered while porting from the `llm_wiki` prototype to `folio`.
Each has a priority: **P0** (blocking), **P1** (important), **P2** (nice-to-have).

---

## Prototype Bugs Found

### [#001] `eval()` security risk in classify_files.py
- **Priority**: P0
- **Status**: Fixed in folio
- **What**: `classify_files.py` used Python `eval()` with a restricted namespace for skip/tier rule conditions. Malicious config could execute arbitrary code.
- **Fix**: Replaced with safe condition DSL in `folio/core/classifier.py`. 12 condition types, no code execution. Legacy `parse_legacy_eval_condition()` provided for migration.

### [#002] Hardcoded funders in ingest.py
- **Priority**: P0
- **Status**: Fixed in folio
- **What**: `ingest.py` had `VALID_FUNDERS = frozenset({'TAC', 'OAC', 'CCA', 'BCAH'})` and `VALID_DOC_TYPES` hardcoded.
- **Fix**: Now validates against `config.funders` dict and `config.doc_types` list.

### [#003] Hardcoded Datalab pipeline ID
- **Priority**: P0
- **Status**: Fixed in folio
- **What**: `ingest.py` and `datalab_retry.py` had `PIPELINE_ID = 'pl_b-mZV9v283iM'` hardcoded.
- **Fix**: Now reads from `config.converter.datalab_pipeline_id`.

### [#004] Hardcoded useless headings in clean_md.py
- **Priority**: P1
- **Status**: Fixed in folio
- **What**: `clean_md.py` had `USELESS_HEADINGS` regexes referencing "Toronto Arts Council", "TAC", "InterAccess 411256" — 12 IA-specific patterns.
- **Fix**: All heading-removal patterns now come from config's `useless_headings` list.

### [#005] Hardcoded stale content patterns in audit_wiki.py
- **Priority**: P1
- **Status**: Fixed in folio
- **What**: `audit_wiki.py` `find_stale_content()` hardcoded IA addresses (Dupont, Lisgar, Ossington, Richmond).
- **Fix**: Replaced with configurable `stale_content_patterns` list in audit config. Empty by default.

### [#006] Hardcoded topic keywords in find_stats.py
- **Priority**: P2
- **Status**: Not yet ported
- **What**: `find_stats.py` `TOPIC_KEYWORDS` references IA programs (Vector Festival, Terra Firma).
- **Fix**: Make topic keywords configurable when ported.

---

## Architecture Improvements Discovered

### [#007] SequenceMatcher autojunk issue
- **Priority**: P1
- **Status**: Fixed in folio
- **What**: Python's `SequenceMatcher` defaults to `autojunk=True`, which silently treats repetitive sequences as "junk" and excludes them from comparison. Grant documents have repetitive sections (boilerplate, form fields) that get incorrectly skipped.
- **Fix**: All `SequenceMatcher` calls in `canonicalizer.py` now use `autojunk=False`.

### [#008] SequenceMatcher scaling for large archives
- **Priority**: P2
- **Status**: Mitigated in folio
- **What**: `SequenceMatcher` is O(n²) for content comparison. For 1000+ files, dedup checking all pairs is too slow.
- **Fix**: Auditor uses 3-stage filtering (size banding → Jaccard name pre-filter → truncated quick_ratio) before full ratio(). Should eventually use TF-IDF or MinHash for very large archives.

### [#009] Python 3.14+ requirement too new
- **Priority**: P0
- **Status**: Fixed in folio
- **What**: Prototype required Python >=3.14 (which didn't exist at the time — bleeding edge).
- **Fix**: Folio requires >=3.10. Uses `from __future__ import annotations` where needed.

### [#010] No config schema validation in prototype
- **Priority**: P1
- **Status**: Fixed in folio
- **What**: Prototype had no validation of config files. Typos in YAML keys silently produced default behavior or crashes.
- **Fix**: Folio has `config/schema.py` with dataclass models and `config/loader.py` with validation. Raises clear errors for invalid values.

### [#011] No shared error taxonomy
- **Priority**: P2
- **Status**: Fixed in folio
- **What**: Each prototype tool returned different error formats (strings, None, exceptions, print-to-stderr).
- **Fix**: `folio/core/errors.py` defines `FileStatus` and `ProcessingTier` enums used across all modules.

---

## Porting Decisions & Tradeoffs

### [#012] No Pydantic dependency (yet)
- **Priority**: P2
- **Status**: Deferred
- **What**: Config validation uses plain dataclasses instead of Pydantic to keep dependencies minimal. Pydantic would provide better validation messages and type coercion.
- **Decision**: Stay with dataclasses for now. Add Pydantic as optional dependency later.

### [#013] `import yaml` vs `from yaml import safe_load`
- **Priority**: P2
- **Status**: Inconsistent
- **What**: Some modules `import yaml` and use `yaml.safe_load()`, others may use different patterns. Should standardize.
- **Decision**: Standardize on `import yaml` with `yaml.safe_load()`.

### [#014] `datalab-python-sdk` is proprietary, not on PyPI
- **Priority**: P2
- **Status**: Documented
- **What**: Datalab SDK is proprietary. Must be installed separately. Marker/docling converters are stubs.
- **Decision**: Datalab remains the default but converter is pluggable. Document how to install and use alternatives.

---

## Future Work (from porting observations)

### [#015] LLMProvider abstraction doesn't return token counts
- **Priority**: P2
- **Status**: Open
- **What**: The `LLMProvider.complete()` method returns only the completion text. The rewriter needs `input_tokens`/`output_tokens` from the API response for cost tracking. Currently, the rewriter bypasses the provider abstraction and creates its own `OpenAI` client.
- **Fix**: Extend the `LLMProvider` interface to return `(text, usage_metadata)` tuple, or add a separate `complete_with_usage()` method.

### [#016] agentmap as Python library
- **Priority**: P2
- **Status**: Not started
- **What**: agentmap is a Go binary (external dependency). Porting its heading extraction + fuzzy matching (~500 lines of Go) to Python would remove one external dependency.
- **Recommendation**: Evaluate after core pipeline ships.

### [#016] French language detection
- **Priority**: P3
- **Status**: Not started
- **What**: Canadian arts orgs have French documents (CCA, BCAH). The pipeline doesn't detect language. French documents would get English heading taxonomies applied incorrectly.
- **Recommendation**: Add language detection pass before heading normalization.

### [#017] Filename convention fragility
- **Priority**: P2
- **Status**: Not addressed
- **What**: Entire pipeline depends on `FUNDER__Year_Topic__SubTopic.md` naming with `__` separators. This convention is undocumented and fragile.
- **Recommendation**: Document the convention. Add a filename validation pass. Support alternative naming schemes via config.

---

## Code Review Findings (2026-06-15)

Full review of all 48 source files. 93 findings: 13 critical, 21 high, 28 medium, 31 low.

### Critical (P0 — must fix before production use)

### [#018] Pipeline `_run_rewrite` calls `rewrite_directory` with wrong signature
- **Priority**: P0
- **Status**: Open
- **Where**: `core/pipeline.py:582`
- **What**: `rewrite_directory(clean_dir, rewrite_dir, config)` passes `rewrite_dir` as the `manifest_path` parameter. The function signature is `rewrite_directory(directory, config, manifest_path=None, ...)`. This will crash at runtime.
- **Fix**: Use keyword arguments: `rewrite_directory(clean_dir, config, manifest_path=manifest_path)`.

### [#019] `prioritizer._validate_priorities` returns wrong types on error
- **Priority**: P0
- **Status**: Open
- **Where**: `core/prioritizer.py:375`
- **What**: Returns `(priorities, {})` when raw_priorities is not a dict, but the caller unpacks as `priorities, errors`. If errors becomes an empty dict, `.append()` will crash.
- **Fix**: Always return `(priorities, errors)` with proper list type for errors.

### [#020] `classifier._evaluate_skip_rules` and `_evaluate_tier_rules` silently swallow all exceptions
- **Priority**: P0
- **Status**: Open
- **Where**: `core/classifier.py:630-632, 648-650`
- **What**: `except Exception: continue` swallows ValueError, KeyError, TypeError, etc. A misconfigured rule produces no results silently.
- **Fix**: Log exceptions at WARNING level, or only catch expected exception types.

### [#021] Broken retry logic in `rewrite_directory`
- **Priority**: P0
- **Status**: Open
- **Where**: `core/rewriter.py` thread pool section
- **What**: The retry loop calls `future.result()` in a loop, but a completed future caches its result. Only the first call returns the fresh result; subsequent calls return the same cached value. `max_retries` has no effect for the concurrent path.
- **Fix**: Re-submit the task on retry instead of re-reading the completed future.

### [#022] Manifest mutation race condition in `rewrite_directory`
- **Priority**: P0
- **Status**: Open
- **Where**: `core/rewriter.py:951-958`
- **What**: `update_file` and `recalculate_summary` mutate `manifest["files"]` from multiple threads simultaneously. `recalculate_summary` iterates `files.values()` while another thread may be adding entries — non-atomic.
- **Fix**: Add a `threading.Lock` around manifest mutations.

### [#023] `_call_llm` sends DeepSeek-specific params to all providers
- **Priority**: P0
- **Status**: Open
- **Where**: `core/rewriter.py:518-521`
- **What**: `reasoning_effort` and `thinking` extra_body are DeepSeek-specific. Sending them to OpenAI, Anthropic, or other providers will cause API errors.
- **Fix**: Gate behind provider check, or catch API errors and retry without them.

### [#024] Missing null check on `response.usage` in `_call_llm`
- **Priority**: P0
- **Status**: Open
- **Where**: `core/rewriter.py:526-528`
- **What**: `response.usage.prompt_tokens` — some providers don't include `usage`. Will crash with `AttributeError`.
- **Fix**: Use `getattr(response, 'usage', None)` with safe defaults.

### [#025] `rewrite_file` bypasses LLMProvider, reads private attrs
- **Priority**: P0
- **Status**: Open
- **Where**: `core/rewriter.py:731-737`
- **What**: Reads `llm_provider._base_url` and `_api_key` (private attributes) to construct a new OpenAI client, discarding the provider. Violates encapsulation.
- **Fix**: Extend `LLMProvider.complete()` to return `(text, usage_dict)` and use it directly.

### [#026] `thinking_enabled` None coercion bug
- **Priority**: P0
- **Status**: Open
- **Where**: `core/rewriter.py:638`
- **What**: `str(thinking_raw).lower() != "disabled"` converts `None` to `"none"` → `True`, enabling thinking mode when user didn't request it.
- **Fix**: Check `thinking_raw is not False` or `thinking_raw is True`.

### [#027] `ingester` imports non-existent function `rewrite_documents`
- **Priority**: P0
- **Status**: Open
- **Where**: `core/ingester.py:263`
- **What**: `from folio.core.rewriter import rewrite_documents` — this function doesn't exist. Import always fails, caught by `except ImportError`. Dead code branch.
- **Fix**: Replace with `rewrite_file` or remove the feature until implemented.

### [#028] 9 CLI stubs registered as entry points
- **Priority**: P1
- **Status**: Open
- **What**: `pyproject.toml` registers `folio-clean`, `folio-classify`, `folio-rewrite`, `folio-prioritize`, `folio-canonicalize`, `folio-ingest`, `folio-audit`, `folio-scan`, `folio-teach` as entry points, but all print "not yet implemented." Running them gives a dead-end experience.
- **Fix**: Either implement them or remove from `[project.scripts]` until ready.

### High (P1 — important to fix)

### [#029] Three separate manifest implementations
- **Priority**: P1
- **Status**: Open
- **What**: `core/manifest.py`, `core/pipeline.py` (private `_load_manifest`), and `core/prioritizer.py` (private `_load_manifest`) each define their own manifest schema and load/save functions. Three different key conventions for the same concept.
- **Fix**: Unify into `core/manifest.py` with a shared schema.

### [#030] Duplicate rate-limiting implementations
- **Priority**: P1
- **Status**: Open
- **What**: `core/rewriter.py:865-877` and `core/prioritizer.py:854-865` implement identical rate-limiting logic.
- **Fix**: Extract into `core/throttle.py` shared utility.

### [#031] Duplicate `_deep_merge` functions
- **Priority**: P1
- **Status**: Open
- **What**: `core/init.py:215-222` and `config/loader.py:30-38` have identical `_deep_merge` functions.
- **Fix**: Import from `config.loader` or move to shared utility.

### [#032] `canonicalize_directory` swallows JSON parse errors from LLM
- **Priority**: P1
- **Status**: Open
- **Where**: `core/canonicalizer.py:546-549`
- **What**: `json.loads()` on untrusted LLM output with fragile code-fence regex stripping. Parse failures silently skipped via bare `except:`.
- **Fix**: Use `_parse_llm_response()` from prioritizer.py. Log parse failures.

### [#033] `sage_wiki` backend: search/query don't check subprocess success
- **Priority**: P1
- **Status**: Open
- **Where**: `adapters/wiki/sage_wiki.py:63-69, 74-80`
- **What**: `subprocess.run()` without `check=True`. Failed search returns empty string silently — caller can't distinguish "no results" from "sage-wiki crashed."
- **Fix**: Add `check=True` and handle `CalledProcessError`.

### [#034] Config `base_url` validation rejects `http://` localhost URLs
- **Priority**: P1
- **Status**: Open
- **Where**: `config/loader.py:141-144`
- **What**: Validates for `https://` only. Local dev proxies (Ollama, LM Studio, localhost) use `http://`.
- **Fix**: Also allow `http://` for localhost/private IPs.

### [#035] `frontmatter.update_frontmatter` uses regex on raw YAML text
- **Priority**: P1
- **Status**: Open
- **Where**: `core/frontmatter.py:140-142`
- **What**: `re.sub` on YAML text can match colons in quoted values, multi-line strings, or comments. Example: if a description value contains `funder: OAC`, the regex will match and corrupt it.
- **Fix**: Parse YAML, update dict, serialize back. Don't regex-replace on YAML text.

### [#036] Skills template path uses 4-level `.parent` — breaks when installed
- **Priority**: P1
- **Status**: Open
- **Where**: `core/skills.py:15`
- **What**: `Path(__file__).resolve().parent.parent.parent.parent / "skills"` — if the package is installed in `site-packages/`, the skills directory won't be found.
- **Fix**: Use `importlib.resources` or package skills templates with the package data.

### [#037] `from __future__ import annotations` — inconsistent across codebase
- **Priority**: P2
- **Status**: Open
- **What**: 10 modules use it, 10 modules don't. No clear pattern.
- **Fix**: Standardize: either all modules or none.
