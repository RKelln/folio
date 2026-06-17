# folio

Turn an arts organization's document archive into a searchable knowledge base that AI coding agents can use to write grants, answer questions, and understand organizational patterns.

**Three steps:** install → init → pipeline. No code changes — just YAML config.

## Prerequisites

- Python 3.10+
- `uv` or `pipx`
- A DeepSeek API key (required). OpenAI key (optional, for wiki embeddings).
- See [Installation](docs/installation.md) for full dependency setup.

## Quickstart

```bash
pipx install folio                            # or: uv tool install --editable .

mkdir my-org && cd my-org
folio init --guided                           # 6 questions, creates folio.yaml

# Copy your PDFs/DOCX/XLSX into archive/, then:

folio scan                                    # Preview: files, costs, time
folio pipeline --dry-run                      # Cost estimate
folio pipeline                                # Run all 8 stages (~$0.04/10 files)
```

## Org library structure

```
my-org/
├── folio.yaml       # Org config — funders, doc types, paths, LLM
├── .env             # API keys (DEEPSEEK_API_KEY, OPENAI_API_KEY, etc.)
├── archive/         # Raw source files (PDF, DOCX, XLSX)
├── markdown/        # Final LLM-rewritten output
├── wiki/            # Sage-wiki knowledge base (symlink)
└── .folio/          # Pipeline intermediates (hidden)
```

Run folio from the library directory — it auto-discovers `folio.yaml`.

## Commands

```bash
folio pipeline      # Run all 8 stages (with --dry-run for cost preview)
folio scan          # Scan archive, detect funders/years/types
folio init          # Guided setup or load a profile
folio skills        # Generate agent skills (opencode, claude, openclaw, hermes)
folio ingest        # Add a single new document
folio convert       # Convert PDF/DOCX/XLSX → markdown
folio clean         # Deterministic markdown cleanup
folio classify      # Quality scoring, tier assignment
folio rewrite       # LLM re-authoring with tiered prompts
folio canonicalize  # Version detection and dedup
folio prioritize    # Archival priority scoring
folio audit         # Wiki quality audit
folio guide         # Built-in agent reference
```

All commands support `--dry-run` and `--json`. Run `folio <cmd> --help` for details.

## Documentation

| Doc | Covers |
|-----|--------|
| [Getting Started](docs/getting-started.md) | Full onboarding walkthrough |
| [Installation](docs/installation.md) | Dependencies, API keys, converters |
| [Configuration](docs/config.md) | folio.yaml reference |
| [Pipeline Stages](docs/pipelines.md) | End-to-end pipeline reference |
| [Frontmatter](docs/frontmatter.md) | YAML frontmatter fields |
| [File Naming](docs/file-naming.md) | Filename convention |
| [Converters](docs/converters.md) | PDF/DOCX → markdown options |
| [Wiki Backends](docs/wiki-backends.md) | Wiki compilation |
| [Skills](docs/skills.md) | Agent skills architecture |

## FAQ

**What does it cost?** ~$0.004/file with DeepSeek flash. About $12 for a 1000-file archive with tiered processing.

**Why flat filenames?** `FUNDER__Year_Program__Type__Description.ext` is machine-parseable. The [file naming doc](docs/file-naming.md) explains why.

**My archive is a mess of nested folders.** Use the pipeline step by step — start with `folio convert`, then `folio clean`, then review before `folio rewrite`. Use `folio repack` for nested → flat migration.

## For AI agents

See [AGENTS.md](AGENTS.md) for coding conventions and module architecture. See [docs/getting-started.md](docs/getting-started.md) if you're helping an org set up folio.
