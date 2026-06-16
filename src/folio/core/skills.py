"""Skills generation — produce platform-specific agent skills from project config.

Reads templates from skills/core/ and skills/templates/ and fills
{placeholders} from the project configuration (folio.yaml).
"""

import logging
import re
from pathlib import Path

from folio.config.schema import ProjectConfig

logger = logging.getLogger(__name__)

try:
    from importlib.resources import files as _resources_files
    _PKG_DIR = Path(str(_resources_files("folio")))
    _SKILLS_DIR = _PKG_DIR.parent.parent / "skills"
except ImportError:
    _SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "skills"
_CORE_DIR = _SKILLS_DIR / "core"
_TEMPLATES_DIR = _SKILLS_DIR / "templates"

_PLATFORM_CHOICES = {"opencode", "claude", "openclaw", "hermes"}

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def generate_skills(
    config: ProjectConfig,
    platform: str,
    output_dir: Path | None = None,
) -> dict:
    """Generate platform-specific agent skills from project config.

    Args:
        config: Validated project configuration.
        platform: Target platform — "opencode", "claude", "openclaw", or "hermes".
        output_dir: Directory to write files to (default: current directory).

    Returns:
        {"files_written": [Path, ...], "warnings": [str, ...]}
    """
    if platform not in _PLATFORM_CHOICES:
        raise ValueError(
            f"Unknown platform: '{platform}'. Must be one of: "
            f"{', '.join(sorted(_PLATFORM_CHOICES))}"
        )

    out = Path(output_dir) if output_dir else Path.cwd()
    warnings: list[str] = []

    generators = {
        "opencode": _generate_opencode,
        "claude": _generate_claude,
        "openclaw": _generate_openclaw,
        "hermes": _generate_hermes,
    }

    files_written = generators[platform](config, out, warnings)
    return {"files_written": files_written, "warnings": warnings}


def build_context(config: ProjectConfig) -> dict:
    """Build the template context dict from project config."""
    org = config.org
    funders = config.funders
    doc_types = config.doc_types
    paths = config.paths

    org_slug = re.sub(r"[^a-z0-9]+", "-", org.name.lower()).strip("-")

    funder_rows = "".join(f"| {abbrev} | {name} |\n" for abbrev, name in sorted(funders.items()))

    funder_table = ("| Abbrev | Full Name |\n|--------|-----------|\n") + funder_rows

    doc_type_rows = "".join(f"| {t} |\n" for t in doc_types)

    doc_type_table = ("| Type |\n|------|\n") + doc_type_rows

    funder_concept_rows = "".join(
        (
            f"| {abbrev} grants | "
            f"`wiki/concepts/{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}.md` |\n"
        )
        for abbrev, name in sorted(funders.items())
    )

    funder_abbrev = sorted(funders.keys())[0] if funders else "FUNDER"

    return {
        "org_name": org.name,
        "org_description": org.description,
        "org_abbreviation": org.abbreviation,
        "org_slug": org_slug,
        "funder_table": funder_table,
        "funder_rows": funder_rows,
        "doc_type_table": doc_type_table,
        "doc_type_rows": doc_type_rows,
        "funder_concept_rows": funder_concept_rows,
        "funder_abbrev": funder_abbrev,
        "rewrite_md_path": paths.rewrite_md,
        "wiki_path": paths.wiki_project,
        "raw_archive_path": paths.raw_archive,
    }


def _build_funder_table(config: ProjectConfig) -> str:
    """Build a markdown table of funders: abbrev | full name."""
    funders = config.funders
    rows = "".join(f"| {abbrev} | {name} |\n" for abbrev, name in sorted(funders.items()))
    return ("| Abbrev | Full Name |\n|--------|-----------|\n") + rows


def _build_doc_type_table(config: ProjectConfig) -> str:
    """Build a markdown table of document types."""
    rows = "".join(f"| {t} |\n" for t in config.doc_types)
    return ("| Type |\n|------|\n") + rows


def _fill_template(template_path: Path, context: dict) -> str:
    """Read a template file and fill {placeholders} from context dict.

    Warns if any placeholder remains unfilled after substitution.
    """
    text = template_path.read_text()

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key in context:
            return str(context[key])
        return match.group(0)

    result = _PLACEHOLDER_RE.sub(_replace, text)

    unfilled = set(_PLACEHOLDER_RE.findall(result))
    if unfilled:
        logger.warning(
            "Unfilled placeholders in %s: %s",
            template_path.name,
            ", ".join(sorted(unfilled)),
        )

    return result


def _read_core(name: str) -> str:
    """Read and return a core skill template."""
    return (_CORE_DIR / name).read_text()


def _fill_core(name: str, context: dict) -> str:
    """Read a core skill template and fill placeholders."""
    return _fill_template(_CORE_DIR / name, context)


def _write_file(path: Path, content: str) -> Path:
    """Write content to path, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


# ── OpenCode ──────────────────────────────────────────────────────────


def _generate_opencode(
    config: ProjectConfig,
    output_dir: Path,
    warnings: list[str],
) -> list[Path]:
    """Generate OpenCode skill files.

    Writes to: {output_dir}/.opencode/skills/grant-writing/SKILL.md
    """
    ctx = build_context(config)
    description = (
        f"Search and draft grant applications using {config.org.name}'s historical "
        f"grant archive. Find precedent applications, extract boilerplate text, "
        f"retrieve budget figures and statistics, and compose new grant sections "
        f"grounded in real organizational data."
    )

    body_parts = [
        _fill_core("archive-search.md", ctx),
        _fill_core("grant-drafting.md", ctx),
        _fill_core("grant-writing-craft.md", ctx),
    ]

    frontmatter = f"""---
name: grant-writing
description: {description}
compatibility: opencode
metadata:
  audience: grant-writers
  repository: {config.project_name}
---

"""

    content = frontmatter + "\n".join(body_parts)
    path = _write_file(
        output_dir / ".opencode" / "skills" / "grant-writing" / "SKILL.md",
        content,
    )
    return [path]


# ── Claude Code ───────────────────────────────────────────────────────


def _generate_claude(
    config: ProjectConfig,
    output_dir: Path,
    warnings: list[str],
) -> list[Path]:
    """Generate Claude Code slash commands.

    Writes to: {output_dir}/.claude/commands/grant-search.md
              {output_dir}/.claude/commands/grant-draft.md
    """
    ctx = build_context(config)

    search_body = _fill_core("archive-search.md", ctx)
    search_content = f"# /grant-search\n\n{search_body}"
    search_path = _write_file(
        output_dir / ".claude" / "commands" / "grant-search.md",
        search_content,
    )

    draft_body = (
        _fill_core("grant-drafting.md", ctx) + "\n\n" + _fill_core("grant-writing-craft.md", ctx)
    )
    draft_content = f"# /grant-draft\n\n{draft_body}"
    draft_path = _write_file(
        output_dir / ".claude" / "commands" / "grant-draft.md",
        draft_content,
    )

    return [search_path, draft_path]


# ── OpenClaw ──────────────────────────────────────────────────────────


def _generate_openclaw(
    config: ProjectConfig,
    output_dir: Path,
    warnings: list[str],
) -> list[Path]:
    """Generate OpenClaw assistant config.

    Writes to: {output_dir}/openclaw/system-prompt.md
              {output_dir}/openclaw/tools.yaml
    """
    ctx = build_context(config)

    system_prompt = (
        "You are a grant-writing assistant for {org_name}. "
        "You search the organization's historical grant archive "
        "to find precedent applications, extract boilerplate text, "
        "retrieve budget figures and statistics, and compose new "
        "grant sections grounded in real organizational data.\n\n"
    ).format(**ctx)

    system_prompt += _fill_core("archive-search.md", ctx)
    system_prompt += "\n\n"
    system_prompt += _fill_core("grant-drafting.md", ctx)
    system_prompt += "\n\n"
    system_prompt += _fill_core("grant-writing-craft.md", ctx)

    system_prompt_path = _write_file(
        output_dir / "openclaw" / "system-prompt.md",
        system_prompt,
    )

    wiki_path = config.paths.wiki_project
    rewrite_md_path = config.paths.rewrite_md

    tools_yaml = f"""tools:
  - name: sage_wiki_search
    command: "cd {wiki_path} && sage-wiki search"
    description: "Search the compiled wiki for relevant documents"
  - name: sage_wiki_query
    command: "cd {wiki_path} && sage-wiki query"
    description: "Ask a question and get a synthesized answer with citations"
  - name: agentmap_search
    command: "cd {rewrite_md_path} && agentmap search"
    description: "Fuzzy-match a heading across documents and return section content"
  - name: agentmap_headings
    command: "cd {rewrite_md_path} && agentmap headings"
    description: "Show NAV trees for all documents"
"""

    tools_path = _write_file(
        output_dir / "openclaw" / "tools.yaml",
        tools_yaml,
    )

    return [system_prompt_path, tools_path]


# ── Hermes ────────────────────────────────────────────────────────────


def _generate_hermes(
    config: ProjectConfig,
    output_dir: Path,
    warnings: list[str],
) -> list[Path]:
    """Generate Hermes agent config.

    Writes to: {output_dir}/hermes/agent.yaml
    """
    wiki_path = config.paths.wiki_project
    rewrite_md_path = config.paths.rewrite_md

    agent_yaml = f"""name: {config.org.abbreviation}-grant-writer
description: >
  Grant-writing agent for {config.org.name}. Searches the historical grant archive
  using sage-wiki (cross-document synthesis) and agentmap (section-level search),
  then composes grant sections grounded in real organizational data.

system_prompt: |
  You are a grant-writing assistant for {config.org.name}.
  You search the organization's historical grant archive to find precedent
  applications, extract boilerplate text, retrieve budget figures and statistics,
  and compose new grant sections grounded in real organizational data.

  Use sage-wiki for cross-document synthesis and concept-level queries.
  Use agentmap for section-level heading search within documents.
  Always ground every claim in a specific source document.

tools:
  - sage_wiki_search:
      command: "cd {wiki_path} && sage-wiki search"
  - sage_wiki_query:
      command: "cd {wiki_path} && sage-wiki query"
  - agentmap_search:
      command: "cd {rewrite_md_path} && agentmap search"
  - agentmap_headings:
      command: "cd {rewrite_md_path} && agentmap headings"

skills:
  - search
  - draft
  - craft
"""

    path = _write_file(
        output_dir / "hermes" / "agent.yaml",
        agent_yaml,
    )
    return [path]
