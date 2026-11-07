from __future__ import annotations

import pytest

from app.domain.ids import make_chunk_id


def test_make_chunk_id_zero_pads_ordinal() -> None:
    assert make_chunk_id("who-ipc-004", "ppe-gloves", 2) == "who-ipc-004::ppe-gloves::0002"


@pytest.mark.parametrize(
    ("doc_id", "slug", "ordinal"),
    [
        ("WHO-IPC", "ppe", 1),  # uppercase is not a slug
        ("who-ipc", "ppe gloves", 1),  # whitespace
        ("who-ipc", "ppe", -1),
        ("who-ipc", "ppe", 10_000),
    ],
)
def test_make_chunk_id_rejects_invalid_parts(doc_id: str, slug: str, ordinal: int) -> None:
    with pytest.raises(ValueError, match=r"ordinal|invalid chunk id"):
        make_chunk_id(doc_id, slug, ordinal)
