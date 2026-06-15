# AGENTS.md — Agent Instructions for folio

## Purpose

folio builds a knowledge base from an organization's document archive (grant applications, reports, budgets, exhibition records) that AI coding agents can use to write grants, answer questions, and understand organizational patterns. Designed for arts organizations but works for any document-heavy non-profit.

**If you are helping a new organization set up folio, start with README.md** — it has the quickstart. This file covers how to build and modify tooling in this repo.

## Rules for All Code

### 1. Configuration drives behavior, not hardcoding

Every pattern, threshold, funder name, and classification rule must live in a config file. The code reads config. An agent customizing for a new org should never need to edit Python code — only YAML or markdown.

### 2. Every tool must be self-documenting

- `--help` must explain what the tool does and show realistic usage examples
- Docstrings must cover purpose, inputs, outputs, and side effects
- Config files must have comments explaining every option

### 3. Make tools discoverable by agents

A new agent dropped into this repo should be able to:
- Run `folio --help` to see available subcommands
- Run `folio <command> --help` to understand what each does
- Open the relevant config file to see what's configurable
- Run with `--dry-run` to preview without side effects

### 4. Every tool must be runnable by agents

- Use `uv run folio <command>` or `folio <command>` (if installed via pipx)
- All dependencies in `pyproject.toml`
- Every tool must have `--dry-run` mode
- Every tool must have `--json` output mode for structured data exchange
- Avoid interactive prompts; everything must work non-interactively via CLI flags
- Exit codes: 0 on success, non-zero on failure
- Use `tqdm` for progress bars

### 5. Design for composition

Tools work as stages in a pipeline:
- One tool's `--json` output can be another tool's `--manifest` input
- Checkpoint state is always a JSON file (not pickle, not sqlite — agents can read JSON)

### 6. Per-org customizations go in config, not code

When an agent needs to adapt folio for a different organization:
- Funder names and abbreviations → `folio.yaml` funders section
- Year range patterns → `folio.yaml`
- Document type vocabulary → `folio.yaml`
- Form chrome and draft marker patterns → classification config
- Classification thresholds → classification config
- Heading taxonomies → headings config
- Skill prompts and rubrics → `skills/core/`

### 7. Keep code files focused

Each module does one job well:

| Module | Job |
|--------|-----|
| `core/cleaner.py` | Deterministic markdown cleanup |
| `core/classifier.py` | File quality scoring and tier assignment |
| `core/rewriter.py` | LLM re-authoring with tiered prompts |
| `core/prioritizer.py` | Archival priority scoring |
| `core/canonicalizer.py` | Version detection and dedup |
| `core/ingester.py` | One-off document ingestion |
| `core/auditor.py` | Wiki quality audit |
| `core/scanner.py` | Archive scanning and funder detection |
| `core/frontmatter.py` | YAML frontmatter parsing, generation, validation |
| `core/manifest.py` | Pipeline manifest read/write |
| `core/errors.py` | Shared error/status types |
| `adapters/converters/` | PDF/DOCX → Markdown converters |
| `adapters/wiki/` | Wiki backend integrations |
| `adapters/llm/` | LLM provider abstraction |
| `adapters/sources/` | Document source connectors |
| `config/` | Config loading and Pydantic validation |
| `cli/` | CLI entry points (thin wrappers around core) |

### 8. Use standard libraries where possible

Prefer the existing dependencies (pyyaml, openai, python-dotenv, tqdm) over new ones unless there's a strong reason.

## Project Structure

```
folio/
├── README.md
├── AGENTS.md              ← This file
├── LICENSE
├── pyproject.toml
│
├── src/folio/
│   ├── cli/               CLI entry points
│   ├── core/              Business logic
│   ├── adapters/          Pluggable integrations
│   │   ├── converters/    PDF → MD converters
│   │   ├── wiki/          Wiki backends
│   │   ├── llm/           LLM providers
│   │   └── sources/       Document sources
│   ├── config/            Config loading and validation
│   ├── templates/         Default prompts, profiles, packs
│   ├── web/               Web dashboard (future)
│   └── service/           Service mode client (future)
│
├── skills/                Agent skills
│   ├── core/              Platform-agnostic instruction content
│   ├── platforms/         Platform-specific wrappers
│   └── templates/         Org-specific fill-in templates
│
├── tests/
├── docs/
└── docker/
```

## Customizing for a new organization

1. Run `folio init --guided` (or `folio init --profile canadian-artist-run-centre`)
2. Edit `folio.yaml` with the org's funders, document types, and paths
3. Edit `headings.yaml` with per-funder canonical section headings
4. Run `folio scan` to preview what the pipeline will do
5. Run `folio pipeline --dry-run` to estimate costs
6. Run `folio pipeline` to process the archive
7. Run `folio skills generate` to produce agent instructions for the org

No Python code changes needed.
