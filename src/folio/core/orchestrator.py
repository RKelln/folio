"""Agentic test orchestrator for folio skills validation.

Dispatches subagents with generated folio skills to perform real tasks
against an org library, then evaluates their output against criteria.

Two modes:
  manual  — prints the agent prompt for human dispatch (CI-safe)
  agent   — dispatches subagents and evaluates results (requires opencode)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from folio.config.loader import load_project_config
from folio.core.skills import generate_skills

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────

@dataclass
class EvalCriteria:
    must_contain: list[str] = field(default_factory=list)
    should_contain: list[str] = field(default_factory=list)
    min_source_count: int = 0
    min_files_found: int = 0
    min_years_found: int = 0
    min_facts: int = 0
    word_count_range: tuple[int, int] | None = None

    @classmethod
    def from_dict(cls, d: dict) -> EvalCriteria:
        return cls(
            must_contain=d.get("must_contain", []),
            should_contain=d.get("should_contain", []),
            min_source_count=d.get("min_source_count", 0),
            min_files_found=d.get("min_files_found", 0),
            min_years_found=d.get("min_years_found", 0),
            min_facts=d.get("min_facts", 0),
            word_count_range=(
                tuple(d["word_count_range"])
                if "word_count_range" in d
                else None
            ),
        )


@dataclass
class Scenario:
    id: str
    name: str
    description: str
    task: str
    evaluation: EvalCriteria
    skills_platform: str = "opencode"

    @classmethod
    def from_dict(cls, d: dict) -> Scenario:
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            task=d["task"],
            evaluation=EvalCriteria.from_dict(d.get("evaluation", {})),
            skills_platform=d.get("skills", "opencode"),
        )


@dataclass
class EvalResult:
    scenario_id: str
    status: str  # "pass" | "fail" | "error" | "manual"
    checks: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    output: str = ""
    prompt: str = ""


# ──────────────────────────────────────────────────────────────────────
# Prompt construction
# ──────────────────────────────────────────────────────────────────────

def build_agent_prompt(scenario: Scenario, config_path: Path, tmp_dir: Path) -> str:
    """Generate skills, then build the full agent prompt.

    Returns the complete prompt text to give to a subagent.
    """
    config = load_project_config(config_path)
    result = generate_skills(config, scenario.skills_platform, tmp_dir)
    skill_content = "\n".join(
        p.read_text() for p in result["files_written"]
    )

    return f"""{skill_content}

---

## Task: {scenario.name}

{scenario.task.strip()}

---

## Evaluation Criteria
{_format_criteria(scenario.evaluation)}

Respond with your complete answer following the specified format.
"""


def _format_criteria(criteria: EvalCriteria) -> str:
    lines = []
    if criteria.must_contain:
        lines.append(f"- Must contain: {', '.join(repr(c) for c in criteria.must_contain)}")
    if criteria.should_contain:
        lines.append(f"- Should contain: {', '.join(repr(c) for c in criteria.should_contain)}")
    if criteria.min_source_count:
        lines.append(f"- Minimum source references: {criteria.min_source_count}")
    if criteria.min_files_found:
        lines.append(f"- Minimum files found: {criteria.min_files_found}")
    if criteria.min_years_found:
        lines.append(f"- Minimum distinct years: {criteria.min_years_found}")
    if criteria.min_facts:
        lines.append(f"- Minimum facts reported: {criteria.min_facts}")
    if criteria.word_count_range:
        lines.append(f"- Word count range: {criteria.word_count_range[0]}-{criteria.word_count_range[1]}")
    return "\n".join(lines) if lines else "None specified"


# ──────────────────────────────────────────────────────────────────────
# Evaluation
# ──────────────────────────────────────────────────────────────────────

def evaluate(output: str, criteria: EvalCriteria) -> EvalResult:
    """Evaluate agent output against criteria.

    This is used in orchestrator mode (not agent mode, where opencode
    handles the subagent dispatch).
    """
    checks: dict[str, Any] = {}
    fail_reasons: list[str] = []

    for phrase in criteria.must_contain:
        present = phrase.lower() in output.lower()
        checks[f"must_contain:{phrase}"] = present
        if not present:
            fail_reasons.append(f"Missing required content: {phrase!r}")

    for phrase in criteria.should_contain:
        present = phrase.lower() in output.lower()
        checks[f"should_contain:{phrase}"] = present

    if criteria.min_source_count:
        sources = _count_source_refs(output)
        checks["source_count"] = sources
        if sources < criteria.min_source_count:
            fail_reasons.append(
                f"Insufficient sources: {sources} < {criteria.min_source_count}"
            )

    if criteria.min_files_found:
        files = _count_file_refs(output)
        checks["files_found"] = files
        if files < criteria.min_files_found:
            fail_reasons.append(
                f"Insufficient files: {files} < {criteria.min_files_found}"
            )

    if criteria.word_count_range:
        wc = _word_count(output)
        checks["word_count"] = wc
        lo, hi = criteria.word_count_range
        if wc < lo or wc > hi:
            fail_reasons.append(
                f"Word count {wc} outside range [{lo}, {hi}]"
            )

    if criteria.min_years_found:
        years = _count_years(output)
        checks["years_found"] = years
        if years < criteria.min_years_found:
            fail_reasons.append(
                f"Insufficient years: {years} < {criteria.min_years_found}"
            )

    if criteria.min_facts:
        facts = _count_facts(output)
        checks["facts_found"] = facts
        if facts < criteria.min_facts:
            fail_reasons.append(
                f"Insufficient facts: {facts} < {criteria.min_facts}"
            )

    return EvalResult(
        scenario_id="",
        status="fail" if fail_reasons else "pass",
        checks=checks,
        errors=fail_reasons,
        output=output,
    )


def _count_source_refs(text: str) -> int:
    """Count source references. Matches .md filenames in text."""
    return len(re.findall(r"[\w_-]+\.md", text))


def _count_file_refs(text: str) -> int:
    """Count unique .md file references."""
    files = set(re.findall(r"[\w_-]+\.md", text))
    return len(files)


def _word_count(text: str) -> int:
    return len(text.split())


def _count_years(text: str) -> int:
    """Count unique 4-digit years (2000-2099) in text."""
    years = set(re.findall(r"\b(20[0-2]\d|209\d)\b", text))
    return len(years)


def _count_facts(text: str) -> int:
    """Heuristic: count lines that look like facts (contain numbers or dates)."""
    lines = text.strip().split("\n")
    fact_lines = [
        l for l in lines
        if re.search(r"\b\d{4}\b", l) or re.search(r"\$\d[\d,]*", l)
    ]
    return len(fact_lines)


# ──────────────────────────────────────────────────────────────────────
# Scenario loading
# ──────────────────────────────────────────────────────────────────────

def load_scenarios(path: Path) -> list[Scenario]:
    """Load scenarios from a YAML file."""
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Invalid scenario file: {path} (expected mapping)")
    raw = data.get("scenarios", [data])
    return [Scenario.from_dict(s) for s in raw]


# ──────────────────────────────────────────────────────────────────────
# Orchestrator — manual mode
# ──────────────────────────────────────────────────────────────────────

def run_manual(
    scenarios: list[Scenario],
    config_path: Path,
    output_dir: Path,
) -> list[EvalResult]:
    """Manual mode: generate prompts and write them to files.

    Returns one result per scenario with status="manual".
    A human (or orchestrator agent) reads the prompt file and dispatches
    the subagent manually.
    """
    results: list[EvalResult] = []
    prompts_dir = output_dir / "agent_prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    for scenario in scenarios:
        prompt = build_agent_prompt(scenario, config_path, output_dir / "skills_cache")
        prompt_path = prompts_dir / f"{scenario.id}.md"
        prompt_path.write_text(prompt)
        results.append(EvalResult(
            scenario_id=scenario.id,
            status="manual",
            output=f"Prompt written to {prompt_path}",
            prompt=prompt,
        ))

    return results


# ──────────────────────────────────────────────────────────────────────
# Orchestrator — agent mode (requires opencode)
# ──────────────────────────────────────────────────────────────────────

def run_agent(
    scenarios: list[Scenario],
    config_path: Path,
    output_dir: Path,
    timeout_per_scenario: int = 300,
) -> list[EvalResult]:
    """Agent mode: dispatch subagents via opencode task tool.

    Each scenario is dispatched as a subagent. Results are collected
    and evaluated against the scenario's criteria.

    NOTE: This mode only works when running within opencode, as it
    requires access to the task dispatching mechanism.
    """
    results: list[EvalResult] = []

    for scenario in scenarios:
        prompt = build_agent_prompt(scenario, config_path, output_dir / "skills_cache")
        result = _dispatch_subagent(scenario, prompt, timeout_per_scenario)
        results.append(result)

    return results


def _dispatch_subagent(
    scenario: Scenario,
    prompt: str,
    timeout: int,
) -> EvalResult:
    """Dispatch a subagent task and evaluate the result.

    When running inside opencode, this uses the task tool.
    When running standalone, this attempts to use the opencode CLI.
    """
    try:
        # Try to use opencode's task dispatch
        output = _run_opencode_task(scenario, prompt, timeout)
        result = evaluate(output, scenario.evaluation)
        result.scenario_id = scenario.id
        result.output = output
        return result
    except Exception as exc:
        return EvalResult(
            scenario_id=scenario.id,
            status="error",
            errors=[f"Dispatch failed: {exc}"],
            output="",
            prompt=prompt,
        )


def _run_opencode_task(
    scenario: Scenario,
    prompt: str,
    timeout: int,
) -> str:
    """Run a task via subprocess opencode CLI.

    Falls back to returning the prompt if opencode is not available.
    """
    import subprocess
    import tempfile

    prompt_file = Path(tempfile.mkdtemp()) / "prompt.md"
    prompt_file.write_text(prompt)

    try:
        result = subprocess.run(
            [
                "opencode", "task",
                "--prompt", str(prompt_file),
                "--timeout", str(timeout),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"opencode task failed: {result.stderr}")

        data = json.loads(result.stdout)
        return data.get("output", data.get("result", result.stdout))
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        # opencode not available — write prompt to disk and return it
        raise RuntimeError(
            f"opencode task dispatch unavailable: {exc}\n"
            f"Prompt saved to: {prompt_file}"
        )


# ──────────────────────────────────────────────────────────────────────
# Report formatting
# ──────────────────────────────────────────────────────────────────────

def format_report(results: list[EvalResult], verbose: bool = False) -> str:
    """Format evaluation results as a markdown report."""
    lines = ["# folio Agent Test Report", ""]
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    manual = sum(1 for r in results if r.status == "manual")
    errors = sum(1 for r in results if r.status == "error")

    lines.append("## Summary")
    lines.append(f"- **Total scenarios**: {len(results)}")
    lines.append(f"- **Passed**: {passed}")
    lines.append(f"- **Failed**: {failed}")
    lines.append(f"- **Manual**: {manual}")
    lines.append(f"- **Errors**: {errors}")
    lines.append("")

    for result in results:
        lines.append(f"### {result.scenario_id} — {result.status.upper()}")
        if result.errors:
            for err in result.errors:
                lines.append(f"- **FAIL**: {err}")
        if verbose and result.checks:
            for check, val in sorted(result.checks.items()):
                icon = "\u2705" if val else "\u274c"
                lines.append(f"  {icon} {check}: {val}")
        if result.output and result.status != "manual":
            preview = result.output[:300]
            if len(result.output) > 300:
                preview += "..."
            lines.append("")
            lines.append("```")
            lines.append(preview)
            lines.append("```")
        lines.append("")

    return "\n".join(lines)
