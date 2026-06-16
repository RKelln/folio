# Pipeline Documentation

## Pipeline Overview

The folio pipeline transforms a raw document archive into a searchable knowledge base through eight automated stages. Each stage reads output from the previous stage, applies its transformation, and produces output for the next stage. The pipeline is designed to be resumable: checkpoint state is saved to a manifest JSON file after every stage, so a failure in stage 6 does not require re-running stages 1 through 5.

**The eight stages, in order:**

| Order | Stage | Purpose | Uses LLM |
|-------|-------|---------|----------|
| 1 | scan | Enumerate the archive, detect funders/years/types | No |
| 2 | convert | PDF/DOCX/XLSX to Markdown | No (external API) |
| 3 | clean | Remove form chrome, boilerplate, PDF artifacts | No |
| 4 | canonicalize | Detect drafts, resolve versions, deduplicate | Optional |
| 5 | classify | Score quality, assign processing tier | No |
| 6 | rewrite | LLM re-authoring with tiered prompts | Yes |
| 7 | prioritize | Score archival priority (1-3) by year groups | Yes |
| 8 | wiki | Compile markdown into searchable wiki | Depends on backend |

Stages 1-5 are deterministic (no LLM cost). Stages 6 and 7 are the primary cost drivers. Stage 2 may have external conversion costs depending on the converter configured.

### Directory Layout

The pipeline operates on this directory structure, defined in `folio.yaml` under `paths`:

```
org-library/
  archive/          (raw_archive)      PDF, DOCX, XLSX source files
  .folio/raw_md/    (raw_md)           Converter output — raw markdown
  .folio/clean_md/  (clean_md)         Cleaned markdown
  markdown/         (rewrite_md)       Final LLM-rewritten output
  wiki/             (wiki_project)     Wiki project directory
```

---

## Stage 1: scan

### Purpose

Scans the raw archive directory to enumerate all files, detect funder abbreviations and years from filenames, identify document types, flag likely drafts, and estimate pipeline costs. Produces a report that guides decision-making before any processing begins.

### Input

- `paths.raw_archive` (default: `./archive/`) — any file types. The scanner reads the directory listing and filename metadata only; it does not open file contents.

### Output

A scan report printed to stdout and (with `--json`) a structured dict containing:

- `total_files` — total file count
- `by_extension` — counts per file extension (`.pdf`, `.docx`, `.xlsx`, `.md`, etc.)
- `by_funder` — per-funder breakdowns with file counts and year ranges
- `by_year` — file counts per detected year
- `by_type` — file counts per detected document type
- `likely_drafts` — list of filenames matching draft markers
- `estimated_costs` — breakdown of estimated conversion, LLM rewrite, prioritize, and wiki costs
- `estimated_time_minutes` — projected total pipeline time

### Key Configuration

| Config option | Location | Effect |
|---------------|----------|--------|
| `paths.raw_archive` | `folio.yaml` > `paths` | Directory to scan |
| `funders` | `folio.yaml` > `funders` | Map of abbreviation to full name for detection |
| `doc_types` | `folio.yaml` > `doc_types` | Document type patterns to match in filenames |
| `llm.pricing` | `folio.yaml` > `llm` | Used for cost estimation of later stages |
| `converter.type` | `folio.yaml` > `converter` | Affects conversion cost estimate (datalab costs money; marker/docling are free) |

### Deterministic or LLM?

Deterministic. No API calls. Funder detection uses substring matching against the funders configured in `folio.yaml`. Year detection uses a regex for 4-digit years (2000-2099). Type detection uses configurable regex patterns against filename tokens.

### Dry-Run Behavior

The scanner itself is a read-only operation. When run as part of `folio pipeline --dry-run`, the scanner runs normally and its cost estimates feed the dry-run estimates for subsequent stages.

### Common Failure Modes

| Problem | Cause | Recovery |
|---------|-------|----------|
| Files not detected | `paths.raw_archive` points to wrong directory | Verify path in `folio.yaml` |
| Funders not detected | Funder abbreviations in `folio.yaml` don't match filename patterns | Add the abbreviation used in filenames to `funders` |
| Years not detected | Filenames lack 4-digit years | Rename files to include years, or use `folio init --guided` to set up patterns |

### CLI

```bash
folio scan                          # Scan default archive directory
folio scan --source ./my-archive/   # Scan a specific directory
folio scan --config custom.yaml     # Use a specific config file
folio scan --json                   # Output as JSON
```

---

## Stage 2: convert

### Purpose

Converts PDF, DOCX, and XLSX files in the raw archive to Markdown format. Uses a pluggable converter backend selected in `folio.yaml`.

### Input

- `paths.raw_archive` (source files in PDF, DOCX, XLSX, or other convertible formats)
- Only files with extensions supported by the configured converter are processed

### Output

- `paths.raw_md` (default: `.folio/raw_md/`) — one `.md` file per converted source file, preserving the original filename stem

The pipeline report records:
- `files` — total convertible files found
- `converted` — count of successful conversions
- `failed` — count of failures (with `failed_files` list up to 20 entries)
- `cost_usd` — conversion cost (0.00 for free converters)

### Key Configuration

| Config option | Location | Effect |
|---------------|----------|--------|
| `converter.type` | `folio.yaml` > `converter` | Which converter to use: `datalab`, `marker`, `docling`, or `null` |
| `paths.raw_archive` | `folio.yaml` > `paths` | Where source files live |
| `paths.raw_md` | `folio.yaml` > `paths` | Where converted markdown is written |

### Converter Backends

| Backend | Cost | Description |
|---------|------|-------------|
| `datalab` | Paid (per-page) | IBM Datalab API. Requires `DATALAB_API_KEY` in `.env`. Strongest PDF conversion. |
| `marker` | Free | Open-source marker-pdf library. Good quality, runs locally. |
| `docling` | Free | IBM Docling library. Strong table extraction. |
| `null` | Free | No conversion. Use when starting with markdown files already in the archive. |

### Deterministic or LLM?

Deterministic conversion. No LLM involved. For `datalab`, an external API is called but it is a document conversion API, not an LLM.

### Dry-Run Behavior

In dry-run mode, the scanner's estimate of conversion costs is reported but no files are actually converted. The estimate is based on file count, average pages per document, and per-page pricing (for datalab).

### Common Failure Modes

| Problem | Cause | Recovery |
|---------|-------|----------|
| No convertible files found | Archive contains only unsupported formats or is empty | Verify source directory; check file extensions |
| Conversion failures | Corrupted PDFs, password-protected files, oversized files | Check `failed_files` list in output; try a different converter |
| Missing API key | Datalab converter requires `DATALAB_API_KEY` | Set the key in `.env` or switch to `marker`/`docling` |
| Converter not installed | `marker` or `docling` require pip packages | Run `pip install marker-pdf` or `pip install docling` |

### CLI

Conversion runs as part of the pipeline; there is no standalone `folio convert` command. To convert a single file, use:

```bash
folio ingest --source grant.pdf --funder TAC --year 2024
```

---

## Stage 3: clean

### Purpose

Deterministic markdown cleanup. Strips artifacts introduced by PDF/DOCX conversion, normalizes whitespace, removes form interface elements, and fixes common text corruption. Prepares content for classification and LLM rewriting.

### Input

- `paths.raw_md` (default: `.folio/raw_md/`) — markdown files from the convert stage

### Output

- `paths.clean_md` (default: `.folio/clean_md/`) — cleaned `.md` files with the same filenames

### What Gets Cleaned

The cleaner performs these operations in order:

1. **Strip base64 images** — replaces inline base64 image data with `[IMAGE]` placeholder
2. **Remove image placeholders** — strips `<!-- image -->` comments and standalone `[IMAGE]` lines
3. **Normalize unicode** — replaces non-breaking spaces, zero-width characters, tabs; normalizes line endings; collapses multiple blank lines
4. **Remove form chrome headings** — strips heading lines matching configurable patterns like "Writing tip", "Upload PDF", "FOR OFFICE USE ONLY"
5. **Remove form field labels** — strips empty form field labels and their corresponding values (e.g., "Organization:", "Address:", "Email:")
6. **Fix text corruption** — rejoins split words (spli t wor ds), removes orphan single-character lines, decodes HTML numeric entities (`&#124;`, `&#8211;`)
7. **Remove bare digit lines** — drops standalone page-number-like lines
8. **Promote bold text to headings** — converts `**Section Title**` lines to `### Section Title`
9. **Normalize ALL-CAPS headings** — converts SHOUTING headings to Title Case
10. **Extract parenthetical from headings** — pulls `(max 500 words)` notes from headings into italic text
11. **Split question-answer lines** — detects `Question? Answer text` and splits into heading + paragraph
12. **Strip form widgets** — removes checkbox markers `[ ]`, `[x]`, unicode checkboxes

### Key Configuration

| Config option | Location | Effect |
|---------------|----------|--------|
| `classification.form_chrome` | `folio.yaml` > `classification` | Regex patterns for form chrome headings to remove |
| `classification.corruption` | `folio.yaml` > `classification` | Toggles for split_words, single_char_lines, html_entities fixes |

### Deterministic or LLM?

Fully deterministic. No API calls, no LLM. All transformations are regex-based rule applications. Runs in milliseconds per file.

### Dry-Run Behavior

Reports the number of files that would be cleaned based on the count of `.md` files in `paths.raw_md`. No files are written.

### Common Failure Modes

| Problem | Cause | Recovery |
|---------|-------|----------|
| `raw_md` directory not found | Convert stage didn't run or failed | Run convert stage first |
| No `.md` files found | Convert produced no output | Check convert stage for failures |
| Over-aggressive cleaning | Form chrome patterns match real content | Adjust `classification.form_chrome` patterns in `folio.yaml` |
| Under-cleaning | Custom form patterns not configured | Add org-specific form patterns to `classification.form_chrome` |

### CLI

```bash
folio clean --source .folio/raw_md/ --dest .folio/clean_md/
folio clean --file .folio/raw_md/grant.md        # Clean a single file
folio clean --file input.md --dest output.md      # Single file with custom output path
```

---

## Stage 4: canonicalize

### Purpose

Detects drafts, resolves submission versions, and deduplicates near-duplicate files. Ensures the clean directory contains only the authoritative (canonical) version of each document. Non-canonical files are moved to a `.non_canonical` subdirectory rather than deleted.

### Input

- `paths.clean_md` (default: `.folio/clean_md/`) — cleaned markdown files

### Output

- `paths.clean_md` — canonical files remain in place
- `paths.rewrite_md/.non_canonical/` — non-canonical files are moved here (drafts, superseded versions, duplicates)

The pipeline report records:
- `files` — total files analyzed
- `canonical` — count of canonical (kept) files
- `non_canonical` — count of non-canonical (moved) files

### How It Works

The canonicalizer groups files by application key (first N double-underscore-separated filename segments, default 2). Within each group it:

1. **Detects drafts** — flags files whose filenames or first 500 characters of content contain draft markers (e.g., `draft`, `work in progress`, `pending review`)
2. **Scores filenames** — assigns scores based on suffix patterns. `_final` = +100, `_submitted` = +90, `_draft` = -50, `_working` = -50, etc.
3. **Resolves submission versions** — identifies numbered submissions (`submission_1`, `2nd_sub`, etc.) and uses content similarity to determine if a higher-numbered submission supersedes a lower one
4. **Deduplicates** — finds near-duplicate pairs using name similarity (Jaccard) + content similarity (SequenceMatcher), keeps the highest-scored version
5. **Optional LLM pass** — resolves ambiguous cases where content similarity is borderline (0.25-0.55). Requires `use_llm=True`.

### Key Configuration

All canonicalizer behavior is driven by `DEFAULT_CANONICALIZE_CONFIG` in `canonicalizer.py`. These can be overridden per-org:

| Config option | Default | Effect |
|---------------|---------|--------|
| `group_segments` | 2 | Number of `__`-separated filename segments for grouping |
| `content_match_threshold` | 0.45 | Minimum similarity for a higher submission to supersede a lower one |
| `dedup_content_threshold` | 0.70 | Minimum content similarity to consider two files duplicates |
| `dedup_name_threshold` | 0.25 | Minimum name similarity to compare content |
| `min_content_length` | 800 | Minimum chars for a submission to be considered authoritative |
| `version_suffixes` | (see source) | Suffix patterns and their scores |
| `draft_suffixes` | (see source) | Suffix patterns that decrease canonicity score |
| `exclude_patterns` | (see source) | Filename patterns that are always non-canonical |

### Deterministic or LLM?

Primarily deterministic (filename scoring, content similarity, regex patterns). The optional LLM pass for ambiguous cases is disabled by default in the pipeline (`use_llm=False`).

### Dry-Run Behavior

Reports estimated file counts but does not analyze file content or move any files.

### Common Failure Modes

| Problem | Cause | Recovery |
|---------|-------|----------|
| Too many files marked non-canonical | Content match thresholds too strict; corrupted files draft-flagged | Adjust `content_match_threshold` or `min_content_length`; check for actual corruption |
| Drafts not detected | Org uses non-standard draft markers | Add markers to `draft_suffixes` and `exclude_patterns` |
| All versions kept | Files don't use submission numbering convention | Rename files to include `submission_N` segments, or adjust canonicalizer config |
| Wrong version chosen as canonical | Scoring rules don't match org's naming conventions | Adjust `version_suffixes` scores in config |

### CLI

```bash
folio canonicalize --source .folio/clean_md/
folio canonicalize --source .folio/clean_md/ --archive-dir ./archived/
folio canonicalize --source .folio/clean_md/ --dry-run
folio canonicalize --source .folio/clean_md/ --use-llm    # Enable LLM for ambiguous cases
```

---

## Stage 5: classify

### Purpose

Analyzes each cleaned markdown file for content quality, assigns a processing tier (`full`, `light`, `minimal`, or `skip`), and evaluates skip rules. The tier determines how much LLM processing the file receives in the rewrite stage.

### Input

- `paths.clean_md` (default: `.folio/clean_md/`) — cleaned and canonicalized markdown files

### Output

A classification manifest (dict, written to `paths.rewrite_md/manifest.json` when run within the pipeline) containing:

- Per-file: status, tier, funder, doc_types, content_lines, corruption_score, form_chrome_count, draft_marker_count, and other quality metrics
- Summary: counts by tier, status, and funder

**Processing tiers:**

| Tier | Criteria | Rewrite Behavior |
|------|----------|------------------|
| `full` | 40+ content lines, good quality | Full LLM rewrite with heading taxonomy, content cleanup, frontmatter generation |
| `light` | 10-39 content lines | Light LLM cleanup, preserve structure, add metadata |
| `minimal` | Less than 10 content lines, or form-heavy | Metadata-only: add frontmatter, remove image placeholders, minor fixes |
| `skip` | Matches a skip rule (e.g., identified as draft) | Not processed by rewrite stage |

> **Note:** The line-count criteria above are a simplification. The actual `DEFAULT_CLASSIFY_CONFIG` uses multi-parameter thresholds including `form_chrome_count`, `draft_marker_count`, `duplicate_heading_count`, and `word_count_annotation_count`. Tiers are assigned by evaluating these thresholds via configurable `tier_rules` (see Condition Types below), not by raw line count alone.

### How Classification Works

For each file, the classifier:

1. **Detects funder** — matches the file path against configured funder abbreviations
2. **Detects document types** — matches filename segments against type patterns
3. **Analyzes content quality** — counts content lines, form chrome lines, draft markers, duplicate headings, word count annotations, corruption score
4. **Evaluates skip rules** — configurable conditions that mark files for skipping (e.g., "files with doc_type `draft`")
5. **Evaluates tier rules** — configurable conditions that assign processing tiers based on quality metrics

### Key Configuration

| Config option | Location | Effect |
|---------------|----------|--------|
| `funders` | `folio.yaml` > `funders` | Funder abbreviations to detect |
| `doc_types` | `folio.yaml` > `doc_types` | Valid document types and their detection patterns |
| `classification.form_chrome` | `folio.yaml` > `classification` | Regex patterns counted as form chrome |
| `classification.draft_markers` | `folio.yaml` > `classification` | Regex patterns counted as draft markers |
| `classification.skip_rules` | `folio.yaml` > `classification` | Rules for skipping files |
| `classification.tier_rules` | `folio.yaml` > `classification` | Rules for assigning tiers |
| `classification.thresholds` | `folio.yaml` > `classification` | Numeric thresholds for tier boundaries |

### Condition Types for Rules

Skip rules and tier rules use a safe condition DSL. Available conditions:

**Simple conditions (each has `"type": "<name>"`):**
- `has_doc_type` with `value` — file has this document type label
- `has_any_type` with `values` (list) — file has any of these type labels
- `field_gt` with `field` + `value` — numeric field greater than `value` (e.g. `{"type": "field_gt", "field": "content_lines", "value": 40}`)
- `field_lt` with `field` + `value` — numeric field less than `value` (e.g. `{"type": "field_lt", "field": "corruption_score", "value": 0.5}`)
- `field_gte` / `field_lte` with `field` + `value` — greater-than-or-equal / less-than-or-equal
- `path_contains` with `values` (list) — file path contains any substring
- `filename_starts_with` with `value` — filename prefix match
- `has_headings` — file has markdown headings
- `has_tables` — file has markdown tables
- `not_` with `condition` — invert another condition
- `true` — always matches

**Compound rules (evaluated by `evaluate_rule`):**
- `{"conditions": [...], "match": "all"}` — all conditions must match (AND)
- `{"conditions": [...], "match": "any"}` — any condition must match (OR)

### Deterministic or LLM?

Fully deterministic. No API calls. All quality metrics are computed from file content using regex and counting. Rules are evaluated with a safe DSL interpreter (no Python `eval()`).

### Dry-Run Behavior

Reports the number of files that would be classified and the tier distribution estimate. No classification manifest is generated.

### Common Failure Modes

| Problem | Cause | Recovery |
|---------|-------|----------|
| All files in `minimal` tier | Content quality thresholds too high for org's documents | Adjust `thresholds` in `classification` config |
| No funder detected | Funders in filenames don't match configured abbreviations | Add abbreviation mappings to `funders` in `folio.yaml` |
| Files incorrectly skipped | Skip rules too broad | Tighten skip rule conditions; add exceptions |
| Files with wrong tier | Tier rules don't capture org's document patterns | Add custom tier rules with appropriate conditions |

### CLI

```bash
folio classify --source .folio/clean_md/
folio classify --file .folio/clean_md/grant.md      # Classify a single file
folio classify --source .folio/clean_md/ --json      # Output as JSON
folio classify --source .folio/clean_md/ --dry-run   # Preview classification
```

---

## Stage 6: rewrite

### Purpose

LLM re-authoring engine. Sends each file to an LLM with tier-specific prompts to produce clean, archival-quality markdown with YAML frontmatter containing structured metadata (funder, type, year, period, grant amount, priority).

This is the largest cost driver in the pipeline.

### Input

- `paths.clean_md` (default: `.folio/clean_md/`) — cleaned and classified markdown files
- The classification manifest for tier selection and metadata hints

### Output

- `paths.rewrite_md` (default: `./markdown/`) — rewritten `.md` files with YAML frontmatter

Each output file includes:
- YAML frontmatter with `funder`, `type`, `written`, `period`, `grant_amount`, `priority`, `errors` fields
- Cleaned markdown body with normalized headings, removed artifacts, preserved factual data
- `<!-- FIXME: description -->` comments where corruption couldn't be recovered
- If a file has no archival value, `errors: -1` in frontmatter

### Tier-Specific Behavior

| Tier | Prompt Strategy | Typical Time/File | Thinking |
|------|----------------|-------------------|----------|
| `full` | Full re-authoring with heading taxonomy, content cleanup, frontmatter generation | ~55 sec | Enabled (high effort) |
| `light` | Light cleanup, preserve structure, add metadata | ~50 sec | Enabled (low effort) |
| `minimal` | Metadata-only: add frontmatter, remove image placeholders, minor fixes | ~20 sec | Disabled |
| `skip` | Not processed | — | — |

**Language detection** — documents are language-detected (via frequency analysis) before heading taxonomy substitution. French and mixed-language documents skip English heading taxonomy normalization. Detected language is recorded in the `language` frontmatter field.

**Undersized files** — files shorter than `min_content_chars` (default 2000 chars) are processed locally without an API call. Only frontmatter metadata is added.

### Key Configuration

| Config option | Location | Effect |
|---------------|----------|--------|
| `llm.provider` | `folio.yaml` > `llm` | LLM provider (deepseek, openai) |
| `llm.models.fast` | `folio.yaml` > `llm` > `models` | Model used for rewrite (default: `deepseek-v4-flash`) |
| `llm.models.quality` | `folio.yaml` > `llm` > `models` | Model used for prioritize and quality-sensitive tasks |
| `llm.pricing` | `folio.yaml` > `llm` | Token pricing for cost calculation |
| `llm.base_url` | `folio.yaml` > `llm` | API endpoint URL |
| `processing.max_workers` | `folio.yaml` > `processing` | Concurrent API workers (default 10) |
| `processing.requests_per_second` | `folio.yaml` > `processing` | Rate limit (default 5) |
| `processing.max_retries` | `folio.yaml` > `processing` | Max retry attempts (default 3) |
| `classification.thresholds` | `folio.yaml` > `classification` | Tier boundaries that affect which prompt is used |
| `headings` section | `folio.yaml` or `headings.yaml` | Per-funder canonical heading taxonomy injected into full-tier prompts |

### Deterministic or LLM?

Heavy LLM usage. Every file above the minimum size threshold is sent to the LLM. Files below the threshold get deterministic metadata-only processing. The rewriter uses `LLMProvider.complete_with_usage()` for token tracking, returning both the response text and usage metadata (prompt tokens, completion tokens, cost). Supports concurrent processing with configurable rate limiting and retry logic with exponential backoff.

### Dry-Run Behavior

Prints a detailed table showing per-tier file counts, estimated token usage, estimated cost, and estimated processing time (both serial and with configured worker count). No API calls are made. The table looks like:

```
  Tier         Files      KB    In $    Out $  Total $  Serial  //10
  full            42   4200K $0.1764 $1.0560 $1.2324     38m    4m
  light           15    900K $0.0378 $0.2263 $0.2641     12m    1m
  minimal          8    400K $0.0168 $0.0800 $0.0968      3m    0m
  TOTAL           65   5500K $0.2310 $1.3623 $1.5933     53m    5m
```

### Common Failure Modes

| Problem | Cause | Recovery |
|---------|-------|----------|
| API key not set | Missing `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` in `.env` | Set the key in `.env` |
| Rate limit exceeded | Too many concurrent requests | Reduce `processing.max_workers` or `processing.requests_per_second` |
| Files return empty body | LLM produced no body content (corrupted input) | File will have `errors: -1` in frontmatter; review and reprocess |
| Corrupted output | LLM response truncated or malformed | Retry: the stage has built-in retry logic (3 attempts default) |
| Cost higher than expected | More/larger files than estimated, or pricing mismatch | Update `llm.pricing` in `folio.yaml` to match current rates |
| Wrong model used | `llm.models.fast` not set | Set `llm.models.fast` in `folio.yaml` (defaults to `deepseek-v4-flash`) |

### CLI

```bash
folio rewrite --source .folio/clean_md/                     # Rewrite all files
folio rewrite --source .folio/clean_md/ --tier full          # Force full tier for all
folio rewrite --source .folio/clean_md/ --limit 10            # Process only 10 files
folio rewrite --file .folio/clean_md/grant.md                # Rewrite a single file
folio rewrite --source .folio/clean_md/ --dry-run             # Estimate cost only
folio rewrite --source .folio/clean_md/ --no-resume           # Force re-process all
```

---

## Stage 7: prioritize

### Purpose

Scores each rewritten file with an archival priority (1-3) by sending year-grouped file digests to an LLM for contextual comparison. The LLM evaluates completeness, uniqueness, and archival value relative to peer documents.

### Input

- `paths.rewrite_md` (default: `./markdown/`) — rewritten markdown files with frontmatter

### Output

- The same files in `paths.rewrite_md`, updated with `priority` field in their YAML frontmatter
- A progress manifest at `paths.rewrite_md/prioritize_progress.json`

**Priority levels:**

| Priority | Label | Description |
|----------|-------|-------------|
| 1 | Essential | Primary, most complete version. Final submitted applications, approved budgets, complete reports. |
| 2 | Supplemental | Useful reference data. Supporting materials, staff/board lists, notification letters, budget breakdowns. |
| 3 | Redundant / Low-value | Information duplicated in higher-priority files. Drafts, internal notes, generic boilerplate. |

### How It Works

1. **Groups files by year** — reads the `written` field from frontmatter, groups files from the same year for contextual comparison
2. **Splits large groups** — groups exceeding `max_files_per_batch` (default 60) are split into roughly equal batches
3. **Builds digests** — for each file, extracts frontmatter + first N characters of body (default 6000 chars)
4. **Sends to LLM** — each group is sent with a rubric prompt asking the LLM to compare files and assign priorities
5. **Writes back** — updates the `priority` field in each file's frontmatter

Files without frontmatter or without a `written` year are placed in an unknown-year group and evaluated together.

### Key Configuration

| Config option | Location | Effect |
|---------------|----------|--------|
| `processing.max_workers` | `folio.yaml` > `processing` | Concurrent group processing (default 5) |
| `processing.requests_per_second` | `folio.yaml` > `processing` | Rate limit (default 3) |
| `grouping.field` | `folio.yaml` > `prioritize` | Frontmatter field used for grouping (default: `written`) |
| `grouping.by_funder` | `folio.yaml` > `prioritize` | If true, also split groups by funder |
| `llm.models.quality` | `folio.yaml` > `llm` > `models` | Model used for prioritization (deeper reasoning via quality model) |
| `digest_max_chars` | Default 6000 | Max characters per file digest sent to LLM |
| `max_files_per_batch` | Default 60 | Maximum files in a single LLM call |

### Deterministic or LLM?

LLM-based. Each year group is sent as a single LLM call. Groups are processed concurrently. The rubric and system prompt are configurable.

### Dry-Run Behavior

Prints a table showing each year group with file count, estimated character count, estimated input tokens, and estimated cost. Lists each file with any existing priority from frontmatter. No API calls are made.

### Common Failure Modes

| Problem | Cause | Recovery |
|---------|-------|----------|
| No files have year data | Files lack frontmatter or `written` field | Ensure rewrite stage completed; check frontmatter validity |
| LLM response unparseable | Malformed JSON from LLM | The stage logs errors per group; retry automatically (3 attempts default) |
| Priority not assigned to all files | LLM missed some filenames in batch | Files without priority keep existing value; re-run for missing groups |
| Groups too large | Single year has more than `max_files_per_batch` files | Groups are auto-split into batches; adjust `max_files_per_batch` if needed |

### CLI

```bash
folio prioritize --source ./markdown/
folio prioritize --source ./markdown/ --year 2024        # Prioritize a specific year
folio prioritize --source ./markdown/ --limit 5            # Process only 5 groups
folio prioritize --source ./markdown/ --dry-run            # Preview groups and cost
folio prioritize --source ./markdown/ --no-resume          # Force re-process all groups
```

---

## Stage 8: wiki

### Purpose

Compiles the rewritten, prioritized markdown files into a searchable wiki knowledge base using a configurable wiki backend. The wiki becomes the queryable interface that AI agents use to answer questions and write grants.

### Input

- `paths.rewrite_md` (default: `./markdown/`) — rewritten and prioritized markdown files

### Output

- `paths.wiki_project` (default: `./wiki/`) — a compiled wiki project

### Wiki Backends

| Backend | Description |
|---------|-------------|
| `sage_wiki` | Sage-wiki searchable knowledge base. Requires `sage-wiki` binary on PATH. Uses a configurable "pack" (default: `arts-org`). |
| `null` | No wiki compilation. The pipeline ends with markdown output only. |

### How It Works

1. Initializes the wiki project directory
2. Adds all markdown files from the rewrite directory
3. Compiles the wiki (generates search indexes, cross-references, etc.)

### Key Configuration

| Config option | Location | Effect |
|---------------|----------|--------|
| `wiki.type` | `folio.yaml` > `wiki` | Which backend: `sage_wiki` or `null` |
| `wiki.sage_wiki_pack` | `folio.yaml` > `wiki` | Pack name for sage-wiki (default: `arts-org`) |
| `paths.wiki_project` | `folio.yaml` > `paths` | Where the wiki project is created |
| `paths.rewrite_md` | `folio.yaml` > `paths` | Source directory for documents added to wiki |

### Deterministic or LLM?

Depends on the backend. `sage_wiki` may use LLM for compilation. `null` backend does nothing.

### Dry-Run Behavior

Reports estimated cost and file count. No wiki project is created.

### Common Failure Modes

| Problem | Cause | Recovery |
|---------|-------|----------|
| Wiki backend is null | `wiki.type` is set to `null` in config | Set `wiki.type: sage_wiki` if you want wiki output |
| sage-wiki not installed | Binary not on PATH | Install sage-wiki; or set `wiki.type: "null"` for markdown-only mode |
| Wiki init fails | Permission issues, missing directories | Verify `paths.wiki_project` directory is writable |
| Wiki compilation fails | Corrupted markdown files, malformed frontmatter | Check the files in `paths.rewrite_md` for issues |

### CLI

Wiki compilation runs as part of the pipeline. There is no standalone `folio wiki` command. To audit an existing wiki:

```bash
folio audit --wiki-dir ./wiki/
```

---

## Pipeline Orchestration

### Running the Full Pipeline

```bash
folio pipeline
```

Runs all eight stages in sequence. Each stage's output is checkpointed to `paths.rewrite_md/manifest.json`. If a stage fails, the pipeline halts. On re-run with `--resume` (the default), completed stages are skipped.

### Running Specific Stages

```bash
folio pipeline --stages scan,convert,clean
folio pipeline --stages rewrite,prioritize
folio pipeline --stages classify,rewrite --no-resume
```

Stages must be specified in pipeline order (they will be sorted automatically). The `--stages` flag accepts a comma-separated list of stage names.

### Dry-Run Estimation

```bash
folio pipeline --dry-run
folio pipeline --dry-run --json                    # Machine-readable cost estimate
folio pipeline --dry-run --stages classify,rewrite  # Estimate specific stages
```

Does not modify any files or make any API calls. Reports:
- Per-stage file counts and cost estimates
- Total estimated cost
- Total estimated time

Always run `--dry-run` before your first pipeline run to understand costs and verify configuration.

### JSON Output

```bash
folio pipeline --json | jq .
folio pipeline --dry-run --json | jq .total_cost_usd
folio pipeline --stages rewrite --json | jq '.stages.rewrite'
```

Every stage and the overall pipeline supports `--json` for structured output suitable for piping to other tools or analysis scripts.

### Checkpoint and Resume

The pipeline saves a manifest to `paths.rewrite_md/manifest.json` after each stage completes. This manifest tracks:

- Per-file status, tier, funder, document types
- Per-stage completion status and timing
- Cumulative cost tracking
- Token usage per file (rewrite and prioritize stages)

**To resume after a failure:**

```bash
folio pipeline --resume       # Default behavior — skips completed stages
folio pipeline --no-resume    # Force re-run all stages from scratch
folio pipeline --stages rewrite,prioritize,wiki --resume   # Resume from a specific point
```

**To inspect the manifest:**

```bash
cat markdown/manifest.json | jq .stages
cat markdown/manifest.json | jq '.stages.classify.status'
cat markdown/manifest.json | jq '.stages.rewrite.files // empty'
```

---

## Recovery Procedures

### If a Stage Fails

1. **Read the error message** — the pipeline prints the stage name and error
2. **Inspect the manifest** — `cat markdown/manifest.json | jq '.stages.<stage_name>'`
3. **Fix the underlying issue** — see the common failure modes table for that stage
4. **Re-run the pipeline** — `folio pipeline --resume` will skip already-completed stages and re-run from the failed stage

### Re-Running a Specific Stage

To force re-processing of a stage that already completed:

```bash
folio pipeline --stages rewrite --no-resume
```

This ignores the manifest checkpoint for the specified stages and re-runs them completely. Other stages are not affected.

### Inspecting Checkpoint State

The manifest is a JSON file. Use `jq` to inspect:

```bash
# See all stage statuses
cat markdown/manifest.json | jq '.stages | to_entries | map({stage: .key, status: .value.status})'

# See per-file rewrite status
cat markdown/manifest.json | jq '.stages.rewrite.files | to_entries | map({file: .key, status: .value.rewrite_status})'

# Count files by priority
cat markdown/manifest.json | jq '[.stages.prioritize.completed_groups | to_entries[].value.priorities | to_entries[] | .value] | group_by(.) | map({priority: .[0], count: length})'

# Estimate remaining cost for incomplete stages
cat markdown/manifest.json | jq '[.stages | to_entries[] | select(.value.status != "ok" and .value.status != "complete") | .value.cost_usd // 0] | add'
```

### Recovering from Partial Runs

If the pipeline was interrupted (e.g., process killed, network failure):

1. Some files in the output directory may be partial or corrupt
2. The manifest tracks which files were successfully processed
3. Re-running with `--resume` will skip completed files within a stage (for rewrite and prioritize)
4. For stages that process directories in bulk (clean, classify), re-running re-processes the entire directory — this is safe as the operations are idempotent (same input produces same output)

### Manual File Reprocessing

To re-process a single file through all stages:

```bash
folio ingest --source problem_file.pdf --funder TAC --year 2024
folio clean --file .folio/raw_md/problem_file.md --dest .folio/clean_md/
folio classify --file .folio/clean_md/problem_file.md
folio rewrite --file .folio/clean_md/problem_file.md
folio prioritize --source ./markdown/ --year 2024
```

---

## Individual Stage CLIs

While the pipeline orchestrates all stages, each stage can also be run independently:

| Command | Description |
|---------|-------------|
| `folio scan` | Scan archive, detect funders/years/types, estimate costs |
| `folio clean` | Deterministic markdown cleanup (single file or directory) |
| `folio canonicalize` | Version detection and deduplication |
| `folio classify` | Quality scoring and tier assignment (single file or directory) |
| `folio rewrite` | LLM re-authoring (single file or directory) |
| `folio prioritize` | Archival priority scoring by year groups |
| `folio ingest` | One-off document ingestion (PDF/DOCX/XLSX to markdown pipeline) |
| `folio audit` | Wiki quality audit (dead links, thin articles) |

All commands support `--help` for detailed usage, `--dry-run` for preview, and `--json` for structured output.

**Note:** The `convert` stage has no standalone CLI. Use `folio ingest` for single-file conversion or run it within `folio pipeline`.
