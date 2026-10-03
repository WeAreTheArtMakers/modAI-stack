"""Compare two persisted RAG evaluation results without making a quality claim."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.evaluation.comparison import compare_evaluations
from app.services.evaluation.models import EvaluationResult


def _load_result(path: str) -> EvaluationResult:
    try:
        return EvaluationResult.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid evaluation result {path}: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Report objective metric deltas between two RAG evaluation runs.")
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--json", action="store_true", help="Print JSON rather than a concise summary")
    args = parser.parse_args()
    try:
        comparison = compare_evaluations(_load_result(args.baseline), _load_result(args.candidate))
    except ValueError as exc:
        raise SystemExit(f"Comparison failed: {exc}") from exc
    if args.json:
        print(json.dumps(comparison.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return
    for metric, delta in comparison.deltas.items():
        print(f"{metric}: {delta}")
    for warning in comparison.warnings:
        print(f"WARNING: {warning}")


if __name__ == "__main__":
    main()
