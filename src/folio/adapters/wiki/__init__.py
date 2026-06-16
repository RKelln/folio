"""Wiki backend integrations.

Pluggable interface with implementations for:
- sage-wiki (default, Go binary, concept extraction + article writing)
- null (no wiki, markdown-only mode)
"""

from __future__ import annotations

from folio.adapters.wiki.base import WikiBackend
from folio.adapters.wiki.null import NullWikiBackend
from folio.adapters.wiki.sage_wiki import SageWikiBackend


def get_wiki_backend(config) -> WikiBackend:
    """Return the configured wiki backend instance."""
    if config is None:
        return NullWikiBackend()
    wiki_type = getattr(config.wiki, 'type', 'null') if hasattr(config.wiki, 'type') else 'null'
    if wiki_type == 'sage-wiki':
        return SageWikiBackend()
    return NullWikiBackend()
