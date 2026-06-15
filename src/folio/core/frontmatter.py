"""YAML frontmatter parsing, generation, validation, and sanitization.

Canonical fields: funder, type, written, period, period_start, period_end,
grant_amount, priority, errors.

Field aliases are normalized (year_written → written, doc_type → type, etc.).
Type values are normalized (support material → support_material, etc.).
Period values are normalized to YYYY or YYYY-YYYY format.
"""
