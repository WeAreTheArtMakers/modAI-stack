from app.services.rag.chunker import chunk_text
from app.services.rag.pipeline import build_rag_prompt
def test_chunking_and_prompt_boundary():
    chunks = chunk_text("one two three four five", 3, 1)
    prompt = build_rag_prompt("what?", chunks)
    assert len(chunks) == 2 and "SYSTEM INSTRUCTIONS" in prompt and "untrusted" in prompt

def test_chunk_text_empty_input_returns_no_chunks():
    assert chunk_text("", 3, 1) == []

def test_chunk_text_preserves_overlap_between_chunks():
    assert chunk_text("one two three four five six", 3, 1) == [
        "one two three",
        "three four five",
        "five six",
    ]

def test_chunk_text_rejects_invalid_parameters():
    for size, overlap in [(0, 0), (-1, 0), (3, -1), (3, 3), (3, 4)]:
        try:
            chunk_text("one two", size, overlap)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid chunk parameters should raise ValueError")
