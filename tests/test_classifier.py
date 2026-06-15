import pytest
from pathlib import Path
from folio.core.classifier import (
    evaluate_condition,
    evaluate_rule,
    parse_legacy_eval_condition,
    _detect_funder,
    _detect_doc_types,
    _compile_patterns,
    _analyze_content,
    _make_context,
    _evaluate_skip_rules,
    _evaluate_tier_rules,
    _normalize_rules,
    _TIER_MAP,
    classify_file,
    DEFAULT_CLASSIFY_CONFIG,
)
from folio.core.errors import FileStatus, ProcessingTier


CONTEXT = {
    "doc_types": ["application", "draft"],
    "corruption_score": 0.6,
    "content_lines": 50,
    "form_chrome_count": 3,
    "draft_marker_count": 1,
    "duplicate_heading_count": 0,
    "word_count_annotation_count": 2,
    "avg_content_line_length": 65.0,
    "has_headings": True,
    "has_tables": True,
    "filename": "OAC__2024_Grant__Application.md",
    "filepath": "/tmp/clean_md/OAC__2024_Grant__Application.md",
    "funder": "OAC",
}


class TestEvaluateCondition:
    def test_has_doc_type_true(self):
        assert evaluate_condition({"type": "has_doc_type", "value": "application"}, CONTEXT) is True

    def test_has_doc_type_false(self):
        assert evaluate_condition({"type": "has_doc_type", "value": "budget"}, CONTEXT) is False

    def test_has_doc_type_missing_key(self):
        assert evaluate_condition({"type": "has_doc_type", "value": "application"}, {}) is False

    def test_has_any_type_true(self):
        assert evaluate_condition({"type": "has_any_type", "values": ["budget", "application"]}, CONTEXT) is True

    def test_has_any_type_false(self):
        assert evaluate_condition({"type": "has_any_type", "values": ["budget", "report"]}, CONTEXT) is False

    def test_has_any_type_empty_context(self):
        assert evaluate_condition({"type": "has_any_type", "values": ["budget"]}, {}) is False

    def test_field_gt_true(self):
        assert evaluate_condition({"type": "field_gt", "field": "corruption_score", "value": 0.5}, CONTEXT) is True

    def test_field_gt_false(self):
        assert evaluate_condition({"type": "field_gt", "field": "corruption_score", "value": 0.9}, CONTEXT) is False

    def test_field_gt_missing_field_defaults_zero(self):
        assert evaluate_condition({"type": "field_gt", "field": "nonexistent", "value": -1}, CONTEXT) is True

    def test_field_lt_true(self):
        assert evaluate_condition({"type": "field_lt", "field": "corruption_score", "value": 0.9}, CONTEXT) is True

    def test_field_lt_false(self):
        assert evaluate_condition({"type": "field_lt", "field": "corruption_score", "value": 0.3}, CONTEXT) is False

    def test_field_gte_true_boundary(self):
        assert evaluate_condition({"type": "field_gte", "field": "content_lines", "value": 50}, CONTEXT) is True

    def test_field_gte_true_above(self):
        assert evaluate_condition({"type": "field_gte", "field": "content_lines", "value": 40}, CONTEXT) is True

    def test_field_gte_false(self):
        assert evaluate_condition({"type": "field_gte", "field": "content_lines", "value": 51}, CONTEXT) is False

    def test_field_lte_true_boundary(self):
        assert evaluate_condition({"type": "field_lte", "field": "content_lines", "value": 50}, CONTEXT) is True

    def test_field_lte_true_below(self):
        assert evaluate_condition({"type": "field_lte", "field": "content_lines", "value": 60}, CONTEXT) is True

    def test_field_lte_false(self):
        assert evaluate_condition({"type": "field_lte", "field": "content_lines", "value": 40}, CONTEXT) is False

    def test_path_contains_true(self):
        assert evaluate_condition({"type": "path_contains", "values": ["clean_md", "OAC"]}, CONTEXT) is True

    def test_path_contains_false(self):
        assert evaluate_condition({"type": "path_contains", "values": ["nowhere", "absent"]}, CONTEXT) is False

    def test_path_contains_empty_context(self):
        assert evaluate_condition({"type": "path_contains", "values": ["test"]}, {}) is False

    def test_filename_starts_with_true(self):
        assert evaluate_condition({"type": "filename_starts_with", "value": "OAC__"}, CONTEXT) is True

    def test_filename_starts_with_false(self):
        assert evaluate_condition({"type": "filename_starts_with", "value": "ZZZ"}, CONTEXT) is False

    def test_has_headings_true(self):
        assert evaluate_condition({"type": "has_headings"}, CONTEXT) is True

    def test_has_headings_false(self):
        ctx = dict(CONTEXT, has_headings=False)
        assert evaluate_condition({"type": "has_headings"}, ctx) is False

    def test_has_headings_missing_defaults_false(self):
        assert evaluate_condition({"type": "has_headings"}, {}) is False

    def test_has_tables_true(self):
        assert evaluate_condition({"type": "has_tables"}, CONTEXT) is True

    def test_has_tables_false(self):
        ctx = dict(CONTEXT, has_tables=False)
        assert evaluate_condition({"type": "has_tables"}, ctx) is False

    def test_not_negates_true(self):
        inner = {"type": "has_doc_type", "value": "budget"}
        assert evaluate_condition({"type": "not_", "condition": inner}, CONTEXT) is True

    def test_not_negates_false(self):
        inner = {"type": "has_doc_type", "value": "application"}
        assert evaluate_condition({"type": "not_", "condition": inner}, CONTEXT) is False

    def test_true_always(self):
        assert evaluate_condition({"type": "true"}, CONTEXT) is True
        assert evaluate_condition({"type": "true"}, {}) is True

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown condition type"):
            evaluate_condition({"type": "nonsense"}, CONTEXT)


class TestEvaluateRule:
    def test_match_all_true(self):
        rule = {
            "conditions": [
                {"type": "has_doc_type", "value": "application"},
                {"type": "field_gt", "field": "content_lines", "value": 10},
            ],
            "match": "all",
        }
        assert evaluate_rule(rule, CONTEXT) is True

    def test_match_all_false(self):
        rule = {
            "conditions": [
                {"type": "has_doc_type", "value": "application"},
                {"type": "field_gt", "field": "content_lines", "value": 100},
            ],
            "match": "all",
        }
        assert evaluate_rule(rule, CONTEXT) is False

    def test_match_any_true(self):
        rule = {
            "conditions": [
                {"type": "has_doc_type", "value": "nonexistent"},
                {"type": "has_doc_type", "value": "application"},
            ],
            "match": "any",
        }
        assert evaluate_rule(rule, CONTEXT) is True

    def test_match_any_false(self):
        rule = {
            "conditions": [
                {"type": "has_doc_type", "value": "nonexistent"},
                {"type": "field_gt", "field": "content_lines", "value": 100},
            ],
            "match": "any",
        }
        assert evaluate_rule(rule, CONTEXT) is False

    def test_empty_conditions_returns_true(self):
        assert evaluate_rule({"conditions": [], "match": "all"}, CONTEXT) is True

    def test_missing_match_defaults_to_all(self):
        rule = {
            "conditions": [
                {"type": "has_doc_type", "value": "application"},
                {"type": "field_gt", "field": "content_lines", "value": 10},
            ],
        }
        assert evaluate_rule(rule, CONTEXT) is True

    def test_missing_match_all_false_defaults_to_all(self):
        rule = {
            "conditions": [
                {"type": "has_doc_type", "value": "nonexistent"},
                {"type": "has_doc_type", "value": "application"},
            ],
        }
        assert evaluate_rule(rule, CONTEXT) is False


class TestLegacyParseCondition:
    def test_simple_has_type(self):
        result = parse_legacy_eval_condition("has_type('guidelines')")
        assert result == {"type": "has_doc_type", "value": "guidelines"}

    def test_simple_has_type_double_quotes(self):
        result = parse_legacy_eval_condition('has_type("guidelines")')
        assert result == {"type": "has_doc_type", "value": "guidelines"}

    def test_has_any_type(self):
        result = parse_legacy_eval_condition("has_any_type('notification', 'budget')")
        assert result == {"type": "has_any_type", "values": ["notification", "budget"]}

    def test_path_contains(self):
        result = parse_legacy_eval_condition("path_contains('prep', 'todo')")
        assert result == {"type": "path_contains", "values": ["prep", "todo"]}

    def test_filename_starts_with(self):
        result = parse_legacy_eval_condition("filename.startswith('~$')")
        assert result == {"type": "filename_starts_with", "value": "~$"}

    def test_field_gt(self):
        result = parse_legacy_eval_condition("corruption_score > 0.5")
        assert result == {"type": "field_gt", "field": "corruption_score", "value": 0.5}

    def test_field_lt(self):
        result = parse_legacy_eval_condition("content_lines < 15")
        assert result == {"type": "field_lt", "field": "content_lines", "value": 15}

    def test_field_gte(self):
        result = parse_legacy_eval_condition("form_chrome_count >= 5")
        assert result == {"type": "field_gte", "field": "form_chrome_count", "value": 5}

    def test_field_lte(self):
        result = parse_legacy_eval_condition("avg_content_line_length <= 30")
        assert result == {"type": "field_lte", "field": "avg_content_line_length", "value": 30}

    def test_not_condition(self):
        result = parse_legacy_eval_condition("not has_headings")
        assert result == {"type": "not_", "condition": {"type": "has_headings"}}

    def test_not_with_parentheses(self):
        result = parse_legacy_eval_condition("not (has_type('application'))")
        expected = {"type": "not_", "condition": {"type": "has_doc_type", "value": "application"}}
        assert result == expected

    def test_compound_and(self):
        result = parse_legacy_eval_condition("has_type('guidelines') and corruption_score > 0.5")
        assert result == {
            "conditions": [
                {"type": "has_doc_type", "value": "guidelines"},
                {"type": "field_gt", "field": "corruption_score", "value": 0.5},
            ],
            "match": "all",
        }

    def test_compound_and_three_terms(self):
        result = parse_legacy_eval_condition("has_type('app') and content_lines > 10 and has_headings")
        assert result == {
            "conditions": [
                {"type": "has_doc_type", "value": "app"},
                {"type": "field_gt", "field": "content_lines", "value": 10},
                {"type": "has_headings"},
            ],
            "match": "all",
        }

    def test_compound_or(self):
        result = parse_legacy_eval_condition("form_chrome_count > 5 or draft_marker_count > 5")
        assert result == {
            "conditions": [
                {"type": "field_gt", "field": "form_chrome_count", "value": 5},
                {"type": "field_gt", "field": "draft_marker_count", "value": 5},
            ],
            "match": "any",
        }

    def test_compound_and_or_mixed(self):
        result = parse_legacy_eval_condition(
            "has_type('app') and form_chrome_count > 5 or draft_marker_count > 5"
        )
        assert result == {
            "conditions": [
                {
                    "conditions": [
                        {"type": "has_doc_type", "value": "app"},
                        {"type": "field_gt", "field": "form_chrome_count", "value": 5},
                    ],
                    "match": "all",
                },
                {"type": "field_gt", "field": "draft_marker_count", "value": 5},
            ],
            "match": "any",
        }

    def test_not_has_any_type_compound(self):
        result = parse_legacy_eval_condition(
            "not has_any_type('notification', 'budget')"
        )
        assert result == {
            "type": "not_",
            "condition": {
                "type": "has_any_type",
                "values": ["notification", "budget"],
            },
        }

    def test_path_contains_with_uppercase(self):
        result = parse_legacy_eval_condition(
            "path_contains('prep', 'todo', 'ToDo', 'PREP')"
        )
        assert result == {
            "type": "path_contains",
            "values": ["prep", "todo", "ToDo", "PREP"],
        }

    def test_true_lowercase(self):
        result = parse_legacy_eval_condition("true")
        assert result == {"type": "true"}

    def test_false_becomes_not_true(self):
        result = parse_legacy_eval_condition("false")
        assert result == {"type": "not_", "condition": {"type": "true"}}

    def test_empty_string_returns_true(self):
        result = parse_legacy_eval_condition("")
        assert result == {"type": "true"}

    def test_whitespace_only_returns_true(self):
        result = parse_legacy_eval_condition("   ")
        assert result == {"type": "true"}

    def test_parenthesized_expression(self):
        result = parse_legacy_eval_condition("(has_type('application'))")
        assert result == {"type": "has_doc_type", "value": "application"}

    def test_bare_has_headings(self):
        result = parse_legacy_eval_condition("has_headings")
        assert result == {"type": "has_headings"}

    def test_bare_has_tables(self):
        result = parse_legacy_eval_condition("has_tables")
        assert result == {"type": "has_tables"}

    def test_compound_not_and(self):
        result = parse_legacy_eval_condition(
            "has_type('email') and not has_any_type('notification', 'budget')"
        )
        assert result == {
            "conditions": [
                {"type": "has_doc_type", "value": "email"},
                {
                    "type": "not_",
                    "condition": {
                        "type": "has_any_type",
                        "values": ["notification", "budget"],
                    },
                },
            ],
            "match": "all",
        }

    def test_four_way_and(self):
        result = parse_legacy_eval_condition(
            "not has_headings and has_tables and avg_content_line_length < 50 and content_lines > 50"
        )
        assert result == {
            "conditions": [
                {"type": "not_", "condition": {"type": "has_headings"}},
                {"type": "has_tables"},
                {"type": "field_lt", "field": "avg_content_line_length", "value": 50},
                {"type": "field_gt", "field": "content_lines", "value": 50},
            ],
            "match": "all",
        }


class TestNormalizeRules:
    def test_new_dsl_rules_passthrough(self):
        rules = [
            {
                "conditions": [{"type": "has_doc_type", "value": "application"}],
                "match": "all",
                "tier": "full",
            }
        ]
        result = _normalize_rules(rules, condition_key="condition", result_key="tier")
        assert result == rules

    def test_legacy_rule_converted(self):
        rules = [{"condition": "has_type('application')", "tier": "full"}]
        result = _normalize_rules(rules, condition_key="condition", result_key="tier")
        assert result == [
            {
                "conditions": [{"type": "has_doc_type", "value": "application"}],
                "match": "all",
                "tier": "full",
            }
        ]

    def test_legacy_rule_empty_condition(self):
        rules = [{"condition": "", "tier": "minimal"}]
        result = _normalize_rules(rules, condition_key="condition", result_key="tier")
        assert result == [
            {"conditions": [], "match": "all", "tier": "minimal"}
        ]

    def test_legacy_compound_merged(self):
        rules = [
            {
                "condition": "has_type('app') and content_lines > 10",
                "tier": "full",
                "reason": "big app",
            }
        ]
        result = _normalize_rules(rules, condition_key="condition", result_key="tier")
        assert result == [
            {
                "conditions": [
                    {"type": "has_doc_type", "value": "app"},
                    {"type": "field_gt", "field": "content_lines", "value": 10},
                ],
                "match": "all",
                "tier": "full",
                "reason": "big app",
            }
        ]


class TestEvaluateSkipRules:
    def test_first_match_wins(self):
        ctx = dict(CONTEXT)
        skip_rules = [
            {
                "conditions": [{"type": "has_doc_type", "value": "application"}],
                "match": "all",
                "reason": "skipped as application",
            },
            {
                "conditions": [{"type": "true"}],
                "match": "all",
                "reason": "catch-all skip",
            },
        ]
        result = _evaluate_skip_rules(skip_rules, ctx)
        assert result is not None
        assert result["reason"] == "skipped as application"

    def test_no_match_returns_none(self):
        ctx = dict(CONTEXT)
        skip_rules = [
            {
                "conditions": [{"type": "has_doc_type", "value": "nonexistent"}],
                "match": "all",
                "reason": "should not match",
            },
        ]
        result = _evaluate_skip_rules(skip_rules, ctx)
        assert result is None

    def test_empty_skip_rules(self):
        assert _evaluate_skip_rules([], CONTEXT) is None

    def test_reason_format_string(self):
        ctx = dict(CONTEXT, content_lines=5)
        skip_rules = [
            {
                "conditions": [{"type": "true"}],
                "match": "all",
                "reason": "only {content_lines} lines, too small",
            },
        ]
        result = _evaluate_skip_rules(skip_rules, ctx)
        assert result["reason"] == "only 5 lines, too small"

    def test_reason_format_string_missing_key(self):
        skip_rules = [
            {
                "conditions": [{"type": "true"}],
                "match": "all",
                "reason": "value is {nonexistent}",
            },
        ]
        result = _evaluate_skip_rules(skip_rules, CONTEXT)
        assert result is not None


class TestEvaluateTierRules:
    def test_first_match_wins(self):
        ctx = dict(CONTEXT)
        tier_rules = [
            {
                "conditions": [{"type": "has_doc_type", "value": "application"}],
                "match": "all",
                "tier": "full",
            },
            {
                "conditions": [{"type": "true"}],
                "match": "all",
                "tier": "light",
            },
        ]
        assert _evaluate_tier_rules(tier_rules, ctx) == "full"

    def test_no_match_defaults_minimal(self):
        ctx = dict(CONTEXT)
        tier_rules = [
            {
                "conditions": [{"type": "has_doc_type", "value": "nonexistent"}],
                "match": "all",
                "tier": "full",
            },
        ]
        assert _evaluate_tier_rules(tier_rules, ctx) == "minimal"

    def test_empty_tier_rules_defaults_minimal(self):
        assert _evaluate_tier_rules([], CONTEXT) == "minimal"

    def test_missing_tier_key_uses_default(self):
        ctx = dict(CONTEXT)
        tier_rules = [
            {
                "conditions": [{"type": "true"}],
                "match": "all",
            },
        ]
        assert _evaluate_tier_rules(tier_rules, ctx) == "minimal"

    def test_skip_tier(self):
        ctx = dict(CONTEXT)
        tier_rules = [
            {
                "conditions": [{"type": "has_doc_type", "value": "draft"}],
                "match": "all",
                "tier": "skip",
            },
        ]
        assert _evaluate_tier_rules(tier_rules, ctx) == "skip"

    def test_light_tier(self):
        ctx = dict(CONTEXT)
        tier_rules = [
            {
                "conditions": [{"type": "field_gt", "field": "content_lines", "value": 30}],
                "match": "all",
                "tier": "light",
            },
        ]
        assert _evaluate_tier_rules(tier_rules, ctx) == "light"


class TestMakeContext:
    def test_builds_all_keys(self):
        result = {
            "corruption_score": 0.1,
            "content_lines": 42,
            "form_chrome_count": 0,
            "draft_marker_count": 0,
            "duplicate_heading_count": 0,
            "word_count_annotation_count": 0,
            "avg_content_line_length": 80.0,
            "has_headings": True,
            "has_tables": False,
            "doc_types": ["application"],
            "filename": "test.md",
            "filepath": "/tmp/test.md",
            "funder": "OAC",
        }
        ctx = _make_context(result)
        assert ctx["corruption_score"] == 0.1
        assert ctx["content_lines"] == 42
        assert ctx["doc_types"] == ["application"]
        assert ctx["filename"] == "test.md"
        assert ctx["funder"] == "OAC"


class TestDetectFunder:
    @pytest.mark.parametrize(
        "path_str,funders,expected",
        [
            ("/tmp/clean_md/OAC__2024_Grant__Application.md", {"OAC": "Ontario Arts Council"}, "OAC"),
            ("/tmp/CAC__Report.md", {"CAC": "Canada Council", "OAC": "Ontario Arts Council"}, "CAC"),
            ("/tmp/random_file.md", {"OAC": "Ontario Arts Council"}, None),
            ("/tmp/clean_md/CAC_blah__2024.md", {"CAC": "Canada Council", "OAC": "Ontario Arts Council"}, "CAC"),
        ],
    )
    def test_detect_funder(self, path_str, funders, expected):
        assert _detect_funder(path_str, funders) == expected

    def test_longs_matched_first(self):
        funders = {"CAC": "Canada Council", "CAC_T": "Canada Council Toronto"}
        result = _detect_funder("/tmp/CAC_T__2024.md", funders)
        assert result == "CAC_T"

    def test_case_insensitive(self):
        funders = {"oac": "Ontario Arts Council"}
        result = _detect_funder("/tmp/OAC__2024.md", funders)
        assert result == "oac"


class TestDetectDocTypes:
    @pytest.fixture
    def doc_type_config(self):
        return {
            "doc_types": {
                "application": [r"(?i)application", r"grant_app"],
                "report": [r"(?i)report", r"final_report"],
                "budget": [r"(?i)budget", r"financial"],
                "cv": [r"\bcv\b", r"curriculum vitae"],
            },
            "form_chrome": [],
            "draft_markers": [],
        }

    @pytest.fixture
    def compiled(self, doc_type_config):
        return _compile_patterns(doc_type_config)

    def test_single_doc_type(self, compiled):
        result = _detect_doc_types("/tmp/OAC__2024_Grant__Application.md", compiled)
        assert "application" in result

    def test_multiple_doc_types(self, compiled):
        result = _detect_doc_types("/tmp/budget_application_report.md", compiled)
        assert "application" in result
        assert "budget" in result
        assert "report" in result

    def test_unknown_doc_type(self, compiled):
        result = _detect_doc_types("/tmp/mystery_file.md", compiled)
        assert result == ["unknown"]

    def test_underscores_normalized(self, compiled):
        result = _detect_doc_types("/tmp/staff_board_meeting.md", compiled)
        assert "cv" not in result
        assert result == ["unknown"]

    def test_cv_detected(self, compiled):
        result = _detect_doc_types("/tmp/artist_cv.md", compiled)
        assert "cv" in result

    def test_case_insensitive_regex(self, compiled):
        compiled2 = _compile_patterns({
            "doc_types": {"application": [r"(?i)application"]},
            "form_chrome": [],
            "draft_markers": [],
        })
        result = _detect_doc_types("/tmp/OAC__Application.md", compiled2)
        assert "application" in result


class TestAnalyzeContent:
    @pytest.fixture
    def empty_compiled(self):
        return _compile_patterns({"doc_types": {}, "form_chrome": [], "draft_markers": []})

    def test_empty_text(self, empty_compiled):
        result = _analyze_content("", empty_compiled)
        assert result["total_lines"] == 1
        assert result["content_lines"] == 0
        assert result["corruption_score"] == 0.0

    def test_simple_content(self, empty_compiled):
        text = "# Heading\n\nSome content here.\n\nMore content."
        result = _analyze_content(text, empty_compiled)
        assert result["total_lines"] == 5
        assert result["content_lines"] == 3
        assert result["has_headings"] is True
        assert result["has_tables"] is False
        assert result["corruption_score"] == 0.0

    def test_headings_detected(self, empty_compiled):
        text = "# Title\n## Section 1\n## Section 2\nbody text\n"
        result = _analyze_content(text, empty_compiled)
        assert result["has_headings"] is True

    def test_tables_detected(self, empty_compiled):
        text = "| col1 | col2 |\n|------|------|\n| a    | b    |\n"
        result = _analyze_content(text, empty_compiled)
        assert result["has_tables"] is True

    def test_corruption_single_char(self, empty_compiled):
        text = "A\nB\nC\nThis is actual content.\n"
        result = _analyze_content(text, empty_compiled)
        assert result["corruption_score"] > 0

    def test_duplicate_headings(self, empty_compiled):
        text = "# Same\n# Same\n# Different\n"
        result = _analyze_content(text, empty_compiled)
        assert result["duplicate_heading_count"] == 1

    def test_word_count_annotations(self, empty_compiled):
        text = "500 words\n1000 words\nOrdinary line.\n"
        result = _analyze_content(text, empty_compiled)
        assert result["word_count_annotation_count"] == 2

    def test_form_chrome_detected(self):
        compiled = _compile_patterns({
            "doc_types": {},
            "form_chrome": [r"\[X\]", r"Please select"],
            "draft_markers": [],
        })
        text = "Please select one:\n[X] Option A\n[ ] Option B\nContent here.\n"
        result = _analyze_content(text, compiled)
        assert result["form_chrome_count"] >= 1

    def test_draft_markers_detected(self):
        compiled = _compile_patterns({
            "doc_types": {},
            "form_chrome": [],
            "draft_markers": [r"DRAFT", r"TODO"],
        })
        text = "DRAFT - do not distribute\nTODO: finish this\nRegular content.\n"
        result = _analyze_content(text, compiled)
        assert result["draft_marker_count"] >= 1

    def test_image_markers(self, empty_compiled):
        text = "<!-- image -->\n[IMAGE]\nReal content.\n"
        result = _analyze_content(text, empty_compiled)
        assert result["image_marker_count"] == 1

    def test_avg_content_line_length(self, empty_compiled):
        text = "short\nA much longer line with many characters\nmedium\n"
        result = _analyze_content(text, empty_compiled)
        assert result["avg_content_line_length"] > 0

    def test_corruption_disabled(self):
        compiled = _compile_patterns({"doc_types": {}, "form_chrome": [], "draft_markers": []})
        corruption_cfg = {"single_char_alpha": False, "bare_digits": False}
        text = "A\nB\n1\nactual\n"
        result = _analyze_content(text, compiled, corruption_cfg)
        assert result["corruption_score"] == 0.0


class TestClassifyFile:
    def config_with_funders_and_doc_types(self):
        return {
            **DEFAULT_CLASSIFY_CONFIG,
            "funders": {"OAC": "Ontario Arts Council", "CAC": "Canada Council"},
            "doc_types": {
                "application": [r"(?i)application", r"grant"],
                "report": [r"(?i)report", r"final"],
            },
            "form_chrome": [r"\[X\]"],
            "draft_markers": [r"DRAFT", r"TODO"],
            "skip_rules": [],
            "tier_rules": [],
        }

    def test_classify_basic_file(self, tmp_path):
        md_file = tmp_path / "OAC__2024_Grant__Application.md"
        md_file.write_text(
            "# OAC Operating Grant Application 2024\n\n"
            "## Project Description\n\n"
            "This is a well-written project description with enough content\n"
            "to meet the minimum line requirements. It describes the project\n"
            "in detail and provides context for the application.\n\n"
            "## Budget Overview\n\n"
            "The budget is reasonable and well-justified.\n\n"
            "## Timeline\n\n"
            "The project will run from January to December.\n\n"
            "## Impact\n\n"
            "Expected outcomes include community engagement.\n"
        )
        config = self.config_with_funders_and_doc_types()
        result = classify_file(md_file, config)

        assert result["filename"] == "OAC__2024_Grant__Application.md"
        assert result["funder"] == "OAC"
        assert "application" in result["doc_types"]
        assert result["status"] == FileStatus.OK
        assert result["content_lines"] > 0
        assert result["has_headings"] is True
        assert result["tier"] in (ProcessingTier.MINIMAL, ProcessingTier.LIGHT, ProcessingTier.FULL)

    def test_classify_file_with_skip_rule(self, tmp_path):
        md_file = tmp_path / "DRAFT_OAC_Application.md"
        md_file.write_text("TODO: finish this application\n\nA bit of content.\n")
        config = {
            **DEFAULT_CLASSIFY_CONFIG,
            "funders": {"OAC": "Ontario Arts Council"},
            "doc_types": {"application": [r"(?i)application"]},
            "skip_rules": [
                {
                    "conditions": [
                        {"type": "has_doc_type", "value": "application"},
                    ],
                    "match": "all",
                    "reason": "Skip applications for now",
                }
            ],
            "tier_rules": [],
        }
        result = classify_file(md_file, config)
        assert result["status"] == FileStatus.SKIPPED_DRAFT
        assert result["tier"] == ProcessingTier.SKIP

    def test_classify_file_with_tier_rules(self, tmp_path):
        md_file = tmp_path / "OAC__Report.md"
        md_file.write_text(
            "# Final Report\n\n"
            + "Content line.\n" * 20
        )
        config = {
            **DEFAULT_CLASSIFY_CONFIG,
            "funders": {"OAC": "Ontario Arts Council"},
            "doc_types": {"report": [r"(?i)report"]},
            "skip_rules": [],
            "tier_rules": [
                {
                    "conditions": [
                        {"type": "has_doc_type", "value": "report"},
                    ],
                    "match": "all",
                    "tier": "light_cleanup",
                }
            ],
        }
        result = classify_file(md_file, config)
        assert result["tier"] == ProcessingTier.LIGHT
        assert result["status"] == FileStatus.OK

    def test_classify_file_with_frontmatter(self, tmp_path):
        md_file = tmp_path / "CAC__2023_Report.md"
        md_file.write_text(
            "---\n"
            "funder: CAC\n"
            "written: 2023\n"
            "---\n\n"
            "# CAC Report\n\n"
            "Content here.\n" * 20
        )
        config = self.config_with_funders_and_doc_types()
        result = classify_file(md_file, config)
        assert result["funder"] == "CAC"

    def test_classify_file_corrupted(self, tmp_path):
        md_file = tmp_path / "corrupt.md"
        md_file.write_text("X\nY\nZ\n1\n2\n3\n")
        config = self.config_with_funders_and_doc_types()
        result = classify_file(md_file, config)
        assert result["corruption_score"] > 0.5
        assert "unknown" in result["doc_types"]

    def test_classify_draft_skip_complex(self, tmp_path):
        md_file = tmp_path / "prep_notes.md"
        md_file.write_text("DRAFT\n\nTODO\n\nSome content.\n" * 10)
        config = {
            **DEFAULT_CLASSIFY_CONFIG,
            "funders": {},
            "doc_types": {"meeting_notes": [r"meeting_notes"]},
            "draft_markers": [r"DRAFT"],
            "skip_rules": [
                {
                    "conditions": [
                        {"type": "path_contains", "values": ["prep", "todo"]},
                    ],
                    "match": "all",
                    "reason": "Prep file: {filename}",
                }
            ],
            "tier_rules": [],
        }
        result = classify_file(md_file, config)
        assert result["status"] == FileStatus.SKIPPED_DRAFT


class TestTIER_MAP:
    def test_all_variants_mapped(self):
        assert _TIER_MAP["full_rewrite"] == ProcessingTier.FULL
        assert _TIER_MAP["full"] == ProcessingTier.FULL
        assert _TIER_MAP["light_cleanup"] == ProcessingTier.LIGHT
        assert _TIER_MAP["light"] == ProcessingTier.LIGHT
        assert _TIER_MAP["minimal"] == ProcessingTier.MINIMAL
        assert _TIER_MAP["skip"] == ProcessingTier.SKIP


class TestLegacyParserErrors:
    def test_unknown_function_raises(self):
        with pytest.raises(ValueError, match="Unknown function"):
            parse_legacy_eval_condition("unknown_func('arg')")

    def test_unknown_method_call_raises(self):
        with pytest.raises(ValueError, match="Unknown method call"):
            parse_legacy_eval_condition("filename.unknown('arg')")

    def test_unknown_bare_name_raises(self):
        with pytest.raises(ValueError, match="Unknown bare name"):
            parse_legacy_eval_condition("some_random_identifier")

    def test_unknown_operator_raises(self):
        with pytest.raises(ValueError, match="Unknown bare name"):
            parse_legacy_eval_condition("corruption_score == 0.5")

    def test_has_type_wrong_arg_count_raises(self):
        with pytest.raises(ValueError, match="has_type expects 1 argument"):
            parse_legacy_eval_condition("has_type('a', 'b')")

    def test_filename_startswith_wrong_arg_count_raises(self):
        with pytest.raises(ValueError, match="filename.startswith expects 1 argument"):
            parse_legacy_eval_condition("filename.startswith('a', 'b')")
