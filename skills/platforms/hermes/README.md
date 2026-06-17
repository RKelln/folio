# Hermes Agent Platform Wrapper

This directory is a placeholder for the Hermes Agent platform integration. Skill generation for Hermes uses the [agentskills.io](https://agentskills.io/specification) open standard (`SKILL.md` format).

## How Hermes loads skills

Hermes Agent discovers skills in these directories:

1. **Primary:** `~/.hermes/skills/` — skills are auto-discovered, with `SKILL.md` files as slash commands
2. **External:** `~/.agents/skills/` — shared across agentskills.io-compatible tools
3. **Workspace context:** Loads `AGENTS.md` from the project root

## Generated output

Running `folio skills --platform hermes` produces:

```
hermes/skills/grant-writing/SKILL.md    # agentskills.io format with filled templates
```

Copy the `grant-writing/` directory to `~/.hermes/skills/` or `~/.agents/skills/` to make it available as a Hermes slash command.

## Bootstrap

```bash
folio install-agent --platform hermes
```

Writes `AGENTS.md` (workspace context) and generates the skills directory.

## References

- [Hermes Agent Docs — Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
- [agentskills.io Specification](https://agentskills.io/specification)
- [Hermes Agent GitHub](https://github.com/NousResearch/hermes-agent)
