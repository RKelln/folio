### Wiki Maintenance

Keep the wiki healthy and discover issues before they affect grant-writing accuracy. All commands run from the wiki project directory.

**Quick health check:**
```bash
cd {wiki_path}
sage-wiki status                    # source count, concept count, pending
sage-wiki doctor                    # validate config and connectivity
sage-wiki coverage                  # compile status table per source
```

### folio audit — Quality & Integrity Audit

`folio audit` scans the compiled wiki for quality, provenance, and structural issues. It replaces the need for external dedup and cleanup scripts.

**Run an audit:**
```bash
folio audit --wiki-dir {wiki_path}
folio audit --wiki-dir {wiki_path} --json     # structured output
folio audit --wiki-dir {wiki_path} --json | jq .issues.name_collisions
folio audit --wiki-dir {wiki_path} --fix      # apply deterministic safe fixes
```

**New check categories (in addition to existing lint checks):**

| Category | What it flags |
|----------|---------------|
| `provenance` | Articles with empty `sources: []` in frontmatter |
| `low_confidence` | Articles marked `confidence: low` |
| `placeholder_phrasing` | Body text containing known placeholder phrases (`"no specific"`, `"insufficient information exists"`, etc.) |
| `speculative_phrasing` | Hedging language (`"likely"`, `"may have been"`, `"unknown"`, etc.) |
| `truncation_suspects` | Generator boilerplate about missing data — requires a second signal (incomplete final line, missing closing `---`, or truncated table) to avoid false positives |
| `weak_sections` | Sections under configurable headers (default: `"Key Figures"`) that are empty or contain only placeholder phrases |
| `link_noise` | Malformed link-like tokens (`[text` without closing `]`) |
| `name_collisions` | Articles whose filenames normalize to the same stem — subtyped as `collision` (same content) or `content_divergent` (different content, should be merged) |

**Configuration via `folio.yaml` `audit:` section:**

All checks are configurable. Override any threshold or phrase list:

```yaml
audit:
  flag_sourceless: true
  flag_low_confidence: true
  placeholder_phrases:
    - "no specific"
    - "insufficient information exists"
  speculative_phrases:
    - "likely"
    - "unknown"
  truncation_require_second_signal: true
  weak_section_headers:
    - "Key Figures"
  flag_link_noise: true
  name_collision_enabled: true
  name_collision_content_divergence_threshold: 0.30
```

**The `--fix` flag** applies only trivially safe, reversible transforms:
- Removes completely empty weak sections (header + nothing under it)
- Escapes link noise (`[text` → `\[text`)

Placeholder and speculative phrasing are **advisory scan results only** — `--fix` never deletes content matching these phrases. Short keywords like `"no specific"` appear in legitimate sentences and cannot be safely auto-removed. Review placeholder hits manually or with an LLM agent.

**Quality improvement workflow:**
```bash
folio audit --wiki-dir {wiki_path}              # 1. Run audit (all 14 checks)
# 2. Review the report — placeholder/speculative hits need human/LLM judgment
folio audit --wiki-dir {wiki_path} --fix        # 3. Apply safe fixes only (links, empty sections)
folio audit --wiki-dir {wiki_path}              # 4. Re-run to verify
```

**Name collision detection** replaces external dedup scripts:
- Same stem (e.g., `OntarioArtsCouncil` and `ontario_arts_council`) with similar content → `collision` subtype (quarantine the lower-quality copy)
- Same stem with very different content → `content_divergent` subtype (merge manually, content is different)

**Find issues before they appear in grant drafts:**
```bash
cd {wiki_path}
sage-wiki lint                      # run all 8 lint passes
sage-wiki lint --pass completeness  # dead wikilinks to non-existent concepts
sage-wiki lint --pass style         # missing YAML frontmatter
sage-wiki lint --pass orphans       # concepts with no ontology relations
sage-wiki lint --pass consistency   # contradictory ontology relations
sage-wiki lint --pass connections   # semantically similar but unconnected concepts
sage-wiki lint --pass impute        # TODO/UNKNOWN/TBD placeholders, thin sections
sage-wiki lint --pass staleness     # articles older than 90 days
sage-wiki lint --pass quality       # low quality scores, compilation errors
sage-wiki lint --fix                # auto-fix style issues
sage-wiki lint --json               # structured output for programmatic use
```

**Lint reports are saved to `.sage/lintlog/` — review after each significant wiki update.**

**Track changes:**
```bash
cd {wiki_path}
sage-wiki diff                      # pending source changes since last compile
sage-wiki diff --json               # structured output
sage-wiki provenance OAC__2024_*.md # which articles came from a source
```

**LLM trust verification:**
```bash
cd {wiki_path}
sage-wiki verify --all              # grounding checks on all pending outputs
sage-wiki verify --since 24h        # only recent outputs
sage-wiki outputs list --state pending   # pending outputs needing review
sage-wiki outputs list --state conflict  # conflicting outputs
sage-wiki outputs promote <id>      # manually confirm an output
sage-wiki outputs reject <id>       # reject and delete a bad output
sage-wiki outputs resolve <id>      # resolve by picking one answer
```

**After adding new documents or fixing issues, always recompile:**
```bash
cd {wiki_path}
sage-wiki compile
```

**Typical maintenance cadence:**
- After pipeline runs: `folio audit --wiki-dir .` + `sage-wiki status && sage-wiki lint`
- After adding new documents: `sage-wiki diff` then recompile
- Weekly: `folio audit --wiki-dir .` + `sage-wiki lint --pass staleness && sage-wiki verify --since 7d`
- Monthly: full `folio audit --wiki-dir .` + `sage-wiki lint` + review lintlog
