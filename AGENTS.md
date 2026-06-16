# AGENTS.md — Agent Instructions for folio

## Purpose

folio builds a knowledge base from an organization's document archive (grant applications, reports, budgets, exhibition records) that AI coding agents can use to write grants, answer questions, and understand organizational patterns. Designed for arts organizations but works for any document-heavy non-profit.

**If you are helping a new organization set up folio, start with README.md** — it has the quickstart. This file covers how to build and modify tooling in this repo.

## Rules for All Code

### 1. Configuration drives behavior, not hardcoding

Every pattern, threshold, funder name, and classification rule must live in a config file. The code reads config. An agent customizing for a new org should never need to edit Python code — only YAML or markdown.

### 2. Every tool must be self-documenting

- `--help` must explain what the tool does and show realistic usage examples
- Docstrings must cover purpose, inputs, outputs, and side effects
- Config files must have comments explaining every option

### 3. Make tools discoverable by agents

A new agent dropped into this repo should be able to:
- Run `folio --help` to see available subcommands
- Run `folio <command> --help` to understand what each does
- Open the relevant config file to see what's configurable
- Run with `--dry-run` to preview without side effects

### 4. Every tool must be runnable by agents

- Use `uv run folio <command>` or `folio <command>` (if installed via pipx)
- All dependencies in `pyproject.toml`
- Every tool must have `--dry-run` mode
- Every tool must have `--json` output mode for structured data exchange
- Avoid interactive prompts; everything must work non-interactively via CLI flags
- Exit codes: 0 on success, non-zero on failure
- Use `tqdm` for progress bars
- Verified: all 14 CLI entry points support `--dry-run` and `--json`

### 5. Design for composition

Tools work as stages in a pipeline:
- One tool's `--json` output can be another tool's `--manifest` input
- Checkpoint state is always a JSON file (not pickle, not sqlite — agents can read JSON)

### 6. Per-org customizations go in config, not code

When an agent needs to adapt folio for a different organization:
- Funder names and abbreviations → `folio.yaml` funders section
- Year range patterns → `folio.yaml`
- Document type vocabulary → `folio.yaml`
- Form chrome and draft marker patterns → classification config
- Classification thresholds → classification config
- Heading taxonomies → headings config
- Skill prompts and rubrics → `skills/core/`

### 7. Keep code files focused

Each module does one job well:

| Module | Job |
|--------|-----|
| `core/cleaner.py` | Deterministic markdown cleanup |
| `core/classifier.py` | File quality scoring, tier assignment, language detection |
| `core/rewriter.py` | LLM re-authoring with tiered prompts |
| `core/prioritizer.py` | Archival priority scoring |
| `core/canonicalizer.py` | Version detection and dedup |
| `core/ingester.py` | One-off document ingestion |
| `core/auditor.py` | Wiki quality audit |
| `core/scanner.py` | Archive scanning and funder detection |
| `core/frontmatter.py` | YAML frontmatter parsing, generation, validation |
| `core/manifest.py` | Pipeline manifest read/write (canonical — no other module should define its own manifest schema) |
| `core/throttle.py` | Thread-safe `RateLimiter` for API calls |
| `core/errors.py` | Shared error/status types |
| `core/skills.py` | Skills generation — platform-agnostic template filling, tool snippet composition |
| `adapters/converters/` | PDF/DOCX → Markdown converters |
| `adapters/wiki/` | Wiki backend integrations |
| `adapters/llm/` | LLM provider abstraction |
| `adapters/sources/` | Document source connectors |
| `config/` | Config loading and Pydantic validation |
| `cli/` | CLI entry points (thin wrappers around core) |
| `cli/guide.py` | Built-in agent reference guide (argparse-based with --dry-run and --json) |

### 8. Use standard libraries where possible

Prefer the existing dependencies (pyyaml, openai, python-dotenv, tqdm) over new ones unless there's a strong reason.

### 9. Never silently discard errors

Bare `except Exception: pass` or `continue` hides bugs. Always log the exception at minimum. Prefer catching specific exception types.

### 10. Guard concurrent state

Any shared mutable state accessed from multiple threads needs a `threading.Lock`. Retry logic must re-submit work, not re-read a cached `Future.result()`.

### 11. Strict DRY — no duplicate implementations

Every function, class, or workflow must have exactly one canonical home. When you need something that might already exist (rate limiter, manifest loader, YAML parser, config merger, LLM response parser), check the module table above. If you find yourself writing the same logic a second time, extract it to a shared module — do not copy-paste. Duplicate implementations cause divergence bugs, dead code, and force orgs to fix the same bug in multiple places when customizing.

## How to use folio (for agents)

folio is installed as a CLI tool. Run it from an org library directory
and it auto-discovers `folio.yaml`.

```bash
folio                  # Show available commands
folio pipeline         # Run all 8 pipeline stages
folio pipeline --dry-run  # Estimate costs without executing
folio scan             # Scan the archive
folio init --guided    # Interactive org setup
folio skills --platform opencode  # Generate agent skills
```

**Org library convention** — each org has its own directory (often a repo):

```
org-library/
├── folio.yaml    # Org config (funders, doc types, paths, LLM)
├── .env          # API keys
├── archive/      # Raw source files (PDF, DOCX, XLSX)
├── markdown/     # Final LLM-rewritten output
├── wiki/         # Sage-wiki searchable knowledge base
└── .folio/       # Pipeline intermediates (hidden)
```

Run `folio <command> --help` for subcommand details. See `README.md` for the full command list.

## Project Structure

```
folio/
├── README.md
├── AGENTS.md              ← This file
├── LICENSE
├── pyproject.toml
│
├── src/folio/
│   ├── cli/               CLI entry points
│   ├── core/              Business logic
│   ├── adapters/          Pluggable integrations
│   │   ├── converters/    PDF → MD converters
│   │   ├── wiki/          Wiki backends
│   │   ├── llm/           LLM providers
│   │   └── sources/       Document sources
│   ├── config/            Config loading and validation
│   ├── templates/         Default prompts, profiles, packs
│   ├── web/               Web dashboard (future)
│   └── service/           Service mode client (future)
│
├── skills/                Agent skills
│   ├── core/              Platform-agnostic instruction content
│   │   ├── _tool-file-search.md         (baseline file search)
│   │   ├── _tool-sage-wiki.md           (wiki search, conditional)
│   │   ├── _tool-agentmap.md            (agentmap search, conditional)
│   │   ├── archive-search.md            (wrapper template)
│   │   ├── grant-drafting.md
│   │   └── grant-writing-craft.md
│   ├── platforms/         Platform-specific wrappers
│   └── templates/         Org-specific fill-in templates
│
├── tests/
├── docs/
└── docker/
```

## Commit conventions

- Use [Conventional Commits](https://www.conventionalcommits.org/) format: `type(scope): description`
- Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Append `Generated-by: <model-name>` trailer to every commit (e.g. `Generated-by: deepseek-v4-pro`)

## Customizing for a new organization

1. Run `folio init --guided` (or `folio init --profile canadian-artist-run-centre`)
2. Edit `folio.yaml` with the org's funders, document types, and paths
3. Edit `headings.yaml` with per-funder canonical section headings
4. Run `folio scan` to preview what the pipeline will do
5. Run `folio pipeline --dry-run` to estimate costs
6. Run `folio pipeline` to process the archive
7. Run `folio skills generate` to produce agent instructions for the org

No Python code changes needed.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
