# folio.yaml Configuration Reference

`folio.yaml` is the single source of truth for an organization's folio pipeline. Every pattern, threshold, funder name, and classification rule lives here. Customizing folio for a new organization should never require editing Python code -- only YAML.

---

## How Configuration Works

### Default Merging

folio ships with built-in defaults in `src/folio/config/defaults.yaml`. When you provide a `folio.yaml`, it is **deep-merged** on top of those defaults:

- **Dicts are merged recursively** -- keys in your file override keys in defaults, but keys you omit retain their defaults.
- **Scalars and lists are replaced** -- providing a value for a scalar or a list key replaces the default entirely; there is no list concatenation.

```
defaults.yaml  +  folio.yaml  =  effective config
     (base)         (overrides)       (merged)
```

To inspect the effective config, run:

```bash
folio pipeline --dry-run
```

### .env File and Environment Variables

folio loads `.env` from the **same directory** as `folio.yaml` via `python-dotenv`. The following environment variables are recognized:

| Variable | Required by | Description |
|---|---|---|
| `DEEPSEEK_API_KEY` | LLM (default provider) | API key for DeepSeek or OpenAI-compatible endpoints |
| `OPENAI_API_KEY` | LLM (alternative) | API key when using `llm.provider: openai` |
| `DATALAB_API_KEY` | Datalab converter | API key for IBM Datalab pipeline |

You can override the expected variable name via `llm.api_key_env` or `converter.datalab.api_key_env`.

### Path Resolution

All paths in `folio.yaml` are **relative to the directory containing `folio.yaml`**. They are resolved to absolute paths at load time. For example, if `folio.yaml` is at `/org/library/folio.yaml`:

```yaml
paths:
  raw_archive: "./archive/"
```

resolves to `/org/library/archive/`.

---

## Section 1: `project`

Controls project-level metadata.

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `project.name` | `str` | `"My Grant Archive"` | Project name, used in reports and manifest files |
| `project.description` | `str` | `""` | Optional free-text description |

Example:

```yaml
project:
  name: "InterAccess Archive"
  description: "Grant documents, reports, and budgets 2018-2025"
```

---

## Section 2: `org`

Organization identity metadata.

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `org.name` | `str` | `"My Organization"` | Full legal/organizational name |
| `org.abbreviation` | `str` | `"ORG"` | Short code used in filenames and manifests |
| `org.description` | `str` | `""` | Optional mission statement or description |

Example:

```yaml
org:
  name: "InterAccess"
  abbreviation: "IA"
  description: "Dedicated to emerging practices in art and technology"
```

---

## Section 3: `funders`

A flat dictionary mapping funder **abbreviations** to their **full names**. Abbreviations are used in filenames (e.g., `TAC__2024__Operating_Grant__application.md`) and for funder detection.

### How Funder Detection Works

Both the **scanner** and **classifier** detect funders by searching file paths for the abbreviation (case-insensitive, longest match first). A file at `OAC/2024/grant.pdf` or named `OAC__2024__Report.md` is matched against the `funders` dictionary keys. If a match is found, the abbreviation is assigned.

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `funders` | `dict[str, str]` | `{}` | Map of abbreviation (key) to full funder name (value) |

Example:

```yaml
funders:
  OAC: "Ontario Arts Council"
  TAC: "Toronto Arts Council"
  CCA: "Canada Council for the Arts"
  BCAH: "Canadian Heritage"
```

---

## Section 4: `doc_types`

A list of valid document type tags. These tags are embedded in filenames (`TAC__2024__Report__report.md`) and used by the classifier to assign content categories.

### How Type Detection Works

The **scanner** uses built-in regex patterns (in `DEFAULT_TYPE_PATTERNS`) to detect types from filenames and directory paths. The **classifier** also uses the `doc_types` list to validate and match types. Underscores in paths are normalized to spaces before matching (so `staff_board` matches `staff board` patterns).

For custom type detection patterns beyond the built-ins, define `doc_types` as a dict where each key is a type name and the value is a list of regex patterns:

```yaml
doc_types:
  application: ["(?i)application", "(?i)submission"]
  report: ["(?i)report", "(?i)annual update"]
  budget: ["(?i)budget", "(?i)financial"]
```

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `doc_types` | `list[str]` | See below | Valid document type tags |

Default list:

```yaml
doc_types:
  - application
  - report
  - budget
  - notification
  - activity_list
  - staff_board
  - support_material
  - agreement
```

---

## Section 5: `paths`

Pipeline input, output, and intermediate directories. All paths are relative to the `folio.yaml` location.

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `paths.raw_archive` | `str` | `"./archive/"` | Directory containing raw source files (PDF, DOCX, XLSX). The pipeline reads from here. |
| `paths.raw_md` | `str` | `"./.folio/converted/"` | Converter output -- raw markdown produced from source files. Intermediate (hidden). |
| `paths.clean_md` | `str` | `"./.folio/cleaned/"` | Cleaned markdown after form chrome and artifact removal. Intermediate (hidden). |
| `paths.rewrite_md` | `str` | `"./markdown/"` | Final LLM-rewritten markdown output. This is the publishable product. Also stores `manifest.json`. |
| `paths.wiki_project` | `str` | `"./.folio/sage-wiki/"` | Sage-wiki project directory (hidden intermediate). After compile, a root `wiki/` symlink is created pointing to the compiled output. `wiki/raw/` is a symlink to `markdown/`. |

Example:

```yaml
paths:
  raw_archive: "./archive/"
  raw_md: "./.folio/converted/"
  clean_md: "./.folio/cleaned/"
  rewrite_md: "./markdown/"
  wiki_project: "./.folio/sage-wiki/"
```

---

## Section 6: `converter`

Controls how source documents (PDF, DOCX, XLSX) are converted to Markdown.

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `converter.type` | `str` | `"docling"` | Converter backend: `docling`, `datalab`, `marker`, or `pandoc` |
| `converter.datalab.pipeline_id` | `str` | `""` | Datalab pipeline ID (required when type is `datalab`) |
| `converter.datalab.api_key_env` | `str` | `"DATALAB_API_KEY"` | Environment variable name for the Datalab API key |

### Converter Types and Supported Extensions

| Type | Supported extensions | Description |
|---|---|---|
| `docling` | `.pdf`, `.docx`, `.xlsx` | IBM Docling open-source library. Local, no API key needed. **Default.** Strong table extraction. |
| `datalab` | `.pdf`, `.docx`, `.xlsx`, `.doc`, `.xls` | IBM Datalab pipeline API. Best quality for grant forms. Requires `datalab-python-sdk` and API key. |
| `marker` | `.pdf` | Open-source `marker-pdf` library. Local, no API key needed. Not yet implemented. |
| `pandoc` | `.pdf`, `.docx`, `.html`, `.rst`, many more | Universal converter via Pandoc. Lowest quality for grant forms. Not yet implemented. |

Example:

```yaml
converter:
  type: "datalab"
  datalab:
    pipeline_id: "abc123-my-pipeline"
    api_key_env: "DATALAB_API_KEY"
```

---

## Section 7: `wiki`

Controls wiki backend compilation.

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `wiki.type` | `str` | `"sage-wiki"` | Wiki backend: `sage-wiki` or `null` (no wiki, markdown-only output) |
| `wiki.sage_wiki.binary_path` | `str` | `"sage-wiki"` | Path to the `sage-wiki` binary (must be on `PATH` or an absolute path) |
| `wiki.sage_wiki.pack` | `str` | `"arts-org"` | Sage-wiki pack name that controls wiki structure and templates |

Example:

```yaml
wiki:
  type: "sage-wiki"
  sage_wiki:
    binary_path: "sage-wiki"
    pack: "arts-org"
```

To disable wiki output entirely:

```yaml
wiki:
  type: "null"
```

---

## Section 8: `agentmap`

Controls agentmap TOC (table of contents) generation for agent navigation.

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `agentmap.enabled` | `bool` | `false` | Set to `true` to enable agentmap TOC generation |
| `agentmap.binary_path` | `str` | `"agentmap"` | Path to the `agentmap` binary (must be on `PATH` or an absolute path) |

Example:

```yaml
agentmap:
  enabled: true
  binary_path: "agentmap"
```

When enabled, the pipeline validates that the `agentmap` binary is accessible on `PATH`. If disabled (default), no agentmap processing occurs.

---

## Section 9: `llm`

Controls the LLM provider used for rewriting and prioritization. Uses an OpenAI-compatible API.

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `llm.provider` | `str` | `"openai_compatible"` | Provider identifier |
| `llm.base_url` | `str` | `"https://api.deepseek.com"` | API base URL. Must use `https://` (or `http://` for localhost/private IPs) |
| `llm.api_key_env` | `str` | `"DEEPSEEK_API_KEY"` | Environment variable name for the API key |
| `llm.models.fast` | `str` | `"deepseek-v4-flash"` | Model used for fast/lightweight tasks (cleaning, tier evaluation) |
| `llm.models.quality` | `str` | `"deepseek-v4-pro"` | Model used for high-quality tasks (full rewrites) |
| `llm.pricing.input_per_million` | `float` | `0.14` | Cost in USD per 1M input tokens (used for dry-run cost estimates) |
| `llm.pricing.cached_input_per_million` | `float` | `0.0028` | Cost in USD per 1M cached input tokens |
| `llm.pricing.output_per_million` | `float` | `0.28` | Cost in USD per 1M output tokens |

Example (DeepSeek):

```yaml
llm:
  provider: "openai_compatible"
  base_url: "https://api.deepseek.com"
  api_key_env: "DEEPSEEK_API_KEY"
  models:
    fast: "deepseek-v4-flash"
    quality: "deepseek-v4-pro"
  pricing:
    input_per_million: 0.14
    cached_input_per_million: 0.0028
    output_per_million: 0.28
```

Example (OpenAI):

```yaml
llm:
  provider: "openai"
  base_url: "https://api.openai.com/v1"
  api_key_env: "OPENAI_API_KEY"
  models:
    fast: "gpt-4o-mini"
    quality: "gpt-4o"
  pricing:
    input_per_million: 0.15
    output_per_million: 0.60
```

---

## Section 10: `processing`

Controls pipeline execution behavior (concurrency, rate limiting, reliability).

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `processing.max_workers` | `int` | `10` | Maximum number of concurrent worker threads. Must be `>= 1`. |
| `processing.requests_per_second` | `float` | `5.0` | Maximum LLM API requests per second (rate limiting) |
| `processing.max_retries` | `int` | `3` | Maximum retry attempts for failed API calls |
| `processing.resume` | `bool` | `true` | Whether to skip already-completed stages on pipeline restart |

Example:

```yaml
processing:
  max_workers: 10
  requests_per_second: 5
  max_retries: 3
  resume: true
```

---

## Section 11: `classification`

Controls how files are scored for quality and assigned to processing tiers. This section is **entirely optional** -- if omitted, sensible defaults apply.

### Processing Tiers

Files are assigned to one of four tiers:

| Tier | Criteria | Description |
|---|---|---|
| `full` | Matched by a `tier_rule` | Full LLM rewrite with heading taxonomy normalization |
| `light` | Matched by a `tier_rule` | Light cleanup, preserve structure |
| `minimal` | Fallback when no `tier_rule` matches | Metadata-only (frontmatter extraction) |
| `skip` | Matched by a `skip_rule` | Excluded from further processing |

### 4.10.1 `classification.thresholds`

Threshold values used by content quality analysis and tier evaluation rules. Thresholds are organized into sub-groups for different processing tiers and document types.

**Top-level thresholds:**

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `classification.thresholds.min_content_lines` | `int` | `15` | Absolute minimum content lines for any tier |
| `classification.thresholds.max_corruption_score` | `float` | `0.5` | Maximum corruption score (0-1) for any tier |

**`classification.thresholds.full_rewrite`** — thresholds for standard documents eligible for full LLM rewrite:

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `...full_rewrite.form_chrome_count` | `int` | `5` | Maximum form chrome lines |
| `...full_rewrite.draft_marker_count` | `int` | `5` | Maximum draft marker lines |
| `...full_rewrite.duplicate_heading_count` | `int` | `5` | Maximum duplicate heading count |
| `...full_rewrite.word_count_annotation_count` | `int` | `5` | Maximum word-count annotation lines |

**`classification.thresholds.full_rewrite_app_report`** — tighter thresholds for application/report documents:

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `...full_rewrite_app_report.form_chrome_count` | `int` | `2` | Maximum form chrome lines |
| `...full_rewrite_app_report.draft_marker_count` | `int` | `2` | Maximum draft marker lines |

**`classification.thresholds.light_cleanup`** — thresholds for documents needing only light cleanup:

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `...light_cleanup.form_chrome_count` | `int` | `2` | Maximum form chrome lines |
| `...light_cleanup.draft_marker_count` | `int` | `2` | Maximum draft marker lines |
| `...light_cleanup.duplicate_heading_count` | `int` | `2` | Maximum duplicate heading count |
| `...light_cleanup.word_count_annotation_count` | `int` | `2` | Maximum word-count annotation lines |

**`classification.thresholds.raw_financial`** — thresholds for raw financial/spreadsheet documents:

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `...raw_financial.max_avg_line_length` | `int` | `50` | Maximum average character length per line |
| `...raw_financial.min_content_lines` | `int` | `50` | Minimum content lines |

Example:

```yaml
classification:
  thresholds:
    min_content_lines: 15
    max_corruption_score: 0.5
    full_rewrite:
      form_chrome_count: 5
      draft_marker_count: 5
      duplicate_heading_count: 5
      word_count_annotation_count: 5
    full_rewrite_app_report:
      form_chrome_count: 2
      draft_marker_count: 2
    light_cleanup:
      form_chrome_count: 2
      draft_marker_count: 2
      duplicate_heading_count: 2
      word_count_annotation_count: 2
    raw_financial:
      max_avg_line_length: 50
      min_content_lines: 50
```

### 4.10.2 `classification.skip_rules`

Rules that cause a file to be **skipped** (excluded from the pipeline). Evaluated in order; first match wins.

Each rule has:
- `condition` -- a condition dict (legacy string format) or `conditions` + `match` (new DSL format)
- `reason` -- human-readable reason for skipping (supports `{field_name}` interpolation)

```yaml
classification:
  skip_rules:
    - condition:
        type: has_doc_type
        value: guidelines
      reason: "Guidelines document — not grant content"

    - condition:
        type: and
        conditions:
          - type: has_doc_type
            value: email
          - type: field_lt
            field: content_lines
            value: 20
      reason: "Short email with insufficient content"

    - condition: "has_type('draft')"
      reason: "Draft document"
```

### 4.10.3 `classification.tier_rules`

Rules that assign processing tiers. Evaluated in order; first match wins. Unmatched files default to `minimal`.

Each rule has:
- `condition` or `conditions` + `match` -- same as skip rules
- `tier` -- one of `full`, `light`, `minimal`, `skip`

```yaml
classification:
  tier_rules:
    - condition:
        type: and
        conditions:
          - type: field_gt
            field: content_lines
            value: 40
          - type: field_lt
            field: corruption_score
            value: 0.5
      tier: full

    - condition:
        type: and
        conditions:
          - type: field_gt
            field: content_lines
            value: 10
          - type: field_lt
            field: corruption_score
            value: 0.3
      tier: light

    - condition: "content_lines > 50 and not has_tables and avg_content_line_length < 50"
      tier: full

    - condition: "form_chrome_count > 5 or draft_marker_count > 5"
      tier: light

    - condition: "true"
      tier: minimal
```

### 4.10.4 `classification.form_chrome`

Regex patterns that identify form boilerplate lines (field labels, instructional text). Matched lines increase the `form_chrome_count` quality metric.

```yaml
classification:
  form_chrome:
    - "(?i)(name of applicant|legal name)"
    - "(?i)(mailing address|postal code)"
    - "(?i)(telephone|fax number)"
    - "(?i)(signature|date)"
    - "(?i)(please check|select one|choose all that apply)"
```

### 4.10.5 `classification.draft_markers`

Regex patterns that identify draft indicators in filenames or content. Matched lines increase `draft_marker_count`.

```yaml
classification:
  draft_markers:
    - "draft"
    - "working_copy"
    - "(?i)do not submit"
```

### 4.10.6 `classification.corruption`

Toggles for corruption detection heuristics.

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `classification.corruption.single_char_alpha` | `bool` | `true` | Flag isolated single alphabetic characters (split-word artifacts) |
| `classification.corruption.bare_digits` | `bool` | `true` | Flag bare digit sequences (page numbers, index artifacts) |

### 4.10.7 `classification.word_count_pattern`

Regex pattern for detecting word-count annotations (e.g., "500 words", "1000 words").

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `classification.word_count_pattern` | `str` | `r'(?m)^\\d+\\s+words?\\s*$'` | Regex for word-count annotation lines |

---

### Condition DSL Reference

Classification rules use a **safe condition DSL** (no `eval()`). There are 12 condition types:

#### Simple Conditions

| Condition type | Value field | Description |
|---|---|---|
| `has_doc_type` | `value` (str) | True if the file has this document type tag |
| `has_any_type` | `values` (list[str]) | True if the file has any of these type tags |
| `field_gt` / `field_lt` / `field_gte` / `field_lte` | `field` (str), `value` (int/float) | Numeric field comparison against context |
| `path_contains` | `values` (list[str]) | True if any substring appears in the file path |
| `filename_starts_with` | `value` (str) | True if the filename starts with this prefix |
| `has_headings` | (none) | True if the file contains markdown headings (`#`) |
| `has_tables` | (none) | True if the file contains markdown tables (`|`) |
| `true` | (none) | Always true |

#### Compound Conditions

| Condition type | Structure | Description |
|---|---|---|
| `not_` | `condition` (dict) | Negates the inner condition |
| `and` | `conditions` (list[dict]), `match: "all"` | All conditions must be true |
| `or` | `conditions` (list[dict]), `match: "any"` | At least one condition must be true |

#### Available Context Fields

Conditions evaluate against these field names:

| Field | Type | Description |
|---|---|---|
| `corruption_score` | `float` | Ratio of corruption lines to total lines (0-1) |
| `content_lines` | `int` | Number of non-blank, non-corruption lines |
| `form_chrome_count` | `int` | Number of lines matching form chrome patterns |
| `draft_marker_count` | `int` | Number of lines matching draft markers |
| `duplicate_heading_count` | `int` | Count of duplicate markdown headings |
| `word_count_annotation_count` | `int` | Count of word-count annotation lines |
| `avg_content_line_length` | `float` | Average character length of content lines |
| `has_headings` | `bool` | Whether the file has any markdown headings |
| `has_tables` | `bool` | Whether the file has any markdown tables |
| `doc_types` | `list[str]` | Detected document type tags |
| `filename` | `str` | Filename (e.g., `TAC__2024__Report.md`) |
| `filepath` | `str` | Full file path |
| `funder` | `str` or `None` | Detected funder abbreviation |

#### Legacy Condition String Format

The classifier also supports a legacy eval-string syntax for backward compatibility. These are parsed into the DSL automatically:

```
has_type('X')                                    → has_doc_type
has_any_type('X', 'Y')                           → has_any_type
path_contains('X', 'Y')                          → path_contains
filename.startswith('X')                         → filename_starts_with
has_headings / has_tables                        → has_headings / has_tables
not <expr>                                       → not_
> < >= <= comparisons                            → field_gt / field_lt / field_gte / field_lte
and / or                                         → compound conditions
true / false                                     → true / not_ true
```

**Prefer the DSL format** (`type: has_doc_type`) for new configurations. The legacy format is maintained for backward compatibility with existing configs.

---

## Section 12: `headings`

Per-funder canonical heading taxonomy. Used by the rewriter to normalize document headings into a consistent structure per funder.

### Structure

```yaml
headings:
  FUNDER_ABBREV:
    display: "Full Funder Name Display"    # optional display name
    headings:
      "Canonical Section Name":              # the normalized heading
        - "Alternate Name 1"                 # heading variants from actual forms
        - "Alternate Name 2"
      "Another Section":
        - "Variant A"
        - "Variant B"
```

Each funder key (e.g., `OAC`, `TAC`) maps to a dict with:
- `display` (optional) -- human-readable funder name
- `headings` -- dict of canonical heading names to lists of alternative/variant heading strings found in actual documents

### How Headings Are Used

During the `rewrite` stage, the LLM maps a document's actual section headings to the canonical headings defined here. This normalizes heterogeneous documents (different years, different form versions) into a consistent taxonomy, making wiki search and agent retrieval reliable.

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `headings` | `dict[str, dict]` | `{}` | Per-funder heading taxonomy. Keys are funder abbreviations. |

Example:

```yaml
headings:
  OAC:
    display: "Ontario Arts Council (OAC)"
    headings:
      "Organization Information":
        - "Organization Information"
        - "Organization Information Updates"
      "Governance and Organizational Structure":
        - "Governance and Organizational Structure"
        - "Governance"
      "Board and Staff":
        - "Board and Staff"
        - "Staff List"
        - "Board of Directors"
      "Financial Overview":
        - "Financial"
        - "Budget"
        - "Financial Statements"

  TAC:
    display: "Toronto Arts Council (TAC)"
    headings:
      "Overview":
        - "Overview"
      "Long-Term Plan":
        - "Long-Term Plan"
        - "Strategic Plan"
      "Organization History and Mandate":
        - "Organization History"
        - "Mandate"
        - "Mission Statement"
      "Financial":
        - "Financial"
        - "Financial Statements"
        - "Finances"
```

---

## Section 13: `audit`

Controls the wiki quality audit tool (`folio audit`). All fields are optional and deep-merged with defaults.

### 4.12.1 Article Size Thresholds

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `audit.min_article_chars` | `int` | `200` | Minimum body character count; articles below this are flagged as thin |
| `audit.min_article_lines` | `int` | `5` | Minimum body line count; articles below this are flagged as thin |

### 4.12.2 Deduplication

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `audit.dedup_threshold` | `float` | `0.85` | SequenceMatcher ratio threshold for near-duplicate detection (0-1) |
| `audit.word_overlap_threshold` | `float` | `0.35` | Jaccard word-bag overlap threshold for dedup candidacy (0-1) |
| `audit.word_band_size` | `int` | `30` | Word-bag size banding granularity for efficient dedup pairing |

### 4.12.3 Section Checking

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `audit.expected_sections` | `list[str]` | `["Definition", "Key Figures", "Body", "Context & Significance", "See also"]` | Sections expected in every concept article |
| `audit.required_sections` | `list[str]` | `["Body"]` | Sections that must be present; articles missing these are flagged |

### 4.12.4 Stale Content Detection

| YAML path | Python type | Default | Description |
|---|---|---|---|
| `audit.stale_content_patterns` | `list[dict]` | `[]` | Patterns for detecting stale content using present-tense indicators |
| `audit.suspicious_name_patterns` | `list[tuple]` | See defaults | (name regex, label) pairs for detecting auto-generated concept names |
| `audit.present_tense_indicators` | `list[str]` | See defaults | Regex patterns indicating present-tense language |
| `audit.timeline_keywords` | `list[str]` | See defaults | Keywords that suggest content covers a historical period (not stale) |

Example:

```yaml
audit:
  min_article_chars: 200
  min_article_lines: 5
  dedup_threshold: 0.85
  expected_sections:
    - "Definition"
    - "Key Figures"
    - "Body"
    - "Context & Significance"
    - "See also"
  required_sections:
    - "Body"
  stale_content_patterns:
    - keywords: ["staff", "director"]
      hint: "Staff/director info may be out of date"
    - keywords: ["board"]
      require_link: "Board of Directors"
      hint: "Board listing may have changed"
```

---

## Complete Example

Putting it all together, a realistic `folio.yaml` for a Canadian artist-run centre:

```yaml
project:
  name: "InterAccess Archive"
  description: "Grant applications, reports, and budgets 2018-2025"

org:
  name: "InterAccess"
  abbreviation: "IA"
  description: "Dedicated to emerging practices in art and technology"

funders:
  OAC: "Ontario Arts Council"
  TAC: "Toronto Arts Council"
  CCA: "Canada Council for the Arts"
  BCAH: "Canadian Heritage"

doc_types:
  - application
  - report
  - budget
  - notification
  - activity_list
  - staff_board
  - support_material
  - agreement

paths:
  raw_archive: "./archive/"
  raw_md: "./.folio/converted/"
  clean_md: "./.folio/cleaned/"
  rewrite_md: "./markdown/"
  wiki_project: "./.folio/sage-wiki/"

converter:
  type: "docling"

wiki:
  type: "sage-wiki"
  sage_wiki:
    binary_path: "sage-wiki"
    pack: "arts-org"

llm:
  provider: "openai_compatible"
  base_url: "https://api.deepseek.com"
  api_key_env: "DEEPSEEK_API_KEY"
  models:
    fast: "deepseek-v4-flash"
    quality: "deepseek-v4-pro"
  pricing:
    input_per_million: 0.14
    cached_input_per_million: 0.0028
    output_per_million: 0.28

processing:
  max_workers: 10
  requests_per_second: 5
  max_retries: 3
  resume: true

classification:
  skip_rules:
    - condition:
        type: has_doc_type
        value: guidelines
      reason: "Guidelines document"

  tier_rules:
    - condition:
        type: and
        conditions:
          - type: field_gt
            field: content_lines
            value: 40
          - type: field_lt
            field: corruption_score
            value: 0.5
      tier: full

    - condition:
        type: and
        conditions:
          - type: field_gt
            field: content_lines
            value: 10
          - type: field_lt
            field: corruption_score
            value: 0.3
      tier: light

  thresholds:
    min_content_lines: 15
    max_corruption_score: 0.5
    full_rewrite:
      form_chrome_count: 5
      draft_marker_count: 5
      duplicate_heading_count: 5
      word_count_annotation_count: 5
    full_rewrite_app_report:
      form_chrome_count: 2
      draft_marker_count: 2
    light_cleanup:
      form_chrome_count: 2
      draft_marker_count: 2
      duplicate_heading_count: 2
      word_count_annotation_count: 2
    raw_financial:
      max_avg_line_length: 50
      min_content_lines: 50

  form_chrome:
    - "(?i)(name of applicant|legal name)"
    - "(?i)(mailing address|postal code)"

  draft_markers:
    - "draft"
    - "working_copy"

  corruption:
    single_char_alpha: true
    bare_digits: true

audit:
  min_article_chars: 200
  min_article_lines: 5
  dedup_threshold: 0.85
  expected_sections:
    - "Definition"
    - "Key Figures"
    - "Body"
    - "Context & Significance"
    - "See also"
  required_sections:
    - "Body"

headings:
  OAC:
    display: "Ontario Arts Council (OAC)"
    headings:
      "Organization Information":
        - "Organization Information"
      "Governance and Organizational Structure":
        - "Governance and Organizational Structure"
        - "Governance"
      "Board and Staff":
        - "Board and Staff"
        - "Staff List"
      "Financial Overview":
        - "Financial"
        - "Budget"
```

---

## Validation Errors

folio validates your `folio.yaml` at load time and raises errors for:

| Condition | Error message |
|---|---|
| `converter.type` not in `{datalab, marker, docling, pandoc}` | `Invalid converter type: '...'` |
| `wiki.type` not in `{sage-wiki, null}` | `Invalid wiki type: '...'` |
| `llm.base_url` not starting with `https://` or allowed `http://` prefix | `LLM base_url must use https://, or http:// for localhost/private IPs` |
| `processing.max_workers < 1` | `processing.max_workers must be >= 1` |
| `llm.pricing.input_per_million` or `output_per_million` not a number | `llm.pricing.input_per_million must be a number` |

Warnings are logged (not errors) for:
- No funders configured
- `paths.raw_archive` directory does not exist
