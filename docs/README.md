# Documents

- [Getting Started](getting-started.md) — full onboarding walkthrough
- [Installation](installation.md) — dependencies, API keys, converters
- [Pipeline stages](pipelines.md) — how the pipeline works end-to-end
- [Configuration](config.md) — folio.yaml reference
- [Converters](converters.md) — PDF/DOCX → markdown converter options
- [Converter Benchmark](benchmark.md) — `folio convert-bench` offline converter scoring
- [Synthetic Corpus](corpus.md) — `folio corpus` PII-free benchmark corpus generation
- [Wiki backends](wiki-backends.md) — wiki compilation backends
- [Frontmatter](frontmatter.md) — YAML frontmatter field reference
- [File naming](file-naming.md) — filename convention reference
- [Agent Workflows](agent-workflows.md) — worked examples for common agent tasks
- [Skills](skills.md) — agent skills architecture
- [Design Notes](design/) — feature design documents

## Commands

Run `folio --help` for the full list. Key additions since v0.1.0:

| Command | New? | Purpose |
|---------|------|---------|
| `folio validate` | new | Deterministic markdown quality checks (frontmatter, content, size, headings, placeholders) |
| `folio repack` | new | Migrate nested folder structures to flat archive/ naming convention |
| `folio wiki` | new | Sage-wiki maintenance (status, doctor, lint, coverage, diff, verify) |
| `folio install-agent` | new | Bootstrap AGENTS.md + skills per platform |
| `folio corpus` | new | Generate a PII-free synthetic benchmark corpus (golden markdown → DOCX/XLSX/PDF) and PII-gate files ([docs](corpus.md)) |
| `folio convert-bench` | new | Offline, deterministic converter benchmark — score converters against the synthetic corpus ([docs](benchmark.md)) |
