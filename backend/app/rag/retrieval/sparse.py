"""Sparse retrieval: Okapi BM25 over analysed (stemmed, stop-word-free) terms.

With an expander, the question becomes concept clauses (bm25_store.search_clauses):
every synonym/acronym group the question mentions is one clause, scored as a single
pseudo-term over all its phrasings (Lucene SynonymQuery semantics), and each remaining
question term is its own clause. Expansion widens recall without letting a long or a
rare phrasing outvote the rest of the question.
"""

from __future__ import annotations

from app.rag.analysis import analyze
from app.rag.index.bm25_store import Clause
from app.rag.pipeline import LoadedIndex
from app.rag.retrieval.expansion import QueryExpander


def build_clauses(question: str, expander: QueryExpander | None) -> list[Clause]:
    """Deterministic: groups in map-file order, then remaining terms in question order."""
    clauses: list[Clause] = []
    covered: set[str] = set()
    if expander is not None:
        for group in expander.matched_groups(question):
            alternatives: list[tuple[str, ...]] = []
            for phrase in group.members:
                terms = tuple(analyze(" ".join(phrase)))
                if terms and terms not in alternatives:
                    alternatives.append(terms)
            for phrase in group.matched:
                covered.update(analyze(" ".join(phrase)))
            clause = tuple(alternatives)
            if clause and clause not in clauses:
                clauses.append(clause)
    seen: set[str] = set()
    for term in analyze(question):
        if term in covered or term in seen:
            continue
        seen.add(term)
        clauses.append(((term,),))
    return clauses


class SparseRetriever:
    def __init__(self, index: LoadedIndex, expander: QueryExpander | None = None) -> None:
        self._index = index
        self._expander = expander

    def search(self, query_text: str, k: int) -> list[tuple[int, float]]:
        """Plain BM25 over the given text: (row, score) pairs, best first."""
        return self._index.bm25.search(analyze(query_text), k)

    def search_question(self, question: str, k: int) -> list[tuple[int, float]]:
        """BM25 with concept-level expansion; plain BM25 when no expander is configured."""
        if self._expander is None:
            return self.search(question, k)
        return self._index.bm25.search_clauses(build_clauses(question, self._expander), k)
