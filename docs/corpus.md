# Synthetic Corpus (`folio corpus`)

`folio corpus` generates a deterministic, **PII-free** synthetic grant corpus whose *structure* (frontmatter, headings, labelled form fields, pipe tables, letters) mirrors a real grant archive, but whose *content* is entirely fake (Faker-generated). It renders the generated documents to DOCX/XLSX/PDF, strips authoring metadata, and runs a PII safety gate.

The corpus is the inverse of the [converters](converters.md): converters turn real documents *into* markdown; the corpus generator authors golden markdown and renders it *out* to binary formats so the converters can be benchmarked against a known-good reference.

## When to use it

- **Build or refresh benchmark fixtures** — committed fixtures live in `benchmark/corpus/` and feed the converter benchmark (bead `folio-ax5`).
- **Test converters / renderers** — every render is generated from a deterministic golden markdown source, so output is byte-reproducible for a given seed.
- **PII-gate anonymized real documents** — `folio corpus scan` runs the same PII detector over arbitrary files/directories and can be used as a pre-commit / CI gate (use `--strict`).

The golden markdown (`md`) render of each document is **the reference**; all other formats (`docx`, `xlsx`, `pdf`, `pdf_scanned`) are derived from it with authoring metadata stripped.

---

## Quickstart

```bash
# Install the optional extra (see Dependencies below)
uv pip install "folio[corpus]"

# Generate the bundled default corpus into benchmark/corpus/
folio corpus

# Preview the plan as JSON without writing anything
folio corpus generate --dry-run --json

# Generate with overrides
folio corpus generate --out ./corpus --seed 42 --funder TAC --formats md,docx

# PII-gate a directory (pre-commit / CI)
folio corpus scan ./benchmark/corpus/

# Strict gate over anonymized real documents (fails on ANY finding)
folio corpus scan --strict --denylist names.yaml ./anonymized/
```

`folio corpus` has two subcommands:

| Subcommand | Purpose |
|------------|---------|
| `generate` (default) | Generate corpus from a spec, render formats, strip metadata, run the PII gate |
| `scan` | Run the PII scan over files/directories (pre-commit / CI gate) |

`generate` is the default: running `folio corpus` with no subcommand is equivalent to `folio corpus generate` with all-default options.

**Exit codes:** `0` on success and a clean (passing) gate; `1` on any error (bad spec, render failure, missing required tool) or a **failing** gate.

---

## Pipeline

`folio corpus generate` runs four steps:

1. **Generate golden markdown** — the deterministic reference, authored from the spec.
2. **Render derived formats** — DOCX/XLSX/PDF/scanned-PDF from the golden markdown.
3. **Strip metadata** — remove authoring metadata from each rendered artifact in place.
4. **PII gate** — scan every written file and apply the gate policy.

### Output layout

Files are written under the spec's `output_dir` (default `benchmark/corpus`):

```
<output_dir>/
├── golden/
│   └── <slug>.md            # the golden reference markdown
└── rendered/
    ├── <slug>.docx
    ├── <slug>.xlsx
    ├── <slug>.pdf
    └── <slug>.scanned.pdf   # image-only / scanned-PDF variant
```

The filename **slug** is `<funder-lowercased>-<kind>-<NN>`, e.g. `oac-application-01`, `tac-budget-02`.

---

## Spec file format

The corpus spec is a **standalone** YAML file — it is *not* part of `folio.yaml` / `ProjectConfig` and is loaded independently by `folio.core.corpus.spec.load_corpus_spec()`. When `--spec` is omitted, the bundled default at `src/folio/templates/corpus/corpus-spec.yaml` is used.

```yaml
# corpus-spec.yaml

# Deterministic RNG seed. The same seed always reproduces the same corpus.
# Must be an integer. Default: 1234
seed: 1234

# folio profile this corpus is modeled on. Drives heading taxonomies and
# vocabulary. See src/folio/templates/profiles/ for available profiles.
# Default: canadian-artist-run-centre
profile: canadian-artist-run-centre

# Funder the documents target. The abbreviation must match a key in the
# profile's headings taxonomy (e.g. OAC, TAC, CCA, BCAH). Non-empty.
# Default: OAC
funder: OAC

# Where generated documents are written, relative to the org library root.
# Default: benchmark/corpus
output_dir: benchmark/corpus

# The documents to generate. Each entry is one document `kind` plus:
#   count   — how many distinct synthetic documents to author (>= 1, default 1)
#   formats — which renders to emit for each authored document (default [md])
documents:
  - kind: application
    count: 1
    formats: [md, pdf, docx]

  - kind: narrative
    count: 1
    formats: [md, pdf]

  - kind: budget
    count: 1
    formats: [md, xlsx, pdf]

  - kind: activity_list
    count: 1
    formats: [md, docx]

  - kind: staff_board
    count: 1
    formats: [md, docx, pdf]

  - kind: support_letter
    count: 1
    formats: [md, pdf, pdf_scanned]
```

The spec is validated on load. Validation fails (with all errors reported at once) if `seed` is not an int, `funder`/`profile`/`output_dir` are empty, `documents` is empty, any `kind` is unknown, any `count` is `< 1`, or any `format` is unknown.

### CLI overrides

`generate` flags override fields read from the spec:

| Flag | Effect |
|------|--------|
| `--spec PATH` | Path to a `corpus-spec.yaml` (default: bundled template) |
| `--out DIR` | Override `output_dir` |
| `--seed N` | Override the RNG `seed` |
| `--funder ABBR` | Override `funder` |
| `--formats LIST` | Comma-separated formats applied to **every** document (e.g. `md,docx,pdf`); validated against the allowed set |
| `--strict` | Fail the gate on ANY PII finding (default fails only on real-PII kinds) |
| `--denylist PATH` | Override the PII name denylist YAML |
| `--dry-run`, `-n` | Preview the plan without writing or scanning |
| `--json` | Emit JSON (dry-run plan, or generation manifest + gate result) |

`folio corpus --version` prints the folio version.

---

## Document kinds

| Kind | Frontmatter `type` | Content |
|------|--------------------|---------|
| `application` | `application` | Labelled form fields (applicant, email, phone, organization, address, request amount, project title, date) followed by one heading section per profile heading. Carries a `grant_amount`. |
| `narrative` | `report` | Multi-paragraph prose under each profile heading. No form fields and no currency — scans completely clean. |
| `budget` | `budget` | A `## Budget` with Revenue + Expenses pipe tables; totals are computed arithmetically (never faked). Carries a `grant_amount` pinned to the funder grant row. |
| `activity_list` | `activity_list` | A 6–12 row `Date / Activity / Location` pipe table. |
| `staff_board` | `staff_board` | A `Name / Role` pipe table of ~8 mixed staff and board roles. |
| `support_letter` | `support_material` | A dated support letter: salutation, body paragraphs, signature. |

Every document's frontmatter carries `funder`, `type`, `written` (a year drawn `2018–2024`), `period`, and `language: en`. `grant_amount` is included only for `application` and `budget`.

---

## Formats and renderers

| Format | Renderer | Required tools |
|--------|----------|----------------|
| `md` | (authored golden source) | none |
| `docx` | python-docx | `python-docx` |
| `xlsx` | openpyxl | `openpyxl` |
| `pdf` | pandoc + typst | `pandoc` **and** `typst` on PATH |
| `pdf_scanned` | pandoc + typst + poppler + Pillow | `pandoc`, `typst`, `pdftoppm` (poppler), and `Pillow` |

`pdf` is a real, text-bearing PDF. `pdf_scanned` is an image-only/rasterized PDF (no embedded text) used to exercise OCR paths: it renders a text PDF, rasterizes each page to PNG via `pdftoppm`, then recombines the images into a single image-only PDF with Pillow.

### Graceful degradation

Each renderer reports `available()` (checks importable Python deps and PATH tools without raising). During generation, a format whose renderer is unavailable is **skipped with a logged warning** — the golden markdown is always written, and the run continues. Skipped formats are listed in the human-readable summary and in the `files_skipped` array of `--json` output. `--dry-run` shows which formats would render vs. `(SKIP)`.

The PDF renderer falls back from `pandoc --pdf-engine=typst` to a two-step `pandoc → .typ`, `typst compile → .pdf` if the direct path fails.

---

## PII gate policy

The synthetic corpus **deliberately** contains Faker-generated emails, phone numbers, and `$` amounts in form fields, budgets, and activity lists — so a "zero findings" gate would be wrong.

The PII scanner reports findings of these kinds:

| Kind | Detected by |
|------|-------------|
| `email`, `phone`, `sin`, `ssn`, `postal_code`, `currency` | conservative structural regexes |
| `denylisted_name` | whole-word, case-insensitive match against the name denylist |
| `unscannable` | recorded when a file's text could not be extracted |

**Default (non-strict) gate** — fails only on the genuine-leak kinds:

```
FAILS on:            denylisted_name, unscannable
COUNTS but PASSES:   email, phone, sin, ssn, postal_code, currency
```

These failing kinds are fixed in code as `GATE_FAILING_KINDS` (`src/folio/cli/corpus.py`).

**`--strict`** — fails the gate on **any** finding. Use this when scanning *anonymized real documents*, where every structural hit is suspicious.

> **Numeric detectors are intentionally noisy.** The `sin` detector matches any 9-digit sequence and will flag grant IDs and large numbers; the gate prefers false positives over missed PII. These structural findings are counted but pass under the default policy.

### Name denylist

Real person/organization names can't be caught by regex, so each org lists them in a denylist YAML (`names:` is a list). The bundled default lives at `src/folio/templates/corpus/pii-denylist.yaml`; override it with `--denylist PATH`. Matching is whole-word and case-insensitive (`"Robert"` will not match `"Robertson"`). This is config, never hardcoded — add your staff, board, applicant, and partner-org names there.

### `scan` subcommand

```bash
folio corpus scan [--strict] [--denylist PATH] [--dry-run] [--json] PATH [PATH ...]
```

`scan` takes one or more files/directories (directories recurse for known extensions: `.md`, `.markdown`, `.txt`, `.html`, `.htm`, `.csv`, `.pdf`, `.docx`, `.xlsx`). It applies the same gate policy and exit codes as `generate`. Text formats are read as UTF-8; `.pdf` is extracted with `pdftotext` (poppler); `.docx` via python-docx; `.xlsx` via openpyxl. A file whose text cannot be extracted yields a single `unscannable` finding — never silently treated as clean.

---

## Metadata stripping

Authoring metadata (author, last-modified-by, PDF Producer/Creator, XMP toolkit, timestamps) is a PII risk. After each artifact is rendered, `strip_metadata` removes it in place, dispatching by suffix:

| Suffix | How |
|--------|-----|
| `.pdf`, `.png`, `.jpg`, `.jpeg` | `exiftool -all=` — **required**; if `exiftool` is missing the strip **raises** rather than leaving metadata in place |
| `.docx` | clear python-docx core properties, then best-effort `exiftool` |
| `.xlsx` | clear openpyxl workbook properties, then best-effort `exiftool` |

DOCX date properties (`created`, `modified`, `last_printed`) are overwritten with a neutral, obviously-synthetic constant — **1980-01-01** — because python-docx rejects `None` for date fields. The DOCX core-property scrub list (`DOCX_CORE_PROPS`) is the single source of truth, applied both by the DOCX renderer and by `strip_metadata`, so the two paths never diverge. For office files the post-strip `exiftool` pass is best-effort: exiftool cannot rewrite OOXML containers, so a failure there is logged (never silently swallowed) because the office library has already cleared the authoritative properties.

---

## Determinism

The corpus is seeded **once** per `generate_corpus()` call, then every document is authored in a fixed order (spec order, and within each entry indices `1..count`). The ordered sequence of Faker draws — and therefore the produced markdown — is identical for an identical spec and seed. Budget totals are computed arithmetically from their rows, and each document's `grant_amount` is drawn once and shared between the frontmatter and the body so they can never contradict each other. The same `seed` reproduces byte-identical golden markdown.

---

## Dependencies

### Python (optional `[corpus]` extra)

```bash
uv pip install "folio[corpus]"
```

The extra installs:

| Package | Used for |
|---------|----------|
| `faker` | synthetic content generation |
| `python-docx` | DOCX render + scan + metadata strip |
| `openpyxl` | XLSX render + scan + metadata strip |
| `pillow` | scanned-PDF image recombination |

### External system tools

These are **not** pip-installable and must be on PATH for the formats/steps that need them:

| Tool | Needed for |
|------|------------|
| `pandoc` | `pdf`, `pdf_scanned` rendering |
| `typst` | `pdf`, `pdf_scanned` rendering (PDF engine) |
| `pdftoppm` (poppler) | `pdf_scanned` rasterization |
| `pdftotext` (poppler) | extracting PDF text during the PII gate / `scan` |
| `exiftool` | stripping/verifying PDF and image metadata (required for those formats) |

On Debian/Ubuntu: `sudo apt install pandoc poppler-utils libimage-exiftool-perl` and install `typst` per its own instructions.

---

## Troubleshooting

**`pdf` / `pdf_scanned` formats skipped** — `pandoc` and/or `typst` are not on PATH. Install both; the golden markdown is still written. Run `folio corpus generate --dry-run` to see which renderers are available.

**Scanned PDF skipped even with pandoc + typst** — `pdftoppm` (poppler) or `Pillow` is missing.

**Gate fails with `unscannable` on a PDF** — the PII gate uses `pdftotext` (poppler) to read PDFs. If poppler is not installed, generated/scanned PDFs are flagged `unscannable`, which **fails the gate** even in non-strict mode. Install `poppler-utils`. (Note: an image-only `pdf_scanned` correctly extracts to empty text and passes — it has no embedded text.)

**`exiftool not available to strip metadata`** — stripping is mandatory for PDF/image artifacts; install `exiftool` or omit `pdf`/`pdf_scanned` from the spec.

**`Error: invalid corpus spec`** — the spec failed validation; the message lists every problem (unknown kind/format, `count < 1`, empty `funder`, etc.).

---

## Committed fixtures and the benchmark

`benchmark/corpus/` holds committed, generated fixtures (`golden/` markdown plus `rendered/` binaries). These fixtures feed the converter benchmark tracked under bead `folio-ax5`: the converters are run over the rendered artifacts and their markdown output is compared against the golden reference. Regenerate the fixtures with `folio corpus` (all required tools installed) and PII-gate them with `folio corpus scan ./benchmark/corpus/` before committing.

---

## Known limitations

- **OOXML zip-entry timestamps.** Core authoring properties are scrubbed, but a rendered `.docx`/`.xlsx` still retains a generation timestamp on its zip entries. This is tracked and considered low sensitivity (no name/author data).
- **Heavy documents.** The generator currently renders the **full** heading taxonomy from the profile, so `application` and `narrative` documents are large (the bundled narrative golden markdown is ~24 KB).
- **Line-oriented scanning.** The PII scanner matches within a single line; a name or pattern split across a newline boundary is not detected. Generated golden text keeps fields on single lines, so this only affects arbitrary external inputs to `scan`.
