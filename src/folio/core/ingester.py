"""One-off document ingestion.

Converts PDF/DOCX/XLSX to markdown (via configured converter),
applies deterministic cleanup, adds YAML frontmatter, and syncs
to the wiki raw directory.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from folio.adapters.converters import get_converter
from folio.adapters.converters.base import Converter
from folio.core.cleaner import clean_markdown
from folio.core.frontmatter import dict_to_frontmatter, parse_frontmatter

logger = logging.getLogger(__name__)

_UNSAFE_FILENAME = re.compile(r'[^a-zA-Z0-9_.,()+#-]')


def _sanitize_filename(name: str) -> str:
    """Make a string safe for use in filenames.

    Replaces spaces and common separators with underscores,
    removes characters unsafe for filesystems, and collapses
    runs of underscores.
    """
    for ch in (' ', '-', '/', '\\', ':'):
        name = name.replace(ch, '_')
    name = _UNSAFE_FILENAME.sub('', name)
    while '__' in name:
        name = name.replace('__', '_')
    return name.strip('_')


def _build_output_filename(
    funder: str,
    year: int,
    description: str | None,
    doc_types: list[str],
    period: str | None = None,
) -> str:
    """Construct output filename from metadata.

    Format: {funder}__{year}__{type1}_and_{type2}.md
    When period is provided, it replaces year in the filename.
    When description is provided, it is appended after the year/period.
    """
    year_segment = period if period else str(year)
    types_segment = '_and_'.join(doc_types)

    parts = [funder]
    if description:
        desc_sanitized = _sanitize_filename(description)
        parts.append(f'{year_segment}_{desc_sanitized}')
    else:
        parts.append(year_segment)
    parts.append(types_segment)

    return '__'.join(parts) + '.md'


def _validate_funder(funder: str, config) -> list[str]:
    """Check funder against config.funders dict.

    Returns list of warning messages (empty if valid).
    """
    warnings = []
    if funder not in config.funders:
        known = (
            ', '.join(sorted(config.funders.keys()))
            if config.funders
            else '(none configured)'
        )
        warnings.append(f'Unrecognized funder "{funder}". Known: {known}')
    return warnings


def _validate_doc_types(types: list[str], config) -> list[str]:
    """Check doc types against config.doc_types list.

    Returns list of unknown type names (does not block processing).
    """
    unknown = []
    known = set(config.doc_types) if config.doc_types else set()
    for t in types:
        if t not in known:
            unknown.append(t)
    return unknown


def _get_converter_extensions(converter: Converter) -> set[str]:
    """Return the set of file extensions this converter handles."""
    try:
        return converter.supported_extensions
    except Exception:
        return {'.pdf', '.docx', '.xlsx', '.doc', '.xls'}


def ingest_document(
    source_path: Path,
    config,
    funder: str,
    year: int,
    period: str | None = None,
    doc_types: list[str] | None = None,
    description: str | None = None,
    run_rewrite: bool = False,
    sync_wiki: bool = True,
    dry_run: bool = False,
) -> dict:
    """Ingest a single document into the pipeline.

    Steps:
        1. Validate inputs (funder, doc_types) against config
        2. Convert to markdown if source is PDF/DOCX/XLSX/etc.
        3. Apply deterministic cleanup
        4. Generate YAML frontmatter and inject it
        5. Save to config.paths.rewrite_md
        6. Sync to wiki raw directory (if sync_wiki)
        7. Optionally run the LLM rewriter on the output

    Args:
        source_path: Path to the source document.
        config: ProjectConfig from folio config.
        funder: Funder abbreviation (validated against config.funders).
        year: Year the document was written/submitted.
        period: Optional grant period (e.g. "2025-2027").
        doc_types: List of document type tags (default: ['application']).
        description: Optional description for the filename.
        run_rewrite: If True, run the LLM rewriter on the output.
        sync_wiki: If True, copy output to the wiki raw directory.
        dry_run: If True, preview without writing files or calling APIs.

    Returns:
        A dict with keys: status, output_path, wiki_status, frontmatter_added,
        warnings, filename, chars, error.
    """
    if doc_types is None:
        doc_types = ['application']

    result: dict = {
        'status': 'pending',
        'output_path': None,
        'wiki_status': None,
        'frontmatter_added': False,
        'warnings': [],
        'filename': None,
        'chars': 0,
        'error': None,
    }

    funder = funder.upper()

    result['warnings'].extend(_validate_funder(funder, config))

    unknown_types = _validate_doc_types(doc_types, config)
    if unknown_types:
        known = (
            ', '.join(sorted(config.doc_types))
            if config.doc_types
            else '(none configured)'
        )
        for t in unknown_types:
            result['warnings'].append(
                f'Unrecognized doc type "{t}". Known: {known}'
            )

    if not source_path.exists():
        result['status'] = 'error'
        result['error'] = f'Source file not found: {source_path}'
        return result

    if not source_path.is_file():
        result['status'] = 'error'
        result['error'] = f'Not a file: {source_path}'
        return result

    ext = source_path.suffix.lower()

    filename = _build_output_filename(
        funder,
        year,
        description,
        doc_types,
        period,
    )
    result['filename'] = filename

    output_dir = Path(config.paths.rewrite_md)
    output_path = output_dir / filename

    if dry_run:
        result['status'] = 'dry_run'
        result['output_path'] = str(output_path)

        if sync_wiki:
            wiki_raw = Path(config.paths.wiki_project) / 'raw' / filename
            result['wiki_status'] = f'would copy to {wiki_raw}'

        if run_rewrite:
            result['rewrite_note'] = 'rewrite would run (dry run)'

        return result

    converter = get_converter(config)
    convert_extensions = _get_converter_extensions(converter)

    if ext in convert_extensions:
        md_content = converter.convert(source_path)
        if md_content is None:
            result['status'] = 'error'
            result['error'] = f'Conversion failed for {source_path.name}'
            return result
        result['conversion_method'] = converter.name
    elif ext == '.md':
        md_content = source_path.read_text(encoding='utf-8', errors='replace')
        result['conversion_method'] = 'passthrough'
    else:
        result['status'] = 'error'
        result['error'] = f'Unsupported file type: {ext}'
        return result

    md_content = clean_markdown(md_content)

    fm_block = dict_to_frontmatter(
        funder=funder,
        type=doc_types,
        written=year,
        period=period if period else None,
        priority=1,
    )

    _, body = parse_frontmatter(md_content)
    if body:
        md_content = f'{fm_block}\n\n{body.strip()}\n'
    else:
        md_content = f'{fm_block}\n\n{md_content.strip()}\n'

    result['frontmatter_added'] = True
    result['chars'] = len(md_content)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_content, encoding='utf-8')
    result['output_path'] = str(output_path)
    result['status'] = 'success'

    if sync_wiki:
        wiki_raw = Path(config.paths.wiki_project) / 'raw'
        wiki_raw.mkdir(parents=True, exist_ok=True)
        wiki_dest = wiki_raw / filename
        shutil.copy2(output_path, wiki_dest)
        result['wiki_status'] = f'synced to {wiki_dest}'
    else:
        result['wiki_status'] = 'skipped'

    if run_rewrite:
        try:
            from folio.core.rewriter import rewrite_file
        except ImportError:
            logger.warning('Rewriter module not available — skipping rewrite pass')
            result['rewrite_status'] = 'rewriter not available'
        else:
            rewrite_result = rewrite_file(
                filepath=output_path,
                config=config,
            )
            result['rewrite_status'] = rewrite_result

    return result
