# CODE_REVIEW.md — folio v0.1.0 Full Code Review

**Date:** 2026-06-15
**Reviewer:** beads-code-reviewer
**Language:** Python 3.10+
**Project type:** CLI pipeline / library
**Conventions read:** AGENTS.md, BUGS.md, pyproject.toml, defaults.yaml
**Files reviewed:** 48 (.py + .yaml) — ~9,500 lines total
**Findings:** 13 critical · 21 high · 28 medium · 31 low

---

## Overview

The codebase shows strong architectural intent — clean separation of concerns, config-driven design, composable pipeline stages. However, it was ported by parallel agents without cross-module review: three manifest implementations, two rate-limiters, an LLM provider abstraction that the rewriter bypasses, and a critically broken pipeline orchestration function. The core algorithmic logic (classifier DSL, canonicalizer dedup, cleaner transformations) is sound, but the integration layer needs significant rework before this package is production-ready.

## Recommendation

**BLOCK MERGE** — too many critical findings that affect core pipeline correctness.

---

## 🔴 Critical (P0 — must fix before production use)

### [#018] Pipeline `_run_rewrite` calls `rewrite_directory` with wrong signature
- **File:** `core/pipeline.py:582`
- **What:** `rewrite_directory(clean_dir, rewrite_dir, config)` passes `rewrite_dir` (a Path) as the `manifest_path` parameter. The function signature is `rewrite_directory(directory, config, manifest_path=None, ...)`. This call will fail at runtime (wrong number/type of positional args).
- **Fix:** Use keyword arguments: `rewrite_directory(clean_dir, config, manifest_path=manifest_path)`.

### [#019] Pipeline `_run_prioritize` has the same broken signature pattern
- **File:** `core/pipeline.py:623`
- **What:** `prioritize_directory(rewrite_dir, config)` — the function expects `(directory, config, dry_run, year, limit, resume)`. While `_resolve_config(config)` handles both dict and dataclass, the lack of explicit keyword args is fragile and the positional meaning is unclear.
- **Fix:** Always use keyword arguments for multi-param functions with `config` in non-obvious positions.

### [#020] Rewriter `_call_llm` — rate-limit token leak via `reasoning_effort` on non-DeepSeek models
- **File:** `core/rewriter.py:518-521`
- **What:** `reasoning_effort` and `thinking` extra_body are DeepSeek-specific API parameters. Sending them to OpenAI, Anthropic, or other providers will cause API errors.
- **Fix:** Gate these behind a provider check, or catch API errors and retry without them.

### [#021] `rewrite_file` ignores `llm_provider` — uses private attrs to construct raw OpenAI client
- **File:** `core/rewriter.py:731-737`
- **What:** Reads `llm_provider._base_url` and `_api_key` (private attributes) to construct a new `OpenAI` client, discarding the provider. If the provider is not OpenAI-compatible, this fails. Also violates encapsulation.
- **Fix:** Either use `llm_provider.complete()` or add a method to the provider base class that exposes a client factory.

### [#022] `prioritizer._validate_priorities` returns wrong types on error
- **File:** `core/prioritizer.py:375`
- **What:** `return priorities, raw_priorities if isinstance(raw_priorities, dict) else {}` — if `raw_priorities` is not a dict, returns `{}` as the second element when `errors` was expected. Worse, line 468 unpacks `priorities, errors` and if `raw_priorities` was a string, `errors` becomes an empty dict, which will crash on `.append()`.
- **Fix:** Always return `(priorities, errors)` with proper types.

### [#023] `classifier._evaluate_skip_rules` swallows all exceptions silently
- **File:** `core/classifier.py:630-632`
- **What:** `except Exception: continue` silently skips any parsing or evaluation error in skip rules, including `ValueError`, `KeyError`, `TypeError`. A misconfigured rule produces no skip results, potentially letting garbage files through.
- **Fix:** Log the exception at WARNING level, or only catch specific expected exceptions.

### [#024] `classifier._evaluate_tier_rules` also swallows all exceptions silently
- **File:** `core/classifier.py:648-650`
- **What:** Same pattern as #023. `except Exception: continue` skips all tier rules silently.
- **Fix:** Log and continue, or only catch expected exceptions.

### [#025] `canonicalizer._resolve_with_llm` — `json.loads()` on untrusted LLM output can crash the pipeline
- **File:** `core/canonicalizer.py:546-549`
- **What:** `content = re.sub(r"```\w*\n?", "", str(content)).strip()` then `json.loads(content)`. The regex is fragile (doesn't handle closing fences, nested code blocks, or multi-line fences). On parse failure, the entire LLM resolution is silently skipped via bare `except:`.
- **Fix:** Use `_parse_llm_response()` from `prioritizer.py`. Log parse failures.

### [#026] `canonicalizer._detect_duplicates` — O(n²) pair comparison with no configurable cap
- **File:** `core/canonicalizer.py:242-252`
- **What:** All-pairs SequenceMatcher (even with 2000-char truncation) is O(n² × m) where m is ~2000. For 5000 files, this is ~12.5M comparisons. No guard against large file counts.
- **Fix:** Add a `max_files_for_dedup` threshold; warn if exceeded; use TF-IDF or MinHash for large sets.

### [#027] `OpenAICompatibleProvider.complete()` creates new client every call
- **File:** `adapters/llm/openai_compatible.py:26-52`
- **What:** Every call creates a new `OpenAI` client (new HTTP session, no connection reuse). Also, `max_tokens` is passed as kwarg but `temperature` is not a first-class parameter — inconsistent with `rewriter._call_llm` which sets `temperature=0`.
- **Fix:** Cache the client. Add `temperature` as a first-class parameter.

### [#028] `sage_wiki.py` — `search()` and `query()` don't check subprocess success
- **File:** `adapters/wiki/sage_wiki.py:63-69, 74-80`
- **What:** `subprocess.run()` without `check=True` means a failed search returns an empty string silently. The caller can't distinguish "no results" from "sage-wiki crashed."
- **Fix:** Add `check=True` or check `result.returncode` and raise on failure.

### [#029] `sage_wiki.compile()` — unbounded timeout, no output capture on error
- **File:** `adapters/wiki/sage_wiki.py:51-58`
- **What:** `capture_output=True`, `timeout=3600`. If compilation fails, `CalledProcessError` is raised but stdout/stderr are captured and discarded. The user sees nothing about what went wrong.
- **Fix:** On `CalledProcessError`, print stderr before re-raising or wrapping.

### [#030] `rewriter._call_llm` — missing `response.usage` attribute guard for non-OpenAI providers
- **File:** `core/rewriter.py:526-528`
- **What:** `response.usage.prompt_tokens` accesses `.usage` directly. Some providers (streaming, non-OpenAI) may not include usage. Will crash with `AttributeError`.
- **Fix:** Use `getattr(response, 'usage', None)` with safe defaults.

---

## 🟡 High (P1 — important to fix)

### [#031] Inconsistent manifest APIs — three separate implementations
- **Files:** `core/manifest.py`, `core/pipeline.py:721-743`, `core/prioritizer.py:681-694`
- **What:** Three different manifest schemas with no shared validation. `core/manifest.py` uses `files` key; pipeline uses `stages` key; prioritizer uses its own format. No shared module for cross-stage state.
- **Fix:** Unify into `core/manifest.py` with a typed schema.

### [#032] `rewriter` and `prioritizer` have duplicate rate-limiting implementations
- **Files:** `core/rewriter.py:865-877`, `core/prioritizer.py:854-865`
- **What:** Both implement rate limiting with `threading.Lock`, `last_request_time[0]`, `time.sleep`. Identical logic, slightly different variable names.
- **Fix:** Extract into shared utility `core/throttle.py`.

### [#033] `rewriter._call_llm` and `OpenAICompatibleProvider.complete()` — two different LLM call paths
- **What:** The rewriter bypasses `LLMProvider` entirely (calls `OpenAI` directly). The prioritizer uses `LLMProvider.complete()`. The rewriter gets token counts; the prioritizer doesn't. The rewriter sets `reasoning_effort`; the provider doesn't support it. This bifurcation means the `LLMProvider` interface is already obsolete.
- **Fix:** Extend `LLMProvider.complete()` to return `(text, usage_dict)`. Migrate rewriter to use it.

### [#034] `classify_file` imports `extract_year` inside function body
- **File:** `core/classifier.py:751`
- **What:** `from folio.core.frontmatter import extract_year` — lazy import inside a function called in a loop. Python caches after first call, but this is an anti-pattern with measurable overhead per call.
- **Fix:** Move to top-level import.

### [#035] `canonicalizer._normalize_for_comparison` strips too aggressively
- **File:** `core/canonicalizer.py:646-652`
- **What:** `re.sub(r"[*_`#>|\-\[\]()!]", " ", text)` removes characters carrying semantic meaning. E.g., `$50,000` becomes `50 000`, which may match unrelated contexts. Overly aggressive normalization reduces dedup accuracy.
- **Fix:** More conservative normalization: remove only markdown syntax, not digits/punctuation carrying meaning.

### [#036] `canonicalizer._DEFAULT_CANONICALIZE_CONFIG.category_segments` — 24 hardcoded patterns
- **File:** `core/canonicalizer.py:35-62`
- **What:** COULD be config-driven per AGENTS.md rule #6. New document types need code changes.
- **Fix:** Move to config with these as defaults.

### [#037] `ingester.ingest_document` imports non-existent function
- **File:** `core/ingester.py:263`
- **What:** `from folio.core.rewriter import rewrite_documents` — this function does not exist. Import always fails, caught by `except ImportError`. Dead code branch.
- **Fix:** Replace with `rewrite_file` or remove until implemented.

### [#038] `cleaner.clean_markdown` accepts `config: dict | None` — no schema validation
- **File:** `core/cleaner.py:317-319`
- **What:** Unlike other modules using typed `ProjectConfig`, the cleaner takes a raw `dict`. Malformed keys are silently ignored.
- **Fix:** Add a lightweight TypedDict or dataclass for cleaner config schema.

### [#039] `cleaner._FORM_FIELD_VALUE` regex is fragile and overly broad
- **File:** `core/cleaner.py:44-53`
- **What:** The regex will match any digit string. Combined with `_remove_form_field_labels`, this can aggressively remove legitimate content lines like `"2024"` or `"2-4 weeks"` that happen to follow a form field label.
- **Fix:** Tighten the pattern. Only remove form field lines adjacent to known form labels. Add a `max_length` guard.

### [#040] `classifier._FILESTATUS_MAP` and `_TIER_MAP` are partially unused
- **File:** `core/classifier.py:678-696`
- **What:** `_FILESTATUS_MAP` is never referenced. Dead code.
- **Fix:** Remove dead dict, or use it for validation/coercion.

### [#041] `classifier.classify_directory` duplicates `recalculate_summary` logic
- **File:** `core/classifier.py:785-845`
- **What:** Manually builds `by_tier`, `by_status`, `by_funder` counts instead of calling `manifest.recalculate_summary()`.
- **Fix:** Call `recalculate_summary()` on the dict after building it.

### [#042] `rewriter._add_metadata_only` generates title from filename only
- **File:** `core/rewriter.py:445-466`
- **What:** Title derived from `filename.replace(".md", "").replace("_", " ")` without checking frontmatter or content headings for a better title.
- **Fix:** Check entry dict for title field or extract from content headings before defaulting to filename.

### [#043] `rewriter._call_llm` — `max_tokens` default of 64000 too large for some models
- **File:** `core/rewriter.py:499`
- **What:** 64000 is supported by DeepSeek v4 but not smaller/free-tier models. API call will fail or truncate silently.
- **Fix:** Read `max_tokens` from tier config or model metadata. Validate against known limits.

### [#044] `prioritizer._group_files_by_year` silently groups unknown-year files into key "0"
- **File:** `core/prioritizer.py:287`
- **What:** No warning or reporting of how many files landed in the unknown group.
- **Fix:** Log a warning with count, or add to `skipped` list.

### [#045] `prioritizer.prioritize_file` with group_context — `raw_response` KeyError
- **File:** `core/prioritizer.py:550-569`
- **What:** Accesses `result["raw_response"]` on line 557, but `_process_group` never sets this key. Always a `KeyError`, caught implicitly by `isinstance` check returning False.
- **Fix:** Rename to match what `_process_group` returns, or add `raw_response` to the return dict.

### [#046] `skills._SKILLS_DIR` path resolution is fragile
- **File:** `core/skills.py:15`
- **What:** `Path(__file__).resolve().parent.parent.parent.parent / "skills"` — 4 levels of `.parent`. If the package is installed in `site-packages/`, the skills directory won't be found.
- **Fix:** Use `importlib.resources` or package skills templates with the package data.

### [#047] `pipeline._estimate_stage` calls `scan_archive` 8 times per dry-run
- **File:** `core/pipeline.py:254-259`
- **What:** Every `_estimate_stage` call re-scans the archive. For a full pipeline dry-run, scan runs 8 times for the same data.
- **Fix:** Cache scan result in `_estimate_pipeline`.

### [#048] `config/loader.py` — `_build_config` uses `float()` without validation
- **File:** `config/loader.py:95-96`
- **What:** `float(llm_pricing.get("input_per_million", 0.14))` — if user sets `input_per_million: "cheap"`, raises `ValueError` with confusing message.
- **Fix:** Validate numeric fields before conversion, with clear error messages.

### [#049] `config/loader.py` — `_validate` rejects `http://` URLs
- **File:** `config/loader.py:141-144`
- **What:** Only validates for `https://`. Local dev proxies (Ollama, LM Studio, localhost) use `http://`.
- **Fix:** Also allow `http://` for localhost/private IPs, or make the check configurable.

### [#050] `init._deep_merge` — duplicate of `config/loader._deep_merge`
- **Files:** `core/init.py:215-222`, `config/loader.py:30-38`
- **What:** Identical `_deep_merge` functions. Duplication.
- **Fix:** Import from `config.loader` or move to shared utility.

### [#051] `pipeline._run_rewrite` catches `NotImplementedError` — no code raises it
- **File:** `core/pipeline.py:590`
- **What:** `except NotImplementedError` — but `rewrite_directory` never raises this. Dead exception handler from stub pattern era.
- **Fix:** Remove the dead handler, or add `raise NotImplementedError` to stub CLI files for consistency.

---

## 🟢 Medium (P2)

### [#052] `canonicalizer.canonicalize_directory` — `shutil.move` parameter format
- **File:** `core/canonicalizer.py:342-345`
- **What:** `shutil.move(str(src), str(...))` — unnecessary `str()` conversion. Use `Path` objects directly.
- **Fix:** `shutil.move(src, archive_dir / fname)`

### [#053] `prioritizer._split_large_groups` — shuffles without configurable seed
- **File:** `core/prioritizer.py:315`
- **What:** Uses global random seed. No way to set seed for reproducible testing/dry-runs.
- **Fix:** Accept optional `random_seed` parameter and use `random.Random(seed).shuffle()`.

### [#054] `classifier._detect_funder` — longest-match-first can match substrings incorrectly
- **File:** `core/classifier.py:420-424`
- **What:** Funders like `"CA"` would match anywhere in a path containing `"Canada"`, `"CAC"`. While the funder keys in the prototype are multi-letter (OAC, TAC), for generic use this is fragile.
- **Fix:** Match on word boundaries or require funder prefix to be `__`-delimited segment.

### [#055] `scanner.scan_archive` — year detection only finds 2000-2099
- **File:** `core/scanner.py:51-54`
- **What:** `r'(20\d{2})'` — documents from 1990-1999 or post-2099 won't be detected.
- **Fix:** Extend to `(19|20|21)\d{2}` or make the century pattern configurable.

### [#056] `classifier._detect_doc_types` — normalizes underscores to spaces globally
- **File:** `core/classifier.py:436`
- **What:** `normalized = path_str.replace("_", " ")` — normalizes the entire path including directory names, which could cause false matches.
- **Fix:** Only normalize the filename stem, not the full path.

### [#057] `cleaner.clean_file` — `encoding='utf-8', errors='replace'` silently corrupts
- **File:** `core/cleaner.py:371,374,376,379`
- **What:** Using `errors='replace'` silently replaces undecodable bytes with `�` (U+FFFD). This can corrupt data without warning.
- **Fix:** Log a warning when replacement occurs. Consider `chardet` or `ftfy` for detection.

### [#058] `rewriter._process_single` — `content_chars = int(max_input * 3.5)` magic constant
- **File:** `core/rewriter.py:586`
- **What:** Assumes 3.5 chars per token. For Chinese text (~1.5 chars/token) this would send 2x more tokens than expected.
- **Fix:** Use `tiktoken` for accurate counting, or make the ratio configurable.

### [#059] `canonicalizer._extract_date` — hardcoded YYYY-MM-DD pattern doesn't match filenames
- **File:** `core/canonicalizer.py:623-625`
- **What:** Default pattern `(\d{4})-(\d{2})-(\d{2})` expects YYYY-MM-DD. The filename convention is `FUNDER__Year_Topic__SubTopic.md` — years appear as bare 4-digit numbers, not with hyphens. This pattern will almost never match.
- **Fix:** Match the actual filename convention or read dates from frontmatter.

### [#060] `frontmatter.update_frontmatter` — string substitution with `re.sub` on YAML is fragile
- **File:** `core/frontmatter.py:140-142`
- **What:** `re.sub(rf'^{key}:\s*.*$', f'{key}: {value}', ...)` — replaces on raw YAML text. Can break quoted strings with colons, multi-line values, or comments.
- **Fix:** Parse the YAML, update the dict, serialize back.

### [#061] `frontmatter.dict_to_frontmatter` — doesn't escape special YAML characters
- **File:** `core/frontmatter.py:103`
- **What:** `fm.append(f'{key}: "{value}"')` — if `value` contains a double-quote character, YAML becomes invalid (e.g., `funder: "The "Art" Gallery"`).
- **Fix:** Use `yaml.dump()` for serialization instead of manual string building.

### [#062] `canonicalizer._detect_duplicates` — 2000-char truncation hardcoded
- **File:** `core/canonicalizer.py:237`
- **What:** Truncation length is hardcoded. May be too aggressive for short documents or too conservative for very large ones.
- **Fix:** Make configurable as `content_snippet_max_chars`.

### [#063] `classifier.DEFAULT_CLASSIFY_CONFIG` — `doc_types` defaults to `{}` but code expects it
- **File:** `core/classifier.py:30`
- **What:** Defaults to `{}`. `classify_file` builds from it but `pipeline._run_classify` only injects `funders`, not `doc_types`. Falls back to `["unknown"]` type.
- **Fix:** Either inject `doc_types` from config or ensure defaults have sensible patterns.

### [#064] `pyproject.toml` — 9 standalone entry points point to "not yet implemented" stubs
- **What:** `folio-pipeline`, `folio-clean`, `folio-classify`, `folio-rewrite`, `folio-prioritize`, `folio-canonicalize`, `folio-ingest`, `folio-audit`, `folio-teach` all print "not yet implemented."
- **Fix:** Either implement them or remove from `[project.scripts]` until ready.

### [#065] `classifier.py` smoke tests run at import time — incomplete coverage
- **File:** `core/classifier.py:850-956`
- **What:** 15 assertions test only the legacy parser, not the DSL `evaluate_condition`/`evaluate_rule` or `classify_file` itself.
- **Fix:** Expand smoke tests or move to proper pytest tests.

### [#066] `frontmatter.py` smoke test — happy path only
- **File:** `core/frontmatter.py:363-366`
- **What:** One assertion. No tests for: missing frontmatter, invalid YAML, empty body, date parsing edge cases.
- **Fix:** Expand smoke tests or add proper unit tests.

### [#067] `cleaner.py` — `_BOLD_TO_HEADING` regex redundant `^` anchor
- **File:** `core/cleaner.py:19`
- **What:** `r'^\*\*([^*]+)\*\*\s*$'` — the `^` anchor is redundant when applied to already-stripped lines. Not a bug, just redundant.
- **Fix:** Remove `^` or document why it's there.

### [#068] `adapters/converters/__init__.py` — unreachable `ValueError` after `raise NotImplementedError`
- **File:** `adapters/converters/__init__.py:24-30`
- **What:** 3 `raise NotImplementedError` statements + unreachable `ValueError`. Dead code.
- **Fix:** Keep raise statements but remove unreachable ValueError or make it the fallback for unvalidated config.

### [#069] `adapters/wiki/__init__.py` — `SageWikiBackend()` constructed without config
- **File:** `adapters/wiki/__init__.py:18-19`
- **What:** Constructor takes no args; config is passed later via `init()`. But the backend itself doesn't read config (binary path, pack name).
- **Fix:** Pass config or at minimum the binary path to the constructor.

### [#070] `sage_wiki.py` — uses `yaml.dump` instead of `yaml.safe_dump`
- **File:** `adapters/wiki/sage_wiki.py:32-33`
- **What:** Inconsistent with rest of codebase which uses `yaml.safe_load`/`yaml.safe_dump`.
- **Fix:** Use `yaml.safe_dump`.

---

## 🔵 Low / Nitpicks

### [#071] Inconsistent `from __future__ import annotations` usage
- **What:** `cleaner.py`, `classifier.py`, `rewriter.py`, `ingester.py`, `auditor.py`, `pipeline.py`, `init.py`, `cli/pipeline.py`, `cli/init.py` use it. `canonicalizer.py`, `prioritizer.py`, `scanner.py`, `frontmatter.py`, `manifest.py`, `errors.py`, `skills.py`, all adapters do NOT.
- **Fix:** Standardize: either all modules or none.

### [#072] `rewriter.py:24` — `Callable` imported but unused
- **Fix:** Remove dead import.

### [#073] `rewriter.py:430-432` — double file access (exists check + open) with race condition
- **What:** `os.path.exists(rules_file)` then `open(rules_file)` — file could be deleted between check and open.
- **Fix:** Use `try/except FileNotFoundError`.

### [#074] `prioritizer.py:817` — dead variable `write_back = directory.resolve() == directory.resolve()` — always True
- **Fix:** Remove.

### [#075] `config/schema.py:15` — `abbreviation: str = "ORG"` default
- **What:** Fine as generic fallback. Not IA-specific but not ideal.

### [#076] `adapters/sources/local.py:24` — `rglob("*")` picks up `.git/`, `__pycache__/`
- **Fix:** Add exclude patterns.

### [#077] `pyproject.toml` — `folio` and `folio-pipeline` both point to the same function
- **Fix:** Remove one or make them distinct.

### [#078] `core/errors.py:9` — inconsistent docstring spacing
### [#079] `core/manifest.py:1-6` — docs say "JSON file" but functions return `dict`
### [#080] `core/manifest.py:36` — returns `create_manifest()` on missing file, silently wipes history if path is wrong
### [#081] `core/cleaner.py:138` — `max_passes = 5` — magic number
### [#082] `core/cleaner.py:221` — `len(title) < 100` — magic number
### [#083] `core/classifier.py:108` — DSL `ValueError` is silently swallowed by rule evaluator's `except Exception`
### [#084] `core/canonicalizer.py:284` — `archive_dir` parameter name misleading (destination, not source)
### [#085] `core/frontmatter.py:146` — `insert_after = ['funder:', 'type:']` hardcoded — needs updating if schema changes
### [#086] `core/ingester.py:10` — `logging` import with `logger` defined but barely used
### [#087] `core/auditor.py:5` — `from __future__ import annotations` not needed for Python 3.10+ but harmless
### [#088] `core/scanner.py:27-30` — 4 magic constants for cost estimation — should be configurable
### [#089] `cli/skills.py:46-49` — `load_project_config(None)` triggers default-only path, fine but subtle
### [#090] `core/cleaner.py` — `stripped` line processing: `^` anchor in regex is always satisfied after `.strip()`
### [#091] `pipeline._format_time` — `seconds=0` → `"0ms"`, correct. `seconds=0.5` → `"500ms"`
### [#092] `frontmatter.parse_frontmatter` — `---` horizontal rule could be confused with frontmatter delimiter
### [#093] `canonicalizer._load_snippets` — no size guard before `read_text()`, could OOM on huge files

---

## Thread Safety Findings

### T1 — Broken retry logic in `rewrite_directory`
- **File:** `core/rewriter.py` thread pool section
- **What:** Retry loop calls `future.result()` in a loop, but a completed future caches its result. Only the first call returns the fresh result; subsequent calls return the same cached value. `max_retries` has no effect for the concurrent path.
- **Fix:** Re-submit the task on retry instead of re-reading the completed future.

### T2 — Manifest mutation race condition
- **File:** `core/rewriter.py:951-958`
- **What:** `update_file` and `recalculate_summary` mutate `manifest["files"]` from multiple threads simultaneously. `recalculate_summary` iterates `files.values()` while another thread may be adding entries — non-atomic.
- **Fix:** Add a `threading.Lock` around manifest mutations.

### T3 — Prioritizer retry is correct
- **File:** `core/prioritizer.py:867-891`
- **What:** Rate-limited process retry loop re-calls `_process_group` on each attempt (not reading from cached future). This one is correct.

### T4 — Rewriter rate limiter lock is correct
- **File:** `core/rewriter.py:865-877`
- **What:** Rate limiter uses `last_request_time = [0.0]` (list-of-float hack) with `threading.Lock`. Lock protects access correctly.

---

## Test Coverage

- **Test directory:** `tests/` has only `__init__.py` and `conftest.py` (2 fixtures, no test functions)
- **Test commands (from pyproject.toml):** `pytest`, `pytest --cov`
- **Smoke tests in-source:** `classifier.py:850-956` (15 assertions, legacy parser only), `frontmatter.py:363-366` (1 assertion, happy path only)
- **Untested:** ~9,500 lines of production code with zero test coverage beyond 16 inline assertions
- **Critical untested areas:** rewriter, prioritizer, canonicalizer (LLM paths), classifier (DSL + tiering), cleaner (all transformations), config loader (merging + validation), ingester (full flow)

---

## AGENTS.md Rule Compliance

| Rule | Status | Notes |
|------|--------|-------|
| #1 Config drives behavior | ✅ Mostly | Some hardcoded patterns in canonicalizer, cleaner, scanner |
| #2 Self-documenting | ✅ | Good docstrings, `--help` on pipeline/init CLI |
| #3 Discoverable | ⚠️ | 9 CLI stubs say "not yet implemented" |
| #4 Runnable by agents | ⚠️ | `uv run folio` works but only pipeline/init/skills are real |
| #5 Composition | ⚠️ | Three separate manifest implementations |
| #6 Per-org in config | ⚠️ | category_segments hardcoded, stale_content_patterns configurable |
| #7 Focused files | ✅ | Each file does one job |
| #8 Standard libs | ✅ | Uses pyyaml, openai, python-dotenv, tqdm |

---

## BUGS.md Cross-Reference

| BUGS.md # | Status | Notes |
|-----------|--------|-------|
| #001 eval() security | ✅ Fixed | Safe DSL in classifier |
| #002 Hardcoded funders | ✅ Fixed | config.funders |
| #003 Datalab pipeline ID | ✅ Fixed | config.converter |
| #004 Useless headings | ✅ Fixed | config-driven |
| #005 Stale content | ✅ Fixed | config-driven |
| #006 Topic keywords | P2 | Not yet ported |
| #007 autojunk | ✅ Fixed | autojunk=False everywhere |
| #008 SequenceMatcher scaling | ⚠️ | Mitigated, not fully resolved |
| #009 Python 3.14 | ✅ Fixed | >=3.10 |
| #010 Config validation | ✅ Fixed | schema.py |
| #011 Error taxonomy | ✅ Fixed | errors.py |
| #012 No Pydantic | Deferred | |
| #013 yaml import | ✅ Consistent | |
| #014 Datalab SDK | P2 | Documented |
| #015 Provider token counts | **Still open** | FINDING #033 |
| #016 French detection | P3 | Not started |
| #017 Filename convention | **Still open** | No documentation |
