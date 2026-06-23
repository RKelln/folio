"""Tests for the offline converter-benchmark scorer.

These exercise the deterministic, dependency-free scoring metrics in
``folio.core.bench.scorer``. All assertions are plain ``assert`` statements and
none of the tests require a converter to be installed or any network access.
"""
from __future__ import annotations

from pathlib import Path

from folio.core.bench.scorer import (
    CategoryScores,
    normalize_text,
    score_document,
    score_links_images,
    score_structure,
    score_tables,
    score_text,
    strip_frontmatter,
)

GOLDEN_BUDGET = (
    Path(__file__).resolve().parents[1]
    / "benchmark"
    / "corpus"
    / "golden"
    / "oac-budget-01.md"
)


class TestStripFrontmatter:
    def test_removes_leading_block(self):
        md = "---\nfunder: OAC\ntype: budget\n---\n\n# Title\n\nBody.\n"
        assert strip_frontmatter(md) == "# Title\n\nBody."

    def test_noop_when_absent(self):
        md = "# Title\n\nBody.\n"
        assert strip_frontmatter(md) == md

    def test_empty_string(self):
        assert strip_frontmatter("") == ""

    def test_only_strips_first_block_keeps_inner_rule(self):
        md = "---\nk: v\n---\n# H\n\ntext\n\n---\n\nmore\n"
        result = strip_frontmatter(md)
        assert result.startswith("# H")
        assert "---" in result

    def test_unclosed_block_is_noop(self):
        md = "---\nfunder: OAC\n# never closed\n"
        assert strip_frontmatter(md) == md

    def test_real_golden_has_frontmatter_removed(self):
        text = GOLDEN_BUDGET.read_text(encoding="utf-8")
        body = strip_frontmatter(text)
        assert body.startswith("# Project Budget")
        assert "funder:" not in body


class TestNormalizeText:
    def test_lowercases_and_collapses_whitespace(self):
        assert normalize_text("  Hello\t  WORLD\n\nthere ") == "hello world there"

    def test_empty(self):
        assert normalize_text("") == ""


class TestScoreText:
    def test_identical_is_one(self):
        md = "The quick brown fox jumps over the lazy dog."
        assert score_text(md, md) == 1.0

    def test_both_empty_is_one(self):
        assert score_text("", "") == 1.0
        assert score_text("   \n", "  ") == 1.0

    def test_empty_candidate_is_zero(self):
        assert score_text("some real golden body text", "") == 0.0

    def test_whitespace_insensitive(self):
        assert score_text("a b   c", "a   b\nc") == 1.0

    def test_monotonic_closer_scores_higher(self):
        golden = "the quick brown fox jumps over the lazy dog"
        close = "the quick brown fox jumps over the lazy cat"
        far = "completely unrelated words here entirely"
        assert score_text(golden, close) > score_text(golden, far)

    def test_in_range(self):
        assert 0.0 <= score_text("a b c d", "a x c y") <= 1.0


class TestScoreTables:
    GOLDEN = (
        "| Source | Amount |\n"
        "| --- | --- |\n"
        "| Grant | $54,573 |\n"
        "| Earned | $4,066 |\n"
        "| **Total** | $58,639 |\n"
    )

    def test_identical_is_one(self):
        assert score_tables(self.GOLDEN, self.GOLDEN) == 1.0

    def test_dropped_rows_below_one(self):
        candidate = (
            "| Source | Amount |\n"
            "| --- | --- |\n"
            "| Grant | $54,573 |\n"
        )
        score = score_tables(self.GOLDEN, candidate)
        assert 0.0 < score < 1.0

    def test_no_tables_either_side_is_one(self):
        assert score_tables("just prose here", "just prose there") == 1.0

    def test_spurious_table_penalized(self):
        golden = "no tables at all, only prose"
        candidate = (
            "prose\n\n"
            "| Bogus | Table |\n"
            "| --- | --- |\n"
            "| 1 | 2 |\n"
        )
        score = score_tables(golden, candidate)
        assert score < 1.0

    def test_real_golden_self_match(self):
        body = strip_frontmatter(GOLDEN_BUDGET.read_text(encoding="utf-8"))
        assert score_tables(body, body) == 1.0

    def test_empty_candidate_against_table(self):
        assert score_tables(self.GOLDEN, "") < 0.5

    def test_in_range(self):
        assert 0.0 <= score_tables(self.GOLDEN, self.GOLDEN[:20]) <= 1.0


class TestScoreStructure:
    GOLDEN = (
        "# Project Budget\n"
        "## Budget\n"
        "### Revenue\n"
        "### Expenses\n"
    )

    def test_identical_headings_is_one(self):
        assert score_structure(self.GOLDEN, self.GOLDEN) == 1.0

    def test_reordered_below_perfect(self):
        reordered = (
            "### Expenses\n"
            "# Project Budget\n"
            "### Revenue\n"
            "## Budget\n"
        )
        assert score_structure(self.GOLDEN, reordered) < 1.0

    def test_missing_headings_below_one(self):
        candidate = "# Project Budget\n## Budget\n"
        assert 0.0 <= score_structure(self.GOLDEN, candidate) < 1.0

    def test_no_structure_either_side_is_one(self):
        assert score_structure("plain paragraph", "another paragraph") == 1.0

    def test_spurious_structure_penalized(self):
        assert score_structure("plain prose", "# Surprise\n- item\n") < 1.0

    def test_list_recovery(self):
        golden = "- one\n- two\n- three\n- four\n"
        full = "- one\n- two\n- three\n- four\n"
        partial = "- one\n- two\n"
        assert score_structure(golden, full) == 1.0
        assert score_structure(golden, partial) < 1.0

    def test_in_range(self):
        assert 0.0 <= score_structure(self.GOLDEN, "# Other\n") <= 1.0


class TestScoreLinksImages:
    def test_no_links_in_golden_is_one(self):
        assert score_links_images("no links here", "anything at all") == 1.0

    def test_full_recall(self):
        golden = "see [docs](http://a) and ![pic](img.png)"
        assert score_links_images(golden, golden) == 1.0

    def test_partial_recall(self):
        golden = "[a](http://a) and [b](http://b)"
        candidate = "only [a](http://a) survived"
        assert score_links_images(golden, candidate) == 0.5

    def test_missing_all_is_zero(self):
        golden = "[a](http://a) [b](http://b)"
        assert score_links_images(golden, "nothing here") == 0.0

    def test_capped_at_one(self):
        golden = "[a](http://a)"
        candidate = "[a](http://a) [a](http://a) [a](http://a)"
        assert score_links_images(golden, candidate) == 1.0

    def test_in_range(self):
        assert 0.0 <= score_links_images("[x](y)", "[x](y) [z](w)") <= 1.0


class TestScoreDocument:
    def test_identical_all_ones(self):
        text = GOLDEN_BUDGET.read_text(encoding="utf-8")
        scores = score_document(text, text)
        assert isinstance(scores, CategoryScores)
        assert scores.text == 1.0
        assert scores.tables == 1.0
        assert scores.structure == 1.0
        assert scores.links_images == 1.0

    def test_strips_frontmatter_from_both(self):
        golden = GOLDEN_BUDGET.read_text(encoding="utf-8")
        candidate = strip_frontmatter(golden)
        scores = score_document(golden, candidate)
        assert scores.text == 1.0
        assert scores.tables == 1.0

    def test_empty_candidate_low_scores(self):
        golden = GOLDEN_BUDGET.read_text(encoding="utf-8")
        scores = score_document(golden, "")
        assert scores.text == 0.0
        assert scores.tables < 0.5
        assert scores.structure < 0.5

    def test_degraded_candidate_between(self):
        golden = GOLDEN_BUDGET.read_text(encoding="utf-8")
        degraded = (
            "# Project Budget\n\n"
            "## Budget\n\n"
            "Revenue and expenses described in prose, tables lost.\n"
        )
        scores = score_document(golden, degraded)
        assert 0.0 < scores.text < 1.0
        assert scores.tables < 1.0
        assert scores.structure < 1.0

    def test_to_dict_keys(self):
        scores = CategoryScores(text=0.5, tables=0.6, structure=0.7, links_images=0.8)
        assert scores.to_dict() == {
            "text": 0.5,
            "tables": 0.6,
            "structure": 0.7,
            "links_images": 0.8,
        }

    def test_all_categories_in_range(self):
        golden = GOLDEN_BUDGET.read_text(encoding="utf-8")
        scores = score_document(golden, "# Project Budget\n\nsome text\n")
        for value in scores.to_dict().values():
            assert 0.0 <= value <= 1.0

    def test_whitespace_only_candidate_against_real_golden(self):
        golden = GOLDEN_BUDGET.read_text(encoding="utf-8")
        scores = score_document(golden, "\n   \n\t\n")
        assert scores.text == 0.0
        assert scores.tables < 1.0
        assert scores.structure < 1.0
        for value in scores.to_dict().values():
            assert 0.0 <= value <= 1.0
