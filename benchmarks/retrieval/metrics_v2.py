"""Schema-v2 retrieval metrics over the ORIGINAL ranked chunk sequence (P1-B1).

Cutoff rule: K means the first K chunk positions of the ranking exactly as retrieved.
Documents are deduplicated only inside that cutoff (first-occurrence order), so one
document occupying positions 1..3 consumes all three production slots. There is no
document-only input: every retrieved item names its document and chunk index.

Incomplete judgments: a document without a judgment for the query is UNJUDGED and is
never treated as grade 0; historical confusables are unjudged. Each metric reports a
lower and an upper bound over every label completion consistent with the judged labels:
judged grades, flags and the required-group structure are fixed, and an unjudged
document may turn out irrelevant, supporting, flagged, or an unlabeled member of any
existing required group. lower == upper means the labels determine the value. Bounds
assume the required-group structure is complete; whether it is belongs to dataset
maturity, not to these metrics.

Validity describes computability and label completeness, independent of dataset lane:
- VALID: the labels determine the value and no score tie can change it;
- EXPLORATORY: computable, but unjudged documents or rank ties leave it open;
- UNAVAILABLE: undefined for the query, or the labels it needs do not exist (value None);
- FAIL-CLOSED: integrity violation; EvaluationIntegrityError is raised, nothing returned.
A VALID number from a fixture or synthetic dataset is still not evidence of real-world
retrieval quality; evidence maturity is decided elsewhere (P1-B3).

These are retrieval-side measurements. They do not show that retrieved evidence reached
the assembled LLM context or was used correctly in an answer.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from types import MappingProxyType

from benchmarks.retrieval.evidence import (
    DocumentChunkMap,
    EvidenceMappingError,
    MappedSpan,
    SpanCoverage,
    chunk_id,
    map_document_chunks,
    map_evidence_span,
    span_coverage,
)
from benchmarks.retrieval.schema import BenchmarkDatasetV2, DocumentV2, QueryV2

VALID = "VALID"
EXPLORATORY = "EXPLORATORY"
UNAVAILABLE = "UNAVAILABLE"

DEFAULT_TIE_TOLERANCE = 1e-9
GROUP_GAIN = 3  # 2**2 - 1, credited once per required group
SUPPORT_GAIN = 1  # 2**1 - 1, credited once per supporting document
MAX_IDEAL_GROUPS = 12

GROUP_METRICS = ("complete", "group_recall", "hit", "mrr", "document_recall")
NDCG_METRICS = ("graded_ndcg", "group_ndcg")
EVIDENCE_METRICS = (
    "evidence_group_coverage",
    "evidence_complete",
    "evidence_single_chunk_group_coverage",
    "evidence_single_chunk_complete",
)
VERSION_METRICS = (
    "obsolete_intrusion",
    "obsolete_exclusive",
    "obsolete_before_current",
    "wrong_variant_intrusion",
    "wrong_variant_exclusive",
    "wrong_variant_before_correct",
)
METRIC_NAMES = (*GROUP_METRICS, *NDCG_METRICS, *EVIDENCE_METRICS, *VERSION_METRICS, "crowded_incomplete")
POSITION_SENSITIVE = frozenset(
    {"mrr", "graded_ndcg", "group_ndcg", "obsolete_before_current", "wrong_variant_before_correct"}
)
OUT_OF_SCOPE_REASONS = frozenset(
    {"unanswerable_query", "no_obsolete_version_judgments", "no_wrong_variant_judgments"}
)


class EvaluationIntegrityError(ValueError):
    """Fail-closed evaluation error; messages carry identifiers only, never text."""


# ---------------------------------------------------------------- inputs


@dataclass(frozen=True)
class RetrievedChunk:
    rank: int  # 1-based position in the original ranking
    document_id: str
    chunk_index: int
    score: float
    chunk_id: str | None = None  # when given, must be the canonical "<document>::chunk-NNNN"
    text_sha256: str | None = None  # when given, must match the mapped production chunk


@dataclass(frozen=True)
class CorpusDocument:
    chunk_map: DocumentChunkMap
    source_family_id: str
    status: str = "current"
    variant_key: str | None = None


def build_corpus(
    documents: Iterable[DocumentV2], *, chunk_size: int, chunk_overlap: int
) -> dict[str, CorpusDocument]:
    corpus: dict[str, CorpusDocument] = {}
    for document in documents:
        corpus[document.document_id] = CorpusDocument(
            chunk_map=map_document_chunks(
                document.document_id, document.text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            ),
            source_family_id=document.source_family_id,
            status=document.status,
            variant_key=document.variant_key,
        )
    return corpus


@dataclass(frozen=True)
class QueryLabels:
    query_id: str
    answerable: bool
    groups: tuple[tuple[str, frozenset[str]], ...]  # (group_id, members), dataset order
    grades: Mapping[str, int]  # judged documents only
    flags: Mapping[str, frozenset[str]] = field(default_factory=lambda: MappingProxyType({}))
    historical: frozenset[str] = frozenset()
    evidence: tuple[MappedSpan, ...] | None = None  # None: evidence labels unavailable
    temporal_intent: str = "current"

    def __post_init__(self) -> None:
        qid = self.query_id
        if self.answerable != bool(self.groups):
            raise EvaluationIntegrityError(f"query {qid}: answerable queries need required groups")
        if any(grade not in (0, 1, 2) for grade in self.grades.values()):
            raise EvaluationIntegrityError(f"query {qid}: grades must be 0, 1 or 2")
        members = {member for _, group in self.groups for member in group}
        if any(not group for _, group in self.groups) or len({gid for gid, _ in self.groups}) != len(self.groups):
            raise EvaluationIntegrityError(f"query {qid}: required groups must be non-empty and uniquely named")
        if any(self.grades.get(member) != 2 for member in members):
            raise EvaluationIntegrityError(f"query {qid}: required group members need grade 2")
        if any(grade == 2 and document not in members for document, grade in self.grades.items()):
            raise EvaluationIntegrityError(f"query {qid}: grade 2 documents must belong to a required group")
        if any(flags and self.grades.get(document) != 0 for document, flags in self.flags.items()):
            raise EvaluationIntegrityError(f"query {qid}: flags require a grade 0 judgment")
        for span in self.evidence or ():
            grade = self.grades.get(span.document_id)
            if grade not in (1, 2):
                raise EvaluationIntegrityError(f"query {qid}: evidence needs a grade 1 or 2 judgment")
            if (grade == 2) != (span.group_id is not None) or (
                span.group_id is not None and span.document_id not in dict(self.groups).get(span.group_id, ())
            ):
                raise EvaluationIntegrityError(f"query {qid}: evidence group does not match the judgment")

    def documents(self) -> set[str]:
        evidence = {span.document_id for span in self.evidence or ()}
        return set(self.grades) | set(self.flags) | set(self.historical) | evidence

    def groups_of(self, document_id: str) -> frozenset[str]:
        return frozenset(gid for gid, members in self.groups if document_id in members)


def query_labels(
    query: QueryV2, dataset: BenchmarkDatasetV2, corpus: Mapping[str, CorpusDocument]
) -> QueryLabels:
    """Labels of one validated schema-v2 query, with evidence spans re-verified and mapped."""
    texts = {document.document_id: document.text for document in dataset.documents}
    evidence: tuple[MappedSpan, ...] | None = None
    if dataset.evidence_labels == "character_spans":
        evidence = tuple(
            map_evidence_span(
                corpus[judgment.document_id].chunk_map,
                texts[judgment.document_id],
                start=span.start,
                end=span.end,
                sha256=span.sha256,
                group_id=span.supports_group,
            )
            for judgment in query.judgments
            for span in judgment.evidence
        )
    return QueryLabels(
        query_id=query.query_id,
        answerable=query.answerable,
        groups=tuple((group.group_id, frozenset(group.members)) for group in query.required_groups),
        grades=MappingProxyType({judgment.document_id: judgment.grade for judgment in query.judgments}),
        flags=MappingProxyType(
            {judgment.document_id: frozenset(judgment.flags) for judgment in query.judgments if judgment.flags}
        ),
        historical=frozenset(item.document_id for item in query.historical_relationships),
        evidence=evidence,
        temporal_intent=query.temporal_intent,
    )


# ---------------------------------------------------------------- results


@dataclass(frozen=True)
class Bounds:
    lower: float | None
    upper: float | None
    validity: str
    reasons: tuple[str, ...] = ()


def _unavailable(reason: str) -> Bounds:
    return Bounds(None, None, UNAVAILABLE, (reason,))


def _bounded(lower: float, upper: float, *open_reasons: str) -> Bounds:
    """VALID when the bounds coincide; otherwise EXPLORATORY, citing why they differ."""
    if lower > upper:
        raise AssertionError("lower bound exceeds upper bound")
    if lower == upper:
        return Bounds(float(lower), float(upper), VALID)
    return Bounds(float(lower), float(upper), EXPLORATORY, tuple(dict.fromkeys(r for r in open_reasons if r)))


@dataclass(frozen=True)
class Crowding:
    slots: int
    distinct_documents: int
    repeated_slots: int
    max_document_occupancy: int


@dataclass(frozen=True)
class RetrievedJudgments:
    """Judgment status of the document identities inside one cutoff."""

    documents: int
    required: int
    supporting: int
    judged_irrelevant: int
    unjudged: tuple[str, ...]  # unresolved, first-rank order
    historical_confusables: tuple[str, ...]
    unjudged_same_family: tuple[str, ...]  # unjudged, sharing a family with a required source

    @property
    def judged(self) -> int:
        return self.documents - len(self.unjudged)

    @property
    def coverage(self) -> float | None:
        return self.judged / self.documents if self.documents else None


@dataclass(frozen=True)
class LabelCoverage:
    """Ranking-independent label facts; corpus annotation completeness is NOT pool coverage."""

    required_sources: int
    required_sources_with_group_evidence: int | None  # None: evidence labels unavailable
    corpus_documents: int
    corpus_judged: int
    evaluation_pool: Bounds  # schema v2 defines no evaluation pool yet

    @property
    def corpus_annotation_completeness(self) -> float:
        return self.corpus_judged / self.corpus_documents


@dataclass(frozen=True)
class CutoffResult:
    k: int
    chunks: tuple[RetrievedChunk, ...]  # R_K, original order
    documents: tuple[str, ...]  # D_K, first-occurrence order
    metrics: Mapping[str, Bounds]
    crowding: Crowding
    judgments: RetrievedJudgments
    evidence: tuple[SpanCoverage, ...]


@dataclass(frozen=True)
class QueryEvaluation:
    query_id: str
    answerable: bool
    required_group_count: int
    cutoffs: Mapping[int, CutoffResult]
    label_coverage: LabelCoverage


# ---------------------------------------------------------------- validation


def _validate_labels_against_corpus(labels: QueryLabels, corpus: Mapping[str, CorpusDocument]) -> None:
    if any(document not in corpus for document in labels.documents()):
        raise EvaluationIntegrityError(f"query {labels.query_id}: labels reference a document outside the corpus")
    for span in labels.evidence or ():
        if span.document_text_sha256 != corpus[span.document_id].chunk_map.text_sha256:
            raise EvaluationIntegrityError(f"query {labels.query_id}: evidence span was mapped against different text")


def _validate_ranking(
    ranking: Sequence[RetrievedChunk], corpus: Mapping[str, CorpusDocument], tie_tolerance: float
) -> None:
    seen: set[tuple[str, int]] = set()
    previous: float | None = None
    for position, item in enumerate(ranking, 1):
        if not isinstance(item, RetrievedChunk):
            raise EvaluationIntegrityError("rankings must contain RetrievedChunk items with chunk identities")
        where = f"ranking position {position}"
        if type(item.rank) is not int or item.rank != position:
            raise EvaluationIntegrityError(f"{where}: ranks must be 1..N in ranking order")
        if not isinstance(item.document_id, str) or not item.document_id:
            raise EvaluationIntegrityError(f"{where}: missing document identity")
        if item.document_id not in corpus:
            raise EvaluationIntegrityError(f"{where}: unknown document {item.document_id}")
        chunks = corpus[item.document_id].chunk_map.chunks
        if type(item.chunk_index) is not int or not 0 <= item.chunk_index < len(chunks):
            raise EvaluationIntegrityError(f"{where}: unknown chunk index for {item.document_id}")
        if item.chunk_id is not None and item.chunk_id != chunk_id(item.document_id, item.chunk_index):
            raise EvaluationIntegrityError(f"{where}: chunk_id does not match document and chunk index")
        mapped = chunks[item.chunk_index]
        if item.text_sha256 is not None and item.text_sha256 != mapped.text_sha256:
            raise EvaluationIntegrityError(f"{where}: chunk text digest does not match the chunk map")
        if (item.document_id, item.chunk_index) in seen:
            raise EvaluationIntegrityError(f"{where}: duplicate chunk {item.document_id}#{item.chunk_index}")
        seen.add((item.document_id, item.chunk_index))
        if isinstance(item.score, bool) or not isinstance(item.score, (int, float)) or not math.isfinite(item.score):
            raise EvaluationIntegrityError(f"{where}: scores must be finite numbers")
        if previous is not None and item.score > previous + tie_tolerance:
            raise EvaluationIntegrityError(f"{where}: ranking is not ordered by descending score")
        previous = float(item.score)


def _validate_cutoffs(ks: Iterable[int]) -> tuple[int, ...]:
    values = tuple(ks)
    if not values or any(type(k) is not int or k < 1 for k in values) or len(set(values)) != len(values):
        raise EvaluationIntegrityError("cutoffs must be distinct positive integers")
    return tuple(sorted(values))


# ---------------------------------------------------------------- metrics


def graded_dcg(document_sequence: Sequence[str], grades: Mapping[str, int]) -> float:
    """Conventional graded DCG over chunk positions; a document gains 2**grade - 1 at its first position."""
    seen: set[str] = set()
    total = 0.0
    for position, document in enumerate(document_sequence, 1):
        if document in seen:
            continue
        seen.add(document)
        total += (2 ** grades[document] - 1) / math.log2(position + 1)
    return total


def graded_idcg(grades: Mapping[str, int], k: int) -> float:
    gains = sorted((2**grade - 1 for grade in grades.values() if grade > 0), reverse=True)[:k]
    return sum(gain / math.log2(position + 1) for position, gain in enumerate(gains, 1))


def group_dcg(document_sequence: Sequence[str], labels: QueryLabels) -> float:
    """Group-aware DCG: GROUP_GAIN per required group at the position that first satisfies it,
    SUPPORT_GAIN per grade-1 document at its first position, nothing for repeats, for an
    equivalent member of an already satisfied group, or for grade 0."""
    covered: set[str] = set()
    seen: set[str] = set()
    total = 0.0
    for position, document in enumerate(document_sequence, 1):
        if document in seen:
            continue
        seen.add(document)
        grade = labels.grades[document]
        if grade == 2:
            new = labels.groups_of(document) - covered
            covered |= new
            gain = GROUP_GAIN * len(new)
        else:
            gain = SUPPORT_GAIN if grade == 1 else 0
        total += gain / math.log2(position + 1)
    return total


def group_idcg(labels: QueryLabels, k: int) -> float:
    """Exact maximum of group_dcg over all rankings of distinct judged documents of length <= k."""
    group_ids = [gid for gid, _ in labels.groups]
    if len(group_ids) > MAX_IDEAL_GROUPS:
        raise EvaluationIntegrityError(f"query {labels.query_id}: too many required groups for an exact ideal ranking")
    bit = {gid: 1 << index for index, gid in enumerate(group_ids)}
    profiles = sorted(
        {
            sum(bit[gid] for gid in labels.groups_of(document))
            for document, grade in labels.grades.items()
            if grade == 2
        }
    )
    supporting = sum(1 for grade in labels.grades.values() if grade == 1)

    @lru_cache(maxsize=None)
    def best(position: int, covered: int, supports_used: int) -> float:
        if position > k:
            return 0.0
        weight = 1 / math.log2(position + 1)
        value = 0.0
        for profile in profiles:
            new = profile & ~covered
            if new:
                value = max(
                    value, GROUP_GAIN * bin(new).count("1") * weight + best(position + 1, covered | new, supports_used)
                )
        if supports_used < supporting:
            value = max(value, SUPPORT_GAIN * weight + best(position + 1, covered, supports_used + 1))
        return value

    return best(1, 0, 0)


def _flag_metrics(
    flag: str,
    labels: QueryLabels,
    corpus: Mapping[str, CorpusDocument],
    documents: Sequence[str],
    first_rank: Mapping[str, int],
    unjudged: Sequence[str],
) -> tuple[Bounds, Bounds, Bounds]:
    flagged = {document for document, flags in labels.flags.items() if flag in flags}
    if not flagged:
        return (_unavailable(f"no_{flag}_judgments"),) * 3
    members = {member for _, group in labels.groups for member in group}

    def family(document: str) -> str:
        return corpus[document].source_family_id

    def first_rescue(source_family: str, *, unjudged_rescue: bool) -> float:
        # A rescuer is a retrieved required source of the same family; unjudged same-family
        # documents may be unlabeled required sources.
        candidates = [first_rank[m] for m in members if m in first_rank and family(m) == source_family]
        if unjudged_rescue:
            candidates += [first_rank[u] for u in unjudged if family(u) == source_family]
        return min(candidates, default=math.inf)

    def may_carry_flag(document: str) -> bool:
        if flag == "obsolete_version":
            return labels.temporal_intent == "current" and corpus[document].status == "superseded"
        return corpus[document].variant_key is not None

    retrieved = [document for document in documents if document in flagged]
    hypothetical = [document for document in unjudged if may_carry_flag(document)]
    reason = "unjudged_retrieved"

    intrusion = _bounded(float(bool(retrieved)), float(bool(retrieved or hypothetical)), reason)
    exclusive = _bounded(
        float(any(first_rescue(family(o), unjudged_rescue=True) == math.inf for o in retrieved)),
        float(
            any(first_rescue(family(o), unjudged_rescue=False) == math.inf for o in retrieved)
            or any(first_rescue(family(u), unjudged_rescue=False) == math.inf for u in hypothetical)
        ),
        reason,
    )
    before = _bounded(
        float(any(first_rank[o] < first_rescue(family(o), unjudged_rescue=True) for o in retrieved)),
        float(
            any(first_rank[o] < first_rescue(family(o), unjudged_rescue=False) for o in retrieved)
            or any(first_rank[u] < first_rescue(family(u), unjudged_rescue=False) for u in hypothetical)
        ),
        reason,
    )
    return intrusion, exclusive, before


def evaluate_cutoff(
    labels: QueryLabels,
    corpus: Mapping[str, CorpusDocument],
    cutoff: Sequence[RetrievedChunk],
    k: int,
    *,
    tie_at_cutoff: bool = False,
    tie_within_cutoff: bool = False,
    tie_tolerance: float = DEFAULT_TIE_TOLERANCE,
) -> CutoffResult:
    """Metrics for one cutoff R_K: the first k (or fewer, if the corpus is exhausted) chunks.

    Tie flags come from evaluate_query, which can see position k + 1.
    """
    _validate_labels_against_corpus(labels, corpus)
    _validate_ranking(cutoff, corpus, tie_tolerance)
    if type(k) is not int or k < 1 or len(cutoff) > k:
        raise EvaluationIntegrityError("a cutoff must be the first K chunks of the ranking")
    documents = tuple(dict.fromkeys(item.document_id for item in cutoff))
    first_rank: dict[str, int] = {}
    for item in cutoff:
        first_rank.setdefault(item.document_id, item.rank)
    grades = labels.grades
    members = {member for _, group in labels.groups for member in group}
    member_families = {corpus[member].source_family_id for member in members}
    unjudged = tuple(document for document in documents if document not in grades)
    open_labels = "unjudged_retrieved" if unjudged else ""

    occupancy: dict[str, int] = {}
    for item in cutoff:
        occupancy[item.document_id] = occupancy.get(item.document_id, 0) + 1
    crowding = Crowding(
        slots=len(cutoff),
        distinct_documents=len(documents),
        repeated_slots=len(cutoff) - len(documents),
        max_document_occupancy=max(occupancy.values(), default=0),
    )
    judgments = RetrievedJudgments(
        documents=len(documents),
        required=sum(1 for document in documents if grades.get(document) == 2),
        supporting=sum(1 for document in documents if grades.get(document) == 1),
        judged_irrelevant=sum(1 for document in documents if grades.get(document) == 0),
        unjudged=unjudged,
        historical_confusables=tuple(document for document in documents if document in labels.historical),
        unjudged_same_family=tuple(
            document for document in unjudged if corpus[document].source_family_id in member_families
        ),
    )

    coverages: tuple[SpanCoverage, ...] = ()
    if labels.evidence is not None:
        chunk_indexes: dict[str, list[int]] = {}
        for item in cutoff:
            chunk_indexes.setdefault(item.document_id, []).append(item.chunk_index)
        try:
            coverages = tuple(
                span_coverage(corpus[span.document_id].chunk_map, span, chunk_indexes.get(span.document_id, ()))
                for span in labels.evidence
            )
        except EvidenceMappingError as exc:
            raise EvaluationIntegrityError(f"query {labels.query_id}: evidence mapping failed") from exc

    def unless_open(exact: float) -> float:
        # Upper bound for "some group is (still) unsatisfied": any unjudged retrieved document
        # may be an unlabeled member of every required group.
        return 1.0 if unjudged else exact

    metrics: dict[str, Bounds] = {}
    if not labels.answerable:
        for name in (*GROUP_METRICS, *NDCG_METRICS, *EVIDENCE_METRICS, "crowded_incomplete"):
            metrics[name] = _unavailable("unanswerable_query")
    else:
        groups = labels.groups
        n = len(groups)
        retrieved = set(documents)
        satisfied = [gid for gid, group in groups if group & retrieved]
        complete = float(len(satisfied) == n)
        metrics["complete"] = _bounded(complete, unless_open(complete), open_labels)
        metrics["group_recall"] = _bounded(len(satisfied) / n, unless_open(len(satisfied) / n), open_labels)
        metrics["hit"] = _bounded(float(bool(satisfied)), unless_open(float(bool(satisfied))), open_labels)

        first_required = min((first_rank[d] for d in documents if d in members), default=None)
        first_unjudged = min((first_rank[d] for d in unjudged), default=None)
        best_case = min((rank for rank in (first_required, first_unjudged) if rank is not None), default=None)
        metrics["mrr"] = _bounded(
            1 / first_required if first_required else 0.0,
            1 / best_case if best_case else 0.0,
            open_labels,
        )

        found = len(members & retrieved)
        unjudged_elsewhere = sum(1 for document in corpus if document not in grades and document not in retrieved)
        metrics["document_recall"] = _bounded(
            found / (len(members) + unjudged_elsewhere),
            (found + len(unjudged)) / (len(members) + len(unjudged)),
            open_labels,
            "unjudged_corpus_documents" if unjudged_elsewhere else "",
        )

        if any(document not in grades for document in corpus):
            metrics["graded_ndcg"] = _unavailable("incomplete_judgments_bounds_deferred")
            metrics["group_ndcg"] = _unavailable("incomplete_judgments_bounds_deferred")
        else:
            sequence = [item.document_id for item in cutoff]
            graded = graded_dcg(sequence, grades) / graded_idcg(grades, k)
            grouped = group_dcg(sequence, labels) / group_idcg(labels, k)
            metrics["graded_ndcg"] = _bounded(graded, graded)
            metrics["group_ndcg"] = _bounded(grouped, grouped)

        if labels.evidence is None:
            for name in EVIDENCE_METRICS:
                metrics[name] = _unavailable("evidence_labels_unavailable")
        else:
            # Evidence is credited only at labeled span positions (union or single chunk).
            for prefix, attribute in (("evidence", "union_covered"), ("evidence_single_chunk", "single_chunk_covered")):
                covered = [
                    gid
                    for gid, _ in groups
                    if any(getattr(item, attribute) for item in coverages if item.span.group_id == gid)
                ]
                fraction, all_covered = len(covered) / n, float(len(covered) == n)
                metrics[f"{prefix}_group_coverage"] = _bounded(fraction, unless_open(fraction), open_labels)
                metrics[f"{prefix}_complete"] = _bounded(all_covered, unless_open(all_covered), open_labels)

        crowded = crowding.repeated_slots > 0
        metrics["crowded_incomplete"] = _bounded(
            float(crowded and metrics["complete"].upper == 0.0),
            float(crowded and metrics["complete"].lower == 0.0),
            open_labels,
        )

    (
        metrics["obsolete_intrusion"],
        metrics["obsolete_exclusive"],
        metrics["obsolete_before_current"],
    ) = _flag_metrics("obsolete_version", labels, corpus, documents, first_rank, unjudged)
    (
        metrics["wrong_variant_intrusion"],
        metrics["wrong_variant_exclusive"],
        metrics["wrong_variant_before_correct"],
    ) = _flag_metrics("wrong_variant", labels, corpus, documents, first_rank, unjudged)

    for name, item in list(metrics.items()):
        if item.validity == UNAVAILABLE:
            continue
        extra = []
        if tie_at_cutoff:
            extra.append("rank_tie_at_cutoff")
        if tie_within_cutoff and name in POSITION_SENSITIVE:
            extra.append("rank_tie_within_cutoff")
        if extra:
            metrics[name] = replace(item, validity=EXPLORATORY, reasons=tuple(dict.fromkeys((*item.reasons, *extra))))

    return CutoffResult(
        k=k,
        chunks=tuple(cutoff),
        documents=documents,
        metrics=MappingProxyType({name: metrics[name] for name in METRIC_NAMES}),
        crowding=crowding,
        judgments=judgments,
        evidence=coverages,
    )


def _ties(ranking: Sequence[RetrievedChunk], k: int, tolerance: float) -> tuple[bool, bool]:
    def tied(position: int) -> bool:  # positions are 1-based; compares position and position + 1
        return abs(ranking[position - 1].score - ranking[position].score) <= tolerance

    at_cutoff = len(ranking) > k and tied(k)
    within = any(tied(position) for position in range(1, min(k, len(ranking))))
    return at_cutoff, within


def evaluate_query(
    labels: QueryLabels,
    ranking: Sequence[RetrievedChunk],
    corpus: Mapping[str, CorpusDocument],
    *,
    retrieval_limit: int,
    ks: Iterable[int] = (1, 3, 5),
    tie_tolerance: float = DEFAULT_TIE_TOLERANCE,
) -> QueryEvaluation:
    """Evaluate one query; production TOP_K=3 corresponds to k=3 chunk positions.

    ``retrieval_limit`` is the limit the ranking was retrieved with. It must exceed the
    largest cutoff so a score tie at the cutoff boundary is observable, and the ranking
    must hold exactly min(retrieval_limit, corpus chunk count) chunks.
    """
    cutoffs = _validate_cutoffs(ks)
    if type(retrieval_limit) is not int or retrieval_limit <= cutoffs[-1]:
        raise EvaluationIntegrityError("retrieval_limit must exceed the largest cutoff")
    if not math.isfinite(tie_tolerance) or tie_tolerance < 0:
        raise EvaluationIntegrityError("tie_tolerance must be a finite non-negative number")
    _validate_labels_against_corpus(labels, corpus)
    _validate_ranking(ranking, corpus, tie_tolerance)
    total_chunks = sum(len(document.chunk_map.chunks) for document in corpus.values())
    if len(ranking) != min(retrieval_limit, total_chunks):
        raise EvaluationIntegrityError(
            f"query {labels.query_id}: ranking holds {len(ranking)} chunks, expected "
            f"{min(retrieval_limit, total_chunks)}"
        )

    results: dict[int, CutoffResult] = {}
    for k in cutoffs:
        at_cutoff, within = _ties(ranking, k, tie_tolerance)
        results[k] = evaluate_cutoff(
            labels,
            corpus,
            ranking[:k],
            k,
            tie_at_cutoff=at_cutoff,
            tie_within_cutoff=within,
            tie_tolerance=tie_tolerance,
        )

    members = {member for _, group in labels.groups for member in group}
    evidence_members = None
    if labels.evidence is not None:
        evidence_members = sum(
            1
            for member in members
            if all(
                any(span.document_id == member and span.group_id == gid for span in labels.evidence)
                for gid in labels.groups_of(member)
            )
        )
    return QueryEvaluation(
        query_id=labels.query_id,
        answerable=labels.answerable,
        required_group_count=len(labels.groups),
        cutoffs=MappingProxyType(results),
        label_coverage=LabelCoverage(
            required_sources=len(members),
            required_sources_with_group_evidence=evidence_members,
            corpus_documents=len(corpus),
            corpus_judged=sum(1 for document in corpus if document in labels.grades),
            evaluation_pool=_unavailable("no_evaluation_pool_defined"),
        ),
    )


# ---------------------------------------------------------------- aggregation


@dataclass(frozen=True)
class AggregateBounds:
    metric: str
    k: int
    queries_in_scope: int
    lower_mean: float | None
    upper_mean: float | None
    validity: str
    validity_counts: Mapping[str, int]
    reasons: tuple[str, ...] = ()


def aggregate(
    evaluations: Sequence[QueryEvaluation],
    metric: str,
    k: int,
    *,
    include: Callable[[QueryEvaluation], bool] = lambda evaluation: True,
) -> AggregateBounds:
    """Macro mean of per-query bounds (mean of lowers <= true mean <= mean of uppers).

    Queries outside the metric's scope (unanswerable, or without the needed flag) are
    excluded. If any in-scope query is UNAVAILABLE the aggregate is UNAVAILABLE rather
    than a mean over a biased subset.
    """
    if metric not in METRIC_NAMES:
        raise EvaluationIntegrityError(f"unknown metric {metric}")
    rows = [evaluation.cutoffs[k].metrics[metric] for evaluation in evaluations if include(evaluation)]
    in_scope = [row for row in rows if not (row.validity == UNAVAILABLE and row.reasons[0] in OUT_OF_SCOPE_REASONS)]
    counts = MappingProxyType(
        {validity: sum(1 for row in in_scope if row.validity == validity) for validity in (VALID, EXPLORATORY, UNAVAILABLE)}
    )
    if not in_scope:
        return AggregateBounds(metric, k, 0, None, None, UNAVAILABLE, counts, ("no_queries_in_scope",))
    if counts[UNAVAILABLE]:
        reasons = tuple(sorted({row.reasons[0] for row in in_scope if row.validity == UNAVAILABLE}))
        return AggregateBounds(metric, k, len(in_scope), None, None, UNAVAILABLE, counts, reasons)
    lower = sum(row.lower for row in in_scope) / len(in_scope)
    upper = sum(row.upper for row in in_scope) / len(in_scope)
    reasons = tuple(sorted({reason for row in in_scope for reason in row.reasons}))
    validity = VALID if counts[EXPLORATORY] == 0 else EXPLORATORY
    return AggregateBounds(metric, k, len(in_scope), lower, upper, validity, counts, reasons)
