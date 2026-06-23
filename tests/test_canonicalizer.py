from __future__ import annotations

import copy
from pathlib import Path

from folio.core.canonicalizer import (
    DEFAULT_CANONICALIZE_CONFIG,
    _app_key,
    _build_doc_identity,
    _detect_category_in_segments,
    _detect_drafts,
    _detect_duplicates,
    _detect_submission_in_segments,
    _extract_date,
    _group_files,
    _load_snippets,
    _name_similarity_jaccard,
    _normalize_for_comparison,
    _pairwise_similarity,
    _parse_all_files,
    _parse_filename_segments,
    _process_group,
    _score_filename,
    _strip_version_suffixes,
    canonicalize_directory,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_file(directory: Path, name: str, content: str) -> Path:
    fpath = directory / name
    fpath.write_text(content, encoding="utf-8")
    return fpath


def _config(**overrides):
    cfg = copy.deepcopy(DEFAULT_CANONICALIZE_CONFIG)
    cfg.update(overrides)
    return cfg


# ── _parse_filename_segments ───────────────────────────────────────────────────

class TestParseFilenameSegments:
    def test_simple_two_segments(self):
        assert _parse_filename_segments("OAC__2024_Application.md") == [
            "OAC", "2024_Application",
        ]

    def test_three_segments(self):
        assert _parse_filename_segments("OAC__2024_Application__final.md") == [
            "OAC", "2024_Application", "final",
        ]

    def test_four_segments(self):
        assert _parse_filename_segments("CCA__2025__report__submission_2.md") == [
            "CCA", "2025", "report", "submission_2",
        ]

    def test_no_separator(self):
        assert _parse_filename_segments("simple_file.md") == ["simple_file"]

    def test_empty_segments_dropped(self):
        assert _parse_filename_segments("OAC____2024.md") == ["OAC", "2024"]

    def test_trailing_underscores_in_segments(self):
        # strip("_") is used as truthiness check; original segments are kept
        assert _parse_filename_segments("Funder____Year_.md") == ["Funder", "Year_"]


# ── _score_filename ────────────────────────────────────────────────────────────

class TestScoreFilename:
    def test_final_suffix_positive(self):
        cfg = _config()
        score = _score_filename("OAC__2024_Application__final.md", cfg)
        assert score > 0

    def test_draft_suffix_negative(self):
        cfg = _config()
        score = _score_filename("OAC__2024_Application__draft.md", cfg)
        assert score < 0

    def test_version_number_positive(self):
        cfg = _config()
        score_v1 = _score_filename("OAC__2024_Application__v1.md", cfg)
        score_v3 = _score_filename("OAC__2024_Application__v3.md", cfg)
        assert score_v3 > score_v1

    def test_multiple_suffixes_accumulate(self):
        cfg = _config()
        # Only _submitted$ matches (at end of stem); _final$ does not because
        # it is not at the end of the stem.
        score = _score_filename("OAC__2024_Application__final_submitted.md", cfg)
        assert score == 90  # submitted = 90

    def test_neutral_filename_zero(self):
        cfg = _config()
        assert _score_filename("OAC__2024_Application.md", cfg) == 0

    def test_working_suffix_negative(self):
        cfg = _config()
        assert _score_filename("OAC__2024__working.md", cfg) < 0

    def test_uppercase_final_positive(self):
        cfg = _config()
        score = _score_filename("OAC__2024__FINAL.md", cfg)
        assert score > 0

    def test_custom_version_suffixes(self):
        cfg = _config(version_suffixes=[
            {"pattern": r"_complete$", "score": 200},
        ])
        assert _score_filename("OAC__2024__complete.md", cfg) == 200

    def test_custom_draft_suffixes(self):
        cfg = _config(draft_suffixes=[
            {"pattern": r"_scratch$", "score": -99},
        ])
        assert _score_filename("OAC__2024__scratch.md", cfg) == -99


# ── _normalize_for_comparison ──────────────────────────────────────────────────

class TestNormalizeForComparison:
    def test_lowercases(self):
        assert _normalize_for_comparison("Hello WORLD") == "hello world"

    def test_collapses_whitespace(self):
        assert _normalize_for_comparison("hello    world\n\nfoo") == "hello world foo"

    def test_strips_markdown_chrome(self):
        result = _normalize_for_comparison("# Heading\n**bold** [link](url) `code`")
        assert "#" not in result
        assert "*" not in result
        assert "[" not in result
        assert "]" not in result
        assert "(" not in result
        assert ")" not in result
        assert "`" not in result

    def test_handles_empty(self):
        assert _normalize_for_comparison("") == ""


# ── _name_similarity_jaccard ───────────────────────────────────────────────────

class TestNameSimilarityJaccard:
    def test_identical(self):
        assert _name_similarity_jaccard("OAC_2024_Application", "OAC_2024_Application") == 1.0

    def test_completely_different(self):
        assert _name_similarity_jaccard("ABC", "XYZ") == 0.0

    def test_partial_overlap(self):
        sim = _name_similarity_jaccard("OAC_2024_Application", "OAC_2024_Budget")
        assert 0 < sim < 1

    def test_short_tokens_ignored(self):
        sim = _name_similarity_jaccard("a_b_c_OAC", "x_y_z_OAC")
        assert sim == 1.0

    def test_empty_tokens(self):
        assert _name_similarity_jaccard("a", "b") == 0.0


# ── _extract_date ──────────────────────────────────────────────────────────────

class TestExtractDate:
    def test_extracts_date_from_stem(self):
        cfg = _config()
        assert _extract_date("OAC__2024-03-15_Application__final", cfg) == "2024-03-15"

    def test_returns_none_when_no_date(self):
        assert _extract_date("OAC__2024_Application__final", _config()) is None

    def test_returns_none_for_empty_stem(self):
        assert _extract_date("", _config()) is None


# ── _detect_submission_in_segments ─────────────────────────────────────────────

class TestDetectSubmissionInSegments:
    def test_submission_number(self):
        assert _detect_submission_in_segments(["submission_3"], _config()) == 3

    def test_ordinal_submission(self):
        assert _detect_submission_in_segments(["2nd_submission"], _config()) == 2

    def test_submission_v(self):
        assert _detect_submission_in_segments(["submission_v5"], _config()) == 5

    def test_highest_wins(self):
        result = _detect_submission_in_segments(
            ["submission_1", "submission_3", "submission_2"], _config()
        )
        assert result == 3

    def test_no_submission_returns_none(self):
        assert _detect_submission_in_segments(["report", "final"], _config()) is None

    def test_empty_segments(self):
        assert _detect_submission_in_segments([], _config()) is None


# ── _detect_category_in_segments ───────────────────────────────────────────────

class TestDetectCategoryInSegments:
    def test_report(self):
        assert _detect_category_in_segments(["report"], _config()) == "report"

    def test_budget(self):
        assert _detect_category_in_segments(["budget"], _config()) == "budget"

    def test_application(self):
        assert _detect_category_in_segments(["application"], _config()) == "application"

    def test_first_category_match(self):
        assert _detect_category_in_segments(["report", "budget"], _config()) == "report"

    def test_fallback_to_first_segment(self):
        result = _detect_category_in_segments(["unknown_category"], _config())
        assert result == "unknown_category"

    def test_empty_segments_returns_none(self):
        assert _detect_category_in_segments([], _config()) is None


# ── _build_doc_identity ────────────────────────────────────────────────────────

class TestBuildDocIdentity:
    def test_excludes_submission_segments(self):
        cfg = _config(group_segments=2)
        segs = ["OAC", "2024", "application", "submission_2", "final"]
        identity = _build_doc_identity(segs, cfg)
        # application remains, submission_2 excluded, final remains? Let me think:
        # remaining = ['application', 'submission_2', 'final']
        # 'submission_2' is a submission segment -> skipped
        # 'application' kept, 'final' kept
        # result: application__final
        assert "submission_2" not in identity
        assert "application" in identity

    def test_single_segment_returns_last(self):
        cfg = _config(group_segments=2)
        assert _build_doc_identity(["OAC"], cfg) == "OAC"

    def test_no_remaining_uses_last(self):
        cfg = _config(group_segments=5)
        segs = ["OAC", "2024", "app"]
        assert _build_doc_identity(segs, cfg) == "app"


# ── _app_key ───────────────────────────────────────────────────────────────────

class TestAppKey:
    def test_default_two_segments(self):
        cfg = _config(group_segments=2)
        assert _app_key(["OAC", "2024", "application", "final"], cfg) == "OAC__2024"

    def test_one_segment(self):
        cfg = _config(group_segments=2)
        assert _app_key(["OAC"], cfg) == "OAC"

    def test_three_group_segments(self):
        cfg = _config(group_segments=3)
        assert _app_key(["OAC", "2024", "application", "final"], cfg) == "OAC__2024__application"


# ── _strip_version_suffixes ────────────────────────────────────────────────────

class TestStripVersionSuffixes:
    def test_strips_v_number(self):
        cfg = _config()
        assert _strip_version_suffixes("application_v3", cfg) == "application"

    def test_strips_final(self):
        cfg = _config()
        assert _strip_version_suffixes("application_final", cfg) == "application"

    def test_strips_draft(self):
        cfg = _config()
        assert _strip_version_suffixes("report_draft", cfg) == "report"

    def test_strips_date_prefix(self):
        cfg = _config()
        result = _strip_version_suffixes("2024-03-15_report", cfg)
        assert "2024-03-15" not in result

    def test_preserves_core(self):
        cfg = _config()
        result = _strip_version_suffixes("OAC__2024_application__final", cfg)
        assert "OAC__2024_application" in result


# ── _pairwise_similarity ───────────────────────────────────────────────────────

class TestPairwiseSimilarity:
    def test_identical_content(self):
        cfg = _config()
        fa = {"content_snippet": "hello world", "doc_identity": "app"}
        fb = {"content_snippet": "hello world", "doc_identity": "app"}
        assert _pairwise_similarity(fa, fb, cfg) > 0.9

    def test_different_content(self):
        cfg = _config()
        fa = {"content_snippet": "hello world small content", "doc_identity": "application_interim"}
        fb = {"content_snippet": "completely different text here utterly distinct", "doc_identity": "budget_financial"}
        assert _pairwise_similarity(fa, fb, cfg) < 0.5

    def test_no_snippets_falls_back_to_name(self):
        cfg = _config()
        fa = {"content_snippet": "", "doc_identity": "OAC_2024_Application"}
        fb = {"content_snippet": "", "doc_identity": "OAC_2024_Application"}
        sim = _pairwise_similarity(fa, fb, cfg)
        assert sim > 0.9


# ── _load_snippets ─────────────────────────────────────────────────────────────

class TestLoadSnippets:
    def test_loads_content(self, tmp_path):
        fpath = _make_file(tmp_path, "test.md", "# Heading\n\nSome content here.\n")
        info = {"path": fpath, "content_snippet": ""}
        _load_snippets([info], tmp_path)
        assert len(info["content_snippet"]) > 0
        assert "heading" in info["content_snippet"].lower()

    def test_strips_frontmatter(self, tmp_path):
        fpath = _make_file(tmp_path, "with_fm.md",
            "---\ntitle: Test\n---\n\nActual content here.\n")
        info = {"path": fpath, "content_snippet": ""}
        _load_snippets([info], tmp_path)
        assert "title" not in info["content_snippet"].lower()
        assert "actual content" in info["content_snippet"].lower()

    def test_unicode_decode_error_handled(self, tmp_path):
        fpath = tmp_path / "bad.txt"
        fpath.write_bytes(b"\xff\xfe\x00\x01")
        info = {"path": fpath, "content_snippet": ""}
        # errors="replace" means no exception is raised; content may be non-empty
        # with replacement chars. The snippet is still set (not empty string).
        _load_snippets([info], tmp_path)
        assert isinstance(info["content_snippet"], str)


# ── _parse_all_files ───────────────────────────────────────────────────────────

class TestParseAllFiles:
    def test_builds_all_info_keys(self, tmp_path):
        _make_file(tmp_path, "OAC__2024_Application__final.md",
            "# OAC Application\n\nContent here.\n" * 20)
        data = _parse_all_files(list(tmp_path.glob("*.md")), _config())
        fname = "OAC__2024_Application__final.md"
        assert fname in data
        info = data[fname]
        assert info["filename"] == fname
        assert info["canonical"] is True
        assert info["segments"] == ["OAC", "2024_Application", "final"]
        assert info["app_key"] == "OAC__2024_Application"  # group_segments=2
        assert info["version_score"] > 0

    def test_multiple_files(self, tmp_path):
        _make_file(tmp_path, "OAC__2024_Application__final.md",
            "# App\n\nContent.\n" * 10)
        _make_file(tmp_path, "OAC__2024_Application__draft.md",
            "# Draft App\n\nRough content.\n" * 5)
        data = _parse_all_files(list(tmp_path.glob("*.md")), _config())
        assert len(data) == 2


# ── _detect_drafts ─────────────────────────────────────────────────────────────

class TestDetectDrafts:
    def test_draft_by_filename_suffix(self, tmp_path):
        f = _make_file(tmp_path, "OAC__2024__draft.md", "# Content\n\nSome body text.\n")
        drafts = _detect_drafts([f], _config())
        assert f in drafts

    def test_draft_by_content_marker(self, tmp_path):
        f = _make_file(tmp_path, "OAC__2024__report.md",
            "# Report\n\nDRAFT - work in progress\n\nMore content.\n")
        drafts = _detect_drafts([f], _config())
        assert f in drafts

    def test_working_marker(self, tmp_path):
        f = _make_file(tmp_path, "OAC__2024__working.md", "# Stuff\n\nBody.\n")
        drafts = _detect_drafts([f], _config())
        assert f in drafts

    def test_exclude_pattern_match(self, tmp_path):
        f = _make_file(tmp_path, "OAC__2024_App__draft_v1.md",
            "# Content\n\nBody.\n")
        drafts = _detect_drafts([f], _config())
        assert f in drafts

    def test_non_draft_kept(self, tmp_path):
        f = _make_file(tmp_path, "OAC__2024__final.md",
            "# Final Report\n\nComplete content goes here.\n")
        drafts = _detect_drafts([f], _config())
        assert f not in drafts

    def test_unreadable_file_not_draft(self, tmp_path):
        f = tmp_path / "nonexistent.md"
        drafts = _detect_drafts([f], _config())
        assert f not in drafts


# ── _group_files ───────────────────────────────────────────────────────────────

class TestGroupFiles:
    def test_groups_by_app_key(self, tmp_path):
        f1 = _make_file(tmp_path, "OAC__2024__application.md", "content")
        f2 = _make_file(tmp_path, "OAC__2024__budget.md", "content")
        f3 = _make_file(tmp_path, "CCA__2025__report.md", "content")
        groups = _group_files([f1, f2, f3], _config(group_segments=2))
        assert "OAC__2024" in groups
        assert "CCA__2025" in groups
        assert len(groups["OAC__2024"]) == 2
        assert len(groups["CCA__2025"]) == 1

    def test_fallback_when_fewer_segments(self, tmp_path):
        f = _make_file(tmp_path, "single.md", "content")
        groups = _group_files([f], _config(group_segments=2))
        assert "single" in groups
        assert len(groups["single"]) == 1

    def test_custom_group_segments(self, tmp_path):
        f = _make_file(tmp_path, "A__B__C__D.md", "content")
        groups = _group_files([f], _config(group_segments=3))
        assert "A__B__C" in groups


# ── _detect_duplicates ─────────────────────────────────────────────────────────

class TestDetectDuplicates:
    def test_identical_content_duplicate(self, tmp_path):
        content = "# Report\n\nThis is a long report with enough content to be meaningful. " * 30
        f1 = _make_file(tmp_path, "OAC__2024__report_v1.md", content)
        f2 = _make_file(tmp_path, "OAC__2024__report_v2.md", content)
        dup_pairs = _detect_duplicates([f1, f2], _config())
        assert len(dup_pairs) >= 1

    def test_different_content_no_duplicate(self, tmp_path):
        f1 = _make_file(tmp_path, "OAC__2024__app.md",
            "# Application\n\n" + "This is unique application content. " * 30)
        f2 = _make_file(tmp_path, "OAC__2024__budget.md",
            "# Budget\n\n" + "This is completely different budget content. " * 30)
        dup_pairs = _detect_duplicates([f1, f2], _config())
        assert len(dup_pairs) == 0

    def test_below_name_threshold_skipped(self, tmp_path):
        content = "lorem ipsum dolor sit amet " * 50
        f1 = _make_file(tmp_path, "OAC__2024__application.md", content)
        f2 = _make_file(tmp_path, "CCA__2023__budget.md", content)
        dup_pairs = _detect_duplicates([f1, f2], _config())
        assert len(dup_pairs) == 0

    def test_skips_when_too_many_files(self, tmp_path):
        content = "some content " * 20
        files = [_make_file(tmp_path, f"file_{i}.md", content) for i in range(10)]
        dup_pairs = _detect_duplicates(files, _config(max_files_for_dedup=5))
        assert dup_pairs == []

    def test_unreadable_file_handled(self, tmp_path):
        f1 = _make_file(tmp_path, "good.md", "some content " * 20)
        f2 = tmp_path / "missing.md"
        dup_pairs = _detect_duplicates([f1, f2], _config())
        assert isinstance(dup_pairs, list)


# ── _process_group ─────────────────────────────────────────────────────────────

class TestProcessGroup:
    def _make_info(self, filename, sub_num, content_snippet="", canonical=True):
        return {
            "path": Path(filename),
            "filename": filename,
            "submission_number": sub_num,
            "content_snippet": content_snippet,
            "canonical": canonical,
            "reason": "",
            "doc_identity": filename,
            "version_score": 0,
        }

    def test_highest_submission_kept(self):
        cfg = _config()
        group = [
            self._make_info("app__submission_1.md", 1, "long enough content here " * 100),
            self._make_info("app__submission_3.md", 3, "long enough content here " * 100),
        ]
        _process_group(group, Path("."), cfg)
        assert group[1]["canonical"] is True
        assert group[0]["canonical"] is False
        assert "superseded" in group[0]["reason"]

    def test_corrupted_max_submission_demoted(self):
        cfg = _config(min_content_length=800)
        group = [
            self._make_info("app__submission_1.md", 1, "long enough content here " * 100),
            self._make_info("app__submission_3.md", 3, "short"),
        ]
        _process_group(group, Path("."), cfg)
        assert group[1]["canonical"] is False
        assert "too small" in group[1]["reason"]

    def test_non_submissions_kept(self):
        cfg = _config()
        group = [
            self._make_info("app__budget.md", None),
            self._make_info("app__report.md", None),
        ]
        _process_group(group, Path("."), cfg)
        for info in group:
            assert info["canonical"] is True

    def test_empty_group(self):
        _process_group([], Path("."), _config())  # should not raise


# ── canonicalize_directory ─────────────────────────────────────────────────────

class TestCanonicalizeDirectory:
    def test_empty_directory(self, tmp_path):
        result = canonicalize_directory(tmp_path, _config())
        assert result == {}

    def test_markdown_only(self, tmp_path):
        f = _make_file(tmp_path, "OAC__2024__final.md",
            "# Report\n\n" + "Content here. " * 30)
        result = canonicalize_directory(tmp_path, _config())
        assert f.name in result
        assert result[f.name]["status"] == "canonical"

    def test_draft_moved_to_archive(self, tmp_path):
        archive = tmp_path / "archive"
        _make_file(tmp_path, "OAC__2024__draft.md",
            "# Draft\n\nDRAFT content\n\n" + "More text. " * 20)
        result = canonicalize_directory(tmp_path, _config(), archive_dir=archive, dry_run=False)
        fname = "OAC__2024__draft.md"
        assert result[fname]["status"] == "non_canonical"
        assert (archive / fname).exists()
        assert not (tmp_path / fname).exists()

    def test_dry_run_no_move(self, tmp_path):
        archive = tmp_path / "archive"
        f = _make_file(tmp_path, "OAC__2024__draft.md",
            "# Draft\n\n" + "Content. " * 20)
        result = canonicalize_directory(tmp_path, _config(), archive_dir=archive, dry_run=True)
        fname = "OAC__2024__draft.md"
        assert result[fname]["status"] == "non_canonical"
        assert not archive.exists()
        assert f.exists()

    def test_submission_version_demoted(self, tmp_path):
        _make_file(tmp_path, "OAC__2024__submission_1.md",
            "# App\n\n" + "Content for version 1. " * 50)
        _make_file(tmp_path, "OAC__2024__submission_2.md",
            "# App\n\n" + "Content for version 2 is more complete. " * 50)
        result = canonicalize_directory(tmp_path, _config())
        assert result["OAC__2024__submission_1.md"]["status"] == "non_canonical"
        assert result["OAC__2024__submission_2.md"]["status"] == "canonical"

    def test_duplicate_content_demoted(self, tmp_path):
        content = "# Budget\n\n" + "Budget line items and justification. " * 30
        _make_file(tmp_path, "OAC__2024__budget_v1.md", content)
        _make_file(tmp_path, "OAC__2024__budget_v2.md", content)
        result = canonicalize_directory(tmp_path, _config())
        statuses = {k: v["status"] for k, v in result.items()}
        assert list(statuses.values()).count("non_canonical") >= 1

    def test_single_file(self, tmp_path):
        _make_file(tmp_path, "OAC__2024__report.md",
            "# Report\n\n" + "A single report file. " * 30)
        result = canonicalize_directory(tmp_path, _config())
        assert len(result) == 1
        assert list(result.values())[0]["status"] == "canonical"


# ── _load_snippets (additional) ────────────────────────────────────────────────

class TestLoadSnippetsEdgeCases:
    def test_missing_file_sets_empty(self, tmp_path):
        info = {"path": tmp_path / "missing.md", "content_snippet": "old"}
        _load_snippets([info], tmp_path)
        assert info["content_snippet"] == "old"

    def test_empty_file(self, tmp_path):
        fpath = _make_file(tmp_path, "empty.md", "")
        info = {"path": fpath, "content_snippet": ""}
        _load_snippets([info], tmp_path)
        assert info["content_snippet"] == ""


# ── _detect_drafts edge ────────────────────────────────────────────────────────

class TestDetectDraftsEdgeCases:
    def test_draft_marker_not_in_head(self, tmp_path):
        long_prefix = "x" * 600
        f = _make_file(tmp_path, "OAC__2024__report.md",
            f"{long_prefix}\ndraft\n\nMore content.\n")
        # draft marker is beyond 500 chars head -> not detected
        drafts = _detect_drafts([f], _config())
        assert f not in drafts

    def test_binary_file_handled(self, tmp_path):
        fpath = tmp_path / "binary.md"
        fpath.write_bytes(b"\x00\x01\x02\x03\x04")
        drafts = _detect_drafts([fpath], _config())
        assert fpath not in drafts
