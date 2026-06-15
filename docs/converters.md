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

### 1. Datalab (default)

Proprietary IBM Datalab SDK. Highest quality conversion for grant forms, PDFs with tables, and complex layouts. Recommended for production archives.

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

### 2. Marker

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

### 3. Docling

IBM Docling, open-source. Supports multiple document formats including PDF, DOCX, and PPTX. Good balance of quality and format coverage without proprietary costs.

| Property | Value |
|----------|-------|
| Class | `DoclingConverter` |
| Supported extensions | `.pdf`, `.docx`, `.pptx` |
| Pricing | Free |
| Requires network | No |

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

**Note:** Implementation is not yet complete. Best for multi-format archives in an open-source pipeline.

---

### 4. Null (skip conversion)

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
| Datalab  | Yes | Yes  | Yes  | Yes  | Yes    | ~$0.02/page | No  | Ready |
| Marker   | Yes | No   | No   | No   | No     | Free   | Yes | Planned |
| Docling  | Yes | Yes  | No   | Yes  | No     | Free   | Yes | Planned |
| Null     | N/A | N/A  | N/A  | N/A  | N/A    | Free   | N/A | Ready |

### Choosing a Converter

- **Large archive with mixed formats, production use** -> Datalab
- **PDF-only archive, offline or cost-sensitive** -> Marker (when implemented)
- **Multi-format archive, open-source pipeline** -> Docling (when implemented)
- **Documents already in markdown** -> Null

### Configuration in folio.yaml

Set the converter type under the `converter:` section:

```yaml
converter:
  type: "datalab"   # datalab | marker | docling | null
```

The default is `datalab`. For null converter, no other fields are needed. For datalab, provide a `pipeline_id` and set the `DATALAB_API_KEY` environment variable.

### Skipping Conversion Entirely

Set `converter.type: "null"` in `folio.yaml`. The pipeline will treat all files in the archive as pre-converted markdown and begin at the clean stage.

---

## Implementation Notes

### Converter Factory

`get_converter(config)` in `src/folio/adapters/converters/__init__.py` receives the application config and returns the correct `Converter` instance. The factory reads `config.converter.type` (defaulting to `"datalab"`) and dispatches to the matching class:

- `"datalab"` -> `DatalabConverter(pipeline_id)`
- `"marker"` -> raises `NotImplementedError` (planned)
- `"docling"` -> raises `NotImplementedError` (planned)
- `"pandoc"` -> raises `NotImplementedError` (planned)
- anything else -> raises `ValueError`

### Optional Dependencies

Converter packages are declared as optional dependencies in `pyproject.toml` under `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
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
