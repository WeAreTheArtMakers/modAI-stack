import hashlib
import math
import random
import subprocess
import sys
from dataclasses import replace
from itertools import permutations
from types import MappingProxyType

import pytest

from benchmarks.retrieval.adapters import CROSS_LANGUAGE_MIRROR_V1, adapt_legacy_corpus
from benchmarks.retrieval.evidence import map_document_chunks, map_evidence_span
from benchmarks.retrieval.metrics_v2 import (
    EVIDENCE_METRICS,
    EXPLORATORY,
    GROUP_METRICS,
    NDCG_METRICS,
    UNAVAILABLE,
    VALID,
    CorpusDocument,
    Crowding,
    EvaluationIntegrityError,
    QueryLabels,
    RetrievedChunk,
    aggregate,
    build_corpus,
    evaluate_cutoff,
    evaluate_query,
    graded_dcg,
    graded_idcg,
    group_dcg,
    group_idcg,
    query_labels,
)
from benchmarks.retrieval.schema import load_dataset_v2

LOG3 = math.log2(3)  # discount at position 2; position 1 is log2(2) = 1, position 3 is log2(4) = 2
EXAMPLE = "benchmarks/retrieval/datasets/v2/example.json"


def doc(document_id, *, chunks=1, family=None, status="current", variant=None):
    """A document of `chunks` four-word chunks (chunk size 4, no overlap)."""
    text = " ".join(f"{document_id}-w{index}" for index in range(4 * chunks))
    return document_id, CorpusDocument(
        chunk_map=map_document_chunks(document_id, text, chunk_size=4, chunk_overlap=0),
        source_family_id=family or document_id,
        status=status,
        variant_key=variant,
    )


def corpus(*documents):
    return dict(documents)


def ranking(*items, scores=None):
    chunks = []
    for position, item in enumerate(items, 1):
        document_id, _, index = item.partition("#")
        score = scores[position - 1] if scores else 1.0 - position / 100
        chunks.append(RetrievedChunk(rank=position, document_id=document_id, chunk_index=int(index or 0), score=score))
    return chunks


def labels(groups=None, grades=None, *, answerable=None, flags=None, historical=(), evidence=None, query_id="q"):
    groups = groups or {}
    return QueryLabels(
        query_id=query_id,
        answerable=bool(groups) if answerable is None else answerable,
        groups=tuple((gid, frozenset(members)) for gid, members in groups.items()),
        grades=MappingProxyType(dict(grades or {})),
        flags=MappingProxyType({document: frozenset(values) for document, values in (flags or {}).items()}),
        historical=frozenset(historical),
        evidence=evidence,
    )


def evaluate(query, chunks, documents, ks=(1, 3, 5), limit=6):
    return evaluate_query(query, chunks, documents, retrieval_limit=limit, ks=ks)


def value(result, k, metric):
    item = result.cutoffs[k].metrics[metric]
    return item.lower, item.upper, item.validity


def reasons(result, k, metric):
    return result.cutoffs[k].metrics[metric].reasons


# ---------------------------------------------------------------- cutoff and groups


def test_three_chunks_from_one_document_consume_all_three_slots():
    documents = corpus(doc("x", chunks=3), doc("y"), doc("z"))
    query = labels({"g1": ["x"], "g2": ["y"]}, {"x": 2, "y": 2, "z": 0})
    chunks = ranking("x#0", "x#1", "x#2", "y#0", "z#0")
    result = evaluate(query, chunks, documents)

    at3 = result.cutoffs[3]
    assert at3.documents == ("x",)
    # Deduplicating the five retrieved chunks first would wrongly report (x, y, z) at K=3.
    assert tuple(dict.fromkeys(chunk.document_id for chunk in chunks))[:3] == ("x", "y", "z")
    assert value(result, 3, "complete") == (0.0, 0.0, VALID)
    assert value(result, 3, "group_recall") == (0.5, 0.5, VALID)
    assert value(result, 3, "hit") == (1.0, 1.0, VALID)
    assert value(result, 3, "mrr") == (1.0, 1.0, VALID)
    assert value(result, 3, "document_recall") == (0.5, 0.5, VALID)
    assert at3.crowding == Crowding(slots=3, distinct_documents=1, repeated_slots=2, max_document_occupancy=3)
    assert value(result, 3, "crowded_incomplete") == (1.0, 1.0, VALID)
    expected_ndcg = 3 / (3 + 3 / LOG3)  # DCG 3 at position 1; ideal: both groups at positions 1-2
    assert result.cutoffs[3].metrics["graded_ndcg"].lower == pytest.approx(expected_ndcg)
    assert result.cutoffs[3].metrics["group_ndcg"].lower == pytest.approx(expected_ndcg)

    assert result.cutoffs[5].documents == ("x", "y", "z")
    assert value(result, 5, "complete") == (1.0, 1.0, VALID)
    assert value(result, 5, "crowded_incomplete") == (0.0, 0.0, VALID)


def test_mrr_counts_chunk_positions_not_document_ranks():
    documents = corpus(doc("x", chunks=2), doc("y"), doc("z"))
    query = labels({"g1": ["y"]}, {"x": 0, "y": 2, "z": 0})
    result = evaluate(query, ranking("x#0", "x#1", "y", "z"), documents)
    assert value(result, 3, "mrr") == (1 / 3, 1 / 3, VALID)  # y is the second document but the third slot
    assert value(result, 1, "hit") == (0.0, 0.0, VALID)


def test_document_only_rankings_have_no_fallback():
    documents = corpus(doc("x"), doc("y"))
    query = labels({"g1": ["x"]}, {"x": 2, "y": 0})
    with pytest.raises(EvaluationIntegrityError, match="chunk identities"):
        evaluate(query, ["x", "y"], documents)


def test_three_required_groups_within_three_slots():
    documents = corpus(doc("a"), doc("b"), doc("c"), doc("d"))
    query = labels({"g1": ["a"], "g2": ["b"], "g3": ["c"]}, {"a": 2, "b": 2, "c": 2, "d": 0})
    result = evaluate(query, ranking("a", "b", "c", "d"), documents)
    assert value(result, 1, "complete") == (0.0, 0.0, VALID)
    assert value(result, 1, "group_recall") == (1 / 3, 1 / 3, VALID)
    assert value(result, 3, "complete") == (1.0, 1.0, VALID)
    assert value(result, 3, "group_recall") == (1.0, 1.0, VALID)
    assert value(result, 3, "group_ndcg") == (1.0, 1.0, VALID)
    assert value(result, 3, "graded_ndcg") == (1.0, 1.0, VALID)
    assert result.cutoffs[5].crowding.slots == 4  # the corpus has four chunks


def test_two_alternative_sources_satisfy_one_group():
    documents = corpus(doc("en"), doc("tr"), doc("z"), doc("w"))
    query = labels({"g1": ["en", "tr"]}, {"en": 2, "tr": 2, "z": 0, "w": 0})
    result = evaluate(query, ranking("tr", "z", "w", "en"), documents)
    assert value(result, 3, "complete") == (1.0, 1.0, VALID)
    assert value(result, 3, "group_recall") == (1.0, 1.0, VALID)
    assert value(result, 3, "mrr") == (1.0, 1.0, VALID)
    # Diagnostic only: document recall penalizes the unretrieved equivalent translation.
    assert value(result, 3, "document_recall") == (0.5, 0.5, VALID)
    assert value(result, 5, "document_recall") == (1.0, 1.0, VALID)


def test_equivalent_translations_earn_no_double_group_credit():
    documents = corpus(doc("en"), doc("tr"), doc("s"), doc("z"))
    query = labels({"g1": ["en", "tr"]}, {"en": 2, "tr": 2, "s": 1, "z": 0})
    redundant = evaluate(query, ranking("en", "tr", "s", "z"), documents)
    diverse = evaluate(query, ranking("en", "s", "z", "tr"), documents)

    # Group-aware: gains 3, 0, 1 vs ideal 3, 1 -> (3 + 1/2) / (3 + 1/log2 3).
    assert redundant.cutoffs[3].metrics["group_ndcg"].lower == pytest.approx((3 + 1 / 2) / (3 + 1 / LOG3))
    assert diverse.cutoffs[3].metrics["group_ndcg"].lower == pytest.approx(1.0)
    # Conventional graded nDCG rewards the second translation (gains 3, 3, 1 = ideal).
    assert redundant.cutoffs[3].metrics["graded_ndcg"].lower == pytest.approx(1.0)
    assert diverse.cutoffs[3].metrics["graded_ndcg"].lower == pytest.approx(
        (3 + 1 / LOG3) / (3 + 3 / LOG3 + 1 / 2)
    )
    assert value(redundant, 3, "complete") == value(diverse, 3, "complete") == (1.0, 1.0, VALID)
    assert group_dcg(["en", "tr"], query) == group_dcg(["en"], query) == 3.0
    assert graded_dcg(["en", "tr"], query.grades) > graded_dcg(["en"], query.grades)


def test_missing_required_group_with_judged_irrelevant_documents_is_valid():
    documents = corpus(doc("a"), doc("b"), doc("z"), doc("w"))
    query = labels({"g1": ["a"], "g2": ["b"]}, {"a": 2, "b": 2, "z": 0, "w": 0})
    result = evaluate(query, ranking("a", "z", "w", "b"), documents)
    assert value(result, 3, "complete") == (0.0, 0.0, VALID)
    assert value(result, 3, "group_recall") == (0.5, 0.5, VALID)
    assert value(result, 3, "hit") == (1.0, 1.0, VALID)
    judgments = result.cutoffs[3].judgments
    assert (judgments.judged_irrelevant, judgments.unjudged, judgments.coverage) == (2, (), 1.0)


def test_unjudged_retrieved_document_opens_bounds_instead_of_counting_as_irrelevant():
    documents = corpus(doc("a"), doc("b"), doc("z"), doc("w"))
    query = labels({"g1": ["a"], "g2": ["b"]}, {"a": 2, "b": 2, "z": 0})  # w is unjudged
    result = evaluate(query, ranking("a", "z", "w", "b"), documents)
    assert value(result, 3, "complete") == (0.0, 1.0, EXPLORATORY)
    assert reasons(result, 3, "complete") == ("unjudged_retrieved",)
    assert value(result, 3, "group_recall") == (0.5, 1.0, EXPLORATORY)
    assert value(result, 3, "hit") == (1.0, 1.0, VALID)
    assert value(result, 3, "mrr") == (1.0, 1.0, VALID)
    assert value(result, 3, "document_recall") == (1 / 2, 2 / 3, EXPLORATORY)
    assert value(result, 3, "graded_ndcg") == (None, None, UNAVAILABLE)
    judgments = result.cutoffs[3].judgments
    assert (judgments.unjudged, judgments.judged, judgments.coverage) == (("w",), 2, 2 / 3)
    # Once every group is satisfied by judged sources, the unjudged document cannot matter.
    assert value(result, 5, "complete") == (1.0, 1.0, VALID)


def test_unjudged_corpus_documents_affect_document_recall_but_not_group_metrics():
    documents = corpus(doc("a"), doc("b"), doc("z"), doc("v"))
    query = labels({"g1": ["a"], "g2": ["b"]}, {"a": 2, "b": 2, "z": 0})  # v is unjudged
    result = evaluate(query, ranking("a", "z", "b", "v"), documents)
    assert value(result, 3, "complete") == (1.0, 1.0, VALID)
    # v (not retrieved) might be another required source: 2 / (2 + 1) <= recall <= 2 / 2.
    assert value(result, 3, "document_recall") == (2 / 3, 1.0, EXPLORATORY)
    assert reasons(result, 3, "document_recall") == ("unjudged_corpus_documents",)
    assert result.cutoffs[3].judgments.coverage == 1.0  # top-K coverage ...
    assert result.label_coverage.corpus_annotation_completeness == 3 / 4  # ... is not corpus completeness
    assert result.label_coverage.evaluation_pool.validity == UNAVAILABLE


def test_supporting_document_never_satisfies_a_group():
    documents = corpus(doc("a"), doc("s"), doc("z"))
    query = labels({"g1": ["a"]}, {"a": 2, "s": 1, "z": 0})
    result = evaluate(query, ranking("s", "z", "a"), documents)
    assert value(result, 1, "hit") == (0.0, 0.0, VALID)
    assert value(result, 1, "mrr") == (0.0, 0.0, VALID)
    assert result.cutoffs[1].metrics["group_ndcg"].lower == pytest.approx(1 / 3)
    assert result.cutoffs[1].metrics["graded_ndcg"].lower == pytest.approx(1 / 3)
    assert value(result, 3, "mrr") == (1 / 3, 1 / 3, VALID)
    assert result.cutoffs[3].metrics["group_ndcg"].lower == pytest.approx((1 + 3 / 2) / (3 + 1 / LOG3))
    assert result.cutoffs[3].judgments.supporting == 1


def test_unjudged_historical_confusable_ranked_first_bounds_mrr():
    documents = corpus(doc("e"), doc("h"), doc("u"))
    query = labels({"g1": ["e"]}, {"e": 2}, historical=["h"])
    result = evaluate(query, ranking("h", "e", "u"), documents)
    assert value(result, 3, "mrr") == (0.5, 1.0, EXPLORATORY)
    assert value(result, 3, "group_recall") == (1.0, 1.0, VALID)
    assert value(result, 1, "hit") == (0.0, 1.0, EXPLORATORY)
    judgments = result.cutoffs[3].judgments
    assert judgments.historical_confusables == ("h",)
    assert judgments.unjudged == ("h", "u")
    assert judgments.coverage == 1 / 3


# ---------------------------------------------------------------- versions and families


def test_obsolete_version_retrieved_instead_of_current_source():
    documents = corpus(doc("cur", family="policy"), doc("old", family="policy", status="superseded"), doc("p"))
    query = labels({"g1": ["cur"]}, {"cur": 2, "old": 0, "p": 0}, flags={"old": ["obsolete_version"]})
    result = evaluate(query, ranking("old", "p", "cur"), documents)
    assert value(result, 1, "complete") == (0.0, 0.0, VALID)
    assert value(result, 1, "obsolete_intrusion") == (1.0, 1.0, VALID)
    assert value(result, 1, "obsolete_exclusive") == (1.0, 1.0, VALID)
    assert value(result, 1, "obsolete_before_current") == (1.0, 1.0, VALID)
    assert value(result, 3, "complete") == (1.0, 1.0, VALID)
    assert value(result, 3, "mrr") == (1 / 3, 1 / 3, VALID)
    assert value(result, 3, "obsolete_exclusive") == (0.0, 0.0, VALID)
    assert value(result, 3, "obsolete_before_current") == (1.0, 1.0, VALID)
    assert value(result, 3, "wrong_variant_intrusion") == (None, None, UNAVAILABLE)
    assert reasons(result, 3, "wrong_variant_intrusion") == ("no_wrong_variant_judgments",)


def test_unjudged_family_members_leave_version_metrics_open():
    documents = corpus(
        doc("cur", family="policy"),
        doc("old", family="policy", status="superseded"),
        doc("sib", family="policy", variant="contractor"),
        doc("old2", family="policy", status="superseded"),
        doc("p"),
    )
    query = labels({"g1": ["cur"]}, {"cur": 2, "old": 0, "p": 0}, flags={"old": ["obsolete_version"]})

    rescued = evaluate(query, ranking("old", "sib", "p", "cur", "old2"), documents)
    # sib might be an unlabeled current source of the family; it ranks after old either way.
    assert value(rescued, 3, "obsolete_exclusive") == (0.0, 1.0, EXPLORATORY)
    assert value(rescued, 3, "obsolete_before_current") == (1.0, 1.0, VALID)
    assert value(rescued, 3, "obsolete_intrusion") == (1.0, 1.0, VALID)
    assert rescued.cutoffs[3].judgments.unjudged_same_family == ("sib",)

    hypothetical = evaluate(query, ranking("cur", "old2", "p", "old", "sib"), documents)
    # old2 is superseded and unjudged: it may be obsolete for this query, but the judged
    # current source already precedes it.
    assert value(hypothetical, 3, "obsolete_intrusion") == (0.0, 1.0, EXPLORATORY)
    assert value(hypothetical, 3, "obsolete_exclusive") == (0.0, 0.0, VALID)
    assert value(hypothetical, 3, "obsolete_before_current") == (0.0, 0.0, VALID)


def test_wrong_variant_retrieved_before_the_required_variant():
    documents = corpus(
        doc("basic", family="plan", variant="basic"), doc("premium", family="plan", variant="premium"), doc("z")
    )
    query = labels({"g1": ["basic"]}, {"basic": 2, "premium": 0, "z": 0}, flags={"premium": ["wrong_variant"]})
    result = evaluate(query, ranking("premium", "z", "basic"), documents)
    assert value(result, 1, "wrong_variant_intrusion") == (1.0, 1.0, VALID)
    assert value(result, 1, "wrong_variant_exclusive") == (1.0, 1.0, VALID)
    assert value(result, 3, "wrong_variant_exclusive") == (0.0, 0.0, VALID)
    assert value(result, 3, "wrong_variant_before_correct") == (1.0, 1.0, VALID)
    assert value(result, 3, "obsolete_intrusion") == (None, None, UNAVAILABLE)


def test_unjudged_variant_may_be_a_wrong_variant():
    documents = corpus(
        doc("basic", family="plan", variant="basic"),
        doc("premium", family="plan", variant="premium"),
        doc("deluxe", family="plan", variant="deluxe"),
        doc("z"),
    )
    query = labels({"g1": ["basic"]}, {"basic": 2, "premium": 0, "z": 0}, flags={"premium": ["wrong_variant"]})
    after_correct = evaluate(query, ranking("basic", "deluxe", "z", "premium"), documents)
    assert value(after_correct, 3, "wrong_variant_intrusion") == (0.0, 1.0, EXPLORATORY)
    assert value(after_correct, 3, "wrong_variant_exclusive") == (0.0, 0.0, VALID)
    assert value(after_correct, 3, "wrong_variant_before_correct") == (0.0, 0.0, VALID)
    first = evaluate(query, ranking("deluxe", "z", "basic", "premium"), documents)
    assert value(first, 1, "wrong_variant_exclusive") == (0.0, 1.0, EXPLORATORY)
    assert value(first, 3, "wrong_variant_before_correct") == (0.0, 1.0, EXPLORATORY)


# ---------------------------------------------------------------- unanswerable, ties, empty


def test_unanswerable_query_reports_judgments_but_no_recall():
    documents = corpus(doc("t"), doc("p"), doc("e"))
    query = labels({}, {"t": 1}, answerable=False)
    result = evaluate(query, ranking("t", "p", "e"), documents)
    for name in (*GROUP_METRICS, *NDCG_METRICS, *EVIDENCE_METRICS, "crowded_incomplete"):
        assert value(result, 3, name) == (None, None, UNAVAILABLE)
        assert reasons(result, 3, name) == ("unanswerable_query",)
    judgments = result.cutoffs[3].judgments
    assert (judgments.supporting, judgments.unjudged, judgments.coverage) == (1, ("p", "e"), 1 / 3)
    assert result.cutoffs[3].crowding.slots == 3

    # Supporting evidence is still mapped, without creating a recall metric.
    text = "t-w0 t-w1 t-w2 t-w3"
    span = map_evidence_span(documents["t"].chunk_map, text, start=5, end=14,
                             sha256=hashlib.sha256(text[5:14].encode()).hexdigest())
    with_span = evaluate(replace(query, evidence=(span,)), ranking("p", "t", "e"), documents)
    assert [item.union_covered for item in with_span.cutoffs[1].evidence] == [False]
    assert [item.literal_single_chunk for item in with_span.cutoffs[3].evidence] == [True]
    assert value(with_span, 3, "evidence_group_coverage") == (None, None, UNAVAILABLE)


def test_score_tie_at_the_cutoff_boundary_is_exploratory():
    documents = corpus(doc("a"), doc("b"), doc("c"), doc("d"))
    query = labels({"g1": ["a"]}, {"a": 2, "b": 0, "c": 0, "d": 0})
    one_ulp_higher = math.nextafter(0.7, 1.0)  # cross-platform float noise, not a real reordering
    result = evaluate(query, ranking("a", "b", "c", "d", scores=[0.9, 0.8, 0.7, one_ulp_higher]), documents)
    assert value(result, 1, "complete") == (1.0, 1.0, VALID)
    assert value(result, 3, "complete") == (1.0, 1.0, EXPLORATORY)
    assert reasons(result, 3, "complete") == ("rank_tie_at_cutoff",)
    assert reasons(result, 3, "mrr") == ("rank_tie_at_cutoff",)


def test_score_tie_inside_the_cutoff_only_affects_position_sensitive_metrics():
    documents = corpus(doc("a"), doc("b"), doc("c"), doc("d"))
    query = labels({"g1": ["a"]}, {"a": 2, "b": 0, "c": 0, "d": 0})
    result = evaluate(query, ranking("b", "a", "c", "d", scores=[0.9, 0.9, 0.5, 0.4]), documents)
    assert value(result, 3, "complete") == (1.0, 1.0, VALID)
    assert value(result, 3, "mrr") == (0.5, 0.5, EXPLORATORY)
    assert reasons(result, 3, "mrr") == ("rank_tie_within_cutoff",)
    assert reasons(result, 3, "group_ndcg") == ("rank_tie_within_cutoff",)
    assert reasons(result, 1, "hit") == ("rank_tie_at_cutoff",)


def test_ranking_order_is_used_as_given_and_evaluation_is_deterministic():
    documents = corpus(doc("a"), doc("b"), doc("c"), doc("d"))
    query = labels({"g1": ["a"]}, {"a": 2, "b": 0, "c": 0, "d": 0})
    tied = [0.5, 0.5, 0.5, 0.5]
    first = evaluate(query, ranking("b", "a", "c", "d", scores=tied), documents)
    assert first.cutoffs[1].documents == ("b",)  # never re-sorted by ID or score
    assert first == evaluate(query, ranking("b", "a", "c", "d", scores=tied), documents)
    assert evaluate(query, ranking("a", "b", "c", "d", scores=tied), documents).cutoffs[1].documents == ("a",)


def test_rising_scores_beyond_the_tie_tolerance_fail_closed():
    documents = corpus(doc("a"), doc("b"))
    query = labels({"g1": ["a"]}, {"a": 2, "b": 0})
    with pytest.raises(EvaluationIntegrityError, match="descending score"):
        evaluate(query, ranking("a", "b", scores=[0.5, 0.6]), documents)


def test_empty_cutoff_scores_zero_and_empty_ranking_fails_closed():
    documents = corpus(doc("a"), doc("b"))
    query = labels({"g1": ["a"]}, {"a": 2, "b": 0})
    empty = evaluate_cutoff(query, documents, [], 3)
    for name in ("complete", "group_recall", "hit", "mrr", "document_recall", "group_ndcg", "graded_ndcg"):
        assert (empty.metrics[name].lower, empty.metrics[name].upper, empty.metrics[name].validity) == (0.0, 0.0, VALID)
    assert empty.crowding == Crowding(0, 0, 0, 0)
    assert empty.judgments.coverage is None
    with pytest.raises(EvaluationIntegrityError, match="ranking holds 0 chunks, expected 2"):
        evaluate(query, [], documents)


def test_exhausted_corpus_may_return_fewer_chunks_than_the_limit():
    documents = corpus(doc("a"), doc("b"))
    query = labels({"g1": ["a"]}, {"a": 2, "b": 0})
    result = evaluate(query, ranking("b", "a"), documents)
    assert result.cutoffs[3].crowding.slots == 2
    assert value(result, 3, "mrr") == (0.5, 0.5, VALID)


# ---------------------------------------------------------------- integrity


def _chunk(rank, document_id, chunk_index=0, score=None, **extra):
    return RetrievedChunk(rank=rank, document_id=document_id, chunk_index=chunk_index,
                          score=0.9 - rank / 10 if score is None else score, **extra)


@pytest.mark.parametrize(
    "chunks, message",
    [
        ([_chunk(1, ""), _chunk(2, "a", 1), _chunk(3, "b")], "missing document identity"),
        ([_chunk(1, "q"), _chunk(2, "a", 1), _chunk(3, "b")], "unknown document q"),
        ([_chunk(1, "a", 5), _chunk(2, "a", 1), _chunk(3, "b")], "unknown chunk index"),
        ([_chunk(1, "a", -1), _chunk(2, "a", 1), _chunk(3, "b")], "unknown chunk index"),
        ([_chunk(1, "a", True), _chunk(2, "a", 1), _chunk(3, "b")], "unknown chunk index"),
        ([_chunk(1, "a", chunk_id="a::chunk-0001"), _chunk(2, "a", 1), _chunk(3, "b")], "chunk_id does not match"),
        ([_chunk(1, "a", text_sha256="0" * 64), _chunk(2, "a", 1), _chunk(3, "b")], "digest does not match"),
        ([_chunk(1, "a"), _chunk(2, "a"), _chunk(3, "b")], "duplicate chunk"),
        ([_chunk(1, "a"), _chunk(3, "a", 1), _chunk(4, "b")], "ranks must be 1..N"),
        ([_chunk(1, "a", score=math.nan), _chunk(2, "a", 1), _chunk(3, "b")], "finite"),
        ([_chunk(1, "a"), _chunk(2, "a", 1)], "ranking holds 2 chunks, expected 3"),
    ],
)
def test_missing_or_inconsistent_chunk_identities_fail_closed(chunks, message):
    documents = corpus(doc("a", chunks=2), doc("b"))
    query = labels({"g1": ["a"]}, {"a": 2, "b": 0})
    with pytest.raises(EvaluationIntegrityError, match=message):
        evaluate(query, chunks, documents)


def test_consistent_chunk_identities_are_accepted():
    documents = corpus(doc("a", chunks=2), doc("b"))
    query = labels({"g1": ["a"]}, {"a": 2, "b": 0})
    digest = documents["a"].chunk_map.chunks[1].text_sha256
    chunks = [_chunk(1, "a", 1, chunk_id="a::chunk-0001", text_sha256=digest), _chunk(2, "a"), _chunk(3, "b")]
    assert evaluate(query, chunks, documents).cutoffs[1].documents == ("a",)


def test_evidence_mapped_against_different_text_fails_closed():
    documents = corpus(doc("t"))
    text = "t-w0 t-w1 altered t-w3"
    other = map_document_chunks("t", text, chunk_size=4, chunk_overlap=0)
    span = map_evidence_span(other, text, start=0, end=4, sha256=hashlib.sha256(b"t-w0").hexdigest())
    query = labels({"g1": ["t"]}, {"t": 2})
    with pytest.raises(EvaluationIntegrityError, match="mapped against different text"):
        evaluate(replace(query, evidence=(replace(span, group_id="g1"),)), ranking("t"), documents)


def test_invalid_evaluation_setup_fails_closed():
    documents = corpus(doc("a"), doc("b"))
    query = labels({"g1": ["a"]}, {"a": 2, "b": 0})
    with pytest.raises(EvaluationIntegrityError, match="retrieval_limit must exceed"):
        evaluate(query, ranking("a", "b"), documents, limit=5)
    with pytest.raises(EvaluationIntegrityError, match="cutoffs"):
        evaluate(query, ranking("a", "b"), documents, ks=(0, 3))
    with pytest.raises(EvaluationIntegrityError, match="outside the corpus"):
        evaluate(labels({"g1": ["a"]}, {"a": 2, "zz": 0}), ranking("a", "b"), documents)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"groups": {"g1": ["a"]}, "grades": {"a": 1}}, "need grade 2"),
        ({"groups": {"g1": ["a"]}, "grades": {"a": 2, "b": 2}}, "must belong to a required group"),
        ({"groups": {"g1": ["a"]}, "grades": {"a": 2, "b": 1}, "flags": {"b": ["wrong_variant"]}}, "grade 0"),
        ({"groups": {}, "grades": {"a": 1}, "answerable": True}, "answerable"),
    ],
)
def test_inconsistent_labels_fail_closed(kwargs, message):
    with pytest.raises(EvaluationIntegrityError, match=message):
        labels(**kwargs)


# ---------------------------------------------------------------- evidence through metrics


def _example():
    dataset = load_dataset_v2(EXAMPLE)
    documents = build_corpus(dataset.documents, chunk_size=8, chunk_overlap=2)
    queries = {query.query_id: query for query in dataset.queries}
    return dataset, documents, queries


def test_example_evidence_coverage_is_separate_from_document_retrieval():
    dataset, documents, queries = _example()
    query = query_labels(queries["q-en-meal-overrun"], dataset, documents)
    assert sum(len(document.chunk_map.chunks) for document in documents.values()) == 28

    spanning = evaluate(query, ranking(
        "travel-policy-2025-en#1", "travel-policy-2025-en#2", "onboarding-guide-en#0",
        "parking-rules-en#0", "parking-rules-en#1", "finance-portal-guide-en#0",
    ), documents)
    assert value(spanning, 3, "group_recall") == (0.5, 1.0, EXPLORATORY)  # onboarding is unjudged
    assert value(spanning, 3, "evidence_group_coverage") == (0.5, 1.0, EXPLORATORY)
    assert value(spanning, 3, "evidence_single_chunk_group_coverage") == (0.0, 1.0, EXPLORATORY)
    assert spanning.cutoffs[3].crowding.repeated_slots == 1
    assert value(spanning, 3, "crowded_incomplete") == (0.0, 1.0, EXPLORATORY)
    en_span = next(item for item in spanning.cutoffs[3].evidence if item.span.document_id == "travel-policy-2025-en")
    assert (en_span.union_covered, en_span.single_chunk_covered, en_span.covering_chunk_indexes) == (True, False, (1, 2))

    missed = evaluate(query, ranking(
        "travel-policy-2025-en#0", "travel-policy-2025-en#3", "expense-approval-en#1",
        "expense-approval-en#2", "expense-approval-en#3", "finance-portal-guide-en#0",
    ), documents)
    # Both required groups are represented by documents, but no labeled evidence is covered.
    assert value(missed, 3, "complete") == (1.0, 1.0, VALID)
    assert value(missed, 3, "evidence_group_coverage") == (0.0, 0.0, VALID)
    assert value(missed, 3, "evidence_complete") == (0.0, 0.0, VALID)
    assert value(missed, 5, "evidence_group_coverage") == (0.5, 0.5, VALID)  # expense chunks 1-3 cover group b
    assert value(missed, 5, "evidence_single_chunk_group_coverage") == (0.0, 0.0, VALID)
    supporting = [item for item in missed.cutoffs[5].evidence if item.span.group_id is None]
    assert [item.span.document_id for item in supporting] == ["finance-portal-guide-en"]
    assert not supporting[0].document_retrieved  # finance is at position 6
    assert value(missed, 3, "graded_ndcg") == (None, None, UNAVAILABLE)  # 4 of 8 documents judged

    coverage = missed.label_coverage
    assert (coverage.required_sources, coverage.required_sources_with_group_evidence) == (3, 3)
    assert (coverage.corpus_documents, coverage.corpus_judged) == (8, 4)


def test_example_query_labels_preserve_groups_flags_and_spans():
    dataset, documents, queries = _example()
    meal = query_labels(queries["q-tr-meal-allowance"], dataset, documents)
    assert meal.groups == (("a", frozenset({"travel-policy-2025-en", "travel-policy-2025-tr"})),)
    assert meal.flags == {"travel-policy-2024-tr": frozenset({"obsolete_version"})}
    assert {span.group_id for span in meal.evidence} == {"a"}
    unanswerable = query_labels(queries["q-en-international-allowance"], dataset, documents)
    assert not unanswerable.answerable and unanswerable.grades == {"travel-policy-2025-en": 1}


def test_legacy_adapted_dataset_has_no_evidence_metrics_and_bounded_mrr():
    dataset, _ = adapt_legacy_corpus(CROSS_LANGUAGE_MIRROR_V1)
    documents = build_corpus(dataset.documents, chunk_size=700, chunk_overlap=100)
    source = dataset.queries[0]
    query = query_labels(source, dataset, documents)
    expected = source.required_groups[0].members[0]
    confusable = source.historical_relationships[0].document_id
    others = [d for d in sorted(documents) if d not in {expected, confusable}][:4]
    result = evaluate(query, ranking(confusable, expected, *others), documents)
    assert value(result, 3, "evidence_group_coverage") == (None, None, UNAVAILABLE)
    assert reasons(result, 3, "evidence_group_coverage") == ("evidence_labels_unavailable",)
    assert value(result, 3, "hit") == (1.0, 1.0, VALID)  # the v1 Hit@3 outcome
    assert value(result, 3, "mrr") == (0.5, 1.0, EXPLORATORY)  # the confusable is unjudged, not wrong
    assert result.cutoffs[3].judgments.historical_confusables == (confusable,)


# ---------------------------------------------------------------- bounds verified by enumeration


def _completions(query, documents, unjudged):
    """Every schema-consistent label completion of the unjudged documents (current intent)."""
    group_ids = [gid for gid, _ in query.groups]
    subsets = [
        frozenset(gid for bit, gid in enumerate(group_ids) if mask >> bit & 1) for mask in range(1, 1 << len(group_ids))
    ]
    options = []
    for document in unjudged:
        choices = [(0, ()), (0, ("obsolete_version",)), (0, ("wrong_variant",)), (1, ())]
        if documents[document].status == "current":
            choices += [(2, subset) for subset in subsets]
        options.append(choices)

    def assign(index, grades, flags, groups):
        if index == len(unjudged):
            yield grades, flags, groups
            return
        document = unjudged[index]
        for grade, extra in options[index]:
            new_groups, new_flags = groups, flags
            if grade == 2:
                new_groups = {gid: members | ({document} if gid in extra else set()) for gid, members in groups.items()}
            elif extra:
                new_flags = {**flags, document: frozenset(extra)}
            yield from assign(index + 1, {**grades, document: grade}, new_flags, new_groups)

    base_groups = {gid: set(members) for gid, members in query.groups}
    for grades, flags, groups in assign(0, dict(query.grades), dict(query.flags), base_groups):
        members = set().union(*groups.values())
        consistent = True
        for document, values in flags.items():
            family = documents[document].source_family_id
            same_family = [m for m in members if documents[m].source_family_id == family]
            if "obsolete_version" in values and not (
                documents[document].status == "superseded"
                and any(documents[m].status == "current" for m in same_family)
            ):
                consistent = False
            if "wrong_variant" in values and not any(
                documents[m].variant_key is not None
                and documents[document].variant_key is not None
                and documents[m].variant_key != documents[document].variant_key
                for m in same_family
            ):
                consistent = False
        if consistent:
            yield labels(groups, grades, flags=flags)


def test_reported_bounds_contain_every_label_completion_and_are_tight_for_group_metrics():
    rng = random.Random("bounds-enumeration")
    checked = 0
    for _ in range(200):
        names = [f"d{index}" for index in range(rng.randint(3, 5))]
        documents = corpus(*(
            doc(
                name,
                chunks=rng.randint(1, 2),
                family=rng.choice(["f1", "f2"]),
                status="superseded" if rng.random() < 0.3 else "current",
                variant=rng.choice([None, "v1", "v2"]),
            )
            for name in names
        ))
        current = [name for name in names if documents[name].status == "current"]
        if len(current) < 2:
            continue
        group_count = rng.randint(1, 2)
        groups = {f"g{index}": {rng.choice(current)} for index in range(group_count)}
        members = set().union(*groups.values())
        grades = {member: 2 for member in members}
        others = [name for name in names if name not in members]
        rng.shuffle(others)
        judged_others = others[: rng.randint(0, max(0, len(others) - 1))]
        flags = {}
        for name in judged_others:
            grades[name] = rng.choice([0, 0, 1])
            family_members = [m for m in members if documents[m].source_family_id == documents[name].source_family_id]
            if grades[name] == 0 and documents[name].status == "superseded" and family_members:
                flags[name] = frozenset({"obsolete_version"})
            elif grades[name] == 0 and documents[name].variant_key and any(
                documents[m].variant_key not in (None, documents[name].variant_key) for m in family_members
            ):
                flags[name] = frozenset({"wrong_variant"})
        query = labels(groups, grades, flags=flags)
        unjudged = [name for name in names if name not in grades]
        chunks = [f"{name}#{index}" for name in names for index in range(len(documents[name].chunk_map.chunks))]
        rng.shuffle(chunks)
        chunks = chunks[:4]
        scores = sorted((rng.random() for _ in chunks), reverse=True)
        if any(abs(a - b) <= 1e-9 for a, b in zip(scores, scores[1:])):
            continue
        ks = (1, 2, 3)
        result = evaluate(query, ranking(*chunks, scores=scores), documents, ks=ks, limit=4)
        values = {(k, name): [] for k in ks for name in result.cutoffs[k].metrics}
        for completion in _completions(query, documents, unjudged):
            exact = evaluate(completion, ranking(*chunks, scores=scores), documents, ks=ks, limit=4)
            for k in ks:
                for name, item in exact.cutoffs[k].metrics.items():
                    if item.validity != UNAVAILABLE:
                        assert item.validity == VALID  # complete labels determine every metric
                        values[(k, name)].append(item.lower)
        for (k, name), observed in values.items():
            reported = result.cutoffs[k].metrics[name]
            if not observed or reported.validity == UNAVAILABLE:
                continue
            assert reported.lower - 1e-12 <= min(observed) and max(observed) <= reported.upper + 1e-12, (k, name)
            if name in ("complete", "group_recall", "hit", "mrr", "document_recall") and all(
                documents[u].status == "current" for u in unjudged
            ):
                assert (reported.lower, reported.upper) == pytest.approx((min(observed), max(observed))), (k, name)
            checked += 1
    assert checked > 1000


# ---------------------------------------------------------------- nDCG invariants


def test_group_ideal_ranking_is_exact_where_greedy_selection_is_not():
    documents = corpus(doc("a"), doc("b"), doc("c"))
    query = labels(
        {"g1": ["a", "b"], "g2": ["a", "b"], "g3": ["a", "c"], "g4": ["a", "c"], "g5": ["b"], "g6": ["c"]},
        {"a": 2, "b": 2, "c": 2},
    )
    greedy = 12 + 3 / LOG3  # a covers four groups first, then one new group
    optimum = 9 + 9 / LOG3  # b then c covers all six groups
    assert optimum > greedy
    assert group_idcg(query, 2) == pytest.approx(optimum)
    result = evaluate(query, ranking("a", "b", "c"), documents, ks=(1, 2, 3), limit=4)
    assert result.cutoffs[2].metrics["group_ndcg"].lower == pytest.approx(greedy / optimum)
    best = evaluate(query, ranking("b", "c", "a"), documents, ks=(1, 2, 3), limit=4)
    assert best.cutoffs[2].metrics["group_ndcg"].lower == pytest.approx(1.0)


def _reference_group_dcg(order, groups, grades):
    """Independent formulation: each group earns 3 at its first satisfying position."""
    first = {}
    for position, document in enumerate(order, 1):
        first.setdefault(document, position)
    total = 0.0
    for _, members in groups:
        positions = [first[m] for m in members if m in first]
        if positions:
            total += 3 / math.log2(min(positions) + 1)
    return total + sum(1 / math.log2(first[d] + 1) for d in first if grades[d] == 1)


def _reference_graded_dcg(order, grades):
    first = {}
    for position, document in enumerate(order, 1):
        first.setdefault(document, position)
    return sum((2 ** grades[d] - 1) / math.log2(position + 1) for d, position in first.items())


def test_ndcg_matches_brute_force_reference_and_stays_in_unit_interval():
    rng = random.Random("ndcg-reference")
    for _ in range(150):
        group_ids = [f"g{index}" for index in range(rng.randint(1, 3))]
        names = [f"d{index}" for index in range(rng.randint(2, 6))]
        grades, groups = {}, {gid: [] for gid in group_ids}
        for name in names:
            grades[name] = rng.choice([0, 1, 2, 2])
            if grades[name] == 2:
                for gid in rng.sample(group_ids, rng.randint(1, len(group_ids))):
                    groups[gid].append(name)
        for gid in group_ids:
            if not groups[gid]:
                names.append(f"m{gid}")
                grades[f"m{gid}"] = 2
                groups[gid].append(f"m{gid}")
        query = labels(groups, grades)
        relevant = [name for name in grades if grades[name] > 0]
        for k in range(1, 5):
            length = min(k, len(relevant))
            orders = list(permutations(relevant, length))
            assert group_idcg(query, k) == pytest.approx(
                max(_reference_group_dcg(order, query.groups, grades) for order in orders)
            )
            assert graded_idcg(grades, k) == pytest.approx(max(_reference_graded_dcg(order, grades) for order in orders))
            sample = [rng.choice(list(grades)) for _ in range(k)]
            assert group_dcg(sample, query) == pytest.approx(_reference_group_dcg(sample, query.groups, grades))
            assert 0.0 <= group_dcg(sample, query) / group_idcg(query, k) <= 1.0 + 1e-12
            assert 0.0 <= graded_dcg(sample, grades) / graded_idcg(grades, k) <= 1.0 + 1e-12


def test_ndcg_is_unavailable_when_an_unjudged_document_could_raise_the_ideal():
    # u is never retrieved in the top 1, yet it might cover both groups and so raise IDCG;
    # unjudged-as-zero would overstate nDCG, so no number is reported.
    documents = corpus(doc("a"), doc("b"), doc("u"))
    query = labels({"g1": ["a"], "g2": ["b"]}, {"a": 2, "b": 2})
    result = evaluate(query, ranking("a", "b", "u"), documents)
    assert result.cutoffs[1].judgments.unjudged == ()
    for name in NDCG_METRICS:
        assert value(result, 1, name) == (None, None, UNAVAILABLE)
        assert reasons(result, 1, name) == ("incomplete_judgments_bounds_deferred",)


def test_swapping_equivalent_members_does_not_change_group_ndcg():
    documents = corpus(doc("en"), doc("tr"), doc("s"), doc("z"))
    query = labels({"g1": ["en", "tr"]}, {"en": 2, "tr": 2, "s": 1, "z": 0})
    first = evaluate(query, ranking("z", "en", "s", "tr"), documents)
    second = evaluate(query, ranking("z", "tr", "s", "en"), documents)
    assert first.cutoffs[3].metrics["group_ndcg"] == second.cutoffs[3].metrics["group_ndcg"]


# ---------------------------------------------------------------- aggregation


def test_aggregate_uses_macro_bounds_and_scopes_queries():
    three = evaluate(
        labels({"g1": ["a"], "g2": ["b"], "g3": ["c"]}, {"a": 2, "b": 2, "c": 2, "d": 0}, query_id="three"),
        ranking("a", "b", "c", "d"),
        corpus(doc("a"), doc("b"), doc("c"), doc("d")),
    )
    open_two = evaluate(
        labels({"g1": ["a"], "g2": ["b"]}, {"a": 2, "b": 2, "z": 0}, query_id="open"),
        ranking("a", "z", "w", "b"),
        corpus(doc("a"), doc("b"), doc("z"), doc("w")),
    )
    single = evaluate(
        labels({"g1": ["a"]}, {"a": 2, "b": 0}, query_id="single"), ranking("b", "a"), corpus(doc("a"), doc("b"))
    )
    unanswerable = evaluate(
        labels({}, {"t": 1}, answerable=False, query_id="none"), ranking("t", "p"), corpus(doc("t"), doc("p"))
    )
    evaluations = [three, open_two, single, unanswerable]

    complete = aggregate(evaluations, "complete", 3)
    assert complete.queries_in_scope == 3  # the unanswerable query is out of scope
    assert (complete.lower_mean, complete.upper_mean) == pytest.approx((2 / 3, 1.0))
    assert complete.validity == EXPLORATORY
    assert dict(complete.validity_counts) == {VALID: 2, EXPLORATORY: 1, UNAVAILABLE: 0}

    multi = aggregate(evaluations, "complete", 3, include=lambda evaluation: evaluation.required_group_count >= 2)
    assert (multi.queries_in_scope, multi.lower_mean, multi.upper_mean) == (2, 0.5, 1.0)

    ndcg = aggregate(evaluations, "group_ndcg", 3)
    assert (ndcg.validity, ndcg.lower_mean, ndcg.reasons) == (UNAVAILABLE, None, ("incomplete_judgments_bounds_deferred",))

    assert aggregate([unanswerable], "complete", 3).reasons == ("no_queries_in_scope",)
    assert aggregate(evaluations, "obsolete_intrusion", 3).validity == UNAVAILABLE
    valid_only = aggregate([three, single], "complete", 3)
    assert (valid_only.validity, valid_only.lower_mean) == (VALID, 1.0)
    with pytest.raises(EvaluationIntegrityError, match="unknown metric"):
        aggregate(evaluations, "recall", 3)


# ---------------------------------------------------------------- purity


def test_pure_modules_import_no_services_models_or_configuration():
    code = (
        "import sys; import benchmarks.retrieval.metrics_v2, benchmarks.retrieval.evidence; "
        "print(sorted(m for m in sys.modules if m == 'app' or m.startswith(('app.', 'qdrant', 'sentence_transformers', "
        "'torch', 'httpx', 'sqlalchemy', 'redis'))))"
    )
    output = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert output.strip() == "['app', 'app.services', 'app.services.rag', 'app.services.rag.chunker']"


def test_bounds_are_frozen_results():
    documents = corpus(doc("a"), doc("b"))
    result = evaluate(labels({"g1": ["a"]}, {"a": 2, "b": 0}), ranking("a", "b"), documents)
    with pytest.raises(TypeError):
        result.cutoffs[3].metrics["complete"] = None
    assert replace(result.cutoffs[3].metrics["complete"], lower=0.0).lower == 0.0
