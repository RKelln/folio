# File Naming Convention

## Overview

Every markdown file in the folio pipeline follows a standard naming convention using double-underscore (`__`) separators between logical segments. This convention is the foundation for automated funder detection, year extraction, document type identification, version resolution, draft detection, and deduplication.

```
FUNDER__Year_Description__Type.md
```

The pipeline both **produces** files following this convention (via `folio ingest`) and **parses** existing files using it (in scan, canonicalize, and classify stages).

---

## Segment Structure

A folio filename consists of three core segments separated by `__` (two underscores):

| Position | Segment | Required | Example |
|----------|---------|----------|---------|
| 1 | Funder abbreviation | Yes | `OAC`, `TAC`, `CCA` |
| 2 | Year and optional description | Yes | `2024`, `2025_Project_Grant_Operating` |
| 3 | Document type | Yes | `application`, `report`, `budget` |

The `.md` extension follows the third segment.

### Segment 1: Funder abbreviation

A short code identifying the funding body. This must match a key in the `funders` dictionary in `folio.yaml`. Matching is case-insensitive and uses longest-match-first.

```yaml
# folio.yaml
funders:
  OAC: "Ontario Arts Council"
  TAC: "Toronto Arts Council"
  CCA: "Canada Council for the Arts"
```

### Segment 2: Year and description

The year component is a 4-digit year (2000–2099). An optional description may follow, joined to the year with a single underscore (`_`). Spaces in the description are replaced with underscores.

```
2024                                    # year only
2025_Project_Grant_Operating            # year + description
2024-2026                               # period (multi-year grant)
```

When a period is provided instead of a single year (e.g., `2024-2026`), it replaces the year in the filename.

### Segment 3: Document type

A canonical document type tag from the `doc_types` list in `folio.yaml`. Multiple types are joined with `_and_`.

```
application
report
budget
application_and_budget                 # multi-type file
```

**Default canonical types:**

| Type | Description |
|------|-------------|
| `application` | Grant application or submission |
| `report` | Final report, mid-cycle report, annual update |
| `budget` | Budget, financial statement, CADAC, P+L |
| `notification` | Approval, acceptance, results, notice |
| `activity_list` | Activity list or activity report |
| `staff_board` | Staff list, board of directors, bios |
| `support_material` | Promotional material, press, supplementary docs |
| `agreement` | Letter of agreement, contract, declaration |
| `webpage` | Pre-scraped website page (ingested via `folio website`) |

---

## Examples

```
OAC__2024__application.md
OAC__2025__Project_Grant_Operating__application.md
CCA__2023__Research_and_Creation__report.md
TAC__2024-2026__Operating_Budget__budget.md
OAC__2024__application_and_budget.md
CCA__2025__Activity_Report__report.md
```

Files produced by `folio ingest` follow the same convention:

```bash
folio ingest --source grant.pdf --funder TAC --year 2024 --type application
# Produces: TAC__2024__application.md

folio ingest --source report.pdf --funder CCA --year 2025 \
    --description "Research and Creation" --type report
# Produces: CCA__2025_Research_and_Creation__report.md

folio ingest --source budget.xlsx --funder OAC --period 2024-2026 \
    --type budget
# Produces: OAC__2024-2026__budget.md
```

---

## How the Pipeline Parses Filenames

### Canonicalize stage (`canonicalizer.py`)

The canonicalizer is the primary consumer of filename structure. It uses `_parse_filename_segments()` to split the filename stem (without `.md`) by `__`:

```
>>> _parse_filename_segments('OAC__2024_Application__final.md')
['OAC', '2024_Application', 'final']
```

From these segments, the canonicalizer derives:

| Derived property | How | Example from `OAC__2024_Application__final.md` |
|------------------|-----|------|
| `app_key` | First `group_segments` (default 2) joined with `__` | `OAC__2024_Application` |
| `submission_number` | Remaining segments matched against `submission_segments` patterns | `None` (no submission marker) |
| `category` | Remaining segments matched against `category_segments` patterns | `final` |
| `doc_identity` | Non-submission remaining segments joined with `__` | `final` |
| `version_score` | Suffix patterns matched against the full stem | `+100` (`_final`) |
| `date_str` | ISO date embedded in stem (e.g., `2024-06-15`) | `None` |

**Grouping:** Files are grouped by `app_key` (first 2 segments by default). Files sharing `OAC__2024` are treated as the same grant application, even if they differ in document type:

```
OAC__2024__application.md   → group "OAC__2024"
OAC__2024__budget.md        → group "OAC__2024"
OAC__2024__report.md        → group "OAC__2024"
```

### Scan stage (`scanner.py`)

The scanner detects funder abbreviations and years via substring and regex matching against the full file path, not by parsing `__` segments:

- **Funder detection:** Longest-match search against `folio.yaml` `funders` keys (case-insensitive).
- **Year detection:** First 4-digit year in the range 2000–2099 via regex `(?<![0-9])(20\d{2})(?![0-9])`.
- **Type detection:** Regex patterns matched against the file path (spaces normalized from underscores).

### Classify stage (`classifier.py`)

The classifier also works with full file paths for funder and type detection:

- **Funder detection:** Longest-match search against `funders` keys in the path string (identical to scanner).
- **Type detection:** Underscores in the path are normalized to spaces before matching `doc_type` regex patterns. This means `staff_board` in a filename correctly matches a pattern for `staff board`.

---

## Draft and Version Suffixes

After the three core segments, additional suffixes can be appended to indicate version status. These are separated by underscores from the preceding segments and are matched against the filename stem (without `.md`).

### Version suffixes (increase canonicity score)

Suffixes that indicate a file is more final/authoritative. Higher scores win during deduplication.

| Suffix | Score | Example |
|--------|-------|---------|
| `_final` | +100 | `OAC__2024__application_final.md` |
| `_submitted` | +90 | `OAC__2024__application_submitted.md` |
| `_signed` | +85 | `TAC__2025__budget_signed.md` |
| `_v{N}` | +10 per version | `CCA__2025__report_v3.md` → +30 |
| `_updated` | +5 | `OAC__2024__staff_board_updated.md` |
| `_corrected` | +5 | `OAC__2024__budget_corrected.md` |

### Draft suffixes (decrease canonicity score)

Suffixes that indicate a file is a draft/working copy. Negative scores mark files as likely non-canonical.

| Suffix | Score | Example |
|--------|-------|---------|
| `_draft` | -50 | `OAC__2024__application_draft.md` |
| `_prep` | -50 | `OAC__2024__application_prep.md` |
| `_working` | -50 | `TAC__2025__budget_working.md` |
| `_todo` | -50 | `CCA__2025__report_todo.md` |
| `_notes` | -30 | `OAC__2024__meeting_notes.md` |
| `_copy` | -30 | `OAC__2024__application_copy.md` |
| `_edit` | -30 | `TAC__2025__budget_edit.md` |

### Content-based draft detection

Beyond filename suffixes, the canonicalizer also scans the **first 500 characters** of file content for draft indicators (case-insensitive):

- `draft`
- `work in progress`
- `not final`
- `pending review`

A file is flagged as a draft if **any** of these conditions are met:
1. Filename matches an `exclude_patterns` regex (e.g., `_draft_`, `_prep_`, `_working_`).
2. Filename stem matches a `draft_suffixes` pattern.
3. First 500 characters of content contain a draft marker string.

### Submission numbers

Some organizations follow a numbered submission convention. The following patterns in filename segments are recognized as submission version numbers:

- `submission_1`, `submission_2`, ...
- `1st_submission`, `2nd_submission`, ...
- `1st_sub`, `2nd_sub`, ...
- `submission_v1`, `submission_v2`, ...

Higher-numbered submissions are considered more authoritative. Content similarity is used to determine if a higher-numbered submission supersedes a lower-numbered one (threshold: `0.45`).

---

## Interaction with Pipeline Stages

| Stage | How it uses the filename convention |
|-------|-------------------------------------|
| **scan** | Detects funder (substring match against `funders` keys), year (4-digit regex), type (path patterns), drafts (filename markers). Produces a report; does not modify files. |
| **convert** | Preserves original filenames. Converted files keep the source filename stem with `.md` extension. |
| **clean** | Reads and writes with same filenames. No renaming. |
| **canonicalize** | Splits on `__` to group files by application key. Scores version/draft suffixes. Detects submission numbers in segments. Resolves duplicates and moves non-canonical files to `.non_canonical/`. |
| **classify** | Detects funder from path (substring match). Detects document types from filename (underscores → spaces, then regex match). Reads frontmatter for year data. |
| **rewrite** | Uses filename-derived metadata (funder, type, year) as hints in LLM prompts. Does not rename files. |
| **prioritize** | Groups files by `written` year from frontmatter. Does not parse filenames. |
| **wiki** | Uses frontmatter fields for metadata. Does not parse filenames. |

---

## Website Files

Website markdown files ingested via `folio website` follow a different convention from the standard `FUNDER__Year_Description__Type.md` format. These files represent scraped web page content (e.g., an organization's "About Us" page or funder program description).

```
{ORG_ABBREV}__{YYYY-MM-DD}__{name_slug}__webpage.md
```

The format consists of three segments separated by `__`:

| Position | Segment | Required | Example |
|----------|---------|----------|---------|
| 1 | Organization abbreviation | Yes | `IA`, `ARC` |
| 2 | Scraped date in `YYYY-MM-DD` format | Yes | `2025-06-01` |
| 3 | Name slug derived from URL or `--name` override | Yes | `about`, `our_mission` |

The final segment `webpage` is the document type tag (always `webpage` for website files).

Examples:

```
IA__2025-06-01__about__webpage.md
ARC__2025-01-15__board_of_directors__webpage.md
```

### How the slug is derived

The name slug is derived from the source URL's final path component, with extensions and special characters removed:

- `https://example.com/about` → slug: `about`
- `https://example.com/pages/our-mission.html` → slug: `our_mission`
- `https://example.com` (no path) → slug: `example_com`
- Empty/missing path → slug: `webpage`

Use `--name` to override the slug when ingesting a single file:

```bash
folio website --source page.md --name custom-slug
```

---

## Edge Cases

### Multiple funders

A file containing content related to multiple funders uses a single funder abbreviation — typically the primary funder. There is no multi-funder filename syntax. If a document references multiple funders, the LLM during rewrite can capture all funders in the frontmatter body, but only one abbreviation appears in the filename.

### Multi-year grants

Grants spanning multiple years use a period in the second segment instead of a single year:

```
OAC__2024-2026__Operating__application.md
```

The ingester supports this via the `--period` flag:

```bash
folio ingest --source grant.pdf --funder OAC --period 2024-2026 --type application
```

### Unknown document types

If a file does not match any configured `doc_types` pattern, the classifier assigns `"unknown"` as the type. The file is still processed — the type field in frontmatter will be confirmed or corrected by the LLM during rewrite.

### Files with fewer than 3 segments

Files that do not follow the `__`-separated convention (e.g., `report.md`, `my_document.md`) still process through the pipeline. The canonicalizer handles short segment lists gracefully:

- Files with fewer than `group_segments` (2) segments use their full stem as the app key.
- Funder and type detection fall back to path-based matching, which is less reliable without the structured naming.

### Segments with embedded underscores

Within segments, underscores are part of the description or type name and do **not** act as segment separators. Only `__` (double underscore) separates segments:

```
TAC__2025_Staff_and_Board__support_material.md
     ^^                          ^^
     segment boundaries
```

The description `2025_Staff_and_Board` is one segment. The type `support_material` is one segment.

---

## Configurable Naming

> **Note:** The filename convention is currently determined by the ingester code (`ingester.py:_build_output_filename`) and the canonicalizer's `DEFAULT_CANONICALIZE_CONFIG`. There is no way to configure an alternative naming scheme through `folio.yaml` at this time. Future versions may expose:
>
> - Configurable segment separators (e.g., `--` instead of `__`)
> - Configurable segment order (e.g., putting type before year)
> - Configurable `group_segments` for organizations that use more or fewer logical groupings

For now, all folio pipelines use the `FUNDER__Year_Description__Type.md` convention described in this document.
