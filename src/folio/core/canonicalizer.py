"""Version detection and deduplication.

Identifies non-canonical versions (drafts, superseded submissions,
near-duplicates) using filename pattern scoring and content similarity.
Optionally uses LLM for ambiguous cases.

All patterns are driven by configuration — no hardcoded org-specific rules.
"""

import logging
import re
import shutil
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from folio.core.prioritizer import _parse_llm_response

logger = logging.getLogger(__name__)

# ── Default configuration ──────────────────────────────────────────────────────

DEFAULT_CANONICALIZE_CONFIG: dict = {
    # An "application" is identified by the first N __-separated segments.
    "group_segments": 2,

    # Patterns matching numbered submission segments in filenames.
    # Higher number = more final.  `number_group` extracts the submission number.
    "submission_segments": [
        {"pattern": r"^submission_(\d+)$", "number_group": 1},
        {"pattern": r"^(\d+)(?:st|nd|rd|th)_submission$", "number_group": 1},
        {"pattern": r"^(\d+)(?:st|nd|rd|th)_sub$", "number_group": 1},
        {"pattern": r"^submission_v(\d+)$", "number_group": 1},
    ],

    # Segments matching these are NOT submission versions — they are document
    # categories (e.g. report, budget, application).  All are kept subject to
    # version / draft filtering.
    "category_segments": [
        r"^report",
        r"^results?$",
        r"^acceptance$",
        r"^approval",
        r"^notice",
        r"^support",
        r"^budget$",
        r"^finance$",
        r"^application$",
        r"^notification",
        r"^agreement$",
        r"^declaration$",
        r"^planning$",
        r"^documentation$",
        r"^activity_lists?$",
        r"^supplementary$",
        r"^attachments",
        r"^confirmation",
        r"^submitted$",
        r"^final_submission$",
        r"^final_report",
        r"^mid-cycle_report",
        r"^submission_confirm",
        r"^press$",
        r"^promo$",
        r"^equipment",
    ],

    # Suffixes that INCREASE finalness score (higher = more canonical).
    "version_suffixes": [
        {"pattern": r"_final$", "score": 100},
        {"pattern": r"_FINAL$", "score": 100},
        {"pattern": r"_Final$", "score": 100},
        {"pattern": r"_submitted$", "score": 90},
        {"pattern": r"_SUBMITTED$", "score": 90},
        {"pattern": r"_Submitted$", "score": 90},
        {"pattern": r"_signed$", "score": 85},
        {"pattern": r"_v(\d+)$", "score_per_number": 10},
        {"pattern": r"_V(\d+)$", "score_per_number": 10},
        {"pattern": r"_updated$", "score": 5},
        {"pattern": r"_corrected$", "score": 5},
    ],

    # Suffixes that DECREASE finalness score (draft / working markers).
    "draft_suffixes": [
        {"pattern": r"_draft$", "score": -50},
        {"pattern": r"_DRAFT$", "score": -50},
        {"pattern": r"_prep$", "score": -50},
        {"pattern": r"_PREP$", "score": -50},
        {"pattern": r"_working$", "score": -50},
        {"pattern": r"_WORKING$", "score": -50},
        {"pattern": r"_todo$", "score": -50},
        {"pattern": r"_ToDo$", "score": -50},
        {"pattern": r"_notes$", "score": -30},
        {"pattern": r"_Notes$", "score": -30},
        {"pattern": r"_copy$", "score": -30},
        {"pattern": r"_Copy$", "score": -30},
        {"pattern": r"_edit$", "score": -30},
        {"pattern": r"_EDIT$", "score": -30},
        {"pattern": r"_blank$", "score": -30},
        {"pattern": r"_short$", "score": -20},
        {"pattern": r"_small$", "score": -20},
    ],

    # Patterns matching filenames that are always non-canonical (case-insensitive).
    "exclude_patterns": [
        r"_(?:draft|DRAFT|prep|PREP|working|WORKING|todo|ToDo|TODO)(?:_|\.)",
    ],

    # For matching docs across submissions: lower threshold since content may be
    # substantially edited between versions but still the same document.
    "content_match_threshold": 0.45,

    # For deduplicating within the canonical set: higher threshold since we only
    # want to remove near-identical duplicates.
    "dedup_content_threshold": 0.70,

    # Name-similarity pre-filter for dedup: only compare content if filenames
    # share at least this Jaccard similarity on word tokens.
    "dedup_name_threshold": 0.25,

    # Minimum content length in chars for a submission file to be considered
    # authoritative (shorter files may be corrupted and demoted).
    "min_content_length": 800,

    # Date pattern for tie-breaking within duplicate clusters.
    "date_pattern": r"(\d{4})-(\d{2})-(\d{2})",

    # LLM model for ambiguous resolution (only used when use_llm=True).
    "llm_model": "deepseek-chat",
}


# ── Public sub-functions ───────────────────────────────────────────────────────


def _parse_filename_segments(filename: str) -> list[str]:
    """Split a markdown filename by ``__`` into logical segments.

    The ``.md`` extension is stripped before splitting.  Segments that are
    empty after stripping underscores are dropped.

    >>> _parse_filename_segments('OAC__2024_Application__final.md')
    ['OAC', '2024_Application', 'final']
    """
    stem = filename.replace(".md", "")
    return [s for s in stem.split("__") if s.strip("_")]


def _score_filename(filename: str, config: dict) -> int:
    """Score a filename for canonicity using configurable suffix patterns.

    Positive scores come from ``version_suffixes`` (e.g. ``_final`` → +100).
    Negative scores come from ``draft_suffixes`` (e.g. ``_draft`` → -50).
    Suffixes with ``score_per_number`` multiply the captured digit by that
    value (e.g. ``_v3`` → 3 × 10 = 30).

    Patterns with ``$`` anchors match against the stem (filename without
    ``.md`` extension) so that ``_final$`` matches ``OAC__...__final.md``.

    >>> cfg = DEFAULT_CANONICALIZE_CONFIG
    >>> _score_filename('OAC__2024_Application__final.md', cfg) > 0
    True
    >>> _score_filename('OAC__2024_Application__draft.md', cfg) < 0
    True
    """
    stem = filename.replace(".md", "")
    score = 0
    for rule in config.get("version_suffixes", []):
        m = re.search(rule["pattern"], stem)
        if m:
            if "score_per_number" in rule:
                score += int(m.group(1)) * rule["score_per_number"]
            else:
                score += rule["score"]
    for rule in config.get("draft_suffixes", []):
        if re.search(rule["pattern"], stem):
            score += rule["score"]
    return score


def _detect_drafts(files: list[Path], config: dict) -> list[Path]:
    """Identify draft files among *files*.

    A file is considered a draft if:
    1. Its filename matches an ``exclude_patterns`` regex (case-insensitive).
    2. Its filename matches a ``draft_suffixes`` pattern.
    3. The first 500 characters of its content contain a draft indicator
       (checked case-insensitively).
    """
    drafts: list[Path] = []
    for fpath in files:
        filename = fpath.name
        stem = fpath.stem

        matched = False
        for pattern in config.get("exclude_patterns", []):
            if re.search(pattern, filename, re.IGNORECASE):
                matched = True
                break

        if not matched:
            for rule in config.get("draft_suffixes", []):
                if re.search(rule["pattern"], stem):
                    matched = True
                    break

        if not matched:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                head = content[:500].lower()
                for marker in ("draft", "work in progress", "not final", "pending review"):
                    if marker in head:
                        matched = True
                        break
            except Exception:
                pass

        if matched:
            drafts.append(fpath)
    return drafts


def _detect_duplicates(files: list[Path], config: dict) -> list[tuple[Path, Path]]:
    """Find near-duplicate pairs within *files* using content similarity.

    Two-stage filter:
    1. **Name pre-filter** — Jaccard similarity of word tokens must exceed
       ``dedup_name_threshold``.
    2. **Content comparison** — SequenceMatcher ratio of normalized text must
       exceed ``dedup_content_threshold``.

    Returns a list of ``(path_a, path_b)`` pairs that pass both filters.
    """
    content_threshold = config.get("dedup_content_threshold", 0.70)
    name_threshold = config.get("dedup_name_threshold", 0.25)

    texts: dict[Path, str] = {}
    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            texts[fpath] = _normalize_for_comparison(content)[:2000]
        except Exception:
            texts[fpath] = ""

    pairs: list[tuple[Path, Path]] = []
    path_list = list(files)
    for i in range(len(path_list)):
        a = path_list[i]
        for j in range(i + 1, len(path_list)):
            b = path_list[j]
            if _name_similarity_jaccard(a.stem, b.stem) < name_threshold:
                continue
            if texts[a] and texts[b]:
                sim = SequenceMatcher(None, texts[a], texts[b], autojunk=False).ratio()
                if sim >= content_threshold:
                    pairs.append((a, b))

    return pairs


def _group_files(files: list[Path], config: dict) -> dict[str, list[Path]]:
    """Group files by application key.

    An application key is formed by joining the first *N* ``__``-separated
    segments of each filename's stem, where *N* is ``group_segments`` (default 2).

    Example with ``group_segments=2``::

        OAC__2024__application.md   → group key "OAC__2024"
        OAC__2024__budget.md        → group key "OAC__2024"
        CCA__2025__report.md        → group key "CCA__2025"
    """
    n = config.get("group_segments", 2)
    groups: dict[str, list[Path]] = defaultdict(list)
    for fpath in files:
        segments = fpath.stem.split("__")
        key = "__".join(segments[:n]) if len(segments) >= n else fpath.stem
        groups[key].append(fpath)
    return dict(groups)


# ── Canonicalize directory (main entry point) ──────────────────────────────────


def canonicalize_directory(
    directory: Path,
    config: dict,
    archive_dir: Path | None = None,
    dry_run: bool = False,
    use_llm: bool = False,
    llm_provider=None,
) -> dict:
    """Analyze and filter *directory* for canonical (non-draft, non-duplicate) files.

    Returns a dict of ``{filename: {"status": "canonical"|"non_canonical", "reason": str}}``.

    If *archive_dir* is set and *dry_run* is False, non-canonical files are
    **moved** into *archive_dir* instead of deleted.

    When *use_llm* is True and *llm_provider* is provided, ambiguous
    cross-submission matches are resolved by an LLM.
    """
    files = sorted(directory.glob("*.md"))
    if not files:
        return {}

    # ── Phase 1: parse every file ───────────────────────────────────────────
    file_data = _parse_all_files(files, config)

    # ── Phase 2: detect drafts by filename + content ────────────────────────
    draft_paths = set(_detect_drafts(files, config))
    for info in file_data.values():
        if info["path"] in draft_paths:
            info["canonical"] = False
            info["reason"] = "draft marker in filename or content"

    # ── Phase 3: group and resolve submission versions ──────────────────────
    groups = _group_files(files, config)
    for _app_key, group_paths in groups.items():
        group_infos = [file_data[p.name] for p in group_paths]
        _process_group(group_infos, directory, config)

    # ── Phase 4: deduplicate within canonical set ───────────────────────────
    canonical_paths = [info["path"] for info in file_data.values() if info["canonical"]]
    dup_pairs = _detect_duplicates(canonical_paths, config)
    _resolve_duplicates(dup_pairs, file_data, config)

    # ── Phase 5: LLM ambiguous resolution (optional) ────────────────────────
    if use_llm and llm_provider is not None:
        _resolve_with_llm(file_data, config, llm_provider)

    # ── Build return manifest ───────────────────────────────────────────────
    result: dict = {}
    for fname, info in file_data.items():
        result[fname] = {
            "status": "canonical" if info["canonical"] else "non_canonical",
            "reason": info["reason"] or "",
        }

    # ── Move non-canonical files ────────────────────────────────────────────
    if not dry_run and archive_dir:
        archive_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        for fname, entry in result.items():
            if entry["status"] == "non_canonical":
                src = directory / fname
                if src.exists():
                    shutil.move(str(src), str(archive_dir / fname))
                    moved += 1

    return result


# ── Internal helpers ────────────────────────────────────────────────────────────


def _parse_all_files(files: list[Path], config: dict) -> dict:
    """Build internal per-file info dicts from *files*."""
    data: dict = {}
    for fpath in files:
        segments = _parse_filename_segments(fpath.name)
        app_key = _app_key(segments, config)
        info = {
            "path": fpath,
            "filename": fpath.name,
            "stem": fpath.stem,
            "segments": segments,
            "app_key": app_key,
            "submission_number": _detect_submission_in_segments(
                segments[config.get("group_segments", 2):], config
            ),
            "category": _detect_category_in_segments(
                segments[config.get("group_segments", 2):], config
            ),
            "version_score": _score_filename(fpath.name, config),
            "doc_identity": _build_doc_identity(segments, config),
            "canonical": True,
            "reason": "",
            "date_str": _extract_date(fpath.stem, config),
            "content_snippet": "",
        }
        data[fpath.name] = info
    return data


def _process_group(group_infos: list[dict], directory: Path, config: dict) -> None:
    """Canonicalize files within one application group.  Modifies *group_infos*."""
    if not group_infos:
        return

    # Separate submissions from non-submission categories
    subs = [fi for fi in group_infos if fi["submission_number"] is not None]
    non_subs = [fi for fi in group_infos if fi["submission_number"] is None]

    # ── Load content snippets for submission files ─────────────────────────
    if subs:
        _load_snippets(subs, directory)

    # ── Find effective max submission (skip corrupted) ─────────────────────
    if subs:
        sub_nums = sorted({fi["submission_number"] for fi in subs})
        max_sub = max(sub_nums)
        min_len = config.get("min_content_length", 800)
        effective_max = max_sub
        for sn in sorted(sub_nums, reverse=True):
            sn_files = [fi for fi in subs if fi["submission_number"] == sn and fi["canonical"]]
            if not sn_files:
                continue
            if any(len(fi["content_snippet"]) >= min_len for fi in sn_files):
                effective_max = sn
                break
            if sn == max_sub:
                for fi in sn_files:
                    fi["canonical"] = False
                    fi["reason"] = (
                        f"submission_{sn} file too small "
                        f"({len(fi['content_snippet'])} chars), likely corrupted"
                    )

        # ── Build lookup of higher-submission files ────────────────────────
        higher: dict[int, list[dict]] = defaultdict(list)
        for fi in subs:
            if fi["canonical"] and fi["content_snippet"]:
                higher[fi["submission_number"]].append(fi)

        # ── Supersede lower submissions via content similarity ─────────────
        threshold = config.get("content_match_threshold", 0.45)
        for fi in subs:
            if fi["submission_number"] >= effective_max:
                continue
            if not fi["canonical"]:
                continue

            best_sim = 0.0
            best_sub = 0
            for sn in sorted(higher):
                if sn <= fi["submission_number"]:
                    continue
                for hf in higher[sn]:
                    if not hf["canonical"]:
                        continue
                    sim = _pairwise_similarity(fi, hf, config)
                    if sim > best_sim:
                        best_sim = sim
                        best_sub = sn

            if best_sim >= threshold:
                fi["canonical"] = False
                fi["reason"] = f"superseded by submission_{best_sub} (content sim={best_sim:.2f})"
            else:
                fi["reason"] = "unique doc not in later submission"

    # Non-submission categories are kept canonical by default
    for fi in non_subs:
        if fi["canonical"] and not fi["reason"]:
            fi["reason"] = "non-submission category"


def _resolve_duplicates(
    dup_pairs: list[tuple[Path, Path]], file_data: dict, config: dict
) -> None:
    """From each duplicate pair, mark the lower-scored file as non-canonical."""
    clusters: dict[int, set[Path]] = {}
    # Group connected pairs into clusters
    path_to_cluster: dict[Path, int] = {}
    next_id = 0
    for a, b in dup_pairs:
        if a in path_to_cluster and b in path_to_cluster:
            cid_a = path_to_cluster[a]
            cid_b = path_to_cluster[b]
            if cid_a != cid_b:
                clusters[cid_a] |= clusters.pop(cid_b)
                for p in clusters[cid_a]:
                    path_to_cluster[p] = cid_a
        elif a in path_to_cluster:
            cid = path_to_cluster[a]
            clusters[cid].add(b)
            path_to_cluster[b] = cid
        elif b in path_to_cluster:
            cid = path_to_cluster[b]
            clusters[cid].add(a)
            path_to_cluster[a] = cid
        else:
            clusters[next_id] = {a, b}
            path_to_cluster[a] = next_id
            path_to_cluster[b] = next_id
            next_id += 1

    for cluster_paths in clusters.values():
        cluster_infos = [file_data[p.name] for p in cluster_paths if p.name in file_data]
        if len(cluster_infos) <= 1:
            continue
        _pick_best(cluster_infos, config)


def _pick_best(cluster_infos: list[dict], config: dict) -> None:
    """Mark all but the best-scored file in a cluster as non-canonical."""
    def _sort_key(fi: dict):
        return (
            fi.get("version_score", 0),
            fi.get("date_str") or "",
            len(fi.get("content_snippet", "")),
        )

    best = max(cluster_infos, key=_sort_key)
    for fi in cluster_infos:
        if fi is not best:
            fi["canonical"] = False
            fi["reason"] = "duplicate; kept version with higher score"


def _resolve_with_llm(file_data: dict, config: dict, llm_provider) -> None:
    """Use LLM to resolve ambiguous cross-submission matches.

    Only called on pairs where content similarity is borderline (0.25-0.55).
    Requires an LLM provider with a ``chat.completions.create`` interface.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for info in file_data.values():
        if info["canonical"] and info["submission_number"] is not None:
            groups[info["app_key"]].append(info)

    for _app_key, group in groups.items():
        max_sub = max(fi["submission_number"] for fi in group)
        max_files = [fi for fi in group if fi["submission_number"] == max_sub]
        lower_files = [fi for fi in group if fi["submission_number"] < max_sub]

        pairs: list[tuple[dict, dict, float]] = []
        for lf in lower_files:
            for mf in max_files:
                if not lf["content_snippet"] or not mf["content_snippet"]:
                    continue
                sim = SequenceMatcher(
                    None, lf["content_snippet"], mf["content_snippet"], autojunk=False
                ).ratio()
                if 0.25 <= sim <= 0.55:
                    pairs.append((lf, mf, sim))

        if not pairs:
            continue

        prompt = _build_llm_prompt(pairs)
        try:
            response = llm_provider.chat.completions.create(
                model=config.get("llm_model", "deepseek-chat"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            content = response.choices[0].message.content
            parsed = _parse_llm_response(str(content))
            if parsed is None:
                logger.warning(
                    "LLM canonicalizer: failed to parse response for app_key=%s",
                    _app_key,
                )
                continue
            results = parsed.get("pairs", [])
        except (AttributeError, Exception):
            logger.warning("LLM canonicalizer: request failed", exc_info=True)
            continue

        for i, result in enumerate(results):
            if i >= len(pairs):
                break
            lf, _mf, _sim = pairs[i]
            if result.get("same"):
                lf["canonical"] = False
                lf["reason"] = (
                    f"superseded by submission_{max_sub} (LLM confirmed match)"
                )


def _build_llm_prompt(pairs: list[tuple[dict, dict, float]]) -> str:
    lines = [
        "You are comparing grant application documents to determine which ones",
        "are the same document across different submission versions.",
        "For each pair below, answer YES if they are the same document",
        "(same form/section, possibly edited) or NO if they are different documents.",
        "",
        'Respond as JSON: {"pairs": [{"a": "<filename_a>", "b": "<filename_b>", "same": true/false}]}',
        "",
    ]
    for i, (lf, mf, sim) in enumerate(pairs):
        lines.append(f"--- Pair {i + 1} (similarity={sim:.2f}) ---")
        lines.append(f"File A ({lf['filename']}):")
        lines.append(lf["content_snippet"][:800])
        lines.append(f"File B ({mf['filename']}):")
        lines.append(mf["content_snippet"][:800])
        lines.append("")
    return "\n".join(lines)


# ── Low-level helpers ───────────────────────────────────────────────────────────


def _app_key(segments: list[str], config: dict) -> str:
    n = config.get("group_segments", 2)
    return "__".join(segments[:n]) if len(segments) >= n else segments[0]


def _detect_submission_in_segments(remaining: list[str], config: dict) -> int | None:
    best: int | None = None
    for seg in remaining:
        for rule in config.get("submission_segments", []):
            m = re.match(rule["pattern"], seg)
            if m:
                num = int(m.group(rule["number_group"]))
                if best is None or num > best:
                    best = num
    return best


def _detect_category_in_segments(remaining: list[str], config: dict) -> str | None:
    for seg in remaining:
        for pattern in config.get("category_segments", []):
            if re.match(pattern, seg, re.IGNORECASE):
                return seg
    return remaining[0] if remaining else None


def _build_doc_identity(segments: list[str], config: dict) -> str:
    n = config.get("group_segments", 2)
    remaining = segments[n:] if len(segments) > n else []
    identity = []
    for seg in remaining:
        if _detect_submission_in_segments([seg], config) is not None:
            continue
        identity.append(seg)
    if identity:
        return "__".join(identity)
    return segments[-1] if segments else ""


def _extract_date(stem: str, config: dict) -> str | None:
    m = re.search(config.get("date_pattern", r"(\d{4})-(\d{2})-(\d{2})"), stem)
    return m.group(0) if m else None


def _load_snippets(infos: list[dict], directory: Path, max_chars: int = 2000) -> None:
    for fi in infos:
        fpath = fi["path"]
        if not fpath.exists():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
            # Strip YAML frontmatter before comparison
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3:]
            text = _normalize_for_comparison(text)
            fi["content_snippet"] = text[:max_chars]
        except Exception:
            fi["content_snippet"] = ""


def _normalize_for_comparison(text: str) -> str:
    """Light normalization: lowercase, collapse whitespace, strip markdown chrome."""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[*_`#>|\-\[\]()!]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _name_similarity_jaccard(a: str, b: str) -> float:
    """Jaccard similarity on word tokens from two filenames/stems."""
    def _tokens(s: str) -> set[str]:
        return {t.lower().strip("_-") for t in s.split("_") if len(t) > 2}

    ta = _tokens(a)
    tb = _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _strip_version_suffixes(name: str, config: dict) -> str:
    """Strip version/draft/date markers from a document identity string."""
    result = name
    result = re.sub(r"_v\d+$", "", result, flags=re.IGNORECASE)
    result = re.sub(r"_?(?:final|FINAL|Final)$", "", result)
    result = re.sub(
        r"_(?:updated|corrected|submitted|SUBMITTED|signed|copy|Copy|edit|EDIT|"
        r"draft|DRAFT|prep|PREP|working|WORKING|todo|ToDo|notes|Notes|"
        r"blank|short|small)$",
        "",
        result,
    )
    result = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", result)
    result = result.strip("_")
    return result


def _pairwise_similarity(fi_a: dict, fi_b: dict, config: dict) -> float:
    """Best-of content + name similarity between two file infos."""
    content_sim = 0.0
    if fi_a.get("content_snippet") and fi_b.get("content_snippet"):
        content_sim = SequenceMatcher(
            None, fi_a["content_snippet"], fi_b["content_snippet"], autojunk=False
        ).ratio()
    name_sim = _name_similarity_jaccard(
        _strip_version_suffixes(fi_a.get("doc_identity", ""), config),
        _strip_version_suffixes(fi_b.get("doc_identity", ""), config),
    )
    return max(content_sim, name_sim)
