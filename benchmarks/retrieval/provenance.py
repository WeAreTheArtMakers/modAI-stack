"""Benchmark source provenance, kept separate from deployed-runtime provenance."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path


SOURCE_SHA_ORIGINS = frozenset({"explicit", "git", "unavailable"})
_SHA_RE = re.compile(r"[0-9a-f]{40}")


def normalize_source_sha(value: str) -> str:
    """Accept exactly 40 hexadecimal characters and return them lowercase."""
    normalized = value.lower()
    if not _SHA_RE.fullmatch(normalized):
        raise ValueError("--source-sha must be exactly 40 hexadecimal characters")
    return normalized


def discover_git_sha() -> str | None:
    """Best-effort HEAD of the repository containing the benchmark source.

    Returns None when git tooling or .git metadata is unavailable, as in the
    isolated benchmark container.
    """
    try:
        output = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip().lower()
    except (OSError, subprocess.SubprocessError):
        return None
    return output if _SHA_RE.fullmatch(output) else None


def resolve_source_sha(
    explicit: str | None,
    discover: Callable[[], str | None] = discover_git_sha,
) -> tuple[str | None, str]:
    """Explicit value wins; git discovery is only a fallback; otherwise unavailable."""
    if explicit is not None:
        return normalize_source_sha(explicit), "explicit"
    discovered = discover()
    if discovered is not None and _SHA_RE.fullmatch(discovered.lower()):
        return discovered.lower(), "git"
    return None, "unavailable"


def normalize_runtime_build_sha(value: str | None) -> str | None:
    """Image BUILD_SHA of the dependency runtime; never a benchmark source SHA."""
    if value is None:
        return None
    normalized = value.lower()
    return normalized if _SHA_RE.fullmatch(normalized) else None


def validate_source_provenance(source_sha: str | None, origin: str) -> None:
    if origin not in SOURCE_SHA_ORIGINS:
        raise ValueError("source_sha_origin must be explicit, git or unavailable")
    if (origin == "unavailable") != (source_sha is None):
        raise ValueError("source_sha must be present exactly when its origin is explicit or git")
    if source_sha is not None and not _SHA_RE.fullmatch(source_sha):
        raise ValueError("source_sha must be 40 lowercase hexadecimal characters")
