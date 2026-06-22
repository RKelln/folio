"""Synthetic, PII-free grant corpus generation.

This package builds a small, committable corpus of grant-style documents whose
*formatting* (tables, headings, reading order, form fields) mirrors real grant
archives, but whose *content* is entirely synthetic (Faker-generated, length
matched). The authored Markdown is the deterministic golden reference; binary
renders (PDF/DOCX/XLSX) are produced from it with all metadata stripped, and an
automated PII scan gates every file before it may be committed.
"""
