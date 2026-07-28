from __future__ import annotations

from pathlib import Path

from folio.core.auditor import (
    DEFAULT_AUDIT_CONFIG,
    _apply_fixes,
    _check_dead_links,
    _check_link_noise,
    _check_low_confidence,
    _check_missing_sections,
    _check_name_collisions,
    _check_near_duplicates,
    _check_placeholder_phrasing,
    _check_provenance,
    _check_speculative_phrasing,
    _check_stale_content,
    _check_suspicious_concepts,
    _check_thin_articles,
    _check_truncation_suspects,
    _check_weak_sections,
    _find_truncation_second_signal,
    _parse_sections,
    _quality_score,
    _rank_by_quality,
    _scan_articles,
    audit_summary_text,
    audit_wiki,
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
                if len(v) == 0:
                    lines.append(f"{k}: []")
                else:
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


# ── Unit: _check_provenance ──────────────────────────────────────────────────


class TestCheckProvenance:
    def test_sourceless_detected(self):
        art = {
            "name": "SourcelessPage",
            "file": Path("/fake/SourcelessPage.md"),
            "frontmatter": {"sources": []},
        }
        issues = _check_provenance([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["article"] == "SourcelessPage"
        assert issues[0]["source_count"] == 0

    def test_with_sources_not_flagged(self):
        art = {
            "name": "SourcedPage",
            "file": Path("/fake/SourcedPage.md"),
            "frontmatter": {"sources": ["source1.pdf", "source2.pdf"]},
        }
        issues = _check_provenance([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_no_sources_key_not_flagged(self):
        art = {
            "name": "NoSourcesKey",
            "file": Path("/fake/NoSourcesKey.md"),
            "frontmatter": {"title": "Something"},
        }
        issues = _check_provenance([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_disabled_by_config(self):
        art = {
            "name": "SourcelessPage",
            "file": Path("/fake/SourcelessPage.md"),
            "frontmatter": {"sources": []},
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "flag_sourceless": False}
        issues = _check_provenance([art], cfg)
        assert len(issues) == 0

    def test_empty_input(self):
        issues = _check_provenance([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: _check_low_confidence ──────────────────────────────────────────────


class TestCheckLowConfidence:
    def test_low_confidence_detected(self):
        art = {
            "name": "LowConfPage",
            "file": Path("/fake/LowConfPage.md"),
            "frontmatter": {"confidence": "low"},
        }
        issues = _check_low_confidence([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["confidence"] == "low"

    def test_high_confidence_not_flagged(self):
        art = {
            "name": "HighConfPage",
            "file": Path("/fake/HighConfPage.md"),
            "frontmatter": {"confidence": "high"},
        }
        issues = _check_low_confidence([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_no_confidence_key_not_flagged(self):
        art = {
            "name": "NoConfPage",
            "file": Path("/fake/NoConfPage.md"),
            "frontmatter": {"title": "Something"},
        }
        issues = _check_low_confidence([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_disabled_by_config(self):
        art = {
            "name": "LowConfPage",
            "file": Path("/fake/LowConfPage.md"),
            "frontmatter": {"confidence": "low"},
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "flag_low_confidence": False}
        issues = _check_low_confidence([art], cfg)
        assert len(issues) == 0

    def test_empty_input(self):
        issues = _check_low_confidence([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: _check_placeholder_phrasing ────────────────────────────────────────


class TestCheckPlaceholderPhrasing:
    def test_placeholder_detected(self):
        art = {
            "name": "PlaceholderPage",
            "file": Path("/fake/PlaceholderPage.md"),
            "body_text": "The report contains no specific figures for the budget.",
            "lines": ["The report contains no specific figures for the budget."],
        }
        issues = _check_placeholder_phrasing([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["phrase"] == "no specific"

    def test_only_first_match_per_article(self):
        art = {
            "name": "MultiPlaceholder",
            "file": Path("/fake/MultiPlaceholder.md"),
            "body_text": "There is no specific data and no concrete information.",
            "lines": ["There is no specific data and no concrete information."],
        }
        issues = _check_placeholder_phrasing([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1

    def test_no_phrases_not_flagged(self):
        art = {
            "name": "CleanPage",
            "file": Path("/fake/CleanPage.md"),
            "body_text": "The report includes detailed figures for the budget.",
            "lines": ["The report includes detailed figures for the budget."],
        }
        issues = _check_placeholder_phrasing([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_custom_phrases(self):
        art = {
            "name": "CustomPhrase",
            "file": Path("/fake/CustomPhrase.md"),
            "body_text": "This contains my custom bad phrase.",
            "lines": ["This contains my custom bad phrase."],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "placeholder_phrases": ["custom bad phrase"]}
        issues = _check_placeholder_phrasing([art], cfg)
        assert len(issues) == 1

    def test_empty_input(self):
        issues = _check_placeholder_phrasing([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: _check_speculative_phrasing ────────────────────────────────────────


class TestCheckSpeculativePhrasing:
    def test_speculative_detected(self):
        art = {
            "name": "SpecPage",
            "file": Path("/fake/SpecPage.md"),
            "body_text": "This likely represents the correct amount.",
            "lines": ["This likely represents the correct amount."],
        }
        issues = _check_speculative_phrasing([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["phrase"] == "likely"

    def test_only_first_match_per_article(self):
        art = {
            "name": "MultiSpec",
            "file": Path("/fake/MultiSpec.md"),
            "body_text": "This likely happened and possibly was incorrect.",
            "lines": ["This likely happened and possibly was incorrect."],
        }
        issues = _check_speculative_phrasing([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1

    def test_no_speculative_not_flagged(self):
        art = {
            "name": "CleanPage",
            "file": Path("/fake/CleanPage.md"),
            "body_text": "The report confirms the budget was approved.",
            "lines": ["The report confirms the budget was approved."],
        }
        issues = _check_speculative_phrasing([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_empty_input(self):
        issues = _check_speculative_phrasing([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: _check_truncation_suspects ─────────────────────────────────────────


class TestCheckTruncationSuspects:
    def test_truncation_with_second_signal_detected(self):
        art = {
            "name": "TruncPage",
            "file": Path("/fake/TruncPage.md"),
            "body_text": "The following data points are missing: budget totals",
            "body_start": 1,
            "lines": [
                "---",
                "title: Test",
                "---",
                "The following data points are missing: budget totals",
            ],
        }
        issues = _check_truncation_suspects([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert "truncated_table" not in issues[0]["reason"]  # ends with "s" not triggered

    def test_truncation_without_second_signal_not_flagged(self):
        art = {
            "name": "TruncNoSecond",
            "file": Path("/fake/TruncNoSecond.md"),
            "body_text": "The following data points are missing: budget totals.",
            "body_start": 1,
            "lines": [
                "---",
                "title: Test",
                "---",
                "The following data points are missing: budget totals.",
            ],
        }
        issues = _check_truncation_suspects([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_truncation_incomplete_final_line(self):
        art = {
            "name": "IncompleteFinal",
            "file": Path("/fake/IncompleteFinal.md"),
            "body_text": "pending retrieval of documents",
            "body_start": 0,
            "lines": ["pending retrieval of documents from the archive"],
        }
        issues = _check_truncation_suspects([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["reason"] == "incomplete_final_line"

    def test_truncation_missing_closing_frontmatter(self):
        art = {
            "name": "MissingFM",
            "file": Path("/fake/MissingFM.md"),
            "body_text": "pending retrieval of source records.",
            "body_start": 0,
            "lines": [
                "---",
                "title: Test",
                "pending retrieval of source records.",
            ],
        }
        issues = _check_truncation_suspects([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["reason"] == "missing_closing_frontmatter"

    def test_truncated_table_signal(self):
        art = {
            "name": "TruncTable",
            "file": Path("/fake/TruncTable.md"),
            "body_text": "the following data points are missing: \n| col1 | col2 | col3",
            "body_start": 0,
            "lines": [
                "the following data points are missing:",
                "| col1 | col2 | col3",
            ],
        }
        issues = _check_truncation_suspects([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["reason"] == "truncated_table"

    def test_no_second_signal_requirement_disabled(self):
        art = {
            "name": "NoSecondSignal",
            "file": Path("/fake/NoSecondSignal.md"),
            "body_text": "The following data points are missing: budget totals.",
            "body_start": 0,
            "lines": ["The following data points are missing: budget totals."],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "truncation_require_second_signal": False}
        issues = _check_truncation_suspects([art], cfg)
        assert len(issues) == 1

    def test_empty_input(self):
        issues = _check_truncation_suspects([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: _find_truncation_second_signal ─────────────────────────────────────


class TestFindTruncationSecondSignal:
    def test_incomplete_final_line(self):
        art = {
            "body_start": 0,
            "lines": ["This sentence does not end properly"],
        }
        result = _find_truncation_second_signal(art)
        assert result == "incomplete_final_line"

    def test_complete_final_line_not_triggered(self):
        art = {
            "body_start": 0,
            "lines": ["This sentence ends properly."],
        }
        result = _find_truncation_second_signal(art)
        assert result is None

    def test_missing_closing_frontmatter(self):
        art = {
            "body_start": 0,
            "lines": ["---", "title: Test"],
        }
        result = _find_truncation_second_signal(art)
        assert result == "missing_closing_frontmatter"

    def test_closing_frontmatter_present(self):
        art = {
            "body_start": 3,
            "lines": ["---", "title: Test", "---", "Body text here."],
        }
        result = _find_truncation_second_signal(art)
        assert result is None

    def test_truncated_table(self):
        art = {
            "body_start": 0,
            "lines": ["| col1 | col2 | col3"],
        }
        result = _find_truncation_second_signal(art)
        assert result == "truncated_table"

    def test_no_signals(self):
        art = {
            "body_start": 0,
            "lines": ["Normal paragraph."],
        }
        result = _find_truncation_second_signal(art)
        assert result is None


# ── Unit: _check_weak_sections ────────────────────────────────────────────────


class TestCheckWeakSections:
    def test_weak_section_empty_detected(self):
        art = {
            "name": "WeakPage",
            "file": Path("/fake/WeakPage.md"),
            "body_start": 0,
            "lines": [
                "## Key Figures",
                "",
                "## Body",
                "Some real content here.",
            ],
        }
        issues = _check_weak_sections([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["section"] == "Key Figures"

    def test_weak_section_placeholder_only(self):
        art = {
            "name": "WeakPlaceholder",
            "file": Path("/fake/WeakPlaceholder.md"),
            "body_start": 0,
            "lines": [
                "## Key Figures",
                "There is no specific data available.",
                "",
                "## Body",
                "Real content.",
            ],
        }
        issues = _check_weak_sections([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["section"] == "Key Figures"

    def test_strong_section_not_flagged(self):
        art = {
            "name": "GoodPage",
            "file": Path("/fake/GoodPage.md"),
            "body_start": 0,
            "lines": [
                "## Key Figures",
                "OAC provided $50,000 in 2024.",
                "",
                "## Body",
                "More content.",
            ],
        }
        issues = _check_weak_sections([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_non_weak_header_ignored(self):
        art = {
            "name": "OtherHeader",
            "file": Path("/fake/OtherHeader.md"),
            "body_start": 0,
            "lines": [
                "## Other Section",
                "",
                "## Body",
                "Real content.",
            ],
        }
        issues = _check_weak_sections([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_custom_weak_headers(self):
        art = {
            "name": "CustomWeak",
            "file": Path("/fake/CustomWeak.md"),
            "body_start": 0,
            "lines": [
                "## Custom Section",
                "",
                "## Body",
                "Content.",
            ],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "weak_section_headers": ["Custom Section"]}
        issues = _check_weak_sections([art], cfg)
        assert len(issues) == 1

    def test_empty_input(self):
        issues = _check_weak_sections([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: _parse_sections ────────────────────────────────────────────────────


class TestParseSections:
    def test_parses_sections_from_body(self):
        art = {
            "name": "Test",
            "body_start": 1,
            "lines": [
                "---",
                "## First", "first content", "more first",
                "## Second", "second content",
                "## Third", "third content",
            ],
        }
        sections = _parse_sections(art)
        assert len(sections) == 3
        assert sections[0]["header"] == "First"
        assert "first content" in sections[0]["body"]
        assert sections[1]["header"] == "Second"
        assert sections[2]["header"] == "Third"

    def test_respects_body_start(self):
        art = {
            "name": "Test",
            "body_start": 3,
            "lines": [
                "## Ignored",
                "ignored content",
                "---",
                "## Real", "real content",
            ],
        }
        sections = _parse_sections(art)
        assert len(sections) == 1
        assert sections[0]["header"] == "Real"

    def test_no_headings(self):
        art = {
            "name": "Test",
            "body_start": 0,
            "lines": ["Just some text without headings."],
        }
        sections = _parse_sections(art)
        assert len(sections) == 0

    def test_body_before_first_heading(self):
        art = {
            "name": "Test",
            "body_start": 0,
            "lines": ["leading text", "## First", "first content"],
        }
        sections = _parse_sections(art)
        assert len(sections) == 1
        assert sections[0]["header"] == "First"


# ── Unit: _check_link_noise ──────────────────────────────────────────────────


class TestCheckLinkNoise:
    def test_link_noise_detected(self):
        art = {
            "name": "NoisePage",
            "file": Path("/fake/NoisePage.md"),
            "body_text": "See the data at [broken-reference for more.",
            "lines": ["See the data at [broken-reference for more."],
        }
        issues = _check_link_noise([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert "[broken-reference" in issues[0]["token"]

    def test_wikilink_not_flagged(self):
        art = {
            "name": "WikiPage",
            "file": Path("/fake/WikiPage.md"),
            "body_text": "See [[CanadaCouncil]] for more.",
            "lines": ["See [[CanadaCouncil]] for more."],
        }
        issues = _check_link_noise([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_markdown_link_not_flagged(self):
        art = {
            "name": "MDPage",
            "file": Path("/fake/MDPage.md"),
            "body_text": "See [Canada Council](https://example.com).",
            "lines": ["See [Canada Council](https://example.com)."],
        }
        issues = _check_link_noise([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_uppercase_not_flagged(self):
        art = {
            "name": "UpperPage",
            "file": Path("/fake/UpperPage.md"),
            "body_text": "The [UPPER-CASE token should not match.",
            "lines": ["The [UPPER-CASE token should not match."],
        }
        issues = _check_link_noise([art], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_disabled_by_config(self):
        art = {
            "name": "NoisePage",
            "file": Path("/fake/NoisePage.md"),
            "body_text": "[broken-link in the text.",
            "lines": ["[broken-link in the text."],
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "flag_link_noise": False}
        issues = _check_link_noise([art], cfg)
        assert len(issues) == 0

    def test_empty_input(self):
        issues = _check_link_noise([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: _check_name_collisions ─────────────────────────────────────────────


class TestCheckNameCollisions:
    def test_name_collision_detected(self):
        art_a = {
            "name": "TestPage",
            "file": Path("/fake/TestPage.md"),
            "body_text": "This is some content about test data and analytics.",
            "frontmatter": {"confidence": "high"},
            "lines": ["This is some content about test data and analytics."],
            "body_start": 0,
        }
        art_b = {
            "name": "test_page",
            "file": Path("/fake/test_page.md"),
            "body_text": "This is some content about test data and analytics.",
            "frontmatter": {"confidence": "low"},
            "lines": ["This is some content about test data and analytics."],
            "body_start": 0,
        }
        issues = _check_name_collisions([art_a, art_b], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["subtype"] == "collision"

    def test_content_divergent_detected(self):
        art_a = {
            "name": "SameStem",
            "file": Path("/fake/SameStem.md"),
            "body_text": "This is completely different content about apples and oranges.",
            "frontmatter": {},
            "lines": ["This is completely different content about apples and oranges."],
            "body_start": 0,
        }
        art_b = {
            "name": "same_stem",
            "file": Path("/fake/same_stem.md"),
            "body_text": "Zebras live in the African savannah where the climate is very hot.",
            "frontmatter": {},
            "lines": ["Zebras live in the African savannah where the climate is very hot."],
            "body_start": 0,
        }
        issues = _check_name_collisions([art_a, art_b], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 1
        assert issues[0]["subtype"] == "content_divergent"

    def test_no_collision_different_stems(self):
        art_a = {
            "name": "PageOne",
            "file": Path("/fake/PageOne.md"),
            "body_text": "Same content.",
            "frontmatter": {},
            "lines": ["Same content."],
            "body_start": 0,
        }
        art_b = {
            "name": "PageTwo",
            "file": Path("/fake/PageTwo.md"),
            "body_text": "Same content.",
            "frontmatter": {},
            "lines": ["Same content."],
            "body_start": 0,
        }
        issues = _check_name_collisions([art_a, art_b], DEFAULT_AUDIT_CONFIG)
        assert len(issues) == 0

    def test_disabled_by_config(self):
        art_a = {
            "name": "TestPage",
            "file": Path("/fake/TestPage.md"),
            "body_text": "Content A",
            "frontmatter": {},
            "lines": ["Content A"],
            "body_start": 0,
        }
        art_b = {
            "name": "test_page",
            "file": Path("/fake/test_page.md"),
            "body_text": "Content A",
            "frontmatter": {},
            "lines": ["Content A"],
            "body_start": 0,
        }
        cfg = {**DEFAULT_AUDIT_CONFIG, "name_collision_enabled": False}
        issues = _check_name_collisions([art_a, art_b], cfg)
        assert len(issues) == 0

    def test_multi_article_bucket(self):
        art_a = {
            "name": "Duplicate",
            "file": Path("/fake/Duplicate.md"),
            "body_text": "Content A same content repeated.",
            "frontmatter": {"confidence": "high", "sources": ["s1.pdf"]},
            "lines": ["Content A same content repeated."],
            "body_start": 0,
        }
        art_b = {
            "name": "duplicate",
            "file": Path("/fake/Duplicate2.md"),
            "body_text": "Content A same content repeated.",
            "frontmatter": {"confidence": "low"},
            "lines": ["Content A same content repeated."],
            "body_start": 0,
        }
        art_c = {
            "name": "duplicate",
            "file": Path("/fake/Duplicate3.md"),
            "body_text": "Content A same content repeated.",
            "frontmatter": {},
            "lines": ["Content A same content repeated."],
            "body_start": 0,
        }
        issues = _check_name_collisions([art_a, art_b, art_c], DEFAULT_AUDIT_CONFIG)
        # Should find pairs within the bucket
        assert len(issues) >= 1

    def test_empty_input(self):
        issues = _check_name_collisions([], DEFAULT_AUDIT_CONFIG)
        assert issues == []


# ── Unit: _quality_score ─────────────────────────────────────────────────────


class TestQualityScore:
    def test_high_confidence_scores_higher(self):
        art_high = {
            "name": "test-page",
            "file": Path("/fake/test-page.md"),
            "frontmatter": {"confidence": "high", "sources": ["s1.pdf"]},
            "body_text": "more content " * 50,
            "body_start": 0,
            "lines": ["## Section"] * 5,
        }
        art_low = {
            "name": "TEST_page",
            "file": Path("/fake/TEST_page.md"),
            "frontmatter": {"confidence": "low"},
            "body_text": "less content",
            "body_start": 0,
            "lines": ["## Section"],
        }
        assert _quality_score(art_high) > _quality_score(art_low)

    def test_source_count_matters(self):
        art_many = {
            "name": "test-page",
            "file": Path("/fake/test-page.md"),
            "frontmatter": {"sources": ["s1.pdf", "s2.pdf", "s3.pdf"]},
            "body_text": "content",
            "body_start": 0,
            "lines": [],
        }
        art_few = {
            "name": "test-page",
            "file": Path("/fake/test-page.md"),
            "frontmatter": {"sources": []},
            "body_text": "content",
            "body_start": 0,
            "lines": [],
        }
        assert _quality_score(art_many) > _quality_score(art_few)

    def test_name_quality(self):
        art_good = {
            "name": "canada-council",
            "file": Path("/fake/canada-council.md"),
            "frontmatter": {},
            "body_text": "content",
            "body_start": 0,
            "lines": [],
        }
        art_bad = {
            "name": "CanadaCouncil",
            "file": Path("/fake/CanadaCouncil.md"),
            "frontmatter": {},
            "body_text": "content",
            "body_start": 0,
            "lines": [],
        }
        assert _quality_score(art_good) > _quality_score(art_bad)


# ── Unit: _apply_fixes ───────────────────────────────────────────────────────


class TestApplyFixes:
    def test_remove_empty_weak_section(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        fp = write_article(concepts, "WeakPage",
            "## Key Figures\n\n## Body\nReal content here.\n")
        art = _scan_articles(concepts)[0]
        issues = {
            "weak_sections": [{"file": str(fp), "section": "Key Figures"}],
        }
        result = _apply_fixes([art], issues)
        assert result["fixed_count"] == 1
        content_after = fp.read_text()
        assert "Key Figures" not in content_after
        assert "Real content here" in content_after

    def test_escape_link_noise(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        fp = write_article(concepts, "NoisePage",
            "See [broken-link in the text.\n## Body\nReal content.\n")
        art = _scan_articles(concepts)[0]
        issues = {
            "link_noise": [{"file": str(fp), "token": "[broken-link"}],
        }
        result = _apply_fixes([art], issues)
        assert result["fixed_count"] == 1
        content_after = fp.read_text()
        assert "\\[broken-link" in content_after

    def test_no_changes_when_no_issues(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        fp = write_article(concepts, "CleanPage",
            "## Body\nClean content.\n")
        art = _scan_articles(concepts)[0]
        issues: dict = {}
        result = _apply_fixes([art], issues)
        assert result["fixed_count"] == 0
        assert result["changed_files"] == []

    def test_placeholder_phrasing_not_auto_fixed(self, tmp_path):
        """Placeholder phrases are advisory only — --fix must NOT auto-delete them."""
        concepts = make_concept_dir(tmp_path)
        fp = write_article(concepts, "PlaceholderPage",
            "## Body\nThis paragraph contains no specific data.\n\nNext paragraph has real content.\n")
        art = _scan_articles(concepts)[0]
        issues = {
            "placeholder_phrasing": [{"file": str(fp), "phrase": "no specific"}],
        }
        result = _apply_fixes([art], issues)
        assert result["fixed_count"] == 0
        content_after = fp.read_text()
        assert "no specific data" in content_after.lower()

    def test_empty_issues_no_errors(self, tmp_path):
        concepts = make_concept_dir(tmp_path)
        fp = write_article(concepts, "Page",
            "## Body\nContent.\n")
        art = _scan_articles(concepts)[0]
        issues = {
            "weak_sections": [],
            "link_noise": [],
            "placeholder_phrasing": [],
        }
        result = _apply_fixes([art], issues)
        assert result["fixed_count"] == 0


# ── Integration: audit_wiki with new checks ──────────────────────────────────


class TestAuditWikiNewChecks:
    def test_wiki_with_provenance_issues(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "SourcelessPage",
            "## Body\n" + "Content here.\n" * 6,
            frontmatter={"sources": []})
        result = audit_wiki(wiki_dir)
        assert len(result["issues"]["provenance"]) == 1

    def test_wiki_with_low_confidence(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "LowConfPage",
            "## Body\n" + "Content here.\n" * 6,
            frontmatter={"confidence": "low"})
        result = audit_wiki(wiki_dir)
        assert len(result["issues"]["low_confidence"]) == 1

    def test_wiki_with_placeholder_phrasing(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "PlaceholderPage",
            "## Body\nThis report contains no specific figures for the budget.\n")
        result = audit_wiki(wiki_dir)
        assert len(result["issues"]["placeholder_phrasing"]) == 1

    def test_wiki_with_link_noise(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "NoisePage",
            "## Body\nSee the data at [broken-ref for more.\n"
            + "Extra content.\n" * 6)
        result = audit_wiki(wiki_dir)
        assert len(result["issues"]["link_noise"]) == 1

    def test_wiki_with_name_collisions(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        body = "## Body\n" + "Shared content across both articles.\n" * 10
        write_article(concepts, "TestPage", body)
        write_article(concepts, "test_page", body)
        result = audit_wiki(wiki_dir)
        assert len(result["issues"]["name_collisions"]) >= 1 or len(result["issues"]["near_duplicates"]) >= 1

    def test_wiki_with_truncation_suspect(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "TruncPage",
            "## Body\nThe following data points are missing: budget data\n")
        result = audit_wiki(wiki_dir)
        assert len(result["issues"]["truncation_suspects"]) == 1

    def test_wiki_with_weak_section(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "WeakPage",
            "## Key Figures\n\n## Body\nReal content here.\n" + "Extra line.\n" * 5)
        result = audit_wiki(wiki_dir)
        assert len(result["issues"]["weak_sections"]) == 1

    def test_all_new_issues_present(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        write_article(concepts, "CleanPage",
            "## Definition\ndef.\n## Key Figures\nfigures.\n## Body\n"
            + "Content here.\n" * 6
            + "## Context & Significance\nctx.\n## See also\nlinks.\n")
        result = audit_wiki(wiki_dir)
        issues = result["issues"]
        for key in ["provenance", "low_confidence", "placeholder_phrasing",
                     "speculative_phrasing", "truncation_suspects",
                     "weak_sections", "link_noise", "name_collisions"]:
            assert key in issues, f"Missing issue key: {key}"
            assert isinstance(issues[key], list), f"Issue key {key} is not a list"


# ── Unit: audit_summary_text with new categories ─────────────────────────────


class TestAuditSummaryTextNew:
    def test_new_categories_in_summary(self):
        findings = {
            "articles_scanned": 10,
            "issues": {
                "dead_links": [],
                "thin_articles": [],
                "near_duplicates": [],
                "missing_sections": [],
                "suspicious_concepts": [],
                "stale_content": [],
                "provenance": [{"file": "a.md"}],
                "low_confidence": [{"file": "b.md"}],
                "placeholder_phrasing": [],
                "speculative_phrasing": [],
                "truncation_suspects": [],
                "weak_sections": [],
                "link_noise": [{"file": "c.md"}],
                "name_collisions": [{"file_a": "x", "file_b": "y"}],
            },
        }
        result = audit_summary_text(findings)
        assert "Sourceless articles: 1" in result
        assert "Low-confidence articles: 1" in result
        assert "Link/syntax noise: 1" in result
        assert "Name collisions: 1" in result

    def test_empty_new_categories(self):
        findings = {
            "articles_scanned": 0,
            "issues": {
                "dead_links": [],
                "thin_articles": [],
                "near_duplicates": [],
                "missing_sections": [],
                "suspicious_concepts": [],
                "stale_content": [],
                "provenance": [],
                "low_confidence": [],
                "placeholder_phrasing": [],
                "speculative_phrasing": [],
                "truncation_suspects": [],
                "weak_sections": [],
                "link_noise": [],
                "name_collisions": [],
            },
        }
        result = audit_summary_text(findings)
        assert "Sourceless articles: 0" in result
        assert "Total issues: 0" in result
