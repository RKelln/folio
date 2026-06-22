"""Tests for the golden Markdown generator (``folio.core.corpus.generator``).

The authored Markdown is THE golden reference for the synthetic grant corpus
(bead folio-4v7). These tests pin the public contract:

* ``generate_corpus`` is **deterministic** — the same spec yields byte-identical
  Markdown (the headline guarantee, because every derived render is produced
  from this source).
* every requested kind is produced with the requested count;
* every document carries a frontmatter block;
* budget totals are the arithmetic sum of their rows (not faked);
* ``load_profile_headings`` reads canonical heading names from the bundled
  profile YAML and raises on unknown profile/funder;
* ``write_golden`` writes ``<out>/golden/<slug>.md``;
* the corpus is PII-free.

PII note
--------
``pii_scan.scan_text`` is deliberately conservative: it flags ``$``-currency
amounts, 9-digit runs (as possible SINs), phone numbers, emails and postal
codes. An **application** or **budget** document legitimately contains form
fields with email/phone/address/amount values, so scanning those WILL produce
``currency``/``phone``/``email``/``postal_code`` findings *by design* — that is
expected, not a leak. To prove the corpus contains no real PII we scan a
**narrative** document (which has no form fields and no currency) and assert it
is completely clean, then additionally assert that NO document anywhere
contains an actual-PII *name* from the denylist.
"""
from __future__ import annotations

import re

import pytest

from folio.core.corpus.generator import (
    GoldenDoc,
    generate_corpus,
    load_profile_headings,
    write_golden,
)
from folio.core.corpus.pii_scan import scan_text
from folio.core.corpus.spec import ALLOWED_KINDS, CorpusSpec, DocSpec

PROFILE = "canadian-artist-run-centre"

# Detector kinds that indicate a *real* leak no document may ever contain.
#
# Note on what is deliberately EXCLUDED: application/budget/activity documents
# carry Faker-generated form fields (emails, phones, addresses, ``$`` amounts).
# The conservative PII gate flags those as email/phone/postal_code/currency/sin
# — but the values are synthetic, so those findings are EXPECTED for
# form-bearing kinds and are not leaks. The only findings that prove a real PII
# leak across every kind are a denylisted (real) name, or an unscannable file.
# The narrative-clean test (below) separately proves the synthetic *prose*
# never even accidentally produces a PII-shaped string.
_LEAK_KINDS = {"denylisted_name", "unscannable"}


def _spec(
    documents: list[tuple[str, int]],
    *,
    seed: int = 1234,
    funder: str = "OAC",
    profile: str = PROFILE,
) -> CorpusSpec:
    """Build a CorpusSpec from ``(kind, count)`` tuples."""
    return CorpusSpec(
        seed=seed,
        profile=profile,
        funder=funder,
        documents=[DocSpec(kind=kind, count=count) for kind, count in documents],
    )


def _one_of_each_spec(**kwargs) -> CorpusSpec:
    return _spec([(kind, 1) for kind in sorted(ALLOWED_KINDS)], **kwargs)


class TestLoadProfileHeadings:
    def test_oac_returns_nonempty_ordered_list(self):
        headings = load_profile_headings(PROFILE, "OAC")
        assert isinstance(headings, list)
        assert headings, "OAC heading list must be non-empty"
        assert all(isinstance(h, str) and h for h in headings)
        # Canonical names from the profile YAML, in declared order.
        assert headings[0] == "Organization Information"

    @pytest.mark.parametrize("funder", ["OAC", "TAC", "CCA", "BCAH"])
    def test_every_profile_funder_has_headings(self, funder):
        assert load_profile_headings(PROFILE, funder)

    def test_unknown_funder_raises_value_error(self):
        with pytest.raises(ValueError):
            load_profile_headings(PROFILE, "NOPE")

    def test_unknown_profile_raises_value_error(self):
        with pytest.raises(ValueError):
            load_profile_headings("no-such-profile", "OAC")


class TestGenerateCorpusShape:
    def test_returns_golden_docs(self):
        docs = generate_corpus(_spec([("narrative", 1)]))
        assert len(docs) == 1
        assert isinstance(docs[0], GoldenDoc)

    def test_every_kind_produced_with_correct_count(self):
        spec = _spec([(kind, 2) for kind in sorted(ALLOWED_KINDS)])
        docs = generate_corpus(spec)
        assert len(docs) == 2 * len(ALLOWED_KINDS)
        counts: dict[str, int] = {}
        for doc in docs:
            counts[doc.kind] = counts.get(doc.kind, 0) + 1
        assert counts == {kind: 2 for kind in ALLOWED_KINDS}

    def test_stable_document_order(self):
        spec = _spec([("budget", 2), ("narrative", 1)])
        docs = generate_corpus(spec)
        assert [d.kind for d in docs] == ["budget", "budget", "narrative"]

    def test_slug_format(self):
        spec = _spec([("application", 3)], funder="TAC")
        docs = generate_corpus(spec)
        assert [d.slug for d in docs] == [
            "tac-application-01",
            "tac-application-02",
            "tac-application-03",
        ]

    def test_funder_propagated(self):
        docs = generate_corpus(_spec([("narrative", 1)], funder="CCA"))
        assert docs[0].funder == "CCA"

    def test_markdown_contains_frontmatter_block(self):
        docs = generate_corpus(_one_of_each_spec())
        for doc in docs:
            assert doc.markdown.startswith("---\n"), doc.slug
            assert "\n---\n" in doc.markdown, doc.slug
            assert "funder:" in doc.markdown, doc.slug
            assert doc.frontmatter["funder"] == "OAC"

    @pytest.mark.parametrize(
        "kind, expected_type",
        [
            ("application", "application"),
            ("narrative", "report"),
            ("budget", "budget"),
            ("activity_list", "activity_list"),
            ("staff_board", "staff_board"),
            ("support_letter", "support_material"),
        ],
    )
    def test_frontmatter_type_per_kind(self, kind, expected_type):
        doc = generate_corpus(_spec([(kind, 1)]))[0]
        assert doc.frontmatter["type"] == expected_type


class TestDeterminism:
    def test_identical_spec_yields_byte_identical_markdown(self):
        spec = _one_of_each_spec()
        first = generate_corpus(spec)
        second = generate_corpus(spec)
        assert len(first) == len(second)
        for a, b in zip(first, second):
            assert a.slug == b.slug
            assert a.kind == b.kind
            assert a.frontmatter == b.frontmatter
            assert a.markdown == b.markdown

    def test_independent_specs_same_seed_match(self):
        docs_a = generate_corpus(_spec([("narrative", 2), ("budget", 1)]))
        docs_b = generate_corpus(_spec([("narrative", 2), ("budget", 1)]))
        assert [d.markdown for d in docs_a] == [d.markdown for d in docs_b]

    def test_different_seed_changes_output(self):
        a = generate_corpus(_spec([("narrative", 1)], seed=1))[0]
        b = generate_corpus(_spec([("narrative", 1)], seed=2))[0]
        assert a.markdown != b.markdown


# --------------------------------------------------------------------------- #
# Budget table parsing helpers + tests
# --------------------------------------------------------------------------- #
_MONEY_RE = re.compile(r"\$\s*([\d,]+)")


def _money_to_int(cell: str) -> int:
    match = _MONEY_RE.search(cell)
    assert match, f"no money value in cell: {cell!r}"
    return int(match.group(1).replace(",", ""))


def _parse_pipe_table_section(markdown: str, sub_heading: str) -> list[list[str]]:
    """Return the data rows (as cell lists) of the pipe table under ``### X``."""
    lines = markdown.splitlines()
    rows: list[list[str]] = []
    capturing = False
    for line in lines:
        stripped = line.strip()
        if stripped == f"### {sub_heading}":
            capturing = True
            continue
        if capturing:
            if stripped.startswith("###") or stripped.startswith("##"):
                break
            if not stripped.startswith("|"):
                if rows:
                    break
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            rows.append(cells)
    return rows


def _data_rows(rows: list[list[str]]) -> tuple[list[list[str]], list[str]]:
    """Split a parsed table into (non-header/non-separator/non-total, total)."""
    body = rows[2:]  # drop header row + ``| --- | --- |`` separator
    total_row = next(r for r in body if "total" in r[0].lower())
    data = [r for r in body if "total" not in r[0].lower()]
    return data, total_row


class TestBudget:
    def test_budget_has_two_tables(self):
        doc = generate_corpus(_spec([("budget", 1)]))[0]
        assert "## Budget" in doc.markdown
        assert "### Revenue" in doc.markdown
        assert "### Expenses" in doc.markdown

    @pytest.mark.parametrize("section", ["Revenue", "Expenses"])
    def test_totals_equal_row_sums(self, section):
        doc = generate_corpus(_spec([("budget", 1)]))[0]
        rows = _parse_pipe_table_section(doc.markdown, section)
        assert rows, f"no rows parsed for {section}"
        data, total_row = _data_rows(rows)
        computed = sum(_money_to_int(r[1]) for r in data)
        declared = _money_to_int(total_row[1])
        assert computed == declared, f"{section}: {computed} != {declared}"

    def test_revenue_table_exact_shape(self):
        doc = generate_corpus(_spec([("budget", 1)]))[0]
        assert "| Source | Amount |" in doc.markdown
        assert "| --- | --- |" in doc.markdown
        assert "| **Total revenue** |" in doc.markdown


class TestTabularKinds:
    def test_activity_list_table_columns(self):
        doc = generate_corpus(_spec([("activity_list", 1)]))[0]
        assert "| Date | Activity | Location |" in doc.markdown
        rows = [
            ln
            for ln in doc.markdown.splitlines()
            if ln.startswith("|") and "---" not in ln
        ]
        # header + 6..12 data rows
        assert 7 <= len(rows) <= 13

    def test_staff_board_table_columns(self):
        doc = generate_corpus(_spec([("staff_board", 1)]))[0]
        assert "| Name | Role |" in doc.markdown

    def test_support_letter_has_letter_structure(self):
        doc = generate_corpus(_spec([("support_letter", 1)]))[0]
        body = doc.markdown
        assert "Dear" in body
        assert "Sincerely" in body or "Yours" in body


class TestApplication:
    def test_application_has_labelled_form_fields(self):
        doc = generate_corpus(_spec([("application", 1)]))[0]
        for label in (
            "**Applicant:**",
            "**Email:**",
            "**Phone:**",
            "**Organization:**",
            "**Address:**",
            "**Request Amount:**",
            "**Project Title:**",
            "**Submission Date:**",
        ):
            assert label in doc.markdown, label

    def test_application_renders_profile_headings(self):
        doc = generate_corpus(_spec([("application", 1)], funder="CCA"))[0]
        for heading in load_profile_headings(PROFILE, "CCA"):
            assert f"## {heading}" in doc.markdown, heading


class TestGrantAmountConsistency:
    """folio-1lk: the single per-document grant figure must be byte-identical
    across the frontmatter, the application ``Request Amount`` line, and the
    budget ``Grant — <funder> Project`` Revenue row (golden-corpus internal
    consistency — no contradictory amounts inside one document).
    """

    def test_application_request_amount_matches_frontmatter(self):
        doc = generate_corpus(_spec([("application", 1)], funder="OAC"))[0]
        expected = doc.frontmatter["grant_amount"]
        request_lines = [
            ln
            for ln in doc.markdown.splitlines()
            if ln.startswith("**Request Amount:**")
        ]
        assert len(request_lines) == 1, request_lines
        amount = request_lines[0].split("**Request Amount:**", 1)[1].strip()
        assert amount == expected

    def test_budget_grant_row_matches_frontmatter(self):
        funder = "OAC"
        doc = generate_corpus(_spec([("budget", 1)], funder=funder))[0]
        expected = doc.frontmatter["grant_amount"]
        grant_label = f"Grant \u2014 {funder} Project"
        grant_rows = [
            ln
            for ln in doc.markdown.splitlines()
            if ln.startswith("|") and grant_label in ln
        ]
        assert len(grant_rows) == 1, grant_rows
        cells = [c.strip() for c in grant_rows[0].strip("|").split("|")]
        assert cells[1] == expected


class TestPiiFree:
    def test_narrative_document_is_completely_clean(self):
        """A narrative has no form fields and no currency, so it must scan
        completely clean. This is the strongest proof the synthetic content
        carries no PII (no emails, phones, SINs, postal codes, or real names).
        """
        doc = generate_corpus(_spec([("narrative", 1)]))[0]
        findings = scan_text(doc.markdown)
        assert findings == [], f"narrative not clean: {findings}"

    def test_no_document_contains_a_real_pii_leak(self):
        """Across every kind (including application/budget/activity where
        synthetic email/phone/currency findings are EXPECTED), no document may
        contain a real leak: a denylisted (real) name, or unscannable content.
        We filter out the structural-only detectors and assert the leak
        detectors never fire.
        """
        docs = generate_corpus(_one_of_each_spec())
        offenders: list[tuple[str, str, str]] = []
        for doc in docs:
            for finding in scan_text(doc.markdown):
                if finding.kind in _LEAK_KINDS:
                    offenders.append((doc.slug, finding.kind, finding.match))
        assert offenders == [], f"real-PII leaks: {offenders}"


class TestWriteGolden:
    def test_writes_file_and_returns_path(self, tmp_path):
        doc = generate_corpus(_spec([("narrative", 1)]))[0]
        out = write_golden(doc, tmp_path)
        assert out == tmp_path / "golden" / f"{doc.slug}.md"
        assert out.exists()
        assert out.read_text(encoding="utf-8") == doc.markdown

    def test_creates_nested_dirs(self, tmp_path):
        doc = generate_corpus(_spec([("budget", 1)]))[0]
        target = tmp_path / "deep" / "nested"
        out = write_golden(doc, target)
        assert out == target / "golden" / f"{doc.slug}.md"
        assert out.exists()
