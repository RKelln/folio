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
pipx install folio

# Guided setup
folio init --guided

# Preview what will happen
folio pipeline --dry-run

# Run the pipeline
folio pipeline
```

## For AI agents

See `AGENTS.md` for conventions, how to customize folio for a new organization, and how to generate skills for different assistant platforms.
