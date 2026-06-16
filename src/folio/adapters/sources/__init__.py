"""Document source connectors.

Pluggable interface for pulling documents from different sources:
- Local filesystem (default)
- Google Drive
- Dropbox
"""

from __future__ import annotations

from folio.adapters.sources.base import DocumentSource
from folio.adapters.sources.local import LocalSource


def get_source(source_path: str) -> DocumentSource:
    """Return a document source for the given path.

    Currently only supports local filesystem. Cloud sources (gdrive, dropbox)
    will be added when their adapters are implemented.
    """
    if source_path.startswith('gdrive://'):
        raise NotImplementedError("Google Drive source not yet implemented")
    if source_path.startswith('dropbox://'):
        raise NotImplementedError("Dropbox source not yet implemented")
    return LocalSource(source_path)
