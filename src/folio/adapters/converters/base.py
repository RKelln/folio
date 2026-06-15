"""Abstract converter interface.

All document converters must implement this protocol.
"""

from abc import ABC, abstractmethod
from pathlib import Path


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

        Args:
            source: Path to the source file.

        Returns:
            Markdown string on success, None on failure.
        """
        ...
