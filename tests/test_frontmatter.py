from __future__ import annotations

import pytest

from folio.core.frontmatter import (
    apply_frontmatter,
    dict_to_frontmatter,
    extract_year,
    get_file_year,
    normalize_field_aliases,
    normalize_field_values,
    parse_frontmatter,
    sanitize_frontmatter,
    strip_existing_frontmatter,
    update_frontmatter,
)


class TestExtractYear:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (2024, 2024),
            ("2024", 2024),
            ("2025-2027", 2025),
            ("2025–2027", 2025),
            ("2025-07-10", 2025),
            ("Fiscal 2024 Report", 2024),
            (None, None),
            ("", None),
            ("some text", None),
        ],
    )
    def test_extract_year(self, value, expected):
        assert extract_year(value) == expected


class TestParseFrontmatter:
    def test_simple_frontmatter_returns_dict_and_body(self):
        fm, body = parse_frontmatter("---\nwritten: 2024\nfunder: OAC\n---\nBody")
        assert fm == {"written": 2024, "funder": "OAC"}
        assert body == "Body"

    def test_no_frontmatter_returns_none_and_full_text(self):
        fm, body = parse_frontmatter("# Heading\n\nBody text")
        assert fm is None
        assert body == "# Heading\n\nBody text"

    def test_unclosed_frontmatter_returns_none(self):
        fm, body = parse_frontmatter("---\nwritten: 2024\nfunder: OAC")
        assert fm is None

    def test_body_after_frontmatter_preserved(self):
        fm, body = parse_frontmatter("---\nfunder: OAC\n---\n\n\nBody content\n\nMore")
        assert fm == {"funder": "OAC"}
        assert body == "Body content\n\nMore"

    def test_frontmatter_parsed_from_sample_fixture(self, sample_markdown_with_frontmatter):
        fm, body = parse_frontmatter(sample_markdown_with_frontmatter)
        assert fm is not None
        assert "funder" in fm
        assert "# OAC Operating Grant Application 2024" in body


class TestGetFileYear:
    def test_with_written_field_returns_year(self):
        fm = {"written": 2024, "funder": "OAC"}
        assert get_file_year(fm, field="written") == 2024

    def test_falls_back_to_period_when_primary_missing(self):
        fm = {"period": 2023, "funder": "OAC"}
        assert get_file_year(fm, field="written") == 2023

    def test_falls_back_to_period_start(self):
        fm = {"period_start": "2022-01-15", "funder": "OAC"}
        assert get_file_year(fm, field="written") == 2022

    def test_no_year_in_fm_returns_none(self):
        fm = {"funder": "OAC", "type": "proposal"}
        assert get_file_year(fm) is None

    def test_none_fm_returns_none(self):
        assert get_file_year(None) is None


class TestDictToFrontmatter:
    def test_generates_valid_yaml_with_delimiters(self):
        result = dict_to_frontmatter(funder="OAC", written=2024)
        assert result == '---\nfunder: "OAC"\nwritten: 2024\n---'

    def test_lists_joined_with_comma(self):
        result = dict_to_frontmatter(tags=["a", "b", "c"])
        assert result == '---\ntags: "a, b, c"\n---'

    def test_none_values_skipped(self):
        result = dict_to_frontmatter(funder="OAC", priority=None)
        assert result == '---\nfunder: "OAC"\n---'

    def test_empty_strings_skipped(self):
        result = dict_to_frontmatter(funder="OAC", notes="")
        assert result == '---\nfunder: "OAC"\n---'

    def test_empty_frontmatter_when_all_skipped(self):
        result = dict_to_frontmatter(priority=None, notes="")
        assert result == "---\n---"


class TestUpdateFrontmatter:
    def test_adds_new_field_to_existing_fm(self):
        result = update_frontmatter("---\nfunder: OAC\n---\n\nBody", written=2024)
        assert "written: 2024" in result
        assert "funder: OAC" in result
        assert "Body" in result

    def test_replaces_existing_field(self):
        result = update_frontmatter("---\nwritten: 2023\n---\n\nBody", written=2024)
        assert "written: 2024" in result
        assert "2023" not in result

    def test_creates_frontmatter_when_none_exists(self):
        result = update_frontmatter("Body text", written=2024)
        assert result.startswith("---\n")
        assert "written: 2024" in result
        assert "Body text" in result

    def test_adds_multiple_fields_at_once(self):
        result = update_frontmatter(
            "---\nfunder: OAC\n---\n\nBody", written=2024, type="proposal"
        )
        assert "funder: OAC" in result
        assert "written: 2024" in result
        assert "type: proposal" in result

    def test_body_preserved_after_update(self):
        result = update_frontmatter(
            "---\nfunder: OAC\n---\n\n# Heading\n\nBody paragraph.",
            written=2024,
        )
        assert "# Heading" in result
        assert "Body paragraph." in result


class TestStripExistingFrontmatter:
    def test_strips_bare_delimited_fm(self):
        result = strip_existing_frontmatter("---\nfunder: OAC\n---\n\nBody text")
        assert "funder" not in result
        assert "Body text" in result

    def test_strips_code_fenced_fm(self):
        result = strip_existing_frontmatter(
            "```yaml\nfunder: OAC\nwritten: 2024\n```\n\nBody text"
        )
        assert "funder" not in result
        assert "written" not in result
        assert "Body text" in result

    def test_passes_through_text_with_no_fm(self):
        text = "# Heading\n\nBody text"
        result = strip_existing_frontmatter(text)
        assert "# Heading" in result
        assert "Body text" in result


class TestSanitizeFrontmatter:
    def test_bare_fm_passes_through(self):
        result = sanitize_frontmatter('---\nfunder: "OAC"\n---\n\nBody text')
        assert "funder" in result
        assert "Body text" in result
        assert result.startswith("---")

    def test_code_fenced_yaml_with_delimiters_inside_stripped(self):
        result = sanitize_frontmatter(
            '```yaml\n---\nfunder: "OAC"\n---\n```\n\nBody text'
        )
        assert "```" not in result
        assert "funder" in result
        assert "Body text" in result

    def test_code_fenced_yaml_without_delimiters_stripped(self):
        result = sanitize_frontmatter(
            '```yaml\nfunder: "OAC"\ntype: "proposal"\n```\n\nBody text'
        )
        assert "```" not in result
        assert "funder" in result
        assert "Body text" in result

    def test_stray_dashes_not_treated_as_fm(self):
        result = sanitize_frontmatter("---\n# Project Notes\nThis is markdown.")
        assert "---" in result or result.strip()

    def test_no_fm_at_all_passthrough(self):
        text = "# Just a heading\n\nSome content"
        result = sanitize_frontmatter(text)
        assert "# Just a heading" in result
        assert "Some content" in result

    def test_empty_fm(self):
        result = sanitize_frontmatter("---\n---")
        assert result is not None

    def test_type_field_normalized(self):
        result = sanitize_frontmatter("---\ntype: support material\n---\n\nBody")
        assert "support_material" in result
        assert "support material" not in result

    def test_year_written_alias_renamed(self):
        result = sanitize_frontmatter(
            "---\nyear_written: 2024\nfunder: OAC\n---\n\nBody"
        )
        assert "year_written" not in result
        assert "written: 2024" in result

    def test_empty_grant_amount_removed(self):
        result = sanitize_frontmatter(
            '---\nfunder: "OAC"\ngrant_amount: ""\n---\n\nBody'
        )
        assert "grant_amount" not in result


class TestNormalizeFieldAliases:
    @pytest.mark.parametrize(
        "fm_text, expected",
        [
            ("year_written: 2024", "written: 2024"),
            ("year: 2024", "written: 2024"),
            ("status: active", "type: active"),
            ("doc_type: proposal", "type: proposal"),
            ("document_type: report", "type: report"),
            ("year_written: 2024\nstatus: active", "written: 2024\ntype: active"),
            ("written: 2024", "written: 2024"),
            ("type: proposal", "type: proposal"),
        ],
    )
    def test_normalize_field_aliases(self, fm_text, expected):
        assert normalize_field_aliases(fm_text) == expected


class TestNormalizeFieldValues:
    @pytest.mark.parametrize(
        "fm_text, expected_fragment",
        [
            ('grant_amount: ""', ""),
            ("grant_amount: ", ""),
            ("grant_amount: ''", ""),
        ],
    )
    def test_empty_value_fields_removed(self, fm_text, expected_fragment):
        result = normalize_field_values(fm_text)
        assert "grant_amount" not in result

    @pytest.mark.parametrize(
        "fm_text, expected_type_line",
        [
            ("type: support material", "type: support_material"),
            ("type: support materials", "type: support_material"),
            ("type: activity list", "type: activity_list"),
            ("type: staff board", "type: staff_board"),
            ("type: meeting notes", "type: meeting_notes"),
            ("type: financial_form", "type: budget"),
            ("type: incorporation", "type: agreement"),
            ("type: letter of agreement", "type: agreement"),
            ("type: results", "type: notification"),
            ("type: result", "type: notification"),
            ("type: approval", "type: notification"),
            ("type: acceptance", "type: notification"),
            ("type: email correspondence", "type: email"),
        ],
    )
    def test_type_values_normalized(self, fm_text, expected_type_line):
        result = normalize_field_values(fm_text)
        assert expected_type_line in result

    @pytest.mark.parametrize(
        "fm_text, expected_fragment",
        [
            ('period: "July 11-14, 2013"', "period: 2013"),
            ("period: February 8 - March 29, 2014", "period: 2014"),
            ("period: Summer 2020", "period: 2020"),
            ("period: 2021-03-01 to 2021-08-31", "period: 2021"),
            ("period: 2015-09-15 to 2020-09-14", "period: 2015\u20132020"),
            ("period: 2025", "period: 2025"),
            ("period: 2025\u20132027", "period: 2025\u20132027"),
            ("period: Vector 2020", "period: 2020"),
        ],
    )
    def test_period_values_normalized(self, fm_text, expected_fragment):
        result = normalize_field_values(fm_text)
        assert expected_fragment in result, f"Expected '{expected_fragment}' in '{result}'"

    def test_period_unchanged_when_no_year_found(self):
        result = normalize_field_values("period: some ancient era")
        assert "period: some ancient era" in result


class TestApplyFrontmatter:
    def test_prepends_fm_to_body(self):
        result = apply_frontmatter("Body text", "---\nwritten: 2024\n---")
        assert result.startswith("---\nwritten: 2024\n---")

    def test_body_preserved_after_fm(self):
        result = apply_frontmatter("Original body.", "---\nwritten: 2024\n---")
        assert "Original body." in result

    def test_existing_fm_replaced(self):
        text = "---\nold: true\n---\n\nContent here"
        result = apply_frontmatter(text, "---\nwritten: 2024\n---")
        assert "old: true" not in result
        assert "written: 2024" in result
        assert "Content here" in result
