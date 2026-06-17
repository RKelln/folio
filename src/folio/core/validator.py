"""Deterministic file validation checks — no LLM calls.

Provides functions to validate frontmatter, content quality, file size,
headings compliance, and placeholder detection across markdown files.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from folio.core.classifier import _analyze_content, _compile_patterns
from folio.core.frontmatter import parse_frontmatter
from folio.core.manifest import load_manifest

logger = logging.getLogger(__name__)

_PLACEHOLDER_PATTERNS = [
    r"\[TODO\]",
    r"\[FIXME\]",
    r"\[UNKNOWN\]",
    r"\[TBD\]",
    r"\?\?\?",
    r"\{placeholder\}",
]

_MIN_FILE_BYTES = 500
_MAX_FILE_BYTES = 1_000_000
_MIN_AVG_LINE_LENGTH = 30
_MAX_CORRUPTION_SCORE = 0.3
_MAX_FORM_CHROME = 20


def validate_frontmatter(text: str, config) -> list[dict]:
    """Check frontmatter for required fields and valid values.

    Returns:
        List of issue dicts with keys: file, issue_type, missing, invalid fields.
    """
    issues: list[dict] = []

    fm, _body = parse_frontmatter(text)
    if fm is None:
        issues.append({
            "issue_type": "missing_frontmatter",
            "message": "No valid YAML frontmatter found",
        })
        return issues

    for field in ("funder", "type", "written"):
        if field not in fm or fm[field] is None:
            issues.append({
                "issue_type": "missing_field",
                "missing": field,
                "message": f"Required field '{field}' not found in frontmatter",
            })

    funder_val = fm.get("funder")
    if funder_val and isinstance(funder_val, str) and hasattr(config, "funders") and config.funders and funder_val not in config.funders:
        valid = sorted(config.funders.keys())
        issues.append({
            "issue_type": "invalid_funder",
            "value": funder_val,
            "valid_funders": valid,
            "message": (
                f"Funder '{funder_val}' not in configured funders: "
                f"{', '.join(valid)}"
            ),
        })

    type_val = fm.get("type")
    if type_val and isinstance(type_val, str) and hasattr(config, "doc_types") and config.doc_types:
        type_list = [t.strip() for t in type_val.split(",")]
        invalid = [t for t in type_list if t not in config.doc_types]
        if invalid:
            valid = sorted(config.doc_types)
            issues.append({
                "issue_type": "invalid_doc_type",
                "value": type_val,
                "invalid": invalid,
                "valid_types": valid,
                "message": (
                    f"Document type(s) {invalid} not in configured types: "
                    f"{', '.join(valid)}"
                ),
            })

    if fm.get("priority") is not None:
        try:
            p = int(fm["priority"])
            if p < 1 or p > 3:
                issues.append({
                    "issue_type": "invalid_priority",
                    "value": fm["priority"],
                    "message": f"Priority must be 1-3, got {fm['priority']}",
                })
        except (TypeError, ValueError):
            issues.append({
                "issue_type": "invalid_priority",
                "value": fm["priority"],
                "message": f"Priority must be an integer, got {fm['priority']!r}",
            })

    if fm.get("errors") is not None:
        try:
            e = int(fm["errors"])
            if e < 0:
                issues.append({
                    "issue_type": "negative_errors",
                    "value": e,
                    "message": f"Errors count must be non-negative, got {e}",
                })
        except (TypeError, ValueError):
            pass

    return issues


def validate_content(text: str, classification_config: dict) -> list[dict]:
    """Check content quality using _analyze_content() from classifier.

    Flags corruption_score > 0.3, form_chrome_count > 20,
    draft_marker_count > 0, avg_content_line_length < 30.

    Returns:
        List of issue dicts.
    """
    issues: list[dict] = []

    if not text.strip():
        issues.append({
            "issue_type": "empty_body",
            "message": "File body is empty",
        })
        return issues

    fm, body = parse_frontmatter(text)
    analysis_text = body if body else text

    compiled = _compile_patterns(classification_config)
    corruption_cfg = classification_config.get("corruption", {}) if classification_config else {}

    try:
        metrics = _analyze_content(analysis_text, compiled, corruption_cfg)
    except Exception:
        logger.warning("_analyze_content() failed", exc_info=True)
        return issues

    corruption_score = metrics.get("corruption_score", 0)
    if corruption_score > _MAX_CORRUPTION_SCORE:
        issues.append({
            "issue_type": "corruption",
            "corruption_score": round(corruption_score, 3),
            "message": (
                f"Corruption score {corruption_score:.3f} exceeds "
                f"threshold {_MAX_CORRUPTION_SCORE}"
            ),
        })

    form_chrome = metrics.get("form_chrome_count", 0)
    if form_chrome > _MAX_FORM_CHROME:
        issues.append({
            "issue_type": "form_chrome",
            "form_chrome_count": form_chrome,
            "message": f"Form chrome count {form_chrome} exceeds threshold {_MAX_FORM_CHROME}",
        })

    draft_markers = metrics.get("draft_marker_count", 0)
    if draft_markers > 0:
        issues.append({
            "issue_type": "draft_marker",
            "draft_marker_count": draft_markers,
            "message": f"{draft_markers} draft markers found in content",
        })

    avg_line_len = metrics.get("avg_content_line_length", 0)
    if avg_line_len < _MIN_AVG_LINE_LENGTH and metrics.get("content_lines", 0) > 0:
        issues.append({
            "issue_type": "short_lines",
            "avg_content_line_length": round(avg_line_len, 1),
            "message": (
                f"Average content line length {avg_line_len:.1f} "
                f"below minimum {_MIN_AVG_LINE_LENGTH}"
            ),
        })

    return issues


def validate_file_size(path: Path) -> list[dict]:
    """Check file size for anomalies.

    Flags files < 500 bytes (too_small), > 1MB (too_large), or 0 content lines.

    Returns:
        List of issue dicts.
    """
    issues: list[dict] = []

    try:
        size = path.stat().st_size
    except OSError as e:
        logger.warning("Cannot stat %s: %s", path, e)
        return issues

    if size < _MIN_FILE_BYTES:
        issues.append({
            "issue_type": "size_anomaly",
            "bytes": size,
            "issue": "too_small",
            "message": f"File size {size} bytes below minimum {_MIN_FILE_BYTES}",
        })

    if size > _MAX_FILE_BYTES:
        issues.append({
            "issue_type": "size_anomaly",
            "bytes": size,
            "issue": "too_large",
            "message": f"File size {size} bytes exceeds maximum {_MAX_FILE_BYTES}",
        })

    return issues


def validate_placeholders(text: str) -> list[dict]:
    """Flag [TODO], [FIXME], [UNKNOWN], [TBD], ???, and {placeholder} patterns.

    Returns:
        List of issue dicts.
    """
    import re

    issues: list[dict] = []
    markers_found: list[str] = []

    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern == r"\?\?\?":
            lines_with = [i + 1 for i, line in enumerate(text.split("\n")) if "???" in line]
            if lines_with:
                markers_found.append(f"??? ({len(lines_with)} lines)")
        else:
            if re.search(pattern, text):
                markers_found.append(pattern.strip(r"\\[\]"))

    if markers_found:
        issues.append({
            "issue_type": "placeholder",
            "markers": markers_found,
            "message": f"Placeholders detected: {', '.join(markers_found)}",
        })

    return issues


def validate_headings(text: str, headings_config: dict, funder: str) -> list[dict]:
    """Compare ## headings against expected canonical sections.

    Args:
        text: Markdown file content.
        headings_config: Dict mapping funder names to lists of expected sections.
        funder: The funder key for this file.

    Returns:
        List of issue dicts.
    """
    import re

    issues: list[dict] = []

    if not headings_config or not funder:
        return issues

    expected_sections = headings_config.get(funder)
    if not expected_sections:
        return issues

    found_headings = re.findall(r"^##\s+(.+)", text, re.MULTILINE)
    found_set = {h.strip().lower() for h in found_headings}

    missing = []
    for section in expected_sections:
        if section.strip().lower() not in found_set:
            missing.append(section)

    if missing:
        issues.append({
            "issue_type": "missing_sections",
            "funder": funder,
            "missing": missing,
            "expected": list(expected_sections),
            "found": list(found_set) if found_set else [],
            "message": f"Missing sections for {funder}: {', '.join(missing)}",
        })

    for heading in re.finditer(r"^##\s+(.+)", text, re.MULTILINE):
        section_name = heading.group(1).strip()
        start = heading.end()
        next_heading = re.search(r"^#", text[start:], re.MULTILINE)
        if next_heading:
            section_body = text[start:start + next_heading.start()].strip()
        else:
            section_body = text[start:].strip()
        if len(section_body.replace(" ", "")) < 50:
            issues.append({
                "issue_type": "thin_section",
                "section": section_name,
                "chars": len(section_body.replace(" ", "")),
                "message": f"Section '{section_name}' has fewer than 50 chars of content",
            })

    return issues


def validate_file(path: Path, config) -> dict:
    """Run all validation checks on a single file.

    Returns:
        Dict with keys: file, issues (list of issue dicts).
    """
    file_issues: list[dict] = []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {
            "file": str(path),
            "issues": [{
                "issue_type": "read_error",
                "message": str(e),
            }],
        }

    fm, _body = parse_frontmatter(text)

    frontmatter_issues = validate_frontmatter(text, config)
    for issue in frontmatter_issues:
        issue["file"] = str(path)
    file_issues.extend(frontmatter_issues)

    classification_config = getattr(config, "classification", {}) or {}
    content_issues = validate_content(text, classification_config)
    for issue in content_issues:
        issue["file"] = str(path)
    file_issues.extend(content_issues)

    size_issues = validate_file_size(path)
    for issue in size_issues:
        issue["file"] = str(path)
    file_issues.extend(size_issues)

    placeholder_issues = validate_placeholders(text)
    for issue in placeholder_issues:
        issue["file"] = str(path)
    file_issues.extend(placeholder_issues)

    headings_config = getattr(config, "headings", {}) or {}
    funder = fm.get("funder") if fm else None
    if headings_config and funder:
        headings_issues = validate_headings(text, headings_config, funder)
        for issue in headings_issues:
            issue["file"] = str(path)
        file_issues.extend(headings_issues)

    return {
        "file": str(path),
        "issues": file_issues,
    }


def validate_directory(
    path: Path,
    config,
    sample: int | None = None,
    tier: str | None = None,
) -> dict:
    """Validate all .md files in a directory, optionally filtered.

    Args:
        path: Directory containing .md files.
        config: ProjectConfig from load_project_config().
        sample: If set, randomly sample this many files.
        tier: If set, only validate files matching this tier
              (looks up tier from manifest at .folio/manifest.json).

    Returns:
        Dict with source_dir, files_scanned, files_passing,
        files_with_issues, validations (grouped by issue_type), summary.
    """
    from collections import defaultdict

    md_files = sorted(path.glob("*.md"))

    tier_filter: set[str] | None = None
    if tier and tier in ("full", "light", "minimal"):
        manifest_path = path / "manifest.json"
        if not manifest_path.exists():
            manifest_path = path.parent / ".folio" / "manifest.json"
        if not manifest_path.exists():
            logger.warning(
                "Manifest not found at %s or %s — tier filter will return no files.",
                path / "manifest.json",
                path.parent / ".folio" / "manifest.json",
            )
        manifest = load_manifest(manifest_path)
        tier_filter = set()
        for fname, entry in manifest.get("files", {}).items():
            entry_tier = entry.get("tier", "")
            if hasattr(entry_tier, "value"):
                entry_tier = entry_tier.value
            if entry_tier == tier:
                tier_filter.add(fname)

    if tier_filter is not None:
        md_files = [f for f in md_files if f.name in tier_filter]

    if sample and sample > 0 and sample < len(md_files):
        md_files = random.sample(md_files, sample)

    all_issues: dict[str, list[dict]] = defaultdict(list)
    files_with_issues = 0
    files_passing = 0

    for fpath in md_files:
        result = validate_file(fpath, config)
        if result["issues"]:
            files_with_issues += 1
            for issue in result["issues"]:
                issue_type = issue.get("issue_type", "unknown")
                all_issues[issue_type].append(issue)
        else:
            files_passing += 1

    if files_with_issues:
        counts = []
        for issue_type, items in sorted(all_issues.items()):
            counts.append(f"{len(items)} {issue_type}")
        summary = f"{files_with_issues} files have issues: {', '.join(counts)}"
    else:
        summary = "All files pass validation."

    return {
        "source_dir": str(path),
        "files_scanned": len(md_files),
        "files_passing": files_passing,
        "files_with_issues": files_with_issues,
        "validations": dict(all_issues),
        "summary": summary,
    }
