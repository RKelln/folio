"""Website markdown ingestion into folio's document pipeline.

Ingests pre-scraped website markdown files into the pipeline's raw_md
directory with proper frontmatter, then optionally runs pipeline stages.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from folio.core.frontmatter import apply_frontmatter, dict_to_frontmatter, parse_frontmatter
from folio.core.pipeline import run_pipeline

logger = logging.getLogger(__name__)

_SCRAPER_HEADER = re.compile(
    r'<!--\s*source:\s*(?P<url>\S+)\s*\|'
    r'\s*scraped:\s*(?P<scraped_at>[^\s|]+)\s*\|'
    r'\s*hash:\s*(?P<hash>\S+)\s*-->'
)

WEBSITE_STAGES = [
    "clean", "canonicalize", "classify",
    "rewrite", "prioritize", "wiki",
]


def discover_website_files(source: Path) -> list[Path]:
    """Find all .md files recursively from source (file or dir)."""
    source = source.resolve()
    if source.is_file():
        if source.suffix.lower() == '.md':
            return [source]
        return []
    if source.is_dir():
        return sorted(source.rglob('*.md'))
    return []


def parse_scraper_header(content: str) -> dict | None:
    """Parse scraper header. Returns dict with url, scraped_at, hash, or None.

    The scraper header must appear as the first non-blank line.
    """
    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
        m = _SCRAPER_HEADER.match(stripped)
        if m:
            return m.groupdict()
        return None
    return None


def _year_from_iso(iso_str: str) -> int:
    """Extract year from ISO 8601 timestamp."""
    m = re.search(r'^(\d{4})', iso_str.strip())
    if m:
        return int(m.group(1))
    raise ValueError(f"Cannot extract year from: {iso_str!r}")


def _sanitize_slug(raw: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]', '_', raw)
    while '__' in slug:
        slug = slug.replace('__', '_')
    slug = slug.strip('_')
    return slug or 'webpage'


def _slug_from_url(url: str) -> str:
    """Extract a filename-safe slug from a URL path."""
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    if not path:
        slug = parsed.netloc.replace('.', '_') or 'webpage'
    else:
        slug = path.rsplit('/', 1)[-1]

    if '.' in slug:
        slug = slug.rsplit('.', 1)[0]

    return _sanitize_slug(slug)


def build_website_filename(org_abbrev: str, scraped_at: str, name_slug: str) -> str:
    """Build {ORG}__{YYYY-MM-DD}__{name}__webpage.md"""
    date_part = scraped_at[:10] if len(scraped_at) >= 10 else scraped_at
    return f"{org_abbrev}__{date_part}__{name_slug}__webpage.md"


def stage_website_file(
    source_path: Path,
    config,
    name_override: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Validate, build name, add frontmatter, write to raw_md. Returns result dict."""
    result: dict = {
        'source_file': str(source_path),
        'status': 'pending',
        'output_path': None,
        'filename': None,
        'source_url': None,
        'scraped_at': None,
        'url_slug': None,
        'error': None,
    }

    try:
        content = source_path.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        result['status'] = 'error'
        result['error'] = f'Cannot read file: {exc}'
        return result

    _, body = parse_frontmatter(content)

    header = parse_scraper_header(body)
    if header is None:
        result['status'] = 'error'
        result['error'] = 'No scraper comment found'
        return result

    url = header['url']
    scraped_at = header['scraped_at']
    content_hash = header['hash']

    result['source_url'] = url
    result['scraped_at'] = scraped_at

    try:
        year = _year_from_iso(scraped_at)
    except ValueError as exc:
        result['status'] = 'error'
        result['error'] = str(exc)
        return result

    if name_override:
        slug = _sanitize_slug(name_override)
    else:
        slug = _slug_from_url(url)

    result['url_slug'] = slug

    filename = build_website_filename(config.org.abbreviation, scraped_at, slug)
    result['filename'] = filename

    fm = dict_to_frontmatter(
        funder=config.org.abbreviation,
        type="webpage",
        written=year,
        source_url=url,
        scraped_at=scraped_at,
        content_hash=content_hash,
    )

    text_with_fm = apply_frontmatter(body, fm)

    output_dir = Path(config.paths.raw_md)
    output_path = output_dir / filename
    result['output_path'] = str(output_path)

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text_with_fm, encoding='utf-8')
        result['status'] = 'staged'
    else:
        result['status'] = 'would_stage'

    return result


def ingest_website(
    source: Path,
    config_path: str | Path = "folio.yaml",
    name: str | None = None,
    stages: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Main entry point. Discover, stage, optionally run pipeline. Returns full report dict."""
    from folio.config.loader import load_project_config
    config = load_project_config(config_path)

    source = source.resolve()

    files = discover_website_files(source)
    files_found = len(files)

    staging_results: list[dict] = []
    files_staged = 0
    files_skipped = 0
    errors: list[dict] = []

    if files_found == 0:
        return {
            'status': 'ok',
            'source_dir': str(source),
            'staging': {
                'files_found': 0,
                'files_staged': 0,
                'files_skipped': 0,
                'errors': [],
            },
            'pipeline': None,
            'warning': 'No .md files found',
        }

    name_override = name if source.is_file() else None

    for f in files:
        result = stage_website_file(f, config, name_override=name_override, dry_run=dry_run)
        staging_results.append(result)
        if result['status'] in ('staged', 'would_stage'):
            files_staged += 1
        else:
            files_skipped += 1
            errors.append({
                'file': str(f),
                'error': result.get('error', 'Unknown error'),
            })

    report: dict = {
        'status': 'ok',
        'source_dir': str(source),
        'staging': {
            'files_found': files_found,
            'files_staged': files_staged,
            'files_skipped': files_skipped,
            'staging_results': staging_results,
            'errors': errors,
        },
        'pipeline': None,
    }

    if stages is None:
        pipeline_stages = list(WEBSITE_STAGES)
    elif len(stages) == 0:
        pipeline_stages = []
    else:
        pipeline_stages = stages

    if pipeline_stages and files_staged > 0:
        try:
            pipeline_result = run_pipeline(
                config_path=config_path,
                stages=pipeline_stages,
                dry_run=dry_run,
            )
            report['pipeline'] = pipeline_result
        except Exception as exc:
            logger.warning('Pipeline run failed: %s', exc)
            report['pipeline'] = {'status': 'error', 'error': str(exc)}

    return report
