"""Null wiki backend (no wiki, markdown-only mode).

Used when an org only wants the markdown pipeline without wiki compilation.
"""

from __future__ import annotations

from pathlib import Path

from folio.adapters.wiki.base import WikiBackend


class NullWikiBackend(WikiBackend):
    """No-op wiki backend. All operations return empty or placeholder results."""

    def init(self, project_dir: Path, config: dict, source_dir: Path | None = None) -> None:
        pass

    def add_documents(self, source_paths: list[Path]) -> None:
        pass

    def compile(self, log_file: Path | None = None, dry_run: bool = False) -> None:
        pass

    def search(self, query: str) -> str:
        return "Wiki not configured. Run with a wiki backend to enable search."

    def query(self, question: str) -> str:
        return "Wiki not configured. Run with a wiki backend to enable search."

    def status(self) -> str:
        return "Wiki not configured. Run with a wiki backend to enable status."

    def doctor(self) -> str:
        return "Wiki not configured. Run with a wiki backend to enable doctor."

    def lint(self, pass_name: str | None = None, fix: bool = False) -> str:
        return "Wiki not configured. Run with a wiki backend to enable lint."

    def coverage(self) -> str:
        return "Wiki not configured. Run with a wiki backend to enable coverage."

    def diff(self) -> str:
        return "Wiki not configured. Run with a wiki backend to enable diff."

    def verify(self, all_files: bool = False, since: str | None = None, limit: int | None = None) -> str:
        return "Wiki not configured. Run with a wiki backend to enable verify."
