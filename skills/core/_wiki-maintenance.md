### Wiki Maintenance

Keep the wiki healthy and discover issues before they affect grant-writing accuracy. All commands run from the wiki project directory.

**Quick health check:**
```bash
cd {wiki_path}
sage-wiki status                    # source count, concept count, pending
sage-wiki doctor                    # validate config and connectivity
sage-wiki coverage                  # compile status table per source
```

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
- After pipeline runs: `sage-wiki status && sage-wiki lint`
- After adding new documents: `sage-wiki diff` then recompile
- Weekly: `sage-wiki lint --pass staleness && sage-wiki verify --since 7d`
- Monthly: full `sage-wiki lint` + review lintlog
