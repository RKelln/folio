# Archive Search

How to search {org_name}'s grant archive to find precedent documents, budget figures, statistics, and boilerplate language.

## Archive layout

The folio pipeline produces two searchable views of the same documents:

| Path | Contents | Tool |
|------|----------|------|
| `{wiki_path}` | Compiled wiki — concept articles, summaries, ontology graph | `sage-wiki` |
| `{rewrite_md_path}` | Full dataset — all documents with YAML frontmatter | `agentmap` |

## Funders

{funder_table}

## Document types

{doc_type_table}

## Two search tools — when to use each

### sage-wiki (cross-document synthesis)

Best for: concept-level queries, Q&A with citations, finding which documents are relevant.

```bash
cd {wiki_path} && sage-wiki search "<query>"
sage-wiki query "<question>"
```

### agentmap (section-level search)

Best for: finding specific passages by heading name, navigating documents by section.

```bash
cd {rewrite_md_path}
agentmap search "<heading>"                 # fuzzy-match a heading, get section content
agentmap headings .                         # show NAV trees for all files
```

### agentmap NAV blocks — building the table of contents

Each rewritten document can carry an `<!-- AGENT:NAV ... -->` block that agentmap uses for section-level navigation. These blocks let agents jump directly to the right section by line number without grep or full-file reads.

**Single file workflow:**

```bash
cd {rewrite_md_path}
agentmap generate <file>     # writes skeleton with ~-prefixed descriptions
# rewrite each ~ description in the nav block (purpose, about fields)
agentmap update <file>       # refresh line numbers; flags changed sections
agentmap check <file>        # validate nav block is in sync before committing
```

**Bulk indexing (after pipeline rewrite):**

```bash
agentmap index .             # generates skeletons for all unindexed files
agentmap next                # prints prompt for next unchecked file
# agent rewrites ~ descriptions in that file, saves it, then:
agentmap next                # advance to next file; repeat until done
```

`agentmap next` handles the update + check-off loop automatically.

**NAV block rules for descriptions:**
- `purpose`: one-line file summary under 10 words; no commas
- `about`: one-line section summary under 10 words; never restate the heading; no commas
- Remove the `~` prefix after writing a real description
- Never hand-edit line numbers — `agentmap update` manages those

**Read a section by NAV offset:** `Read(offset=s, limit=n)` using the `s,n` values from the nav block entry.

### Combined workflow

1. `sage-wiki search` → find which documents are relevant
2. `sage-wiki query` → synthesized answer with citations
3. `agentmap search "<heading>"` → exact section content from candidate docs
4. Read AGENT:NAV block → jump to exact line offset with `Read(offset=s, limit=n)`
5. If NAV block is missing or stale → `agentmap generate <file>` then fill descriptions

## Reading metadata from any file

YAML frontmatter on every file in `{rewrite_md_path}`:

```yaml
---
funder: OAC
type: application
written: 2025
grant_amount: "$50,538"
priority: 1
errors: 0
---
```

## Common search patterns

```bash
# Find all applications for a funder
sage-wiki search "<funder> application"

# Find a specific section across a funder's applications
agentmap search "<section>" {rewrite_md_path}/{funder_abbrev}_*.md

# Find budget/financial information
sage-wiki query "What were {funder_abbrev} grant amounts by year?"
agentmap search "budget" {rewrite_md_path}/{funder_abbrev}_*

# Find org overview
sage-wiki query "Describe {org_name}"

# Find demographics
sage-wiki query "{org_name} membership demographics"
```
