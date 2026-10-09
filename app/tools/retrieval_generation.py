"""Build, validate, activate and roll back a workspace index generation.

    python -m app.tools.retrieval_generation status   --workspace-id 1
    python -m app.tools.retrieval_generation plan     --workspace-id 1 [--profile balanced-multilingual@1]
    python -m app.tools.retrieval_generation build    --generation-id <uuid>
    python -m app.tools.retrieval_generation validate --generation-id <uuid>
    python -m app.tools.retrieval_generation activate --workspace-id 1 --generation-id <uuid> --expected-epoch N --confirm-workspace 1
    python -m app.tools.retrieval_generation rollback --workspace-id 1 --expected-epoch N --confirm-workspace 1

plan/build/validate/activate refuse to run unless RETRIEVAL_GENERATIONS_ENABLED=true. Rollback to
the legacy MiniLM index always works: the worker keeps indexing every upload into rag_documents
(and, once a generation is active, into that generation too), so rollback is a pointer change.

A generation is built from the stored source files of each document's active ready version, with the
pinned materialization contract, into its embedding space's own collection; MiniLM points and the
rag_documents collection are never read or written. Activation requires a passing validation whose
source snapshot and last source event are still current. Output carries ids, counts and hashes only:
no document text, questions or vectors.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (
    IndexGeneration,
    IndexGenerationItem,
    KnowledgeBase,
    Workspace,
    WorkspaceRetrievalAssignment,
)
from app.services.audit import record_audit_event
from app.services.documents.parser import extract_text
from app.services.rag.chunker import chunk_text
from app.services.rag.generation_collection_binding import assert_collection_space_binding
from app.services.rag.generation_qdrant import GenerationQdrantAdapter
from app.services.rag.generation_runtime import (
    WORD_CHUNKS_V1,
    eligible_sources,
    generation_contracts,
    generation_lag,
    generations_enabled,
    get_contract_embedder,
    latest_source_event_id,
    source_snapshot_sha256,
)
from app.services.rag.retrieval_contract_registry import get_reviewed_candidate
from app.services.rag.retrieval_contracts import (
    AuthorizedTenantGeneration,
    GenerationWriteScope,
    ResolvedGenerationWriteIndex,
    ResolvedRetrievalIndex,
    RetrievalContractError,
    collection_name_for_space,
)
from app.services.storage import storage

VALIDATION_CHECK_VERSION = 1
SMOKE_PROBES = 5
CANDIDATE_STATES = ("planned", "building", "catching_up", "validating")


class GenerationToolError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_enabled() -> None:
    if not generations_enabled():
        raise GenerationToolError("index generations are disabled: requires RETRIEVAL_GENERATIONS_ENABLED=true and APP_ENV=staging")


async def _workspace(db: AsyncSession, workspace_id: int) -> Workspace:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None or workspace.organization_id is None:
        raise GenerationToolError("workspace not found")
    return workspace


async def _generation(db: AsyncSession, generation_id: str) -> IndexGeneration:
    generation = await db.get(IndexGeneration, str(UUID(generation_id)))
    if generation is None:
        raise GenerationToolError("generation not found")
    return generation


def _write_index(generation: IndexGeneration, organization_id: int) -> ResolvedGenerationWriteIndex:
    contracts = generation_contracts(generation)
    return ResolvedGenerationWriteIndex(
        scope=GenerationWriteScope(organization_id=organization_id, workspace_id=generation.workspace_id, generation_id=UUID(generation.id)),
        space=contracts.space,
        materialization=contracts.materialization,
        collection_name=contracts.collection_name,
    )


async def _is_active(db: AsyncSession, generation: IndexGeneration) -> bool:
    assignment = await db.get(WorkspaceRetrievalAssignment, generation.workspace_id)
    return assignment is not None and assignment.serving_mode == "generation" and assignment.active_generation_id == generation.id


async def plan(db: AsyncSession, workspace_id: int, profile: str) -> dict:
    _require_enabled()
    workspace = await _workspace(db, workspace_id)
    profile_id, _, version = profile.partition("@")
    candidate = get_reviewed_candidate(profile_id, int(version or 0))
    if candidate is None:
        raise GenerationToolError("profile is not a reviewed candidate")
    open_candidates = await db.scalar(
        select(func.count()).select_from(IndexGeneration).where(
            IndexGeneration.workspace_id == workspace_id, IndexGeneration.state.in_(CANDIDATE_STATES)
        )
    )
    if open_candidates:
        raise GenerationToolError("workspace already has an unfinished candidate generation")
    space, materialization = candidate.space, WORD_CHUNKS_V1
    collection = collection_name_for_space(space.space_sha256)
    await assert_collection_space_binding(db, collection_name=collection, space_sha256=space.space_sha256)
    number = (await db.scalar(select(func.max(IndexGeneration.generation_number)).where(IndexGeneration.workspace_id == workspace_id)) or 0) + 1
    generation = IndexGeneration(
        workspace_id=workspace_id,
        generation_number=number,
        profile_id=candidate.profile_id,
        profile_version=candidate.profile_version,
        space_json=space.canonical_payload(),
        space_sha256=space.space_sha256,
        materialization_json=materialization.canonical_payload(),
        materialization_sha256=materialization.materialization_sha256,
        qdrant_collection=collection,
        state="planned",
        validation_json={},
    )
    db.add(generation)
    await db.flush()
    record_audit_event(
        db, action="retrieval_migration_created", resource_type="index_generation", resource_id=generation.id,
        organization_id=workspace.organization_id, workspace_id=workspace_id,
        metadata={"profile": profile, "space_sha256": space.space_sha256, "materialization_sha256": materialization.materialization_sha256},
    )
    await db.commit()
    return {"generation_id": generation.id, "generation_number": number, "collection": collection, "state": "planned"}


async def build(db: AsyncSession, generation_id: str, adapter: GenerationQdrantAdapter, embedder=None) -> dict:
    """Materialize every eligible source into the candidate. Resumable: complete items whose source
    is unchanged are skipped; a changed or removed source replaces or deletes that document's points."""
    _require_enabled()
    generation = await _generation(db, generation_id)
    if generation.state not in ("planned", "building"):
        raise GenerationToolError(f"cannot build a generation in state {generation.state}")
    if await _is_active(db, generation):
        raise GenerationToolError("cannot rebuild the active generation; roll back first")
    workspace = await _workspace(db, generation.workspace_id)
    write = _write_index(generation, workspace.organization_id)
    contracts = generation_contracts(generation)
    embedder = embedder or get_contract_embedder(contracts.candidate)
    if generation.baseline_event_id is None:
        generation.baseline_event_id = await latest_source_event_id(db, generation.workspace_id)
    generation.state = "building"
    await db.commit()
    await adapter.create_collection(write)

    sources = await eligible_sources(db, generation.workspace_id, workspace.organization_id)
    items = {
        item.document_id: item
        for item in (await db.scalars(select(IndexGenerationItem).where(IndexGenerationItem.generation_id == generation.id))).all()
    }
    counts = Counter()
    for document, version in sources:
        item = items.get(document.id)
        if (
            item is not None and item.state == "complete" and item.source_revision == document.source_revision
            and item.document_version == version.version and item.content_hash == version.content_hash
        ):
            counts["unchanged"] += 1
            continue
        if item is None:
            item = IndexGenerationItem(generation_id=generation.id, document_id=document.id, source_revision=document.source_revision, attempts=0, indexed_chunk_count=0)
            db.add(item)
        item.attempts += 1
        try:
            text = extract_text(document.filename, await storage.read(version.stored_path or ""))
            chunks = chunk_text(text, contracts.materialization.chunk_size, contracts.materialization.chunk_overlap)
            vectors = await embedder.embed_texts(chunks)
            # A previous attempt may hold another version or more chunks: replace the document.
            await adapter.delete_document(write, document_id=document.id)
            await adapter.upsert_document(
                write, vector_space=contracts.space, knowledge_base_id=document.knowledge_base_id,
                document_id=document.id, document_version=version.version, source_revision=document.source_revision,
                content_hash=version.content_hash, filename=document.filename, chunks=chunks, vectors=vectors,
            )
        except Exception as exc:
            item.state, item.error_code = "failed", type(exc).__name__
            await db.commit()
            counts["failed"] += 1
            continue
        item.source_revision, item.document_version, item.content_hash = document.source_revision, version.version, version.content_hash
        item.expected_chunk_count = item.indexed_chunk_count = len(chunks)
        item.state, item.error_code = "complete", None
        await db.commit()  # the receipt only after Qdrant acknowledged the write
        counts["indexed"] += 1
    eligible_ids = {document.id for document, _ in sources}
    for document_id, item in items.items():
        if document_id not in eligible_ids and item.state != "removed":
            await adapter.delete_document(write, document_id=document_id)
            item.state, item.indexed_chunk_count = "removed", 0
            await db.commit()
            counts["removed"] += 1
    if counts["failed"]:
        return {"generation_id": generation.id, "state": "building", **counts}
    generation.state = "validating"
    await db.commit()
    return {"generation_id": generation.id, "state": "validating", "eligible_documents": len(sources), **counts}


async def validate(db: AsyncSession, generation_id: str, adapter: GenerationQdrantAdapter, embedder=None) -> dict:
    """The activation gate: contracts, collection, source coverage, every point, isolation, smoke."""
    _require_enabled()
    generation = await _generation(db, generation_id)
    if generation.state not in ("validating", "ready", "superseded"):
        raise GenerationToolError(f"cannot validate a generation in state {generation.state}")
    workspace = await _workspace(db, generation.workspace_id)
    failures: list[str] = []
    contracts = generation_contracts(generation)
    write = _write_index(generation, workspace.organization_id)
    await adapter.validate_payload_indexes(write)  # vector name, size, distance, payload indexes

    sources = await eligible_sources(db, generation.workspace_id, workspace.organization_id)
    max_event_id = await latest_source_event_id(db, generation.workspace_id)
    items = {
        item.document_id: item
        for item in (await db.scalars(select(IndexGenerationItem).where(IndexGenerationItem.generation_id == generation.id))).all()
    }
    expected: dict[int, tuple] = {}
    for document, version in sources:
        item = items.get(document.id)
        if item is None or item.state != "complete":
            failures.append(f"source_missing:{document.id}")
        elif (item.source_revision, item.document_version, item.content_hash) != (document.source_revision, version.version, version.content_hash):
            failures.append(f"source_stale:{document.id}")
        else:
            expected[document.id] = (document.knowledge_base_id, version.version, document.source_revision, item.expected_chunk_count)

    seen: Counter = Counter()
    first_chunks: dict[int, str] = {}
    offset = None
    while True:
        records, offset = await adapter.scroll_generation(write, limit=100, offset=offset)  # validates each payload
        for record in records:
            payload = record.payload
            document_id = payload["document_id"]
            want = expected.get(document_id)
            if want is None:
                failures.append(f"point_for_ineligible_document:{document_id}")
                continue
            kb_id, version, revision, chunk_count = want
            if (payload["knowledge_base_id"], payload["document_version"], payload["source_revision"]) != (kb_id, version, revision):
                failures.append(f"point_scope_or_version_mismatch:{document_id}")
            if not 0 <= payload["chunk_index"] < chunk_count:
                failures.append(f"point_chunk_out_of_range:{document_id}")
            seen[(document_id, payload["chunk_index"])] += 1
            if payload["chunk_index"] == 0:
                text = payload.get("text") or ""
                # The middle of the first chunk: every demo document opens with the same disclaimer.
                first_chunks[document_id] = text[max(0, len(text) // 2 - 200):len(text) // 2 + 200]
        if offset is None:
            break
    if any(count > 1 for count in seen.values()):
        failures.append("duplicate_chunk_points")
    expected_points = sum(want[3] for want in expected.values())
    if len(seen) != expected_points:
        failures.append(f"point_count_mismatch:{len(seen)}!={expected_points}")
    if await adapter.count_generation(write) != sum(seen.values()):
        failures.append("count_scroll_mismatch")

    # Retrieval smoke and isolation, with the generation's own model and read path.
    embedder = embedder or get_contract_embedder(contracts.candidate)
    kb_ids = tuple(sorted(set(
        (await db.scalars(select(KnowledgeBase.id).where(KnowledgeBase.workspace_id == generation.workspace_id))).all()
    ))) or (1,)

    def read_index(kbs: tuple[int, ...], workspace_id: int = generation.workspace_id) -> ResolvedRetrievalIndex:
        return ResolvedRetrievalIndex(
            scope=AuthorizedTenantGeneration(organization_id=workspace.organization_id, workspace_id=workspace_id, knowledge_base_ids=kbs, generation_id=UUID(generation.id)),
            space=contracts.space, materialization=contracts.materialization, collection_name=contracts.collection_name, assignment_epoch=0,
        )

    probes = hits_found = 0
    for document_id in sorted(first_chunks)[:SMOKE_PROBES]:
        vector = await embedder.embed_text(first_chunks[document_id])
        hits = await adapter.search(read_index(kb_ids), query_space=contracts.space, vector=vector, limit=3)
        probes += 1
        hits_found += any(hit.payload["document_id"] == document_id for hit in hits)
    if probes and hits_found < probes:
        failures.append(f"smoke_retrieval:{hits_found}/{probes}")
    unauthorized = 0
    if first_chunks:
        vector = await embedder.embed_text(next(iter(first_chunks.values())))
        outside_kb = (max(kb_ids) + 1_000_000,)
        unauthorized += len(await adapter.search(read_index(outside_kb), query_space=contracts.space, vector=vector, limit=3))
        unauthorized += len(await adapter.search(read_index(kb_ids, generation.workspace_id + 1_000_000), query_space=contracts.space, vector=vector, limit=3))
    if unauthorized:
        failures.append("isolation_probe_returned_points")

    report = {
        "check_version": VALIDATION_CHECK_VERSION,
        "passed": not failures,
        "validated_at": _now(),
        "failures": failures[:50],
        "eligible_documents": len(sources),
        "points": sum(seen.values()),
        "expected_points": expected_points,
        "snapshot_sha256": source_snapshot_sha256(sources),
        "max_event_id": max_event_id,
        "space_sha256": contracts.space.space_sha256,
        "materialization_sha256": contracts.materialization.materialization_sha256,
        "smoke_probes": probes,
        "smoke_hits": hits_found,
        "isolation_points": unauthorized,
    }
    active = await _is_active(db, generation)
    generation.validation_json = report
    if not active:  # an active generation keeps serving; its operator decides on rollback
        generation.state = "ready" if not failures else "building"
    record_audit_event(
        db, action="retrieval_migration_validation_passed" if not failures else "retrieval_migration_validation_failed",
        resource_type="index_generation", resource_id=generation.id, organization_id=workspace.organization_id,
        workspace_id=generation.workspace_id, success=not failures,
        metadata={"points": report["points"], "eligible_documents": len(sources), "failures": len(failures)},
    )
    await db.commit()
    return {"generation_id": generation.id, "state": generation.state, **report}


async def _locked_assignment(db: AsyncSession, workspace_id: int) -> WorkspaceRetrievalAssignment:
    assignment = await db.scalar(
        select(WorkspaceRetrievalAssignment).where(WorkspaceRetrievalAssignment.workspace_id == workspace_id).with_for_update()
    )
    if assignment is None:
        assignment = WorkspaceRetrievalAssignment(workspace_id=workspace_id, serving_mode="legacy", active_generation_id=None, assignment_epoch=0)
        db.add(assignment)
        await db.flush()
    return assignment


async def activate(db: AsyncSession, workspace_id: int, generation_id: str, expected_epoch: int, confirm_workspace: int) -> dict:
    _require_enabled()
    if confirm_workspace != workspace_id:
        raise GenerationToolError("--confirm-workspace must repeat the workspace id")
    workspace = await _workspace(db, workspace_id)
    assignment = await _locked_assignment(db, workspace_id)
    if assignment.assignment_epoch != expected_epoch:
        raise GenerationToolError(f"assignment changed: epoch is {assignment.assignment_epoch}")
    generation = await _generation(db, generation_id)
    if generation.workspace_id != workspace_id or generation.state != "ready":
        raise GenerationToolError("generation is not a ready generation of this workspace")
    generation_contracts(generation)
    report = generation.validation_json or {}
    if not report.get("passed") or report.get("check_version") != VALIDATION_CHECK_VERSION:
        raise GenerationToolError("generation has no passing validation")
    # The validation must still describe the current sources: same snapshot, no later source event.
    sources = await eligible_sources(db, workspace_id, workspace.organization_id)
    if source_snapshot_sha256(sources) != report.get("snapshot_sha256"):
        raise GenerationToolError("sources changed since validation; build and validate again")
    if await latest_source_event_id(db, workspace_id) != report.get("max_event_id"):
        raise GenerationToolError("source events after validation; build and validate again")
    previous = assignment.active_generation_id if assignment.serving_mode == "generation" else None
    assignment.serving_mode, assignment.active_generation_id = "generation", generation.id
    assignment.assignment_epoch += 1
    if previous and previous != generation.id:
        (await _generation(db, previous)).state = "superseded"
    record_audit_event(
        db, action="retrieval_profile_activated", resource_type="workspace_retrieval_assignment", resource_id=workspace_id,
        organization_id=workspace.organization_id, workspace_id=workspace_id,
        metadata={"generation_id": generation.id, "profile": f"{generation.profile_id}@{generation.profile_version}", "assignment_epoch": assignment.assignment_epoch, "space_sha256": generation.space_sha256},
    )
    await db.commit()
    return {"workspace_id": workspace_id, "serving_mode": "generation", "active_generation_id": generation.id, "assignment_epoch": assignment.assignment_epoch}


async def rollback(db: AsyncSession, workspace_id: int, expected_epoch: int, confirm_workspace: int) -> dict:
    """Back to the legacy MiniLM index. Allowed even when generations are disabled."""
    if confirm_workspace != workspace_id:
        raise GenerationToolError("--confirm-workspace must repeat the workspace id")
    workspace = await _workspace(db, workspace_id)
    assignment = await _locked_assignment(db, workspace_id)
    if assignment.assignment_epoch != expected_epoch:
        raise GenerationToolError(f"assignment changed: epoch is {assignment.assignment_epoch}")
    if assignment.serving_mode != "generation":
        raise GenerationToolError("workspace already serves the legacy index")
    previous = assignment.active_generation_id
    assignment.serving_mode, assignment.active_generation_id = "legacy", None
    assignment.assignment_epoch += 1
    (await _generation(db, previous)).state = "superseded"  # retained; points are not deleted
    record_audit_event(
        db, action="retrieval_profile_rollback", resource_type="workspace_retrieval_assignment", resource_id=workspace_id,
        organization_id=workspace.organization_id, workspace_id=workspace_id,
        metadata={"from_generation_id": previous, "assignment_epoch": assignment.assignment_epoch},
    )
    await db.commit()
    return {"workspace_id": workspace_id, "serving_mode": "legacy", "assignment_epoch": assignment.assignment_epoch, "retained_generation_id": previous}


async def status(db: AsyncSession, workspace_id: int) -> dict:
    workspace = await _workspace(db, workspace_id)
    assignment = await db.get(WorkspaceRetrievalAssignment, workspace_id)
    generations = (await db.scalars(select(IndexGeneration).where(IndexGeneration.workspace_id == workspace_id).order_by(IndexGeneration.generation_number))).all()
    sources = await eligible_sources(db, workspace_id, workspace.organization_id)
    snapshot = source_snapshot_sha256(sources)
    latest_event = await latest_source_event_id(db, workspace_id)
    return {
        "generations_enabled": generations_enabled(),
        "serving_mode": assignment.serving_mode if assignment else "legacy (no assignment row)",
        "active_generation_id": assignment.active_generation_id if assignment else None,
        "assignment_epoch": assignment.assignment_epoch if assignment else 0,
        "eligible_documents": len(sources),
        "generations": [
            {
                "id": generation.id, "number": generation.generation_number, "profile": f"{generation.profile_id}@{generation.profile_version}",
                "state": generation.state, "collection": generation.qdrant_collection,
                "validated": generation.validation_json.get("passed"), "points": generation.validation_json.get("points"),
                # Current means: activation would accept this validation now.
                "validation_current": generation.validation_json.get("snapshot_sha256") == snapshot and generation.validation_json.get("max_event_id") == latest_event,
                # Sources the generation does not match now; empty for an active generation the
                # worker keeps current.
                "lag": await generation_lag(db, generation, workspace.organization_id),
            }
            for generation in generations
        ],
    }


async def _main(args: argparse.Namespace) -> dict:
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        if args.command == "status":
            return await status(db, args.workspace_id)
        if args.command == "plan":
            return await plan(db, args.workspace_id, args.profile)
        if args.command == "activate":
            return await activate(db, args.workspace_id, args.generation_id, args.expected_epoch, args.confirm_workspace)
        if args.command == "rollback":
            return await rollback(db, args.workspace_id, args.expected_epoch, args.confirm_workspace)
        adapter = GenerationQdrantAdapter()
        try:
            if args.command == "build":
                return await build(db, args.generation_id, adapter)
            return await validate(db, args.generation_id, adapter)
        finally:
            await adapter.client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.tools.retrieval_generation")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "plan", "activate", "rollback"):
        command = commands.add_parser(name)
        command.add_argument("--workspace-id", type=int, required=True)
    commands.choices["plan"].add_argument("--profile", default="balanced-multilingual@1")
    for name in ("build", "validate", "activate"):
        command = commands.choices.get(name) or commands.add_parser(name)
        command.add_argument("--generation-id", required=True)
    for name in ("activate", "rollback"):
        commands.choices[name].add_argument("--expected-epoch", type=int, required=True)
        commands.choices[name].add_argument("--confirm-workspace", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(_main(args))
    except (GenerationToolError, RetrievalContractError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1, default=str))
    return 0 if result.get("passed", True) and result.get("state") != "building" else 1


if __name__ == "__main__":
    raise SystemExit(main())
