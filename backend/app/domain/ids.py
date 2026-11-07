"""Identifier formats shared by the API contract, the index and the gold dataset.

These identifiers are defined once and in Phase 0 because three independent
artifacts must agree on them: citations returned by `/qa` (Phase 3), chunk IDs
written by the chunker (Phase 1), and relevance labels in the gold set (Phase 4).
If any of the three drifted, Precision@K would silently read 0.

Chunk ID format (plan §4 Phase 1): ``<doc_id>::<section_slug>::<ordinal>``
    e.g. ``who-ipc-004::ppe-gloves::0002``
"""

from __future__ import annotations

import re
from typing import Annotated, Final

from pydantic import StringConstraints

SLUG_PATTERN: Final = r"[a-z0-9]+(?:-[a-z0-9]+)*"
DOC_ID_PATTERN: Final = rf"^{SLUG_PATTERN}$"
# Four-digit, zero-padded ordinal: lexical order == document order.
CHUNK_ID_PATTERN: Final = rf"^{SLUG_PATTERN}::{SLUG_PATTERN}::\d{{4}}$"
INDEX_VERSION_PATTERN: Final = r"^[0-9a-f]{7,64}$"

DocId = Annotated[str, StringConstraints(pattern=DOC_ID_PATTERN)]
ChunkId = Annotated[str, StringConstraints(pattern=CHUNK_ID_PATTERN)]
Slug = Annotated[str, StringConstraints(pattern=rf"^{SLUG_PATTERN}$")]

_CHUNK_ID_RE: Final = re.compile(CHUNK_ID_PATTERN)


def make_chunk_id(doc_id: str, section_slug: str, ordinal: int) -> str:
    """Build a chunk ID and fail fast if the parts cannot form a valid one."""
    if ordinal < 0 or ordinal > 9999:
        raise ValueError(f"ordinal must be in 0..9999, got {ordinal}")
    chunk_id = f"{doc_id}::{section_slug}::{ordinal:04d}"
    if not _CHUNK_ID_RE.fullmatch(chunk_id):
        raise ValueError(f"invalid chunk id parts: {doc_id!r}, {section_slug!r}")
    return chunk_id
