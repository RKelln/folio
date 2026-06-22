"""Tests for the corpus PII scan gate (folio.core.corpus.pii_scan).

These tests exercise the safety mechanism that must pass before any synthetic
corpus file is committed. They cover each PII kind (positive + negative cases),
denylist matching semantics (case-insensitive, whole-word), file scanning for
text formats, the PIIReport.clean property, and loading the bundled denylist.
"""
from __future__ import annotations

import pytest

from folio.core.corpus.pii_scan import (
    Finding,
    PIIReport,
    load_denylist,
    scan_file,
    scan_paths,
    scan_text,
)


def _kinds(findings: list[Finding]) -> set[str]:
    return {f.kind for f in findings}


class TestLoadDenylist:
    def test_loads_bundled_default_without_args(self):
        names = load_denylist()
        assert isinstance(names, list)
        assert names, "bundled denylist should not be empty"
        assert all(isinstance(n, str) for n in names)
        assert any(n.lower() == "john doe" for n in names)

    def test_loads_from_explicit_path(self, tmp_path):
        path = tmp_path / "deny.yaml"
        path.write_text("names:\n  - Specific Person\n  - Other Org\n")
        names = load_denylist(path)
        assert names == ["Specific Person", "Other Org"]

    def test_missing_names_key_returns_empty(self, tmp_path):
        path = tmp_path / "deny.yaml"
        path.write_text("other: value\n")
        assert load_denylist(path) == []


class TestEmail:
    @pytest.mark.parametrize(
        "text",
        [
            "Contact me at jane.doe@example.com please.",
            "Reach out: first+tag@sub.domain.co.uk",
            "EMAIL: USER_NAME@Example.ORG",
        ],
    )
    def test_positive(self, text):
        findings = scan_text(text, denylist=[])
        assert "email" in _kinds(findings)

    @pytest.mark.parametrize(
        "text",
        [
            "Meet me @ the office at noon.",
            "The rate is 5@once is not an email here.",
            "Plain prose with no contact details whatsoever.",
        ],
    )
    def test_negative(self, text):
        findings = scan_text(text, denylist=[])
        assert "email" not in _kinds(findings)


class TestPhone:
    @pytest.mark.parametrize(
        "text",
        [
            "Call 416-555-1234 today.",
            "Phone: (416) 555-1234",
            "Reach us at 416.555.1234",
            "International: +1 416 555 1234",
            "Cell 4165551234 anytime",
        ],
    )
    def test_positive(self, text):
        findings = scan_text(text, denylist=[])
        assert "phone" in _kinds(findings)

    @pytest.mark.parametrize(
        "text",
        [
            "The fiscal period 2024-2027 was strong.",
            "Released on 2024-06-22 to the public.",
            "Only 42 people attended the gala.",
            "Refer to clause 12.3.4 of the agreement.",
        ],
    )
    def test_negative(self, text):
        findings = scan_text(text, denylist=[])
        assert "phone" not in _kinds(findings)


class TestSIN:
    @pytest.mark.parametrize(
        "text",
        [
            "SIN: 123-456-789 on file.",
            "Number 123 456 789 recorded.",
            "Raw 123456789 stored.",
        ],
    )
    def test_positive(self, text):
        findings = scan_text(text, denylist=[])
        assert "sin" in _kinds(findings)

    @pytest.mark.parametrize(
        "text",
        [
            "We served 1234 patrons last year.",
            "Grant ID AB-12-34 was approved.",
            "Just twelve thirty-four hundred words.",
        ],
    )
    def test_negative(self, text):
        findings = scan_text(text, denylist=[])
        assert "sin" not in _kinds(findings)


class TestSSN:
    @pytest.mark.parametrize(
        "text",
        [
            "SSN 123-45-6789 verified.",
            "Provide 987-65-4321 to HR.",
        ],
    )
    def test_positive(self, text):
        findings = scan_text(text, denylist=[])
        assert "ssn" in _kinds(findings)

    @pytest.mark.parametrize(
        "text",
        [
            "Phone 416-555-1234 here.",
            "Range 12-34-56 of inventory.",
            "Period 2024-25 budget.",
        ],
    )
    def test_negative(self, text):
        findings = scan_text(text, denylist=[])
        assert "ssn" not in _kinds(findings)


class TestPostalCode:
    @pytest.mark.parametrize(
        "text",
        [
            "Mail to K1A 0B1 Ottawa.",
            "Postal code M5V3L9 downtown.",
            "Located at H2X-1Y4 in Montreal.",
        ],
    )
    def test_positive(self, text):
        findings = scan_text(text, denylist=[])
        assert "postal_code" in _kinds(findings)

    @pytest.mark.parametrize(
        "text",
        [
            "Section A of the report.",
            "Item B7 in the catalogue.",
            "The grade was A1 overall.",
        ],
    )
    def test_negative(self, text):
        findings = scan_text(text, denylist=[])
        assert "postal_code" not in _kinds(findings)


class TestCurrency:
    @pytest.mark.parametrize(
        "text",
        [
            "Awarded $1,234.56 this cycle.",
            "Budget of $1234 total.",
            "Requested CAD 1,000 for travel.",
            "Spent USD 25,000.00 on staff.",
        ],
    )
    def test_positive(self, text):
        findings = scan_text(text, denylist=[])
        assert "currency" in _kinds(findings)

    @pytest.mark.parametrize(
        "text",
        [
            "We hosted 1,000 visitors.",
            "About 5 percent growth.",
            "The number 1234 is fine here.",
        ],
    )
    def test_negative(self, text):
        findings = scan_text(text, denylist=[])
        assert "currency" not in _kinds(findings)


class TestDenylistedName:
    def test_case_insensitive_match(self):
        findings = scan_text("Submitted by JANE DOE.", denylist=["Jane Doe"])
        assert "denylisted_name" in _kinds(findings)

    def test_whole_word_only_does_not_match_substring(self):
        findings = scan_text(
            "Robertson signed the form.", denylist=["Robert"]
        )
        assert "denylisted_name" not in _kinds(findings)

    def test_exact_word_matches(self):
        findings = scan_text("Robert signed the form.", denylist=["Robert"])
        assert "denylisted_name" in _kinds(findings)

    def test_multiword_name_matches(self):
        findings = scan_text(
            "Reviewed by Acme Corporation staff.", denylist=["Acme Corporation"]
        )
        assert "denylisted_name" in _kinds(findings)

    def test_clean_text_no_name_match(self):
        findings = scan_text(
            "The committee reviewed the proposal.", denylist=["Jane Doe"]
        )
        assert "denylisted_name" not in _kinds(findings)

    def test_default_denylist_used_when_none(self):
        findings = scan_text("Signed by John Doe.")
        assert "denylisted_name" in _kinds(findings)


class TestFindingMetadata:
    def test_line_is_one_based(self):
        text = "clean line one\nemail here jane@example.com\n"
        findings = scan_text(text, denylist=[])
        emails = [f for f in findings if f.kind == "email"]
        assert emails
        assert emails[0].line == 2

    def test_context_contains_match(self):
        findings = scan_text("Reach jane@example.com now.", denylist=[])
        emails = [f for f in findings if f.kind == "email"]
        assert emails
        assert "jane@example.com" in emails[0].context

    def test_match_field_is_the_matched_text(self):
        findings = scan_text("Call 416-555-1234.", denylist=[])
        phones = [f for f in findings if f.kind == "phone"]
        assert phones
        assert "416-555-1234" in phones[0].match


class TestPIIReport:
    def test_clean_true_on_clean_text(self, tmp_path):
        path = tmp_path / "clean.md"
        path.write_text("# Title\n\nA wholly synthetic paragraph of prose.\n")
        report = scan_file(path, denylist=[])
        assert report.clean is True
        assert report.findings == []

    def test_clean_false_when_findings_exist(self):
        report = PIIReport(
            path="x.md",
            findings=[Finding(kind="email", match="a@b.com", line=1, context="a@b.com")],
        )
        assert report.clean is False


class TestScanFile:
    def test_scan_md_file(self, tmp_path):
        path = tmp_path / "doc.md"
        path.write_text("# Report\n\nContact jane.doe@example.com for details.\n")
        report = scan_file(path, denylist=[])
        assert report.path == str(path)
        assert "email" in _kinds(report.findings)
        assert report.clean is False

    def test_scan_txt_file(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("Phone 416-555-1234 and SIN 123-456-789.\n")
        report = scan_file(path, denylist=[])
        assert "phone" in _kinds(report.findings)
        assert "sin" in _kinds(report.findings)

    def test_unscannable_when_extractor_missing_is_not_clean(self, tmp_path, monkeypatch):
        import folio.core.corpus.pii_scan as mod

        monkeypatch.setattr(mod.shutil, "which", lambda *_a, **_k: None)
        path = tmp_path / "scan.pdf"
        path.write_bytes(b"%PDF-1.4 fake")
        report = scan_file(path, denylist=[])
        assert report.clean is False
        assert "unscannable" in _kinds(report.findings)


class TestScanPaths:
    def test_returns_report_per_path(self, tmp_path):
        a = tmp_path / "a.md"
        a.write_text("Clean content here.\n")
        b = tmp_path / "b.md"
        b.write_text("Email leak: jane@example.com\n")
        reports = scan_paths([a, b], denylist=[])
        assert len(reports) == 2
        by_path = {r.path: r for r in reports}
        assert by_path[str(a)].clean is True
        assert by_path[str(b)].clean is False
