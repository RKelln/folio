# folio

Turn an arts organization's document archive into a searchable knowledge base that AI coding agents can use to write grants, answer questions, and understand organizational patterns.

## What it does

- Converts PDFs, DOCX, and XLSX to clean markdown
- Strips form chrome, fixes PDF corruption, normalizes headings
- Classifies documents by quality, assigns processing tiers
- LLM re-authors documents into clean archival markdown with YAML frontmatter
- Compiles a wiki (via sage-wiki) with cross-document concept articles
- Generates agent skills that teach AI assistants how to search and draft from the archive

## Quickstart

```bash
# Install (from PyPI or local checkout)
pipx install folio
# or from local: cd folio && uv tool install --editable .

# Create a new org library
mkdir my-org-library && cd my-org-library
folio init --guided

# Preview what will happen
folio pipeline --dry-run

# Run the pipeline
folio pipeline
```

## Org library structure

Each organization gets its own directory (often its own git repo):

```
my-org-library/
├── folio.yaml       # Org config — funders, doc types, paths, LLM settings
├── .env             # API keys (DEEPSEEK_API_KEY, etc.)
├── archive/         # Raw source files (PDF, DOCX, XLSX)
├── markdown/        # Final LLM-rewritten markdown
├── wiki/            # Sage-wiki searchable knowledge base
└── .folio/          # Pipeline intermediates (hidden)
```

Run folio from the library directory — it auto-discovers `folio.yaml` and
resolves all paths relative to the config location.

## Available commands

```bash
folio               # Show available commands
folio pipeline      # Run all or selected stages
folio scan          # Scan archive, detect funders/years/types
folio init          # Guided setup or load a profile
folio skills        # Generate agent skills for opencode/claude/etc
folio classify      # Classify a directory of markdown files
folio rewrite       # LLM re-author a directory of markdown files
folio prioritize    # Assign archival priority scores
folio ingest        # One-off document ingestion
folio audit         # Wiki quality audit
folio clean          # Deterministic markdown cleanup
folio canonicalize   # Version detection and dedup
```

Run `folio <command> --help` for details on each subcommand.

## For AI agents

See `AGENTS.md` for conventions, how to customize folio for a new organization, and how to generate skills for different assistant platforms.
