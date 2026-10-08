import hashlib
import random

import pytest

from app.services.rag.chunker import chunk_text
from benchmarks.retrieval import evidence
from benchmarks.retrieval.evidence import (
    EvidenceMappingError,
    literal_chunk_offsets,
    map_document_chunks,
    map_evidence_span,
    span_coverage,
    word_spans,
)
from benchmarks.retrieval.schema import load_dataset_v2


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _span(document_map, text, start, end, group_id=None):
    return map_evidence_span(document_map, text, start=start, end=end, sha256=_sha(text[start:end]), group_id=group_id)


REPEATED = "Expense rule.\nApprove within 10 days.\n\nExpense rule.\nApprove within 10 days."
WHITESPACE = [" ", "  ", "\n", "\n\n", "\t", " \t ", " ", "　", " ", "\x1c", " "]
WORDS = ["İzin", "ıslak", "şoför", "Öğle", "çay", "ğ", "EUR", "40", "naïve", "é", "a.b", "—", "日本", "x"]


def _random_text(rng: random.Random, words: int) -> str:
    pieces = [rng.choice(WHITESPACE) if rng.random() < 0.3 else ""]
    for index in range(words):
        pieces.append(rng.choice(WORDS))
        if index < words - 1:
            pieces.append(rng.choice(WHITESPACE))
    pieces.append(rng.choice(WHITESPACE) if rng.random() < 0.3 else "")
    return "".join(pieces)


def test_split_and_isspace_agree_on_every_code_point():
    # word_spans relies on str.isspace() reproducing str.split()'s separators.
    for code_point in range(0x110000):
        if 0xD800 <= code_point <= 0xDFFF:
            continue
        character = chr(code_point)
        assert (("a" + character + "b").split() == ["a", "b"]) == character.isspace()


@pytest.mark.parametrize("size, overlap", [(1, 0), (2, 1), (3, 0), (4, 1), (8, 2), (700, 100)])
def test_chunk_ranges_reproduce_production_chunks_on_varied_whitespace(size, overlap):
    rng = random.Random(f"{size}/{overlap}")
    for _ in range(40):
        text = _random_text(rng, rng.randint(1, 30))
        production = chunk_text(text, size, overlap)
        document_map = map_document_chunks("doc-a", text, chunk_size=size, chunk_overlap=overlap)
        assert len(document_map.chunks) == len(production)
        for index, (chunk, produced) in enumerate(zip(document_map.chunks, production, strict=True)):
            source = text[chunk.char_start:chunk.char_end]
            # Independent oracle: the source range, whitespace-normalized, is the chunk.
            assert " ".join(source.split()) == produced
            assert not source[0].isspace() and not source[-1].isspace()
            assert chunk.char_start == 0 or text[chunk.char_start - 1].isspace()
            assert chunk.char_end == len(text) or text[chunk.char_end].isspace()
            assert (chunk.chunk_index, chunk.chunk_id) == (index, f"doc-a::chunk-{index:04d}")
            assert chunk.text_sha256 == _sha(produced)


def test_repeated_paragraphs_are_mapped_by_position_not_by_text():
    document_map = map_document_chunks("doc-a", REPEATED, chunk_size=4, chunk_overlap=0)
    assert [(c.char_start, c.char_end) for c in document_map.chunks] == [(0, 28), (29, 52), (53, 76)]
    production = chunk_text(REPEATED, 4, 0)
    assert production == ["Expense rule. Approve within", "10 days. Expense rule.", "Approve within 10 days."]
    assert REPEATED.count("Expense rule.") == 2
    assert production[0] not in REPEATED  # the chunk is not a source substring

    first = _span(document_map, REPEATED, 0, 13)
    second = _span(document_map, REPEATED, 39, 52)
    assert first.sha256 == second.sha256  # identical text, different evidence

    # Chunk 0 contains the words "Expense rule." but only at the FIRST occurrence.
    only_first_chunk = span_coverage(document_map, second, [0])
    assert only_first_chunk.document_retrieved and not only_first_chunk.union_covered
    assert only_first_chunk.covered_content_codepoints == 0
    assert span_coverage(document_map, first, [0]).literal_single_chunk

    second_in_chunk_1 = span_coverage(document_map, second, [1])
    assert second_in_chunk_1.union_covered and second_in_chunk_1.single_chunk_covered
    assert second_in_chunk_1.literal_single_chunk
    assert literal_chunk_offsets(document_map, second, 1) == (9, 22)
    assert production[1][9:22] == REPEATED[39:52]


def test_whitespace_normalization_never_claims_source_whitespace():
    text = "Meal  allowance:\n\t40 EUR per day."
    document_map = map_document_chunks("doc-a", text, chunk_size=700, chunk_overlap=100)
    assert document_map.whitespace_normalized
    assert chunk_text(text, 700, 100) == ["Meal allowance: 40 EUR per day."]

    span = _span(document_map, text, 6, 24)  # "allowance:\n\t40 EUR"
    assert text[6:24] == "allowance:\n\t40 EUR"
    assert span.content_codepoints == len("allowance:") + len("40") + len("EUR") == 15
    coverage = span_coverage(document_map, span, [0])
    assert coverage.union_covered and coverage.single_chunk_covered
    assert coverage.covered_content_codepoints == 15  # "\n\t" is not counted as delivered
    assert not coverage.literal_single_chunk
    assert literal_chunk_offsets(document_map, span, 0) is None

    leading = _span(document_map, text, 4, 15)  # starts in the double space
    assert leading.content_codepoints == len("allowance") and not leading.literal_eligible

    exact = _span(document_map, text, 21, 33)  # "EUR per day."
    assert literal_chunk_offsets(document_map, exact, 0) == (19, 31)
    assert chunk_text(text, 700, 100)[0][19:31] == text[21:33]


def test_span_starting_inside_a_word_counts_only_its_own_code_points():
    text = "Reimbursement requires receipts."
    document_map = map_document_chunks("doc-a", text, chunk_size=700, chunk_overlap=100)
    span = _span(document_map, text, 2, 22)  # "imbursement requires"
    assert (span.first_word, span.last_word, span.content_codepoints) == (0, 1, 11 + 8)
    assert literal_chunk_offsets(document_map, span, 0) == (2, 22)


def test_evidence_spanning_two_overlapping_chunks_and_uncovered_evidence():
    dataset = load_dataset_v2("benchmarks/retrieval/datasets/v2/example.json")
    text = next(d.text for d in dataset.documents if d.document_id == "travel-policy-2025-en")
    document_map = map_document_chunks("travel-policy-2025-en", text, chunk_size=8, chunk_overlap=2)
    assert [(c.char_start, c.char_end) for c in document_map.chunks] == [
        (0, 54), (45, 98), (83, 128), (116, 157), (149, 184),
    ]
    span = _span(document_map, text, 45, 110, "a")
    assert (span.first_word, span.last_word) == (6, 16)
    words = text.split()

    two_chunks = span_coverage(document_map, span, [2, 1])
    assert two_chunks.union_covered and not two_chunks.single_chunk_covered
    assert two_chunks.covering_chunk_indexes == (1, 2)
    # Words 12-13 sit in both overlapping chunks and are counted once.
    assert two_chunks.covered_content_codepoints == span.content_codepoints == sum(map(len, words[6:17]))
    assert not two_chunks.literal_single_chunk

    wrong_chunks = span_coverage(document_map, span, [0, 3])
    assert wrong_chunks.document_retrieved and not wrong_chunks.union_covered
    assert wrong_chunks.covered_content_codepoints == len(words[6]) + len(words[7])

    unrelated = span_coverage(document_map, span, [4])
    assert unrelated.document_retrieved and unrelated.covering_chunk_indexes == ()
    assert span_coverage(document_map, span, []).document_retrieved is False


def test_literal_offsets_reproduce_span_text_inside_production_chunks():
    rng = random.Random("literal")
    checked = 0
    for _ in range(300):
        text = _random_text(rng, rng.randint(2, 20))
        size = rng.randint(2, 6)
        overlap = rng.randint(0, size - 1)
        document_map = map_document_chunks("doc-a", text, chunk_size=size, chunk_overlap=overlap)
        production = chunk_text(text, size, overlap)
        start = rng.randrange(len(text))
        end = rng.randint(start + 1, len(text))
        if not text[start:end].strip():
            continue
        span = _span(document_map, text, start, end)
        for chunk in document_map.chunks:
            offsets = literal_chunk_offsets(document_map, span, chunk.chunk_index)
            inside = chunk.word_start <= span.first_word and span.last_word < chunk.word_end
            if offsets is not None:
                a, b = offsets
                assert production[chunk.chunk_index][a:b] == text[start:end]
                checked += 1
            elif inside:
                quote = text[start:end]
                assert quote != quote.strip() or any(
                    gap and gap != " " for gap in _gaps(quote)
                )
    assert checked > 50


def _gaps(quote: str) -> list[str]:
    spans = word_spans(quote)
    return [quote[spans[i][1]:spans[i + 1][0]] for i in range(len(spans) - 1)]


def test_reconstruction_mismatch_with_indexed_chunks_fails_closed():
    with pytest.raises(EvidenceMappingError, match="indexed chunks differ"):
        map_document_chunks(
            "doc-a", REPEATED, chunk_size=4, chunk_overlap=0,
            indexed_chunk_texts=["Expense rule. Approve within", "10 days. Expense rule.", "Approve within 10 days"],
        )
    assert map_document_chunks(
        "doc-a", REPEATED, chunk_size=4, chunk_overlap=0, indexed_chunk_texts=chunk_text(REPEATED, 4, 0)
    ).chunks


def test_production_chunker_drift_fails_closed(monkeypatch):
    def newline_joined(text, size, overlap):
        return [chunk.replace(" ", "\n") for chunk in chunk_text(text, size, overlap)]

    monkeypatch.setattr(evidence, "chunk_text", newline_joined)
    with pytest.raises(EvidenceMappingError, match="does not match production"):
        map_document_chunks("doc-a", REPEATED, chunk_size=4, chunk_overlap=0)
    monkeypatch.setattr(evidence, "chunk_text", lambda text, size, overlap: chunk_text(text, size, overlap)[:-1])
    with pytest.raises(EvidenceMappingError, match="chunk count"):
        map_document_chunks("doc-a", REPEATED, chunk_size=4, chunk_overlap=0)


@pytest.mark.parametrize(
    "start, end, digest, message",
    [
        (0, 13, "0" * 64, "digest does not match"),
        (70, 77, None, "outside the document"),
        (13, 14, None, "no content code points"),  # "\n"
        (37, 39, None, "no content code points"),  # "\n\n"
    ],
)
def test_invalid_spans_fail_closed_without_echoing_text(start, end, digest, message):
    document_map = map_document_chunks("doc-a", REPEATED, chunk_size=4, chunk_overlap=0)
    with pytest.raises(EvidenceMappingError, match=message) as error:
        map_evidence_span(
            document_map, REPEATED, start=start, end=end, sha256=digest or _sha(REPEATED[start:end])
        )
    assert "Expense" not in str(error.value) and "Approve" not in str(error.value)


def test_span_text_must_be_the_mapped_text_and_chunks_must_exist():
    document_map = map_document_chunks("doc-a", REPEATED, chunk_size=4, chunk_overlap=0)
    altered = REPEATED.replace("10", "14")
    with pytest.raises(EvidenceMappingError, match="differs from the chunk map"):
        map_evidence_span(document_map, altered, start=0, end=13, sha256=_sha(altered[0:13]))
    span = _span(document_map, REPEATED, 0, 13)
    with pytest.raises(EvidenceMappingError, match="unknown chunk index 3"):
        span_coverage(document_map, span, [3])
    other = map_document_chunks("doc-b", REPEATED, chunk_size=4, chunk_overlap=0)
    with pytest.raises(EvidenceMappingError, match="checked against doc-b"):
        span_coverage(other, span, [0])
    altered_map = map_document_chunks("doc-a", altered, chunk_size=4, chunk_overlap=0)
    with pytest.raises(EvidenceMappingError, match="mapped against different text"):
        span_coverage(altered_map, span, [0])


@pytest.mark.parametrize("size, overlap", [(0, 0), (4, 4), (4, -1)])
def test_invalid_chunk_configuration_fails_closed(size, overlap):
    with pytest.raises(EvidenceMappingError, match="invalid chunk configuration"):
        map_document_chunks("doc-a", REPEATED, chunk_size=size, chunk_overlap=overlap)
