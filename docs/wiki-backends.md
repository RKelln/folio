# Wiki Backends

folio supports pluggable wiki compilation backends. Each backend implements the
`WikiBackend` interface and is selected via the `wiki.type` field in `folio.yaml`.

---

## Interface: `WikiBackend`

All wiki backends inherit from `WikiBackend` (`src/folio/adapters/wiki/base.py:7`)
and must implement eleven methods:

### `init(project_dir: Path, config: dict, source_dir: Path | None = None) -> None`

Initialize a new wiki project on disk. Creates the project directory, writes a
`config.yaml` file, and sets up the `raw/` directory for incoming documents.

- **project_dir** — absolute path to the wiki project root (typically `./.folio/sage-wiki/`)
- **config** — a dict of wiki-specific configuration (e.g. pack name)
- **source_dir** — optional path to markdown source files (defaults to None)

### `add_documents(source_paths: list[Path]) -> None`

Copy markdown documents into the wiki's `raw/` directory. Skips files that
already exist (keyed by filename).

- **source_paths** — list of paths to `.md` files produced by the rewriter stage

### `compile() -> None`

Run wiki compilation. This step may:
- Extract concepts and keywords from documents
- Generate summaries and cross-references
- Build search indexes

### `search(query: str) -> str`

Full-text search against the compiled wiki. Returns matching document excerpts
as a string.

- **query** — free-text search string

### `query(question: str) -> str`

Ask a natural-language question and receive a synthesized answer drawn from
wiki content.

- **question** — natural-language question string

### `status() -> str`

Return wiki project status information (article count, last compile time, etc.)
as a plain-text string.

### `doctor() -> str`

Run diagnostic checks on the wiki project (config validity, file structure,
symlink health) and return a report.

### `lint(pass_name: str | None = None) -> str`

Run linting rules against wiki content. Optionally filter by pass name.

### `coverage() -> str`

Report concept coverage statistics — which documents have concepts extracted,
which are missing, and coverage ratio.

### `diff(since: str | None = None) -> str`

Show what changed in the wiki since the last compile or a given time.

### `verify(all_files: bool = False, since: str | None = None, limit: int | None = None) -> str`

Run integrity verification on wiki articles. Checks for broken links, missing
concepts, and structural issues.

- **all_files** — verify all files, not just changed ones
- **since** — only check files changed since this date
- **limit** — maximum number of files to check

---

## Available Backends

### Sage Wiki (default)

The default backend. Uses the `sage-wiki` Go binary to build a local,
markdown-native, offline searchable knowledge base. No server required.

#### What it is

Sage Wiki is the primary wiki backend. It compiles a directory of markdown
documents into a structured, searchable knowledge base with concept extraction,
cross-referencing, and question answering.

#### Installation

The `sage-wiki` binary must be on your `PATH`. The backend checks availability
at construction time and raises `RuntimeError` if not found.

If you do not need wiki functionality, configure `wiki.type: "null"` instead.

#### Configuration

```yaml
# folio.yaml
wiki:
  type: "sage-wiki"
  sage_wiki:
    binary_path: "sage-wiki"   # path or name on PATH
    pack: "arts-org"           # pack profile controlling extraction behavior
```

| Key | Default | Description |
|-----|---------|-------------|
| `wiki.type` | `"sage-wiki"` | Backend selection |
| `wiki.sage_wiki.binary_path` | `"sage-wiki"` | Path to the sage-wiki Go binary |
| `wiki.sage_wiki.pack` | `"arts-org"` | Pack profile for concept extraction |

#### How it works

1. **`init()`** creates the wiki project directory under `.folio/sage-wiki/`, writes `config.yaml` (with pack, LLM settings, and embed config), and creates the `raw/` directory.

2. **Pack installation** — The pipeline automatically runs `sage-wiki pack install <templates/packs/arts-org>` followed by `sage-wiki pack apply arts-org --mode merge`. The pack is bundled at `src/folio/templates/packs/arts-org/`. It ships with 23 entity types, 19 relation types, and 6 prompt templates (v1.1). The install step copies the pack into sage-wiki's local store; the apply step merges it into the project configuration. Both steps are skipped if `sage-wiki` is not on `PATH`.

3. **`add_documents()`** creates a symlink `raw/ → ../markdown/` inside the wiki project, so rewritten files are available without copying. Duplicate filenames are skipped.

4. **`compile()`** invokes `sage-wiki compile` as a subprocess with a 1-hour timeout, after ensuring the API key env var is set. This reads documents from `raw/`, extracts concepts, and writes structured output. After compile, a root `wiki/` symlink is created pointing to `.folio/sage-wiki/wiki/`.

5. **`search(query)`** runs `sage-wiki search <query>` and returns stdout.

6. **`query(question)`** runs `sage-wiki query <question>` and returns the synthesized answer from stdout.

7. **`status()`** runs `sage-wiki status` and returns project health information.

8. **`doctor()`** runs `sage-wiki doctor` for diagnostic checks.

9. **`lint(pass_name)`** runs `sage-wiki lint` with optional pass filter for content quality rules.

10. **`coverage()`** runs `sage-wiki coverage` to report concept extraction coverage.

11. **`diff(since)`** runs `sage-wiki diff` to show what changed since last compile.

12. **`verify(all_files, since, limit)`** runs `sage-wiki verify` for integrity checks on articles.

On subprocess failure, the backend logs the error and returns an empty string.

#### Query language

Sage Wiki accepts natural-language questions via `query()` and free-text keyword
searches via `search()`. The `pack` profile (e.g. `arts-org`) tunes extraction
and answering behavior for the domain.

#### Output structure

```
.folio/sage-wiki/
├── config.yaml          # pack profile, LLM config, and settings
├── raw/ -> ../markdown/  # symlink to markdown/ (no file copying)
└── wiki/                # compiled output (concepts, indexes)
    └── concepts/        # extracted concepts, one .md per concept
```

A root `wiki/` symlink is created pointing to `.folio/sage-wiki/wiki/` for convenient access to compiled output.

#### Best for

- Local knowledge bases that agents can search for grant-writing context
- Offline environments where no server is acceptable
- Organizations that want semantic search and Q&A over their archive

---

### Null Backend

No-op backend. All wiki operations return placeholder results or do nothing.
Use this when you only want the markdown pipeline output — no searchable wiki.

#### Configuration

```yaml
# folio.yaml
wiki:
  type: "null"
```

#### Behavior

| Method | Result |
|--------|--------|
| `init()` | No-op |
| `add_documents()` | No-op |
| `compile()` | No-op |
| `search()` | Returns `"Wiki not configured. ..."` |
| `query()` | Returns `"Wiki not configured. ..."` |

#### When to use

- You only need the markdown pipeline output (`rewrite_md/*.md`)
- You plan to use a different search system entirely
- You are running in CI or testing and do not need wiki compilation

The pipeline still produces `rewrite_md/*.md` files regardless of wiki backend.

---

## How Agents Use the Wiki

### Searching

Agents search the wiki to find relevant past applications, reports, and budgets
when writing new grants. Run `folio audit` to check wiki quality (completeness,
missing concepts, stale content).

### Querying

Agents call `sage-wiki query "What was our 2024 operating budget?"` to get
synthesized answers from the compiled knowledge base. This is the primary
interface for extracting structured information without reading raw documents.

### Grant writing workflow

1. Agent receives a grant-writing task
2. Agent queries the wiki for relevant past applications and budget figures
3. Agent searches for specific funder patterns and narrative styles
4. Agent uses retrieved context to draft the new application

---

## Implementation Notes

### Backend factory

`get_wiki_backend(config)` in `src/folio/adapters/wiki/__init__.py:13` reads
`config.wiki.type` and returns the appropriate backend instance:

| `wiki.type` | Backend class |
|-------------|---------------|
| `"sage-wiki"` | `SageWikiBackend` |
| `"null"` or absent | `NullWikiBackend` |

If `config` is `None`, a `NullWikiBackend` is returned.

### Adding a new backend

1. Create a new file in `src/folio/adapters/wiki/`
2. Subclass `WikiBackend` and implement all five abstract methods
3. Register it in `get_wiki_backend()` by adding a branch for the new type
4. Add default configuration under `wiki:` in `src/folio/config/defaults.yaml`

### Subprocess management

`SageWikiBackend` manages the `sage-wiki` binary through `subprocess.run()`:

- **`compile()`** uses `timeout=3600` (1 hour) and `check=True` — failures
  raise `CalledProcessError`
- **`search()`** and **`query()`** catch `CalledProcessError`, log it, and
  return an empty string rather than raising
- All calls use `capture_output=True` and `text=True` for string output
- The `cwd` is set to the wiki project directory so the binary finds its
  `config.yaml` and `raw/` directory
