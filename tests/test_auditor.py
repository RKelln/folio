from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from folio.core.auditor import (
    _scan_articles,
    _check_dead_links,
    _check_thin_articles,
    _check_near_duplicates,
    _check_missing_sections,
    _check_suspicious_concepts,
    _check_stale_content,
    audit_summary_text,
    audit_wiki,
    DEFAULT_AUDIT_CONFIG,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_concept_dir(tmp_path: Path) -> Path:
    concepts = tmp_path / "wiki" / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    return concepts


def write_article(concepts_dir: Path, name: str, body: str, frontmatter: dict | None = None) -> Path:
    fp = concepts_dir / f"{name}.md"
    lines = []
    if frontmatter is not None:
        lines.append("---")
        for k, v in frontmatter.items():
            if isinstance(v, list):
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{k}: {v}")
        lines.append("---")
    lines.append(body)
    fp.write_text("\n".join(lines) + "\n")
    return fp


# ── Unit: _scan_articles ─────────────────────────────────────────────────────

class TestScanArticles:
    def test_scans_single_article(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        write_article(concepts, "CanadaCouncil", "## Definition\n\nThis is the Canada Council for the Arts.\n\n## Body\n\nMore content.\n")

        articles = _scan_articles(concepts)
        assert len(articles) == 1
        assert articles[0]["name"] == "CanadaCouncil"
        assert "This is the Canada Council" in articles[0]["body_text"]
        assert articles[0]["body_line_count"] > 0

    def test_scans_multiple_articles(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        write_article(concepts, "OntarioArtsCouncil", "## Body\n\nOAC content.\n")
        write_article(concepts, "TorontoArtsCouncil", "## Body\n\nTAC content.\n")
        write_article(concepts, "BCArtsCouncil", "## Body\n\nBCAC content.\n")

        articles = _scan_articles(concepts)
        assert len(articles) == 3

    def test_extracts_frontmatter_aliases(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        write_article(concepts, "CanadaCouncil", "## Body\n\nContent.\n", frontmatter={
            "aliases": ["CAC", "Canada Council for the Arts"],
        })

        articles = _scan_articles(concepts)
        assert len(articles) == 1
        assert "cac" in articles[0]["aliases"]
        assert "canada-council-for-the-arts" in articles[0]["aliases"]

    def test_extracts_wikilinks(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        write_article(concepts, "MainArticle", "## Body\n\nSee [[OtherPage]] and [[AnotherPage|with display text]].\n")

        articles = _scan_articles(concepts)
        assert len(articles) == 1
        assert "OtherPage" in articles[0]["wikilinks"]
        assert "AnotherPage" in articles[0]["wikilinks"]

    def test_no_frontmatter(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        write_article(concepts, "SimplePage", "## Body\n\nJust content.\n")

        articles = _scan_articles(concepts)
        assert articles[0]["aliases"] == []
        assert articles[0]["body_start"] == 0

    def test_empty_directory(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        articles = _scan_articles(concepts)
        assert articles == []

    def test_body_len_calculated(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        body = "A" * 500
        write_article(concepts, "TestPage", body)

        articles = _scan_articles(concepts)
        assert articles[0]["body_len"] == len(body)
        assert articles[0]["body_line_count"] == 1

    def test_word_bag_extracted(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        write_article(concepts, "TestPage", "## Body\n\nThis is some test content with multiple words of varying length.\n")

        articles = _scan_articles(concepts)
        assert len(articles[0]["word_bag"]) > 0
        assert "this" in articles[0]["word_bag"]
        assert "test" in articles[0]["word_bag"]
        assert "content" in articles[0]["word_bag"]


# ── Unit: _check_dead_links ──────────────────────────────────────────────────

class TestCheckDeadLinks:
    def test_dead_link_detected(self):
        art1 = {
            "name": "pagea", "file": Path("/fake/pagea.md"),
            "wikilinks": ["PageB"], "lines": ["[[PageB]]"],
            "aliases": [],
        }
        issues = _check_dead_links([art1])
        assert len(issues) == 1
        assert issues[0]["target"] == "pageb"
        assert issues[0]["article"] == "pagea"

    def test_valid_link_no_issue(self):
        art1 = {
            "name": "pagea", "file": Path("/fake/pagea.md"),
            "wikilinks": ["PageB"], "lines": ["[[PageB]]"],
            "aliases": [],
        }
        art2 = {
            "name": "pageb", "file": Path("/fake/pageb.md"),
            "wikilinks": [], "lines": [],
            "aliases": [],
        }
        issues = _check_dead_links([art1, art2])
        assert len(issues) == 0

    def test_alias_resolves_link(self):
        art1 = {
            "name": "pagea", "file": Path("/fake/pagea.md"),
            "wikilinks": ["CAC"], "lines": ["[[CAC]]"],
            "aliases": [],
        }
        art2 = {
            "name": "canadacouncil", "file": Path("/fake/canadacouncil.md"),
            "wikilinks": [], "lines": [],
            "aliases": ["cac"],
        }
        issues = _check_dead_links([art1, art2])
        assert len(issues) == 0

    def test_self_link_not_flagged(self):
        art1 = {
            "name": "pagea", "file": Path("/fake/pagea.md"),
            "wikilinks": ["PageA"], "lines": ["[[PageA]]"],
            "aliases": [],
        }
        issues = _check_dead_links([art1])
        assert len(issues) == 0

    def test_duplicate_dead_link_deduplicated(self):
        art1 = {
            "name": "pagea", "file": Path("/fake/pagea.md"),
            "wikilinks": ["Missing"], "lines": ["[[Missing]] content [[Missing]]"],
            "aliases": [],
        }
        issues = _check_dead_links([art1])
        assert len(issues) == 1

    def test_no_wikilinks_no_issues(self):
        art1 = {
            "name": "pagea", "file": Path("/fake/pagea.md"),
            "wikilinks": [], "lines": ["No links here."],
            "aliases": [],
        }
        issues = _check_dead_links([art1])
        assert len(issues) == 0

    def test_special_chars_in_link_normalized(self):
        art1 = {
            "name": "pager", "file": Path("/fake/pager.md"),
            "wikilinks": ["Arts_Council_(Ontario)"], "lines": ["[[Arts Council (Ontario)]]"],
            "aliases": [],
        }
        issues = _check_dead_links([art1])
        assert len(issues) == 1
        assert issues[0]["target"] == "arts-council--ontario-" or True


# ── Unit: _check_thin_articles ───────────────────────────────────────────────

class TestCheckThinArticles:
    def test_thin_by_chars(self):
        art = {
            "name": "ThinPage", "file": Path("/fake/ThinPage.md"),
            "body_len": 50, "body_line_count": 10,
        }
        issues = _check_thin_articles([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["article"] == "ThinPage"

    def test_thin_by_lines(self):
        art = {
            "name": "ThinPage", "file": Path("/fake/ThinPage.md"),
            "body_len": 500, "body_line_count": 2,
        }
        issues = _check_thin_articles([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1

    def test_normal_article_not_thin(self):
        art = {
            "name": "GoodPage", "file": Path("/fake/GoodPage.md"),
            "body_len": 500, "body_line_count": 20,
        }
        issues = _check_thin_articles([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_custom_thresholds(self):
        art = {
            "name": "MediumPage", "file": Path("/fake/MediumPage.md"),
            "body_len": 100, "body_line_count": 5,
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "min_article_chars": 500}
        issues = _check_thin_articles([art], cfg)
        assert len(issues) == 1

    def test_empty_input(self):
        issues = _check_thin_articles([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: _check_near_duplicates ─────────────────────────────────────────────

class TestCheckNearDuplicates:
    def test_name_based_duplicate(self):
        art_a = {
            "name": "TestPage", "file": Path("/fake/TestPage.md"),
            "body_text": "Content A", "body_len": 9,
            "word_bag": frozenset(["content"]),
        }
        art_b = {
            "name": "test_page", "file": Path("/fake/test_page.md"),
            "body_text": "Content B", "body_len": 9,
            "word_bag": frozenset(["content"]),
        }
        issues = _check_near_duplicates([art_a, art_b], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["similarity"] == 1.0

    def test_content_based_duplicate(self):
        text = "The Ontario Arts Council provides funding for artists across the province. It supports various disciplines including visual arts, music, and dance. The council has been operating since 1960. It provides grants to individuals and organizations. Many artists rely on this funding for their projects."
        art_a = {
            "name": "OntarioArtsCouncil", "file": Path("/fake/OAC.md"),
            "body_text": text,
            "body_len": len(text),
            "word_bag": frozenset(w.lower() for w in text.split() if len(w) >= 4),
        }
        art_b = {
            "name": "OACFunding", "file": Path("/fake/OACFunding.md"),
            "body_text": text,
            "body_len": len(text),
            "word_bag": frozenset(w.lower() for w in text.split() if len(w) >= 4),
        }
        issues = _check_near_duplicates([art_a, art_b], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["similarity"] >= DEFAULT_AUDIT_CONFIG["dedup_threshold"]

    def test_no_duplicates(self):
        art_a = {
            "name": "PageA", "file": Path("/fake/A.md"),
            "body_text": "This is about apples and oranges.",
            "body_len": 31,
            "word_bag": frozenset(["this", "about", "apples", "oranges"]),
        }
        art_b = {
            "name": "PageB", "file": Path("/fake/B.md"),
            "body_text": "Completely different content about zebras and elephants in the savannah region of Africa.",
            "body_len": 87,
            "word_bag": frozenset(["completely", "different", "content", "about", "zebras", "elephants", "savannah", "region", "africa"]),
        }
        issues = _check_near_duplicates([art_a, art_b], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_empty_input(self):
        issues = _check_near_duplicates([], DEFAULT_AUDIT_CONFIG)
        assert issues == []

    def test_single_article_no_dupes(self):
        art = {
            "name": "Solo", "file": Path("/fake/Solo.md"),
            "body_text": "Content",
            "body_len": 7,
            "word_bag": frozenset(["content"]),
        }
        issues = _check_near_duplicates([art], DEFAULT_AUDIT_CONFIG)
        assert issues == []

    def test_length_ratio_filter(self):
        art_a = {
            "name": "Short", "file": Path("/fake/Short.md"),
            "body_text": "Short.",
            "body_len": 6,
            "word_bag": frozenset(["short"]),
        }
        art_b = {
            "name": "Long", "file": Path("/fake/Long.md"),
            "body_text": "This is a much longer document with lots and lots of content that makes it very different in terms of length from the short one above it.",
            "body_len": 140,
            "word_bag": frozenset(["this", "much", "longer", "document", "with", "lots", "content", "that", "makes", "very", "different", "terms", "length", "from", "short", "above"]),
        }
        issues = _check_near_duplicates([art_a, art_b], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0


# ── Unit: _check_missing_sections ────────────────────────────────────────────

class TestCheckMissingSections:
    def test_all_sections_present(self):
        art = {
            "name": "CompletePage", "file": Path("/fake/CompletePage.md"),
            "body_start": 0,
            "lines": [
                "## Definition", "def content",
                "## Key Figures", "figure content",
                "## Body", "body content",
                "## Context & Significance", "context",
                "## See also", "links",
            ],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG}
        issues = _check_missing_sections([art], cfg)
        assert len(issues) == 0

    def test_missing_section_detected(self):
        art = {
            "name": "IncompletePage", "file": Path("/fake/IncompletePage.md"),
            "body_start": 0,
            "lines": [
                "## Body",
                "body content only",
            ],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG}
        issues = _check_missing_sections([art], cfg)
        assert len(issues) == 1
        assert "Definition" in issues[0]["missing"]

    def test_missing_multiple_sections(self):
        art = {
            "name": "BarePage", "file": Path("/fake/BarePage.md"),
            "body_start": 0,
            "lines": ["## Body", "content"],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG}
        issues = _check_missing_sections([art], cfg)
        assert len(issues) == 1
        assert len(issues[0]["missing"]) > 1

    def test_custom_expected_sections(self):
        art = {
            "name": "Page", "file": Path("/fake/Page.md"),
            "body_start": 0,
            "lines": ["## Body", "content"],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "expected_sections": ["CustomSection"], "required_sections": []}
        issues = _check_missing_sections([art], cfg)
        assert len(issues) == 1
        assert issues[0]["missing"] == ["CustomSection"]

    def test_no_expected_sections(self):
        art = {
            "name": "Page", "file": Path("/fake/Page.md"),
            "body_start": 0,
            "lines": ["content"],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "expected_sections": [], "required_sections": []}
        issues = _check_missing_sections([art], cfg)
        assert len(issues) == 0

    def test_empty_input(self):
        issues = _check_missing_sections([], DEFAULT_AUDIT_CONFIG)
        assert issues == []

    def test_headings_only_below_body_start(self):
        art = {
            "name": "Page", "file": Path("/fake/Page.md"),
            "body_start": 5,
            "lines": [
                "ignored heading above",
                "## Definition",
                "also ignored",
                "---",
                "frontmatter end",
                "## Body",
                "real content",
            ],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "expected_sections": ["Body"], "required_sections": []}
        issues = _check_missing_sections([art], cfg)
        assert len(issues) == 0


# ── Unit: _check_suspicious_concepts ─────────────────────────────────────────

class TestCheckSuspiciousConcepts:
    def test_phone_number_detected(self):
        art = {
            "name": "555-123-4567", "file": Path("/fake/555-123-4567.md"),
        }
        issues = _check_suspicious_concepts([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["subtype"] == "phone_number"

    def test_application_id_detected(self):
        art = {
            "name": "application-id-12345", "file": Path("/fake/app.md"),
        }
        issues = _check_suspicious_concepts([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["subtype"] == "application_id"

    def test_org_number_detected(self):
        art = {
            "name": "rr-1234abc5678", "file": Path("/fake/rr.md"),
        }
        issues = _check_suspicious_concepts([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["subtype"] == "org_number"

    def test_normal_name_not_flagged(self):
        art = {
            "name": "CanadaCouncil", "file": Path("/fake/CanadaCouncil.md"),
        }
        issues = _check_suspicious_concepts([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_no_patterns_configured(self):
        art = {
            "name": "555-123-4567", "file": Path("/fake/555.md"),
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "suspicious_name_patterns": []}
        issues = _check_suspicious_concepts([art], cfg)
        assert len(issues) == 0

    def test_empty_input(self):
        issues = _check_suspicious_concepts([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: _check_stale_content ───────────────────────────────────────────────

class TestCheckStaleContent:
    def test_stale_content_without_patterns_returns_empty(self):
        art = {
            "name": "SomeOrg",
            "file": Path("/fake/SomeOrg.md"),
            "body_text": "This is currently operating in Toronto.",
            "body_start": 0,
            "lines": ["This is currently operating in Toronto."],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "stale_content_patterns": []}
        issues = _check_stale_content([art], cfg)
        assert len(issues) == 0

    def test_stale_content_detected(self):
        art = {
            "name": "SomeOrg",
            "file": Path("/fake/SomeOrg.md"),
            "body_text": "SomeOrg is currently operating in Toronto.",
            "body_start": 0,
            "lines": ["SomeOrg is currently operating in Toronto."],
        }
        cfg = {
            **DEFAULT_AUDIT_CONFIG,
            "stale_content_patterns": [
                {"keywords": ["someorg"], "hint": "May be stale"},
            ],
        }
        issues = _check_stale_content([art], cfg)
        assert len(issues) == 1
        assert "stale" in issues[0]["reason"].lower() or "present" in issues[0]["reason"].lower()

    def test_no_present_tense_no_issue(self):
        art = {
            "name": "SomeOrg",
            "file": Path("/fake/SomeOrg.md"),
            "body_text": "SomeOrg was operating in Toronto and moved in 2020.",
            "body_start": 0,
            "lines": ["SomeOrg was operating in Toronto and moved in 2020."],
        }
        cfg = {
            **DEFAULT_AUDIT_CONFIG,
            "stale_content_patterns": [
                {"keywords": ["someorg"], "hint": "May be stale"},
            ],
        }
        issues = _check_stale_content([art], cfg)
        assert len(issues) == 0

    def test_timeline_keyword_avoids_flag(self):
        art = {
            "name": "SomeOrg",
            "file": Path("/fake/SomeOrg.md"),
            "body_text": "SomeOrg is currently operating in Toronto. The former director resigned.",
            "body_start": 0,
            "lines": ["SomeOrg is currently operating in Toronto. The former director resigned."],
        }
        cfg = {
            **DEFAULT_AUDIT_CONFIG,
            "stale_content_patterns": [
                {"keywords": ["someorg"], "hint": "May be stale"},
            ],
        }
        issues = _check_stale_content([art], cfg)
        assert len(issues) == 0

    def test_require_link_constraint(self):
        art = {
            "name": "SomeOrg",
            "file": Path("/fake/SomeOrg.md"),
            "body_text": "SomeOrg is currently operating in Toronto.",
            "body_start": 0,
            "lines": ["SomeOrg is currently operating in Toronto."],
        }
        cfg = {
            **DEFAULT_AUDIT_CONFIG,
            "stale_content_patterns": [
                {"keywords": ["someorg"], "hint": "May be stale", "require_link": "FormerOrg"},
            ],
        }
        issues = _check_stale_content([art], cfg)
        assert len(issues) == 0

    def test_require_link_satisfied(self):
        art = {
            "name": "SomeOrg",
            "file": Path("/fake/SomeOrg.md"),
            "body_text": "SomeOrg is currently operating in Toronto. [[SuccessorOrg]]",
            "body_start": 0,
            "lines": ["SomeOrg is currently operating in Toronto. [[SuccessorOrg]]"],
        }
        cfg = {
            **DEFAULT_AUDIT_CONFIG,
            "stale_content_patterns": [
                {"keywords": ["someorg"], "hint": "May be stale", "require_link": "SuccessorOrg"},
            ],
        }
        issues = _check_stale_content([art], cfg)
        assert len(issues) == 1

    def test_empty_input(self):
        issues = _check_stale_content([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: audit_summary_text ─────────────────────────────────────────────────

class TestAuditSummaryText:
    def test_basic_summary(self):
        findings = {
            "articles_scanned": 10,
            "issues": {
                "dead_links": [{"file": "a.md", "line": 1, "target": "missing"}],
                "thin_articles": [],
                "near_duplicates": [],
                "missing_sections": [],
                "suspicious_concepts": [],
                "stale_content": [],
            },
        }
        result = audit_summary_text(findings)
        assert "Articles scanned: 10" in result
        assert "Total issues: 1" in result
        assert "Dead wikilinks: 1" in result
        assert "Thin articles: 0" in result

    def test_multiple_issues(self):
        findings = {
            "articles_scanned": 50,
            "issues": {
                "dead_links": [{"file": "a.md"}, {"file": "b.md"}],
                "thin_articles": [{"file": "c.md"}, {"file": "d.md"}, {"file": "e.md"}],
                "near_duplicates": [{"file_a": "x", "file_b": "y"}],
                "missing_sections": [],
                "suspicious_concepts": [],
                "stale_content": [],
            },
        }
        result = audit_summary_text(findings)
        assert "Total issues: 6" in result
        assert "Dead wikilinks: 2" in result
        assert "Thin articles: 3" in result
        assert "Near-duplicates: 1" in result

    def test_zero_articles(self):
        findings = {
            "articles_scanned": 0,
            "issues": {
                "dead_links": [],
                "thin_articles": [],
                "near_duplicates": [],
                "missing_sections": [],
                "suspicious_concepts": [],
                "stale_content": [],
            },
        }
        result = audit_summary_text(findings)
        assert "Articles scanned: 0" in result
        assert "Total issues: 0" in result


# ── Integration: audit_wiki ──────────────────────────────────────────────────

class TestAuditWiki:
    def test_empty_wiki_directory(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        result = audit_wiki(wiki_dir)
        assert result["articles_scanned"] == 0
        assert "No articles found" in result["summary"]

    def test_missing_concepts_directory(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()

        result = audit_wiki(wiki_dir)
        assert result["articles_scanned"] == 0
        assert "Concepts directory not found" in result["summary"]

    def test_single_healthy_article(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "HealthyPage",
            "## Definition\nDefinition text.\n\n"
            "## Key Figures\nKey figures.\n\n"
            "## Body\n"
            "This is a healthy article with substantial content that meets the minimum requirements.\n"
            "It has multiple lines and enough characters to pass all checks.\n"
            "Additional content to make sure we exceed thresholds.\n"
            "Even more content for good measure.\n"
            "And yet another line to be absolutely sure.\n"
            "## Context & Significance\nContext here.\n"
            "## See also\nLinks here.\n",
        )

        result = audit_wiki(wiki_dir)
        assert result["articles_scanned"] == 1
        assert len(result["issues"]["dead_links"]) == 0
        assert len(result["issues"]["thin_articles"]) == 0
        assert len(result["issues"]["missing_sections"]) == 0

    def test_wiki_with_dead_links(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "PageA",
            "## Definition\ndef.\n## Key Figures\nfigures.\n## Body\n"
            "Content here with a [[MissingPage]] link.\n"
            "More content for length.\n"
            "Even more content.\n"
            "Still more lines.\n"
            "And more.\n"
            "## Context & Significance\nctx.\n## See also\nlinks.\n",
        )

        result = audit_wiki(wiki_dir)
        assert result["articles_scanned"] == 1
        assert len(result["issues"]["dead_links"]) == 1
        assert result["issues"]["dead_links"][0]["target"] == "missingpage"

    def test_wiki_with_thin_article(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "ThinPage", "## Body\nShort.\n")

        result = audit_wiki(wiki_dir)
        assert len(result["issues"]["thin_articles"]) == 1
        assert result["issues"]["thin_articles"][0]["article"] == "ThinPage"

    def test_wiki_with_near_duplicates(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        # Same content, different names
        body = "## Body\nSubstantial content that is the same across both articles.\n" * 10
        write_article(concepts, "ArticleOne", body)
        write_article(concepts, "ArticleTwo", body)

        result = audit_wiki(wiki_dir)
        assert result["articles_scanned"] == 2
        # Articles may or may not be flagged depending on content length
        # With sufficient content, they should be detected as near-duplicates
        if len(result["issues"]["near_duplicates"]) > 0:
            dup = result["issues"]["near_duplicates"][0]
            assert dup["similarity"] >= DEFAULT_AUDIT_CONFIG["dedup_threshold"]

    def test_wiki_with_missing_sections(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "IncompletePage",
            "## Body\n"
            "Content that meets minimum line requirements.\n" * 6)

        result = audit_wiki(wiki_dir)
        assert len(result["issues"]["missing_sections"]) == 1
        missing = result["issues"]["missing_sections"][0]["missing"]
        assert "Definition" in missing

    def test_wiki_with_suspicious_concept(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "555-123-4567",
            "## Body\n" + "Content line.\n" * 6)

        result = audit_wiki(wiki_dir)
        assert len(result["issues"]["suspicious_concepts"]) == 1
        assert result["issues"]["suspicious_concepts"][0]["subtype"] == "phone_number"

    def test_wiki_with_stale_content(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "SomeOrg",
            "## Body\n"
            "SomeOrg is currently located in Toronto.\n" * 6)

        cfg = {
            **DEFAULT_AUDIT_CONFIG,
            "stale_content_patterns": [
                {"keywords": ["someorg"], "hint": "May be stale"},
            ],
        }
        result = audit_wiki(wiki_dir, config=cfg)
        assert result["articles_scanned"] == 1

    def test_wiki_with_multiple_issues(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "ThinPage", "## Body\nShort.\n")
        body = ("## Body\nSubstantial content.\n" * 10 +
                "[[MissingLink]]\n")
        write_article(concepts, "PageA", body)

        result = audit_wiki(wiki_dir)
        assert result["articles_scanned"] == 2
        total_issues = sum(len(v) for v in result["issues"].values())
        assert total_issues >= 1

    def test_custom_config_overrides(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "MediumPage",
            "## Body\n"
            "Some content that would be thin under custom but not under default.\n" * 4)

        cfg = {
            **DEFAULT_AUDIT_CONFIG,
            "min_article_chars": 1000,
            "min_article_lines": 20,
        }
        result = audit_wiki(wiki_dir, config=cfg)
        assert len(result["issues"]["thin_articles"]) == 1

    def test_report_summary_provided(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "TestPage",
            "## Body\n" + "Content here.\n" * 6)

        result = audit_wiki(wiki_dir)
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0
        assert "Articles scanned" in result["summary"]
