#!/usr/bin/env python3
"""Download the retrieval embedding models pinned in retrieval-models.lock.json.

The multilingual BGE-M3 profile (balanced-multilingual@1) loads only this exact snapshot: files
come from huggingface.co at the locked revision and are written to models/<directory>/ only after
their size and SHA-256 match. Docker Compose mounts ./models at /models (RETRIEVAL_MODEL_ROOT).
The folder is git-ignored; never commit weights. About 2.4 GB.

Usage:
  python3 scripts/fetch_retrieval_models.py           # download missing or changed files
  python3 scripts/fetch_retrieval_models.py --check   # verify only, no network
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # also under python -I
from fetch_voice_models import _download, _safe_relative, _sha256  # noqa: E402  (same download and checks)

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "retrieval-models.lock.json"
DEFAULT_DEST = ROOT / "models"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify existing files without downloading")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args(argv)

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if lock.get("lock_version") != 1:
        raise SystemExit("unsupported retrieval model lock version")
    problems = 0
    for model in lock["models"]:
        directory = args.dest / _safe_relative(model["directory"])
        print(f"{model['id']} ({model['profile']}): {model['repository']} @ {model['revision']} ({model['license']})")
        for entry in model["files"]:
            relative = _safe_relative(entry["path"])
            target = directory / relative
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
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
