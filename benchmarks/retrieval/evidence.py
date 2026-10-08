"""Deterministic evidence mapping for production word chunks (retrieval benchmark P1-B1).

Production ``chunk_text`` splits text on Unicode whitespace (``str.split()``) and joins
each window of words with one U+0020. A chunk is therefore not generally a substring of
its source: line breaks, tabs and repeated spaces are normalized, and identical passages
can occur at several offsets. This module never searches for chunk or evidence text. It
derives each chunk's source range from word positions, proves the derivation by
rebuilding every chunk and comparing it with production ``chunk_text`` output, and fails
closed on any mismatch.

Coverage vocabulary (offsets are Unicode code points of the dataset text):

- content code points: non-whitespace code points. Each belongs to exactly one word and
  appears verbatim in every chunk that contains the word.
- token coverage: every word touched by an evidence span lies inside retrieved chunks, so
  every content code point of the span is present in the retrieved chunk text. Source
  whitespace is never claimed, because chunks replace it with single spaces.
- literal coverage: the exact span text, whitespace included, appears inside ONE chunk at
  the mapped position.

These are retrieval-side facts only. Whether a chunk reached the assembled LLM context,
or was used correctly in an answer, is outside this module.

Pure: no I/O, no Qdrant, no models, no settings. Errors name document IDs, chunk indexes
and offsets, never text.
"""

from __future__ import annotations

import bisect
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.services.rag.chunker import chunk_text

MAPPING_VERSION = "word-offsets-v1"


class EvidenceMappingError(ValueError):
    """Fail-closed mapping error; messages carry identifiers and offsets, never text."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_id(document_id: str, chunk_index: int) -> str:
    return f"{document_id}::chunk-{chunk_index:04d}"


def word_spans(text: str) -> tuple[tuple[int, int], ...]:
    """[start, end) ranges of maximal non-whitespace runs, exactly the words of ``text.split()``."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, character in enumerate(text):
        if character.isspace():
            if start is not None:
                spans.append((start, index))
                start = None
        elif start is None:
            start = index
    if start is not None:
        spans.append((start, len(text)))
    if [text[a:b] for a, b in spans] != text.split():
        raise EvidenceMappingError("word segmentation does not reproduce str.split()")
    return tuple(spans)


def _word_windows(word_count: int, chunk_size: int, chunk_overlap: int) -> list[tuple[int, int]]:
    # Mirrors app.services.rag.chunker.chunk_text; map_document_chunks proves the mirror.
    windows: list[tuple[int, int]] = []
    step = chunk_size - chunk_overlap
    start = 0
    while start < word_count:
        end = min(start + chunk_size, word_count)
        windows.append((start, end))
        if end == word_count:
            break
        start += step
    return windows


@dataclass(frozen=True)
class ChunkSpan:
    """Source range of one production chunk; identity is (document_id, chunk_index), never text."""

    document_id: str
    chunk_index: int
    word_start: int
    word_end: int  # exclusive
    char_start: int  # first code point of the first word
    char_end: int  # one past the last code point of the last word
    text_sha256: str  # digest of the production chunk text

    @property
    def chunk_id(self) -> str:
        return chunk_id(self.document_id, self.chunk_index)


@dataclass(frozen=True)
class DocumentChunkMap:
    document_id: str
    text_length: int
    text_sha256: str
    chunk_size: int
    chunk_overlap: int
    words: tuple[tuple[int, int], ...]
    single_space_gaps: tuple[bool, ...]  # gap i separates word i and word i + 1
    chunks: tuple[ChunkSpan, ...]
    mapping_version: str = MAPPING_VERSION

    @property
    def whitespace_normalized(self) -> bool:
        """True when some chunk renders a source gap that is not exactly one U+0020."""
        return not all(self.single_space_gaps)


def map_document_chunks(
    document_id: str,
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    indexed_chunk_texts: Sequence[str] | None = None,
) -> DocumentChunkMap:
    """Map every production chunk of ``text`` to its source code-point range.

    ``text`` is used exactly as given (for schema v2: the NFC/LF ``DocumentV2.text`` the
    labels refer to); nothing is normalized here. When ``indexed_chunk_texts`` is given
    (the chunk texts actually indexed), it must equal the production output.
    """
    try:
        production = chunk_text(text, chunk_size, chunk_overlap)
    except ValueError as exc:
        raise EvidenceMappingError(f"document {document_id}: invalid chunk configuration") from exc
    words = word_spans(text)
    windows = _word_windows(len(words), chunk_size, chunk_overlap)
    if len(windows) != len(production):
        raise EvidenceMappingError(f"document {document_id}: chunk count does not match production chunk_text")
    chunks: list[ChunkSpan] = []
    for index, ((word_start, word_end), produced) in enumerate(zip(windows, production, strict=True)):
        rebuilt = " ".join(text[a:b] for a, b in words[word_start:word_end])
        if rebuilt != produced:
            raise EvidenceMappingError(
                f"document {document_id}: chunk {index} does not match production chunk_text output"
            )
        chunks.append(
            ChunkSpan(
                document_id=document_id,
                chunk_index=index,
                word_start=word_start,
                word_end=word_end,
                char_start=words[word_start][0],
                char_end=words[word_end - 1][1],
                text_sha256=_sha256(produced),
            )
        )
    if indexed_chunk_texts is not None and list(indexed_chunk_texts) != production:
        raise EvidenceMappingError(f"document {document_id}: indexed chunks differ from production chunk_text output")
    gaps = tuple(text[words[i][1]:words[i + 1][0]] == " " for i in range(len(words) - 1))
    return DocumentChunkMap(
        document_id=document_id,
        text_length=len(text),
        text_sha256=_sha256(text),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        words=words,
        single_space_gaps=gaps,
        chunks=tuple(chunks),
    )


@dataclass(frozen=True)
class MappedSpan:
    """A verified evidence span located by word positions."""

    document_id: str
    document_text_sha256: str  # the exact text the span was verified against
    start: int
    end: int
    sha256: str
    group_id: str | None
    first_word: int
    last_word: int  # inclusive
    content_codepoints: int
    literal_eligible: bool  # starts and ends on content and every inner gap is one U+0020


def map_evidence_span(
    document_map: DocumentChunkMap,
    text: str,
    *,
    start: int,
    end: int,
    sha256: str,
    group_id: str | None = None,
) -> MappedSpan:
    """Verify a span against the exact text the map was built from and locate its words."""
    location = f"document {document_map.document_id}, span [{start}, {end})"
    if _sha256(text) != document_map.text_sha256:
        raise EvidenceMappingError(f"document {document_map.document_id}: text differs from the chunk map")
    if not (0 <= start < end <= len(text)):
        raise EvidenceMappingError(f"{location} is outside the document")
    if _sha256(text[start:end]) != sha256:
        raise EvidenceMappingError(f"{location} digest does not match the text")
    words = document_map.words
    first_word = bisect.bisect_right([word_end for _, word_end in words], start)
    last_word = bisect.bisect_left([word_start for word_start, _ in words], end) - 1
    if first_word > last_word:
        raise EvidenceMappingError(f"{location} contains no content code points")
    content = sum(min(b, end) - max(a, start) for a, b in words[first_word:last_word + 1])
    literal_eligible = (
        not text[start].isspace()
        and not text[end - 1].isspace()
        and all(document_map.single_space_gaps[first_word:last_word])
    )
    return MappedSpan(
        document_id=document_map.document_id,
        document_text_sha256=document_map.text_sha256,
        start=start,
        end=end,
        sha256=sha256,
        group_id=group_id,
        first_word=first_word,
        last_word=last_word,
        content_codepoints=content,
        literal_eligible=literal_eligible,
    )


@dataclass(frozen=True)
class SpanCoverage:
    span: MappedSpan
    document_retrieved: bool
    covering_chunk_indexes: tuple[int, ...]  # retrieved chunks touching the span, ascending
    covered_content_codepoints: int
    union_covered: bool  # token coverage by the union of retrieved chunks
    single_chunk_covered: bool  # token coverage by one retrieved chunk
    literal_single_chunk: bool  # exact span text inside one retrieved chunk


def _retrieved_chunks(document_map: DocumentChunkMap, chunk_indexes: Iterable[int]) -> list[ChunkSpan]:
    indexes = sorted(set(chunk_indexes))
    for index in indexes:
        if not 0 <= index < len(document_map.chunks):
            raise EvidenceMappingError(f"document {document_map.document_id}: unknown chunk index {index}")
    return [document_map.chunks[index] for index in indexes]


def span_coverage(
    document_map: DocumentChunkMap, span: MappedSpan, retrieved_chunk_indexes: Iterable[int]
) -> SpanCoverage:
    """Coverage of ``span`` by the given retrieved chunks of the same document."""
    if span.document_id != document_map.document_id:
        raise EvidenceMappingError(f"span for {span.document_id} checked against {document_map.document_id}")
    if span.document_text_sha256 != document_map.text_sha256:
        raise EvidenceMappingError(f"document {span.document_id}: span was mapped against different text")
    chunks = _retrieved_chunks(document_map, retrieved_chunk_indexes)
    covered_codepoints = 0
    uncovered = False
    for word in range(span.first_word, span.last_word + 1):
        a, b = document_map.words[word]
        if any(chunk.word_start <= word < chunk.word_end for chunk in chunks):
            covered_codepoints += min(b, span.end) - max(a, span.start)
        else:
            uncovered = True
    single = any(chunk.word_start <= span.first_word and span.last_word < chunk.word_end for chunk in chunks)
    return SpanCoverage(
        span=span,
        document_retrieved=bool(chunks),
        covering_chunk_indexes=tuple(
            chunk.chunk_index
            for chunk in chunks
            if chunk.word_start <= span.last_word and span.first_word < chunk.word_end
        ),
        covered_content_codepoints=covered_codepoints,
        union_covered=not uncovered,
        single_chunk_covered=single,
        literal_single_chunk=single and span.literal_eligible,
    )


def literal_chunk_offsets(document_map: DocumentChunkMap, span: MappedSpan, chunk_index: int) -> tuple[int, int] | None:
    """[a, b) in the chunk text that reproduces the span literally, or None if it does not."""
    (chunk,) = _retrieved_chunks(document_map, (chunk_index,))
    if not (span.literal_eligible and chunk.word_start <= span.first_word and span.last_word < chunk.word_end):
        return None
    words = document_map.words

    def offset(position: int, word: int) -> int:
        preceding = sum(b - a for a, b in words[chunk.word_start:word]) + (word - chunk.word_start)
        return preceding + position - words[word][0]

    return offset(span.start, span.first_word), offset(span.end - 1, span.last_word) + 1
