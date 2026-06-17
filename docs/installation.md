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

At least one converter must be installed. **docling is the default and recommended.**

| Converter | Install | Notes |
|-----------|---------|-------|
| **docling** (default) | `uv pip install docling` | Recommended. Best quality. |
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

## Platform-specific quick install

### Ubuntu / Debian

```bash
# Python tooling
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: sudo apt install pipx && pipx ensurepath

# folio
uv tool install folio

# Converter (docling)
uv pip install docling

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

# Converter (docling)
uv pip install docling

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
uv run python -c "import docling; print('ok')" 2>/dev/null      # converter
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
