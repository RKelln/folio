### sage-wiki (cross-document synthesis)

Best for: concept-level queries, Q&A with citations, finding which documents are relevant.

**All sage-wiki commands must be run from the wiki project directory.**

`sage-wiki search` uses the local keyword index (no API key needed).
`sage-wiki query` needs the LLM API key in the environment — load it from `.env` before querying:

```bash
cd {wiki_path}
sage-wiki search "<query>"

# For synthesized answers, set the API key first:
export $(grep {api_key_env} {wiki_path}/../../.env | xargs)
sage-wiki query "<question>"
```

If sage-wiki returns no results, verify `pwd` is `{wiki_path}`. If `query` returns 401 auth errors, the API key isn't set — run `export $(grep {api_key_env} {wiki_path}/../../.env | xargs)` first.

**Common patterns:**

```bash
cd {wiki_path}

# Find all applications for a funder (keyword search, no API key needed)
sage-wiki search "{funder_abbrev} application"

# Find budget information (keyword search)
sage-wiki search "budget operating"

# Synthesized Q&A (needs {api_key_env} from .env):
export $(grep {api_key_env} {wiki_path}/../../.env | xargs)
sage-wiki query "What were {funder_abbrev} grant amounts by year?"
sage-wiki query "{org_name} membership demographics"
sage-wiki query "Describe {org_name}"
```
