"""Pre-Phase-0 feasibility spike: deterministic hashed embeddings + FAISS.

Throwaway code. It exists only to give evidence for risks R4 (cross-platform
non-determinism), R5 (lexical weakness of hashed vectors) and R7 (faiss-cpu
wheel availability) before Phase 0 commits to ADR-003 and ADR-005.
The production embedder is built in Phase 1 (backend/app/rag/embeddings.py).

Run (no project install needed):
    uv run --python 3.12 --with faiss-cpu --with numpy python -I docs/spikes/faiss_determinism_spike.py
"""

from __future__ import annotations

import hashlib
import platform
import sys
from collections.abc import Callable, Iterable

import faiss
import numpy as np

DIM = 256
# Fixed key: blake2b is stable across processes, unlike Python's salted hash().
SALT = b"hc-rag-spike-v1"

DOCS = [
    "Perform hand hygiene before donning gloves and after removing them.",
    "Store vaccines between 2 and 8 degrees Celsius in a monitored refrigerator.",
    "Dispose of used sharps immediately in puncture-resistant containers.",
    "Wear an N95 respirator for aerosol-generating procedures.",
]
# (query, index of the document that should rank first)
QUERIES = [
    ("vaccine storage temperature", 1),
    ("respirators for aerosol procedures", 3),
    ("glove hand hygiene", 0),
]


def word_tokens(text: str) -> list[str]:
    return text.lower().replace(".", " ").replace(",", " ").split()


def word_and_char_ngrams(text: str) -> list[str]:
    """Words plus char 3-5-grams: subword overlap links 'vaccine'~'vaccines'."""
    toks = word_tokens(text)
    grams: list[str] = []
    for tok in toks:
        padded = f"<{tok}>"
        for n in (3, 4, 5):
            grams.extend(f"#{padded[i:i + n]}" for i in range(len(padded) - n + 1))
    return toks + grams


def embed(texts: Iterable[str], tokenizer: Callable[[str], list[str]]) -> np.ndarray:
    rows = list(texts)
    out = np.zeros((len(rows), DIM), dtype=np.float32)
    for i, text in enumerate(rows):
        for tok in tokenizer(text):
            digest = hashlib.blake2b(tok.encode("utf-8"), key=SALT, digest_size=8).digest()
            h = int.from_bytes(digest, "little")
            # Signed hashing: the sign bit reduces collision bias.
            out[i, h % DIM] += 1.0 if (h >> 63) & 1 else -1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    out /= np.maximum(norms, 1e-12)
    return out


def build_index(tokenizer: Callable[[str], list[str]]) -> faiss.IndexFlatIP:
    index = faiss.IndexFlatIP(DIM)
    index.add(embed(DOCS, tokenizer))
    return index


def index_sha256(index: faiss.IndexFlatIP) -> str:
    return hashlib.sha256(faiss.serialize_index(index).tobytes()).hexdigest()


def main() -> int:
    print(f"python {sys.version.split()[0]} | {platform.system()} {platform.machine()} "
          f"| faiss {faiss.__version__} | numpy {np.__version__}")
    ok = True
    for name, tok in (("words", word_tokens), ("words+char3-5", word_and_char_ngrams)):
        a, b = index_sha256(build_index(tok)), index_sha256(build_index(tok))
        same = a == b
        ok &= same
        index = build_index(tok)
        _, ids = index.search(embed([q for q, _ in QUERIES], tok), 1)
        hits = sum(int(ids[i][0] == exp) for i, (_, exp) in enumerate(QUERIES))
        print(f"[{name:>14}] sha256={a[:16]} rebuild-identical={same} top1={hits}/{len(QUERIES)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
