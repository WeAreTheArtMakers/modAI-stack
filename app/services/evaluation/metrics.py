"""Deterministic retrieval, source, and fact metrics without a judge model."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


def normalize_text(value: str) -> str:
    """Normalize Unicode, case, and whitespace for conservative string matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    # Unicode casefold represents Turkish dotted capital I as ``i`` plus a
    # combining dot. Treat that canonical spelling like a regular lowercase i
    # while retaining all other characters for conservative fact matching.
    normalized = normalized.replace("\u0307", "")
    return re.sub(r"\s+", " ", normalized).strip()


def document_matches(expected: Iterable[str], returned: Iterable[str]) -> list[bool]:
    expected_values = {normalize_text(value) for value in expected}
    return [normalize_text(value) in expected_values for value in returned]


def hit_at_k(expected: Iterable[str], returned: Iterable[str]) -> bool | None:
    expected_values = {normalize_text(value) for value in expected}
    if not expected_values:
        return None
    return any(normalize_text(value) in expected_values for value in returned)


def reciprocal_rank(expected: Iterable[str], returned: Iterable[str]) -> float | None:
    expected_values = {normalize_text(value) for value in expected}
    if not expected_values:
        return None
    for index, value in enumerate(returned, start=1):
        if normalize_text(value) in expected_values:
            return 1.0 / index
    return 0.0


def supported_fact_count(expected_facts: Iterable[str], source_texts: Iterable[str | None]) -> int:
    source_context = normalize_text(" ".join(text or "" for text in source_texts))
    return sum(bool(normalize_text(fact)) and normalize_text(fact) in source_context for fact in expected_facts)


def fact_coverage(expected_facts: Iterable[str], source_texts: Iterable[str | None]) -> float | None:
    facts = list(expected_facts)
    if not facts:
        return None
    return supported_fact_count(facts, source_texts) / len(facts)


def answer_fact_groundedness(
    expected_facts: Iterable[str], source_texts: Iterable[str | None], answer: str | None,
) -> float | None:
    """Count expected facts present in both the generated answer and retrieved context.

    This is a deterministic support signal, not a semantic LLM-judge score.
    """
    if answer is None:
        return None
    facts = list(expected_facts)
    if not facts:
        return None
    normalized_answer = normalize_text(answer)
    normalized_context = normalize_text(" ".join(text or "" for text in source_texts))
    supported = sum(
        bool(normalize_text(fact))
        and normalize_text(fact) in normalized_answer
        and normalize_text(fact) in normalized_context
        for fact in facts
    )
    return supported / len(facts)
