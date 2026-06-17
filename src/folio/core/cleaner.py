"""Deterministic markdown cleanup.

Strips base64 images, normalizes whitespace, removes form chrome,
promotes bold text to headings, fixes text corruption, decodes HTML entities.
"""

from __future__ import annotations

import re
from pathlib import Path

from tqdm import tqdm

_BASE64_IMAGE = re.compile(r'!\[Image\]\(data:image/\w+;base64,[A-Za-z0-9+/=]+\)')
_HTML_COMMENT_IMAGE = re.compile(r'<!--\s*image\s*-->', re.IGNORECASE)
_STANDALONE_IMAGE_PLACEHOLDER = re.compile(r'^\[IMAGE\]\s*$', re.MULTILINE)
_MULTI_BLANK = re.compile(r'\n{3,}')
_BOLD_TO_HEADING = re.compile(r'^\*\*([^*]+)\*\*\s*$')
_CHECKBOX_WIDGETS = re.compile(r'^\[[ xX]\]\s*', re.MULTILINE)
_UNICODE_CHECKBOX = re.compile(r'^[☐☑]\s*', re.MULTILINE)
_FILE_METADATA = re.compile(r'^Total\s+Files?\s*:\s*\d+\s*$', re.IGNORECASE | re.MULTILINE)
_BARE_DIGIT_LINE = re.compile(r'^\d{1,4}\s*$')
_SINGLE_CHAR_ALPHA_LINE = re.compile(r'^[a-zA-Z]\s*$')
_SPLIT_WORD_GAP = re.compile(r'\b([a-zA-Z]{1,3}) ([a-zA-Z]{1,3})\b')
_FORM_LABEL_ONLY = re.compile(
    r'^(?:'
    r'(?:Applicant\s+)?Organization\s*(?:or\s+Collective\s+Name)?\s*:'
    r'|Address\s*:'
    r'|Postal\s+Code\s*:'
    r'|Telephone\s+Primary\s*:'
    r'|Website\s*:'
    r'|CADAC\s+ID\s*:'
    r'|Incorporation\s+Status\s*:'
    r'|Charitable\s+Tax\s+Status\s*:'
    r'|Application\s+Contact\s*:'
    r'|Email\s*:'
    r'|File\s+Number\s*:'
    r'|Portal\s+Account\s+ID\s*:'
    r'|Date\s*:'
    r')\s*$',
    re.IGNORECASE,
)
_FORM_FIELD_VALUE = re.compile(
    r'^(?:\d[\d\s-]*\d'
    r'|[\w.-]+@[\w.-]+'
    r'|https?://[\w./-]+'
    r'|M\d[A-Z]\s*\d[A-Z]\d'
    r'|Incorporated\s+since\s+\d{4}'
    r'|Yes\s+\d[\d-]+[A-Z]{2}\d+'
    r')\s*$',
    re.IGNORECASE,
)
_NUMERIC_ENTITY_DECIMAL = re.compile(r'&#(\d+);')
_NUMERIC_ENTITY_HEX = re.compile(r'&#x([0-9a-fA-F]+);')

_UNICODE_REPLACEMENTS = {
    '\u00A0': ' ',
    '\u200B': '',
    '\u200C': '',
    '\u200D': '',
    '\uFEFF': '',
}

_DEFAULT_FORM_CHROME_PATTERNS = [
    r'^#{1,6}\s+Writing\s+tip',
    r'^#{1,6}\s+Upload\s+.*?(?:PDF|file)',
    r'^#{1,6}\s+\(mandatory',
    r'^#{1,6}\s+FOR OFFICE USE ONLY',
    r'^#{1,6}\s+Protected\s+\w+\s+when\s+completed',
    r'^#{1,6}\s+Please\s+(?:note|select|choose|enter|complete)',
    r'^#{1,6}\s+To\s+(?:enter|edit|complete|submit)\s+.*',
    r'^#{1,6}\s+Application\s+(?:Preview|ID|Number)',
    r'^#{1,6}\s+Voluntary\s+Self.Identification',
]


def _compile_patterns(patterns: list[str] | None) -> list[re.Pattern]:
    if not patterns:
        return []
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def _strip_base64_images(text: str) -> str:
    return _BASE64_IMAGE.sub('[IMAGE]', text)


def _remove_image_placeholders(text: str) -> str:
    text = _HTML_COMMENT_IMAGE.sub('', text)
    text = _STANDALONE_IMAGE_PLACEHOLDER.sub('', text)
    return text


def _normalize_unicode(text: str) -> str:
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    text = text.replace('\t', ' ')
    text = re.sub(r' {2,}', ' ', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = _MULTI_BLANK.sub('\n\n', text)
    return text


def _remove_bare_digit_lines(text: str) -> str:
    lines = text.split('\n')
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _BARE_DIGIT_LINE.match(stripped):
            prev_blank = i == 0 or not lines[i - 1].strip()
            next_blank = i == len(lines) - 1 or not lines[i + 1].strip()
            if prev_blank or next_blank:
                continue
        result.append(line)
    return '\n'.join(result)


def _fix_single_char_lines(text: str) -> str:
    lines = text.split('\n')
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _SINGLE_CHAR_ALPHA_LINE.match(stripped):
            prev_blank = i == 0 or not lines[i - 1].strip()
            next_blank = i == len(lines) - 1 or not lines[i + 1].strip()
            if prev_blank and next_blank:
                continue
        result.append(line)
    return '\n'.join(result)


def _rejoin_split_words(text: str) -> str:
    def _replacer(m: re.Match) -> str:
        return m.group(1) + m.group(2)

    max_passes = 5
    for _ in range(max_passes):
        new_text = _SPLIT_WORD_GAP.sub(_replacer, text)
        if new_text == text:
            break
        text = new_text
    return text


def _decode_numeric_html_entities(text: str) -> str:
    text = _NUMERIC_ENTITY_HEX.sub(
        lambda m: chr(int(m.group(1), 16)), text
    )
    text = _NUMERIC_ENTITY_DECIMAL.sub(
        lambda m: chr(int(m.group(1))), text
    )
    return text


def _remove_form_chrome_headings(
    text: str, form_chrome_patterns: list[re.Pattern]
) -> str:
    if not form_chrome_patterns:
        return text
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            if any(p.match(stripped) for p in form_chrome_patterns):
                continue
        result.append(line)
    return '\n'.join(result)


def _remove_useless_headings(
    text: str, useless_headings: list[re.Pattern]
) -> str:
    if not useless_headings:
        return text
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            if any(p.match(stripped) for p in useless_headings):
                continue
        result.append(line)
    return '\n'.join(result)


def _remove_form_field_labels(text: str) -> str:
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line_stripped = lines[i].strip()
        if _FORM_LABEL_ONLY.match(line_stripped):
            i += 1
            if i < len(lines) and _FORM_FIELD_VALUE.match(lines[i].strip()):
                i += 1
            continue
        if _FORM_FIELD_VALUE.match(line_stripped):
            if result and (
                _FORM_LABEL_ONLY.match(result[-1].strip())
                or _FORM_FIELD_VALUE.match(result[-1].strip())
            ):
                i += 1
                continue
        result.append(lines[i])
        i += 1
    return '\n'.join(result)


def _promote_bold_to_headings(text: str) -> str:
    lines = text.split('\n')
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        m = _BOLD_TO_HEADING.match(stripped)
        if m:
            title = m.group(1).strip()
            prev_blank = i == 0 or not lines[i - 1].strip()
            next_blank = i == len(lines) - 1 or not lines[i + 1].strip()
            if prev_blank and next_blank and len(title) < 100:
                result.append(f'### {title}')
                continue
        result.append(line)
    return '\n'.join(result)


def _normalize_all_caps_headings(text: str) -> str:
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            m = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if m:
                hashes = m.group(1)
                heading_text = m.group(2)
                alpha_chars = [c for c in heading_text if c.isalpha()]
                if alpha_chars:
                    upper_ratio = (
                        sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
                    )
                    if upper_ratio > 0.7:
                        heading_text = heading_text.title()
                        for word in [
                            'Of', 'And', 'The', 'For', 'To', 'In',
                            'At', 'On', 'With', 'A', 'An',
                        ]:
                            heading_text = re.sub(
                                rf'\b{word}\b',
                                word.lower(),
                                heading_text,
                                flags=re.IGNORECASE,
                            )
                line = f'{hashes} {heading_text}'
        result.append(line)
    return '\n'.join(result)


def _italicize_writing_tips(text: str) -> str:
    return re.sub(
        r'^(Writing\s+tip\s*:?\s*)(.*)$',
        r'*\1\2*',
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )


def _split_question_answer_lines(text: str) -> str:
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#') or not stripped:
            result.append(line)
            continue
        qm_pos = stripped.find('?')
        if qm_pos > 0 and qm_pos < len(stripped) * 0.6:
            question_part = stripped[: qm_pos + 1].strip()
            answer_part = stripped[qm_pos + 1 :].strip()
            if answer_part and len(answer_part) > 20:
                heading = question_part.rstrip('?')
                result.append(f'### {heading}')
                result.append('')
                result.append(answer_part)
                continue
        result.append(line)
    return '\n'.join(result)


def _extract_parenthetical_from_headings(text: str) -> str:
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            m = re.match(r'^(#{1,6}\s+)(.+?)\s*\((.+?)\)\s*$', stripped)
            if m:
                hashes_and_space = m.group(1)
                heading_text = m.group(2).strip()
                note = m.group(3).strip()
                result.append(f'{hashes_and_space}{heading_text}')
                result.append('')
                result.append(f'*{note}*')
                continue
        result.append(line)
    return '\n'.join(result)


def _strip_form_widgets(text: str) -> str:
    text = _CHECKBOX_WIDGETS.sub('', text)
    text = _UNICODE_CHECKBOX.sub('', text)
    text = _FILE_METADATA.sub('', text)
    return text


def clean_markdown(text: str, config: dict | None = None) -> str:
    if config is None:
        config = {}

    corruption_fixes = config.get('corruption_fixes', {})
    if isinstance(corruption_fixes, bool):
        enable_split_words = corruption_fixes
        enable_single_char = corruption_fixes
        enable_html_entities = corruption_fixes
    else:
        enable_split_words = corruption_fixes.get('split_words', True)
        enable_single_char = corruption_fixes.get('single_char_lines', True)
        enable_html_entities = corruption_fixes.get('html_entities', True)

    form_chrome_patterns_raw = config.get('form_chrome_patterns')
    if form_chrome_patterns_raw is None:
        form_chrome_patterns_raw = _DEFAULT_FORM_CHROME_PATTERNS
    form_chrome_patterns = _compile_patterns(form_chrome_patterns_raw)

    useless_headings_raw = config.get('useless_headings', [])
    useless_headings = _compile_patterns(useless_headings_raw)

    text = _strip_base64_images(text)
    text = _remove_image_placeholders(text)
    text = _normalize_unicode(text)
    text = _remove_form_chrome_headings(text, form_chrome_patterns)
    text = _remove_useless_headings(text, useless_headings)
    text = _remove_form_field_labels(text)

    if enable_html_entities:
        text = _decode_numeric_html_entities(text)
    if enable_split_words:
        text = _rejoin_split_words(text)
    if enable_single_char:
        text = _fix_single_char_lines(text)

    text = _remove_bare_digit_lines(text)
    text = _promote_bold_to_headings(text)
    text = _normalize_all_caps_headings(text)
    text = _italicize_writing_tips(text)
    text = _split_question_answer_lines(text)
    text = _extract_parenthetical_from_headings(text)
    text = _strip_form_widgets(text)
    text = text.strip() + '\n'
    return text


def clean_file(
    source: Path, dest: Path, config: dict | None = None
) -> None:
    if source.is_dir():
        md_files = sorted(source.glob('*.md'))
        dest.mkdir(parents=True, exist_ok=True)
        for md_file in tqdm(md_files, desc='Cleaning', unit='file'):
            original = md_file.read_text(encoding='utf-8', errors='replace')
            cleaned = clean_markdown(original, config)
            out_path = dest / md_file.name
            out_path.write_text(cleaned, encoding='utf-8')
    else:
        original = source.read_text(encoding='utf-8', errors='replace')
        cleaned = clean_markdown(original, config)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(cleaned, encoding='utf-8')
