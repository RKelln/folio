"""Tests for the seeded, length-matched synthetic content helpers.

The hard requirement under test is *determinism*: re-seeding with the same
integer must reproduce byte-identical output across the full helper surface.
These tests are intentionally aggressive about that contract because the whole
synthetic-corpus pipeline (folio-4v7) relies on the authored Markdown being a
stable golden reference.
"""
from __future__ import annotations

import datetime
import re

import pytest

from folio.core.corpus.content import (
    fake_address,
    fake_date,
    fake_email,
    fake_money,
    fake_name,
    fake_org_name,
    fake_paragraphs,
    fake_phone,
    lorem_matching,
    seed_all,
)

MONEY_RE = re.compile(r"^\$\d{1,3}(,\d{3})*$")


def _run_sequence(seed: int) -> list[str]:
    """Exercise every helper in a fixed order and return the captured outputs.

    This is the canonical "trace" used to assert determinism: the same seed
    must yield the same trace, list element for list element.
    """
    fake = seed_all(seed)
    trace: list[str] = []
    for _ in range(5):
        name = fake_name(fake)
        trace.append(name)
        trace.append(fake_email(fake, name))
        trace.append(fake_email(fake))
        trace.append(fake_phone(fake))
        trace.append(fake_address(fake))
        trace.append(fake_org_name(fake))
        trace.append(fake_money(fake))
        trace.append(fake_money(fake, low=1000, high=2000))
        trace.append(fake_date(fake))
        trace.append(lorem_matching(fake, 300))
        trace.extend(fake_paragraphs(fake, 800, min_paras=2))
    return trace


class TestSeedAll:
    def test_returns_faker_instance(self):
        fake = seed_all(42)
        assert hasattr(fake, "name")
        assert callable(fake.name)

    def test_helpers_use_module_default_when_no_instance_passed(self):
        seed_all(7)
        first = fake_name()
        seed_all(7)
        second = fake_name()
        assert first == second


class TestDeterminism:
    def test_same_seed_produces_identical_trace(self):
        first = _run_sequence(42)
        second = _run_sequence(42)
        assert first == second

    @pytest.mark.parametrize("seed", [0, 1, 42, 1234, 2024])
    def test_repeatable_across_many_seeds(self, seed):
        assert _run_sequence(seed) == _run_sequence(seed)

    def test_trace_survives_round_trip_through_disk(self, tmp_path):
        first = _run_sequence(99)
        payload = "\u0001".join(first)
        artifact = tmp_path / "trace.txt"
        artifact.write_text(payload, encoding="utf-8")
        reloaded = artifact.read_text(encoding="utf-8").split("\u0001")
        second = _run_sequence(99)
        assert reloaded == second


class TestDifferentSeeds:
    def test_different_seeds_diverge(self):
        assert _run_sequence(1) != _run_sequence(2)

    def test_different_seeds_diverge_on_single_helper(self):
        a = seed_all(1)
        first = [fake_name(a) for _ in range(10)]
        b = seed_all(2)
        second = [fake_name(b) for _ in range(10)]
        assert first != second


class TestLoremMatching:
    @pytest.mark.parametrize("target", [200, 1000, 5000])
    def test_length_within_ten_percent(self, target):
        fake = seed_all(42)
        text = lorem_matching(fake, target)
        tolerance = target * 0.1
        assert abs(len(text) - target) <= tolerance, (
            f"len={len(text)} target={target} tol={tolerance}"
        )

    def test_not_fixed_lorem_ipsum_phrase(self):
        fake = seed_all(42)
        a = lorem_matching(fake, 500)
        b = lorem_matching(fake, 500)
        assert a != b

    @pytest.mark.parametrize("target", [0, -5])
    def test_non_positive_target_returns_empty(self, target):
        fake = seed_all(42)
        assert lorem_matching(fake, target) == ""

    def test_ends_on_sentence_boundary(self):
        fake = seed_all(42)
        text = lorem_matching(fake, 1000)
        assert text.rstrip().endswith(".")


class TestFakeParagraphs:
    @pytest.mark.parametrize("target", [400, 1500, 4000])
    def test_total_length_within_ten_percent(self, target):
        fake = seed_all(42)
        paras = fake_paragraphs(fake, target, min_paras=2)
        total = sum(len(p) for p in paras)
        assert abs(total - target) <= target * 0.1

    def test_respects_min_paras(self):
        fake = seed_all(42)
        paras = fake_paragraphs(fake, 2000, min_paras=3)
        assert len(paras) >= 3

    def test_returns_list_of_strings(self):
        fake = seed_all(42)
        paras = fake_paragraphs(fake, 600)
        assert isinstance(paras, list)
        assert all(isinstance(p, str) and p for p in paras)


class TestFakeMoney:
    @pytest.mark.parametrize("low, high", [(500, 50000), (1000, 1000), (10, 999)])
    def test_matches_currency_format(self, low, high):
        fake = seed_all(42)
        for _ in range(20):
            value = fake_money(fake, low=low, high=high)
            assert MONEY_RE.match(value), value

    def test_value_within_bounds(self):
        fake = seed_all(42)
        for _ in range(50):
            value = fake_money(fake, low=500, high=50000)
            amount = int(value.lstrip("$").replace(",", ""))
            assert 500 <= amount <= 50000


class TestFakeDate:
    def test_parses_as_iso_date(self):
        fake = seed_all(42)
        for _ in range(20):
            value = fake_date(fake)
            parsed = datetime.date.fromisoformat(value)
            assert isinstance(parsed, datetime.date)

    def test_within_year_bounds(self):
        fake = seed_all(42)
        for _ in range(50):
            value = fake_date(fake, start_year=2018, end_year=2024)
            parsed = datetime.date.fromisoformat(value)
            assert 2018 <= parsed.year <= 2024


class TestFakeEmail:
    def test_contains_at_sign(self):
        fake = seed_all(42)
        assert "@" in fake_email(fake)

    def test_derives_local_part_from_name(self):
        fake = seed_all(42)
        email = fake_email(fake, "John Q. Smith")
        local = email.split("@", 1)[0]
        assert "john" in local
        assert "smith" in local


class TestFakePhone:
    def test_has_at_least_ten_digits(self):
        fake = seed_all(42)
        for _ in range(20):
            phone = fake_phone(fake)
            digits = re.sub(r"\D", "", phone)
            assert len(digits) >= 10, phone


class TestFakeName:
    def test_returns_non_empty_string(self):
        fake = seed_all(42)
        assert fake_name(fake).strip()


class TestFakeAddress:
    def test_single_line(self):
        fake = seed_all(42)
        assert "\n" not in fake_address(fake)


class TestFakeOrgName:
    def test_returns_non_empty_string(self):
        fake = seed_all(42)
        assert fake_org_name(fake).strip()
