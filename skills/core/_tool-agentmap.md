### agentmap (section-level search)

Best for: finding specific passages by heading name, navigating documents by section.

**All agentmap commands must be run from the markdown directory:**

```bash
cd {rewrite_md_path}
agentmap search "<heading>"                 # fuzzy-match a heading, get section content
agentmap headings .                         # show NAV trees for all files
```

If agentmap returns nothing, verify you're in the right directory with `pwd` — it must be the rewrite markdown directory (`{rewrite_md_path}`).

**Use headings.yaml to find canonical heading names per funder.** The `headings.yaml` file in the org library root maps variant headings (like "Exhibitions & Vector Festival") to their canonical form ("Exhibitions"). Search for the canonical name to get complete results across all variant headings.

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
cd {rewrite_md_path}
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

**Common patterns:**

```bash
cd {rewrite_md_path}

# Find a specific section across a funder's applications
agentmap search "<section>" {funder_abbrev}_*.md

# Find budget information by heading
agentmap search "budget" {funder_abbrev}_*

# Find all headings across all files
agentmap headings .

# Search for sections using canonical names from headings.yaml
agentmap search "Exhibitions" OAC_*.md
```
