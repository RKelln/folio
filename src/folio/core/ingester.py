"""One-off document ingestion.

Converts PDF/DOCX/XLSX to markdown (via configured converter),
applies deterministic cleanup, adds YAML frontmatter, and syncs
to the wiki raw directory.
"""
