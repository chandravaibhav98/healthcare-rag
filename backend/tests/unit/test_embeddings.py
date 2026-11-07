from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from app.rag.embeddings import EMBEDDER_VERSION, HashingEmbedder, HashingEmbedderConfig

CORPUS = [
    "Perform hand hygiene before donning gloves and after removing them.",
    "Store vaccines between 2 and 8 degrees Celsius in a monitored refrigerator.",
    "Dispose of used sharps immediately in puncture-resistant containers.",
    "Wear a fit-tested respirator for aerosol-generating procedures.",
]


def _fitted(cfg: HashingEmbedderConfig | None = None) -> HashingEmbedder:
    emb = HashingEmbedder(cfg)
    emb.fit(CORPUS)
    return emb


def test_shape_dtype_and_unit_norm() -> None:
    vecs = _fitted().embed(CORPUS)
    assert vecs.shape == (4, 256)
    assert vecs.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(vecs, axis=1), 1.0, rtol=1e-6)


def test_identical_bytes_across_instances() -> None:
    assert _fitted().embed(CORPUS).tobytes() == _fitted().embed(CORPUS).tobytes()


def test_empty_text_is_zero_vector() -> None:
    assert not _fitted().embed([""]).any()


def test_related_text_scores_higher_than_unrelated() -> None:
    emb = _fitted()
    q = emb.embed(["vaccine storage temperature"])[0]
    sims = emb.embed(CORPUS) @ q
    assert int(np.argmax(sims)) == 1


def test_salt_and_dim_change_the_vectors() -> None:
    base = _fitted().embed(CORPUS[:1])
    assert (
        _fitted(HashingEmbedderConfig(salt="other")).embed(CORPUS[:1]).tobytes() != base.tobytes()
    )
    assert _fitted(HashingEmbedderConfig(dim=128)).embed(CORPUS[:1]).shape == (1, 128)


def test_state_roundtrip_reproduces_vectors_exactly() -> None:
    emb = _fitted()
    clone = HashingEmbedder.from_state_bytes(emb.state_bytes())
    assert clone.state_bytes() == emb.state_bytes()
    assert clone.embed(CORPUS).tobytes() == emb.embed(CORPUS).tobytes()


def test_incompatible_state_version_is_rejected() -> None:
    current = f'"version":{EMBEDDER_VERSION}'.encode()
    bad = _fitted().state_bytes().replace(current, b'"version":99')
    with pytest.raises(ValueError, match="incompatible"):
        HashingEmbedder.from_state_bytes(bad)


_SCRIPT = (
    "import hashlib;from app.rag.embeddings import HashingEmbedder as H;"
    "e=H();e.fit({c!r});print(hashlib.sha256(e.embed({c!r}).tobytes()).hexdigest())"
)


@pytest.mark.parametrize("seeds", [("0", "1", "4242", "random")])
def test_vectors_are_invariant_to_pythonhashseed(seeds: tuple[str, ...]) -> None:
    """Python's hash() is salted per process; the embedder must not depend on it (SC1)."""
    code = _SCRIPT.format(c=CORPUS)
    digests = set()
    for seed in seeds:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run(  # noqa: S603  (fixed interpreter and code)
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).parents[2],
        )
        digests.add(out.stdout.strip())
    assert len(digests) == 1, digests
    in_process = hashlib.sha256(_fitted().embed(CORPUS).tobytes()).hexdigest()
    assert digests == {in_process}
