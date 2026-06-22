"""Abstract converter interface.

All document converters must implement this protocol.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConversionResult:
    """Outcome of a single conversion, carrying optional quality/cost trace.

    Attributes:
        markdown: Converted markdown, or None on hard failure.
        tier: Name of the converter that produced ``markdown`` (None on failure).
        score: Optional normalized [0, 1] quality score (None when not scored).
        cost_usd: Estimated cost in USD attributable to producing this result.
    """

    markdown: str | None
    tier: str | None = None
    score: float | None = None
    cost_usd: float = 0.0


class Converter(ABC):
    """Convert a document (PDF, DOCX, XLSX, etc.) to markdown."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable converter name."""
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """File extensions this converter handles (e.g. {'.pdf', '.docx'})."""
        ...

    @abstractmethod
    def convert(self, source: Path) -> str | None:
        """Convert a file to markdown.

        Implementations must NOT raise exceptions on failure;
        log the error and return None instead.

        Args:
            source: Path to the source file.

        Returns:
            Markdown string on success, None on failure.
        """
        ...

    def estimate_cost(self, source: Path) -> float:
        """Estimate the USD cost of converting *source*.

        Defaults to zero (local/free converters). Paid converters (e.g.
        Datalab) may override this to report per-file cost.
        """
        return 0.0

    def convert_traced(self, source: Path) -> ConversionResult:
        """Convert *source* and wrap the outcome in a :class:`ConversionResult`.

        Provides every converter a traced API for free. The result carries
        this converter's name (on success) and its estimated cost; quality
        scoring is left to higher-level orchestrators (e.g. the cascade).
        """
        markdown = self.convert(source)
        if markdown is None:
            return ConversionResult(markdown=None, tier=None, score=None, cost_usd=0.0)
        return ConversionResult(
            markdown=markdown,
            tier=self.name,
            score=None,
            cost_usd=self.estimate_cost(source),
        )
