# Document Converters

folio converts source documents (PDF, DOCX, XLSX) to markdown before running the classification, cleaning, and LLM-rewrite pipeline stages. Convert is stage 2 in the pipeline (after scan).

## Converter Interface

All converters implement the `Converter` abstract base class defined in `src/folio/adapters/converters/base.py`:

```python
class Converter(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable converter name."""

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """File extensions this converter handles (e.g. {'.pdf', '.docx'})."""

    @abstractmethod
    def convert(self, source: Path) -> str | None:
        """Convert a file to markdown.

        Returns:
            Markdown string on success, None on failure.
        """
```

To add a new converter, subclass `Converter`, implement the three methods above, and register it in the factory at `src/folio/adapters/converters/__init__.py`.

---

## Available Converters

### 1. LiteParse (default)

LiteParse is an open-source, Rust-based document parser from LlamaIndex (https://developers.llamaindex.ai/liteparse/). It parses text with spatial layout and renders clean Markdown, running entirely on the local machine with no cloud calls, no LLMs, and no API keys. Built-in Tesseract OCR handles scanned documents. Its speed makes it the recommended default for bulk archive conversion.

| Property | Value |
|----------|-------|
| Class | `LiteParseConverter` |
| Supported extensions | `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.png`, `.jpg`, `.jpeg` |
| Pricing | Free (OSS) |
| Requires network | No (runs entirely offline) |

**Installation:**

```bash
uv add liteparse
```

Or with the optional dependency group:

```bash
uv pip install "folio[liteparse]"
```

**Configuration in folio.yaml:**

```yaml
converter:
  type: "liteparse"
```

For OCR of scanned documents in offline/air-gapped environments, set `TESSDATA_PREFIX` to a directory containing Tesseract `.traineddata` files.

---

### 2. Docling

Docling is an open-source document converter (Apache 2.0) originally from IBM Research. It handles PDF, DOCX, PPTX, and XLSX with high-quality output. A strong choice when you need Docling's table extraction.

| Property | Value |
|----------|-------|
| Class | `DoclingConverter` |
| Supported extensions | `.pdf`, `.docx`, `.pptx`, `.xlsx` |
| Pricing | Free (OSS, Apache 2.0) |
| Requires network | No (runs entirely offline) |

**Installation:**

```bash
uv add docling
```

Or with the optional dependency group:

```bash
uv pip install "folio[docling]"
```

**Configuration in folio.yaml:**

```yaml
converter:
  type: "docling"
```

---

### 3. Datalab

Proprietary IBM Datalab SDK. Highest quality conversion for grant forms, PDFs with tables, and complex layouts. Recommended for production archives that need the best possible fidelity.

| Property | Value |
|----------|-------|
| Class | `DatalabConverter` |
| Supported extensions | `.pdf`, `.docx`, `.xlsx`, `.doc`, `.xls` |
| Pricing | ~$0.02/page |
| Requires network | Yes |

**Installation:**

```bash
uv add datalab-python-sdk
```

Or with the optional dependency group:

```bash
uv pip install "folio[datalab]"
```

**Configuration in folio.yaml:**

```yaml
converter:
  type: "datalab"
  datalab:
    pipeline_id: "your-pipeline-id"
    api_key_env: "DATALAB_API_KEY"   # env var name containing the API key
```

Set your API key:

```bash
export DATALAB_API_KEY="your-key"
```

---

### 4. Marker

Open-source `marker-pdf` package. Runs entirely offline. Converts PDF to markdown with good table and layout handling.

| Property | Value |
|----------|-------|
| Class | `MarkerConverter` |
| Supported extensions | `.pdf` |
| Pricing | Free |
| Requires network | No |

**Installation:**

```bash
uv add marker-pdf
```

Or with the optional dependency group:

```bash
uv pip install "folio[marker]"
```

**Configuration in folio.yaml:**

```yaml
converter:
  type: "marker"
```

**Note:** Implementation is not yet complete. This converter is best for archives that contain only PDF files and need offline processing.

---

### 5. Pandoc

Universal document converter that shells out to the [`pandoc`](https://pandoc.org/) binary. Runs entirely offline with no network calls, API keys, or models, which makes it a reliable, fast baseline for the converter benchmark. Pandoc reads a wide range of markup and word-processor formats but does **not** read binary PDF or spreadsheet (XLSX) formats.

| Property | Value |
|----------|-------|
| Class | `PandocConverter` |
| Supported extensions | `.docx`, `.html`, `.htm`, `.odt`, `.epub`, `.rtf`, `.tex`, `.md`, `.markdown` |
| Pricing | Free |
| Requires network | No (runs entirely offline) |

**Installation:**

Pandoc is a system binary, not a Python package — install it from your package manager and ensure it is on `PATH`:

```bash
apt install pandoc        # Debian/Ubuntu
brew install pandoc       # macOS
```

**Configuration in folio.yaml:**

```yaml
converter:
  type: "pandoc"
```

Output is GitHub-flavored Markdown (`gfm`). Best for archives of DOCX/HTML/ODT/EPUB documents that need fast, free, fully-offline conversion. For PDF or XLSX sources, use LiteParse, Docling, or Datalab instead.

---

### 6. Null (skip conversion)

Use when source documents are already in markdown format. The pipeline starts at the clean stage, bypassing conversion entirely.

**Configuration in folio.yaml:**

```yaml
converter:
  type: "null"
```

No additional dependencies required. No API key needed.

---

## Selecting a Converter

### Comparison

| Converter | PDF | DOCX | XLSX | PPTX | Images | Pricing | Offline | Status |
|-----------|-----|------|------|------|--------|---------|---------|--------|
| LiteParse | Yes | Yes  | Yes  | Yes  | Yes    | Free   | Yes | Ready |
| Docling  | Yes | Yes  | Yes  | Yes  | No     | Free   | Yes | Ready |
| Datalab  | Yes | Yes  | Yes  | Yes  | Yes    | ~$0.02/page | No  | Ready |
| Pandoc   | No  | Yes  | No   | No   | No     | Free   | Yes | Ready |
| Marker   | Yes | No   | No   | No   | No     | Free   | Yes | Planned |
| Null     | N/A | N/A  | N/A  | N/A  | N/A    | Free   | N/A | Ready |

### Choosing a Converter

- **Most archives** -> LiteParse (default, fast, local, no API key, multi-format)
- **Need Docling's table extraction** -> Docling
- **Maximum fidelity for complex grant forms** -> Datalab
- **DOCX/HTML/ODT/EPUB only, want a fast free offline baseline** -> Pandoc
- **Documents already in markdown** -> Null

#### Benchmark-driven selection

Don't guess — measure. [`folio convert-bench`](benchmark.md) runs every available converter over the committed synthetic corpus and scores each output against a golden reference, fully offline and deterministically. Run it and let the scorecard drive the choice:

```bash
folio convert-bench            # print the scorecard
folio convert-bench --out docs/converter-report.md   # also write a full comparison report
```

> **Illustrative example only** — example output from one machine, **not** authoritative results. Run `folio convert-bench` yourself for current numbers.

```
Converter  Overall  Quality  Scored  Text   Tables  Struct  Links  Time/pg(s)  Cost/pg  Offline  Pass
liteparse  0.853    0.853    10/10   0.816  0.807   0.900   1.000  0.973       0.0000   yes      PASS
docling    0.750    0.750    10/10   0.821  0.894   0.393   1.000  5.128       0.0000   yes      PASS
pandoc     0.292    0.974    3/10    0.936  1.000   1.000   1.000  0.100       0.0000   yes      FAIL
```

**Read it carefully:** `Overall` is **coverage-weighted** (formats a converter can't read count as zero, so `Overall = Quality × Scored/attempted`) and is comparable across converters as a whole-corpus score; `Quality` is the mean over only the docs it could read (`Scored` = `scored/attempted`). In this sample **liteparse** is the strongest balanced all-format offline option and the recommended default. **pandoc** has the best `Quality` (0.974 on DOCX) but cannot read PDF/XLSX, so it covers only 3/10 and its `Overall` is 0.292 (**FAIL** as a general-purpose default) — it remains an excellent pick *specifically for DOCX*. **docling** has strong tables but weaker structure and is much slower (OCR). See [the benchmark doc](benchmark.md) for scoring categories, weights, and caveats (docling fetches OCR models on first run, `marker` is GPU-only, `datalab` is online + paid).


### Configuration in folio.yaml

Set the converter type under the `converter:` section:

```yaml
converter:
  type: "liteparse"   # liteparse | docling | datalab | pandoc | marker | null
```

The default is `liteparse`. For null converter, no other fields are needed. For datalab, provide a `pipeline_id` and set the `DATALAB_API_KEY` environment variable.

### Skipping Conversion Entirely

Set `converter.type: "null"` in `folio.yaml`. The pipeline will treat all files in the archive as pre-converted markdown and begin at the clean stage.

---

## Implementation Notes

### Converter Factory

`get_converter(config)` in `src/folio/adapters/converters/__init__.py` receives the application config and returns the correct `Converter` instance. The factory reads `config.converter.type` (defaulting to `"liteparse"`) and dispatches to the matching class:

- `"liteparse"` -> `LiteParseConverter()`
- `"docling"` -> `DoclingConverter()`
- `"datalab"` -> `DatalabConverter(pipeline_id)`
- `"pandoc"` -> `PandocConverter()`
- `"marker"` -> raises `NotImplementedError` (planned)
- anything else -> raises `ValueError`

### Optional Dependencies

Converter packages are declared as optional dependencies in `pyproject.toml` under `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
liteparse = ["liteparse"]
datalab = ["datalab-python-sdk"]
marker = ["marker-pdf"]
docling = ["docling"]
```

This avoids forcing all users to install every converter dependency. Install only what you need.

### Adding a New Converter

1. Create a new file in `src/folio/adapters/converters/` (e.g. `myconv.py`)
2. Subclass `Converter` and implement `name`, `supported_extensions`, and `convert()`
3. Import the class in `src/folio/adapters/converters/__init__.py`
4. Add a branch in `get_converter()` to return your class for its type string
5. Add the optional dependency to `pyproject.toml`
6. Document the converter in this file
