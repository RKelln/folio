"""LLM re-authoring engine.

Tiered prompts (full/light/minimal) sent to an LLM provider to produce
clean archival markdown with YAML frontmatter. Supports concurrency,
checkpoint/resume, and cost tracking.
"""
