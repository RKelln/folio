"""Abstract document source interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileRef:
    """Reference to a file in a document source."""

    name: str
    path: str       # source-specific path/identifier
    size_bytes: int
    modified: str | None = None  # ISO 8601


class DocumentSource(ABC):
    """Abstract source of documents (local filesystem, cloud storage, etc.)."""

    @abstractmethod
    def list_files(self) -> list[FileRef]:
        """List all available files with metadata."""
        ...

    @abstractmethod
    def download(self, ref: FileRef, dest: Path) -> Path:
        """Download a file to local storage. Returns path to downloaded file."""
        ...
