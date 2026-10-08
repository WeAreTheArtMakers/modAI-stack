"""Read-only dataset validator: ``python -m benchmarks.retrieval.validate <dataset.json>``.

Prints counts, lane/classification and fingerprints only. It never prints
document text, questions, evidence text or the dataset path, never imports the
application package and never connects to any service.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from benchmarks.retrieval.schema import (
    BenchmarkDataset,
    DatasetValidationError,
    assess_dataset,
    dataset_fingerprint,
    dataset_fingerprints_v2,
    load_any_dataset,
)


def summarize(dataset) -> dict:
    if isinstance(dataset, BenchmarkDataset):
        return {
            "dataset_schema_version": 1,
            "dataset_version": dataset.dataset_version,
            "classification": dataset.classification,
            "document_count": len(dataset.documents),
            "query_count": len(dataset.queries),
            "expected_document_labels": sum(len(query.expected_document_ids) for query in dataset.queries),
            "graded_relevance": "not available in schema v1",
            "dataset_sha256": dataset_fingerprint(dataset),
        }
    assessment = asdict(assess_dataset(dataset))
    return {
        "dataset_schema_version": 2,
        "dataset_version": dataset.dataset_version,
        **assessment,
        "fingerprints": asdict(dataset_fingerprints_v2(dataset)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a local retrieval benchmark dataset (read-only).")
    parser.add_argument("dataset")
    args = parser.parse_args(argv)
    try:
        dataset = load_any_dataset(args.dataset)
    except DatasetValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "VALID", **summarize(dataset)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
