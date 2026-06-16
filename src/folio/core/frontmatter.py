"""YAML frontmatter parsing, generation, updating, and sanitization for folio.

Canonical fields: funder, type, written, period, period_start, period_end,
grant_amount, priority, errors.

Field aliases are normalized (year_written → written, doc_type → type, etc.).
Type values are normalized (support material → support_material, etc.).
Period values are normalized to YYYY or YYYY–YYYY format.
"""

from __future__ import annotations

import datetime
import re

import yaml

YEAR_FIELDS = ['written', 'period', 'period_start']


# ── Parse ──────────────────────────────────────────────────────────────────────

def extract_year(value) -> int | None:
    """Extract a year integer from a frontmatter value.

    Handles: 2024, "2024", "2025-2027", "2025–2027", "2025-07-10",
    datetime.date(2017, 7, 12), datetime.datetime(2024, 1, 15, 10, 30).
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.year
    if isinstance(value, str):
        m = re.search(r'\b(20\d{2})\b', value)
        if m:
            return int(m.group(1))
    return None


def parse_frontmatter(text: str) -> tuple[dict | None, str]:
    """Parse YAML frontmatter from a markdown string.

    Returns:
        Tuple of (parsed_dict_or_None, body_text).
        If no frontmatter or invalid YAML, dict is None and the full
        text is returned as body.
    """
    if not text.startswith('---'):
        return None, text
    end_idx = text.find('---', 3)
    if end_idx == -1:
        return None, text
    fm_text = text[3:end_idx].strip()
    body = text[end_idx + 3:].strip()
    try:
        fm = yaml.safe_load(fm_text)
        if isinstance(fm, dict):
            return fm, body
    except yaml.YAMLError:
        pass
    return None, body


def get_file_year(fm: dict | None, field: str = 'written') -> int | None:
    """Extract the year from frontmatter using the configured field.

    Falls back to alternative fields (written, period, period_start)
    if the primary field is missing.
    """
    if fm is None:
        return None
    year = extract_year(fm.get(field))
    if year:
        return year
    for alt in ['written', 'period', 'period_start']:
        if alt == field:
            continue
        year = extract_year(fm.get(alt))
        if year:
            return year
    return None


# ── Generate ───────────────────────────────────────────────────────────────────

def dict_to_frontmatter(**fields) -> str:
    """Generate YAML frontmatter from key-value pairs.

    String values are always quoted. List values are joined with commas
    and quoted. Int/float values are left unquoted.

    Example:
        >>> dict_to_frontmatter(funder="OAC", type=["proposal", "report"], written=2024)
        '---\\nfunder: "OAC"\\ntype: "proposal, report"\\nwritten: 2024\\n---'
    """
    fm = ['---']
    for key, value in fields.items():
        if value is None or value == '':
            continue
        if isinstance(value, list):
            fm.append(f'{key}: "{", ".join(value)}"')
        elif isinstance(value, str):
            fm.append(f'{key}: "{value}"')
        else:
            fm.append(f'{key}: {value}')
    fm.append('---')
    return '\n'.join(fm)


# ── Update ─────────────────────────────────────────────────────────────────────

def update_frontmatter(content: str, **fields) -> str:
    """Update or add fields in YAML frontmatter.

    Parses existing YAML frontmatter, updates the dict with new fields,
    and serializes back to YAML. Correctly handles quoted values,
    multi-line strings, and comments.

    Example:
        >>> update_frontmatter(doc, priority=2)
        >>> update_frontmatter(doc, priority=1, status="final")
    """
    if not fields:
        return content

    if not content.startswith('---'):
        fm_block = '---\n' + yaml.safe_dump(fields, default_flow_style=False, allow_unicode=True, sort_keys=False).strip() + '\n---\n\n'
        return fm_block + content

    end_idx = content.find('---', 3)
    if end_idx == -1:
        return content

    fm_text = content[3:end_idx].strip()
    body = content[end_idx + 3:].lstrip('\n')

    try:
        fm_dict = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm_dict = {}

    fm_dict.update(fields)

    fm_yaml = yaml.safe_dump(fm_dict, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()

    return f'---\n{fm_yaml}\n---\n{body}'


# ── Strip / sanitize ───────────────────────────────────────────────────────────

def strip_existing_frontmatter(text: str) -> str:
    """Remove any frontmatter from a markdown string.

    Handles both markdown code-fenced frontmatter (```yaml ... ```)
    and bare --- delimited frontmatter.
    """
    lines = text.split('\n')
    result = []
    in_frontmatter = False
    in_code_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped in ('---', '...'):
            in_frontmatter = not in_frontmatter
            continue
        if stripped.startswith('```'):
            in_code_fence = not in_code_fence
            continue
        if in_frontmatter or in_code_fence:
            continue
        result.append(line)
    return '\n'.join(result)


def sanitize_frontmatter(text: str) -> str:
    """Clean up frontmatter from various input formats.

    Handles:
      - Code-fenced with --- delimiters: ```yaml\\n---\\n...\\n---\\n```
      - Code-fenced bare YAML: ```yaml\\nfunder: OAC\\n...```
      - Bare --- delimited: ---\\n...\\n---
      - Stray --- followed by markdown (treated as non-frontmatter)
      - No frontmatter at all (returned as-is)
      - Field name normalization (year_written → written, etc.)
    """
    text = text.strip()

    # Normalize frontmatter field name aliases early
    text = normalize_field_aliases(text)

    # Strip code fences: ```yaml ... ``` → bare content
    text = re.sub(r'^```(?:yaml|yml)?\s*\n', '', text, count=1)
    text = re.sub(r'\n```\s*', '\n', text, count=1)
    # Belt-and-suspenders: orphaned ``` on its own line after closing ---
    text = re.sub(r'---\n```\s*(\n|$)', r'---\1', text)
    text = text.strip()

    # Try standard --- delimited frontmatter first
    fm, body = parse_frontmatter(text)
    if fm is not None:
        end_idx = text.find('---', 3)
        original_fm = '\n'.join(text.split('\n')[1:end_idx]).strip()
        # Normalize field values within frontmatter block only
        original_fm = normalize_field_values(original_fm)
        out = ['---', original_fm, '---', '']
        if body.strip():
            out.append(body.strip())
        return '\n'.join(out) + '\n'

    # No --- delimiters — try to extract YAML key: value pairs from the top
    lines = text.split('\n')
    yaml_lines = []
    for line in lines:
        stripped = line.strip()
        if ':' in stripped and not stripped.startswith('#') and not stripped.startswith('|'):
            yaml_lines.append(line)
        elif not stripped:
            yaml_lines.append(line)
        else:
            break
    if yaml_lines:
        try:
            parsed = yaml.safe_load('\n'.join(yaml_lines))
            if isinstance(parsed, dict):
                out = ['---']
                for k, v in parsed.items():
                    if isinstance(v, str):
                        out.append(f'{k}: "{v}"')
                    elif isinstance(v, list):
                        out.append(f'{k}: "{", ".join(v)}"')
                    else:
                        out.append(f'{k}: {v}')
                out.append('---')
                out.append('')
                body = '\n'.join(lines[len(yaml_lines):]).strip()
                if body:
                    out.append(body)
                return '\n'.join(out) + '\n'
        except yaml.YAMLError:
            pass

    return text + '\n'


# ── Field alias normalization ───────────────────────────────────────────────────

# Map of non-standard field names → canonical names.
_FIELD_ALIASES = {
    'year_written': 'written',
    'year': 'written',
    'status': 'type',
    'doc_type': 'type',
    'document_type': 'type',
}

# Map of non-standard type values → canonical values.
_TYPE_VALUES = {
    'support material': 'support_material',
    'support materials': 'support_material',
    'activity list': 'activity_list',
    'activity lists': 'activity_list',
    'staff board': 'staff_board',
    'meeting notes': 'meeting_notes',
    'financial_form': 'budget',
    'incorporation': 'agreement',
    'letter of agreement': 'agreement',
    'acceptance': 'notification',
    'approval': 'notification',
    'results': 'notification',
    'result': 'notification',
    'email correspondence': 'email',
}


def normalize_field_aliases(fm_text: str) -> str:
    """Replace known non-standard field names with canonical equivalents."""
    for alias, canonical in _FIELD_ALIASES.items():
        fm_text = re.sub(rf'^{alias}:', f'{canonical}:', fm_text, flags=re.MULTILINE)
    return fm_text


def normalize_field_values(fm_text: str) -> str:
    """Fix common field value formatting issues in frontmatter.

    Handles:
      - Empty-quoted values (grant_amount: "") → remove field
      - Non-standard type values → canonical equivalents
      - Messy period values → canonical YYYY or YYYY–YYYY
    """
    # Remove fields with empty values: key: "" or key: '' or key: (nothing)
    fm_text = re.sub(r'(?m)^\w+:\s*["\']?\s*["\']?\s*$', '', fm_text)

    # Collapse blank lines left by field removal
    fm_text = re.sub(r'\n{2,}', '\n', fm_text)

    # Normalize type values
    for variant, canonical in _TYPE_VALUES.items():
        fm_text = re.sub(
            rf'(?m)^(type:\s*).*{re.escape(variant)}.*$',
            rf'\1{canonical}',
            fm_text,
        )

    # Normalize period values to canonical YYYY or YYYY–YYYY
    fm_text = _normalize_period_values(fm_text)

    return fm_text


def _normalize_period_values(fm_text: str) -> str:
    """Convert messy period strings to canonical year format."""

    def _clean_period(match):
        key = match.group(1)
        value = match.group(2).strip().strip('"').strip("'")
        years = _extract_years(value)
        if not years:
            return match.group(0)

        min_y, max_y = min(years), max(years)
        if min_y == max_y:
            return f'{key}: {min_y}'
        return f'{key}: {min_y}–{max_y}'

    return re.sub(
        r'(?m)^(period):\s*(.+)$',
        _clean_period,
        fm_text,
    )


def _extract_years(text: str) -> list[int]:
    """Extract 4-digit years (2000-2099) from a string."""
    years = []
    for m in re.finditer(r'\b(20\d{2})\b', text):
        years.append(int(m.group(1)))
    return years


def apply_frontmatter(text: str, frontmatter: str) -> str:
    """Strip any existing frontmatter and insert canonical version at the top."""
    text = strip_existing_frontmatter(text)
    return f'{frontmatter}\n\n{text.strip()}\n'


# ── Smoke tests ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    fm, body = parse_frontmatter('---\nwritten: 2024\nfunder: OAC\n---\nBody')
    ok = (fm == {'written': 2024, 'funder': 'OAC'} and body == 'Body')
    print('OK' if ok else 'FAIL')
