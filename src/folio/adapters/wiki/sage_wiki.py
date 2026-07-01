"""sage-wiki backend (default).

Wraps the sage-wiki Go binary for wiki compilation and search.
Requires sage-wiki to be installed and on PATH.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import threading
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

    def _run_wiki_command(self, *args: str, timeout: int | None = None) -> str:
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")
        cmd_name = args[1] if len(args) > 1 else args[0]
        try:
            result = subprocess.run(
                list(args),
                cwd=str(self._project_dir),
                timeout=timeout,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            if e.stderr:
                logger.error("sage-wiki %s stderr:\n%s", cmd_name, e.stderr.strip())
            return ""
        except subprocess.TimeoutExpired as e:
            if e.stderr:
                stderr_str = e.stderr.decode() if isinstance(e.stderr, bytes) else str(e.stderr)
                logger.error(
                    "sage-wiki %s timed out after %ds — stderr:\n%s",
                    cmd_name,
                    e.timeout if e.timeout is not None else 0,
                    stderr_str,
                )
            return ""
        return result.stdout

    def add_documents(self, source_paths: list[Path]) -> None:
        pass

    def compile(self, log_file: Path | None = None, dry_run: bool = False) -> None:
        """Run sage-wiki compile, streaming stdout/stderr to terminal and optionally to a log file."""
        if self._project_dir is None:
            raise RuntimeError("Wiki not initialized. Call init() first.")

        cmd = ["sage-wiki", "compile"]
        if dry_run:
            cmd.append("--dry-run")
        proc = subprocess.Popen(
            cmd,
            cwd=str(self._project_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        log_fh = None
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_fh = open(log_file, "w")

        def _tee(pipe, log_fh):
            try:
                for line in pipe:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    if log_fh:
                        log_fh.write(line)
                        log_fh.flush()
            finally:
                if log_fh:
                    log_fh.close()

        tee_thread = threading.Thread(target=_tee, args=(proc.stdout, log_fh), daemon=True)
        tee_thread.start()

        ret = proc.wait()
        tee_thread.join()

        if ret != 0:
            raise subprocess.CalledProcessError(ret, ["sage-wiki", "compile"])

    def search(self, query: str) -> str:
        return self._run_wiki_command("sage-wiki", "search", query, timeout=60)

    def query(self, question: str) -> str:
        return self._run_wiki_command("sage-wiki", "query", question, timeout=60)

    def status(self) -> str:
        return self._run_wiki_command("sage-wiki", "status", "--json", timeout=300)

    def doctor(self) -> str:
        return self._run_wiki_command("sage-wiki", "doctor", timeout=300)

    def lint(self, pass_name: str | None = None, fix: bool = False) -> str:
        cmd = ["sage-wiki", "lint"]
        if pass_name is not None:
            cmd.extend(["--pass", pass_name])
        if fix:
            cmd.append("--fix")
        return self._run_wiki_command(*cmd, timeout=300)

    def coverage(self) -> str:
        return self._run_wiki_command("sage-wiki", "coverage", timeout=300)

    def diff(self) -> str:
        return self._run_wiki_command("sage-wiki", "diff", "--json", timeout=300)

    def verify(self, all_files: bool = False, since: str | None = None, limit: int | None = None) -> str:
        cmd = ["sage-wiki", "verify"]
        if all_files:
            cmd.append("--all")
        if since is not None:
            cmd.extend(["--since", since])
        if limit is not None:
            cmd.extend(["--limit", str(limit)])
        return self._run_wiki_command(*cmd, timeout=300)
