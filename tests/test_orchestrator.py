"""Pytest integration for folio agentic skill tests.

Runs scenarios in "manual" mode by default (generates prompts for human review).
Use --agent-mode to dispatch subagents directly.

Usage:
  pytest tests/test_orchestrator.py -v
  pytest tests/test_orchestrator.py -v --agent-mode --openlink
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

SCENARIOS_DIR = Path(__file__).parent / "agent_scenarios"

IA_LIBRARY = Path(os.environ.get("IA_LIBRARY_PATH", Path(__file__).resolve().parents[2] / "ia-library"))
IA_CONFIG = IA_LIBRARY / "folio.yaml"
IA_AVAILABLE = IA_CONFIG.exists()


@pytest.fixture
def scenario_dir() -> Path:
    return SCENARIOS_DIR


@pytest.fixture
def ia_config_path() -> Path:
    return IA_CONFIG


# ──────────────────────────────────────────────────────────────────────
# Scenario validation tests (always run)
# ──────────────────────────────────────────────────────────────────────

def test_scenarios_are_valid_yaml():
    """All scenario files must be parseable YAML."""
    from folio.core.orchestrator import load_scenarios

    for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
        scenarios = load_scenarios(yaml_file)
        assert len(scenarios) > 0, f"No scenarios in {yaml_file.name}"


def test_scenarios_have_required_fields():
    """Every scenario must have id, name, and task."""
    from folio.core.orchestrator import load_scenarios

    for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
        scenarios = load_scenarios(yaml_file)
        for s in scenarios:
            assert s.id, f"Missing id in {yaml_file.name}"
            assert s.name, f"Missing name for {s.id}"
            assert s.task.strip(), f"Missing task for {s.id}"


def test_scenario_ids_are_unique():
    """No duplicate scenario IDs across all files."""
    from folio.core.orchestrator import load_scenarios

    all_ids: list[str] = []
    for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
        for s in load_scenarios(yaml_file):
            all_ids.append(s.id)
    assert len(all_ids) == len(set(all_ids)), (
        f"Duplicate scenario IDs: {[i for i in all_ids if all_ids.count(i) > 1]}"
    )


def test_scenarios_have_evaluation_criteria():
    """Each scenario should define at least one evaluation criterion."""
    from folio.core.orchestrator import load_scenarios

    for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
        scenarios = load_scenarios(yaml_file)
        for s in scenarios:
            crit = s.evaluation
            has_criteria = (
                crit.must_contain or crit.should_contain
                or crit.min_source_count or crit.min_files_found
                or crit.min_years_found or crit.min_facts
                or crit.word_count_range
            )
            assert has_criteria, (
                f"Scenario {s.id} has no evaluation criteria"
            )


# ──────────────────────────────────────────────────────────────────────
# Prompt generation tests (always run, don't need IA library)
# ──────────────────────────────────────────────────────────────────────

def test_prompts_can_be_generated(scenario_dir, minimal_folio_yaml):
    """Manual mode generates prompts for every scenario."""
    from folio.core.orchestrator import load_scenarios, run_manual

    config = minimal_folio_yaml / "folio.yaml"

    for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
        scenarios = load_scenarios(yaml_file)
        results = run_manual(scenarios, config, minimal_folio_yaml / "output")
        assert len(results) == len(scenarios)
        for result in results:
            assert result.status == "manual"
            assert result.prompt, f"Empty prompt for {result.scenario_id}"

        # Verify prompt files were written
        for s in scenarios:
            prompt_file = minimal_folio_yaml / "output" / "agent_prompts" / f"{s.id}.md"
            assert prompt_file.exists(), f"Missing prompt file for {s.id}"
            content = prompt_file.read_text()
            assert s.name in content
            assert len(content) > 100, f"Prompt too short for {s.id}"


def test_prompt_includes_task(scenario_dir, minimal_folio_yaml):
    """Generated prompts must include the scenario task text."""
    from folio.core.orchestrator import load_scenarios, run_manual

    config = minimal_folio_yaml / "folio.yaml"

    for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
        for scenario in load_scenarios(yaml_file):
            results = run_manual([scenario], config, minimal_folio_yaml / "output")
            prompt = results[0].prompt
            # Task text should appear in the prompt (normalize whitespace)
            task_normalized = " ".join(scenario.task.split())
            prompt_normalized = " ".join(prompt.split())
            first_30_words = " ".join(task_normalized.split()[:30])
            assert first_30_words in prompt_normalized, (
                f"Task not found in prompt for {scenario.id}"
            )


# ──────────────────────────────────────────────────────────────────────
# IA library integration (requires ia-library to be set up)
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not IA_AVAILABLE, reason="IA library not available")
class TestIALibraryOrchestrator:
    """End-to-end tests using the real InterAccess library."""

    def test_manual_mode_against_ia_library(self, scenario_dir, tmp_path):
        """Generate prompts for all scenarios against the real IA config."""
        from folio.core.orchestrator import load_scenarios, run_manual

        for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
            scenarios = load_scenarios(yaml_file)
            results = run_manual(scenarios, IA_CONFIG, tmp_path / "ia_output")
            assert len(results) == len(scenarios)
            for result in results:
                assert result.status == "manual"
                assert len(result.prompt) > 200, (
                    f"Prompt too short for {result.scenario_id}"
                )
                # Prompt must reference actual IA paths
                assert "./markdown/" in result.prompt or "markdown" in result.prompt
                assert "InterAccess" in result.prompt

    def test_prompts_contain_ia_funders(self, scenario_dir, tmp_path):
        """IA prompts must reference the configured funders."""
        from folio.core.orchestrator import load_scenarios, run_manual

        for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
            scenarios = load_scenarios(yaml_file)
            results = run_manual(scenarios, IA_CONFIG, tmp_path / "ia_output")

        # Collect all prompt text and check for funder references
        all_text = " ".join(r.prompt for r in results)
        for funder in ("OAC", "TAC", "CCA", "BCAH", "Ontario Arts Council",
                       "Toronto Arts Council", "Canada Council"):
            assert funder in all_text, f"Funder {funder!r} not in any prompt"

    def test_output_size_reasonable(self, scenario_dir, tmp_path):
        """Prompts should not be excessively large."""
        from folio.core.orchestrator import load_scenarios, run_manual

        for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
            scenarios = load_scenarios(yaml_file)
            results = run_manual(scenarios, IA_CONFIG, tmp_path / "ia_output")

        for result in results:
            prompt_size = len(result.prompt)
            assert prompt_size < 100_000, (
                f"Prompt for {result.scenario_id} too large: {prompt_size} chars"
            )


# ──────────────────────────────────────────────────────────────────────
# Evaluation logic tests
# ──────────────────────────────────────────────────────────────────────

class TestEvaluation:
    def test_pass_on_all_criteria_met(self):
        from folio.core.orchestrator import evaluate, EvalCriteria

        output = "The OAC grant application covers years 2015-2024.\n"
        output += "Source: OAC__2024_grant.md, OAC__2023_grant.md"
        criteria = EvalCriteria(
            must_contain=["OAC", "grant"],
            min_source_count=2,
        )
        result = evaluate(output, criteria)
        assert result.status == "pass"

    def test_fail_on_missing_must_contain(self):
        from folio.core.orchestrator import evaluate, EvalCriteria

        criteria = EvalCriteria(must_contain=["MISSING_PHRASE"])
        result = evaluate("Some output without the phrase.", criteria)
        assert result.status == "fail"
        assert any("MISSING_PHRASE" in e for e in result.errors)

    def test_fail_on_insufficient_sources(self):
        from folio.core.orchestrator import evaluate, EvalCriteria

        criteria = EvalCriteria(min_source_count=5)
        result = evaluate("Only one ref: - doc.md", criteria)
        assert result.status == "fail"

    def test_fail_on_word_count_out_of_range(self):
        from folio.core.orchestrator import evaluate, EvalCriteria

        criteria = EvalCriteria(word_count_range=(10, 20))
        result = evaluate("one two three", criteria)
        assert result.status == "fail"

    def test_pass_on_word_count_in_range(self):
        from folio.core.orchestrator import evaluate, EvalCriteria

        criteria = EvalCriteria(word_count_range=(1, 10))
        result = evaluate("one two three", criteria)
        assert result.status == "pass"

    def test_case_insensitive_must_contain(self):
        from folio.core.orchestrator import evaluate, EvalCriteria

        criteria = EvalCriteria(must_contain=["interaccess"])
        result = evaluate("InterAccess is an arts organization.", criteria)
        assert result.status == "pass"

    def test_year_counting(self):
        from folio.core.orchestrator import evaluate, EvalCriteria

        criteria = EvalCriteria(min_years_found=3)
        result = evaluate("Years: 2020, 2021, 2022, 2023, 2024", criteria)
        assert result.status == "pass"

    def test_json_output(self, tmp_path):
        from folio.core.orchestrator import format_report, EvalResult

        results = [
            EvalResult("test-1", "pass", {"must_contain:OK": True}),
            EvalResult("test-2", "fail", {"must_contain:X": False}, ["X missing"]),
        ]
        report = format_report(results)
        assert "PASS" in report
        assert "FAIL" in report
        assert "X missing" in report
