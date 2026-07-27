"""Wiki quality audit.

Scans compiled wiki for cleanup candidates: dead links, thin articles,
near-duplicates, suspicious concepts, stale content, missing sections,
provenance issues, low confidence, placeholder/speculative phrasing,
truncation suspects, weak sections, link noise, name collisions.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

LINK_NOISE_RE = re.compile(r"(?<!\[)\[[a-z0-9][a-z0-9\-\.]+(?!\])")

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
    # ── Provenance & confidence ─────────────────────────────────────
    "flag_sourceless": True,
    "flag_low_confidence": True,
    # ── Placeholder phrasing ────────────────────────────────────────
    "placeholder_phrases": [
        "no specific", "no data", "no quantitative", "no concrete",
        "no verifiable", "no corroborating", "insufficient information exists",
        "future updates should", "future archival research should",
        "future research should", "absence of source documentation",
        "no primary source materials were provided for this",
        "remains unconfirmed", "remain undocumented",
        "absence of specific figures", "absence of detailed documentation",
        "not been substantiated with detailed documentation",
        "no source material", "no specific numerical data",
        "no specific figures", "no specific numbers", "no specific amounts",
        "no source data", "no figures", "no statistics",
        "no attendance", "no dates", "no dollar amounts",
        "no percentages", "no count",
    ],
    # ── Speculative phrasing ────────────────────────────────────────
    "speculative_phrases": [
        "likely", "may have been", "could have", "possibly",
        "plausible", "presumed", "assumed", "it is plausible",
        "may represent", "might", "potentially",
        "without source verification", "untreated", "unknown",
        "remains unknown", "not documented", "cannot be determined",
    ],
    # ── Truncation suspects ─────────────────────────────────────────
    "truncation_suspect_phrases": [
        "the following data points are missing:",
        "pending retrieval of",
        "future updates should incorporate any available facts",
        "the absence of specific figures here reflects the current state of the source record",
        "all data above derives from publicly available information",
    ],
    # Require a second signal (incomplete final line, missing closing ---, or truncated table)
    # so generator boilerplate phrases don't cause false positives
    "truncation_require_second_signal": True,
    # ── Weak sections ───────────────────────────────────────────────
    "weak_section_headers": ["key figures"],
    "weak_section_phrases": ["no specific", "no data"],
    # ── Link noise ──────────────────────────────────────────────────
    "flag_link_noise": True,
    # ── Name-based collisions (stem dedup) ─────────────────────────
    "name_collision_enabled": True,
    # Threshold for content detection: if two same-stem files have
    # content similarity below this, they are content-divergent
    # and should be merged, not quarantined
    "name_collision_content_divergence_threshold": 0.30,
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
                "provenance": [],
                "low_confidence": [],
                "placeholder_phrasing": [],
                "speculative_phrasing": [],
                "truncation_suspects": [],
                "weak_sections": [],
                "link_noise": [],
                "name_collisions": [],
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
                "provenance": [],
                "low_confidence": [],
                "placeholder_phrasing": [],
                "speculative_phrasing": [],
                "truncation_suspects": [],
                "weak_sections": [],
                "link_noise": [],
                "name_collisions": [],
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
        "provenance": _check_provenance(articles, cfg),
        "low_confidence": _check_low_confidence(articles, cfg),
        "placeholder_phrasing": _check_placeholder_phrasing(articles, cfg),
        "speculative_phrasing": _check_speculative_phrasing(articles, cfg),
        "truncation_suspects": _check_truncation_suspects(articles, cfg),
        "weak_sections": _check_weak_sections(articles, cfg),
        "link_noise": _check_link_noise(articles, cfg),
        "name_collisions": _check_name_collisions(articles, cfg),
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

        frontmatter: dict = {}
        if fm_lines:
            fm_text = "\n".join(fm_lines)
            try:
                fm = yaml.safe_load(fm_text)
                if isinstance(fm, dict):
                    frontmatter = fm
                    if fm.get("aliases"):
                        aliases = [
                            str(a).lower().replace(" ", "-") for a in fm["aliases"]
                        ]
            except yaml.YAMLError as e:
                logger.debug("YAML parse error in %s frontmatter: %s", fp.name, e)

        wikilinks = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)

        word_bag = frozenset(
            w.lower() for w in re.findall(r"\w{4,}", body_text)
        )

        articles.append({
            "file": fp,
            "name": fp.stem,
            "aliases": aliases,
            "frontmatter": frontmatter,
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


def _check_provenance(articles: list[dict], config: dict) -> list[dict]:
    """Flag articles with empty sources in frontmatter."""
    if not config.get("flag_sourceless", True):
        return []

    issues: list[dict] = []
    for art in articles:
        fm = art.get("frontmatter", {})
        sources = fm.get("sources")
        if isinstance(sources, list) and len(sources) == 0:
            issues.append({
                "file": str(art["file"]),
                "article": art["name"],
                "source_count": 0,
            })
    return issues


def _check_low_confidence(articles: list[dict], config: dict) -> list[dict]:
    """Flag articles with confidence: low in frontmatter."""
    if not config.get("flag_low_confidence", True):
        return []

    issues: list[dict] = []
    for art in articles:
        fm = art.get("frontmatter", {})
        confidence = fm.get("confidence")
        if isinstance(confidence, str) and confidence.lower() == "low":
            issues.append({
                "file": str(art["file"]),
                "article": art["name"],
                "confidence": confidence,
            })
    return issues


def _check_phrasing(articles: list[dict], config: dict, config_key: str) -> list[dict]:
    """Flag articles whose body text contains any of the configured phrases.

    Reports only the first matching phrase per article to avoid noise.
    """
    phrases = config.get(config_key, [])
    if not phrases:
        return []

    issues: list[dict] = []
    for art in articles:
        body = art["body_text"].lower()
        for phrase in phrases:
            idx = body.find(phrase.lower())
            if idx != -1:
                line_no = None
                for i, line in enumerate(art["lines"]):
                    if phrase.lower() in line.lower():
                        line_no = i + 1
                        break
                issues.append({
                    "file": str(art["file"]),
                    "article": art["name"],
                    "phrase": phrase,
                    "line": line_no,
                })
                break
    return issues


def _check_placeholder_phrasing(articles: list[dict], config: dict) -> list[dict]:
    """Flag articles with known placeholder phrases."""
    return _check_phrasing(articles, config, "placeholder_phrases")


def _check_speculative_phrasing(articles: list[dict], config: dict) -> list[dict]:
    """Flag articles with speculative hedging phrases."""
    return _check_phrasing(articles, config, "speculative_phrases")


def _check_truncation_suspects(articles: list[dict], config: dict) -> list[dict]:
    """Flag content that appears truncated or incomplete."""
    phrases = config.get("truncation_suspect_phrases", [])
    if not phrases:
        return []

    require_second = config.get("truncation_require_second_signal", True)
    issues: list[dict] = []

    for art in articles:
        body = art["body_text"]
        matched_phrase = None
        for phrase in phrases:
            idx = body.lower().find(phrase.lower())
            if idx != -1:
                matched_phrase = phrase
                break

        if matched_phrase is None:
            continue

        if require_second:
            second_signal = _find_truncation_second_signal(art)
            if not second_signal:
                continue
        else:
            second_signal = "phrase_match_only"

        line_no = None
        for i, line in enumerate(art["lines"]):
            if matched_phrase.lower() in line.lower():
                line_no = i + 1
                break

        issues.append({
            "file": str(art["file"]),
            "article": art["name"],
            "phrase": matched_phrase,
            "line": line_no,
            "reason": second_signal,
        })

    return issues


def _find_truncation_second_signal(art: dict) -> str | None:
    """Find a second signal confirming truncation beyond a suspect phrase.

    Returns the reason string or None if no second signal found.
    """
    # Signal 1: missing closing frontmatter delimiter
    lines = art["lines"]
    if lines and lines[0].strip() == "---":
        found_closing = False
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                found_closing = True
                break
        if not found_closing:
            return "missing_closing_frontmatter"

    # Signal 2: truncated table (last line is part of a table) — check before
    # incomplete_final_line since table rows don't end with sentence terminators
    if lines:
        last_line = lines[-1].strip()
        if last_line.startswith("|"):
            return "truncated_table"

    # Signal 3: incomplete final line
    body_lines_raw = art["lines"][art["body_start"]:]
    body_lines = [ln for ln in body_lines_raw if ln.strip()]
    if body_lines:
        last = body_lines[-1].strip()
        if last and last[-1] not in {".", "!", "?", '"', ")", "]", ":"}:
            return "incomplete_final_line"

    return None


def _check_weak_sections(articles: list[dict], config: dict) -> list[dict]:
    """Find sections that are templated-empty under weak section headers."""
    headers = config.get("weak_section_headers", [])
    weak_phrases = config.get("weak_section_phrases", [])
    if not headers:
        return []

    issues: list[dict] = []

    for art in articles:
        sections = _parse_sections(art)
        for section in sections:
            if section["header"].lower() not in [h.lower() for h in headers]:
                continue
            body = section["body"].strip()
            if not body:
                issues.append({
                    "file": str(art["file"]),
                    "article": art["name"],
                    "section": section["header"],
                    "line": section["line"],
                })
                continue
            has_content = False
            for line in body.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                is_weak = any(
                    wp.lower() in stripped.lower() for wp in weak_phrases
                )
                if not is_weak:
                    has_content = True
                    break
            if not has_content:
                issues.append({
                    "file": str(art["file"]),
                    "article": art["name"],
                    "section": section["header"],
                    "line": section["line"],
                })
    return issues


def _parse_sections(art: dict) -> list[dict]:
    """Parse an article into sections by ## headings.

    Returns list of {"header": str, "line": int, "body": str}.
    """
    sections: list[dict] = []
    current_header: str | None = None
    current_line: int = 0
    current_body_lines: list[str] = []
    header_pattern = re.compile(r"^## (.+)")

    for i, line in enumerate(art["lines"]):
        if i < art["body_start"]:
            continue
        m = header_pattern.match(line)
        if m:
            if current_header is not None:
                sections.append({
                    "header": current_header,
                    "line": current_line + 1,
                    "body": "\n".join(current_body_lines),
                })
            current_header = m.group(1).strip()
            current_line = i
            current_body_lines = []
        elif current_header is not None:
            current_body_lines.append(line)

    if current_header is not None:
        sections.append({
            "header": current_header,
            "line": current_line + 1,
            "body": "\n".join(current_body_lines),
        })
    return sections


def _check_link_noise(articles: list[dict], config: dict) -> list[dict]:
    """Find malformed link-like tokens that aren't proper markdown links."""
    if not config.get("flag_link_noise", True):
        return []

    issues: list[dict] = []

    for art in articles:
        body = art["body_text"]
        m = LINK_NOISE_RE.search(body)
        if m:
            token = m.group(0)
            line_no = None
            for i, line in enumerate(art["lines"]):
                if token in line:
                    line_no = i + 1
                    break
            issues.append({
                "file": str(art["file"]),
                "article": art["name"],
                "token": token,
                "line": line_no,
            })
    return issues


def _check_name_collisions(articles: list[dict], config: dict) -> list[dict]:
    """Find articles whose stems normalize to the same key.

    For same-stem pairs with low content similarity (< threshold),
    marks as 'content_divergent' (should be merged, not quarantined).
    Otherwise ranks by quality signals and marks as 'collision'.
    """
    if not config.get("name_collision_enabled", True):
        return []

    threshold = config.get("name_collision_content_divergence_threshold", 0.30)
    issues: list[dict] = []
    reported: set[tuple[str, str]] = set()

    name_buckets: dict[str, list[dict]] = {}
    for art in articles:
        key = re.sub(r"[^a-z0-9]", "", art["name"].lower())
        name_buckets.setdefault(key, []).append(art)

    for bucket in name_buckets.values():
        if len(bucket) < 2:
            continue
        for i, a in enumerate(bucket):
            for b in bucket[i + 1:]:
                pair = tuple(sorted([a["name"], b["name"]]))
                if pair in reported:
                    continue
                reported.add(pair)

                sm = SequenceMatcher(None, a["body_text"], b["body_text"])
                similarity = round(sm.ratio(), 4)

                if similarity < threshold:
                    issues.append({
                        "file_a": str(a["file"]),
                        "file_b": str(b["file"]),
                        "article_a": a["name"],
                        "article_b": b["name"],
                        "similarity": similarity,
                        "subtype": "content_divergent",
                    })
                else:
                    ranked = _rank_by_quality([a, b])
                    canonical = ranked[0]
                    collision = ranked[1]
                    issues.append({
                        "file_a": str(canonical["file"]),
                        "file_b": str(collision["file"]),
                        "article_a": canonical["name"],
                        "article_b": collision["name"],
                        "similarity": similarity,
                        "subtype": "collision",
                    })
    return issues


def _quality_score(art: dict) -> tuple[int, int, int, int, int]:
    """Score an article for quality ranking (higher = better).

    Returns (confidence_rank, source_count, word_count, section_count, name_quality).
    Confidence: high=3, medium=2, unknown/low=1.
    Name quality: 1 if pure ASCII lowercase slug, 0 otherwise.
    """
    fm = art.get("frontmatter", {})
    confidence = fm.get("confidence")
    if isinstance(confidence, str):
        cl = confidence.lower()
        conf_rank = 3 if cl == "high" else 2 if cl == "medium" else 1
    else:
        conf_rank = 1

    sources = fm.get("sources")
    source_count = len(sources) if isinstance(sources, list) else 0

    word_count = len(art["body_text"].split())

    section_count = 0
    for line in art["lines"][art["body_start"]:]:
        if re.match(r"^## ", line):
            section_count += 1

    name_quality = 1 if re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", art["name"]) else 0

    return (conf_rank, source_count, word_count, section_count, name_quality)


def _rank_by_quality(arts: list[dict]) -> list[dict]:
    """Sort articles by quality score descending."""
    return sorted(arts, key=_quality_score, reverse=True)


def _apply_fixes(articles: list[dict], issues: dict, config: dict | None = None) -> dict:
    """Apply deterministic, safe fixes for audit issues.

    Returns {"fixed_count": int, "changed_files": [str], "actions": [{"file": str, "action": str}]}.
    """
    changed_files: set[str] = set()
    actions: list[dict] = []
    cfg = {**DEFAULT_AUDIT_CONFIG, **(config or {})}

    # Collect files with weak sections for targeted fix
    weak_files: set[str] = set()
    weak_sections_by_file: dict[str, list[dict]] = {}
    for issue in issues.get("weak_sections", []):
        fpath = issue["file"]
        weak_files.add(fpath)
        weak_sections_by_file.setdefault(fpath, []).append(issue)

    # Collect files with placeholder phrasing
    placeholder_files: set[str] = set()
    for issue in issues.get("placeholder_phrasing", []):
        placeholder_files.add(issue["file"])

    # Collect files with link noise
    link_noise_files: set[str] = set()
    for issue in issues.get("link_noise", []):
        link_noise_files.add(issue["file"])

    for art in articles:
        fpath_str = str(art["file"])
        fp = art["file"]
        lines = list(art["lines"])
        changed = False

        # 1. Remove empty weak sections
        if fpath_str in weak_files:
            weak_sections = weak_sections_by_file.get(fpath_str, [])
            sections_to_remove = set()
            for ws in weak_sections:
                sections_to_remove.add(ws["section"].lower())

            new_lines: list[str] = []
            in_weak_section = False
            for i, line in enumerate(lines):
                if i < art["body_start"]:
                    new_lines.append(line)
                    continue
                m = re.match(r"^## (.+)", line)
                if m:
                    header = m.group(1).strip()
                    if header.lower() in sections_to_remove:
                        in_weak_section = True
                        continue
                    else:
                        in_weak_section = False
                if in_weak_section:
                    changed = True
                    continue
                new_lines.append(line)
            if changed:
                lines = new_lines
                actions.append({"file": fpath_str, "action": "removed_weak_sections"})

        # 2. Strip placeholder paragraphs (standalone paragraph entirely composed of placeholder phrases)
        if fpath_str in placeholder_files:
            phrases = cfg.get("placeholder_phrases", [])
            if phrases:
                new_lines = []
                paragraph_lines: list[str] = []
                in_paragraph = False

                def _is_placeholder_paragraph(para_lines: list[str]) -> bool:
                    non_empty = [ln.strip().lower() for ln in para_lines if ln.strip()]
                    if not non_empty:
                        return False
                    return all(
                        any(phrase.lower() in ln for phrase in phrases)
                        for ln in non_empty
                    )

                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if i < art["body_start"]:
                        new_lines.append(line)
                        in_paragraph = False
                        paragraph_lines = []
                        continue
                    if stripped.startswith("#"):
                        new_lines.append(line)
                        in_paragraph = False
                        paragraph_lines = []
                        continue
                    if not stripped:
                        if in_paragraph and _is_placeholder_paragraph(paragraph_lines):
                            changed = True
                        else:
                            new_lines.extend(paragraph_lines)
                            new_lines.append(line)
                        in_paragraph = False
                        paragraph_lines = []
                        continue
                    if not in_paragraph:
                        in_paragraph = True
                        paragraph_lines = [line]
                    else:
                        paragraph_lines.append(line)

                if in_paragraph and _is_placeholder_paragraph(paragraph_lines):
                    changed = True
                else:
                    new_lines.extend(paragraph_lines)
                if changed:
                    lines = new_lines
                    actions.append({"file": fpath_str, "action": "stripped_placeholder_paragraphs"})

        # 3. Escape link noise
        if fpath_str in link_noise_files:
            new_lines = []
            for line in lines:
                new_line = LINK_NOISE_RE.sub(lambda m: "\\" + m.group(0), line)
                if new_line != line:
                    changed = True
                new_lines.append(new_line)
            if changed:
                lines = new_lines
                actions.append({"file": fpath_str, "action": "escaped_link_noise"})

        if changed:
            changed_files.add(fpath_str)
            fp.write_text("\n".join(lines))

    return {
        "fixed_count": len(changed_files),
        "changed_files": sorted(changed_files),
        "actions": actions,
    }


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
        "provenance": "Sourceless articles",
        "low_confidence": "Low-confidence articles",
        "placeholder_phrasing": "Placeholder phrasing",
        "speculative_phrasing": "Speculative phrasing",
        "truncation_suspects": "Truncation suspects",
        "weak_sections": "Weak sections",
        "link_noise": "Link/syntax noise",
        "name_collisions": "Name collisions",
    }

    for key, label in labels.items():
        count = len(issues.get(key, []))
        lines.append(f"  {label}: {count}")

    return "\n".join(lines)
