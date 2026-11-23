"""Okapi BM25 sparse index (in-house) with deterministic JSON persistence.

JSON is used instead of the plan's `bm25.pkl`: unpickling executes code, so a tampered
index artifact could compromise the API. JSON is also byte-stable for SC1.

Two query forms:

* `search(terms)`: classic BM25, summed over distinct terms.
* `search_clauses(clauses)`: concept-level BM25 for expanded queries. A clause is one
  concept from the question, given as alternative phrasings (each a term tuple), and
  is scored as ONE pseudo-term, as Lucene's SynonymQuery does:

      tf(concept, d) = Σ over phrasings of tf(phrasing, d)
      df(concept)    = number of documents containing any phrasing
      score          = BM25(tf, df)

  A multi-term phrasing ("infection prevention and control") occurs in d only when all
  its terms do, with tf = the smallest of their tfs (a bag-of-words phrase estimate).

  Why not max-over-phrasings (dis_max)? Phrasings differ wildly in rarity. Under
  dis_max the rarest synonym ("autoclave") carries the highest IDF and outvotes the
  word the question actually used ("sterilization"). Sharing one df gives the concept
  one IDF, so the document that discusses the concept most wins, whatever its spelling.

`search` is `search_clauses` with one single-term clause per term and gives
bit-identical scores to classic BM25 (same tf, df, formula and summation order).
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from typing import Any, Final

BM25_VERSION: Final = 1  # artifact format; query-side scoring does not change it

type Clause = tuple[tuple[str, ...], ...]


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._postings: dict[str, list[tuple[int, int]]] = {}
        self._doc_len: list[int] = []

    def config(self) -> dict[str, Any]:
        return {"name": "okapi-bm25", "version": BM25_VERSION, "k1": self.k1, "b": self.b}

    @property
    def size(self) -> int:
        return len(self._doc_len)

    def build(self, docs: Sequence[Sequence[str]]) -> None:
        postings: dict[str, list[tuple[int, int]]] = {}
        self._doc_len = []
        for doc_idx, terms in enumerate(docs):
            self._doc_len.append(len(terms))
            for term, tf in sorted(Counter(terms).items()):
                postings.setdefault(term, []).append((doc_idx, tf))
        self._postings = dict(sorted(postings.items()))

    def _idf_for_df(self, df: int) -> float:
        n = self.size
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def idf(self, term: str) -> float:
        """BM25 IDF; unseen terms get the maximum (they are maximally specific)."""
        return self._idf_for_df(len(self._postings.get(term, ())))

    def _concept_tf(self, clause: Clause) -> dict[int, int]:
        """Summed tf of every phrasing of one concept, per document that contains it."""
        concept: dict[int, int] = {}
        for alternative in clause:
            terms = sorted(set(alternative))
            if not terms:
                continue
            tf_maps = [dict(self._postings.get(t, ())) for t in terms]
            if any(not m for m in tf_maps):
                continue  # some term of this phrasing never occurs in the corpus
            docs = set(tf_maps[0]).intersection(*tf_maps[1:])
            for doc_idx in docs:
                concept[doc_idx] = concept.get(doc_idx, 0) + min(m[doc_idx] for m in tf_maps)
        return concept

    def search(self, query_terms: Sequence[str], k: int) -> list[tuple[int, float]]:
        """Classic BM25: each distinct term is its own concept."""
        return self.search_clauses([((t,),) for t in sorted(set(query_terms))], k)

    def search_clauses(self, clauses: Sequence[Clause], k: int) -> list[tuple[int, float]]:
        """Concept-level BM25: Σ over clauses of BM25(concept tf, concept df)."""
        n = self.size
        if n == 0 or k <= 0:
            return []
        avgdl = sum(self._doc_len) / n or 1.0
        totals: dict[int, float] = {}
        for clause in clauses:
            concept_tf = self._concept_tf(clause)
            if not concept_tf:
                continue
            idf = self._idf_for_df(len(concept_tf))
            for doc_idx in sorted(concept_tf):
                tf = concept_tf[doc_idx]
                denom = tf + self.k1 * (1 - self.b + self.b * self._doc_len[doc_idx] / avgdl)
                totals[doc_idx] = totals.get(doc_idx, 0.0) + idf * tf * (self.k1 + 1) / denom
        ranked = sorted(totals.items(), key=lambda p: (-round(p[1], 9), p[0]))
        return ranked[:k]

    def to_bytes(self) -> bytes:
        state = {
            "config": self.config(),
            "doc_len": self._doc_len,
            "postings": {t: [list(p) for p in pl] for t, pl in self._postings.items()},
        }
        return (
            json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> BM25Index:
        state = json.loads(data)
        cfg = state["config"]
        if cfg.get("version") != BM25_VERSION:
            raise ValueError("BM25 artifact written by an incompatible version")
        idx = cls(k1=float(cfg["k1"]), b=float(cfg["b"]))
        idx._doc_len = [int(x) for x in state["doc_len"]]
        idx._postings = {
            t: [(int(d), int(f)) for d, f in pl] for t, pl in state["postings"].items()
        }
        return idx
