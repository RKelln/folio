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

**Phase 1-4 complete. 407 tests passing. All 14 CLI subcommands functional. Docs written. Only Phase 5 (IA deployment validation) remains.**

All 20 core pipeline tasks ported from the prototype. All 10 P0 and 11 P1 bugs fixed. All 8 BUGS.md #039-#046 CLI review findings fixed. The CLI dispatcher provides `folio <command>` UX with subcommands auto-discovering `folio.yaml` from cwd.

IA deployment: `ia-library/folio.yaml` created merging all 3 prototype configs. Scan (2,600 files) and classify (1,255 files) validated against prototype data.

**Key files to read FIRST (in order):**
1. **`HANDOFF.md`** — this file (Phase 5 plan below)
2. **`AGENTS.md`** — conventions, module table, how to run folio
3. **`TASKS.md`** — task status (Phase 1-4 done, 5 remaining)
4. **`BUGS.md`** — known issues (only #037, #038 still open)
5. **`folio guide`** — built-in agent reference (run `folio guide`)
6. **`docs/`** — 6 reference files

## What to do next: Phase 5 — IA Deployment Validation

**Goal:** Prove folio produces equivalent output to the `llm_wiki` prototype for InterAccess's 1,033-file grant archive, with **minimal LLM cost** (under $2).

**Budget principle:** The prototype already spent ~$161 on the full rewrite. We validate with sampling — not re-running. Only Step 3 has LLM cost. Everything else is free.

Prototype reference data at:
- `/home/ryankelln/Documents/Work/IA_board/llm_wiki/` (read only)
  - `classify_config.yaml`, `rewrite_config.yaml`, `prioritize_config.yaml` — source configs
  - `rewrite_md/` — prototype output to compare against
  - `.opencode/skills/grant-writing/SKILL.md` — prototype skills to compare against

IA library at:
- `/home/ryankelln/Documents/Work/IA_board/ia-library/`
  - `folio.yaml` — merged from 3 prototype configs
  - `.env` — API keys
  - `_raw_archive/` — 2,600+ source files (PDF/DOCX/XLSX)
  - `.folio/raw_md/` — converter output
  - `.folio/clean_md/` — cleaned markdown

### Step 1: Config parity audit (free — no API calls)

Verify `ia-library/folio.yaml` contains EVERY value from the 3 prototype configs. Missing values cause folio to silently use defaults, producing different output.

Read each prototype config and cross-check against `folio.yaml`:

**From `classify_config.yaml`:**
- `funders` dict — all abbreviations and full names
- `doc_types` dict — all patterns per type
- `skip_rules` — every rule with conditions and reasons
- `tier_rules` — every rule with conditions and tiers
- `thresholds` — all sub-objects (full_rewrite, full_rewrite_app_report, light_cleanup, raw_financial)
- `form_chrome` patterns, `draft_markers`

**From `rewrite_config.yaml`:**
- `headings` — per-funder canonical heading taxonomies (TAC, OAC, CCA, etc.)
- `useless_headings` — every regex pattern
- `form_chrome_patterns` — every pattern
- `prompts` section (full, light, minimal tier prompts — if customized)

**From `prioritize_config.yaml`:**
- Rubric criteria, grouping config
- Any custom processing settings

Report every missing or mismatched value. Fix `folio.yaml` before proceeding.

### Step 2: Classify validation (free)

Classify already ran against 1,255 files and was "validated against prototype data" per earlier notes. Verify:

1. `folio classify --source .folio/clean_md/ --json` returns tiers matching the prototype's tier assignments for at least a spot-check of 20 files across funders and years.

2. If BUGS.md #038 is relevant (~170 files getting wrong tier due to `KeyError: 'type'`), assess impact: are these mostly `minimal` tier files that would be skipped for LLM rewrite anyway? If so, low impact.

If classify tier assignments are wrong for >5% of files that matter (full/light tier), fix the legacy condition parser first. Otherwise proceed.

### Step 3: 10-file sample rewrite (~$0.10-0.50 in LLM costs)

**This is the only step with API cost.** Pick 10 files spanning:
- Funders: at least TAC, OAC, CCA
- Tiers: 4 full, 3 light, 3 minimal (from classify manifest)
- Years: at least 2023, 2024, 2025
- Doc types: application, report, budget

```bash
cd /home/ryankelln/Documents/Work/IA_board/ia-library
folio clean --source .folio/raw_md/ --dest .folio/clean_md/
folio classify --source .folio/clean_md/
folio rewrite --source .folio/clean_md/ --limit 10
```

Then compare each output against `../llm_wiki/rewrite_md/`:
- LLM output won't be **byte-identical** (temperature, model version)
- Compare **semantic content**: are the same facts present? Same structure? Same frontmatter fields?
- If the 10 files match semantically, the pipeline is validated
- If they don't, investigate why (prompt differences, heading taxonomy, tier assignment)

SAVE THE 10-FILE OUTPUT for comparison with future runs.

### Step 4: Skills comparison (free)

```bash
folio skills --platform opencode --output /tmp/folio-skills/
diff /tmp/folio-skills/grant-writing/SKILL.md ../llm_wiki/.opencode/skills/grant-writing/SKILL.md
```

Check: funder names, table formats, heading references, org context. Template differences are expected (folio's templates may differ from prototype's custom skills). Content should be substantially similar.

### Step 5 (optional): Prioritize validation

If Steps 1-4 all pass, run `folio prioritize` on 1-2 year groups (e.g., `--year 2024`). Compare priority rankings with prototype. This costs ~$0.05-0.10.

### What NOT to do:

- **DO NOT** run `folio pipeline` on all 1,255 files — $161, not needed
- **DO NOT** run `folio pipeline` without `--dry-run` first
- **DO NOT** modify prototype files in `../llm_wiki/`
- **DO NOT** waste time byte-comparing LLM output — semantic equivalence is the bar

### If validation fails:

1. Check classification tier assignments first (most likely root cause)
2. Compare heading taxonomies (missed headings = missing sections)
3. Check prompts (prototype may have custom prompts not in folio defaults)
4. See `BUGS.md` — #015 (LLMProvider token counts), #038 (legacy parser)

### After validation passes:

1. Update `BUGS.md` — close #038 if classification fixed, mark Phase 5 complete
2. Update `TASKS.md` — mark Phase 5 done
3. Push `ia-library/` changes (if folio.yaml was modified)
4. Update `HANDOFF.md` — mark this section complete

---

**Known open issue:** BUGS.md #038 — ~170 files get wrong tier from legacy condition parser. P2, likely affects `minimal` tier files (no LLM cost impact). Fix only if it affects full/light tier files or if classification validation (Step 2) shows meaningful discrepancies.

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
