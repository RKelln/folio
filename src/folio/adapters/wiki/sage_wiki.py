"""sage-wiki backend (default).

Wraps the sage-wiki Go binary for wiki compilation and search.
Requires sage-wiki to be installed and on PATH.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import yaml

from folio.adapters.wiki.base import WikiBackend

logger = logging.getLogger(__name__)


class SageWikiBackend(WikiBackend):
    """Wiki backend that wraps the sage-wiki Go binary."""

    def __init__(self):
        if not shutil.which("sage-wiki"):
            raise RuntimeError(
                "sage-wiki not found on PATH. Install sage-wiki to use this backend, "
                "or configure wiki type to 'null' for markdown-only mode."
            )
        self._project_dir: Path | None = None

    def init(self, project_dir: Path, config: dict, source_dir: Path | None = None) -> None:
        project_dir.mkdir(parents=True, exist_ok=True)
        self._project_dir = project_dir

        config_file = project_dir / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        raw_link = project_dir / "raw"
        if source_dir and source_dir.is_dir():
            if raw_link.is_symlink() or raw_link.exists():
                raw_link.unlink()
            raw_link.symlink_to(source_dir.resolve(), target_is_directory=True)
        else:
            raw_link.mkdir(exist_ok=True)

    def add_documents(self, source_paths: list[Path]) -> None:
        # Documents are visible via the raw/ symlink to the markdown directory.
        # No copying needed.
        pass

    def compile(self) -> None:
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")
        try:
            subprocess.run(
                ["sage-wiki", "compile"],
                cwd=str(self._project_dir),
                timeout=3600,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            if e.stderr:
                logger.error("sage-wiki compile stderr:\n%s", e.stderr.strip())
            raise
        except subprocess.TimeoutExpired as e:
            if e.stderr:
                logger.error(
                    "sage-wiki compile timed out after %ds — stderr:\n%s",
                    e.timeout,
                    e.stderr.decode() if isinstance(e.stderr, bytes) else str(e.stderr),
                )
            raise

    def search(self, query: str) -> str:
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")
        try:
            result = subprocess.run(
                ["sage-wiki", "search", query],
                cwd=str(self._project_dir),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("sage-wiki search failed: %s", e)
            return ""
        return result.stdout

    def query(self, question: str) -> str:
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")
        try:
            result = subprocess.run(
                ["sage-wiki", "query", question],
                cwd=str(self._project_dir),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("sage-wiki query failed: %s", e)
            return ""
        return result.stdout

    def status(self) -> str:
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")
        try:
            result = subprocess.run(
                ["sage-wiki", "status", "--json"],
                cwd=str(self._project_dir),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("sage-wiki status failed: %s", e)
            return ""
        return result.stdout

    def doctor(self) -> str:
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")
        try:
            result = subprocess.run(
                ["sage-wiki", "doctor"],
                cwd=str(self._project_dir),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("sage-wiki doctor failed: %s", e)
            return ""
        return result.stdout

    def lint(self, pass_name: str | None = None, fix: bool = False) -> str:
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")
        cmd = ["sage-wiki", "lint"]
        if pass_name is not None:
            cmd.extend(["--pass", pass_name])
        if fix:
            cmd.append("--fix")
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._project_dir),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("sage-wiki lint failed: %s", e)
            return ""
        return result.stdout

    def coverage(self) -> str:
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")
        try:
            result = subprocess.run(
                ["sage-wiki", "coverage"],
                cwd=str(self._project_dir),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("sage-wiki coverage failed: %s", e)
            return ""
        return result.stdout

    def diff(self) -> str:
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")
        try:
            result = subprocess.run(
                ["sage-wiki", "diff", "--json"],
                cwd=str(self._project_dir),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("sage-wiki diff failed: %s", e)
            return ""
        return result.stdout

    def verify(self, all: bool = False, since: str | None = None, limit: int | None = None) -> str:
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")
        cmd = ["sage-wiki", "verify"]
        if all:
            cmd.append("--all")
        if since is not None:
            cmd.extend(["--since", since])
        if limit is not None:
            cmd.extend(["--limit", str(limit)])
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._project_dir),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("sage-wiki verify failed: %s", e)
            return ""
        return result.stdout
