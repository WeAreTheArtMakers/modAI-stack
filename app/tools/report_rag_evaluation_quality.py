"""Print aggregate-only quality metadata for a local evaluation corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.evaluation.models import EvaluationResult, dataset_fingerprint
from app.services.evaluation.quality import (
    dataset_quality_summary,
    expected_source_rank_distribution,
    result_quality_summary,
)
from app.services.evaluation.runner import load_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize an evaluation corpus without printing case content.")
    parser.add_argument("--dataset", required=True, help="Private, versioned evaluation dataset JSON")
    parser.add_argument("--result", help="Optional local evaluation result JSON for rank distribution")
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    report = dataset_quality_summary(dataset)
    if args.result:
        result = EvaluationResult.model_validate_json(Path(args.result).read_text(encoding="utf-8"))
        if result.dataset_fingerprint != dataset_fingerprint(dataset):
            raise SystemExit("Evaluation result fingerprint does not match the supplied dataset")
        report["expected_source_rank_distribution"] = expected_source_rank_distribution(result)
        report["no_answer_confusable_case_count"] = result.summary.no_answer_confusable_case_count
        report["no_answer_confusable_source_count"] = result.summary.no_answer_confusable_source_count
        report["result_quality"] = result_quality_summary(result)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
