"""Tests for the cascade converter and the traced converter API.

These tests drive the real ``analyze_content`` quality scorer (it is NEVER
mocked) so that pass/soft-fail decisions reflect production behaviour.

Quality scoring formula under test (see ``CascadeConverter._passes_quality``):

    content_ratio = min(content_lines / min_content_lines, 1.0)   # 0..1
    cleanliness   = max(0.0, 1.0 - corruption_score)              # 0..1
    score         = content_ratio * cleanliness                   # 0..1

Justification: a normalized [0, 1] quality number that rises monotonically
with content volume (saturating once enough content lines exist) and falls
with OCR garble (corruption_score). A clean, content-rich document scores
near 1.0; a near-empty or heavily garbled document scores near 0.0. The
pass/fail gate is independent of the score and uses the configured
thresholds directly: passes iff
``content_lines >= min_content_lines and corruption_score <= max_corruption_score``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from folio.adapters.converters.base import ConversionResult, Converter
from folio.adapters.converters.cascade import CascadeConverter

SRC = Path("dummy.pdf")


def _good_markdown() -> str:
    """Markdown that passes: a heading plus >=15 real content lines, no garble."""
    lines = ["# Annual Report 2023"]
    for i in range(20):
        lines.append(
            f"In fiscal year segment {i}, the organization delivered programming "
            f"to artists and audiences across the region."
        )
    return "\n".join(lines)


def _sparse_markdown() -> str:
    """Markdown that soft-fails: too few content lines (below min_content_lines)."""
    return "# Title\nA single short paragraph of content."


def _garbled_markdown() -> str:
    """Markdown that soft-fails: high corruption_score (mostly single-char lines)."""
    return "\n".join(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j",
                      "k", "l", "m", "n", "o", "p", "q", "r", "s", "t"])


def _n_content_lines(n: int) -> str:
    """Markdown with exactly *n* real content lines and zero corruption.

    Each line is a multi-word sentence (non-blank, not single-char, not an
    image marker), so ``analyze_content`` counts exactly *n* content lines
    and a corruption_score of 0.0 (well under the default max of 0.5).
    """
    return "\n".join(
        f"Content line {i} describing organizational programming and activities."
        for i in range(n)
    )


def _fake_tier(name: str, result: ConversionResult | None) -> MagicMock:
    """Build a fake Converter tier whose ``convert_traced`` returns *result*.

    If *result* is None the tier hard-fails (markdown None).
    """
    tier = MagicMock()
    tier.name = name
    tier.supported_extensions = {".pdf"}
    tier.convert_traced.return_value = (
        result if result is not None else ConversionResult(markdown=None, tier=None)
    )
    return tier


def test_first_tier_good_no_escalation():
    tier0 = _fake_tier("tier0", ConversionResult(markdown=_good_markdown(), tier="tier0"))
    tier1 = _fake_tier("tier1", ConversionResult(markdown=_good_markdown(), tier="tier1"))

    cascade = CascadeConverter([tier0, tier1])
    out = cascade.convert_traced(SRC)

    assert out.markdown == _good_markdown()
    assert out.tier == "tier0"
    assert out.score is not None and out.score > 0.5
    tier0.convert_traced.assert_called_once_with(SRC)
    tier1.convert_traced.assert_not_called()
    tier1.convert.assert_not_called()


def test_hard_fail_escalates_to_next_tier():
    tier0 = _fake_tier("tier0", None)  # hard fail -> markdown None
    tier1 = _fake_tier("tier1", ConversionResult(markdown=_good_markdown(), tier="tier1"))

    cascade = CascadeConverter([tier0, tier1])
    out = cascade.convert_traced(SRC)

    assert out.markdown == _good_markdown()
    assert out.tier == "tier1"
    tier0.convert_traced.assert_called_once_with(SRC)
    tier1.convert_traced.assert_called_once_with(SRC)


def test_soft_fail_garbled_escalates():
    tier0 = _fake_tier("tier0", ConversionResult(markdown=_garbled_markdown(), tier="tier0"))
    tier1 = _fake_tier("tier1", ConversionResult(markdown=_good_markdown(), tier="tier1"))

    cascade = CascadeConverter([tier0, tier1])
    out = cascade.convert_traced(SRC)

    assert out.tier == "tier1"
    assert out.markdown == _good_markdown()
    tier1.convert_traced.assert_called_once_with(SRC)


def test_soft_fail_sparse_escalates():
    tier0 = _fake_tier("tier0", ConversionResult(markdown=_sparse_markdown(), tier="tier0"))
    tier1 = _fake_tier("tier1", ConversionResult(markdown=_good_markdown(), tier="tier1"))

    cascade = CascadeConverter([tier0, tier1])
    out = cascade.convert_traced(SRC)

    assert out.tier == "tier1"
    assert out.markdown == _good_markdown()


def test_best_effort_returns_last_produced_when_none_pass():
    tier0 = _fake_tier("tier0", None)  # hard fail
    tier1 = _fake_tier("tier1", ConversionResult(markdown=_sparse_markdown(), tier="tier1"))
    tier2 = _fake_tier("tier2", ConversionResult(markdown=_garbled_markdown(), tier="tier2"))

    cascade = CascadeConverter([tier0, tier1, tier2])
    out = cascade.convert_traced(SRC)

    assert out.markdown == _garbled_markdown()
    assert out.tier == "tier2"
    assert out.score is not None


def test_all_tiers_hard_fail_returns_none():
    tier0 = _fake_tier("tier0", None)
    tier1 = _fake_tier("tier1", None)

    cascade = CascadeConverter([tier0, tier1])
    out = cascade.convert_traced(SRC)

    assert out.markdown is None
    assert out.tier is None


def test_convert_delegates_to_convert_traced():
    tier0 = _fake_tier("tier0", ConversionResult(markdown=_good_markdown(), tier="tier0"))
    cascade = CascadeConverter([tier0])
    assert cascade.convert(SRC) == _good_markdown()


def test_cost_accumulates_across_invoked_tiers():
    tier0 = _fake_tier(
        "tier0", ConversionResult(markdown=_sparse_markdown(), tier="tier0", cost_usd=0.01)
    )
    tier1 = _fake_tier(
        "tier1", ConversionResult(markdown=_good_markdown(), tier="tier1", cost_usd=0.50)
    )

    cascade = CascadeConverter([tier0, tier1])
    out = cascade.convert_traced(SRC)

    assert out.tier == "tier1"
    assert out.cost_usd == pytest.approx(0.51)


def test_supported_extensions_is_union():
    tier0 = MagicMock()
    tier0.name = "tier0"
    tier0.supported_extensions = {".pdf"}
    tier1 = MagicMock()
    tier1.name = "tier1"
    tier1.supported_extensions = {".docx", ".pdf"}

    cascade = CascadeConverter([tier0, tier1])
    assert cascade.supported_extensions == {".pdf", ".docx"}


def test_name_is_cascade():
    tier0 = _fake_tier("tier0", ConversionResult(markdown=_good_markdown(), tier="tier0"))
    assert CascadeConverter([tier0]).name == "cascade"


def test_empty_tiers_raises_value_error():
    with pytest.raises(ValueError):
        CascadeConverter([])


def test_passes_quality_thresholds_are_config_driven():
    tier0 = _fake_tier("tier0", ConversionResult(markdown=_sparse_markdown(), tier="tier0"))
    # Lower min_content_lines so the sparse doc now passes -> proves config drives it.
    cascade = CascadeConverter([tier0], thresholds={"min_content_lines": 1})
    out = cascade.convert_traced(SRC)
    assert out.tier == "tier0"
    assert out.markdown == _sparse_markdown()


def test_min_content_lines_boundary_just_below_soft_fails():
    just_below = _n_content_lines(14)  # one short of the default threshold (15)
    tier0 = _fake_tier("tier0", ConversionResult(markdown=just_below, tier="tier0"))
    tier1 = _fake_tier("tier1", ConversionResult(markdown=_good_markdown(), tier="tier1"))

    cascade = CascadeConverter([tier0, tier1])
    out = cascade.convert_traced(SRC)

    assert out.tier == "tier1"
    assert out.markdown == _good_markdown()
    tier1.convert_traced.assert_called_once_with(SRC)


def test_min_content_lines_boundary_exact_passes():
    exact = _n_content_lines(15)  # exactly the default threshold (15)
    tier0 = _fake_tier("tier0", ConversionResult(markdown=exact, tier="tier0"))
    tier1 = _fake_tier("tier1", ConversionResult(markdown=_good_markdown(), tier="tier1"))

    cascade = CascadeConverter([tier0, tier1])
    out = cascade.convert_traced(SRC)

    assert out.tier == "tier0"
    assert out.markdown == exact
    tier1.convert_traced.assert_not_called()


# ── base Converter.convert_traced default behaviour ──────────────────────────


class _StubConverter(Converter):
    def __init__(self, markdown: str | None, cost: float = 0.0):
        self._markdown = markdown
        self._cost = cost

    @property
    def name(self) -> str:
        return "stub"

    @property
    def supported_extensions(self) -> set[str]:
        return {".pdf"}

    def convert(self, source: Path) -> str | None:
        return self._markdown

    def estimate_cost(self, source: Path) -> float:
        return self._cost


def test_base_convert_traced_wraps_success():
    conv = _StubConverter("# Doc\nbody text", cost=0.25)
    out = conv.convert_traced(SRC)
    assert out.markdown == "# Doc\nbody text"
    assert out.tier == "stub"
    assert out.score is None
    assert out.cost_usd == pytest.approx(0.25)


def test_base_convert_traced_wraps_failure():
    conv = _StubConverter(None, cost=0.25)
    out = conv.convert_traced(SRC)
    assert out.markdown is None
    assert out.tier is None
    assert out.cost_usd == 0.0


def test_base_estimate_cost_defaults_zero():
    class _Bare(Converter):
        @property
        def name(self) -> str:
            return "bare"

        @property
        def supported_extensions(self) -> set[str]:
            return set()

        def convert(self, source: Path) -> str | None:
            return "x"

    assert _Bare().estimate_cost(SRC) == 0.0
