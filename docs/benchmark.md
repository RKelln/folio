# Converter Benchmark

`folio convert-bench` is an **offline, deterministic** harness that runs every available document converter over the committed synthetic corpus, scores each Markdown output against a hand-authored golden reference, and prints a side-by-side scorecard. It exists to answer one question with data instead of guesswork: *which converter should this org use?*

It feeds the [Choosing a Converter](converters.md#choosing-a-converter) guidance in the converters doc.

## Why it's trustworthy

- **No network, no LLMs.** Scoring uses the Python standard library only (`difflib` + `re`). Quality scores are identical on every run; only wall-clock timings vary.
- **Golden references.** Each corpus document has an authored golden `.md`; converter output is compared against it, not against another converter.
- **Free by default.** The default line-up benchmarks only the local, free converters (`liteparse`, `docling`, `pandoc`). The paid hosted converter (`datalab`) and the GPU converter (`marker`) ship disabled.

## Quickstart

Run from an org library directory (the corpus lives at `benchmark/corpus/` in the folio repo):

```bash
folio convert-bench                 # Score all enabled converters, print the scorecard
folio convert-bench --json          # Machine-readable results
folio convert-bench --dry-run       # Preview the plan (cases + converter availability), run nothing
folio convert-bench --dry-run --json
```

### Common options

| Flag | Effect |
|------|--------|
| `--spec PATH` | Use a custom `bench-spec.yaml` instead of the bundled default |
| `--corpus DIR` | Override the corpus directory from the spec |
| `--converters a,b` | Run only the named converters (comma-separated) |
| `--out FILE.md` | Also write a full Markdown comparison report to `FILE.md` |
| `--dry-run`, `-n` | Preview the plan without converting anything |
| `--json` | Emit JSON (the dry-run plan, or the full results) |
| `--version` | Print the version and exit |

```bash
folio convert-bench --converters liteparse,pandoc      # Just these two
folio convert-bench --corpus ./benchmark/corpus        # Point at a corpus elsewhere
folio convert-bench --spec ./my-bench-spec.yaml        # Custom weights/converters
folio convert-bench --out docs/converter-report.md     # Write the Markdown report too
```

`--converters` opts converters **in even if the spec ships them disabled** — naming `datalab` runs it (you still need its API key); converters you do *not* name are dropped from the run. An unknown converter name is an error (exit code 1).

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | The benchmark ran and **at least one converter produced a scored document**. |
| `1` | The spec was invalid, no benchmark cases were found, an unknown converter was requested, or **no converter produced any scored output** (every converter was unavailable or failed on all of its supported documents). |

## Corpus layout

The committed synthetic corpus is produced by [`folio corpus`](corpus.md) and is PII-free. The benchmark pairs each rendered input with its golden reference by slug:

```
benchmark/corpus/
├── golden/
│   └── <slug>.md                 # authored golden Markdown reference
└── rendered/
    ├── <slug>.pdf                # converter inputs derived from the golden
    ├── <slug>.docx
    ├── <slug>.xlsx
    └── <slug>.scanned.pdf        # image-only PDF → format "pdf_scanned" (OCR path)
```

`<slug>` is `<funder>-<kind>-<NN>` where `<kind>` may contain underscores (e.g. `oac-activity_list-01`). A `.scanned.pdf` input is classified as format `pdf_scanned`. Rendered files with an unknown extension, a malformed slug, or a missing golden reference are skipped with a warning (the run does not fail).

## Scoring

Each converter's Markdown output is scored against its golden reference across four categories, each a deterministic value in `[0, 1]` (`1.0` = perfect recovery). YAML frontmatter is stripped from both sides before scoring, since converters never reproduce it.

| Category | Default weight | What it measures |
|----------|----------------|------------------|
| `text` | 0.40 | Body-text fidelity — `difflib.SequenceMatcher` ratio over normalized, whitespace-tokenized text |
| `tables` | 0.25 | GitHub pipe-table recovery — cell-text F1 blended with row-count recovery |
| `structure` | 0.25 | Heading reading-order similarity blended with list-item recovery |
| `links_images` | 0.10 | Recall of Markdown links/images present in the golden |

The four scores are combined into a single **Overall** weighted score using the weights above (normalized internally, so they need not sum to 1). A converter **passes** when its mean Overall score is at least the spec's `pass_threshold` (default `0.7`).

`Time/pg(s)` is mean wall-clock convert time per estimated page (the page estimate is a deterministic word-count heuristic over the golden, so cost figures are reproducible). `Cost/pg` comes from the spec's `cost_per_page` for that converter.

## Configuration: `bench-spec.yaml`

The benchmark uses a **standalone** spec — separate from `folio.yaml` / `ProjectConfig`. The bundled, fully-commented default is at `src/folio/templates/bench/bench-spec.yaml`. Copy it, edit it, and pass it with `--spec`; no Python changes are needed.

```yaml
corpus_dir: benchmark/corpus     # root of the committed corpus
golden_subdir: golden            # holds the golden <slug>.md references
rendered_subdir: rendered        # holds the rendered converter inputs
pass_threshold: 0.7              # mean Overall score (0..1) needed to "pass"

weights:                         # need not sum to 1 — normalized internally
  text: 0.40
  tables: 0.25
  structure: 0.25
  links_images: 0.10

converters:
  - { name: liteparse, enabled: true,  offline: true,  cost_per_page: 0.0 }
  - { name: docling,   enabled: true,  offline: true,  cost_per_page: 0.0 }
  - { name: pandoc,    enabled: true,  offline: true,  cost_per_page: 0.0 }
  - { name: datalab,   enabled: false, offline: false, cost_per_page: 0.003 }
  - { name: marker,    enabled: false, offline: true,  cost_per_page: 0.0 }
```

## Example scorecard

> **Illustrative only.** The numbers below are example output from one machine, not authoritative benchmark results. Run `folio convert-bench` yourself for current figures.

```
Converter  Overall  Quality  Scored  Text   Tables  Struct  Links  Time/pg(s)  Cost/pg  Offline  Pass
liteparse  0.853    0.853    10/10   0.816  0.807   0.900   1.000  0.973       0.0000   yes      PASS
docling    0.750    0.750    10/10   0.821  0.894   0.393   1.000  5.128       0.0000   yes      PASS
pandoc     0.292    0.974    3/10    0.936  1.000   1.000   1.000  0.100       0.0000   yes      FAIL
```

How to read this sample:

- **`Overall` is coverage-weighted** — documents a converter can't read (or fails on) count as zero, so `Overall = Quality × (Scored ÷ attempted)`. This makes `Overall` directly comparable across converters as a *whole-corpus capability* score, and it drives the `Pass` flag and the recommendation.
- **`Quality`** is the mean over only the documents the converter actually scored — "how good is it *when* it can read the file?" Read it together with `Scored`.
- **liteparse** is the strongest *balanced* all-format offline option (`Overall` 0.853, `10/10`) and is the recommended default here.
- **pandoc** has the highest `Quality` (0.974 — excellent on DOCX) but it **cannot read PDF or XLSX**, so it only covers 3/10 docs and its coverage-weighted `Overall` drops to 0.292 (**FAIL** as a general-purpose default). It is still an excellent choice *specifically for DOCX-heavy* archives — exactly the kind of signal a per-format router (the cascade converter) should use.
- **docling** has the best `Tables` score but weaker `Structure`, and is much slower because of its OCR/structure models.

## Important caveats

1. **`Overall` vs `Quality` — know which you need.** `Overall` is coverage-weighted (unsupported/failed formats count as zero), so it answers *"how good is this converter across the whole corpus?"* and is comparable across converters. `Quality` answers *"how good is it on the formats it can read?"* and must be read alongside `Scored` (`scored/attempted`). A converter like pandoc reads DOCX (and other markup/word-processor formats) but **not PDF or XLSX**, so it scores 3 of 10 documents: high `Quality`, low `Overall`. For per-format decisions, use the `Quality` column together with the **per-document-type breakdown** in the `--out` Markdown report.
2. **docling fetches OCR/structure models from the network on first run**, then runs offline thereafter. It is "offline after a one-time warmup," **not air-gapped on first use** — plan a warmup run before benchmarking in an air-gapped environment.
3. **`marker` is unavailable** (it is a GPU-dependent stub and will report as `unavailable`). **`datalab` is online and needs an API key** (`DATALAB_API_KEY`) and is disabled by default; opt in with `--converters datalab` (and expect per-page cost).

## See also

- [Converters](converters.md) — converter options and how to select one in `folio.yaml`
- [Synthetic Corpus](corpus.md) — how `folio corpus` builds the PII-free corpus this benchmark runs on
