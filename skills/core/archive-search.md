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

### Combined workflow

1. `sage-wiki search` → find which documents are relevant
2. `sage-wiki query` → synthesized answer with citations
3. `agentmap search "<heading>"` → exact section content from candidate docs
4. Read file at NAV offsets → verbatim text

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
