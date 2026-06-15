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
