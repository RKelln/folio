"""Cascade converter: try converters in order, escalating on quality failure.

The cascade runs a list of converters (cheapest/fastest first). After each
tier produces markdown it is scored against configured quality thresholds
using the shared :func:`folio.core.classifier.analyze_content` scorer (no
duplicate scoring logic — strict DRY). The first tier whose output passes
wins. If no tier passes but at least one produced markdown, the last
produced markdown is returned best-effort (expensive output is not
discarded). Only when every tier hard-fails is None returned.

All thresholds are config-driven, defaulting to
:data:`folio.core.classifier.DEFAULT_CLASSIFY_CONFIG`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from folio.adapters.converters.base import ConversionResult, Converter
from folio.core.classifier import (
    DEFAULT_CLASSIFY_CONFIG,
    analyze_content,
    compile_patterns,
)

logger = logging.getLogger(__name__)


class CascadeConverter(Converter):
    """Run converter tiers in order, escalating when output fails quality.

    Args:
        tiers: Ordered converters to try (must contain at least one).
        thresholds: Optional override of soft-failure thresholds. Keys:
            ``min_content_lines`` and ``max_corruption_score``. Unset keys
            fall back to ``DEFAULT_CLASSIFY_CONFIG['thresholds']``.

    Raises:
        ValueError: If *tiers* is empty.
    """

    def __init__(self, tiers: list[Converter], thresholds: dict | None = None):
        if not tiers:
            raise ValueError("CascadeConverter requires at least one tier")
        self._tiers = tiers
        default_thresholds = DEFAULT_CLASSIFY_CONFIG["thresholds"]
        self._thresholds = {
            "min_content_lines": default_thresholds["min_content_lines"],
            "max_corruption_score": default_thresholds["max_corruption_score"],
        }
        if thresholds:
            self._thresholds.update(thresholds)
        self._compiled = compile_patterns(DEFAULT_CLASSIFY_CONFIG)
        self._corruption = DEFAULT_CLASSIFY_CONFIG.get("corruption")

    @property
    def name(self) -> str:
        return "cascade"

    @property
    def supported_extensions(self) -> set[str]:
        exts: set[str] = set()
        for tier in self._tiers:
            exts |= set(tier.supported_extensions)
        return exts

    def _passes_quality(self, markdown: str) -> tuple[bool, float]:
        analysis = analyze_content(markdown, self._compiled, self._corruption)
        content_lines = analysis["content_lines"]
        corruption_score = analysis["corruption_score"]
        min_content = self._thresholds["min_content_lines"]
        max_corruption = self._thresholds["max_corruption_score"]

        passes = content_lines >= min_content and corruption_score <= max_corruption

        if min_content > 0:
            content_ratio = min(content_lines / min_content, 1.0)
        else:
            content_ratio = 1.0 if content_lines else 0.0
        cleanliness = max(0.0, 1.0 - corruption_score)
        score = content_ratio * cleanliness
        return passes, score

    def convert_traced(self, source: Path) -> ConversionResult:
        total_cost = 0.0
        fallback: ConversionResult | None = None

        for tier in self._tiers:
            result = tier.convert_traced(source)
            total_cost += result.cost_usd
            markdown = result.markdown

            if markdown is None:
                logger.warning(
                    "Cascade tier '%s' hard-failed for %s; escalating",
                    tier.name,
                    source,
                )
                continue

            passes, score = self._passes_quality(markdown)
            if passes:
                return ConversionResult(
                    markdown=markdown,
                    tier=tier.name,
                    score=score,
                    cost_usd=total_cost,
                )

            logger.warning(
                "Cascade tier '%s' soft-failed quality for %s (score=%.3f); escalating",
                tier.name,
                source,
                score,
            )
            fallback = ConversionResult(
                markdown=markdown,
                tier=tier.name,
                score=score,
                cost_usd=total_cost,
            )

        if fallback is not None:
            logger.warning(
                "Cascade exhausted all tiers for %s; returning best-effort '%s' output",
                source,
                fallback.tier,
            )
            return ConversionResult(
                markdown=fallback.markdown,
                tier=fallback.tier,
                score=fallback.score,
                cost_usd=total_cost,
            )

        logger.error("Cascade: every tier hard-failed for %s", source)
        return ConversionResult(markdown=None, tier=None, score=None, cost_usd=total_cost)

    def convert(self, source: Path) -> str | None:
        """Return only the winning markdown (or None if every tier hard-fails).

        Provided for backward compatibility with the plain ``Converter.convert``
        contract. Callers that need the winning tier name, quality score, or
        accumulated cost should prefer :meth:`convert_traced`, which returns a
        full :class:`ConversionResult`; this method simply discards that trace
        metadata.
        """
        return self.convert_traced(source).markdown
