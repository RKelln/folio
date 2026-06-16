"""Abstract wiki backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class WikiBackend(ABC):
    """Interface for wiki compilation and querying."""

    @abstractmethod
    def init(self, project_dir: Path, config: dict) -> None:
        """Initialize a new wiki project."""
        ...

    @abstractmethod
    def add_documents(self, source_paths: list[Path]) -> None:
        """Add documents to the wiki's raw directory."""
        ...

    @abstractmethod
    def compile(self) -> None:
        """Compile the wiki (generate summaries, concepts, articles)."""
        ...

    @abstractmethod
    def search(self, query: str) -> str:
        """Search the compiled wiki."""
        ...

    @abstractmethod
    def query(self, question: str) -> str:
        """Ask a question and get a synthesized answer."""
        ...
