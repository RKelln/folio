"""File repacker — nested-to-flat migration helper.

Walks a nested source directory tree, detects funder/year/doc-type from
path segments and filenames, and copies (or moves) files to a flat
destination following the folio naming convention:

    FUNDER__Year_Description__Type.ext
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_FILENAME_SEP = "__"

YEAR_PATTERN = re.compile(r"(?<![0-9])(20\d{2})(?![0-9])")

TYPE_KEYWORDS: dict[str, list[str]] = {
    "application": [
        "application", "submission", "submitted", "grant application",
        "project grant", "operating grant",
    ],
    "report": [
        "report", "annual report", "final report", "mid-cycle report",
        "mid cycle report", "annual update", "progress report",
    ],
    "budget": [
        "budget", "financial", "cadac", "p+l", "cash flow",
        "financial statement", "p&l",
    ],
    "notification": [
        "notification", "approval", "result", "notice", "award letter",
    ],
    "activity_list": [
        "activity list", "activity report", "activities", "program of activities",
    ],
    "staff_board": [
        "staff", "board", "bios", "board of directors", "board list",
        "staff list",
    ],
    "support_material": [
        "support material", "promotional", "promo", "press", "supplementary",
        "letter of support",
    ],
}


def _detect_funder_from_segments(segments: list[str], funders: dict[str, str]) -> str | None:
    """Detect funder abbreviation from path segments (longest match first)."""
    for abbrev in sorted(funders.keys(), key=len, reverse=True):
        abbrev_lower = abbrev.lower()
        for segment in segments:
            if abbrev_lower in segment.lower():
                return abbrev
    return None


def _detect_year_from_segments(segments: list[str]) -> int | None:
    """Extract first 4-digit year from any path segment."""
    for segment in segments:
        match = YEAR_PATTERN.search(segment)
        if match:
            return int(match.group(1))
    return None


def _detect_type_from_segments(segments: list[str]) -> str | None:
    """Detect document type from path segments and filename keywords."""
    combined = " ".join(segments).lower().replace("_", " ")
    for doc_type, keywords in TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in combined:
                return doc_type
    return None


def _detect_description_from_segments(
    segments: list[str], funder: str | None, year_str: str, doc_type: str | None
) -> str:
    """Extract a human-readable description from filename segments.

    Strips funder abbreviation, year, doc type keywords, and file extension
    from the original filename, then capitalizes the remaining words.
    """
    filename_no_ext = segments[-1] if segments else ""
    dot_idx = filename_no_ext.rfind(".")
    if dot_idx != -1:
        filename_no_ext = filename_no_ext[:dot_idx]

    cleaned = filename_no_ext
    cleaned = cleaned.replace("_", " ").replace("-", " ")

    if funder:
        cleaned = re.sub(
            re.escape(funder) + r"\b", "", cleaned, flags=re.IGNORECASE
        )
    if year_str:
        cleaned = cleaned.replace(year_str, "")

    if doc_type:
        cleaned = re.sub(
            r"\b" + re.escape(doc_type.replace("_", " ")) + r"\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    words = cleaned.split()
    return " ".join(word.capitalize() for word in words)


def _build_filename(
    funder: str,
    year: int | str,
    description: str,
    doc_type: str,
    ext: str,
) -> str:
    """Build a folio-convention filename.

    Format: FUNDER__Year_Description__Type.ext
    """
    year_str = str(year)
    description_part = description.replace(" ", "_") if description else ""

    if description_part:
        segment2 = f"{year_str}_{description_part}"
    else:
        segment2 = year_str

    return f"{funder}__{segment2}__{doc_type}{ext}"


def _confidence_score(
    funder: str | None, year: int | None, doc_type: str | None
) -> float:
    """Compute a heuristic confidence score (0.0 to 1.0)."""
    score = 0.0
    if funder:
        score += 0.35
    if year:
        score += 0.35
    if doc_type:
        score += 0.30
    return score


def scan_nested(
    source_dir: Path,
    funders: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Walk a directory tree and detect funder/year/doc-type for each file.

    Args:
        source_dir: Root directory to walk.
        funders: Dict of funder abbreviation -> full name. Used for detection.

    Returns:
        List of dicts with keys:
            old_path, suggested_filename, funder, year, doc_type,
            description, confidence, needs_review
    """
    if funders is None:
        funders = {}

    results: list[dict[str, Any]] = []
    source_dir = source_dir.resolve()

    for file_path in sorted(source_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.name.startswith("."):
            continue

        ext = file_path.suffix.lower()
        if not ext:
            continue

        rel_path = file_path.relative_to(source_dir)
        path_segments = list(rel_path.parts)

        funder = _detect_funder_from_segments(path_segments, funders)
        year = _detect_year_from_segments(path_segments)
        doc_type = _detect_type_from_segments(path_segments)

        year_str = str(year) if year else "0000"
        description = _detect_description_from_segments(
            path_segments, funder, year_str, doc_type
        )

        funder_abbrev = funder if funder else "UNKNOWN"
        doc_type_val = doc_type if doc_type else "unknown"

        suggested_filename = _build_filename(
            funder_abbrev, year if year else "0000", description, doc_type_val, ext
        )

        confidence = _confidence_score(funder, year, doc_type)
        needs_review = confidence < 0.65

        results.append({
            "old_path": str(file_path),
            "suggested_filename": suggested_filename,
            "funder": funder,
            "year": year,
            "doc_type": doc_type,
            "description": description,
            "confidence": round(confidence, 2),
            "needs_review": needs_review,
        })

    return results


def _resolve_collision(dest_dir: Path, filename: str) -> Path:
    """Resolve filename collisions by appending a counter."""
    stem = Path(filename).stem
    ext = Path(filename).suffix
    candidate = dest_dir / filename
    counter = 1
    while candidate.exists():
        candidate = dest_dir / f"{stem}_{counter}{ext}"
        counter += 1
    return candidate


def repack_files(
    source_dir: Path,
    dest_dir: Path,
    dry_run: bool = False,
    move: bool = False,
    funders: dict[str, str] | None = None,
    funder_override: str | None = None,
    year_override: int | None = None,
    type_override: str | None = None,
) -> dict[str, Any]:
    """Copy or move files from nested source to flat destination.

    Args:
        source_dir: Root directory to walk.
        dest_dir: Flat destination directory.
        dry_run: If True, preview without writing files.
        move: If True, move files instead of copying.
        funders: Dict of funder abbreviation -> full name.
        funder_override: Override detected funder.
        year_override: Override detected year.
        type_override: Override detected doc type.

    Returns:
        Dict with keys:
            total, success, skipped, mapping (old_path -> new_path),
            items (list of per-file results).
    """
    source_dir = source_dir.resolve()
    dest_dir = dest_dir.resolve()

    items = scan_nested(source_dir, funders)

    for item in items:
        if funder_override:
            item["funder"] = funder_override
            item["needs_review"] = False
        if year_override:
            item["year"] = year_override
        if type_override:
            item["doc_type"] = type_override

        funder_abbrev = item["funder"] if item["funder"] else "UNKNOWN"
        year_val = item["year"] if item["year"] else "0000"
        doc_type_val = item["doc_type"] if item["doc_type"] else "unknown"
        description = item["description"]

        ext = Path(item["old_path"]).suffix.lower()
        suggested = _build_filename(
            funder_abbrev, year_val, description, doc_type_val, ext
        )
        item["suggested_filename"] = suggested

        confidence = _confidence_score(
            item["funder"], item["year"], item["doc_type"]
        )
        item["confidence"] = round(confidence, 2)
        item["needs_review"] = item.get("needs_review", confidence < 0.65)

    mapping: dict[str, str] = {}
    success = 0
    skipped = 0

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        src = Path(item["old_path"])
        filename = item["suggested_filename"]
        dest = _resolve_collision(dest_dir, filename)

        mapping[item["old_path"]] = str(dest)
        item["new_path"] = str(dest)

        if not dry_run:
            try:
                if move:
                    shutil.move(str(src), str(dest))
                else:
                    shutil.copy2(str(src), str(dest))
                success += 1
            except OSError as e:
                logger.warning("Failed to repack %s -> %s: %s", src, dest, e)
                item["error"] = str(e)
                skipped += 1
        else:
            success += 1

    manifest_path = dest_dir / ".folio_repack_manifest.json"
    if not dry_run:
        manifest_data = {
            "source_dir": str(source_dir),
            "dest_dir": str(dest_dir),
            "mapping": mapping,
        }
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, default=str), encoding="utf-8"
        )

    return {
        "total": len(items),
        "success": success,
        "skipped": skipped,
        "mapping": mapping,
        "items": items,
    }
