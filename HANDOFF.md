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

**Phase 1 + Phase 2 complete. Phase 3 (CLI stubs) complete. CI/CD workflow added. 352/354 tests passing. All 11 CLI subcommands functional.**

All 20 core pipeline tasks ported from the prototype. All 10 P0 and 11 P1 bugs fixed. The CLI dispatcher provides `folio <command>` UX with subcommands auto-discovering `folio.yaml` from cwd.

**New in this session:**
- 8 CLI stubs implemented: `clean`, `classify`, `rewrite`, `prioritize`, `canonicalize`, `ingest`, `audit`, `scan`
- All CLIs support `--help`, `--dry-run`, `--json`, `--config` flags per AGENTS.md Rule 4
- `folio guide` added — comprehensive agent-facing reference (with `--topic config` for extended config docs)
- `teach` registered in dispatcher (interactive tutorial placeholder)
- `skills.py` fixed to accept `argv` parameter and added epilog/help
- `main.py` dispatcher has `__name__ == '__main__'` guard for `python -m` usage
- All ruff E501 line-length errors fixed in CLI
- CI/CD: `.github/workflows/ci.yml` — runs ruff, mypy, pytest on Python 3.10/3.11/3.12
- Code reviewed by beads-code-reviewer: 0 critical, all P1s fixed

IA deployment: `ia-library/folio.yaml` created merging all 3 prototype configs. Scan (2,600 files) and classify (1,255 files) validated against prototype data. Single-file LLM rewrite tested end-to-end. Full pipeline dry-run estimates $161 for 2,600 files.

**Key files to read FIRST (in order):**
1. **`HANDOFF.md`** — this file
2. **`AGENTS.md`** — conventions, module table, how to run folio
3. **`TASKS.md`** — 47 tasks, Phase 1–3 done, Phase 4/5 remaining
4. **`README.md`** — quickstart and command reference
5. **`folio guide`** — built-in agent reference (run `folio guide`)

## What to do next

### Step 1: Complete IA deployment validation (Phase 5)

The IA config is at `../ia-library/folio.yaml`. Install folio and run from there:

```bash
cd /home/ryankelln/Documents/Work/IA_board/folio
uv tool install --editable .
cd ../ia-library
folio pipeline --dry-run  # verify estimate
```

**Remaining validation:**
1. `folio rewrite` on a 10-file sample — compare output with prototype `rewrite_md/`
2. If sample matches, run `folio rewrite` on all 1,255 files
3. `folio prioritize` on the rewrite output
4. `folio skills --platform opencode` — compare with prototype `.opencode/skills/grant-writing/SKILL.md`

**Known issue:** ~170 files get wrong classification tier (`BUGS.md` #038) — legacy condition parser produces `KeyError: 'type'` for some compound rules. P2, not blocking.

### Step 2: Documentation (Phase 3)

Write `docs/` reference files: `pipelines.md`, `config.md`, `converters.md`, `wiki-backends.md`, `frontmatter.md`, `skills.md`.

`folio guide` already provides an agent-facing reference. The docs files should be the human-facing detailed reference.

### Step 3: Remaining polish (Phase 4)

- Add `--version` flag to all CLI tools (reads from `folio.__version__`)
- Write CLI tests under `tests/cli/`
- Fix 2 pre-existing test failures in `tests/test_config.py` (path defaults — tests expect relative paths but loader resolves absolute)

## Important design decisions

1. **No Pydantic** — config validation uses plain dataclasses to keep deps minimal.
2. **LLM provider bypass** — the rewriter creates its own OpenAI client for token tracking because `LLMProvider.complete()` doesn't return usage metadata. See `BUGS.md` #015.
3. **Safe condition DSL** — the 12 condition types in `classifier.py` are the canonical way to express classification rules. Legacy eval parser exists for migration from prototype configs.
4. **SequenceMatcher autojunk** — always use `autojunk=False` when comparing grant documents. See `BUGS.md` #007.
5. **Frontmatter API is frozen** — `parse_frontmatter`, `dict_to_frontmatter`, `sanitize_frontmatter`, `update_frontmatter` have the same signatures as the prototype. Don't change them.
6. **Manifest as checkpoint state** — the manifest at `{paths.rewrite_md}/manifest.json` is the pipeline's resume mechanism. Save after each stage.
7. **Filename convention** — files use `FUNDER__Year_Description__Type.md` with double-underscore separators. See `BUGS.md` #017.
8. **Paths resolve relative to config** — `load_project_config()` resolves relative paths from the config file's directory, not cwd.
9. **Org repos are separate** — org-specific config + data lives in its own repo (e.g., `ia-library/`). The folio tool repo (`folio/`) contains only code.
10. **load_dotenv() is automatic** — `.env` is loaded from the same directory as `folio.yaml` at config load time.

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
├── folio.yaml       # Org config (funders, doc types, paths, LLM, headings, etc.)
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
| Known issues | `BUGS.md` |
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
