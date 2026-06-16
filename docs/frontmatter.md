# Frontmatter Reference

## What is frontmatter

Frontmatter is a YAML block between `---` delimiters at the top of a markdown file. It carries structured metadata about the document -- funder, year, type, priority, and other pipeline-managed fields. Every markdown file produced by the folio pipeline begins with a frontmatter block.

```yaml
---
funder: "TAC"
type: "application"
written: 2024
period: "2024-2025"
priority: 1
errors: 0
---
```

---

## Standard fields

### YAML frontmatter fields

These fields appear inside the `---` block of markdown files.

| Field | Key | Python type | Added by | Optional | Example |
|-------|-----|-------------|----------|----------|---------|
| Funder abbreviation | `funder` | `str` | Scan (filename), Ingest, Rewrite (LLM) | No | `"TAC"` |
| Document type(s) | `type` | `str` (comma-separated) | Scan (filename), Ingest, Rewrite (LLM) | No | `"application, report"` |
| Year written/submitted | `written` | `int` | Scan (filename), Ingest, Rewrite (LLM) | No | `2024` |
| Grant period | `period` | `str` | Ingest, Rewrite (LLM) | Yes | `"2024–2025"` |
| Period start year | `period_start` | `int` | Rewrite (LLM) | Yes | `2024` |
| Period end year | `period_end` | `int` | Rewrite (LLM) | Yes | `2025` |
| Grant dollar amount | `grant_amount` | `str` | Rewrite (LLM) | Yes | `"$51,000"` |
| Document language | `language` | `str` — `"en"`, `"fr"`, `"mixed"` | Rewrite | Yes | `"en"` |
| Archival priority | `priority` | `int` (1, 2, or 3) | Ingest (default=1), Prioritize (LLM) | No | `2` |
| Error/corruption count | `errors` | `int` | Rewrite | No | `0` |

**Field aliases** (normalized to canonical names by `sanitize_frontmatter`):

| Alias | Canonical |
|-------|-----------|
| `year` | `written` |
| `year_written` | `written` |
| `status` | `type` |
| `doc_type` | `type` |
| `document_type` | `type` |

**Type value normalizations** (non-standard values mapped to canonical):

| Written | Canonical |
|---------|-----------|
| `support material`, `support materials` | `support_material` |
| `activity list`, `activity lists` | `activity_list` |
| `staff board` | `staff_board` |
| `meeting notes` | `meeting_notes` |
| `financial_form` | `budget` |
| `incorporation`, `letter of agreement` | `agreement` |
| `acceptance`, `approval`, `results`, `result` | `notification` |
| `email correspondence` | `email` |

**Priority rubric** (from config):

| Priority | Label | Meaning |
|----------|-------|---------|
| `1` | Essential | Primary, most complete version. Final submitted applications, approved budgets, complete reports. Go-to source for grant writing. |
| `2` | Supplemental | Useful reference data that augments priority-1. Supporting materials, staff/board lists, notification letters. |
| `3` | Redundant/Low-value | Information substantially duplicated in higher-priority files. Drafts, internal prep notes, generic boilerplate. |

**Special field values:**

- `errors: -1` means the document has no archival value and should not be included in the wiki. Set by the LLM during rewrite when a document is a blank form, navigation-only page, or entirely corrupted beyond recovery.
- `errors: 0` means clean -- no FIXME flags.
- `errors: >0` -- count of `<!-- FIXME: ... -->` flags in the document body, indicating specific irrecoverable corruption.

### Pipeline manifest fields

These fields are tracked in the pipeline manifest JSON (`manifest.json`) for checkpoint/resume and inter-stage communication. They are **not** written to YAML frontmatter.

| Field | Python type | Added by | Optional | Example |
|-------|-------------|----------|----------|---------|
| `tier` | `ProcessingTier` (`"full"`, `"light"`, `"minimal"`, `"skip"`) | Classify | No | `"full"` |
| `status` | `FileStatus` (`"ok"`, `"skipped_draft"`, `"error_llm"`, etc.) | Classify, Rewrite | No | `"ok"` |
| `corruption_score` | `float` (0.0-1.0) | Classify | No | `0.03` |
| `content_lines` | `int` | Classify | No | `342` |
| `form_chrome_count` | `int` | Classify | No | `12` |
| `draft_marker_count` | `int` | Classify | No | `2` |
| `duplicate_heading_count` | `int` | Classify | No | `0` |
| `word_count_annotation_count` | `int` | Classify | No | `5` |
| `rewrite_input_tokens` | `int` | Rewrite | No | `3245` |
| `rewrite_output_tokens` | `int` | Rewrite | No | `2871` |
| `rewrite_cost_usd` | `float` | Rewrite | No | `0.0013` |
| `rewrite_status` | `str` | Rewrite | No | `"success"` |
| `funder` | `str` or `None` | Classify (detected from path) | Yes | `"TAC"` |
| `doc_types` | `list[str]` | Classify (detected from path) | No | `["application"]` |
| `year_written` | `int` or `None` | Classify (from YAML frontmatter) | Yes | `2024` |
| `size_kb` | `float` | Classify | No | `24.5` |
| `reason` | `str` | Classify, Canonicalize | No | `"2 draft markers; 12 form chrome lines"` |

---

## Frontmatter API

The frontmatter API is frozen -- do not change these function signatures. All functions live in `src/folio/core/frontmatter.py`.

### `parse_frontmatter(text: str) -> tuple[dict | None, str]`

Extract YAML frontmatter and body from a markdown string.

- **Input**: Raw markdown text, possibly with a `---` delimited frontmatter block.
- **Output**: `(parsed_dict_or_None, body_text)`. If no frontmatter or invalid YAML, the dict is `None` and the full text is returned as body.
- **Example**: `parse_frontmatter('---\nwritten: 2024\nfunder: OAC\n---\nBody\n')` returns `({'written': 2024, 'funder': 'OAC'}, 'Body')`.

### `dict_to_frontmatter(**fields) -> str`

Serialize key-value pairs to a YAML frontmatter block.

- **Input**: Keyword arguments of field names and values.
- **Output**: String with `---` delimiters. String values are quoted. List values are joined with commas and quoted. Int/float values are unquoted. `None` and empty strings are skipped.
- **Example**: `dict_to_frontmatter(funder="OAC", type=["proposal", "report"], written=2024)` returns `'---\nfunder: "OAC"\ntype: "proposal, report"\nwritten: 2024\n---'`.

### `sanitize_frontmatter(text: str) -> str`

Clean up frontmatter from various input formats (LLM output).

- **Input**: Raw text that may contain code-fenced YAML (` ```yaml ... ``` `), bare YAML, or standard `---` delimited frontmatter.
- **Output**: Clean markdown string with standardized `---` delimited frontmatter. Normalizes field name aliases (`year_written` -> `written`, `doc_type` -> `type`, etc.), normalizes type values (`support material` -> `support_material`), normalizes period values to `YYYY` or `YYYY-YYYY` format, and removes empty-valued fields.
- **Example**: `sanitize_frontmatter('```yaml\n---\nyear_written: 2024\ntype: support material\n---\n```\n# Body')` produces clean `---\nwritten: 2024\ntype: "support_material"\n---\n\n# Body`.

### `update_frontmatter(content: str, **fields) -> str`

Update or add fields in existing frontmatter.

- **Input**: Markdown text and keyword arguments of field updates.
- **Output**: Markdown text with updated frontmatter. If no frontmatter exists, one is created.
- **Example**: `update_frontmatter(doc, priority=2)` adds or overwrites the `priority` field.

### `apply_frontmatter(text: str, frontmatter: str) -> str`

Strip any existing frontmatter and insert a canonical version.

- **Input**: Markdown text and a frontmatter string (as produced by `dict_to_frontmatter`).
- **Output**: Markdown text with the new frontmatter prepended, existing frontmatter removed.
- **Use case**: When the LLM fails to produce valid frontmatter, insert deterministic frontmatter from filename-based metadata.

### `strip_existing_frontmatter(text: str) -> str`

Remove any frontmatter from a markdown string.

- **Input**: Markdown text.
- **Output**: Markdown text with all frontmatter stripped (handles both `---` delimited and code-fenced ` ```yaml ` frontmatter).
- **Example**: `strip_existing_frontmatter('---\nwritten: 2024\n---\n\n# Body\n')` returns `'# Body'`.

### `get_file_year(fm: dict | None, field: str = 'written') -> int | None`

Extract a year from a frontmatter dict.

- **Input**: `fm` dict (from `parse_frontmatter`) and optional field name (default: `"written"`).
- **Output**: Year as `int`, or `None`. Falls back through `written`, `period`, `period_start` fields.
- **Example**: `get_file_year({'written': 2024, 'period': '2024-2025'})` returns `2024`.

---

## Frontmatter lifecycle

Fields are added at specific pipeline stages in a defined order.

### Stage 1: Scan

Reads filenames only. Detects funder abbreviation and year from the file path. Does not write frontmatter -- produces a scan report.

**Detected**: `funder` (from filename path match against config.funders), `written` (first 4-digit year in filename).

### Stage 2: Convert

Converts PDF/DOCX/XLSX files to markdown via the configured converter. No frontmatter is added.

**Tracked in manifest**: `source_file` (original filename), `converter` (converter name, e.g. `"datalab"`).

### Stage 3: Clean

Deterministic markdown cleanup (strip base64 images, normalize whitespace, fix split words, decode HTML entities, remove form chrome). No frontmatter changes.

### Stage 4: Canonicalize

Version detection and deduplication. Identifies canonical vs. non-canonical (draft, superseded, duplicate) files. Moves non-canonical files to a `.non_canonical` archive directory. Does not modify frontmatter.

**Manifest fields**: `canonical` (boolean), `version_of` (implied by grouping).

### Stage 5: Classify

Content analysis and tier assignment. Scores file quality (corruption, form chrome, draft markers, content density) and assigns a processing tier. Parses existing frontmatter to extract years.

**Frontmatter written**: Reads existing `written`, `period_start`, `period_end` from frontmatter.
**Manifest fields added**: `tier`, `status`, `corruption_score`, `content_lines`, `form_chrome_count`, `draft_marker_count`, `duplicate_heading_count`, `word_count_annotation_count`, `doc_types`, `funder`, `year_written`, `size_kb`, `reason`.

### Stage 6: Rewrite

LLM re-authoring. Files are sent to an LLM with tier-specific prompts. The LLM produces complete markdown with YAML frontmatter.

**Frontmatter written** (by LLM, sanitized on return):
- `funder` -- confirmed/corrected from document body
- `type` -- confirmed/corrected from document body
- `written` -- confirmed/corrected from document body
- `period` -- extracted from document body (e.g. `"2025-2027"`)
- `grant_amount` -- extracted from document body if mentioned
- `language` -- added by rewrite stage for French/mixed documents (detected via frequency analysis)
- `errors` -- count of `<!-- FIXME: -->` flags (added post-LLM by code)

**Manifest fields added**: `rewrite_input_tokens`, `rewrite_output_tokens`, `rewrite_cost_usd`, `rewrite_status`.

### Stage 7: Prioritize

LLM priority scoring. Files are grouped by year and sent to an LLM for comparative evaluation against the priority rubric. Each file gets a priority score of 1-3.

**Frontmatter written**: `priority` (added via `update_frontmatter`).

### Stage 8: Wiki

Wiki compilation. Frontmatter in files is **read** to populate wiki metadata (funder, type, dates) but no new frontmatter is added.

---

## Complete example

```yaml
---
funder: "TAC"
type: "application"
written: 2024
period: "2024-2025"
grant_amount: "$51,000"
priority: 1
errors: 0
---
```

With the full markdown body:

```markdown
---
funder: "TAC"
type: "application"
written: 2024
period: "2024-2025"
grant_amount: "$51,000"
priority: 1
errors: 0
---

# 2024 Operating Grant Application

## Organization Information

Organization name: Example Arts Collective
Incorporation status: Incorporated since 2010
Charitable number: 12345 6789 RR0001

## Project Description

Example Arts Collective seeks operating funding to support its
2024-2025 programming season, including exhibitions, workshops,
and community outreach programs.

## Budget Summary

Total project budget: $120,000
Amount requested: $51,000

[... additional sections ...]
```
