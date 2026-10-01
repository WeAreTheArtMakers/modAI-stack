def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0:
        raise ValueError("chunk size must be greater than zero")
    if overlap < 0:
        raise ValueError("chunk overlap must be non-negative")
    if overlap >= size:
        raise ValueError("chunk overlap must be smaller than chunk size")

    words = text.split()
    chunks: list[str] = []
    step = size - overlap
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        chunks.append(" ".join(words[start:end]))
        # Do not emit a final overlap-only chunk after this chunk reaches EOF.
        if end == len(words):
            break
        start += step
    return chunks
