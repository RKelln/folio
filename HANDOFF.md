# HANDOFF.md — folio project state and next steps

## What this is

This document is for the next AI agent taking over work on `folio`. Read it fully before doing anything. It provides context, current state, what's done, and what to do next.

## Project overview

**folio** turns an arts organization's document archive (grant applications, reports, budgets, exhibition records in PDF/DOCX/XLSX) into a searchable knowledge base that AI agents can use to write grants, answer questions, and understand organizational patterns. It was ported from a working prototype (`llm_wiki`) built for InterAccess gallery's 1,033-file grant archive.

**Repo location:** `/home/ryankelln/Documents/Work/IA_board/folio/`
**IA org library:** `/home/ryankelln/Documents/Work/IA_board/ia-library/` (separate repo)
**Design plan:** `PLAN.md` (read it — extensive design rationale)

## Current state

**All 13 P0 CODE_REVIEW bugs fixed. CODE_REVIEW.md deleted. 528 tests passing. 17 CLI subcommands. Onboarding docs complete. Agent skills refactored with librarian, wiki-maintenance, and tool snippets.** 

### What was done this session (2026-06-17)

**Docs & onboarding (8 beads closed):**
- README.md rewritten for agent-first onboarding (~90 lines, prerequisites, FAQ)
- AGENTS.md updated with "helping an org" section and onboarding table
- CLAUDE.md filled with real build/test/architecture (no more placeholders)
- `docs/getting-started.md` — 12-step end-to-end onboarding walkthrough
- `docs/installation.md` — full deps guide per platform (Ubuntu, macOS)
- `docs/agent-workflows.md` — 6 worked examples for common agent tasks
- `docs/design/validate.md` — design doc for the validate CLI

**New features (4 beads closed):**
- `folio validate` — deterministic quality checks (frontmatter, content, size, headings, placeholders). `--sample`, `--tier`, `--all`, `--approve`, `--json`, `--dry-run`.
- `folio repack` — nested-to-flat file migration tool with `--move`, `--dry-run`, funder/year/type detection
- `folio wiki` — 6 subcommands wrapping sage-wiki native tools: `status`, `doctor`, `lint`, `coverage`, `diff`, `verify`
- `folio install-agent` — bootstrap AGENTS.md/CLAUDE.md + skills per platform

**Skills refactored (2 beads closed):**
- `skills/core/_wiki-maintenance.md` — conditional snippet (wiki enabled): lint, verify, diff, provenance workflows
- `skills/core/_librarian.md` — always-loaded master orchestrator skill: tool choice table, daily/grant-writing/research/maintenance workflows
- `skills.py build_context()` — updated to compose new snippets conditionally

**Bug fixes (1 bead closed):**
- `folio-1qw` — all 13 P0 CODE_REVIEW items resolved, file deleted
  - #026: `max_files_for_dedup` cap in canonicalizer
  - #027: cached OpenAI client in `_get_client()`
  - #029: sage-wiki stderr printed on compile failure
  - #031: Manifest TypedDicts + prioritizer syncs to canonical manifest

**Tests:**
- 528 tests passing (93 added via `test_skills.py`, `test_orchestrator.py` updates)
- Agentic test scenario added for `folio validate` (`validate-markdown-quality`)
- Validated against 606-file IA library: 234 issues found, 3 priority files identified

## Open beads

| ID | P | Title |
|----|---|-------|
| `folio-706` | P2 | Update Hermes Agent support to agentskills.io SKILL.md format |

## Key files to read FIRST (in order)

1. **`HANDOFF.md`** — this file
2. **`AGENTS.md`** — conventions, module table, how to run folio
3. **`README.md`** — quickstart, commands, doc links
4. **`docs/getting-started.md`** — full onboarding walkthrough
5. **`docs/INFO.md`** — all docs index
6. **`folio guide`** — built-in agent reference (run `folio guide`)

## New CLI commands added this session

| Command | Purpose |
|---------|---------|
| `folio validate` | Deterministic markdown quality checks |
| `folio repack` | Nested → flat file migration |
| `folio wiki` | Sage-wiki maintenance (status, doctor, lint, coverage, diff, verify) |
| `folio install-agent` | Bootstrap AGENTS.md + skills per platform |

## Important design decisions

1. **No Pydantic** — config validation uses plain dataclasses to keep deps minimal.
2. **Safe condition DSL** — the 12 condition types in `classifier.py` are the canonical way to express classification rules.
3. **SequenceMatcher autojunk** — always use `autojunk=False` when comparing grant documents.
4. **Frontmatter API is frozen** — `parse_frontmatter`, `dict_to_frontmatter`, `sanitize_frontmatter`, `update_frontmatter` have the same signatures as the prototype.
5. **Manifest as checkpoint state** — the manifest at `{paths.rewrite_md}/manifest.json` is the pipeline's resume mechanism.
6. **Paths resolve relative to config** — `load_project_config()` resolves relative paths from the config file's directory.
7. **Org repos are separate** — org-specific config + data lives in its own repo (e.g., `ia-library/`).
8. **load_dotenv() is automatic** — `.env` is loaded from the same directory as `folio.yaml`.
9. **Agentmap is standalone** — kept as a separate Go binary, not ported to Python.
10. **Skills compose from tool snippets** — snippets composed at generation time in `build_context()`. Always: `_tool-file-search.md` + `_librarian.md`. Conditional: `_tool-sage-wiki.md`, `_wiki-maintenance.md` (wiki enabled), `_tool-agentmap.md` (agentmap enabled).

## How to run things

```bash
# Install folio as a CLI tool
cd /home/ryankelln/Documents/Work/IA_board/folio
uv tool install --editable .

# Work from an org library directory
cd /home/ryankelln/Documents/Work/IA_board/ia-library

folio                      # Show available commands (17 now)
folio pipeline --dry-run   # Estimate costs
folio pipeline             # Run all stages
folio validate --source ./markdown/ --sample 20  # Quality check
folio repack --source ./messy/ --dest ./archive/ --dry-run  # Migrate files
folio wiki status          # Wiki health
folio install-agent --platform opencode  # Bootstrap agent config

# Run tests
cd /home/ryankelln/Documents/Work/IA_board/folio
uv run pytest tests/ -v    # 528 tests, ~3s
```

## Org library convention

```
ia-library/          # Org repo (separate git repo from folio tool)
├── folio.yaml       # Org config (funders, doc types, paths, LLM, headings, agentmap, etc.)
├── .env             # API keys (DEEPSEEK_API_KEY, OPENAI_API_KEY, etc.)
├── archive/         # Raw source files (PDF, DOCX, XLSX)
├── markdown/        # Final LLM-rewritten output
├── wiki/            # Symlink to .folio/sage-wiki/wiki/ (compiled output)
│   └── raw/         # Symlink to markdown/ (no file copying)
├── .folio/          # Pipeline intermediates (converter output, cleaned md, manifests)
│   └── sage-wiki/   # Sage-wiki project directory (wiki_project default)
└── .opencode/       # Generated agent skills (opencode platform)
```

## Quick code navigation

| Need to find | Look in |
|---|---|
| How a module works | `AGENTS.md` section 7 (module table) |
| Task status | `bd ready` / `bd show <id>` (beads) |
| CLI entry point | `src/folio/cli/<name>.py` |
| New: validator | `src/folio/core/validator.py` |
| New: repacker | `src/folio/core/repacker.py` |
| New: wiki CLI | `src/folio/cli/wiki.py` |
| New: install-agent | `src/folio/cli/install_agent.py` |
| Skill templates | `skills/core/*.md` (6 templates now: file-search, sage-wiki, agentmap, wiki-maintenance, librarian + 3 wrapper templates) |
| Design docs | `docs/design/` |
| Test scenarios | `tests/agent_scenarios/ia_scenarios.yaml` |
| IA org library | `../ia-library/` (separate repo) |

## Deferred

- **Step 5 prioritize validation** — run `folio prioritize` on 1-2 year groups (~$0.10)
- **Full archive rewrite** — DO NOT run on all 1,255 files (~$161); only with explicit budget approval
