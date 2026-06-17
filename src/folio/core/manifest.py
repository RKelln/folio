"""Pipeline manifest read/write and schema.

The manifest is a JSON file tracking per-file status, tier, costs,
and metadata through the pipeline. Used for checkpoint/resume and
inter-stage communication.

This module is the CANONICAL manifest implementation.  Other stages may
extend the schema (e.g. ``"stages"`` in pipeline.py, ``"completed_groups"``
in prioritizer.py), but the base ``"files"`` and ``"summary"`` keys must
remain as defined here so ``recalculate_summary`` and other utilities
work across all consumers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


class FileEntry(TypedDict, total=False):
    """Per-file entry in the manifest ``files`` dict."""
    status: str
    tier: str
    funder: str
    doc_types: list[str]
    rewrite_cost_usd: float
    prioritize_cost_usd: float
    priority: int


class ManifestSummary(TypedDict, total=False):
    """Aggregated counts in the manifest ``summary`` dict."""
    total_files: int
    by_status: dict[str, int]
    by_tier: dict[str, int]
    by_funder: dict[str, int]
    total_cost_usd: float


class Manifest(TypedDict, total=False):
    """Canonical manifest schema.

    Extension keys (``stages``, ``completed_groups``, etc.) may be
    added by individual pipeline stages, but the base ``files`` and
    ``summary`` keys must match this schema.
    """
    project: str
    generated: str
    updated: str
    files: dict[str, FileEntry]
    summary: ManifestSummary


def create_manifest(project_name: str = "folio") -> dict:
    """Create a new empty manifest."""
    return {
        "project": project_name,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": {},
        "summary": {
            "total_files": 0,
            "by_status": {},
            "by_tier": {},
            "by_funder": {},
            "total_cost_usd": 0.0,
        }
    }


def load_manifest(path: str | Path) -> dict:
    """Load manifest from JSON file. Returns empty manifest if file missing."""
    path = Path(path)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return create_manifest()


def save_manifest(manifest: dict, path: str | Path) -> None:
    """Save manifest to JSON file, updating the 'updated' timestamp."""
    manifest["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(manifest, f, indent=2)


def update_file(manifest: dict, filename: str, **fields) -> None:
    """Update or create a file entry in the manifest."""
    if filename not in manifest["files"]:
        manifest["files"][filename] = {}
    manifest["files"][filename].update(fields)


def get_file(manifest: dict, filename: str) -> dict | None:
    """Get a file entry from the manifest, or None."""
    return manifest["files"].get(filename)


def get_files_by_status(manifest: dict, status: str) -> list[str]:
    """Get all filenames with a given status."""
    return [f for f, d in manifest["files"].items() if d.get("status") == status]


def _ensure_str(value, default: str) -> str:
    """Coerce enum members to plain strings for use as dict keys."""
    if hasattr(value, 'value'):
        return value.value
    return value if isinstance(value, str) else default


def recalculate_summary(manifest: dict) -> None:
    """Recalculate summary counts from file entries."""
    files = manifest["files"]
    manifest["summary"]["total_files"] = len(files)
    manifest["summary"]["by_status"] = {}
    manifest["summary"]["by_tier"] = {}
    manifest["summary"]["by_funder"] = {}
    manifest["summary"]["total_cost_usd"] = 0.0
    for entry in files.values():
        status = _ensure_str(entry.get("status", "pending"), "pending")
        manifest["summary"]["by_status"][status] = manifest["summary"]["by_status"].get(status, 0) + 1
        tier = _ensure_str(entry.get("tier", "?"), "?")
        manifest["summary"]["by_tier"][tier] = manifest["summary"]["by_tier"].get(tier, 0) + 1
        funder = entry.get("funder", "?")
        funder = _ensure_str(funder, "?")
        manifest["summary"]["by_funder"][funder] = manifest["summary"]["by_funder"].get(funder, 0) + 1
        cost = entry.get("rewrite_cost_usd", 0) + entry.get("prioritize_cost_usd", 0)
        manifest["summary"]["total_cost_usd"] += cost


def manifest_summary_text(manifest: dict) -> str:
    """Return a human-readable multi-line summary of the manifest."""
    s = manifest["summary"]
    lines = [
        f"Project: {manifest.get('project', 'folio')}",
        f"Generated: {manifest.get('generated', '?')}",
        f"Updated:   {manifest.get('updated', '?')}",
        "",
        f"Total files: {s['total_files']}",
        f"Total cost:  ${s['total_cost_usd']:.4f} USD",
        "",
        "By status:",
    ]
    for status, count in sorted(s.get("by_status", {}).items()):
        lines.append(f"  {status}: {count}")
    lines.append("")
    lines.append("By tier:")
    for tier, count in sorted(s.get("by_tier", {}).items()):
        lines.append(f"  {tier}: {count}")
    lines.append("")
    lines.append("By funder:")
    for funder, count in sorted(s.get("by_funder", {}).items()):
        lines.append(f"  {funder}: {count}")
    return "\n".join(lines)
