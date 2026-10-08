"""Versioned, human-reviewable fixture corpus contracts."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


Language = Literal["tr", "en", "mixed"]
Category = Literal[
    "single_document_fact",
    "multi_document",
    "long_document",
    "semantic_distractors",
    "unanswerable",
]

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_CHUNK_ID_RE = re.compile(r"^(?P<document>[a-z][a-z0-9_-]{0,63})::chunk-(?P<index>[0-9]{4,})$")


class BenchmarkDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    language: Language
    text: str = Field(min_length=1, max_length=250_000)

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("document_id must be a stable lowercase benchmark identifier")
        return value

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document text must not be blank")
        return value


class QueryCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str
    language: Language
    question: str = Field(min_length=1, max_length=12_000)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    categories: list[Category] = Field(min_length=1)
    answerable: bool
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("query_id")
    @classmethod
    def validate_query_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("query_id must be a stable lowercase benchmark identifier")
        return value

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()

    @field_validator("expected_document_ids", "expected_chunk_ids", "categories")
    @classmethod
    def validate_unique_values(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("labels and categories must not contain duplicates")
        return values

    @field_validator("expected_chunk_ids")
    @classmethod
    def validate_chunk_ids(cls, values: list[str]) -> list[str]:
        if any(not _CHUNK_ID_RE.fullmatch(value) for value in values):
            raise ValueError("expected_chunk_ids must use stable document::chunk-NNNN identifiers")
        return values

    @model_validator(mode="after")
    def validate_relevance(self) -> "QueryCase":
        if self.answerable:
            if not self.expected_document_ids:
                raise ValueError("answerable queries require expected document IDs")
            if "multi_document" in self.categories and len(self.expected_document_ids) < 2:
                raise ValueError("multi_document cases require at least two expected documents")
            if "single_document_fact" in self.categories and len(self.expected_document_ids) != 1:
                raise ValueError("single_document_fact cases require exactly one expected document")
            if "unanswerable" in self.categories:
                raise ValueError("answerable queries cannot use the unanswerable category")
            chunk_documents = {
                _CHUNK_ID_RE.fullmatch(chunk_id).group("document")
                for chunk_id in self.expected_chunk_ids
            }
            if not chunk_documents.issubset(set(self.expected_document_ids)):
                raise ValueError("expected chunk labels must belong to expected documents")
        else:
            if self.expected_document_ids or self.expected_chunk_ids:
                raise ValueError("unanswerable queries cannot declare relevant documents or chunks")
            if "unanswerable" not in self.categories:
                raise ValueError("unanswerable queries must include the unanswerable category")
        return self


class BenchmarkDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    dataset_version: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    classification: Literal["fixture", "authoritative"]
    documents: list[BenchmarkDocument] = Field(min_length=1)
    queries: list[QueryCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> "BenchmarkDataset":
        document_ids = [document.document_id for document in self.documents]
        query_ids = [query.query_id for query in self.queries]
        if len(set(document_ids)) != len(document_ids):
            raise ValueError("document IDs must be unique")
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("query IDs must be unique")

        known_documents = set(document_ids)
        for query in self.queries:
            if not set(query.expected_document_ids).issubset(known_documents):
                raise ValueError(f"query {query.query_id} references an unknown document")
            if any(
                _CHUNK_ID_RE.fullmatch(chunk_id).group("document") not in known_documents
                for chunk_id in query.expected_chunk_ids
            ):
                raise ValueError(f"query {query.query_id} references an unknown chunk document")
        return self


def load_dataset(path: str | Path) -> BenchmarkDataset:
    """Load and fully validate a JSON benchmark dataset before model/vector work."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("benchmark dataset could not be read as valid JSON") from exc
    if isinstance(payload, dict) and payload.get("schema_version") == 2:
        # Reject before pydantic so v2 content is never echoed in v1 errors.
        raise ValueError(
            "dataset schema v2 is not supported by the v1 retrieval benchmark runner; "
            "use load_dataset_v2 (runner support is deferred to P1-B)"
        )
    return BenchmarkDataset.model_validate(payload)


def dataset_fingerprint(dataset: BenchmarkDataset) -> str:
    """Hash validated content for paired-run identity without serializing its text."""
    canonical = json.dumps(
        dataset.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Dataset schema v2 (P1-A): graded relevance, required source groups, evidence
# spans, document families and evidence lanes. The v1 runner does not consume
# v2 datasets; runtime integration is deferred to P1-B.
# ---------------------------------------------------------------------------

DATASET_SCHEMA_V2 = 2
LONG_DOCUMENT_MIN_WORDS = 1500
REAL_WORLD_STATUS_NOT_ESTABLISHED = "NOT YET ESTABLISHED"

StableId = Annotated[str, Field(pattern=_ID_RE.pattern)]
GroupId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]
Pseudonym = Annotated[str, Field(pattern=r"^r-[0-9a-f]{8}$")]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
GitSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]

Lane = Literal["real_representative", "synthetic_stress", "fixture"]
SourceClass = Literal["public_real", "internal_approved", "synthetic_authored", "synthetic_generated"]
AccessPolicy = Literal["public", "internal_restricted", "confidential_restricted"]
Domain = Literal[
    "hr",
    "it_access",
    "security_privacy",
    "procurement_finance",
    "operations",
    "support",
    "legal_compliance",
    "facilities_safety",
    "general",
]
CategoryV2 = Literal[
    "single_document_fact",
    "procedure",
    "multi_document",
    "cross_lingual",
    "long_document",
    "semantic_distractor",
    "near_duplicate",
    "current_vs_obsolete",
    "terminology",
    "unanswerable",
]
JudgmentFlag = Literal["obsolete_version", "wrong_variant", "confusable"]
JudgmentBasis = Literal["human_review", "fixture_authored", "legacy_expected_source"]
ReviewStatus = Literal[
    "generator_labeled",
    "unreviewed",
    "single_reviewed",
    "double_reviewed_agreed",
    "double_reviewed_adjudicated",
]
LimitationCode = Literal[
    "document_families_unavailable",
    "evidence_spans_unavailable",
    "expected_facts_not_represented",
    "historical_confusables_unjudged",
    "knowledge_base_scope_not_represented",
    "legacy_category_not_represented",
    "required_groups_may_be_incomplete",
    "retrieval_policy_not_represented",
]
Direction = Literal["same_language", "tr_to_en", "en_to_tr", "mixed_sources", "code_mixed", "not_applicable"]

_REAL_SOURCE_CLASSES = frozenset({"public_real", "internal_approved"})
_SYNTHETIC_SOURCE_CLASSES = frozenset({"synthetic_authored", "synthetic_generated"})
_REVIEWED_STATUSES = frozenset({"single_reviewed", "double_reviewed_agreed", "double_reviewed_adjudicated"})
_DOUBLE_REVIEWED_STATUSES = frozenset({"double_reviewed_agreed", "double_reviewed_adjudicated"})


class DatasetValidationError(ValueError):
    """Validation failure whose message never contains document, question or evidence text."""


def _validate_text(value: str, field: str) -> str:
    """Reject, never repair: offsets and digests must refer to the exact stored text."""
    for offset, character in enumerate(value):
        codepoint = ord(character)
        if character in "\n\t":
            continue
        if codepoint < 0x20 or 0x7F <= codepoint <= 0x9F or 0xD800 <= codepoint <= 0xDFFF or codepoint == 0xFEFF:
            raise ValueError(
                f"{field} contains a disallowed control, surrogate or byte-order-mark character "
                f"at code-point offset {offset}"
            )
    if not value.strip():
        raise ValueError(f"{field} must not be blank")
    if not unicodedata.is_normalized("NFC", value):
        raise ValueError(f"{field} must be NFC-normalized before labeling; the validator does not normalize")
    return value


def _require_trimmed(value: str, field: str) -> str:
    if value != value.strip():
        raise ValueError(f"{field} must not have leading or trailing whitespace")
    return value


def _require_unique(values: Iterable[str], field: str) -> None:
    values = list(values)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain duplicates")


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _V2Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LabelingGuideRef(_V2Model):
    version: Annotated[str, Field(pattern=r"^[0-9A-Za-z][0-9A-Za-z.\-]{0,39}$")]
    sha256: Sha256Hex


class LegacySource(_V2Model):
    corpus_version: StableId
    legacy_corpus_sha256: Sha256Hex
    legacy_dataset_sha256: Sha256Hex
    adapter_version: Literal["1"]
    limitations: list[LimitationCode] = Field(min_length=1)

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, values: list[str]) -> list[str]:
        _require_unique(values, "limitations")
        if values != sorted(values):
            raise ValueError("limitations must be sorted")
        return values


class RepresentativenessAttestation(_V2Model):
    attested_by: Pseudonym
    attested_on: date
    scope: str = Field(min_length=1, max_length=500)
    corpus_sha256: Sha256Hex

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return _require_trimmed(_validate_text(value, "scope"), "scope")


class UsageAuthorization(_V2Model):
    authorized_by: Pseudonym
    authorization_ref: str = Field(min_length=1, max_length=120)
    authorized_on: date

    @field_validator("authorization_ref")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        return _require_trimmed(_validate_text(value, "authorization_ref"), "authorization_ref")


class Extraction(_V2Model):
    """Records the exact, reproducible transform from extracted text to the labeled text."""

    extractor: Literal["app.services.documents.parser.extract_text"]
    extractor_source_sha: GitSha
    raw_text_sha256: Sha256Hex
    text_transform: Literal["none", "nfc", "lf_nfc"]


class Provenance(_V2Model):
    source_class: SourceClass
    source_ref: str = Field(min_length=1, max_length=300)
    license: str | None = Field(default=None, min_length=1, max_length=120)
    usage_authorization: UsageAuthorization | None = None
    access_policy: AccessPolicy
    original_sha256: Sha256Hex | None = None
    extraction: Extraction | None = None
    pii_review: Literal["not_required", "completed"]

    @field_validator("source_ref")
    @classmethod
    def validate_source_ref(cls, value: str) -> str:
        _require_trimmed(_validate_text(value, "source_ref"), "source_ref")
        if value.startswith(("/", "~")) or "\\" in value or "file:" in value.lower():
            raise ValueError("source_ref must not be a local filesystem path")
        return value

    @model_validator(mode="after")
    def validate_source_class(self) -> "Provenance":
        if self.source_class in _REAL_SOURCE_CLASSES:
            if self.original_sha256 is None or self.extraction is None:
                raise ValueError("real source documents require original_sha256 and extraction provenance")
        if self.source_class == "public_real":
            if self.license is None:
                raise ValueError("public_real documents require a license")
            if self.access_policy != "public":
                raise ValueError("public_real documents must use the public access policy")
        elif self.source_class == "internal_approved":
            if self.usage_authorization is None:
                raise ValueError("internal_approved documents require usage authorization")
            if self.access_policy == "public":
                raise ValueError("internal_approved documents must not use the public access policy")
            if self.pii_review != "completed":
                raise ValueError("internal_approved documents require a completed PII review")
        elif self.usage_authorization is not None:
            raise ValueError("synthetic documents must not carry usage authorization")
        return self


class DocumentV2(_V2Model):
    document_id: StableId
    language: Language
    text: str = Field(min_length=1, max_length=250_000)
    domain: Domain | None = None
    source_family_id: StableId
    translation_group_id: StableId | None = None
    variant_key: StableId | None = None
    version_label: str | None = Field(default=None, min_length=1, max_length=40)
    effective_from: date | None = None
    status: Literal["current", "superseded"] = "current"
    supersedes: list[StableId] = Field(default_factory=list)
    provenance: Provenance

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _validate_text(value, "document text")

    @field_validator("version_label")
    @classmethod
    def validate_version_label(cls, value: str | None) -> str | None:
        return None if value is None else _require_trimmed(_validate_text(value, "version_label"), "version_label")

    @model_validator(mode="after")
    def validate_document(self) -> "DocumentV2":
        _require_unique(self.supersedes, "supersedes")
        if self.document_id in self.supersedes:
            raise ValueError(f"document {self.document_id} cannot supersede itself")
        extraction = self.provenance.extraction
        if extraction is not None and extraction.text_transform == "none":
            if _text_sha256(self.text) != extraction.raw_text_sha256:
                raise ValueError(
                    f"document {self.document_id} text does not match raw_text_sha256 for text_transform 'none'"
                )
        return self


class EvidenceSpan(_V2Model):
    """Zero-based, end-exclusive Unicode code-point offsets into DocumentV2.text."""

    start: int = Field(ge=0)
    end: int = Field(ge=1)
    sha256: Sha256Hex
    supports_group: GroupId | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> "EvidenceSpan":
        if self.end <= self.start:
            raise ValueError("evidence spans must have end > start")
        return self


class Judgment(_V2Model):
    document_id: StableId
    grade: Literal[0, 1, 2]
    basis: JudgmentBasis
    flags: list[JudgmentFlag] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_judgment(self) -> "Judgment":
        _require_unique(self.flags, "flags")
        if self.flags and self.grade != 0:
            raise ValueError(f"judgment flags require grade 0 (document {self.document_id})")
        if self.grade == 0 and self.evidence:
            raise ValueError(f"grade 0 judgments cannot carry evidence (document {self.document_id})")
        if self.basis == "legacy_expected_source" and self.grade != 2:
            raise ValueError("legacy_expected_source judgments may only record grade 2")
        keys = [(span.start, span.end, span.supports_group) for span in self.evidence]
        if len(set(keys)) != len(keys):
            raise ValueError(f"duplicate evidence spans for document {self.document_id}")
        return self


class HistoricalRelationship(_V2Model):
    """A preserved legacy relationship; it is not a relevance judgment."""

    document_id: StableId
    relation: Literal["confusable"]
    legacy_corpus_version: StableId
    legacy_case_id: StableId
    legacy_document_id: int = Field(gt=0)


class RequiredGroup(_V2Model):
    """Satisfied when ANY member is retrieved; a query needs ALL of its groups."""

    group_id: GroupId
    members: list[StableId] = Field(min_length=1)

    @field_validator("members")
    @classmethod
    def validate_members(cls, values: list[str]) -> list[str]:
        _require_unique(values, "required group members")
        return values


class ReviewRecord(_V2Model):
    status: ReviewStatus
    guide_version: str | None = None
    reviewer_ids: list[Pseudonym] = Field(default_factory=list)
    adjudicator_id: Pseudonym | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    reviewed_on: date | None = None

    @model_validator(mode="after")
    def validate_review(self) -> "ReviewRecord":
        _require_unique(self.reviewer_ids, "reviewer_ids")
        expected_reviewers = {
            "generator_labeled": 0,
            "unreviewed": 0,
            "single_reviewed": 1,
            "double_reviewed_agreed": 2,
            "double_reviewed_adjudicated": 2,
        }[self.status]
        if len(self.reviewer_ids) != expected_reviewers:
            raise ValueError(f"review status {self.status} requires {expected_reviewers} reviewer(s)")
        reviewed = self.status in _REVIEWED_STATUSES
        details = (self.guide_version, self.confidence, self.reviewed_on)
        if reviewed and any(value is None for value in details):
            raise ValueError("reviewed queries require guide_version, confidence and reviewed_on")
        if not reviewed and any(value is not None for value in details):
            raise ValueError("unreviewed queries must not carry review details")
        if self.status == "double_reviewed_adjudicated":
            if self.adjudicator_id is None or self.adjudicator_id in self.reviewer_ids:
                raise ValueError("adjudicated reviews require an adjudicator who is not one of the reviewers")
        elif self.adjudicator_id is not None:
            raise ValueError("only adjudicated reviews may name an adjudicator")
        return self


class QueryV2(_V2Model):
    query_id: StableId
    scenario_id: StableId
    language: Language
    question: str = Field(min_length=1, max_length=12_000)
    primary_category: CategoryV2
    tags: list[CategoryV2] = Field(default_factory=list)
    temporal_intent: Literal["current", "historical"] = "current"
    answerable: bool
    required_groups: list[RequiredGroup] = Field(default_factory=list)
    judgments: list[Judgment] = Field(default_factory=list)
    historical_relationships: list[HistoricalRelationship] = Field(default_factory=list)
    review: ReviewRecord

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        return _require_trimmed(_validate_text(value, "question"), "question")

    @model_validator(mode="after")
    def validate_query(self) -> "QueryV2":
        qid = self.query_id
        _require_unique(self.tags, "tags")
        if self.primary_category in self.tags:
            raise ValueError(f"query {qid} repeats its primary category in tags")
        _require_unique([group.group_id for group in self.required_groups], "required group IDs")
        _require_unique([judgment.document_id for judgment in self.judgments], "judged documents")
        _require_unique([item.document_id for item in self.historical_relationships], "historical relationships")

        if self.answerable != bool(self.required_groups):
            raise ValueError(f"query {qid}: answerable queries need required groups and unanswerable ones none")
        if (self.primary_category == "unanswerable") == self.answerable or "unanswerable" in self.tags:
            raise ValueError(f"query {qid}: the unanswerable category must match answerable=false")

        judgments = {judgment.document_id: judgment for judgment in self.judgments}
        groups_by_member: dict[str, set[str]] = {}
        for group in self.required_groups:
            for member in group.members:
                groups_by_member.setdefault(member, set()).add(group.group_id)
                if member not in judgments or judgments[member].grade != 2:
                    raise ValueError(f"query {qid}: required group member {member} needs a grade 2 judgment")
        for judgment in self.judgments:
            if judgment.grade == 2 and judgment.document_id not in groups_by_member:
                raise ValueError(f"query {qid}: grade 2 document {judgment.document_id} must belong to a required group")
            if judgment.basis == "human_review" and self.review.status not in _REVIEWED_STATUSES:
                raise ValueError(f"query {qid}: human_review judgments require a reviewed query")
            for span in judgment.evidence:
                if judgment.grade == 2 and span.supports_group not in groups_by_member[judgment.document_id]:
                    raise ValueError(
                        f"query {qid}: evidence for {judgment.document_id} must support one of its required groups"
                    )
                if judgment.grade == 1 and span.supports_group is not None:
                    raise ValueError(f"query {qid}: supporting evidence must not claim a required group")
            if "obsolete_version" in judgment.flags and self.temporal_intent != "current":
                raise ValueError(f"query {qid}: obsolete_version flags require temporal_intent 'current'")
        for relationship in self.historical_relationships:
            if relationship.document_id in groups_by_member:
                raise ValueError(f"query {qid}: a required source cannot also be a historical confusable")

        categories = {self.primary_category, *self.tags}
        flags = {flag for judgment in self.judgments for flag in judgment.flags}
        if "multi_document" in categories and len(self.required_groups) < 2:
            raise ValueError(f"query {qid}: multi_document requires at least two required groups")
        if "single_document_fact" in categories and len(self.required_groups) != 1:
            raise ValueError(f"query {qid}: single_document_fact requires exactly one required group")
        if "current_vs_obsolete" in categories and "obsolete_version" not in flags:
            raise ValueError(f"query {qid}: current_vs_obsolete requires an obsolete_version judgment")
        if "near_duplicate" in categories and "wrong_variant" not in flags:
            raise ValueError(f"query {qid}: near_duplicate requires a wrong_variant judgment")
        if "semantic_distractor" in categories and "confusable" not in flags and not self.historical_relationships:
            raise ValueError(f"query {qid}: semantic_distractor requires a confusable judgment or relationship")
        return self


def derived_direction(query: QueryV2, documents: Mapping[str, DocumentV2]) -> Direction:
    """Language direction implied by the required groups; derived, never stored."""
    if not query.answerable:
        return "not_applicable"
    if query.language == "mixed":
        return "code_mixed"
    group_languages = [{documents[member].language for member in group.members} for group in query.required_groups]
    if all(query.language in languages or "mixed" in languages for languages in group_languages):
        return "same_language"
    if all(query.language not in languages for languages in group_languages):
        others = set().union(*group_languages)
        if others == {"en"} and query.language == "tr":
            return "tr_to_en"
        if others == {"tr"} and query.language == "en":
            return "en_to_tr"
    return "mixed_sources"


def _validate_evidence(query: QueryV2, judgment: Judgment, document: DocumentV2) -> None:
    text = document.text
    for span in judgment.evidence:
        location = f"query {query.query_id}, document {document.document_id}, span [{span.start}, {span.end})"
        if span.end > len(text):
            raise ValueError(f"{location} exceeds the document length in code points")
        if unicodedata.combining(text[span.start]) or (span.end < len(text) and unicodedata.combining(text[span.end])):
            raise ValueError(f"{location} splits a combining character sequence")
        quote = text[span.start:span.end]
        if not quote.strip():
            raise ValueError(f"{location} contains only whitespace")
        if _text_sha256(quote) != span.sha256:
            raise ValueError(f"{location} digest does not match the text (offsets are Unicode code points)")


class BenchmarkDatasetV2(_V2Model):
    schema_version: Literal[2]
    dataset_id: StableId
    dataset_version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
    title: str = Field(min_length=1, max_length=160)
    lane: Lane
    evidence_labels: Literal["character_spans", "unavailable"]
    labeling_guide: LabelingGuideRef | None = None
    legacy_source: LegacySource | None = None
    representativeness: RepresentativenessAttestation | None = None
    documents: list[DocumentV2] = Field(min_length=1)
    queries: list[QueryV2] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _require_trimmed(_validate_text(value, "title"), "title")

    @model_validator(mode="after")
    def validate_dataset(self) -> "BenchmarkDatasetV2":
        _require_unique([document.document_id for document in self.documents], "document IDs")
        _require_unique([query.query_id for query in self.queries], "query IDs")
        documents = {document.document_id: document for document in self.documents}
        self._validate_families(documents)
        self._validate_lane(documents)
        for query in self.queries:
            self._validate_query_against_documents(query, documents)
        if self.representativeness is not None:
            if self.lane != "real_representative":
                raise ValueError("representativeness attestations are only valid in the real_representative lane")
            if self.representativeness.corpus_sha256 != corpus_fingerprint_v2(self.documents):
                raise ValueError("representativeness attestation does not match the current corpus fingerprint")
        return self

    def _validate_families(self, documents: Mapping[str, DocumentV2]) -> None:
        superseded_targets: set[str] = set()
        for document in self.documents:
            for target_id in document.supersedes:
                target = documents.get(target_id)
                if target is None:
                    raise ValueError(f"document {document.document_id} supersedes an unknown document")
                if target.source_family_id != document.source_family_id or target.status != "superseded":
                    raise ValueError(
                        f"document {document.document_id} may only supersede superseded documents of its family"
                    )
                if document.effective_from and target.effective_from and target.effective_from >= document.effective_from:
                    raise ValueError(f"document {document.document_id} must take effect after {target_id}")
                superseded_targets.add(target_id)
        for document in self.documents:
            if document.status == "superseded" and document.document_id not in superseded_targets:
                raise ValueError(f"superseded document {document.document_id} is not superseded by any document")
        current_keys = Counter(
            (document.source_family_id, document.variant_key, document.language)
            for document in self.documents
            if document.status == "current"
        )
        if any(count > 1 for count in current_keys.values()):
            raise ValueError("a document family may have only one current document per variant and language")
        translation_groups: dict[str, list[DocumentV2]] = {}
        for document in self.documents:
            if document.translation_group_id is not None:
                translation_groups.setdefault(document.translation_group_id, []).append(document)
        for group_id, members in translation_groups.items():
            if len({member.language for member in members}) != len(members):
                raise ValueError(f"translation group {group_id} repeats a language")
            if len({(member.source_family_id, member.status, member.version_label) for member in members}) != 1:
                raise ValueError(f"translation group {group_id} must share family, status and version")

    def _validate_lane(self, documents: Mapping[str, DocumentV2]) -> None:
        classes = {document.provenance.source_class for document in self.documents}
        if self.lane == "real_representative":
            if not classes <= _REAL_SOURCE_CLASSES:
                raise ValueError("the real_representative lane must not contain synthetic documents")
            if self.evidence_labels != "character_spans" or self.labeling_guide is None:
                raise ValueError("the real_representative lane requires character spans and a labeling guide")
        if self.lane == "fixture":
            if not classes <= _SYNTHETIC_SOURCE_CLASSES:
                raise ValueError("fixture datasets may only contain synthetic documents")
            if any(document.provenance.access_policy != "public" for document in self.documents):
                raise ValueError("fixture datasets may only contain public documents")
        if self.legacy_source is not None and self.lane != "synthetic_stress":
            raise ValueError("legacy adapter output must use the synthetic_stress lane")
        reviewed = [query for query in self.queries if query.review.status in _REVIEWED_STATUSES]
        if reviewed and self.labeling_guide is None:
            raise ValueError("reviewed queries require a dataset labeling guide")
        for query in reviewed:
            if query.review.guide_version != self.labeling_guide.version:
                raise ValueError(f"query {query.query_id} was reviewed with a different labeling guide version")

    def _validate_query_against_documents(self, query: QueryV2, documents: Mapping[str, DocumentV2]) -> None:
        qid = query.query_id
        referenced = (
            [member for group in query.required_groups for member in group.members]
            + [judgment.document_id for judgment in query.judgments]
            + [relationship.document_id for relationship in query.historical_relationships]
        )
        if any(document_id not in documents for document_id in referenced):
            raise ValueError(f"query {qid} references an unknown document")
        if query.historical_relationships and self.legacy_source is None:
            raise ValueError(f"query {qid}: historical relationships are only valid in legacy adapter output")
        if self.lane == "real_representative" and query.review.status == "generator_labeled":
            raise ValueError(f"query {qid}: the real_representative lane does not accept generator labels")

        judgments = {judgment.document_id: judgment for judgment in query.judgments}
        members = {member for group in query.required_groups for member in group.members}
        for judgment in query.judgments:
            if judgment.basis == "fixture_authored" and self.lane != "fixture":
                raise ValueError(f"query {qid}: fixture_authored judgments are only valid in fixture datasets")
            if judgment.basis == "legacy_expected_source" and self.legacy_source is None:
                raise ValueError(f"query {qid}: legacy_expected_source judgments require a legacy source")
            if self.lane == "real_representative" and judgment.basis != "human_review":
                raise ValueError(f"query {qid}: the real_representative lane requires human_review judgments")
            if self.evidence_labels == "unavailable" and judgment.evidence:
                raise ValueError(f"query {qid}: evidence spans are not allowed when evidence labels are unavailable")
            document = documents[judgment.document_id]
            _validate_evidence(query, judgment, document)
            if "obsolete_version" in judgment.flags:
                if document.status != "superseded" or not any(
                    documents[member].source_family_id == document.source_family_id
                    and documents[member].status == "current"
                    for member in members
                ):
                    raise ValueError(
                        f"query {qid}: obsolete_version requires a superseded document whose family has a current "
                        "required source"
                    )
            if "wrong_variant" in judgment.flags and not any(
                documents[member].source_family_id == document.source_family_id
                and documents[member].variant_key is not None
                and document.variant_key is not None
                and documents[member].variant_key != document.variant_key
                for member in members
            ):
                raise ValueError(f"query {qid}: wrong_variant requires a different variant of a required source")

        for group in query.required_groups:
            for member in group.members:
                document = documents[member]
                if query.temporal_intent == "current" and document.status != "current":
                    raise ValueError(f"query {qid}: current questions cannot require superseded document {member}")
                if self.evidence_labels == "character_spans" and not any(
                    span.supports_group == group.group_id for span in judgments[member].evidence
                ):
                    raise ValueError(f"query {qid}: {member} has no evidence span for required group {group.group_id}")
                if document.translation_group_id is not None:
                    for sibling in self.documents:
                        if (
                            sibling.translation_group_id == document.translation_group_id
                            and sibling.document_id not in judgments
                        ):
                            raise ValueError(
                                f"query {qid}: translation sibling {sibling.document_id} of a required source is unjudged"
                            )

        categories = {query.primary_category, *query.tags}
        if "cross_lingual" in categories and derived_direction(query, documents) not in {"tr_to_en", "en_to_tr"}:
            raise ValueError(f"query {qid}: cross_lingual requires sources only in the other language")
        if "long_document" in categories and not any(
            len(documents[member].text.split()) >= LONG_DOCUMENT_MIN_WORDS for member in members
        ):
            raise ValueError(f"query {qid}: long_document requires a required source of at least {LONG_DOCUMENT_MIN_WORDS} words")


# ---------------------------------------------------------------- fingerprints

_FINGERPRINT_PREFIX = b"modai-retrieval-dataset-v2:"


def _fingerprint(tag: str, payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(_FINGERPRINT_PREFIX + tag.encode("utf-8") + b"\n" + canonical.encode("utf-8")).hexdigest()


def corpus_fingerprint_v2(documents: Iterable[DocumentV2]) -> str:
    """Identity of the retrieval-visible corpus; independent of list order."""
    return _fingerprint(
        "corpus",
        [
            {"document_id": document.document_id, "language": document.language, "text": document.text}
            for document in sorted(documents, key=lambda item: item.document_id)
        ],
    )


def _document_metadata(document: DocumentV2) -> dict:
    payload = document.model_dump(mode="json", exclude={"text"})
    payload["supersedes"] = sorted(payload["supersedes"])
    return payload


def _query_annotation(query: QueryV2) -> dict:
    return {
        "query_id": query.query_id,
        "scenario_id": query.scenario_id,
        "primary_category": query.primary_category,
        "tags": sorted(query.tags),
        "temporal_intent": query.temporal_intent,
        "answerable": query.answerable,
        "required_groups": sorted(
            ({"group_id": group.group_id, "members": sorted(group.members)} for group in query.required_groups),
            key=lambda group: group["group_id"],
        ),
        "judgments": sorted(
            (
                {
                    "document_id": judgment.document_id,
                    "grade": judgment.grade,
                    "basis": judgment.basis,
                    "flags": sorted(judgment.flags),
                    "evidence": sorted(
                        (span.model_dump(mode="json") for span in judgment.evidence),
                        key=lambda span: (span["start"], span["end"], span["supports_group"] or ""),
                    ),
                }
                for judgment in query.judgments
            ),
            key=lambda judgment: judgment["document_id"],
        ),
        "historical_relationships": sorted(
            (item.model_dump(mode="json") for item in query.historical_relationships),
            key=lambda item: item["document_id"],
        ),
    }


def _query_review(query: QueryV2) -> dict:
    review = query.review.model_dump(mode="json")
    review["reviewer_ids"] = sorted(review["reviewer_ids"])
    return {"query_id": query.query_id, "review": review}


@dataclass(frozen=True)
class DatasetFingerprints:
    corpus_sha256: str
    document_metadata_sha256: str
    queries_sha256: str
    annotation_sha256: str
    review_sha256: str
    dataset_sha256: str


def dataset_fingerprints_v2(dataset: BenchmarkDatasetV2) -> DatasetFingerprints:
    """Deterministic, order-independent identities. Model or run settings never enter them."""
    documents = sorted(dataset.documents, key=lambda item: item.document_id)
    queries = sorted(dataset.queries, key=lambda item: item.query_id)
    corpus = corpus_fingerprint_v2(documents)
    metadata = _fingerprint("document-metadata", [_document_metadata(document) for document in documents])
    query_inputs = _fingerprint(
        "queries",
        [{"query_id": query.query_id, "language": query.language, "question": query.question} for query in queries],
    )
    annotation = _fingerprint(
        "annotations",
        {
            "evidence_labels": dataset.evidence_labels,
            "labeling_guide_version": dataset.labeling_guide.version if dataset.labeling_guide else None,
            "queries": [_query_annotation(query) for query in queries],
        },
    )
    review = _fingerprint(
        "review",
        {
            "labeling_guide": dataset.labeling_guide.model_dump(mode="json") if dataset.labeling_guide else None,
            "representativeness": (
                dataset.representativeness.model_dump(mode="json") if dataset.representativeness else None
            ),
            "reviews": [_query_review(query) for query in queries],
        },
    )
    combined = _fingerprint(
        "dataset",
        {
            "schema_version": dataset.schema_version,
            "dataset_id": dataset.dataset_id,
            "dataset_version": dataset.dataset_version,
            "lane": dataset.lane,
            "legacy_source": dataset.legacy_source.model_dump(mode="json") if dataset.legacy_source else None,
            "corpus_sha256": corpus,
            "document_metadata_sha256": metadata,
            "queries_sha256": query_inputs,
            "annotation_sha256": annotation,
            "review_sha256": review,
        },
    )
    return DatasetFingerprints(corpus, metadata, query_inputs, annotation, review, combined)


# ---------------------------------------------------------------- assessment


@dataclass(frozen=True)
class DatasetAssessment:
    """Computed maturity facts; real-world status is never established at dataset level."""

    lane: str
    document_count: int
    real_document_count: int
    synthetic_document_count: int
    query_count: int
    answerable_query_count: int
    judgment_grade_counts: dict[int, int]
    unjudged_pair_count: int
    historical_relationship_count: int
    unjudged_historical_relationship_count: int
    review_status_counts: dict[str, int]
    human_review_complete: bool
    evidence_spans_present: bool
    provenance_complete: bool
    representativeness_attested: bool
    eligible_for_locking: bool
    real_world_benchmark_status: str = REAL_WORLD_STATUS_NOT_ESTABLISHED


def assess_dataset(dataset: BenchmarkDatasetV2) -> DatasetAssessment:
    real_documents = sum(document.provenance.source_class in _REAL_SOURCE_CLASSES for document in dataset.documents)
    grades = Counter(judgment.grade for query in dataset.queries for judgment in query.judgments)
    judged_pairs = sum(grades.values())
    historical = [(query, item) for query in dataset.queries for item in query.historical_relationships]
    unjudged_historical = sum(
        item.document_id not in {judgment.document_id for judgment in query.judgments} for query, item in historical
    )
    statuses = Counter(query.review.status for query in dataset.queries)
    human_review_complete = all(query.review.status in _DOUBLE_REVIEWED_STATUSES for query in dataset.queries)
    evidence = dataset.evidence_labels == "character_spans"
    provenance_complete = real_documents == len(dataset.documents)
    attested = dataset.representativeness is not None
    return DatasetAssessment(
        lane=dataset.lane,
        document_count=len(dataset.documents),
        real_document_count=real_documents,
        synthetic_document_count=len(dataset.documents) - real_documents,
        query_count=len(dataset.queries),
        answerable_query_count=sum(query.answerable for query in dataset.queries),
        judgment_grade_counts={grade: grades.get(grade, 0) for grade in (0, 1, 2)},
        unjudged_pair_count=len(dataset.documents) * len(dataset.queries) - judged_pairs,
        historical_relationship_count=len(historical),
        unjudged_historical_relationship_count=unjudged_historical,
        review_status_counts=dict(sorted(statuses.items())),
        human_review_complete=human_review_complete,
        evidence_spans_present=evidence,
        provenance_complete=provenance_complete,
        representativeness_attested=attested,
        eligible_for_locking=(
            dataset.lane == "real_representative" and human_review_complete and evidence and attested
        ),
    )


# ---------------------------------------------------------------- loading


def describe_validation_error(exc: ValidationError) -> str:
    """Field locations and messages only; never echoes submitted values."""
    messages = [
        f"{'.'.join(str(part) for part in error['loc']) or 'dataset'}: {error['msg']}"
        for error in exc.errors(include_input=False, include_url=False, include_context=False)
    ]
    return "; ".join(messages[:20])


def _read_dataset_payload(path: str | Path) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatasetValidationError("benchmark dataset could not be read as valid JSON") from exc
    if not isinstance(payload, dict):
        raise DatasetValidationError("benchmark dataset must be a JSON object")
    return payload


def validate_dataset_v2(payload: Mapping[str, Any]) -> BenchmarkDatasetV2:
    if payload.get("schema_version") != DATASET_SCHEMA_V2:
        raise DatasetValidationError("dataset schema_version must be 2")
    try:
        return BenchmarkDatasetV2.model_validate(payload)
    except ValidationError as exc:
        raise DatasetValidationError(describe_validation_error(exc)) from None


def load_dataset_v2(path: str | Path) -> BenchmarkDatasetV2:
    return validate_dataset_v2(_read_dataset_payload(path))


def load_any_dataset(path: str | Path) -> BenchmarkDataset | BenchmarkDatasetV2:
    """Explicit version dispatch; never upgrades v1 labels into v2 semantics."""
    payload = _read_dataset_payload(path)
    version = payload.get("schema_version")
    if version == DATASET_SCHEMA_V2 and not isinstance(version, bool):
        return validate_dataset_v2(payload)
    if version == 1 and not isinstance(version, bool):
        try:
            return BenchmarkDataset.model_validate(payload)
        except ValidationError as exc:
            raise DatasetValidationError(describe_validation_error(exc)) from None
    raise DatasetValidationError("dataset schema_version must be 1 or 2")
