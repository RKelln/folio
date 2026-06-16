"""Shared error and status types used across all pipeline stages."""

from __future__ import annotations

from enum import Enum


class FileStatus(str, Enum):
    """Status of a file in the pipeline."""
    OK = "ok"
    PENDING = "pending"                    # Not yet processed
    SKIPPED_GUIDELINES = "skipped_guidelines"
    SKIPPED_CORRUPTED = "skipped_corrupted"
    SKIPPED_TOO_SMALL = "skipped_too_small"
    SKIPPED_CV = "skipped_cv"
    SKIPPED_EMAIL = "skipped_email"
    SKIPPED_DRAFT = "skipped_draft"
    SKIPPED_NON_CANONICAL = "skipped_non_canonical"
    SKIPPED_UNDERSIZED = "skipped_undersized"
    ERROR_CONVERSION = "error_conversion"
    ERROR_LLM = "error_llm"
    ERROR_PARSE = "error_parse"


class ProcessingTier(str, Enum):
    """Classification tier for LLM re-authoring."""
    SKIP = "skip"
    MINIMAL = "minimal"
    LIGHT = "light"
    FULL = "full"
