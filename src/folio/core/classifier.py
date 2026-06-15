"""File quality classification and tier assignment.

Scores files by content quality (form chrome, corruption, draft markers,
content density) and assigns processing tiers: skip, minimal, light, full.
Uses configurable rules from the project or classification config.
"""
