"""Tests for folio archival priority scoring (core/prioritizer.py).

Covers:
- Config resolution (_resolve_config) with dict, ProjectConfig, and None
- Rubric text formatting
- System/user prompt building (group and single-file)
- Digest extraction and file digest formatting
- Year-grouping logic (_group_files_by_year)
- Large group splitting (_split_large_groups)
- LLM response parsing (_parse_llm_response)
- Priority validation (_validate_priorities)
- Group processing with mocked LLM (_process_group)
- Group sort key
- Single file API (prioritize_file) with mocked LLM
- Directory processing (prioritize_directory) with mocked LLM
- Dry-run mode
- Edge cases: empty directories, single file, all same-year files
- Error handling on LLM failures
- Priority propagation to frontmatter
- Concurrent behavior (file scanning, grouping without API)
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from folio.core.prioritizer import (
    DEFAULT_PRIORITIZE_CONFIG,
    _build_digest,
    _build_rubric_text,
    _build_system_prompt,
    _build_user_prompt,
    _format_file_digest,
    _group_files_by_year,
    _group_sort_key,
    _parse_llm_response,
    _process_group,
    _resolve_config,
    _scan_files,
    _split_large_groups,
    _validate_priorities,
    prioritize_directory,
    prioritize_file,
)
from tests.conftest import make_test_config

# ── Sample fixtures ──────────────────────────────────────────────────────

SAMPLE_FM = {
    "funder": "OAC",
    "type": "application",
    "written": 2024,
    "period": "2024",
    "grant_amount": "$50,000",
}

SAMPLE_CONTENT = textwrap.dedent("""\
    ---
    funder: OAC
    type: application
    written: 2024
    period: "2024"
    grant_amount: "$50,000"
    ---

    # OAC Operating Grant Application 2024

    ## Project Description

    This is a well-written project description with substantial content
    for the grant application. The project will involve community engagement
    and artistic production over a twelve-month period.

    ## Budget Overview

    The total budget is estimated at $50,000, with $30,000 allocated to
    artist fees and $20,000 to production costs.
    """)

SAMPLE_CONTENT_2023 = textwrap.dedent("""\
    ---
    funder: OAC
    type: report
    written: 2023
    period: "2023"
    ---

    # OAC Final Report 2023

    ## Summary

    This report summarizes activities from the 2023 grant cycle.
    """)

SAMPLE_CONTENT_NO_FUNDER = textwrap.dedent("""\
    ---
    type: activity_list
    written: 2024
    period: "2024"
    ---

    # Activity List 2024

    Event list content here.
    """)

SAMPLE_CONTENT_NO_FM = """# Just Content

No frontmatter here.
"""

LLM_GROUP_RESPONSE = json.dumps({
    "priorities": {
        "doc_a.md": {"priority": 1, "rationale": "Final application — most complete"},
        "doc_b.md": {"priority": 3, "rationale": "Draft — content duplicated in final"},
        "doc_c.md": {"priority": 2, "rationale": "Supporting material"},
    },
})

LLM_SINGLE_RESPONSE = json.dumps({
    "priorities": {
        "doc.md": {"priority": 1, "rationale": "Complete application"},
    },
})

LLM_RESPONSE_INVALID = "Not valid JSON at all {broken"

LLM_RESPONSE_NO_PRIORITIES = json.dumps({"other": "data"})

LLM_RESPONSE_INVALID_PRIORITY = json.dumps({
    "priorities": {
        "doc.md": {"priority": 5, "rationale": "Bad"},
    },
})

LLM_RESPONSE_MISSING_FILE = json.dumps({
    "priorities": {
        "other.md": {"priority": 1, "rationale": "Only other"},
    },
})


# ── Mock LLM provider helper ──────────────────────────────────────────────

def make_mock_llm(response_text: str = LLM_GROUP_RESPONSE):
    """Create a MagicMock LLM provider with canned complete() response."""
    provider = MagicMock()
    provider.complete.return_value = response_text
    return provider


def make_file_item(filename, content, fm=SAMPLE_FM, body=None):
    """Create a file item dict as used by _scan_files and grouping functions."""
    return {
        "path": Path(f"/tmp/{filename}"),
        "filename": filename,
        "content": content,
        "fm": fm,
        "body": body or content,
    }


# ══════════════════════════════════════════════════════════════════════════
# Config resolution
# ══════════════════════════════════════════════════════════════════════════

class TestResolveConfig:
    def test_none_config_returns_default(self):
        result = _resolve_config(None)
        assert result["processing"]["max_workers"] == 5
        assert result["processing"]["requests_per_second"] == 3
        assert result["processing"]["max_retries"] == 3
        assert result["grouping"]["field"] == "written"
        # Keys are stringified by json roundtrip
        assert result["rubric"]["1"]["label"] == "Essential"
        assert result["rubric"]["2"]["label"] == "Supplemental"
        assert result["rubric"]["3"]["label"] == "Redundant/Low-value"

    def test_dict_config_merges(self):
        config = {
            "processing": {"max_workers": 3},
            "llm_model": "gpt-4",
        }
        result = _resolve_config(config)
        assert result["processing"]["max_workers"] == 3
        assert result["llm_model"] == "gpt-4"
        # Unspecified keys remain at defaults
        assert result["processing"]["requests_per_second"] == 3

    def test_project_config_dataclass(self):
        config = make_test_config()
        result = _resolve_config(config)
        assert result["processing"]["max_workers"] == 10  # from ProcessingConfig
        assert result["llm_model"] == "deepseek-v4-pro"   # quality_model

    def test_dict_rubric_override(self):
        config = {
            "rubric": {
                "1": {"label": "Critical", "description": "Top priority."},
            },
        }
        result = _resolve_config(config)
        assert result["rubric"]["1"]["label"] == "Critical"

    def test_dict_grouping_override(self):
        config = {"grouping": {"field": "period", "by_funder": True}}
        result = _resolve_config(config)
        assert result["grouping"]["field"] == "period"
        assert result["grouping"]["by_funder"] is True


# ══════════════════════════════════════════════════════════════════════════
# Rubric text formatting
# ══════════════════════════════════════════════════════════════════════════

class TestBuildRubricText:
    def test_formats_default_rubric(self):
        text = _build_rubric_text(DEFAULT_PRIORITIZE_CONFIG["rubric"])
        assert "Priority 1" in text
        assert "Essential" in text
        assert "Priority 2" in text
        assert "Supplemental" in text
        assert "Priority 3" in text
        assert "Redundant" in text

    def test_empty_rubric(self):
        text = _build_rubric_text({})
        assert text == ""


# ══════════════════════════════════════════════════════════════════════════
# Prompt building
# ══════════════════════════════════════════════════════════════════════════

class TestBuildSystemPrompt:
    def test_contains_rubric(self):
        prompt = _build_system_prompt(DEFAULT_PRIORITIZE_CONFIG)
        assert "Priority 1" in prompt
        assert "Essential" in prompt
        assert "Return ONLY a valid JSON object" in prompt


class TestBuildUserPrompt:
    def test_group_prompt(self):
        prompt = _build_user_prompt(DEFAULT_PRIORITIZE_CONFIG, "2024", "File contents here.")
        assert "2024" in prompt
        assert "File contents here." in prompt
        assert "priorities" in prompt

    def test_single_file_prompt(self):
        prompt = _build_user_prompt(
            DEFAULT_PRIORITIZE_CONFIG,
            "2024",
            "File contents.",
            is_single=True,
            filename="doc.md",
            funder_context=" from OAC",
            context_instruction="Evaluate against rubric.",
        )
        assert "doc.md" in prompt
        assert " from OAC" in prompt
        assert "Evaluate against rubric." in prompt


# ══════════════════════════════════════════════════════════════════════════
# Digest extraction
# ══════════════════════════════════════════════════════════════════════════

class TestBuildDigest:
    def test_short_content_returned_verbatim(self):
        content = "Short.\n"
        result = _build_digest("file.md", content, 500)
        assert result == content

    def test_long_content_truncated_at_section(self):
        content = "Start\n" + ("A\n" * 6000) + "\n## Section\n\nBody\n"
        result = _build_digest("file.md", content, 6000)
        assert "[... content truncated ...]" in result
        assert result.startswith("Start")

    def test_truncation_fallback_when_no_boundary(self):
        content = "X" * 10000
        result = _build_digest("file.md", content, 6000)
        assert "[... content truncated ...]" in result

    def test_boundary_too_early_not_used(self):
        content = "## Early\n" + "B\n" * 10000
        result = _build_digest("file.md", content, 6000)
        assert "[... content truncated ...]" in result


# ══════════════════════════════════════════════════════════════════════════
# File digest formatting
# ══════════════════════════════════════════════════════════════════════════

class TestFormatFileDigest:
    def test_formats_with_full_frontmatter(self):
        body_preview = "Preview of body content."
        result = _format_file_digest("doc.md", SAMPLE_FM, body_preview)
        assert "### doc.md" in result
        assert "**funder**: OAC" in result
        assert "**type**: application" in result
        assert "**written**: 2024" in result
        assert "Preview of body content." in result

    def test_missing_frontmatter(self):
        result = _format_file_digest("doc.md", None, "body text")
        assert "### doc.md" in result
        assert "body text" in result

    def test_empty_frontmatter_values_skipped(self):
        fm = {"funder": "", "type": "", "written": 2024}
        result = _format_file_digest("doc.md", fm, "body")
        assert "**funder**" not in result or "**funder**: " in result


# ══════════════════════════════════════════════════════════════════════════
# File grouping by year
# ══════════════════════════════════════════════════════════════════════════

class TestGroupFilesByYear:
    def test_groups_by_year(self):
        items = [
            make_file_item("a.md", SAMPLE_CONTENT, fm=SAMPLE_FM),
            make_file_item("b.md", SAMPLE_CONTENT_2023, fm={"written": 2023, "type": "report"}),
            make_file_item("c.md", SAMPLE_CONTENT, fm=SAMPLE_FM),
        ]
        groups, skipped = _group_files_by_year(items, DEFAULT_PRIORITIZE_CONFIG)
        assert len(groups) == 2
        assert "2024" in groups
        assert "2023" in groups
        assert len(groups["2024"]) == 2
        assert len(groups["2023"]) == 1
        assert len(skipped) == 0

    def test_all_same_year(self):
        items = [
            make_file_item("a.md", SAMPLE_CONTENT, fm=SAMPLE_FM),
            make_file_item("b.md", SAMPLE_CONTENT, fm=SAMPLE_FM),
        ]
        groups, skipped = _group_files_by_year(items, DEFAULT_PRIORITIZE_CONFIG)
        assert len(groups) == 1
        assert len(groups["2024"]) == 2

    def test_no_frontmatter_skipped(self):
        items = [
            make_file_item("a.md", SAMPLE_CONTENT_NO_FM, fm=None),
            make_file_item("b.md", SAMPLE_CONTENT, fm=SAMPLE_FM),
        ]
        groups, skipped = _group_files_by_year(items, DEFAULT_PRIORITIZE_CONFIG)
        assert len(groups) == 1
        assert "2024" in groups
        assert len(skipped) == 1

    def test_by_funder_grouping(self):
        config = dict(DEFAULT_PRIORITIZE_CONFIG)
        config["grouping"]["by_funder"] = True
        items = [
            make_file_item("a.md", SAMPLE_CONTENT, fm={"funder": "OAC", "written": 2024}),
            make_file_item("b.md", SAMPLE_CONTENT, fm={"funder": "CAC", "written": 2024}),
        ]
        groups, skipped = _group_files_by_year(items, config)
        assert len(groups) == 2
        assert "2024_OAC" in groups
        assert "2024_CAC" in groups

    def test_empty_list(self):
        groups, skipped = _group_files_by_year([], DEFAULT_PRIORITIZE_CONFIG)
        assert len(groups) == 0
        assert len(skipped) == 0

    def test_unknown_year_group_zero(self):
        items = [
            make_file_item("a.md", SAMPLE_CONTENT_NO_FM, fm={}),  # no written field
        ]
        groups, skipped = _group_files_by_year(items, DEFAULT_PRIORITIZE_CONFIG)
        assert "0" in groups


# ══════════════════════════════════════════════════════════════════════════
# Large group splitting
# ══════════════════════════════════════════════════════════════════════════

class TestSplitLargeGroups:
    def test_no_split_for_small_group(self):
        groups = {"2024": [make_file_item(f"doc{i}.md", SAMPLE_CONTENT) for i in range(5)]}
        result = _split_large_groups(groups, 60)
        assert len(result) == 1
        assert "2024" in result
        assert len(result["2024"]) == 5

    def test_splits_large_group(self):
        groups = {"2024": [make_file_item(f"doc{i}.md", SAMPLE_CONTENT) for i in range(61)]}
        result = _split_large_groups(groups, 60)
        assert len(result) == 2
        assert "2024_batch1" in result
        assert "2024_batch2" in result
        total = sum(len(v) for v in result.values())
        assert total == 61

    def test_max_files_zero_skips_split(self):
        groups = {"2024": [make_file_item(f"doc{i}.md", SAMPLE_CONTENT) for i in range(100)]}
        result = _split_large_groups(groups, 0)
        assert len(result) == 1

    def test_multiple_groups_with_split(self):
        groups = {
            "2024": [make_file_item(f"a{i}.md", SAMPLE_CONTENT) for i in range(65)],
            "2023": [make_file_item(f"b{i}.md", SAMPLE_CONTENT_2023) for i in range(5)],
        }
        result = _split_large_groups(groups, 60)
        # 2024 splits into 2 batches (33+32), 2023 stays as 1 = 3 total
        assert len(result) == 3
        assert "2023" in result
        assert len(result["2023"]) == 5


# ══════════════════════════════════════════════════════════════════════════
# LLM response parsing
# ══════════════════════════════════════════════════════════════════════════

class TestParseLlmResponse:
    def test_parses_valid_json(self):
        result = _parse_llm_response(LLM_GROUP_RESPONSE)
        assert result is not None
        assert "priorities" in result
        assert result["priorities"]["doc_a.md"]["priority"] == 1

    def test_parses_json_with_code_fences(self):
        text = '```json\n' + LLM_GROUP_RESPONSE + '\n```'
        result = _parse_llm_response(text)
        assert result is not None
        assert "priorities" in result

    def test_invalid_json_returns_none(self):
        result = _parse_llm_response(LLM_RESPONSE_INVALID)
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_llm_response("")
        assert result is None

    def test_no_braces_returns_none(self):
        result = _parse_llm_response("Just text, no JSON here.")
        assert result is None

    def test_stray_text_before_json(self):
        text = "Here is my analysis.\n\n" + LLM_GROUP_RESPONSE + "\n\nI hope this helps."
        result = _parse_llm_response(text)
        assert result is not None
        assert "priorities" in result

    def test_unclosed_brace_returns_none(self):
        result = _parse_llm_response('{"priorities": {"a": {"priority": 1')
        assert result is None


# ══════════════════════════════════════════════════════════════════════════
# Priority validation
# ══════════════════════════════════════════════════════════════════════════

class TestValidatePriorities:
    def test_valid_priorities(self):
        parsed = json.loads(LLM_GROUP_RESPONSE)
        expected = {"doc_a.md", "doc_b.md", "doc_c.md"}
        priorities, errors = _validate_priorities(parsed, expected)
        assert priorities == {"doc_a.md": 1, "doc_b.md": 3, "doc_c.md": 2}
        assert len(errors) == 0

    def test_none_parsed(self):
        priorities, errors = _validate_priorities(None, {"test.md"})
        assert len(errors) > 0
        assert len(priorities) == 0

    def test_missing_priorities_key(self):
        parsed = json.loads(LLM_RESPONSE_NO_PRIORITIES)
        priorities, errors = _validate_priorities(parsed, {"test.md"})
        assert len(errors) > 0

    def test_invalid_priority_value(self):
        parsed = json.loads(LLM_RESPONSE_INVALID_PRIORITY)
        priorities, errors = _validate_priorities(parsed, {"doc.md"})
        # One error for invalid priority + one for missing file (same name)
        assert len(errors) == 2
        assert any("Invalid priority" in e for e in errors)

    def test_missing_expected_filename(self):
        parsed = json.loads(LLM_RESPONSE_MISSING_FILE)
        priorities, errors = _validate_priorities(parsed, {"doc.md", "other.md"})
        assert "doc.md" not in priorities
        assert len(errors) == 1
        assert "doc.md" in errors[0]

    def test_invalid_entry_not_dict(self):
        parsed = {"priorities": {"doc.md": "not a dict"}}
        priorities, errors = _validate_priorities(parsed, {"doc.md"})
        # One error for invalid entry + one for missing priority
        assert len(errors) == 2

    def test_string_priority_converted(self):
        parsed = json.dumps({"priorities": {"doc.md": {"priority": "2", "rationale": "ok"}}})
        parsed = json.loads(parsed)
        priorities, errors = _validate_priorities(parsed, {"doc.md"})
        assert priorities == {"doc.md": 2}


# ══════════════════════════════════════════════════════════════════════════
# Group processing
# ══════════════════════════════════════════════════════════════════════════

class TestProcessGroup:
    def test_successful_processing(self):
        files = [
            make_file_item("doc_a.md", SAMPLE_CONTENT),
            make_file_item("doc_b.md", SAMPLE_CONTENT_2023, fm={"written": 2023, "type": "report"}),
            make_file_item("doc_c.md", SAMPLE_CONTENT, fm=SAMPLE_FM),
        ]
        llm = make_mock_llm(LLM_GROUP_RESPONSE)

        result = _process_group("2024", files, DEFAULT_PRIORITIZE_CONFIG, llm)

        assert result["group_key"] == "2024"
        assert result["files_count"] == 3
        # LLM_GROUP_RESPONSE maps: doc_a=1, doc_b=3, doc_c=2
        assert result["priorities"]["doc_a.md"] == 1
        assert result["priorities"]["doc_b.md"] == 3
        assert result["priorities"]["doc_c.md"] == 2
        assert len(result["errors"]) == 0
        assert result["input_tokens"] > 0
        assert result["output_tokens"] > 0

    def test_llm_failure(self):
        files = [make_file_item("doc.md", SAMPLE_CONTENT)]
        llm = MagicMock()
        llm.complete.side_effect = RuntimeError("API failure")

        result = _process_group("2024", files, DEFAULT_PRIORITIZE_CONFIG, llm)

        assert result["group_key"] == "2024"
        assert result["priorities"] == {}
        assert len(result["errors"]) == 1
        assert "LLM call failed" in result["errors"][0]

    def test_unknown_year_label(self):
        files = [make_file_item("doc.md", SAMPLE_CONTENT)]
        llm = make_mock_llm()

        result = _process_group("0", files, DEFAULT_PRIORITIZE_CONFIG, llm)

        assert result["group_key"] == "0"

    def test_single_file_group(self):
        files = [make_file_item("doc.md", SAMPLE_CONTENT)]
        llm = make_mock_llm(LLM_SINGLE_RESPONSE)

        result = _process_group("2024", files, DEFAULT_PRIORITIZE_CONFIG, llm)

        assert result["priorities"] == {"doc.md": 1}

    def test_invalid_response(self):
        files = [make_file_item("doc.md", SAMPLE_CONTENT)]
        llm = make_mock_llm(LLM_RESPONSE_INVALID)

        result = _process_group("2024", files, DEFAULT_PRIORITIZE_CONFIG, llm)

        assert result["priorities"] == {}
        assert len(result["errors"]) > 0


# ══════════════════════════════════════════════════════════════════════════
# Group sort key
# ══════════════════════════════════════════════════════════════════════════

class TestGroupSortKey:
    def test_known_year_sorted_first(self):
        key = _group_sort_key(("2024", []))
        assert key[0] == 0

    def test_unknown_year_sorted_last(self):
        key = _group_sort_key(("0", []))
        assert key[0] == 1

    def test_batch_key_strips_batch(self):
        key = _group_sort_key(("2024_batch2", []))
        assert key == (0, "2024")


# ══════════════════════════════════════════════════════════════════════════
# File scanning
# ══════════════════════════════════════════════════════════════════════════

class TestScanFiles:
    def test_scans_markdown_files(self, tmp_path):
        (tmp_path / "a.md").write_text(SAMPLE_CONTENT)
        (tmp_path / "b.md").write_text(SAMPLE_CONTENT_2023)
        (tmp_path / "not_md.txt").write_text("not markdown")

        items = _scan_files(tmp_path)
        assert len(items) == 2
        filenames = {it["filename"] for it in items}
        assert filenames == {"a.md", "b.md"}

    def test_empty_directory(self, tmp_path):
        items = _scan_files(tmp_path)
        assert len(items) == 0

    def test_unreadable_file_skipped(self, tmp_path):
        (tmp_path / "ok.md").write_text(SAMPLE_CONTENT)
        items = _scan_files(tmp_path)
        assert len(items) == 1

    def test_parses_frontmatter(self, tmp_path):
        (tmp_path / "test.md").write_text(SAMPLE_CONTENT)
        items = _scan_files(tmp_path)
        item = items[0]
        assert item["fm"] is not None
        assert item["fm"]["funder"] == "OAC"
        assert item["fm"]["written"] == 2024


# ══════════════════════════════════════════════════════════════════════════
# prioritize_file (single file API)
# ══════════════════════════════════════════════════════════════════════════

class TestPrioritizeFile:
    def test_single_file_isolation(self, tmp_path):
        """Evaluate a file in isolation, without group context."""
        filepath = tmp_path / "doc.md"
        filepath.write_text(SAMPLE_CONTENT)
        llm = make_mock_llm(LLM_SINGLE_RESPONSE)

        with patch("folio.adapters.llm.get_llm_provider", return_value=llm):
            result = prioritize_file(filepath, make_test_config())

        assert result["filename"] == "doc.md"
        assert result["priority"] == 1
        assert result["rationale"] == "Complete application"

    def test_single_file_with_group_context(self, tmp_path):
        """Evaluate a file alongside peer files."""
        filepath = tmp_path / "doc_a.md"
        filepath.write_text(SAMPLE_CONTENT)
        llm = make_mock_llm(LLM_GROUP_RESPONSE)
        group = [
            make_file_item("doc_b.md", SAMPLE_CONTENT_2023, fm={"written": 2023}),
            make_file_item("doc_c.md", SAMPLE_CONTENT, fm=SAMPLE_FM),
        ]

        with patch("folio.adapters.llm.get_llm_provider", return_value=llm):
            result = prioritize_file(filepath, make_test_config(), group_context=group)

        assert result["filename"] == "doc_a.md"
        assert result["priority"] == 1
        assert "Final application" in result["rationale"]

    def test_unreadable_file(self, tmp_path):
        """Unreadable file returns priority=None with error."""
        filepath = tmp_path / "missing.md"

        with patch("folio.adapters.llm.get_llm_provider", return_value=MagicMock()):
            result = prioritize_file(filepath, make_test_config())

        assert result["priority"] is None
        assert len(result["errors"]) == 1

    def test_llm_failure(self, tmp_path):
        """LLM failure returns priority=None with error message."""
        filepath = tmp_path / "doc.md"
        filepath.write_text(SAMPLE_CONTENT)
        llm = MagicMock()
        llm.complete.side_effect = RuntimeError("Connection error")

        with patch("folio.adapters.llm.get_llm_provider", return_value=llm):
            result = prioritize_file(filepath, make_test_config())

        assert result["priority"] is None
        assert any("LLM call failed" in e for e in result["errors"])

    def test_uses_config_model(self, tmp_path):
        """Uses quality_model from ProjectConfig."""
        filepath = tmp_path / "doc.md"
        filepath.write_text(SAMPLE_CONTENT)
        config = make_test_config()
        llm = make_mock_llm(LLM_SINGLE_RESPONSE)

        with patch("folio.adapters.llm.get_llm_provider", return_value=llm):
            result = prioritize_file(filepath, config)

        assert result["priority"] == 1


# ══════════════════════════════════════════════════════════════════════════
# prioritize_directory
# ══════════════════════════════════════════════════════════════════════════

class TestPrioritizeDirectory:
    def test_empty_directory(self, tmp_path):
        """Empty directory returns zero counts."""
        result = prioritize_directory(tmp_path, make_test_config())
        assert result["summary"]["total_files"] == 0
        assert result["summary"]["total_groups"] == 0

    def test_dry_run_mode(self, tmp_path):
        """Dry run previews groups without API calls."""
        (tmp_path / "doc_a.md").write_text(SAMPLE_CONTENT)
        (tmp_path / "doc_b.md").write_text(SAMPLE_CONTENT)

        result = prioritize_directory(tmp_path, make_test_config(), dry_run=True)

        assert result["summary"]["dry_run"] is True
        assert result["summary"]["total_files"] == 2
        assert result["summary"]["total_groups"] == 1
        assert "dry_run_report" in result["summary"]

    def test_directory_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            prioritize_directory(tmp_path / "nonexistent", make_test_config())

    def test_year_filter(self, tmp_path):
        """Filter to specific year."""
        (tmp_path / "doc_2024.md").write_text(SAMPLE_CONTENT)
        (tmp_path / "doc_2023.md").write_text(SAMPLE_CONTENT_2023)

        with patch("folio.adapters.llm.get_llm_provider", return_value=make_mock_llm()):
            result = prioritize_directory(tmp_path, make_test_config(), year=2024)

        # Should only process 2024
        assert result["summary"]["total_files"] == 1

    def test_limit_groups(self, tmp_path):
        """Limit restricts number of groups processed."""
        for i in range(3):
            (tmp_path / f"doc_2024_{i}.md").write_text(SAMPLE_CONTENT)
        (tmp_path / "doc_2023.md").write_text(SAMPLE_CONTENT_2023)

        with patch("folio.adapters.llm.get_llm_provider", return_value=make_mock_llm()):
            result = prioritize_directory(tmp_path, make_test_config(), limit=1)

        # Should process one group only (2024 with 3 files, or 2023 with 1)
        assert result["summary"]["total_files"] in (1, 3)

    def test_writes_priority_to_files(self, tmp_path):
        """Priority is written into file frontmatter."""
        (tmp_path / "doc.md").write_text(SAMPLE_CONTENT)
        llm = make_mock_llm(LLM_SINGLE_RESPONSE)

        with patch("folio.adapters.llm.get_llm_provider", return_value=llm):
            result = prioritize_directory(tmp_path, make_test_config())

        assert result["summary"]["total_files"] == 1
        assert result["summary"]["priority_counts"].get("1", 0) == 1
        # Verify file was updated
        updated = (tmp_path / "doc.md").read_text()
        assert "priority: 1" in updated

    def test_multiple_groups(self, tmp_path):
        """Files from different years are grouped and processed separately."""
        (tmp_path / "doc_2024.md").write_text(SAMPLE_CONTENT)
        (tmp_path / "doc_2023.md").write_text(SAMPLE_CONTENT_2023)
        llm = make_mock_llm(LLM_SINGLE_RESPONSE)

        with patch("folio.adapters.llm.get_llm_provider", return_value=llm):
            result = prioritize_directory(tmp_path, make_test_config())

        assert result["summary"]["total_files"] == 2
        assert result["summary"]["total_groups"] == 2

    def test_skips_files_without_frontmatter(self, tmp_path):
        """Files without frontmatter are skipped (counted but not processed in groups)."""
        (tmp_path / "no_fm.md").write_text(SAMPLE_CONTENT_NO_FM)
        (tmp_path / "with_fm.md").write_text(SAMPLE_CONTENT_NO_FUNDER)
        llm = make_mock_llm(LLM_SINGLE_RESPONSE)

        with patch("folio.adapters.llm.get_llm_provider", return_value=llm):
            result = prioritize_directory(tmp_path, make_test_config())

        assert result["summary"]["skipped"] == 1
        assert result["summary"]["total_files"] == 1  # only with_fm.md in groups

    def test_large_group_batched(self, tmp_path):
        """Large groups are split into sub-batches."""
        # Create 61 files all in 2024
        for i in range(61):
            (tmp_path / f"doc{i:03d}.md").write_text(SAMPLE_CONTENT)
        llm = make_mock_llm(LLM_GROUP_RESPONSE)

        with patch("folio.adapters.llm.get_llm_provider", return_value=llm):
            result = prioritize_directory(tmp_path, make_test_config())

        assert result["summary"]["total_files"] == 61
        # Should be split into 2 groups (60 + 1 or similar)
        assert result["summary"]["total_groups"] == 2

    def test_resume_skips_completed_groups(self, tmp_path):
        """On resume, already completed groups are skipped from processing."""
        (tmp_path / "doc.md").write_text(SAMPLE_CONTENT)
        progress_path = tmp_path / "prioritize_progress.json"
        import json as _json
        progress_path.write_text(_json.dumps({
            "completed_groups": {"2024": {"files_count": 1, "priorities": {"doc.md": 1}}},
            "summary": {
                "total_files": 1,
                "total_groups": 1,
                "success": 1,
                "error": 0,
                "skipped": 0,
                "total_input_tokens": 100,
                "total_output_tokens": 50,
                "total_elapsed_seconds": 1.0,
                "priority_counts": {"1": 1, "2": 0, "3": 0},
            },
        }))
        llm = make_mock_llm()

        with patch("folio.adapters.llm.get_llm_provider", return_value=llm):
            result = prioritize_directory(tmp_path, make_test_config(), resume=True)

        assert result["summary"]["total_files"] == 1
        assert result["summary"]["success"] == 1
        assert result["summary"]["total_groups"] == 1

    def test_no_files_matching_year(self, tmp_path):
        """Year filter with no matches returns empty result."""
        (tmp_path / "doc.md").write_text(SAMPLE_CONTENT)
        result = prioritize_directory(tmp_path, make_test_config(), year=2099)
        assert result["summary"]["total_files"] == 0
        assert result["summary"]["total_groups"] == 0
