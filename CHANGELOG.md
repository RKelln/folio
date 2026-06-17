# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v0.1.1 — Cleanup & Polish — 2026-06-17

Bugfix and cleanup release removing org-specific naming, stale documentation, and
a broken flag in the release command.

### Fixed
- `uv build --check` replaced with `uv build` in release command (`--check` does not exist)
- Conflicting `--generate-notes` flag removed from `gh release create` in release command

### Changed
- `IA_LIBRARY_PATH` env var renamed to `LIBRARY_PATH` (folio is art-org agnostic)
- All `IA_*` variable names, function names, and test names replaced with `LIBRARY_*`
- Default fallback directory for tests changed from `ia-library` to `org-library`
- `.gitignore` org-library ignore pattern updated to `org-library/`
- `docs/INFO.md` renamed to `docs/README.md` for consistency

### Infrastructure
- Removed 1,851 lines of stale implementation docs (PLAN.md, TASKS.md, HANDOFF.md, CLAUDE.md)
- 1088 tests passing, 16 skipped

## v0.1.0 — Initial Release — 2026-06-17

folio turns an arts organization's document archive into a searchable knowledge
base that AI coding agents can use to write grants, answer questions, and
understand organizational patterns.

No code changes — just YAML config.

### Quick start

```bash
git clone https://github.com/RKelln/folio
uv tool install --editable ./folio

mkdir my-org && cd my-org
folio init --guided
folio scan
folio pipeline --dry-run
folio pipeline
```

### How it works

folio processes a raw document archive through 8 pipeline stages:

1. **scan** — enumerate files, detect funders, years, document types, and drafts
2. **convert** — PDF/DOCX/XLSX → Markdown via docling, datalab, marker-pdf, or pandoc
3. **clean** — remove form chrome, boilerplate, and PDF artifacts
4. **canonicalize** — detect drafts, resolve versions, deduplicate near-duplicates
5. **classify** — score quality, assign processing tier (full / light / minimal)
6. **rewrite** — LLM re-authoring with tiered prompts and per-funder heading taxonomies
7. **prioritize** — score archival priority (1–3) within year groups
8. **wiki** — compile markdown into a searchable sage-wiki knowledge base

The pipeline saves checkpoint state after each stage — interrupted runs resume
where they left off. Every command supports `--dry-run` for cost preview and
`--json` for structured output.

### 19 CLI commands

| Command | Purpose |
|---------|---------|
| `folio pipeline` | Run all 8 stages end-to-end |
| `folio scan` | Preview archive contents, costs, and estimated time |
| `folio init` | Guided setup with 8+ built-in profiles for Canadian arts orgs |
| `folio convert` | Convert PDF/DOCX/XLSX → markdown |
| `folio clean` | Deterministic markdown cleanup |
| `folio classify` | Quality scoring and tier assignment (12 condition types) |
| `folio rewrite` | LLM re-authoring with tiered prompts |
| `folio prioritize` | Archival priority scoring with concurrent processing |
| `folio canonicalize` | Version detection and content-hash deduplication |
| `folio ingest` | One-off document ingestion with auto frontmatter |
| `folio audit` | Wiki quality audit (dead links, thin articles, duplicates, staleness) |
| `folio validate` | Validate output against config (frontmatter, headings, placeholders) |
| `folio repack` | Migrate nested directories to flat folio filename convention |
| `folio wiki` | Wiki management (init, compile, search, query, status, lint, verify) |
| `folio skills` | Generate agent skills for opencode, claude, openclaw, and hermes |
| `folio guide` | Built-in agent reference with keyword search and JSON output |
| `folio install-agent` | Write AGENTS.md and skills files into a project |
| `folio teach` | Interactive tutorial (coming soon) |
| `folio test-skills` | Scenario-based agent skill validation |

### LLM provider support

folio uses OpenAI-compatible APIs and works with any provider:

| Provider | Example `base_url` | Env var |
|----------|-------------------|---------|
| DeepSeek | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |
| OpenAI | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| Groq | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| Ollama (local) | `http://localhost:11434/v1` | (none required) |

Configure model IDs, base URL, and pricing in `folio.yaml`. Cost is ~$4–12 for
a typical 1000-file archive with tiered processing.

### Installation

```bash
git clone https://github.com/RKelln/folio
uv tool install --editable ./folio
```

Requires Python 3.10+. See [docs/installation.md](docs/installation.md) for
platform-specific dependency setup (converters, sage-wiki, agentmap).

### What's under the hood

- **1,104 tests** across 10 new test modules, 76% coverage (up from 39%)
- **Thread-safe** adapter layer with locking on lazy-initialized clients
- **Pluggable architecture** — converters, wiki backends, LLM providers, and sources can be swapped via YAML
- **Self-documenting CLI** — every command has `--help`, `--dry-run`, and `--json`
- **Agent-native** — designed to be run by AI coding agents with structured output, no interactive prompts, and deterministic exit codes
