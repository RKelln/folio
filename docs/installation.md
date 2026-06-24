# Installation

Everything needed to install folio and its dependencies.

## Core

| Requirement | Install |
|-------------|---------|
| Python 3.10+ | `python.org` or system package manager |
| `uv` (recommended) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `pipx` (alternative) | `python -m pip install --user pipx` |
| folio | `uv tool install folio` or `pipx install folio` |

Local dev install: `cd folio && uv tool install --editable .`

Verify: `folio --version`

## Upgrading

**If installed via `uv tool install git+...`:**

```bash
uv tool install --reinstall git+https://github.com/RKelln/folio@v0.2.0
```

Replace `v0.2.0` with the desired version tag. Run `folio --version` to confirm.

**If installed from a clone + editable (`uv tool install --editable .`):**

```bash
cd folio
git pull
# or for a specific version:
git fetch --tags && git checkout v0.2.0
```

No reinstall needed — `--editable` picks up changes immediately. Run `folio --version` to confirm.

## API keys

Set in `.env` in your org library directory (folio auto-loads it):

| Variable | Required | Purpose | Get it from |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes* | LLM calls (openai_compatible provider default) | [platform.openai.com](https://platform.openai.com) |
| `DEEPSEEK_API_KEY` | Yes* | LLM calls (when using DeepSeek) | [platform.deepseek.com](https://platform.deepseek.com) |
| `GROQ_API_KEY` | Yes* | LLM calls (when using Groq) | [console.groq.com](https://console.groq.com) |
| `DATALAB_API_KEY` | Optional | Datalab converter (legacy) | [datalab.to](https://datalab.to) |

*At least one LLM API key is required. folio works with any OpenAI-compatible provider — set the matching env var and configure `llm.base_url`, `llm.api_key_env`, and `llm.models` in `folio.yaml`.

Example pricing (budget tier): ~$0.14/M input tokens. A typical 1000-file archive costs ~$4-12 in LLM fees.

## Converters

At least one converter must be installed. **liteparse is the default and recommended.**

| Converter | Install | Notes |
|-----------|---------|-------|
| **liteparse** (default) | `uv pip install liteparse` | Recommended. Fast local Rust parser, no API key. |
| docling | `uv pip install docling` | OSS, strong table extraction. |
| marker-pdf | `uv pip install marker-pdf` | Good quality, fast. |
| datalab | `pip install datalab-python-sdk` | Cloud API. Needs `DATALAB_API_KEY`. |
| pandoc | `sudo apt install pandoc` (Linux) or `brew install pandoc` (macOS) | Fallback. Free. |

See [docs/converters.md](converters.md) for detailed comparison and configuration.

## Wiki (optional)

[sage-wiki](https://github.com/xoai/sage-wiki) compiles markdown into a searchable knowledge base with concept articles, ontology, and hybrid BM25 + vector search.

```bash
go install github.com/xoai/sage-wiki@latest
```

Verify: `sage-wiki --version` (requires `go` on PATH).

If you skip the wiki, set `wiki.type: "null"` in `folio.yaml` for markdown-only mode. See [docs/wiki-backends.md](wiki-backends.md).

## Agentmap (optional)

Agentmap generates section-level navigation blocks (`<!-- AGENT:NAV -->`) in markdown files for fast agent lookup.

```bash
go install github.com/xoai/agentmap@latest
```

Verify: `agentmap --version`.

Set `agentmap.enabled: true` and `agentmap.binary: "agentmap"` in `folio.yaml` to enable. Setting `agentmap.enabled: false` disables it entirely.

## Synthetic corpus (optional)

`folio corpus` generates a PII-free synthetic benchmark corpus. Install the optional Python extra:

```bash
uv pip install "folio[corpus]"
```

This installs `faker`, `python-docx`, `openpyxl`, and `pillow`.

PDF rendering, OCR rasterization, and metadata stripping additionally require external system tools (not pip-installable):

| Tool | Needed for | Install (Debian/Ubuntu) |
|------|------------|-------------------------|
| `pandoc` | `pdf` / `pdf_scanned` rendering | `sudo apt install pandoc` |
| `typst` | `pdf` / `pdf_scanned` PDF engine | see [typst.app](https://typst.app) install docs |
| `poppler` (`pdftoppm`, `pdftotext`) | scanned-PDF rasterization + PDF text extraction for the PII gate | `sudo apt install poppler-utils` |
| `exiftool` | stripping/verifying PDF and image metadata | `sudo apt install libimage-exiftool-perl` |

Formats whose tools are missing are skipped with a warning (the golden markdown is always written). See [docs/corpus.md](corpus.md).

## Platform-specific quick install

### Ubuntu / Debian

```bash
# Python tooling
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: sudo apt install pipx && pipx ensurepath

# folio
uv tool install folio

# Converter (liteparse)
uv pip install liteparse

# Wiki (needs Go)
sudo snap install go --classic    # or: sudo apt install golang-go
go install github.com/xoai/sage-wiki@latest

# Agentmap
go install github.com/xoai/agentmap@latest

# Fallback converter
sudo apt install pandoc
```

### macOS

```bash
# Python tooling
brew install uv
# or: brew install pipx && pipx ensurepath

# folio
uv tool install folio

# Converter (liteparse)
uv pip install liteparse

# Wiki (needs Go)
brew install go
go install github.com/xoai/sage-wiki@latest

# Agentmap
go install github.com/xoai/agentmap@latest

# Fallback converter
brew install pandoc
```

## Verify installation

```bash
folio --version                                                 # folio installed
sage-wiki --version                                             # wiki backend (if installed)
uv run python -c "import liteparse; print('ok')" 2>/dev/null     # converter
```

Then in your org library directory:

```bash
folio pipeline --dry-run    # Should show cost estimates and file counts
folio scan                  # Should enumerate your archive/ files
```

## Troubleshooting

**`folio: command not found`** — The `~/.local/bin` or uv tool bin directory isn't on PATH. Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` or `~/.zshrc`.

**`sage-wiki: command not found`** — Go binaries go to `~/go/bin/`. Add `export PATH="$HOME/go/bin:$PATH"` to your shell config, or set `wiki.type: "null"` in folio.yaml.

**PDF conversion fails** — Try an alternative converter (`marker-pdf` or `pandoc`). Some PDFs are scanned images — these won't convert cleanly with any tool.

**`API key not set`** — Create a `.env` file in your org library directory with your provider's API key (e.g. `OPENAI_API_KEY=sk-...` or `DEEPSEEK_API_KEY=sk-...`). The `.env` must be in the same directory as `folio.yaml`.
