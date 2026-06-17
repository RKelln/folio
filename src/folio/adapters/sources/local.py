"""Local filesystem document source (default)."""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path

from folio.adapters.sources.base import DocumentSource, FileRef


class LocalSource(DocumentSource):
    """Read documents from a local filesystem directory."""

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".doc", ".xls", ".md"}

    def __init__(self, source_path: str | Path):
        self._source_path = Path(source_path).resolve()

    def list_files(self) -> list[FileRef]:
        if not self._source_path.is_dir():
            return []

        refs = []
        for file_path in self._source_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue

            try:
                stat = file_path.stat()
            except (OSError, PermissionError):
                continue

            mtime = datetime.datetime.fromtimestamp(
                stat.st_mtime, tz=datetime.timezone.utc
            ).isoformat()

            refs.append(
                FileRef(
                    name=file_path.name,
                    path=str(file_path.relative_to(self._source_path)),
                    size_bytes=stat.st_size,
                    modified=mtime,
                )
            )
        return refs

    def download(self, ref: FileRef, dest: Path) -> Path:
        source_file = self._source_path / ref.path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, dest)
        return dest
