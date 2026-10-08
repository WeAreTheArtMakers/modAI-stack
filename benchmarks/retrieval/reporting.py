"""Content-minimizing, stable benchmark report serialization."""

from __future__ import annotations

import json
from pathlib import Path


def serialize_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def render_markdown(report: dict) -> str:
    metrics = report["metrics"]
    dry_run_notice = []
    if report["metadata"]["execution_mode"].startswith("dry-run"):
        dry_run_notice.append(
            "This run used deterministic hash-stub vectors; its retrieval scores are not embedding-model quality results."
        )
    metadata = report["metadata"]
    source_sha = metadata["source_sha"]
    runtime_build_sha = metadata["runtime_build_sha"]
    rows = [("Global", metrics["global"])]
    rows.extend((language, summary) for language, summary in metrics["by_language"].items())
    rows.extend((category, summary) for category, summary in metrics["by_category"].items())
    lines = [
        "# Retrieval Quality Benchmark v1",
        "",
        f"- Classification: **{report['classification']}**",
        f"- Execution mode: `{report['metadata']['execution_mode']}`",
        f"- Dataset: `{report['metadata']['dataset_name']}` ({report['metadata']['dataset_version']})",
        f"- Embedding model: `{report['metadata']['embedding_model']}`",
        f"- Embedding dimension: {report['metadata']['embedding_dimension']}",
        f"- Vector store: `{report['metadata']['qdrant_isolation_mode']}`",
        f"- Benchmark source SHA: {f'`{source_sha}`' if source_sha else 'unavailable'} ({metadata['source_sha_origin']})",
        (
            f"- Runtime build SHA (dependency image, not the benchmark source): "
            f"{f'`{runtime_build_sha}`' if runtime_build_sha else 'not recorded'}"
        ),
        f"- Real-world benchmark status: **{report['real_world_benchmark_status']}**",
        "",
        *dry_run_notice,
        (
            "Fixture scores validate the framework only; they do not represent production retrieval quality."
            if report["metadata"]["dataset_classification"] == "fixture"
            else "Dataset authority is operator-declared; review corpus provenance and metrics before making product claims."
        ),
        "Unanswerable candidate presence is a retrieval observation, not answerability classification.",
        "",
        "| Group | n | Answerable | Recall@1 | Recall@3 | Recall@5 | MRR@5 | Hit@5 | Median embed ms | Median retrieval ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, summary in rows:
        def val(value):
            return "—" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)

        lines.append(
            "| {label} | {count} | {answerable} | {r1} | {r3} | {r5} | {mrr} | {hit} | {embed} | {retrieval} |".format(
                label=label,
                count=summary["query_count"],
                answerable=summary["answerable_query_count"],
                r1=val(summary["recall_at_k"]["1"]),
                r3=val(summary["recall_at_k"]["3"]),
                r5=val(summary["recall_at_k"]["5"]),
                mrr=val(summary["mrr_at_k"]["5"]),
                hit=val(summary["hit_at_k"]["5"]),
                embed=val(summary["median_embedding_latency_ms"]),
                retrieval=val(summary["median_retrieval_latency_ms"]),
            )
        )
    lines.extend(
        [
            "",
            "## Metric definitions",
            "",
            "- Recall@K is macro-average per answerable query: relevant labeled documents represented by the first K Qdrant chunk results divided by all relevant labeled documents.",
            "- Hit@K (source hit rate) is the fraction of answerable queries with at least one relevant document represented by the first K chunks.",
            "- MRR@K is the mean reciprocal rank of the first relevant document in deduplicated first-seen source order from the first K chunks; misses score zero.",
            "- Source precision@K is relevant distinct documents represented by the first K chunks divided by all distinct documents represented by those chunks across answerable queries.",
            "- Chunk recall is reported only over queries with explicit expected chunk IDs.",
            "- Unanswerable candidate-return rate and mean top score describe nearest-neighbor retrieval only; no abstention threshold is evaluated.",
            "- Latencies are medians from this machine/run and are not deterministic quality metrics.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(report: dict, output_dir: str | Path) -> tuple[Path, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "retrieval-benchmark-v1.json"
    markdown_path = output_path / "retrieval-benchmark-v1.md"
    json_path.write_text(serialize_json(report), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path
