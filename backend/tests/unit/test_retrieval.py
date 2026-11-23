from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from app.domain.models import ExpandedQuery
from app.rag.analysis import analyze
from app.rag.index.bm25_store import BM25Index
from app.rag.pipeline import load_index
from app.rag.retrieval.expansion import QueryExpander
from app.rag.retrieval.hybrid import HybridRetriever, RetrievalMode, reciprocal_rank_fusion
from app.rag.retrieval.sparse import build_clauses

# ---------------------------------------------------------------- RRF maths ----


def test_rrf_sums_reciprocal_ranks() -> None:
    fused = reciprocal_rank_fusion([[10, 20, 30], [20, 40]], k=60)
    assert fused[10] == pytest.approx(1 / 61)
    assert fused[20] == pytest.approx(1 / 62 + 1 / 61)
    assert fused[30] == pytest.approx(1 / 63)
    assert fused[40] == pytest.approx(1 / 62)


def test_rrf_rewards_agreement_over_a_single_first_place() -> None:
    fused = reciprocal_rank_fusion([[1, 2], [2, 1]], k=60)
    assert fused[1] == pytest.approx(fused[2])  # symmetric ranks tie exactly
    fused = reciprocal_rank_fusion([[1, 2, 3], [3, 2, 9]], k=60)
    assert fused[2] > fused[1]  # 2nd + 2nd beats 1st + absent


def test_rrf_empty_rankings() -> None:
    assert reciprocal_rank_fusion([[], []], k=60) == {}


def test_weighted_rrf_scales_each_vote_and_skips_zero_weights() -> None:
    fused = reciprocal_rank_fusion([[1, 2], [2, 3]], k=60, weights=[0.5, 1.0])
    assert fused[1] == pytest.approx(0.5 / 61)
    assert fused[2] == pytest.approx(0.5 / 62 + 1 / 61)
    assert reciprocal_rank_fusion([[1], [2]], k=60, weights=[0.0, 1.0]) == {
        2: pytest.approx(1 / 61)
    }
    with pytest.raises(ValueError, match="one weight per ranking"):
        reciprocal_rank_fusion([[1], [2]], k=60, weights=[1.0])


# ---------------------------------------------------------- query expansion ----


@pytest.fixture(scope="module")
def expander() -> QueryExpander:
    return QueryExpander.from_file()


def test_acronyms_expand_both_ways(expander: QueryExpander) -> None:
    assert "personal protective equipment" in expander.expand("When is PPE needed?").added_terms
    assert "aefi" in expander.expand("Report an adverse event following immunization").added_terms


def test_synonym_phrases_match_on_token_boundaries(expander: QueryExpander) -> None:
    added = expander.expand("What is the order for taking off gloves?").added_terms
    assert "doffing" in added
    assert "taking off" not in added  # never re-adds what the question already says
    # "hand" is not "handrub"
    assert expander.expand("A handover note").added_terms == ()


def test_expansion_is_deterministic_and_deduplicated(expander: QueryExpander) -> None:
    a = expander.expand("PPE doffing: how long?")
    assert a == expander.expand("PPE doffing: how long?")
    assert len(a.added_terms) == len(set(a.added_terms))
    assert a.text.startswith("PPE doffing: how long?")


def test_no_expansion_returns_original() -> None:
    assert ExpandedQuery("q", ()).text == "q"


# ----------------------------------------------------------- hybrid search ----


@pytest.fixture(scope="module")
def retriever(fixture_index_dir: Path) -> HybridRetriever:
    return HybridRetriever(load_index(fixture_index_dir), expander=QueryExpander.from_file())


@pytest.mark.parametrize("top_k", [0, 21, -1])
def test_top_k_guard(retriever: HybridRetriever, top_k: int) -> None:
    with pytest.raises(ValueError, match="top_k"):
        retriever.retrieve("gloves", top_k)


def test_empty_question_is_rejected(retriever: HybridRetriever) -> None:
    with pytest.raises(ValueError, match="empty"):
        retriever.retrieve("   ", 5)


def test_results_are_ranked_normalised_and_deterministic(retriever: HybridRetriever) -> None:
    hits = retriever.retrieve("hand hygiene compliance monitoring", 5)
    assert [h.rank for h in hits] == list(range(1, len(hits) + 1))
    assert all(0.0 < h.score <= 1.0 for h in hits)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert hits == retriever.retrieve("hand hygiene compliance monitoring", 5)


def test_ties_break_on_chunk_id(retriever: HybridRetriever) -> None:
    hits = retriever.retrieve("zzzz unknownword glove", 20)
    for a, b in itertools.pairwise(hits):
        if round(a.score, 12) == round(b.score, 12):
            assert a.chunk.chunk_id < b.chunk.chunk_id


@pytest.mark.parametrize("mode", list(RetrievalMode))
def test_modes_report_their_ranks(fixture_index_dir: Path, mode: RetrievalMode) -> None:
    hits = HybridRetriever(load_index(fixture_index_dir), mode=mode).retrieve("glove removal", 3)
    assert hits
    if mode is RetrievalMode.DENSE:
        assert all(h.sparse_rank is None for h in hits)
    if mode is RetrievalMode.SPARSE:
        assert all(h.dense_rank is None for h in hits)
    if mode is not RetrievalMode.HYBRID:
        assert hits[0].score == pytest.approx(1.0)  # first place in the only list


def test_invalid_configuration(fixture_index_dir: Path) -> None:
    with pytest.raises(ValueError, match="rrf_k"):
        HybridRetriever(load_index(fixture_index_dir), rrf_k=0)
    with pytest.raises(ValueError, match="RRF weights"):
        HybridRetriever(load_index(fixture_index_dir), dense_weight=0.0, sparse_weight=0.0)


def test_single_retriever_modes_ignore_tuned_hybrid_weights(fixture_index_dir: Path) -> None:
    """`--mode dense` is an ablation: a tuned dense vote of 0 must not disable it."""
    r = HybridRetriever(load_index(fixture_index_dir), mode=RetrievalMode.DENSE, dense_weight=0.0)
    assert r.weights == (1.0, 0.0)
    hits = r.retrieve("glove removal", 3)
    assert hits
    assert all(h.dense_rank is not None and h.sparse_rank is None for h in hits)


def test_expansion_counts_each_concept_once() -> None:
    """Summed BM25 lets IPC's 3-word expansion outvote 'sterilization'; concepts do not."""
    bm25 = BM25Index()
    bm25.build(
        [
            ["ipc", "infect", "prevent", "control", "program"],  # IPC programme text
            ["steril", "steril", "monitor"],  # sterilization text
            ["glove"],
            ["mask"],
        ]
    )
    flat = bm25.search(["ipc", "infect", "prevent", "control", "steril", "autoclav"], 2)
    assert flat[0][0] == 0
    clauses = [(("ipc",), ("infect", "prevent", "control")), (("steril",), ("autoclav",))]
    assert bm25.search_clauses(clauses, 2)[0][0] == 1


def test_rare_synonym_does_not_outvote_the_common_one() -> None:
    """Regression: under max-over-phrasings, one 'autoclave' beat three 'sterilization's.

    'steril' is common (df 3) and 'autoclav' rare (df 1), so per-term IDF favours the
    autoclave document. As one concept they share a df, and term frequency decides.
    """
    bm25 = BM25Index()
    bm25.build(
        [
            ["steril", "steril", "steril", "monitor"],  # about sterilization
            ["autoclav", "bag", "wast"],  # mentions an autoclave once
            ["glove"],
            ["mask"],
            ["steril", "glove"],
            ["steril", "mask"],
        ]
    )
    assert bm25.search_clauses([(("steril",), ("autoclav",))], 2)[0][0] == 0


def test_multi_term_phrasing_needs_all_its_terms() -> None:
    bm25 = BM25Index()
    bm25.build([["infect", "prevent", "team"], ["infect", "prevent", "control"], ["glove"]])
    ranked = bm25.search_clauses([(("ipc",), ("infect", "prevent", "control"))], 3)
    # "infection prevention team" is not IPC
    assert [doc for doc, _ in ranked] == [1]


def test_plain_search_is_single_term_clauses() -> None:
    bm25 = BM25Index()
    bm25.build([["a", "b"], ["b", "c", "c"], ["d"]])
    terms = ["c", "b", "b"]
    assert bm25.search(terms, 3) == bm25.search_clauses([(("b",),), (("c",),)], 3)


def test_build_clauses_groups_expansions(expander: QueryExpander) -> None:
    clauses = build_clauses("IPC measures for sterilisation", expander)
    ipc = (tuple(analyze("ipc")), tuple(analyze("infection prevention and control")))
    assert ipc in clauses
    assert any(
        tuple(analyze("sterilisation")) in c and tuple(analyze("sterilization")) in c
        for c in clauses
    )
    assert ((analyze("measures")[0],),) in clauses
    # inside its group, not counted twice
    assert ((analyze("ipc")[0],),) not in clauses
    assert build_clauses("IPC measures", None) == [((t,),) for t in analyze("IPC measures")]


def test_expansion_recovers_a_spelling_the_corpus_does_not_use(corpus_index_dir: Path) -> None:
    """The corpus is written in US spelling: 'sterilisation' only matches via its group.

    Retrieval for a question where sterilisation is the only topic must reach the
    sterilization documents through expansion, and must not without it.
    """
    index = load_index(corpus_index_dir)
    question = "How is sterilisation monitored?"

    def ster_hits(expander: QueryExpander | None) -> int:
        hits = HybridRetriever(index, expander=expander, mode=RetrievalMode.SPARSE).retrieve(
            question, 5
        )
        return sum("-ster-" in h.chunk.doc_id for h in hits)

    assert ster_hits(QueryExpander.from_file()) >= 2
    assert ster_hits(None) < ster_hits(QueryExpander.from_file())


def test_zero_dense_vote_equals_sparse_mode(fixture_index_dir: Path) -> None:
    index = load_index(fixture_index_dir)
    bm25_only = HybridRetriever(index, dense_weight=0.0).retrieve("glove removal hand hygiene", 5)
    sparse = HybridRetriever(index, mode=RetrievalMode.SPARSE).retrieve(
        "glove removal hand hygiene", 5
    )
    assert [h.chunk.chunk_id for h in bm25_only] == [h.chunk.chunk_id for h in sparse]
    assert all(h.dense_rank is None for h in bm25_only)
