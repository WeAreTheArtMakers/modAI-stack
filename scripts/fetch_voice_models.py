#!/usr/bin/env python3
"""Download the modAI Voice browser models pinned in frontend/voice-models.lock.json.

Files come from huggingface.co at the exact revision in the lock file and are written to
frontend/public/voice-models/<directory>/ only after their size and SHA-256 match. Vite serves
that folder in development and copies it into the production build, so the browser loads
every model from the application origin. The folder is git-ignored; never commit weights.

Usage:
  python3 scripts/fetch_voice_models.py            # download missing or changed files
  python3 scripts/fetch_voice_models.py --check    # verify only, no network
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "frontend" / "voice-models.lock.json"
DEFAULT_DEST = ROOT / "frontend" / "public" / "voice-models"
CHUNK = 1 << 20


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe path in lock file: {value!r}")
    return path


def _download(url: str, target: Path, expected_size: int, expected_sha: str) -> None:
    partial = target.with_name(target.name + ".partial")
    digest = hashlib.sha256()
    size = 0
    request = urllib.request.Request(url, headers={"User-Agent": "modai-voice-model-fetch/1"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
        for block in iter(lambda: response.read(CHUNK), b""):
            handle.write(block)
            digest.update(block)
            size += len(block)
    if size != expected_size or digest.hexdigest() != expected_sha:
        partial.unlink(missing_ok=True)
        raise ValueError(f"{target.name}: size or SHA-256 mismatch (got {size} bytes)")
    partial.replace(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify existing files without downloading")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args(argv)

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if lock.get("lock_version") != 1:
        raise SystemExit("unsupported voice model lock version")
    problems = 0
    total = 0
    for model in lock["models"]:
        directory = args.dest / _safe_relative(model["directory"])
        print(f"{model['id']}: {model['repository']} @ {model['revision']} ({model['license']})")
        for entry in model["files"]:
            relative = _safe_relative(entry["path"])
            target = directory / relative
            total += entry["size"]
            if target.is_file() and target.stat().st_size == entry["size"] and _sha256(target) == entry["sha256"]:
                print(f"  ok        {relative}")
                continue
            if args.check:
                print(f"  MISSING   {relative}")
                problems += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            url = f"https://huggingface.co/{model['repository']}/resolve/{model['revision']}/{relative}"
            print(f"  download  {relative} ({entry['size'] / 1e6:.1f} MB)", flush=True)
            try:
                _download(url, target, entry["size"], entry["sha256"])
            except Exception as exc:  # report every file, then fail
                print(f"  FAILED    {relative}: {exc}", file=sys.stderr)
                problems += 1
    print(f"total model bytes: {total / 1e6:.1f} MB")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
