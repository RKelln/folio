# Archive Search

How to search {org_name}'s grant archive to find precedent documents, budget figures, statistics, and boilerplate language.

## Archive layout

The folio pipeline produces searchable views of the documents:

| Path | Contents |
|------|----------|
| `{rewrite_md_path}` | All rewritten markdown files with YAML frontmatter |
| `{wiki_path}` | Compiled wiki — concept articles, summaries, ontology graph |
| `headings.yaml` | Per-funder canonical heading taxonomy — maps variant headings to canonical names |

**headings.yaml** tells you what sections exist per funder. Use it with `agentmap search "<heading>"` to find exact section content across documents. Each funder (OAC, TAC, CCA, BCAH) has its own set of canonical headings with variant forms.

## Funders

{funder_table}

## Document types

{doc_type_table}

## Search tools

{tool_sections}
