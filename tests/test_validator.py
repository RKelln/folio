"""Tests for deterministic file validation in folio.core.validator."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from folio.core.validator import (
    validate_frontmatter,
    validate_content,
    validate_file_size,
    validate_headings,
    validate_placeholders,
    validate_file,
    validate_directory,
)
from folio.config.schema import ProjectConfig
from tests.conftest import make_test_config


# ── Helpers ──────────────────────────────────────────────────────────────────────

_VALID_FM = """---
funder: OAC
type: application
written: 2024
priority: 2
---

This is a test document with sufficient content to pass validation checks.
It contains multiple lines of meaningful text that should register as proper
content rather than corruption or placeholder patterns.
"""

_VALID_FM_TAC = """---
funder: TAC
type: report
written: 2023
priority: 1
---

## Project Summary

This is a detailed report document with multiple sections and substantial
content in each section to avoid thin-section and short-lines flags.

## Budget Overview

The budget for this project includes all the necessary line items covering
personnel, materials, equipment, travel, and other direct costs.

## Outcomes

The project achieved all of its stated goals and objectives within the
approved timeframe and budget parameters established at the outset.
"""

_NO_FM = """This document has no frontmatter at all.

It just contains plain text with some markdown formatting.

## Section One

Content for section one of this report document.

"""

_ONLY_FM = """---
funder: OAC
type: application
written: 2024
---
"""

_EMPTY_TEXT = ""

_WHITESPACE_ONLY = "   \n\n  \n  "

_BIG_VALID_FM = """---
funder: OAC
type: application
written: 2024
priority: 2
---

This is a test document with sufficient content to pass validation checks.
It contains multiple lines of meaningful text that should register as proper
content rather than corruption or placeholder patterns. The document has been
padded with additional sentences to ensure the file size exceeds the minimum
threshold of five hundred bytes which is required by the file size validator.
This padding text discusses the project scope, objectives, methodology, and
expected outcomes in a comprehensive manner suitable for grant applications.
The organization has extensive experience in delivering arts programming and
community engagement initiatives across multiple regions and demographics.
Funding from the Ontario Arts Council would support core operational costs
including staff salaries, venue rental, marketing, and artist fees for the
upcoming fiscal year. The project timeline spans twelve months from April to
March with quarterly reporting milestones and a final evaluation report.
"""


_BINARY_LIKE = """---
funder: OAC
type: report
written: 2025
---

\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f
\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f
"""

_CORRUPTED = """---
funder: OAC
type: application
written: 2024
---

a
b
c
d
e
f
g
h
i
j
k
l
m
n
o
p
q
r
s
t
u
v
w
x
y
z
1
2
3
4
5
6
7
8
9
0
"""

_CORRUPTED_DIGITS = """---
funder: OAC
type: application
written: 2024
---

1
12
123
1234
12345
56
789
0000
42
99
"""

_SHORT_LINES = """---
funder: OAC
type: application
written: 2024
---

Hi.
Ok.
Yes.
No.
Go.
Do.
Be.
"""

_FORM_CHROME_TEXT = """---
funder: OAC
type: application
written: 2024
---

## Application Form

Please enter your name: _______________
Please enter your address: _______________
Please enter your phone: _______________
Please enter your email: _______________
Date of birth: ____/____/____
Date of application: ____/____/____
Date of signature: ____/____/____
Signature: _________________
Signature of applicant: _________________
Signature of witness: _________________
Check this box: [ ] I agree
Check this box: [ ] I consent
Check this box: [ ] I confirm
Office use only: _________________
Office use only date: _________________
Office use only ref: _________________
Reference number: ABC-12345
Reference number: DEF-67890
Reference number: GHI-11111
Reference number: JKL-22222
Reference number: MNO-33333
Reference number: PQR-44444
Reference number: STU-55555
Reference number: VWX-66666
Reference number: YZA-77777
"""




_PLACEHOLDER_TEXT = """---
funder: OAC
type: application
written: 2024
---

## Summary

[TODO] Need to add project description here.

## Budget

[FIXME] Update budget figures for 2024.

[UNKNOWN] Source of matching funds.

## Timeline

[TBD] Final completion date.

??? Not sure about this section.

{placeholder} More details coming soon.
"""

_HEADINGS_DOC = """---
funder: TAC
type: report
written: 2024
---

## Project Summary

This is the project summary section with enough content to avoid the thin
section flag. It describes the project in reasonable detail and provides
context for the reader.

## Budget Overview

Another substantial section with budget details, line items, and financial
analysis that covers all the required information for a proper report.

## Missing Section

Very short.
"""

_HEADINGS_CONFIG = {
    "TAC": ["Project Summary", "Budget Overview", "Outcomes", "Timeline"],
    "OAC": ["Project Description", "Budget", "Work Plan"],
}


# ── validate_frontmatter ───────────────────────────────────────────────────────

class TestValidateFrontmatter:
    """Tests for validate_frontmatter()."""

    def test_valid_frontmatter_passes(self):
        """Frontmatter with all required fields and valid funder produces no issues."""
        config = make_test_config()
        issues = validate_frontmatter(_VALID_FM, config)
        assert issues == []

    def test_missing_frontmatter_flagged(self):
        """Document with no YAML frontmatter produces missing_frontmatter issue."""
        config = make_test_config()
        issues = validate_frontmatter(_NO_FM, config)
        assert len(issues) == 1
        assert issues[0]["issue_type"] == "missing_frontmatter"

    def test_missing_required_field_funder(self):
        """Missing 'funder' field produces missing_field issue."""
        config = make_test_config()
        text = "---\ntype: application\nwritten: 2024\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        missing = [i for i in issues if i["issue_type"] == "missing_field"]
        assert any(i["missing"] == "funder" for i in missing)

    def test_missing_required_field_type(self):
        """Missing 'type' field produces missing_field issue."""
        config = make_test_config()
        text = "---\nfunder: OAC\nwritten: 2024\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        missing = [i for i in issues if i["issue_type"] == "missing_field"]
        assert any(i["missing"] == "type" for i in missing)

    def test_missing_required_field_written(self):
        """Missing 'written' field produces missing_field issue."""
        config = make_test_config()
        text = "---\nfunder: OAC\ntype: application\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        missing = [i for i in issues if i["issue_type"] == "missing_field"]
        assert any(i["missing"] == "written" for i in missing)

    def test_null_field_flagged_as_missing(self):
        """A field set to None is treated as missing."""
        config = make_test_config()
        text = "---\nfunder: null\ntype: application\nwritten: 2024\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        missing = [i for i in issues if i["issue_type"] == "missing_field"]
        assert any(i["missing"] == "funder" for i in missing)

    def test_invalid_funder_flagged(self):
        """Funder not in config.funders produces invalid_funder issue."""
        config = make_test_config()
        text = "---\nfunder: NASA\ntype: application\nwritten: 2024\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        invalid = [i for i in issues if i["issue_type"] == "invalid_funder"]
        assert len(invalid) == 1
        assert invalid[0]["value"] == "NASA"
        assert "OAC" in invalid[0]["valid_funders"]

    def test_funder_check_skipped_when_config_has_no_funders(self):
        """When config.funders is empty, no invalid_funder issue is raised."""
        config = make_test_config(funders={})
        text = "---\nfunder: Anything\ntype: application\nwritten: 2024\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        assert not any(i["issue_type"] == "invalid_funder" for i in issues)

    def test_invalid_doc_type_flagged(self):
        """Doc type not in config.doc_types produces invalid_doc_type issue."""
        config = make_test_config(doc_types=["application", "report"])
        text = "---\nfunder: OAC\ntype: budget, invoice\nwritten: 2024\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        invalid = [i for i in issues if i["issue_type"] == "invalid_doc_type"]
        assert len(invalid) == 1
        assert "budget" in invalid[0]["invalid"]

    def test_doc_type_check_skipped_when_no_doc_types(self):
        """When config.doc_types is empty, no invalid_doc_type issue is raised."""
        config = make_test_config(doc_types=[])
        text = "---\nfunder: OAC\ntype: anything\nwritten: 2024\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        assert not any(i["issue_type"] == "invalid_doc_type" for i in issues)

    def test_valid_single_doc_type_passes(self):
        """A single valid doc type produces no issues."""
        config = make_test_config(doc_types=["application", "report", "budget"])
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        assert not any(i["issue_type"] == "invalid_doc_type" for i in issues)

    def test_valid_comma_separated_doc_types_pass(self):
        """Comma-separated valid doc types produce no issues."""
        config = make_test_config(doc_types=["application", "report", "budget"])
        text = "---\nfunder: OAC\ntype: application, report\nwritten: 2024\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        assert not any(i["issue_type"] == "invalid_doc_type" for i in issues)

    def test_priority_out_of_range_flagged(self):
        """Priority outside 1-3 range produces invalid_priority issue."""
        config = make_test_config()
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\npriority: 5\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        invalid = [i for i in issues if i["issue_type"] == "invalid_priority"]
        assert len(invalid) == 1
        assert invalid[0]["value"] == 5

    def test_priority_zero_flagged(self):
        """Priority 0 (below range) produces invalid_priority issue."""
        config = make_test_config()
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\npriority: 0\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        assert any(i["issue_type"] == "invalid_priority" for i in issues)

    def test_priority_non_integer_flagged(self):
        """Non-integer priority value produces invalid_priority issue."""
        config = make_test_config()
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\npriority: high\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        invalid = [i for i in issues if i["issue_type"] == "invalid_priority"]
        assert len(invalid) == 1

    def test_valid_priority_passes(self):
        """Priority 1, 2, or 3 produces no issues."""
        config = make_test_config()
        for p in [1, 2, 3]:
            text = f"---\nfunder: OAC\ntype: application\nwritten: 2024\npriority: {p}\n---\n\nContent."
            issues = validate_frontmatter(text, config)
            assert not any(i["issue_type"] == "invalid_priority" for i in issues)

    def test_priority_missing_is_ok(self):
        """No priority field is acceptable (optional)."""
        config = make_test_config()
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        assert not any(i["issue_type"] == "invalid_priority" for i in issues)

    def test_negative_errors_value_flagged(self):
        """Negative errors value produces negative_errors issue."""
        config = make_test_config()
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\nerrors: -3\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        invalid = [i for i in issues if i["issue_type"] == "negative_errors"]
        assert len(invalid) == 1
        assert invalid[0]["value"] == -3

    def test_non_integer_errors_ignored(self):
        """Non-integer errors value is silently skipped."""
        config = make_test_config()
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\nerrors: nope\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        assert not any(i["issue_type"] == "negative_errors" for i in issues)

    def test_valid_errors_passes(self):
        """Non-negative integer errors produces no issues."""
        config = make_test_config()
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\nerrors: 0\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        assert not any(i["issue_type"] == "negative_errors" for i in issues)

    def test_config_without_funders_attr_handled(self):
        """Config without 'funders' attribute is handled gracefully."""
        class NoFundersConfig:
            doc_types = []
        issues = validate_frontmatter(_VALID_FM, NoFundersConfig())
        assert not any(i["issue_type"] == "invalid_funder" for i in issues)


# ── validate_content ───────────────────────────────────────────────────────────

class TestValidateContent:
    """Tests for validate_content()."""

    def test_empty_text_flagged(self):
        """Completely empty text produces empty_body issue."""
        config = {}
        issues = validate_content(_EMPTY_TEXT, config)
        assert len(issues) == 1
        assert issues[0]["issue_type"] == "empty_body"

    def test_whitespace_only_flagged(self):
        """Whitespace-only text produces empty_body issue."""
        config = {}
        issues = validate_content(_WHITESPACE_ONLY, config)
        assert len(issues) == 1
        assert issues[0]["issue_type"] == "empty_body"

    def test_frontmatter_only_not_empty_body(self):
        """Frontmatter-only text is not flagged as empty_body; body is analyzed."""
        config = {}
        issues = validate_content(_ONLY_FM, config)
        assert not any(i["issue_type"] == "empty_body" for i in issues)
        assert len(issues) >= 1

    def test_valid_content_passes(self):
        """Content with good metrics produces no issues."""
        config = {}
        issues = validate_content(_VALID_FM, config)
        assert issues == []

    def test_high_corruption_score_flagged(self):
        """Content with many single-char lines produces corruption issue."""
        config = {"corruption": {"single_char_alpha": True, "bare_digits": True}}
        issues = validate_content(_CORRUPTED, config)
        corruption = [i for i in issues if i["issue_type"] == "corruption"]
        assert len(corruption) == 1
        assert corruption[0]["corruption_score"] > 0.3

    def test_bare_digits_corruption_flagged(self):
        """Content with many bare-digit lines produces corruption issue."""
        config = {"corruption": {"single_char_alpha": True, "bare_digits": True}}
        issues = validate_content(_CORRUPTED_DIGITS, config)
        corruption = [i for i in issues if i["issue_type"] == "corruption"]
        assert len(corruption) == 1

    def test_corruption_disabled_produces_no_issue(self):
        """When corruption checks are disabled, no corruption issue is raised."""
        config = {"corruption": {"single_char_alpha": False, "bare_digits": False}}
        issues = validate_content(_CORRUPTED, config)
        assert not any(i["issue_type"] == "corruption" for i in issues)

    def test_short_average_line_length_flagged(self):
        """Content with very short lines produces short_lines issue."""
        config = {}
        issues = validate_content(_SHORT_LINES, config)
        short = [i for i in issues if i["issue_type"] == "short_lines"]
        assert len(short) == 1
        assert short[0]["avg_content_line_length"] < 30

    def test_form_chrome_count_flagged(self):
        """Content with many form chrome lines produces form_chrome issue."""
        config = {
            "form_chrome": [
                "(?i)office use",
                "(?i)signature",
                "(?i)date of birth",
                "(?i)check this box",
                "(?i)reference number",
                "(?i)please enter",
            ]
        }
        issues = validate_content(_FORM_CHROME_TEXT, config)
        form = [i for i in issues if i["issue_type"] == "form_chrome"]
        assert len(form) == 1
        assert form[0]["form_chrome_count"] > 0

    def test_draft_marker_flagged(self):
        """Content with draft markers produces draft_marker issue."""
        config = {
            "draft_markers": [
                r"(?i)\bdraft\b",
                r"(?i)\bconfidential\b",
            ]
        }
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\n---\n\nDRAFT - For internal review only.\nThis document is a draft version."
        issues = validate_content(text, config)
        draft = [i for i in issues if i["issue_type"] == "draft_marker"]
        assert len(draft) == 1
        assert draft[0]["draft_marker_count"] > 0

    def test_no_draft_markers_no_issue(self):
        """Content without draft markers produces no draft_marker issue."""
        config = {
            "draft_markers": [r"(?i)\bdraft\b"]
        }
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\n---\n\nFinal version of the document with no early markers present."
        issues = validate_content(text, config)
        assert not any(i["issue_type"] == "draft_marker" for i in issues)

    def test_analyze_content_exception_handled(self, monkeypatch):
        """When analyze_content raises, issues remain empty (caught by handler)."""
        from folio.core import validator, classifier

        def _raise(*args, **kwargs):
            raise RuntimeError("simulated analysis failure")

        monkeypatch.setattr(classifier, "analyze_content", _raise)
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\n---\n\nValid content."
        issues = validate_content(text, {})
        assert isinstance(issues, list)

    def test_body_without_frontmatter_analyzed(self):
        """When no frontmatter exists, the full text is analyzed as body."""
        config = {}
        issues = validate_content("A valid line.\nAnother valid line.\n", config)
        assert not any(i["issue_type"] == "empty_body" for i in issues)

    def test_binary_like_content_handled(self):
        """Binary-like content is processed without crashing."""
        config = {}
        issues = validate_content(_BINARY_LIKE, config)
        assert isinstance(issues, list)

    def test_classification_config_none_raises(self):
        """None classification_config causes AttributeError in compile_patterns."""
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\n---\n\nShort.\n"
        with pytest.raises(AttributeError):
            validate_content(text, None)


# ── validate_file_size ─────────────────────────────────────────────────────────

class TestValidateFileSize:
    """Tests for validate_file_size()."""

    def test_valid_size_passes(self, tmp_path):
        """File within valid range produces no issues."""
        path = tmp_path / "valid.md"
        path.write_text("x" * 1000)
        issues = validate_file_size(path)
        assert issues == []

    def test_too_small_file_flagged(self, tmp_path):
        """File below 500 bytes produces too_small issue."""
        path = tmp_path / "tiny.md"
        path.write_text("hi")
        issues = validate_file_size(path)
        assert len(issues) == 1
        assert issues[0]["issue"] == "too_small"

    def test_too_large_file_flagged(self, tmp_path):
        """File above 1MB produces too_large issue."""
        path = tmp_path / "huge.md"
        path.write_text("x" * 1_500_000)
        issues = validate_file_size(path)
        assert len(issues) == 1
        assert issues[0]["issue"] == "too_large"

    def test_exactly_min_size_passes(self, tmp_path):
        """File at exactly 500 bytes passes."""
        path = tmp_path / "min.md"
        path.write_text("x" * 500)
        issues = validate_file_size(path)
        assert not any(i["issue"] == "too_small" for i in issues)

    def test_exactly_max_size_passes(self, tmp_path):
        """File at exactly 1MB passes."""
        path = tmp_path / "max.md"
        path.write_text("x" * 1_000_000)
        issues = validate_file_size(path)
        assert not any(i["issue"] == "too_large" for i in issues)

    def test_nonexistent_file_handled(self, tmp_path):
        """Non-existent file produces no issues (OSError caught)."""
        path = tmp_path / "nope.md"
        issues = validate_file_size(path)
        assert issues == []

    def test_zero_byte_file_flagged(self, tmp_path):
        """Zero-byte file is flagged as too_small."""
        path = tmp_path / "empty.md"
        path.write_text("")
        issues = validate_file_size(path)
        assert len(issues) == 1
        assert issues[0]["issue"] == "too_small"


# ── validate_placeholders ──────────────────────────────────────────────────────

class TestValidatePlaceholders:
    """Tests for validate_placeholders()."""

    def test_no_placeholders_passes(self):
        """Text without placeholders produces no issues."""
        issues = validate_placeholders(_VALID_FM)
        assert issues == []

    def test_todo_detected(self):
        """[TODO] is flagged as a placeholder."""
        issues = validate_placeholders("Some text.\n[TODO] Add more.\n")
        assert len(issues) == 1
        assert issues[0]["issue_type"] == "placeholder"
        assert any("TODO" in m for m in issues[0]["markers"])

    def test_fixme_detected(self):
        """[FIXME] is flagged as a placeholder."""
        issues = validate_placeholders("[FIXME] broken code here.")
        assert len(issues) == 1
        assert issues[0]["issue_type"] == "placeholder"
        assert any("FIXME" in m for m in issues[0]["markers"])

    def test_unknown_detected(self):
        """[UNKNOWN] is flagged as a placeholder."""
        issues = validate_placeholders("[UNKNOWN] value.")
        assert len(issues) == 1

    def test_tbd_detected(self):
        """[TBD] is flagged as a placeholder."""
        issues = validate_placeholders("Decision: [TBD]")
        assert len(issues) == 1
        assert any("TBD" in m for m in issues[0]["markers"])

    def test_triple_question_mark_detected(self):
        """??? is flagged as a placeholder."""
        issues = validate_placeholders("Not sure about this???")
        assert len(issues) == 1
        assert any("???" in m for m in issues[0]["markers"])

    def test_braced_placeholder_detected(self):
        """{placeholder} is flagged."""
        issues = validate_placeholders("{placeholder} text here.")
        assert len(issues) == 1
        assert any("placeholder" in m for m in issues[0]["markers"])

    def test_multiple_placeholders_in_one_text(self):
        """All placeholder types in one document are reported together."""
        issues = validate_placeholders(_PLACEHOLDER_TEXT)
        assert len(issues) == 1
        assert issues[0]["issue_type"] == "placeholder"
        assert len(issues[0]["markers"]) >= 4

    def test_empty_text_no_placeholders(self):
        """Empty text produces no placeholder issues."""
        issues = validate_placeholders("")
        assert issues == []

    def test_plain_text_no_placeholders(self):
        """Normal text without any marker patterns produces no issues."""
        issues = validate_placeholders("This is a normal paragraph.")
        assert issues == []


# ── validate_headings ──────────────────────────────────────────────────────────

class TestValidateHeadings:
    """Tests for validate_headings()."""

    def test_no_headings_config_returns_empty(self):
        """Empty headings_config produces no issues."""
        issues = validate_headings(_HEADINGS_DOC, {}, "TAC")
        assert issues == []

    def test_no_funder_returns_empty(self):
        """Empty funder string produces no issues."""
        issues = validate_headings(_HEADINGS_DOC, _HEADINGS_CONFIG, "")
        assert issues == []

    def test_funder_not_in_config_returns_empty(self):
        """Funder not present in headings_config produces no issues."""
        issues = validate_headings(_HEADINGS_DOC, _HEADINGS_CONFIG, "UNKNOWN")
        assert issues == []

    def test_all_headings_present_passes(self):
        """All expected sections present produces no missing_sections issue."""
        doc = """---
funder: TAC
type: report
written: 2024
---

## Project Summary

This section has enough content text to pass the thin-section threshold
because it contains many words describing the project in good detail.

## Budget Overview

The budget overview section also contains substantial text with financial
analysis and line-item breakdowns for the entire project duration.

## Outcomes

The outcomes section describes the project results in sufficient detail
for a complete report covering all aspects of the deliverables.

## Timeline

The timeline section lays out the project schedule with milestones and
delivery dates for each phase of the work plan.
"""
        issues = validate_headings(doc, _HEADINGS_CONFIG, "TAC")
        assert not any(i["issue_type"] == "missing_sections" for i in issues)

    def test_missing_sections_flagged(self):
        """Missing expected sections are flagged with details."""
        issues = validate_headings(_HEADINGS_DOC, _HEADINGS_CONFIG, "TAC")
        missing = [i for i in issues if i["issue_type"] == "missing_sections"]
        assert len(missing) == 1
        assert "Outcomes" in missing[0]["missing"]
        assert "Timeline" in missing[0]["missing"]

    def test_thin_section_flagged(self):
        """Sections with fewer than 50 chars of content are flagged."""
        issues = validate_headings(_HEADINGS_DOC, _HEADINGS_CONFIG, "TAC")
        thin = [i for i in issues if i["issue_type"] == "thin_section"]
        assert len(thin) >= 1
        assert any(s["section"] == "Missing Section" for s in thin)

    def test_section_with_enough_content_not_thin(self):
        """Sections with substantial content are not flagged as thin."""
        doc = """---
funder: OAC
type: application
written: 2024
---

## Project Description

This is a project description section with plenty of substantial content
text that easily exceeds the fifty character minimum threshold for thin
section detection in the validation system.
"""
        issues = validate_headings(doc, _HEADINGS_CONFIG, "OAC")
        assert not any(i["issue_type"] == "thin_section" for i in issues)

    def test_case_insensitive_heading_matching(self):
        """Heading matching is case-insensitive."""
        doc = """---
funder: TAC
type: report
written: 2024
---

## project summary

This is a project summary section with enough meaningful content to pass
the thin-section threshold because it contains many words describing what
was accomplished during the grant period in substantial detail.

## budget overview

The budget overview has enough detail with financial data and analysis to
cover all required line items and provide comprehensive reporting.
"""
        issues = validate_headings(doc, _HEADINGS_CONFIG, "TAC")
        missing = [i for i in issues if i["issue_type"] == "missing_sections"]
        assert "Project Summary" not in (missing[0]["missing"] if missing else [])
        assert "Budget Overview" not in (missing[0]["missing"] if missing else [])

    def test_text_with_no_headings_flagged(self):
        """Document with no ## headings has all sections missing."""
        doc = "---\nfunder: TAC\ntype: report\nwritten: 2024\n---\n\nJust text, no headings."
        issues = validate_headings(doc, _HEADINGS_CONFIG, "TAC")
        missing = [i for i in issues if i["issue_type"] == "missing_sections"]
        assert len(missing) == 1

    def test_last_section_boundary_handled(self):
        """The last section's body is correctly extracted to end of text."""
        doc = """---
funder: TAC
type: report
written: 2024
---

## Project Summary

This section has plenty of words and substantial content that goes on for
several lines to ensure that this description is not mistakenly flagged as
a thin section by the heading validation mechanism.
"""
        issues = validate_headings(doc, _HEADINGS_CONFIG, "TAC")
        assert not any(i["issue_type"] == "thin_section" for i in issues)


# ── validate_file ──────────────────────────────────────────────────────────────

class TestValidateFile:
    """Tests for validate_file() integration function."""

    def test_valid_file_passes_all_checks(self, tmp_path):
        """A well-formed file passes all validation checks."""
        path = tmp_path / "good.md"
        path.write_text(_BIG_VALID_FM)
        config = make_test_config()
        result = validate_file(path, config)
        assert result["file"] == str(path)
        assert result["issues"] == []

    def test_file_with_multiple_issues_collects_all(self, tmp_path):
        """A file with several problems collects issues from all checkers."""
        path = tmp_path / "bad.md"
        path.write_text("[TODO]\n[FIXME]\n")
        config = make_test_config()
        result = validate_file(path, config)
        assert len(result["issues"]) >= 2

    def test_unreadable_file_reports_error(self, tmp_path):
        """A file that cannot be read produces a read_error issue."""
        path = tmp_path / "nofile.md"
        config = make_test_config()
        result = validate_file(path, config)
        assert len(result["issues"]) == 1
        assert result["issues"][0]["issue_type"] == "read_error"

    def test_file_with_frontmatter_and_placeholder_collects_both(self, tmp_path):
        """Placeholder and content issues are collected together."""
        path = tmp_path / "mixed.md"
        path.write_text("---\nfunder: BADFUNDER\ntype: unknown_type\nwritten: 2024\n---\n\n[TODO]\n")
        config = make_test_config()
        result = validate_file(path, config)
        issue_types = [i["issue_type"] for i in result["issues"]]
        assert "invalid_funder" in issue_types
        assert "placeholder" in issue_types

    def test_size_issues_collected(self, tmp_path):
        """File size issues are included in the result."""
        path = tmp_path / "small.md"
        path.write_text("x")
        config = make_test_config()
        result = validate_file(path, config)
        issue_types = [i["issue_type"] for i in result["issues"]]
        assert "size_anomaly" in issue_types

    def test_headings_check_included(self, tmp_path):
        """When config has headings and fm has funder, headings check runs."""
        path = tmp_path / "with_headings.md"
        path.write_text(_HEADINGS_DOC)
        config = make_test_config(headings=_HEADINGS_CONFIG)
        result = validate_file(path, config)
        issue_types = [i["issue_type"] for i in result["issues"]]
        assert "missing_sections" in issue_types


# ── validate_directory ─────────────────────────────────────────────────────────

class TestValidateDirectory:
    """Tests for validate_directory() integration function."""

    def test_empty_directory(self, tmp_path):
        """Directory with no .md files reports zero scanned."""
        config = make_test_config()
        result = validate_directory(tmp_path, config)
        assert result["files_scanned"] == 0
        assert result["files_passing"] == 0
        assert result["files_with_issues"] == 0
        assert result["summary"] == "All files pass validation."

    def test_all_valid_files(self, tmp_path):
        """Directory where all files pass produces correct summary."""
        for i in range(3):
            p = tmp_path / f"doc_{i}.md"
            p.write_text(_BIG_VALID_FM)
        config = make_test_config()
        result = validate_directory(tmp_path, config)
        assert result["files_scanned"] == 3
        assert result["files_passing"] == 3
        assert result["files_with_issues"] == 0

    def test_some_files_with_issues(self, tmp_path):
        """Mixed directory reports correct pass/fail counts."""
        (tmp_path / "good.md").write_text(_BIG_VALID_FM)
        (tmp_path / "bad.md").write_text("[TODO]\n[FIXME]\n")
        config = make_test_config()
        result = validate_directory(tmp_path, config)
        assert result["files_scanned"] == 2
        assert result["files_passing"] == 1
        assert result["files_with_issues"] == 1

    def test_summary_lists_issue_counts(self, tmp_path):
        """Summary string includes counts of each issue type."""
        (tmp_path / "bad.md").write_text("[TODO]\n[FIXME]\n")
        config = make_test_config()
        result = validate_directory(tmp_path, config)
        assert "placeholder" in result["summary"]
        assert "files have issues" in result["summary"]

    def test_validations_dict_grouped_by_type(self, tmp_path):
        """validations dict groups issues by issue_type."""
        (tmp_path / "a.md").write_text("[TODO]\n")
        (tmp_path / "b.md").write_text("[FIXME]\n")
        config = make_test_config()
        result = validate_directory(tmp_path, config)
        assert "placeholder" in result["validations"]
        assert len(result["validations"]["placeholder"]) == 2

    def test_sample_limit(self, tmp_path):
        """Sample parameter limits the number of files checked."""
        for i in range(10):
            (tmp_path / f"doc_{i}.md").write_text(_VALID_FM)
        config = make_test_config()
        result = validate_directory(tmp_path, config, sample=3)
        assert result["files_scanned"] == 3

    def test_sample_exceeds_file_count(self, tmp_path):
        """Sample larger than file count scans all files."""
        for i in range(5):
            (tmp_path / f"doc_{i}.md").write_text(_VALID_FM)
        config = make_test_config()
        result = validate_directory(tmp_path, config, sample=20)
        assert result["files_scanned"] == 5

    def test_sample_zero_scans_all(self, tmp_path):
        """Sample of 0 scans all files."""
        for i in range(5):
            (tmp_path / f"doc_{i}.md").write_text(_VALID_FM)
        config = make_test_config()
        result = validate_directory(tmp_path, config, sample=0)
        assert result["files_scanned"] == 5

    def test_tier_filter(self, tmp_path):
        """Tier filter uses manifest to select files."""
        (tmp_path / "a.md").write_text(_BIG_VALID_FM)
        (tmp_path / "b.md").write_text(_BIG_VALID_FM)
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "files": {
                "a.md": {"tier": "full"},
                "b.md": {"tier": "minimal"},
            }
        }))
        config = make_test_config()
        result = validate_directory(tmp_path, config, tier="full")
        assert result["files_scanned"] == 1

    def test_tier_filter_no_manifest_fallback(self, tmp_path):
        """When manifest not found, tier filter logs warning and finds no files."""
        (tmp_path / "a.md").write_text(_VALID_FM)
        config = make_test_config()
        result = validate_directory(tmp_path, config, tier="full")
        assert result["files_scanned"] == 0

    def test_non_md_files_ignored(self, tmp_path):
        """Non-.md files are not scanned."""
        (tmp_path / "doc.md").write_text(_VALID_FM)
        (tmp_path / "notes.txt").write_text("hello")
        (tmp_path / "data.json").write_text("{}")
        config = make_test_config()
        result = validate_directory(tmp_path, config)
        assert result["files_scanned"] == 1

    def test_all_issue_types_present_in_validations(self, tmp_path):
        """Multiple issue types appear in the validations dict."""
        path = tmp_path / "messy.md"
        path.write_text("[TODO]\n")
        config = make_test_config()
        result = validate_directory(tmp_path, config)
        assert isinstance(result["validations"], dict)
        for issue_list in result["validations"].values():
            for issue in issue_list:
                assert "file" in issue
                assert "issue_type" in issue

    def test_result_structure(self, tmp_path):
        """Result dict has all expected keys."""
        config = make_test_config()
        result = validate_directory(tmp_path, config)
        for key in ("source_dir", "files_scanned", "files_passing",
                     "files_with_issues", "validations", "summary"):
            assert key in result

    def test_errors_field_non_integer_handled(self):
        """Non-integer errors value in frontmatter is silently skipped."""
        config = make_test_config()
        text = "---\nfunder: OAC\ntype: application\nwritten: 2024\nerrors: not_a_number\n---\n\nContent."
        issues = validate_frontmatter(text, config)
        assert not any(i["issue_type"] == "negative_errors" for i in issues)
