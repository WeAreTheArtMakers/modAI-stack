"""Run a local, authorized RAG quality evaluation without sending data to a cloud judge."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.core.security import decode_token
from app.services.evaluation.models import EvaluationCase, RetrievalResult, RetrievedEvidence
from app.services.evaluation.runner import AuthorizedRagRetriever, EvaluationRunner, load_dataset
from app.services.llm.ollama import OllamaProvider


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate authorized local RAG retrieval and source quality.")
    parser.add_argument("--dataset", required=True, help="Versioned evaluation dataset JSON path")
    parser.add_argument("--mode", choices=("local", "fixture"), default="local")
    parser.add_argument("--fixture", help="Deterministic retrieval fixture JSON; required in fixture mode")
    parser.add_argument(
        "--access-token-env",
        default="MODAI_EVALUATION_ACCESS_TOKEN",
        help="Environment variable containing an access JWT for local mode (default: MODAI_EVALUATION_ACCESS_TOKEN)",
    )
    parser.add_argument("--generate", action="store_true", help="Also generate answers with the configured local Ollama model")
    parser.add_argument("--json", action="store_true", help="Print the complete versioned result as JSON")
    parser.add_argument("--output", help="Write the complete versioned result to this JSON path")
    parser.add_argument("--min-hit-at-k", type=float)
    parser.add_argument("--min-source-accuracy", type=float)
    parser.add_argument("--min-fact-coverage", type=float)
    parser.add_argument("--max-median-total-ms", type=float)
    return parser.parse_args()


def _fixture_retriever(path: str):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid retrieval fixture: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Invalid retrieval fixture: expected an object keyed by case ID")

    async def retrieve(case: EvaluationCase) -> RetrievalResult:
        values = raw.get(case.id, [])
        if not isinstance(values, list):
            raise ValueError(f"Invalid retrieval fixture for case {case.id}")
        return RetrievalResult(evidence=[RetrievedEvidence.model_validate(value) for value in values])

    return retrieve


async def _run_local(dataset_path: str, token_env: str, generate: bool):
    # Keep CLI fixture mode importable in test/air-gapped environments where a
    # production DATABASE_URL driver has intentionally not been installed.
    from app.db.session import SessionLocal

    token = os.environ.get(token_env)
    if not token:
        raise ValueError(f"Local mode requires an access JWT in {token_env}")
    user = decode_token(token)
    if user.get("type") != "access":
        raise ValueError("Local mode requires an access JWT")
    dataset = load_dataset(dataset_path)
    async with SessionLocal() as db:
        retriever = AuthorizedRagRetriever(db, user)
        generator = None
        if generate:
            provider = OllamaProvider()

            async def generator(_case: EvaluationCase, result: RetrievalResult) -> str:
                if result.prompt is None:
                    raise RuntimeError("Local retrieval did not return a RAG prompt")
                return await provider.generate(result.prompt)

        return await EvaluationRunner(retriever, generator).run(dataset, mode="local")


async def _run_fixture(dataset_path: str, fixture_path: str | None):
    if not fixture_path:
        raise ValueError("Fixture mode requires --fixture")
    dataset = load_dataset(dataset_path)
    return await EvaluationRunner(_fixture_retriever(fixture_path)).run(dataset, mode="fixture")


def _validate_thresholds(args: argparse.Namespace, result) -> list[str]:
    checks = (
        ("min_hit_at_k", "hit_at_k", "minimum Hit@K"),
        ("min_source_accuracy", "source_accuracy", "minimum source accuracy"),
        ("min_fact_coverage", "fact_coverage", "minimum fact coverage"),
    )
    failures: list[str] = []
    for argument, metric, label in checks:
        expected = getattr(args, argument)
        actual = getattr(result.summary, metric)
        if expected is not None and (actual is None or actual < expected):
            failures.append(f"{label} threshold failed: actual={actual}, required={expected}")
    maximum = args.max_median_total_ms
    actual_latency = result.summary.median_total_ms
    if maximum is not None and (actual_latency is None or actual_latency > maximum):
        failures.append(f"maximum median total latency threshold failed: actual={actual_latency}, maximum={maximum}")
    return failures


def _validate_threshold_arguments(args: argparse.Namespace) -> None:
    for argument in ("min_hit_at_k", "min_source_accuracy", "min_fact_coverage"):
        value = getattr(args, argument)
        if value is not None and not 0 <= value <= 1:
            raise ValueError(f"{argument} must be between 0 and 1")
    if args.max_median_total_ms is not None and args.max_median_total_ms < 0:
        raise ValueError("max_median_total_ms must be non-negative")


def _print_summary(result) -> None:
    summary = result.summary
    print(
        f"{result.dataset_name}: cases={summary.case_count} hit_at_k={summary.hit_at_k} "
        f"mrr={summary.mean_reciprocal_rank} source_accuracy={summary.source_accuracy} "
        f"fact_coverage={summary.fact_coverage} median_total_ms={summary.median_total_ms}"
    )


def main() -> None:
    args = parse_args()
    try:
        _validate_threshold_arguments(args)
        result = asyncio.run(
            _run_fixture(args.dataset, args.fixture)
            if args.mode == "fixture"
            else _run_local(args.dataset, args.access_token_env, args.generate)
        )
        payload = result.model_dump(mode="json")
        if args.output:
            Path(args.output).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            _print_summary(result)
        failures = _validate_thresholds(args, result)
        if failures:
            for failure in failures:
                print(f"THRESHOLD FAILED: {failure}")
            raise SystemExit(2)
    except ValueError as exc:
        raise SystemExit(f"Evaluation failed: {exc}") from exc


if __name__ == "__main__":
    main()
