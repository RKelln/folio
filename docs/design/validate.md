# `folio validate` — Design Document

## Purpose

A deterministic CLI tool that helps humans and agents review pipeline output quality. No LLM calls. Checks frontmatter, content corruption, file size anomalies, heading compliance, and produces actionable reports.

## Architecture

```
src/folio/
  cli/validate.py     ← CLI entry (--source DIR, --sample N, --tier, --all, --approve)
  core/validator.py   ← Core logic (no LLM, deterministic checks)
```

## CLI interface

```
folio validate --source ./markdown/              # Validate all files
folio validate --source ./markdown/ --sample 10  # Random sample of 10
folio validate --source ./markdown/ --tier full   # Only full-tier files
folio validate --source ./markdown/ --all         # All checks, verbose
folio validate --source ./markdown/ --json        # JSON output
folio validate --source ./markdown/ --dry-run     # Preview counts

Standard args: --config, --dry-run, --json, --version
```

## Core checks (deterministic, sequential)

### 1. Frontmatter validation
- Parse frontmatter via `parse_frontmatter()` from `core/frontmatter.py`
- Required fields present: `funder`, `type`, `written`
- Valid funder (against `config.funders`)
- Valid doc type (against `config.doc_types`)
- Non-negative `errors` count
- Priority in 1-3 if present

### 2. Content quality
- Reuse `_analyze_content()` from `core/classifier.py`
- Flag `corruption_score > 0.3` (excessive garbled text)
- Flag `form_chrome_count > 20` (poor cleanup)
- Flag `draft_marker_count > 0` in non-draft files
- Flag `avg_content_line_length < 30` (suspiciously short lines)

### 3. File size anomalies
- Flag files < 500 bytes (likely lost content)
- Flag files > 1MB (unusually large, possible binary remnants)
- Flag files with 0 content lines (empty after cleanup)

### 4. Heading compliance (when `headings.yaml` exists)
- Parse section headings from markdown (`## Heading` lines)
- Compare against expected canonical sections per funder
- Flag missing required sections
- Flag sections with < 50 chars of content (thin sections, adapted from `_check_thin_articles`)

### 5. Placeholder detection
- Flag `[TODO]`, `[FIXME]`, `[UNKNOWN]`, `[TBD]`, `???` markers
- Flag `{placeholder}` patterns (unfilled template variables)
- Flag common PDF corruption artifacts: repeated single characters, bare digits on lines

## Output format

```json
{
  "source_dir": "./markdown/",
  "files_scanned": 200,
  "files_passing": 185,
  "files_with_issues": 15,
  "validations": {
    "missing_frontmatter": [
      {"file": "abc.md", "missing": ["funder", "type"]}
    ],
    "corruption": [
      {"file": "def.md", "score": 0.72, "form_chrome": 45}
    ],
    "size_anomaly": [
      {"file": "ghi.md", "bytes": 234, "issue": "too_small"},
      {"file": "jkl.md", "bytes": 1250000, "issue": "too_large"}
    ],
    "missing_sections": [
      {"file": "mno.md", "funder": "OAC", "missing": ["Budget", "Timeline"]}
    ],
    "placeholders": [
      {"file": "pqr.md", "markers": ["[FIXME]", "[TODO]", "??? (3 lines)"]}
    ]
  },
  "summary": "15 files have issues: 3 missing frontmatter, 4 corruption, 2 size anomalies, 4 missing sections, 2 placeholders"
}
```

## Approval workflow

```bash
folio validate --source ./markdown/ --approve OAC__2024_App__Final.md
```

Writes to manifest via `update_file(manifest, fname, validated=True, validation_errors=[])`.

## Implementation plan

### Step 1: `core/validator.py` (~150 lines)
- `validate_frontmatter(text, config) -> list[dict]`
- `validate_content(text, classification_config) -> list[dict]`
- `validate_file_size(path) -> list[dict]`
- `validate_headings(text, headings_config, funder) -> list[dict]`
- `validate_placeholders(text) -> list[dict]`
- `validate_directory(path, config) -> dict` (orchestrator)
- `validate_file(path, config) -> dict` (single file)

Each returns a list of issue dicts with `{file, issue_type, details...}`.

### Step 2: `cli/validate.py` (~100 lines)
- Mirror `cli/audit.py` scaffolding
- `--source` flag for directory
- `--sample N` for random subset
- `--tier full|light|minimal` filter
- `--approve FILE` to mark reviewed
- `--all` for verbose output
- Standard `--config`, `--dry-run`, `--json`, `--version`

### Step 3: Registration
- Add `validate` to `_COMMANDS` in `cli/main.py`
- Add `folio-validate` to `pyproject.toml` entry points

### Step 4: Tests
- Unit tests for each validation function
- CLI tests for --help, --dry-run, --json

## Reusable APIs (already exist, do not reimplement)

| What | Module | Function | Line |
|------|--------|----------|------|
| Parse frontmatter | `core/frontmatter.py` | `parse_frontmatter()` | 42 |
| Content quality | `core/classifier.py` | `_analyze_content()` | 505 |
| Funder detection | `core/classifier.py` | `_detect_funder()` | 474 |
| Manifest I/O | `core/manifest.py` | `load/save/update_file()` | 73/82/91 |
| Project config | `config/loader.py` | `load_project_config()` | 225 |
| FileStatus enum | `core/errors.py` | `FileStatus` | 8 |

## Not in scope
- LLM-powered quality checks (deferred to future)
- Side-by-side diff view (human-only feature, not needed for agent-driven workflow)
- Auto-fix (validator reports, doesn't modify files)
