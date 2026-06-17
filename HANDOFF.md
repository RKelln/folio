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

**Phase 1-5 complete. 434 tests passing. All 14 CLI subcommands functional. Pipeline validated against prototype with semantic equivalence confirmed ($0.04 LLM cost). Wiki layout refactored (`.folio/sage-wiki/` + symlinks). All beads closed.**

All 20 core pipeline tasks ported from the prototype. All 10 P0 and 11 P1 bugs fixed. All 8 CLI review findings (folio-039–folio-046) fixed. 8 additional bugs found and fixed during Phase 5 validation. The CLI dispatcher provides `folio <command>` UX with subcommands auto-discovering `folio.yaml` from cwd.

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

## Recent additions (2026-06-16)

### All open beads closed — 21 issues resolved

All bugs consolidated from BUGS.md into beads, then all resolved:
- Wiki layout refactored: `.folio/sage-wiki/` as wiki project dir, root `wiki/` symlink to compiled output, `wiki/raw/` symlink to `markdown/` (no file copying)
- Docling is now the default converter (replaces datalab)
- CLI `--dry-run`/`--json` compliance across all 14 subcommands (folio-3ps epic + 4 children)
- Dead code removed from CLI files (folio-lqr)
- `from __future__ import annotations` standardized across 66 files (folio-bme)
- `build_context()` public API added to core.skills (folio-27e)
- `LLMProvider.complete_with_usage()` — rewriter no longer bypasses abstraction (folio-dj1)
- Skills refactored from `{?conditional}` blocks to tool snippet composition (folio-7dt)
- French language detection with frequency analysis (folio-j9h)
- Config behavior normalized — optional CLIs log warnings, required CLIs error consistently (folio-20o)
- Filename convention documented in `docs/file-naming.md` (folio-r8c)
- Guide CLI refactored from manual argv to argparse, section regex fixed (folio-83v, folio-zqr)
- 13 new CLI tests added (folio-3je)

## What to do next

### ✅ COMPLETED — (no open beads)

All 21 beads closed. 434 tests passing. All P0-P3 issues resolved.

### Resolved bugs (all now fixed)

| Bead ID | Original # | What | Status |
|---------|-----------|------|--------|
| folio-dj1 | 015 | LLMProvider token counts | ✅ complete_with_usage() |
| folio-j9h | 016b | French language detection | ✅ detect_language() + rewriter skip |
| folio-r8c | 017 | Filename convention | ✅ docs/file-naming.md |
| folio-bme | 037 | `__future__` annotations | ✅ 66 files standardized |

### Deferred

- **Step 5 prioritize validation** — run `folio prioritize` on 1-2 year groups (~$0.10)
- **Full archive rewrite** — DO NOT run on all 1,255 files (~$161); only with explicit budget approval

## Important design decisions

1. **No Pydantic** — config validation uses plain dataclasses to keep deps minimal.
2. **LLM provider bypass** — ✅ Resolved — `complete_with_usage()` added to `LLMProvider`.
3. **Safe condition DSL** — the 12 condition types in `classifier.py` are the canonical way to express classification rules. Legacy eval parser exists for migration from prototype configs.
4. **SequenceMatcher autojunk** — always use `autojunk=False` when comparing grant documents.
5. **Frontmatter API is frozen** — `parse_frontmatter`, `dict_to_frontmatter`, `sanitize_frontmatter`, `update_frontmatter` have the same signatures as the prototype. Don't change them.
6. **Manifest as checkpoint state** — the manifest at `{paths.rewrite_md}/manifest.json` is the pipeline's resume mechanism. Save after each stage.
7. **Filename convention** — ✅ Resolved — `docs/file-naming.md` created.
8. **Paths resolve relative to config** — `load_project_config()` resolves relative paths from the config file's directory, not cwd.
9. **Org repos are separate** — org-specific config + data lives in its own repo (e.g., `ia-library/`). The folio tool repo (`folio/`) contains only code.
10. **load_dotenv() is automatic** — `.env` is loaded from the same directory as `folio.yaml` at config load time.
11. **Agentmap is standalone** — kept as a separate Go binary, not ported to Python. Config toggle with PATH validation.
12. **Skills compose from tool snippets** — ✅ Implemented — tool snippets composed at generation time in `build_context()`.

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
folio convert --source ./archive/ --dest ./.folio/converted/  # Convert source files
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
