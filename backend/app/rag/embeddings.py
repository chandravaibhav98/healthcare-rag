"""Deterministic 256-D embeddings, the spec's `embeddings.py` (ADR-0003).

`HashingEmbedder` maps text to a fixed-size vector with *signed feature hashing*:

    features   word unigrams + bigrams + char 3-5-grams, all over non-stop-words
    weight     ns_weight × (1 + ln tf) × idf      (sublinear TF × smoothed IDF)
    bucket     blake2b(key=salt)(feature) mod dim; the sign comes from the top hash bit
    output     L2-normalised float32

Determinism guarantees (SC1):
* blake2b with a fixed key, never Python `hash()`, which is salted per process;
* features are accumulated in sorted order with Python floats (IEEE-754, fixed order);
* ln() goes through `analysis.exact_ln` (correctly rounded on every platform);
* the norm uses `math.fsum` and `math.sqrt` (both exactly specified), not BLAS.

Only document frequencies are learned (`fit`). They are stored as integers in
`embedder.json`, so the state has no float serialisation ambiguity.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any, Final

import numpy as np

from app.domain.protocols import FloatMatrix
from app.rag.analysis import STOPWORDS, exact_ln, word_tokens

EMBEDDER_NAME: Final = "signed-feature-hashing"
EMBEDDER_VERSION: Final = 2


@dataclass(frozen=True, slots=True)
class HashingEmbedderConfig:
    dim: int = 256
    salt: str = "hc-rag-v1"
    char_ngram_min: int = 3
    char_ngram_max: int = 5
    weight_word: float = 1.0
    weight_bigram: float = 0.7
    weight_char: float = 0.35

    def as_dict(self) -> dict[str, Any]:
        return {"name": EMBEDDER_NAME, "version": EMBEDDER_VERSION, **asdict(self)}


@lru_cache(maxsize=1024)
def _sublinear_tf(tf: int) -> float:
    return 1.0 + exact_ln(Decimal(tf))


class HashingEmbedder:
    def __init__(self, config: HashingEmbedderConfig | None = None) -> None:
        self._cfg = config or HashingEmbedderConfig()
        self._key = self._cfg.salt.encode("utf-8")
        self._n_docs = 0
        self._df: dict[str, int] = {}
        self._bucket_cache: dict[str, tuple[int, float]] = {}
        self._idf_cache: dict[int, float] = {}

    # ----------------------------------------------------------- protocol ----
    @property
    def dim(self) -> int:
        return self._cfg.dim

    def config(self) -> dict[str, Any]:
        return self._cfg.as_dict()

    def fit(self, texts: Sequence[str]) -> None:
        df: Counter[str] = Counter()
        for text in texts:
            df.update(set(self._features(text)))
        self._n_docs = len(texts)
        self._df = dict(df)
        self._idf_cache.clear()

    def embed(self, texts: Sequence[str]) -> FloatMatrix:
        out = np.zeros((len(texts), self._cfg.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            out[row] = self._embed_one(text)
        return out

    # ------------------------------------------------------- persistence ----
    def state_bytes(self) -> bytes:
        state = {"config": self.config(), "n_docs": self._n_docs, "df": self._df}
        return (
            json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode()

    @classmethod
    def from_state_bytes(cls, data: bytes) -> HashingEmbedder:
        state = json.loads(data)
        cfg_dict = {k: v for k, v in state["config"].items() if k not in {"name", "version"}}
        if state["config"].get("version") != EMBEDDER_VERSION:
            raise ValueError("embedder state was written by an incompatible embedder version")
        emb = cls(HashingEmbedderConfig(**cfg_dict))
        emb._n_docs = int(state["n_docs"])
        emb._df = {str(k): int(v) for k, v in state["df"].items()}
        return emb

    # ---------------------------------------------------------- internals ----
    def _features(self, text: str) -> Counter[str]:
        cfg = self._cfg
        # Stop-words carry no topical signal and only add hash collisions ("how", "should").
        words = [w for w in word_tokens(text) if w not in STOPWORDS]
        feats: Counter[str] = Counter()
        for i, w in enumerate(words):
            feats["w:" + w] += 1
            if i + 1 < len(words):
                feats["b:" + w + " " + words[i + 1]] += 1
            if w.isdigit():
                continue
            padded = f"<{w}>"
            for n in range(cfg.char_ngram_min, cfg.char_ngram_max + 1):
                for j in range(len(padded) - n + 1):
                    feats["c:" + padded[j : j + n]] += 1
        return feats

    def _bucket(self, feature: str) -> tuple[int, float]:
        hit = self._bucket_cache.get(feature)
        if hit is None:
            digest = hashlib.blake2b(feature.encode("utf-8"), key=self._key, digest_size=8).digest()
            h = int.from_bytes(digest, "little")
            hit = (h % self._cfg.dim, 1.0 if (h >> 63) & 1 else -1.0)
            self._bucket_cache[feature] = hit
        return hit

    def _idf(self, feature: str) -> float:
        df = self._df.get(feature, 0)
        idf = self._idf_cache.get(df)
        if idf is None:
            # Smoothed IDF; unseen query features (df = 0) get the maximum weight.
            idf = exact_ln(Decimal(1 + self._n_docs) / Decimal(1 + df)) + 1.0
            self._idf_cache[df] = idf
        return idf

    def _ns_weight(self, feature: str) -> float:
        prefix = feature[0]
        if prefix == "w":
            return self._cfg.weight_word
        if prefix == "b":
            return self._cfg.weight_bigram
        return self._cfg.weight_char

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._cfg.dim
        for feature, tf in sorted(self._features(text).items()):
            idx, sign = self._bucket(feature)
            vec[idx] += sign * self._ns_weight(feature) * _sublinear_tf(tf) * self._idf(feature)
        norm = math.sqrt(math.fsum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]
