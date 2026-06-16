# HANDOFF.md — folio project state and next steps

## What this is

This document is for the next AI agent taking over work on `folio`. Read it fully before doing anything. It provides context, current state, what's done, and what to do next.

## Project overview

**folio** turns an arts organization's document archive (grant applications, reports, budgets, exhibition records in PDF/DOCX/XLSX) into a searchable knowledge base that AI agents can use to write grants, answer questions, and understand organizational patterns. It was ported from a working prototype (`llm_wiki`) built for InterAccess gallery's 1,033-file grant archive.

**Repo location:** `/home/ryankelln/Documents/Work/IA_board/folio/`
**Prototype (reference):** `/home/ryankelln/Documents/Work/IA_board/llm_wiki/` (read only — never modify)
**IA org library:** `/home/ryankelln/Documents/Work/IA_board/ia-library/` (separate repo)
**Design plan:** `PLAN.md` (read it — extensive design rationale)

## Current state

**Phase 1-5 complete. 407 tests passing. All 14 CLI subcommands functional. Pipeline validated against prototype with semantic equivalence confirmed ($0.04 LLM cost).**

All 20 core pipeline tasks ported from the prototype. All 10 P0 and 11 P1 bugs fixed. All 8 BUGS.md #039-#046 CLI review findings fixed. 8 additional bugs found and fixed during Phase 5 validation. The CLI dispatcher provides `folio <command>` UX with subcommands auto-discovering `folio.yaml` from cwd.

**Key files to read FIRST (in order):**
1. **`HANDOFF.md`** — this file
2. **`AGENTS.md`** — conventions, module table, how to run folio
3. **`TASKS.md`** — task status (Phase 1-5 done)
4. **`folio guide`** — built-in agent reference (run `folio guide`)
5. **`docs/`** — 6 reference files

## Phase 5 — IA Deployment Validation: COMPLETE

Validated against InterAccess's 1,033-file grant archive. $0.04 total LLM cost.

- **Step 1: Config parity audit** — all classification/rewrite/prioritize values matched. Minor gaps: `period_start`/`period_end` (fixed), `rules_file` (deferred).
- **Step 2: Classify validation** — 1,255 files classified: 292 full, 121 light, 618 minimal, 224 skip. BUGS #038 fixed (legacy parser nested conditions).
- **Step 3: 10-file sample rewrite** — $0.04 cost. 10 files across TAC/OAC/CCA, full/light/minimal tiers. Semantic equivalence confirmed vs prototype.
- **Step 4: Skills comparison** — generated successfully. Template differences expected.
- **Step 5: Prioritize** — not run (optional, deferred).

### Bugs fixed during Phase 5

| Bug | Fix |
|-----|-----|
| rewrite_directory manifest `KeyError: 'files'` crash | `create_manifest()` fallback when file absent |
| User rewrite config from folio.yaml never merged | `_deep_merge_rewrite()` in rewriter |
| Skills template path resolution broken | Fixed `importlib.resources` path to repo root |
| CLI summary shows 0/0 (wrong dict keys) | `summary["ok"]` → `summary["success"]` + errors |
| BUGS #038: 235 files `KeyError: 'type'` in tier rules | Recursive `evaluate_rule` guard for nested conditions |
| `--dest` flag in rewrite CLI not wired | Added `dest` param to `rewrite_directory` |
| Prioritizer ignores `config.prioritize` (dataclass path) | Merge rubric/grouping/processing from `config.prioritize` |
| `period_start`/`period_end` missing from frontmatter defaults | Added to `DEFAULT_REWRITE_CONFIG` and metadata block |

## Recent additions (2026-06-15)

### Agentmap toggle

New `agentmap` config section with `enabled` (bool) and `binary_path`. When enabled:
- Config validation verifies `agentmap` binary is on PATH
- Generated skills include full agentmap NAV workflow (generate → update → check, bulk indexing)
- When disabled, all agentmap references are stripped from generated skills

`ia-library/folio.yaml` has agentmap enabled.

### Conditional skill template blocks

Skill templates support `{?key}...{/key}` blocks. Content between them is included only when `context[key]` is truthy. Currently used to conditionally include agentmap sections.

## What to do next

### Priority: P3 — `folio-7dt` — Refactor skills to compose tool instructions from snippets

**Current state:** `archive-search.md` is a monolithic template with `{?conditional}` blocks for agentmap. Sage-wiki instructions are always included (not conditional).

**Design:**
- Folio ships tool-specific template snippets under `skills/core/`:
  - `_tool-file-search.md` — always included (baseline: grep, glob, Read on `markdown/`)
  - `_tool-sage-wiki.md` — included when `wiki.type != 'null'`
  - `_tool-agentmap.md` — included when `agentmap.enabled`
- `archive-search.md` becomes a wrapper with a `{tool_sections}` placeholder
- Skills generator concatenates enabled snippets into `{tool_sections}`
- Remove `{?conditional}` blocks entirely — composition replaces conditionals

**Acceptance:**
- Default (no tools): skills only teach basic file search on `markdown/`
- sage-wiki enabled: adds wiki search/query instructions
- agentmap enabled: adds section-level search and NAV generation
- Both: includes combined workflow as today

See beads issue `folio-7dt` for full details.

### Remaining open bugs (all P2/P3, tracked in beads)

| Bead ID | BUGS # | What | Priority |
|---------|--------|------|----------|
| folio-dj1 | 015 | LLMProvider doesn't return token counts — rewriter bypasses abstraction | P2 |
| folio-j9h | 016b | French language detection for CCA/BCAH documents | P3 |
| folio-r8c | 017 | Filename convention `FUNDER__Year__Type.md` undocumented/fragile | P2 |
| folio-bme | 037 | `from __future__ import annotations` inconsistent across codebase | P2 |

### Deferred

- **Step 5 prioritize validation** — run `folio prioritize` on 1-2 year groups (~$0.10)
- **Full archive rewrite** — DO NOT run on all 1,255 files (~$161); only with explicit budget approval

## Important design decisions

1. **No Pydantic** — config validation uses plain dataclasses to keep deps minimal.
2. **LLM provider bypass** — the rewriter creates its own OpenAI client for token tracking because `LLMProvider.complete()` doesn't return usage metadata. See beads `folio-dj1`.
3. **Safe condition DSL** — the 12 condition types in `classifier.py` are the canonical way to express classification rules. Legacy eval parser exists for migration from prototype configs.
4. **SequenceMatcher autojunk** — always use `autojunk=False` when comparing grant documents. See `BUGS.md` #007.
5. **Frontmatter API is frozen** — `parse_frontmatter`, `dict_to_frontmatter`, `sanitize_frontmatter`, `update_frontmatter` have the same signatures as the prototype. Don't change them.
6. **Manifest as checkpoint state** — the manifest at `{paths.rewrite_md}/manifest.json` is the pipeline's resume mechanism. Save after each stage.
7. **Filename convention** — files use `FUNDER__Year_Description__Type.md` with double-underscore separators. See beads `folio-r8c`.
8. **Paths resolve relative to config** — `load_project_config()` resolves relative paths from the config file's directory, not cwd.
9. **Org repos are separate** — org-specific config + data lives in its own repo (e.g., `ia-library/`). The folio tool repo (`folio/`) contains only code.
10. **load_dotenv() is automatic** — `.env` is loaded from the same directory as `folio.yaml` at config load time.
11. **Agentmap is standalone** — kept as a separate Go binary, not ported to Python. Config toggle with PATH validation.
12. **Skills compose from tool snippets** — (design in `folio-7dt`) generated skills are assembled from per-tool template snippets based on what's installed.

## How to run things

```bash
# Install folio as a CLI tool
cd /home/ryankelln/Documents/Work/IA_board/folio
uv tool install --editable .

# Work from an org library directory
cd /home/ryankelln/Documents/Work/IA_board/ia-library

folio                    # Show available commands
folio pipeline --dry-run # Estimate costs
folio pipeline           # Run all stages
folio scan               # Scan the archive
folio classify           # Classify markdown files
folio init --guided      # Interactive org setup
folio skills --platform opencode  # Generate agent skills

# Run tests
cd /home/ryankelln/Documents/Work/IA_board/folio
uv run pytest tests/ -v
```

## Org library convention

```
ia-library/          # Org repo (separate git repo from folio tool)
├── folio.yaml       # Org config (funders, doc types, paths, LLM, headings, agentmap, etc.)
├── .env             # API keys (DEEPSEEK_API_KEY, DATALAB_API_KEY)
├── archive/         # Raw source files (PDF, DOCX, XLSX)
├── markdown/        # Final LLM-rewritten output
├── wiki/            # Sage-wiki searchable knowledge base
└── .folio/          # Pipeline intermediates (converter output, cleaned md, manifests)
```

## Quick code navigation

| Need to find | Look in |
|---|---|
| How a module works | `AGENTS.md` section 7 (module table) |
| Task status | `TASKS.md` |
| Known issues | `bd ready` / `bd show <id>` (beads) |
| CLI entry point | `src/folio/cli/<name>.py` |
| CLI dispatcher | `src/folio/cli/main.py` |
| Business logic | `src/folio/core/<name>.py` |
| Shared throttle | `src/folio/core/throttle.py` |
| Converter interface | `src/folio/adapters/converters/base.py` |
| Wiki interface | `src/folio/adapters/wiki/base.py` |
| LLM interface | `src/folio/adapters/llm/base.py` |
| Config schema | `src/folio/config/schema.py` |
| Config defaults | `src/folio/config/defaults.yaml` |
| Test fixtures | `tests/conftest.py` |
| Org profiles | `src/folio/templates/profiles/*.yaml` |
| Skill templates | `skills/core/*.md` |
| IA org library | `../ia-library/` (separate repo) |
