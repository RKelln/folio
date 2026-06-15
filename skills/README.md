# Agent Skills

This directory contains agent skills that teach AI assistants how to use a folio archive. Skills are organized in three layers:

## Layers

| Layer | File | What it teaches |
|-------|------|-----------------|
| Layer 1: Search | `core/archive-search.md` | How to search the archive using wiki + agentmap |
| Layer 2: Draft | `core/grant-drafting.md` | How to assemble found information into grant text |
| Layer 3: Craft | `core/grant-writing-craft.md` | How to write effective grant applications |

## Platform wrappers

The `core/` files are platform-agnostic. The `platforms/` directory contains wrappers that adapt them for specific assistant platforms (OpenCode, Claude Code, OpenClaw, Hermes).

## Generating skills for an org

```bash
folio skills generate --platform openclaw   # produces system prompt + tool config
folio skills generate --platform opencode   # produces .opencode/skills/
folio skills generate --platform claude     # produces .claude/commands/
```

The generator fills `{placeholders}` in the core files from the org's `folio.yaml` config — funder names, directory paths, org name, wiki structure.

## Customization

- `templates/funders.md` — auto-generated funder table
- `templates/organization.md` — auto-generated org context
- `templates/wiki-agents.md` — template for the wiki's AGENTS.md file
