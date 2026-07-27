# Agent Skills

Agent skills teach AI assistants how to use a folio-built knowledge base.
They live in `skills/core/` as platform-agnostic markdown files, with
platform wrappers in `skills/platforms/` and org-specific fill-in data
in `skills/templates/`.

## Naming convention

| Prefix | Meaning |
|--------|---------|
| `_` (underscore) | Component — composed into other skills during generation, never loaded directly by a platform. May be conditional (e.g. `_tool-sage-wiki.md` only when wiki is enabled) or always included (e.g. `_librarian.md`). |
| No prefix | Standalone skill — a complete instruction set loaded directly by the platform as a named skill. |

The generator in `src/folio/core/skills.py:122-134` controls composition:
```
_tool-file-search.md   → always
_tool-sage-wiki.md     → if wiki enabled
_tool-agentmap.md      → if agentmap enabled
_wiki-maintenance.md   → if wiki enabled
_librarian.md          → always, last (master skill — assembles all helpers)
```

The non-prefix files (`archive-search.md`, `grant-drafting.md`, `grant-writing-craft.md`) are assembled directly into the `grant-writing` skill output.

## Core files

| File | Type | What it teaches |
|------|------|-----------------|
| `_librarian.md` | Helper | Master skill — all workflows (search, grant writing, research, maintenance). The single-file entry point that assembles tool helpers conditionally. |
| `_wiki-maintenance.md` | Helper | Wiki health and quality improvement. Runs `folio audit` for dead links, thin articles, duplicates, provenance, placeholder phrasing, truncation, and more. Documents `folio audit --fix` for deterministic cleanup. |
| `_tool-file-search.md` | Helper | Baseline file search with `grep` and `Read`. Always included. |
| `_tool-sage-wiki.md` | Helper | sage-wiki search and query commands. Included only when wiki backend is sage-wiki. |
| `_tool-agentmap.md` | Helper | agentmap section-level search. Included only when `agentmap.enabled: true`. |
| `archive-search.md` | Layer 1 | Search the archive — combines wiki and file search for cross-document queries |
| `grant-drafting.md` | Layer 2 | Assemble grant text — find precedent applications, extract boilerplate, gather statistics from the archive |
| `grant-writing-craft.md` | Layer 3 | Write effective grant applications — persuasive writing craft grounded in organizational data |

## Three layers

folio skills are organized in three layers that build on each other:

| Layer | File | What it teaches |
|-------|------|-----------------|
| Layer 1: Search | `archive-search.md` | How to search the archive using wiki + agentmap |
| Layer 2: Draft | `grant-drafting.md` | How to assemble found information into grant text |
| Layer 3: Craft | `grant-writing-craft.md` | How to write effective grant applications |

Agents load the layers appropriate to their task. A search agent might only need Layer 1; a grant-writing agent needs all three.

## Wiki maintenance

The `_wiki-maintenance.md` helper teaches agents to run health checks on compiled wiki output:

```bash
folio audit                    # All 14 check categories:
                               #   dead links, thin articles, near-duplicates,
                               #   missing sections, suspicious concepts, stale content,
                               #   provenance, low confidence, placeholder phrasing,
                               #   speculative phrasing, truncation suspects,
                               #   weak sections, link noise, name collisions
folio audit --fix              # Deterministic safe cleanup of flagged issues
folio audit --dry-run          # Preview without making changes
folio audit --json             # Machine-readable output
```

All phrase lists, thresholds, and flags are configurable under `audit:` in `folio.yaml`. See the section in `defaults.yaml` for documentation of every option.

## Platform wrappers

The `core/` files are platform-agnostic. The `platforms/` directory contains wrappers that adapt them for specific assistant platforms:

- OpenCode (`opencode`)
- Claude Code / Claude Desktop (`claude`)
- Hermes Agent (`hermes`)
- OpenClaw (`openclaw`)

Each wrapper provides the platform-specific format (system prompt, tool configuration, SKILL.md file) while the core content stays the same.

## Generating skills for an org

```bash
folio skills generate --platform openclaw   # produces system prompt + tool config
folio skills generate --platform opencode   # produces .opencode/skills/
folio skills generate --platform claude     # produces .claude/commands/
folio skills generate --platform hermes     # produces skills/skill-name/SKILL.md
```

The generator reads `skills/core/` files, fills `{placeholders}` from the org's
`folio.yaml` (funder names, directory paths, org name, wiki structure, tool
availability), applies platform wrappers, and writes the output to the
appropriate platform-specific directory.

## Customization

- `templates/funders.md` — auto-generated funder table (filled during generation)
- `templates/organization.md` — auto-generated org context (filled during generation)
- `templates/wiki-agents.md` — template for the wiki's AGENTS.md file
