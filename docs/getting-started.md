# Getting Started

Step-by-step walkthrough for setting up folio at a new organization. For an AI agent helping an org onboard — follow this guide in order.

## 1. Prerequisites

You need:
- **Python 3.10+** with `uv` or `pipx`
- **DEEPSEEK_API_KEY** (required — LLM calls)
- **OPENAI_API_KEY** (optional — wiki embeddings)
- **Go** (optional — for sage-wiki and agentmap binaries)

See [docs/installation.md](installation.md) for full dependency setup commands per platform.

## 2. Install folio

```bash
pipx install folio
# verify:
folio --version
```

If working from the folio source repo: `uv tool install --editable .`

## 3. Create your org library

Each organization gets its own directory (often its own git repo). Create one:

```bash
mkdir my-org-library && cd my-org-library
folio init --guided
```

The guided setup asks 6 questions:
1. Organization name (e.g., "My Gallery")
2. Organization abbreviation (e.g., "MG")
3. Funders (e.g., "OAC: Ontario Arts Council, TAC: Toronto Arts Council")
4. Document types (press Enter for defaults: application, report, budget, etc.)
5. Path to raw archive (default: `./archive/`)
6. LLM configuration (defaults to DeepSeek)

This creates `folio.yaml` and prompts you to create a `.env` file.

### Alternative: use a pre-built profile

If your org matches a known type, skip the guided setup:

```bash
folio init --profile canadian-artist-run-centre   # OAC, TAC, CCA, BCAH funders
folio init --profile generic-canadian-arts         # Generic Canadian arts funders
folio init --profile generic                       # Empty template
```

### Alternative: scan an existing archive

If you already have files with funder-prefixed names:

```bash
folio init --scan ./my-existing-archive/
```

This auto-detects funder abbreviations and years from filenames.

## 4. Configure

Open `folio.yaml`. Key things to check:

```yaml
project:
  name: "My Gallery Grant Archive"

org:
  name: "My Gallery"
  abbreviation: "MG"

funders:
  OAC: "Ontario Arts Council"
  TAC: "Toronto Arts Council"
  CCA: "Canada Council for the Arts"

paths:
  raw_archive: ./archive/          # Where your PDFs/DOCX live
  rewrite_md: ./markdown/          # Final output
  wiki_project: ./.folio/sage-wiki/

llm:
  provider: openai_compatible
  base_url: https://api.deepseek.com
  api_key_env: DEEPSEEK_API_KEY

converter:
  type: docling                    # Default. Change to marker-pdf, datalab, or pandoc
```

Set up `.env`:

```
DEEPSEEK_API_KEY=sk-your-key-here
OPENAI_API_KEY=sk-your-openai-key    # Optional
```

See [docs/config.md](config.md) for every option.

## 5. Organize your archive

Place all source documents (PDF, DOCX, XLSX) into `archive/` with the naming convention:

```
{FUNDER}__{year}_{program-name}__{submission-stage}__{description}.ext
```

Examples:
- `OAC__2024_Operating_Grant__Application__Final.docx`
- `TAC__2025_Exhibition_Series__Report__Q2_Report.pdf`
- `CCA__2023-2025_Research_and_Creation__Budget__Budget.xlsx`

The double-underscore (`__`) separates the 4 segments. See [docs/file-naming.md](file-naming.md) for the full convention.

### If your files are in nested folders

Tool coming soon: `folio repack` will scan nested directories, detect funders/years/types from paths and filenames, and copy them to a flat `archive/` with proper names. For now, rename manually or use the scan output as a guide.

## 6. Preview with scan

```bash
folio scan
```

Shows:
- How many files found
- Which funders and years detected
- Estimated LLM costs
- Estimated processing time

No APIs are called — scan only reads filenames. Safe to run any time.

## 7. Run the pipeline

### Step 1: Dry run

```bash
folio pipeline --dry-run
```

Estimates total cost and shows what each stage will do. No files written, no API calls.

### Step 2: Run it

```bash
folio pipeline
```

The pipeline has 8 stages. You can run them all at once, or one at a time:

```bash
folio pipeline --stages scan,convert,clean          # Just the first 3 stages
folio convert --source ./archive/ --dest ./.folio/converted/
folio clean --source ./.folio/converted/ --dest ./.folio/cleaned/
```

### Pipeline stages

| Stage | What it does | Cost |
|-------|-------------|------|
| 1. `scan` | Enumerate files, detect funders/years/types | Free |
| 2. `convert` | PDF/DOCX/XLSX → Markdown | Free (local) or API cost |
| 3. `clean` | Strip form chrome, fix corruption, normalize headings | Free |
| 4. `canonicalize` | Detect drafts, duplicates, version resolution | Free |
| 5. `classify` | Quality scoring, assign tiers (full/light/minimal/skip) | Free |
| 6. `rewrite` | **LLM re-authoring** — the main cost driver | ~$0.004/file (DeepSeek flash) |
| 7. `prioritize` | LLM priority scoring (1-3) by year groups | Minimal |
| 8. `wiki` | Compile wiki with sage-wiki | Free (local) |

Expect ~$4-12 for a 1000-file archive with DeepSeek. See [docs/pipelines.md](pipelines.md) for stage-by-stage reference.

## 8. Validate output

After the pipeline completes, review the output in `markdown/`:

```bash
# Spot-check a few files
ls markdown/ | head -20
# Check file sizes — tiny files may have lost content
ls -lhS markdown/ | head -20
# Check frontmatter is present
head -5 markdown/OAC__*.md
```

Key things to look for:
- **YAML frontmatter** at the top of each file (funder, type, written, period, priority)
- **`<!-- AGENT:NAV ... -->`** blocks (if agentmap is enabled)
- **No garbled text** from PDF corruption
- **Reasonable file sizes** — very small (< 1KB) or very large (> 500KB) files may need attention

If you find issues, you can:
- Re-run the rewrite on specific files: `folio rewrite --files file1.md,file2.md`
- Re-convert a problematic PDF with a different converter
- Edit the markdown files directly — folio won't overwrite manually edited files

## 9. Build the wiki

The pipeline stage 8 handles this automatically, but you can run it standalone:

```bash
folio pipeline --stages wiki
```

This compiles all `markdown/` files into a sage-wiki knowledge base at `.folio/sage-wiki/`. A symlink at `wiki/` points to the compiled output.

The wiki creates:
- **Concept articles** — cross-document entities (artists, exhibitions, grants, programs)
- **Ontology** — relationships between entities (funded_by, exhibited_at, governed_by)
- **Search index** — hybrid BM25 + vector search

## 10. Generate agent skills

Skills teach AI coding agents how to search and draft from your archive:

```bash
folio skills --platform opencode    # OpenCode assistant
folio skills --platform claude      # Claude Code
folio skills --platform openclaw    # OpenClaw assistant
folio skills --platform hermes      # Hermes agent
```

Each platform gets its own output format:
- **OpenCode**: `.opencode/skills/grant-writing/SKILL.md`
- **Claude Code**: `.claude/commands/grant-search.md` and `grant-draft.md`
- **OpenClaw**: `openclaw/system-prompt.md` and `tools.yaml`
- **Hermes**: (future)

The skills include funder-specific rubrics, heading taxonomies, and writing rules grounded in your archive. See [docs/skills.md](skills.md) for architecture details.

## 11. Ongoing maintenance

### Adding new documents

```bash
folio ingest --source new-grant.pdf --funder OAC --year 2026 --period "2026-2027" --rewrite
```

This converts, cleans, classifies, rewrites, and updates the wiki for a single document. Use `--no-wiki` to skip wiki update, or `--dry-run` to preview.

### Rebuilding the wiki

After adding several documents, recompile:

```bash
folio pipeline --stages wiki
```

Or if you've added new raw files:

```bash
folio pipeline --stages convert,clean,classify,rewrite,wiki
```

### Checking wiki health

```bash
folio audit                     # Dead links, thin articles, near-duplicates
```

Sage-wiki also has built-in health commands:
```bash
cd .folio/sage-wiki
sage-wiki status                # Source count, concept count
sage-wiki lint                  # 8 lint passes (completeness, style, quality, etc.)
sage-wiki coverage              # Compilation coverage table
sage-wiki diff                  # Pending changes since last compile
```

### Generating agentmap navigation

If agentmap is enabled, update section-level NAV blocks:

```bash
agentmap ./markdown/
```

## 12. Using the library

Once everything is set up, an AI agent with the grant-writing skill loaded can:

```bash
# Search the wiki for past OAC operating grants
sage-wiki search "OAC operating grant budget 2024"

# Query the wiki for specific information
sage-wiki query "How many OAC operating grants did we submit between 2020-2024?"

# Search markdown files directly
grep -r "accessibility" markdown/ --include="*.md"

# Find all applications by funder
grep -l 'funder: "OAC"' markdown/*.md

# agentmap section-level search (must be run from markdown/ directory)
cd markdown/
agentmap search "budget"                                    # find sections by heading
agentmap search "Exhibitions" OAC_*.md                     # filter by funder pattern
agentmap headings .                                         # show NAV trees for all files

# Read a specific section by NAV block offset
# (use line numbers from the AGENT:NAV block in the file)
```

### Using agentmap for section-level search

Agentmap generates `<!-- AGENT:NAV ... -->` blocks in each rewritten file that let agents jump directly to specific sections by line number without grep or full-file reads.

**Quick workflows:**
```bash
cd markdown/
agentmap search "accessibility"                             # find passages by heading
agentmap search "budget" OAC_*                              # budget sections in OAC files
agentmap headings .                                         # list all NAV trees
```

**After pipeline rewrite — bulk indexing:**
```bash
cd markdown/
agentmap index .             # generates skeletons for all unindexed files
agentmap next                # prompts for next unchecked file
# Write descriptions, save, then:
agentmap next                # advance; repeat until done
```

See the grant-writing skill for the full agentmap NAV workflow, or `agentmap --help` for all commands.

```bash
# Draft a new grant using past applications as reference
# (the agent does this using the grant-writing skill)
```

## Next steps

- Set up a git repo for your org library so the archive is version-controlled
- Add CI/CD to auto-rebuild the wiki on new commits
- Create a second org library if you manage multiple organizations
- Read [docs/pipelines.md](pipelines.md) for deep dive on each stage
- Read [docs/config.md](config.md) for every configuration option

## Troubleshooting

**"No funders configured"** — Edit `folio.yaml` and add entries under `funders:` (e.g., `OAC: "Ontario Arts Council"`).

**PDF conversion produces garbled text** — Try an alternative converter. Set `converter.type: "marker-pdf"` or `"pandoc"` in folio.yaml. Scanned/image-based PDFs won't convert cleanly with any tool.

**Pipeline fails on a specific file** — The manifest checkpoint system tracks per-file status. Fix the issue and re-run — folio will skip already-completed files. To force re-process a specific file, delete its entry from `markdown/manifest.json`.

**Costs higher than expected** — Review your classification config in `folio.yaml`. Files classified as `full` tier use more expensive LLM calls. Adjust thresholds or increase `skip` rules to reduce costs.

**Wiki not compiling** — Check `sage-wiki --version`. If not installed, set `wiki.type: "null"` in folio.yaml for markdown-only mode. Or install it: `go install github.com/xoai/sage-wiki@latest`.
