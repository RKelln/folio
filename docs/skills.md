# Agent Skills

Skills are platform-specific instruction files that teach AI coding agents how to write grants for an organization. When an agent loads a skill, it gains funder-specific rubrics, heading taxonomies, organization context, and writing rules grounded in the org's historical grant archive.

Skills are generated from `folio.yaml` config. No Python code changes are needed to customize them for a new organization.

## Architecture

Skills are organized in three layers under the `skills/` directory:

```
skills/
├── core/              Platform-agnostic instruction content
│   ├── archive-search.md
│   ├── grant-drafting.md
│   └── grant-writing-craft.md
├── templates/         Org-specific fill-in templates
│   ├── funders.md
│   ├── organization.md
│   └── wiki-agents.md
├── platforms/         Platform-specific wrapper directories
│   ├── opencode/
│   ├── claude/
│   ├── openclaw/
│   └── hermes/
└── README.md
```

### Layer 1: `skills/core/` — platform-agnostic content

Three markdown templates that form the instruction content, independent of any specific agent platform:

| File | Layer | Purpose |
|------|-------|---------|
| `archive-search.md` | Search | How to search the wiki and markdown archive using `sage-wiki` and `agentmap`. Covers funder tables, document types, search patterns, and the combined two-tool workflow. |
| `grant-drafting.md` | Draft | How to assemble searched information into grant text. Covers drafting principles (ground claims in sources, match funder tone, cite sources) and the output format with section/sources/key-facts structure. |
| `grant-writing-craft.md` | Craft | Writing quality rules: the pre-writing checklist, Pass 1 (fact draft) / Pass 2 (narrative rewrite) workflow, the juror test, section-level rules (the "So What" test), and 15 anti-patterns to avoid. |

These files use `{placeholder}` syntax for context substitution. The generator fills them from `folio.yaml`.

### Layer 2: `skills/templates/` — org-specific fill-in templates

Templates that get filled with org-specific data during generation:

| File | Content | Placeholders Used |
|------|---------|-------------------|
| `funders.md` | Auto-generated funder reference table | `{funder_rows}` |
| `organization.md` | Organization name, description, archive paths | `{org_name}`, `{org_description}`, `{org_abbreviation}`, `{rewrite_md_path}`, `{wiki_path}`, `{raw_archive_path}` |
| `wiki-agents.md` | Template for the wiki's AGENTS.md heading file | `{org_name}`, `{org_slug}`, `{funder_concept_rows}`, `{funder_table}`, `{doc_type_table}` |

### Layer 3: `skills/platforms/` — platform wrappers

Each platform directory contains platform-specific scaffolding. The generator code in `src/folio/core/skills.py` reads core templates, fills placeholders, and assembles output in each platform's native format. The platform directories themselves (aside from `.gitkeep`) are not used at generation time — the logic lives in the generator functions.

### Template substitution

The generator reads template files from `skills/core/` and substitutes `{placeholders}` using Python's `str.format()`-style replacement. Placeholders are matched with the regex `\{(\w+)\}`. If a placeholder has no matching key in the context dictionary, it is left in the output unchanged and a warning is logged.

Context is built by `build_context()` in `src/folio/core/skills.py:65`, which reads from the `ProjectConfig` object (parsed from `folio.yaml`).

## Supported Platforms

Four platforms are supported. Each platform's output format differs to match that platform's native skill/command/agent convention.

### OpenCode

**Output:** `.opencode/skills/grant-writing/SKILL.md`

A single markdown file with YAML frontmatter containing `name`, `description`, and `metadata`. The body concatenates all three core templates (archive-search, grant-drafting, grant-writing-craft) with filled placeholders. This file is placed in the `.opencode/skills/grant-writing/` directory so OpenCode discovers it as a skill named `grant-writing`.

Frontmatter structure:

```yaml
---
name: grant-writing
description: Search and draft grant applications using {org_name}'s historical grant archive...
compatibility: opencode
metadata:
  audience: grant-writers
  repository: {project_name}
---
```

### Claude Code

**Output:** `.claude/commands/grant-search.md` and `.claude/commands/grant-draft.md`

Two separate slash command files. `grant-search.md` contains filled `archive-search.md` content. `grant-draft.md` contains filled `grant-drafting.md` + `grant-writing-craft.md` content. Each is a single markdown file with an H1 heading (`# /grant-search` or `# /grant-draft`).

### OpenClaw

**Output:** `openclaw/system-prompt.md` and `openclaw/tools.yaml`

A system prompt file containing all core template content plus an introductory assistant role paragraph. A separate `tools.yaml` file declares the available tools (`sage_wiki_search`, `sage_wiki_query`, `agentmap_search`, `agentmap_headings`) with their commands and descriptions, pointing at the wiki and rewrite paths from config.

### Hermes

**Output:** `hermes/agent.yaml`

A single YAML file defining an agent named `{org_abbreviation}-grant-writer` with description, system prompt, tool declarations, and skill references (`search`, `draft`, `craft`). All three core templates are embedded in the system prompt field.

## Using the Skills CLI

```bash
folio skills --help
```

### Generate skills for a platform

```bash
folio skills --platform opencode
folio skills --platform claude
folio skills --platform openclaw
folio skills --platform hermes
```

Files are written to the current directory by default.

### Specify an output directory

```bash
folio skills --platform opencode --output .opencode/skills/
```

### Dry run — preview context without writing files

```bash
folio skills --platform opencode --dry-run
```

Prints the platform that would be targeted and the list of context keys that would be available during generation. Useful for verifying `folio.yaml` is correctly configured before generating.

### JSON output for machine consumption

```bash
folio skills --platform opencode --json
```

Returns a JSON object with `files_written` and `warnings` fields:

```json
{
  "files_written": [
    ".opencode/skills/grant-writing/SKILL.md"
  ],
  "warnings": []
}
```

In dry-run mode with `--json`:

```json
{
  "platform": "opencode",
  "context_keys": ["doc_type_rows", "doc_type_table", ...],
  "dry_run": true
}
```

### Specify a custom config file

```bash
folio skills --platform opencode --config path/to/folio.yaml
```

The default config path is `folio.yaml` in the current directory. In dry-run mode, if the config file does not exist, the generator falls back to default config (loading `None`).

## Customizing Skills

### Editing core templates

Edit files in `skills/core/` to change the instruction content that appears in all generated skills across all platforms:

- `archive-search.md` — Modify search workflows, add new search patterns, change tool commands.
- `grant-drafting.md` — Adjust drafting principles, output format requirements, citation rules.
- `grant-writing-craft.md` — Refine writing rules, add or remove anti-patterns, adjust the juror test.

Use `{placeholder}` syntax to reference values from `folio.yaml`. Available placeholders are listed in the Context Variables section below.

### Adding a new platform

1. Add the platform name to `_PLATFORM_CHOICES` in `src/folio/core/skills.py:23`.
2. Write a `_generate_{platform}()` function following the pattern of existing generators:
   - Accept `(config, output_dir, warnings)`.
   - Build context with `build_context(config)`.
   - Fill core templates with `_fill_core("template-name.md", ctx)`.
   - Write output files with `_write_file(path, content)`.
   - Return a list of written paths.
3. Register the generator in the `generators` dict in `generate_skills()`.
4. Add the platform to the `--platform` choices in `src/folio/cli/skills.py:28`.
5. Create a placeholder directory under `skills/platforms/` (optional, but consistent with existing conventions).

### Editing org-specific templates

Files in `skills/templates/` contain org data that gets filled during generation. Edit these to change the structure of funder tables, organization descriptions, or wiki agent files that appear in generated output.

### Per-org configuration

All per-org customization flows from `folio.yaml`. When adapting folio for a different organization:

- **Funder names and abbreviations** — `folio.yaml` funders section feeds `{funder_table}`, `{funder_rows}`, `{funder_abbrev}`, `{funder_concept_rows}`.
- **Organization identity** — `folio.yaml` org section feeds `{org_name}`, `{org_description}`, `{org_abbreviation}`, `{org_slug}`.
- **Document types** — `folio.yaml` doc_types list feeds `{doc_type_table}`, `{doc_type_rows}`.
- **Paths** — `folio.yaml` paths section feeds `{rewrite_md_path}`, `{wiki_path}`, `{raw_archive_path}`.
- **LLM configuration** — `folio.yaml` llm section feeds model and provider references.

No Python code changes are needed for per-org customization.

## Context Variables

These placeholders are available in all core templates and are filled from `ProjectConfig` (parsed from `folio.yaml`). They are built by `build_context()` in `src/folio/core/skills.py:65`.

### Organization identity

| Placeholder | Source | Example |
|-------------|--------|---------|
| `{project_name}` | `project.name` | `My Grant Archive` |
| `{org_name}` | `org.name` | `Mercer Union` |
| `{org_description}` | `org.description` | `A centre for contemporary art...` |
| `{org_abbreviation}` | `org.abbreviation` | `MU` |
| `{org_slug}` | Derived from `org.name` | `mercer-union` (lowercase, dashes) |

### Funders

| Placeholder | Description |
|-------------|-------------|
| `{funder_table}` | Full markdown table: `\| Abbrev \| Full Name \|` with all funders |
| `{funder_rows}` | Table body rows: `\| ABBREV \| Full Name \|` per funder |
| `{funder_abbrev}` | Abbreviation of the first funder alphabetically (used in search pattern examples) |
| `{funder_concept_rows}` | Table body rows mapping funder names to wiki concept paths: `\| ABBREV grants \| wiki/concepts/... \|` |

### Document types

| Placeholder | Description |
|-------------|-------------|
| `{doc_type_table}` | Markdown table: `\| Type \|` with all doc types |
| `{doc_type_rows}` | Table body rows: `\| type_name \|` per type |

### Paths

| Placeholder | Source |
|-------------|--------|
| `{rewrite_md_path}` | `paths.rewrite_md` |
| `{wiki_path}` | `paths.wiki_project` |
| `{raw_archive_path}` | `paths.raw_archive` |

## Generated Skill Structure

A generated skill file (using OpenCode as the canonical example) has this structure:

```
┌─ YAML frontmatter ──────────────────────────────────────┐
│ name: grant-writing                                      │
│ description: Search and draft grant applications...      │
│ compatibility: opencode                                  │
│ metadata:                                                │
│   audience: grant-writers                                │
│   repository: {project_name}                             │
├─ Body section 1: Archive Search ─────────────────────────┤
│ How to search {org_name}'s grant archive...              │
│                                                          │
│ Archive layout (wiki + markdown paths)                   │
│ Funder table                                             │
│ Document type table                                      │
│ Two search tools: sage-wiki vs agentmap                  │
│ Combined workflow (4 steps)                              │
│ YAML frontmatter reference                               │
│ Common search patterns with bash examples                │
├─ Body section 2: Grant Drafting ─────────────────────────┤
│ How to draft grant text using historical archive...      │
│                                                          │
│ Before you write — search first (3-step pipeline)        │
│ Drafting principles: ground, match tone, cite            │
│ Output format: section / drafted text / sources / facts  │
├─ Body section 3: Grant Writing Craft ────────────────────┤
│ Pre-writing checklist (must-have + strongly preferred)   │
│ Core principle: frame as a support organization          │
│ Writing workflow: Pass 1 (fact draft) + Pass 2 (rewrite) │
│ The juror test                                           │
│ Section-level rules (the "So What" test)                 │
│ 15 anti-patterns                                         │
└──────────────────────────────────────────────────────────┘
```

The three core templates are assembled sequentially. The combined file provides a complete grant-writing workflow: find precedent (Search) -> assemble facts (Draft) -> write well (Craft). An agent that loads this skill has everything it needs to write a grant application grounded in organizational data.
