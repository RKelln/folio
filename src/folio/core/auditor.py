"""Wiki quality audit.

Scans compiled wiki for cleanup candidates: dead links, thin articles,
near-duplicates, suspicious concepts, stale content, missing sections.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import yaml

DEFAULT_AUDIT_CONFIG: dict = {
    "min_article_chars": 200,
    "min_article_lines": 5,
    "dedup_threshold": 0.85,
    "word_overlap_threshold": 0.35,
    "word_band_size": 30,
    "expected_sections": [
        "Definition",
        "Key Figures",
        "Body",
        "Context & Significance",
        "See also",
    ],
    "required_sections": ["Body"],
    "stale_content_patterns": [],
    "suspicious_name_patterns": [
        (r"^\d{3}-\d{3}-\d{4}$", "phone_number"),
        (r"^application-id-\d+", "application_id"),
        (r"^file-no-\d+.*", "file_number"),
        (r"^ontario-corporation-number-\d+", "org_number"),
        (r"^rr-\d+[a-z]+\d+", "org_number"),
    ],
    "present_tense_indicators": [
        r"\bis (?:the|a|an|currently|now|presently)\b",
        r"\bcurrent(?:ly)?\b",
        r"\bpresent(?:ly)?\b",
        r"\bnow (?:located|housed|based|operating)\b",
        r"\bas of (?:today|now)\b",
        r"\btoday\b",
    ],
    "timeline_keywords": [
        "former",
        "previous",
        "relocated",
        "moved to",
        "moved from",
        "succeeded by",
        "replaced by",
        "until",
        "stepped down",
        "resigned",
        "left in",
        "departed",
        "transitioned",
    ],
}


def audit_wiki(wiki_dir: Path, config: dict | None = None) -> dict:
    """Audit a compiled sage-wiki for cleanup candidates.

    Returns a dict with audit findings:
    {
        "articles_scanned": int,
        "issues": {
            "dead_links": [{"file": str, "line": int, "target": str}],
            "thin_articles": [{"file": str, "lines": int, "chars": int}],
            "near_duplicates": [{"file_a": str, "file_b": str, "similarity": float}],
            "missing_sections": [{"file": str, "missing": [str]}],
            "suspicious_concepts": [{"file": str, "subtype": str}],
            "stale_content": [{"file": str, "reason": str}],
        },
        "summary": str
    }
    """
    cfg = {**DEFAULT_AUDIT_CONFIG, **(config or {})}

    concepts_dir = wiki_dir / "wiki" / "concepts"
    if not concepts_dir.is_dir():
        return {
            "articles_scanned": 0,
            "issues": {
                "dead_links": [],
                "thin_articles": [],
                "near_duplicates": [],
                "missing_sections": [],
                "suspicious_concepts": [],
                "stale_content": [],
            },
            "summary": f"Concepts directory not found: {concepts_dir}",
        }

    articles = _scan_articles(concepts_dir)
    if not articles:
        return {
            "articles_scanned": 0,
            "issues": {
                "dead_links": [],
                "thin_articles": [],
                "near_duplicates": [],
                "missing_sections": [],
                "suspicious_concepts": [],
                "stale_content": [],
            },
            "summary": f"No articles found in {concepts_dir}",
        }

    issues = {
        "dead_links": _check_dead_links(articles),
        "thin_articles": _check_thin_articles(articles, cfg),
        "near_duplicates": _check_near_duplicates(articles, cfg),
        "missing_sections": _check_missing_sections(articles, cfg),
        "suspicious_concepts": _check_suspicious_concepts(articles, cfg),
        "stale_content": _check_stale_content(articles, cfg),
    }

    findings: dict = {
        "articles_scanned": len(articles),
        "issues": issues,
        "summary": "",
    }
    findings["summary"] = audit_summary_text(findings)
    return findings


def _scan_articles(articles_dir: Path) -> list[dict]:
    """Scan all .md files in concepts dir, extract frontmatter, body, wikilinks."""
    articles: list[dict] = []
    for fp in sorted(articles_dir.glob("*.md")):
        content = fp.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        body_start = 0
        aliases: list[str] = []
        in_fm = False
        fm_lines: list[str] = []

        for i, line in enumerate(lines):
            if line.strip() == "---":
                if i == 0:
                    in_fm = True
                elif in_fm:
                    body_start = i + 1
                    break
            elif in_fm:
                fm_lines.append(line)

        body_lines = [ln for ln in lines[body_start:] if ln.strip()]
        body_text = "\n".join(body_lines)

        if fm_lines:
            fm_text = "\n".join(fm_lines)
            try:
                fm = yaml.safe_load(fm_text)
                if isinstance(fm, dict) and fm.get("aliases"):
                    aliases = [
                        str(a).lower().replace(" ", "-") for a in fm["aliases"]
                    ]
            except Exception:
                pass

        wikilinks = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)

        word_bag = frozenset(
            w.lower() for w in re.findall(r"\w{4,}", body_text)
        )

        articles.append({
            "file": fp,
            "name": fp.stem,
            "aliases": aliases,
            "content": content,
            "lines": lines,
            "body_start": body_start,
            "body_text": body_text,
            "body_len": len(body_text),
            "body_line_count": len(body_lines),
            "wikilinks": wikilinks,
            "total_lines": len(lines),
            "word_bag": word_bag,
        })
    return articles


def _check_dead_links(articles: list[dict]) -> list[dict]:
    """Find [[wikilinks]] to targets that don't exist in the wiki."""
    existing = {a["name"] for a in articles}
    for art in articles:
        for alias in art.get("aliases", []):
            existing.add(alias)

    issues: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for art in articles:
        for link in art["wikilinks"]:
            target = link.lower().replace(" ", "-")
            target = re.sub(r"[()/,._'&]", "-", target)
            target = re.sub(r"-+", "-", target).strip("-")
            if target not in existing and target != art["name"]:
                key = (art["name"], target)
                if key in seen:
                    continue
                seen.add(key)
                line_no = None
                for i, line in enumerate(art["lines"]):
                    if link in line:
                        line_no = i + 1
                        break
                issues.append({
                    "file": str(art["file"]),
                    "line": line_no,
                    "target": target,
                    "article": art["name"],
                    "target_display": link,
                })
    return issues


def _check_thin_articles(articles: list[dict], config: dict) -> list[dict]:
    """Find articles below minimum size thresholds."""
    min_chars = config.get("min_article_chars", 200)
    min_lines = config.get("min_article_lines", 5)
    issues: list[dict] = []
    for art in articles:
        if art["body_len"] < min_chars or art["body_line_count"] < min_lines:
            issues.append({
                "file": str(art["file"]),
                "lines": art["body_line_count"],
                "chars": art["body_len"],
                "article": art["name"],
            })
    return issues


def _check_near_duplicates(articles: list[dict], config: dict) -> list[dict]:
    """Find pairs of articles with high content similarity.

    Optimisation:
    1. Name-based dedup: filenames that normalise to the same key.
    2. Word-bag size banding: only compare pairs whose word-bag sizes are
       within the same band or adjacent bands.
    3. Word-bag Jaccard pre-filter on band-candidate pairs.
    4. Truncated quick_ratio on Jaccard survivors.
    5. Full SequenceMatcher.ratio() only on final candidates.
    """
    threshold = config.get("dedup_threshold", 0.85)
    word_overlap = config.get("word_overlap_threshold", 0.35)
    band_size = config.get("word_band_size", 30)
    issues: list[dict] = []
    reported: set[tuple[str, str]] = set()

    # --- name-based near-duplicates ---
    name_buckets: dict[str, list[dict]] = {}
    for art in articles:
        key = re.sub(r"[^a-z0-9]", "", art["name"].lower())
        name_buckets.setdefault(key, []).append(art)

    for bucket in name_buckets.values():
        if len(bucket) < 2:
            continue
        for i, a in enumerate(bucket):
            for b in bucket[i + 1 :]:
                pair = tuple(sorted([a["name"], b["name"]]))
                if pair in reported:
                    continue
                reported.add(pair)
                issues.append({
                    "file_a": str(a["file"]),
                    "file_b": str(b["file"]),
                    "similarity": 1.0,
                    "article_a": a["name"],
                    "article_b": b["name"],
                })

    # --- content similarity with size banding ---
    # Assign each article to a word-bag size band
    bands: dict[int, list[dict]] = {}
    for art in articles:
        wb_size = len(art["word_bag"])
        band = wb_size // band_size if band_size > 0 else 0
        bands.setdefault(band, []).append(art)

    # Compare only within each band and adjacent bands
    seen_band_pairs: set[tuple[int, int]] = set()
    for band_a, arts_a in bands.items():
        for band_b_offset in (0, 1):
            band_b = band_a + band_b_offset
            if band_b not in bands:
                continue
            band_pair = (band_a, band_b)
            if band_pair in seen_band_pairs:
                continue
            seen_band_pairs.add(band_pair)

            arts_b = bands[band_b]
            for a in arts_a:
                for b in arts_b:
                    if a is b:
                        continue
                    if band_a == band_b and a["name"] >= b["name"]:
                        continue

                    pair = tuple(sorted([a["name"], b["name"]]))
                    if pair in reported:
                        continue

                    # Length ratio filter
                    if max(a["body_len"], b["body_len"]) == 0:
                        continue
                    len_ratio = min(a["body_len"], b["body_len"]) / max(
                        a["body_len"], b["body_len"]
                    )
                    if len_ratio < 0.5:
                        continue

                    # Word-bag Jaccard pre-filter
                    ab = a["word_bag"]
                    bb = b["word_bag"]
                    if not ab or not bb:
                        continue
                    intersection = len(ab & bb)
                    min_wb = min(len(ab), len(bb))
                    if min_wb == 0:
                        continue
                    if intersection / min_wb < word_overlap:
                        continue

                    # Truncated quick_ratio
                    trunc_a = a["body_text"][:800]
                    trunc_b = b["body_text"][:800]
                    sm_trunc = SequenceMatcher(None, trunc_a, trunc_b)
                    if sm_trunc.quick_ratio() < threshold:
                        continue

                    # Full ratio
                    sm = SequenceMatcher(None, a["body_text"], b["body_text"])
                    ratio = sm.ratio()
                    if ratio >= threshold:
                        reported.add(pair)
                        issues.append({
                            "file_a": str(a["file"]),
                            "file_b": str(b["file"]),
                            "similarity": round(ratio, 4),
                            "article_a": a["name"],
                            "article_b": b["name"],
                        })

    return issues


def _check_missing_sections(articles: list[dict], config: dict) -> list[dict]:
    """Find concept articles missing expected sections."""
    expected = config.get("expected_sections", [])
    required = config.get("required_sections", [])
    all_sections = sorted(set(expected + required))
    if not all_sections:
        return []

    issues: list[dict] = []
    for art in articles:
        headings: set[str] = set()
        for line in art["lines"][art["body_start"] :]:
            m = re.match(r"^## (.+)", line)
            if m:
                headings.add(m.group(1).strip())
        missing = [s for s in all_sections if s not in headings]
        if missing:
            issues.append({
                "file": str(art["file"]),
                "missing": missing,
                "article": art["name"],
            })
    return issues


def _check_suspicious_concepts(articles: list[dict], config: dict) -> list[dict]:
    """Find articles with names matching suspicious patterns (phone numbers, IDs, etc.)."""
    patterns = config.get("suspicious_name_patterns", [])
    if not patterns:
        return []

    issues: list[dict] = []
    for art in articles:
        for pattern, label in patterns:
            if re.match(pattern, art["name"]):
                issues.append({
                    "file": str(art["file"]),
                    "subtype": label,
                    "article": art["name"],
                })
                break
    return issues


def _check_stale_content(articles: list[dict], config: dict) -> list[dict]:
    """If patterns configured, flag articles with present-tense language that may
    describe former states.
    """
    patterns = config.get("stale_content_patterns", [])
    if not patterns:
        return []

    present_indicators = config.get(
        "present_tense_indicators",
        DEFAULT_AUDIT_CONFIG["present_tense_indicators"],
    )
    timeline_keywords = config.get(
        "timeline_keywords",
        DEFAULT_AUDIT_CONFIG["timeline_keywords"],
    )

    issues: list[dict] = []
    for art in articles:
        body = art["body_text"]

        has_present = any(
            re.search(indicator, body, re.IGNORECASE)
            for indicator in present_indicators
        )
        if not has_present:
            continue

        for pat in patterns:
            keywords = pat.get("keywords", [])
            if not keywords:
                continue
            matches = any(kw.lower() in art["name"].lower() for kw in keywords)
            if not matches:
                continue

            require_link = pat.get("require_link")
            if require_link and f"[[{require_link}]]" not in body:
                continue

            has_timeline = any(kw in body.lower() for kw in timeline_keywords)
            if has_timeline:
                continue

            line_no = art["body_start"] + 1
            for i, line in enumerate(
                art["lines"][art["body_start"] :],
                start=art["body_start"] + 1,
            ):
                for indicator in present_indicators:
                    if re.search(indicator, line, re.IGNORECASE):
                        line_no = i
                        break
                else:
                    continue
                break

            hint = pat.get(
                "hint", "Uses present tense — may describe a former state"
            )
            issues.append({
                "file": str(art["file"]),
                "reason": hint,
                "line": line_no,
                "article": art["name"],
            })
            break

    return issues


def audit_summary_text(findings: dict) -> str:
    """Return a human-readable multi-line summary of audit findings."""
    lines = [f"Articles scanned: {findings['articles_scanned']}", ""]

    issues = findings["issues"]
    total = sum(len(v) for v in issues.values())
    lines.append(f"Total issues: {total}")
    lines.append("")

    labels = {
        "dead_links": "Dead wikilinks",
        "thin_articles": "Thin articles",
        "near_duplicates": "Near-duplicates",
        "missing_sections": "Missing sections",
        "suspicious_concepts": "Suspicious concepts",
        "stale_content": "Stale content",
    }

    for key, label in labels.items():
        count = len(issues.get(key, []))
        lines.append(f"  {label}: {count}")

    return "\n".join(lines)
