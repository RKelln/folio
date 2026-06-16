### File search (on-disk markdown)

The `{rewrite_md_path}` directory contains all rewritten markdown files with YAML frontmatter.

Use standard file search tools to find and read documents:
- `grep` or `rg` — search text across files: `rg "grant_amount" {rewrite_md_path}/`
- `glob` — find files by name pattern: `glob("{rewrite_md_path}/OAC_*.md")`
- `Read` — read files with offset/limit for large documents

**Reading metadata:** Every file in `{rewrite_md_path}` has YAML frontmatter:

```yaml
---
funder: OAC
type: application
written: 2025
grant_amount: "$50,538"
priority: 1
---
```

Use `Read(filePath, offset=0, limit=30)` to see the frontmatter without loading the entire file.

**Common patterns:**

```bash
# Find all applications for a funder by filename
glob("{rewrite_md_path}/{funder_abbrev}_*.md")

# Search for budget figures across all files
rg "grant_amount" {rewrite_md_path}/

# Read a specific file's frontmatter
Read(offset=0, limit=30) on {rewrite_md_path}/{funder_abbrev}_2025_Project.md
```
