### sage-wiki (cross-document synthesis)

Best for: concept-level queries, Q&A with citations, finding which documents are relevant.

```bash
cd {wiki_path} && sage-wiki search "<query>"
sage-wiki query "<question>"
```

**Common patterns:**

```bash
# Find all applications for a funder
sage-wiki search "{funder_abbrev} application"

# Find budget information
sage-wiki query "What were {funder_abbrev} grant amounts by year?"

# Find demographics
sage-wiki query "{org_name} membership demographics"

# Find org overview
sage-wiki query "Describe {org_name}"
```
