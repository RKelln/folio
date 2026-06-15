"""Version detection and deduplication.

Identifies non-canonical versions (drafts, superseded submissions,
near-duplicates) using filename pattern scoring and content similarity.
Optionally uses LLM for ambiguous cases.
"""
