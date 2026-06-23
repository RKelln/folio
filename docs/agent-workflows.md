# Agent Workflows

Concrete examples of how an AI agent uses a folio library day-to-day. Each example shows exact commands, expected output, and reasoning.

## Example 1: Drafting a grant application

**Task:** Write a new OAC Operating Grant application for 2026-2027.

### Step 1: Find past applications to the same funder

```bash
grep -l 'funder: "OAC"' markdown/*.md | head -20
```

Output: 45 OAC files. Filter to operating grants specifically:

```bash
grep -l 'funder: "OAC"' markdown/*Operating*.md
```

Output: ~8 past OAC operating grant applications.

### Step 2: Find the most recent and most successful ones

Check priority scores (1 = essential, 2 = supplemental, 3 = redundant):

```bash
grep 'priority: 1' markdown/OAC__*Operating__Application*.md | head -5
```

Output: 3 essential applications. Read the most recent:

```bash
head -50 markdown/OAC__2025-2027_OAC_Operating_(multi-year)__Application__Final.md
```

### Step 3: Extract boilerplate that doesn't change

```bash
cd markdown/
agentmap search "organization description" OAC__*Operating*.md
agentmap search "mandate" OAC__*Operating*.md
agentmap search "governance" OAC__*Operating*.md
```

These sections are nearly identical across years — copy the most recent version.

### Step 4: Get updated statistics from recent reports

```bash
cd .folio/sage-wiki/
sage-wiki query "What were the attendance numbers reported in the most recent OAC final report?"
sage-wiki search "audience engagement 2025"
```

### Step 5: Check budget figures

```bash
cd markdown/
agentmap search "budget" OAC__2025*
```

Read the budget section from the most recent approved application. Update numbers for the new year.

### Step 6: Verify funder requirements haven't changed

```bash
cd markdown/
agentmap headings OAC__*Operating__Application*.md
```

Compare heading structures across years. If the funder added new required sections, the most recent application will show them.

---

## Example 2: Answering a board question

**Task:** "How much funding have we received from all sources in the last 3 years?"

### Cross-funder query via wiki

```bash
cd .folio/sage-wiki/
sage-wiki query "What was the total funding received from all funders in 2023, 2024, and 2025?"
```

The wiki synthesizes across documents and can extract and sum figures.

### Verify with direct file search

```bash
grep -r "amount.*awarded\|total.*grant\|funding.*total" markdown/*2023* markdown/*2024* markdown/*2025* --include="*.md" -h | head -20
```

Cross-check the wiki's answer against the source documents.

---

## Example 3: Adding a new quarterly report

**Task:** The org just submitted a mid-year report to TAC. Add it to the library.

### Step 1: Ingest the file

```bash
folio ingest \
  --source archive/TAC_MidYear_Report_2026.docx \
  --funder TAC \
  --year 2026 \
  --period "2025-2026" \
  --doc-types report \
  --rewrite
```

This converts, cleans, classifies, and rewrites the file. Output:

```
Ingested: TAC__2026_Mid-Year_Report__Report__TAC_MidYear_Report_2026.md
Tier: light
Cost: $0.002
```

### Step 2: Verify the output

```bash
head -20 markdown/TAC__2026_Mid-Year_Report__Report__TAC_MidYear_Report_2026.md
```

Check frontmatter is correct, content looks clean.

### Step 3: Update the wiki

```bash
folio pipeline --stages wiki
```

The wiki recompiles, incorporating the new report.

### Step 4: Verify wiki health

```bash
folio audit
cd .folio/sage-wiki/ && sage-wiki status && sage-wiki lint --pass quality
```

---

## Example 4: Running wiki health checks and fixing issues

**Task:** Monthly maintenance check.

### Quick health scan

```bash
cd .folio/sage-wiki/
sage-wiki status
```

Output:
```
Sources: 200
Concepts: 834
Pending: 3
```

3 pending concepts need attention.

### Check what's pending

```bash
sage-wiki coverage
```

Shows which sources haven't been compiled. If it's the new TAC report from Example 3:

```bash
folio pipeline --stages wiki    # recompile
```

### Full lint

```bash
sage-wiki lint
```

Output might show:
- 2 dead wikilinks (completeness pass) — pages link to concepts that don't exist
- 1 stale article (staleness pass) — hasn't been updated in 120 days
- 0 style issues
- 0 quality issues

Fix dead links by finding the correct concept name:
```bash
sage-wiki search "concept name"
```

### Trust verification

```bash
sage-wiki verify --since 7d
```

If any outputs fail grounding checks:
```bash
sage-wiki outputs list --state conflict
sage-wiki outputs resolve <id>    # pick the correct answer
```

---

## Example 5: Onboarding a new staff member

**Task:** A new grant writer needs to understand the org's funding history and patterns.

### Step 1: Generate the grant-writing skill

```bash
folio skills --platform opencode
```

This creates `.opencode/skills/grant-writing/SKILL.md` with funder-specific rubrics, heading taxonomies, and writing rules.

### Step 2: Show them the wiki

The wiki at `wiki/` is a browsable knowledge base. Point them to key concept articles:
- Organization overview
- Funder profiles (OAC, TAC, CCA)
- Grant programs the org has applied to

### Step 3: Run a sample query together

```bash
cd .folio/sage-wiki/
sage-wiki query "What are the key elements of a successful OAC operating grant application based on our past submissions?"
```

This gives the new writer an immediate understanding of what works.

### Step 4: Show them how to search by section

```bash
cd markdown/
agentmap search "artistic mandate" OAC_*
agentmap search "community engagement" OAC_*
```

They can drill into specific sections across all applications without reading entire files.

---

## Example 6: Ingesting a scraped website

**Task:** The org's website has been scraped to markdown. Add the "About Us", "Board of Directors", and "Program History" pages to the archive.

### Step 1: Verify files have scraper headers

Each `.md` file must have a scraper header as its first non-blank line:

```
<!-- source: https://example.com/about | scraped: 2025-06-01T12:00:00+00:00 | hash: abc123def4567890 -->
```

### Step 2: Preview what would be staged

```bash
folio website --source ./scraped_pages/ --list
```

Shows each file's source URL, scraped date, derived slug, and whether it would stage successfully.

### Step 3: Dry-run the full ingestion

```bash
folio website --source ./scraped_pages/ --dry-run
```

Shows staging summary and estimated pipeline costs without writing files.

### Step 4: Stage only, skip pipeline

```bash
folio website --source ./scraped_pages/ --stages none
```

Files are written to `paths.raw_md` with proper frontmatter (`type: webpage`, `source_url`, `scraped_at`, `content_hash`). No pipeline stages run.

### Step 5: Run pipeline stages selectively

```bash
folio website --source ./scraped_pages/ --stages clean,classify,rewrite
```

### Step 6: Verify output

```bash
ls .folio/raw_md/*__webpage.md
head -15 .folio/raw_md/IA__2025-06-01__about__webpage.md
```

Check frontmatter includes `funder`, `type: "webpage"`, `written`, `source_url`, `scraped_at`, and `content_hash`.

---

## Example 7: Preparing for a funder meeting

**Task:** The ED has a meeting with CCA and needs to know: what have we applied for, what was funded, what's in progress?

### All CCA applications

```bash
grep -l 'funder: "CCA"' markdown/*.md
```

### Status overview via wiki

```bash
cd .folio/sage-wiki/
sage-wiki query "For CCA grants, list each application with its year, program name, and whether it was funded. Summarize the total amounts."
```

### Current in-progress grants

```bash
sage-wiki search "CCA active grant 2025 2026"
```

### Past successful applications to reference

```bash
sage-wiki query "What were the strongest elements of our successful CCA applications?"
```

---

## Common patterns cheat sheet

| I want to... | Command |
|-------------|---------|
| Find all files for a funder | `grep -l 'funder: "FUNDER"' markdown/*.md` |
| Find a section across all funder files | `cd markdown/ && agentmap search "section" FUNDER_*` |
| Get synthesized answer across documents | `cd .folio/sage-wiki/ && sage-wiki query "..."` |
| Search wiki by keyword | `cd .folio/sage-wiki/ && sage-wiki search "keyword"` |
| Read a specific section | `Read markdown/file.md offset=N limit=M` (from NAV block) |
| Check wiki health | `folio audit` or `cd .folio/sage-wiki/ && sage-wiki status` |
| Add one document | `folio ingest --source FILE --funder X --year Y --rewrite` |
| Ingest scraped website pages | `folio website --source DIR/ --stages clean,classify,rewrite` |
| Rebuild wiki | `folio pipeline --stages wiki` |
| Check what changed | `cd .folio/sage-wiki/ && sage-wiki diff` |
| List all NAV headings | `cd markdown/ && agentmap headings .` |
