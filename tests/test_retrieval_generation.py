"""Staging index generations: build, validation gate, activation, rollback and the request path.

Real SQLAlchemy models on in-memory SQLite and a real in-memory Qdrant; the embedding model is a
deterministic stand-in with the reviewed BGE-M3 contract's dimensions.
"""

import hashlib
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.api.routes import documents
from app.core.config import Settings
from app.models.database import (
    AuditEvent,
    Base,
    Document,
    DocumentIndexEvent,
    DocumentVersion,
    IndexGeneration,
    IndexGenerationItem,
    KnowledgeBase,
    Organization,
    User,
    Workspace,
    WorkspaceRetrievalAssignment,
)
from app.services.rag import generation_qdrant
from app.services.rag import generation_runtime as runtime
from app.services.rag import pipeline
from app.services.rag.generation_qdrant import GenerationQdrantAdapter
from app.services.rag.retrieval_contract_registry import BALANCED_MULTILINGUAL_BGE_M3_V1
from app.services.rag.retrieval_contracts import (
    LegacyUnverifiedRetrieval,
    RetrievalCompatibilityError,
    collection_name_for_space,
)
from app.tools import retrieval_generation as tool

SPACE = BALANCED_MULTILINGUAL_BGE_M3_V1.space
TEXTS = {
    "/data/modai/uploads/izin.md": "Yıllık izin tablosu: 0–5 yıl 16 iş günü, 5–15 yıl 21 iş günü. Kıdem esas alınır.",
    "/data/modai/uploads/vpn.md": "AtlasConnect VPN: you can be connected from at most 2 devices at the same time.",
    "/data/modai/uploads/sla.md": "Premium plan Severity 2 first response target is 2 hours.",
    "/data/modai/uploads/deleted.md": "Silinmiş belge metni.",
    "/data/modai/uploads/queued.md": "Henüz indekslenmemiş sürüm.",
}


class WordHashEmbedder:
    """Stand-in for the BGE-M3 model: normalized bag of hashed words, 1024 dimensions."""

    def __init__(self):
        self.calls = 0

    async def embed_texts(self, texts):
        self.calls += 1
        out = []
        for text in texts:
            vector = [0.0] * SPACE.dimensions
            for word in text.lower().split():
                vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % SPACE.dimensions] += 1.0
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            out.append([v / norm for v in vector] if any(vector) else [1.0] + [0.0] * (SPACE.dimensions - 1))
        return out

    async def embed_text(self, text):
        return (await self.embed_texts([text]))[0]


class FakeStorage:
    def __init__(self, fail: set[str] | None = None):
        self.fail = fail or set()

    async def read(self, path):
        if path in self.fail:
            raise OSError("unreadable")
        return TEXTS.get(path, f"Belge {path.rsplit('/', 1)[-1]} metni.").encode()


class IndexedLocalQdrant:
    """In-memory Qdrant that reports the payload indexes it was asked to create (local mode ignores
    them), so the strict validation gate can be exercised."""

    def __init__(self):
        self.client = AsyncQdrantClient(":memory:")
        self.indexes: dict[str, dict] = {}

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def create_payload_index(self, collection_name, field_name, field_schema, wait=True):
        self.indexes.setdefault(collection_name, {})[field_name] = SimpleNamespace(data_type=field_schema)

    async def get_collection(self, collection_name):
        info = await self.client.get_collection(collection_name)
        return info.model_copy(update={"payload_schema": self.indexes.get(collection_name, {})})


def staging(enabled=True):
    return Settings(retrieval_generations_enabled=enabled)


@pytest_asyncio.fixture
async def env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    client = IndexedLocalQdrant()
    adapter = GenerationQdrantAdapter(client)
    embedder = WordHashEmbedder()
    monkeypatch.setattr(runtime, "get_settings", lambda: staging())
    monkeypatch.setattr(runtime, "get_generation_adapter", lambda: adapter)
    monkeypatch.setattr(pipeline, "get_generation_adapter", lambda: adapter)
    # Any adapter built from settings by mistake must fail here, never reach a real Qdrant.
    monkeypatch.setattr(generation_qdrant, "get_settings", lambda: Settings(qdrant_url="http://127.0.0.1:9"))
    monkeypatch.setattr(runtime, "get_contract_embedder", lambda _candidate: embedder)
    monkeypatch.setattr(tool, "get_contract_embedder", lambda _candidate: embedder)
    monkeypatch.setattr(tool, "storage", FakeStorage())

    async with maker() as db:
        organization = Organization(name="Org", slug="org")
        workspace = Workspace(name="WS", slug="ws", organization=organization)
        other = Workspace(name="Other", slug="other", organization=organization)
        user = User(email="owner@example.com", password_hash="x")
        db.add_all([organization, workspace, other, user])
        await db.flush()
        kb = KnowledgeBase(workspace_id=workspace.id, name="Demo", slug="demo")
        kb2 = KnowledgeBase(workspace_id=workspace.id, name="Second", slug="second")
        foreign = KnowledgeBase(workspace_id=other.id, name="Foreign", slug="foreign")
        db.add_all([kb, kb2, foreign])
        await db.flush()

        def document(name, kb_id, *, deleted=False, status="ready", workspace_id=workspace.id):
            doc = Document(
                user_id=user.id, organization_id=organization.id, workspace_id=workspace_id, knowledge_base_id=kb_id,
                filename=f"{name}.md", content="", active_version=1, source_revision=2,
                deleted_at=None if not deleted else __import__("datetime").datetime(2026, 1, 1),
            )
            doc.versions.append(DocumentVersion(version=1, content_hash=name * 8, file_size=10, status=status, stored_path=f"/data/modai/uploads/{name}.md"))
            return doc

        docs = {
            "izin": document("izin", kb.id),
            "vpn": document("vpn", kb.id),
            "sla": document("sla", kb2.id),
            "deleted": document("deleted", kb.id, deleted=True),
            "queued": document("queued", kb.id, status="queued"),
        }
        db.add_all(docs.values())
        await db.flush()
        for doc in docs.values():
            db.add(DocumentIndexEvent(organization_id=organization.id, workspace_id=workspace.id, knowledge_base_id=doc.knowledge_base_id,
                                      document_id=doc.id, source_revision=2, operation="active_version_published"))
        await db.commit()
        # Plain ids: a rollback in a test expires ORM objects.
        yield SimpleNamespace(db=db, adapter=adapter, client=client, embedder=embedder, org_id=organization.id, ws_id=workspace.id,
                              other_id=other.id, kb_id=kb.id, kb2_id=kb2.id, doc_ids={name: doc.id for name, doc in docs.items()})
    await client.close()
    await engine.dispose()


async def built_and_validated(env):
    planned = await tool.plan(env.db, env.ws_id, "balanced-multilingual@1")
    built = await tool.build(env.db, planned["generation_id"], env.adapter)
    validated = await tool.validate(env.db, planned["generation_id"], env.adapter)
    return planned, built, validated


def test_generation_serving_is_off_unless_enabled():
    assert Settings().retrieval_generations_enabled is False


@pytest.mark.asyncio
async def test_tool_refuses_to_plan_build_or_activate_when_disabled(env, monkeypatch):
    monkeypatch.setattr(runtime, "get_settings", lambda: staging(enabled=False))
    with pytest.raises(tool.GenerationToolError, match="disabled"):
        await tool.plan(env.db, env.ws_id, "balanced-multilingual@1")
    assert (await env.db.scalars(select(IndexGeneration))).all() == []


@pytest.mark.asyncio
async def test_build_and_validate_cover_exactly_the_eligible_sources_in_their_own_collection(env):
    planned, built, validated = await built_and_validated(env)

    collection = collection_name_for_space(SPACE.space_sha256)
    assert planned["collection"] == collection
    assert built["state"] == "validating" and built["indexed"] == 3 and built["eligible_documents"] == 3
    assert validated["passed"] is True, validated["failures"]
    assert validated["state"] == "ready"
    assert validated["points"] == validated["expected_points"] == 3
    assert validated["smoke_hits"] == validated["smoke_probes"] == 3
    assert validated["isolation_points"] == 0
    # Only the BGE-M3 space collection exists: the legacy MiniLM collection is never touched.
    names = {item.name for item in (await env.client.get_collections()).collections}
    assert names == {collection}
    records, _ = await env.client.scroll(collection, limit=100, with_payload=True)
    assert {r.payload["filename"] for r in records} == {"izin.md", "vpn.md", "sla.md"}  # no deleted or queued source
    assert {r.payload["knowledge_base_id"] for r in records} == {env.kb_id, env.kb2_id}
    assert all(r.payload["organization_id"] == env.org_id and r.payload["workspace_id"] == env.ws_id for r in records)
    actions = (await env.db.scalars(select(AuditEvent.action))).all()
    assert "retrieval_migration_created" in actions and "retrieval_migration_validation_passed" in actions


@pytest.mark.asyncio
async def test_rebuild_resumes_and_skips_unchanged_documents(env):
    planned = await tool.plan(env.db, env.ws_id, "balanced-multilingual@1")
    await tool.build(env.db, planned["generation_id"], env.adapter)
    generation = await env.db.get(IndexGeneration, planned["generation_id"])
    generation.state = "building"
    await env.db.commit()
    again = await tool.build(env.db, planned["generation_id"], env.adapter)
    assert again["unchanged"] == 3 and "indexed" not in again


@pytest.mark.asyncio
async def test_an_incomplete_generation_cannot_be_validated_or_activated(env, monkeypatch):
    monkeypatch.setattr(tool, "storage", FakeStorage(fail={"/data/modai/uploads/vpn.md"}))
    planned = await tool.plan(env.db, env.ws_id, "balanced-multilingual@1")
    built = await tool.build(env.db, planned["generation_id"], env.adapter)

    assert built["state"] == "building" and built["failed"] == 1
    item = await env.db.get(IndexGenerationItem, (planned["generation_id"], env.doc_ids["vpn"]))
    assert item.state == "failed" and item.error_code == "OSError"
    with pytest.raises(tool.GenerationToolError, match="cannot validate"):
        await tool.validate(env.db, planned["generation_id"], env.adapter)
    with pytest.raises(tool.GenerationToolError, match="not a ready generation"):
        await tool.activate(env.db, env.ws_id, planned["generation_id"], expected_epoch=0, confirm_workspace=env.ws_id)
    assert await env.db.get(WorkspaceRetrievalAssignment, env.ws_id) is None or (
        (await env.db.get(WorkspaceRetrievalAssignment, env.ws_id)).serving_mode == "legacy"
    )


@pytest.mark.asyncio
async def test_validation_fails_when_a_point_is_missing(env):
    planned = await tool.plan(env.db, env.ws_id, "balanced-multilingual@1")
    await tool.build(env.db, planned["generation_id"], env.adapter)
    generation = await env.db.get(IndexGeneration, planned["generation_id"])
    write = tool._write_index(generation, env.org_id)
    await env.adapter.delete_document(write, document_id=env.doc_ids["sla"])

    report = await tool.validate(env.db, planned["generation_id"], env.adapter)

    assert report["passed"] is False and report["state"] == "building"
    assert any(failure.startswith("point_count_mismatch") for failure in report["failures"])


@pytest.mark.asyncio
async def test_activation_requires_typed_confirmation_epoch_and_current_sources(env):
    planned, _, _ = await built_and_validated(env)
    generation_id = planned["generation_id"]

    with pytest.raises(tool.GenerationToolError, match="confirm-workspace"):
        await tool.activate(env.db, env.ws_id, generation_id, expected_epoch=0, confirm_workspace=env.ws_id + 1)
    with pytest.raises(tool.GenerationToolError, match="epoch is 0"):
        await tool.activate(env.db, env.ws_id, generation_id, expected_epoch=5, confirm_workspace=env.ws_id)
    await env.db.rollback()

    # A source event after validation (a new upload, a replacement, a delete) blocks activation.
    env.db.add(DocumentIndexEvent(organization_id=env.org_id, workspace_id=env.ws_id, knowledge_base_id=env.kb_id,
                                  document_id=env.doc_ids["izin"], source_revision=3, operation="source_staged"))
    await env.db.commit()
    with pytest.raises(tool.GenerationToolError, match="source events after validation"):
        await tool.activate(env.db, env.ws_id, generation_id, expected_epoch=0, confirm_workspace=env.ws_id)
    await env.db.rollback()

    report = await tool.validate(env.db, generation_id, env.adapter)
    assert report["passed"] is True
    activated = await tool.activate(env.db, env.ws_id, generation_id, expected_epoch=0, confirm_workspace=env.ws_id)
    assert activated == {"workspace_id": env.ws_id, "serving_mode": "generation", "active_generation_id": generation_id, "assignment_epoch": 1}


@pytest.mark.asyncio
async def test_request_path_serves_the_active_generation_and_rollback_restores_legacy(env, monkeypatch):
    planned, _, _ = await built_and_validated(env)
    scope = {"organization_id": env.org_id, "workspace_id": env.ws_id, "knowledge_base_ids": [env.kb_id, env.kb2_id]}
    assert isinstance(await runtime.resolve_retrieval_index(env.db, **scope), LegacyUnverifiedRetrieval)

    await tool.activate(env.db, env.ws_id, planned["generation_id"], expected_epoch=0, confirm_workspace=env.ws_id)

    class NoLegacy:
        async def search(self, **_kwargs):
            raise AssertionError("a generation-mode workspace must never query rag_documents")

    def no_minilm():
        raise AssertionError("a generation-mode workspace must never embed with the legacy model")

    monkeypatch.setattr(pipeline, "qdrant_service", NoLegacy())
    monkeypatch.setattr(pipeline, "get_embedding_service", no_minilm)
    monkeypatch.setattr(pipeline, "get_settings", lambda: SimpleNamespace(rag_top_k=3))

    context = await pipeline.retrieve_rag_context("Premium plan Severity 2 first response", db=env.db, **scope)
    assert context.sources[0].document == "sla.md"
    assert {source.document for source in context.sources} <= {"izin.md", "vpn.md", "sla.md"}

    # Only the selected Knowledge Base is searched.
    narrow = await pipeline.retrieve_rag_context("Premium plan Severity 2", db=env.db, **{**scope, "knowledge_base_ids": [env.kb_id]})
    assert "sla.md" not in {source.document for source in narrow.sources}

    # A source replaced after activation: its indexed points are stale and never reach the prompt.
    (await env.db.get(Document, env.doc_ids["sla"])).source_revision = 3
    await env.db.commit()
    stale = await pipeline.retrieve_rag_context("Premium plan Severity 2 first response", db=env.db, **scope)
    assert "sla.md" not in {source.document for source in stale.sources}

    generation = await env.db.get(IndexGeneration, planned["generation_id"])
    points_before = await env.adapter.count_generation(tool._write_index(generation, env.org_id))
    rolled_back = await tool.rollback(env.db, env.ws_id, expected_epoch=1, confirm_workspace=env.ws_id)
    assert rolled_back["serving_mode"] == "legacy" and rolled_back["assignment_epoch"] == 2
    assert isinstance(await runtime.resolve_retrieval_index(env.db, **scope), LegacyUnverifiedRetrieval)
    await env.db.refresh(generation)
    assert generation.state == "superseded"
    assert await env.adapter.count_generation(tool._write_index(generation, env.org_id)) == points_before  # retained
    actions = (await env.db.scalars(select(AuditEvent.action))).all()
    assert "retrieval_profile_activated" in actions and "retrieval_profile_rollback" in actions


@pytest.mark.asyncio
async def test_archived_document_is_never_served_and_unarchiving_needs_no_reindex(env, monkeypatch):
    planned, _, _ = await built_and_validated(env)
    await tool.activate(env.db, env.ws_id, planned["generation_id"], expected_epoch=0, confirm_workspace=env.ws_id)
    monkeypatch.setattr(pipeline, "get_settings", lambda: SimpleNamespace(rag_top_k=3))
    scope = {"organization_id": env.org_id, "workspace_id": env.ws_id, "knowledge_base_ids": [env.kb_id, env.kb2_id]}
    question = "Premium plan Severity 2 first response"
    sla_id = env.doc_ids["sla"]

    async def manager_access(db, _user, document_id, role):
        assert role == "manager"
        return await db.get(Document, document_id), SimpleNamespace(role="manager")

    monkeypatch.setattr(documents, "require_document_access", manager_access)

    def request_for(path):
        return Request({"type": "http", "method": "POST", "scheme": "http", "path": path, "headers": []})

    generation = await env.db.get(IndexGeneration, planned["generation_id"])
    write = tool._write_index(generation, env.org_id)
    points_before = await env.adapter.count_generation(write)
    last_event_before = await runtime.latest_source_event_id(env.db, env.ws_id)
    assert (await pipeline.retrieve_rag_context(question, db=env.db, **scope)).sources[0].document == "sla.md"

    await documents.archive_document(request_for(f"/documents/{sla_id}/archive"), sla_id, {"sub": "1"}, env.db)

    context = await pipeline.retrieve_rag_context(question, db=env.db, **scope)
    assert "sla.md" not in {source.document for source in context.sources}
    assert sla_id not in {source.document_id for source in context.sources}
    assert TEXTS["/data/modai/uploads/sla.md"] not in context.prompt
    # Its points stay in the generation, current and eligible: nothing is behind and no source
    # event was written, so the activation gate and the lag report are unaffected.
    assert await env.adapter.count_generation(write) == points_before
    assert sla_id in {document.id for document, _ in await runtime.eligible_sources(env.db, env.ws_id, env.org_id)}
    assert (await tool.status(env.db, env.ws_id))["generations"][0]["lag"] == {"missing_or_outdated": [], "stale_points": []}
    assert await runtime.latest_source_event_id(env.db, env.ws_id) == last_event_before

    # Un-archiving serves the same points again at once, without any reindex.
    embed_calls = env.embedder.calls
    await documents.unarchive_document(request_for(f"/documents/{sla_id}/unarchive"), sla_id, {"sub": "1"}, env.db)
    restored = await pipeline.retrieve_rag_context(question, db=env.db, **scope)
    assert restored.sources[0].document == "sla.md"
    assert env.embedder.calls == embed_calls + 1  # the question only
    assert await env.adapter.count_generation(write) == points_before


@pytest.mark.asyncio
async def test_generation_mode_fails_closed_instead_of_falling_back(env, monkeypatch):
    planned, _, _ = await built_and_validated(env)
    await tool.activate(env.db, env.ws_id, planned["generation_id"], expected_epoch=0, confirm_workspace=env.ws_id)
    scope = {"organization_id": env.org_id, "workspace_id": env.ws_id, "knowledge_base_ids": [env.kb_id]}

    # The deployment loses the staging flag: the workspace does not silently return to MiniLM.
    monkeypatch.setattr(runtime, "get_settings", lambda: staging(enabled=False))
    with pytest.raises(runtime.RetrievalIndexUnavailableError):
        await runtime.resolve_retrieval_index(env.db, **scope)
    monkeypatch.setattr(runtime, "get_settings", lambda: staging())

    # A tampered contract fails before any embedding or search.
    generation = await env.db.get(IndexGeneration, planned["generation_id"])
    generation.space_json = {**generation.space_json, "dimensions": 384}
    await env.db.commit()
    with pytest.raises(RetrievalCompatibilityError):
        await runtime.resolve_retrieval_index(env.db, **scope)

    # An active pointer to a generation that is not ready is refused.
    generation.space_json = SPACE.canonical_payload()
    generation.state = "building"
    await env.db.commit()
    with pytest.raises(runtime.RetrievalIndexUnavailableError):
        await runtime.resolve_retrieval_index(env.db, **scope)


@pytest.mark.asyncio
async def test_only_one_unfinished_candidate_per_workspace(env):
    await tool.plan(env.db, env.ws_id, "balanced-multilingual@1")
    with pytest.raises(tool.GenerationToolError, match="unfinished candidate"):
        await tool.plan(env.db, env.ws_id, "balanced-multilingual@1")
    with pytest.raises(tool.GenerationToolError, match="not a reviewed candidate"):
        await tool.plan(env.db, env.other_id, "balanced-multilingual@2")


@pytest.mark.asyncio
async def test_rollback_needs_the_current_epoch_and_works_without_the_flag(env, monkeypatch):
    planned, _, _ = await built_and_validated(env)
    await tool.activate(env.db, env.ws_id, planned["generation_id"], expected_epoch=0, confirm_workspace=env.ws_id)
    with pytest.raises(tool.GenerationToolError, match="epoch is 1"):
        await tool.rollback(env.db, env.ws_id, expected_epoch=0, confirm_workspace=env.ws_id)
    await env.db.rollback()
    monkeypatch.setattr(runtime, "get_settings", lambda: staging(enabled=False))
    result = await tool.rollback(env.db, env.ws_id, expected_epoch=1, confirm_workspace=env.ws_id)
    assert result["serving_mode"] == "legacy"


def test_contract_embedder_refuses_an_unpinned_or_different_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "get_settings", lambda: Settings(retrieval_model_root=str(tmp_path)))
    embedder = runtime.ContractEmbedder(BALANCED_MULTILINGUAL_BGE_M3_V1)
    with pytest.raises(runtime.RetrievalIndexUnavailableError, match="not provisioned"):
        embedder._load()
    artifact = Path(tmp_path) / BALANCED_MULTILINGUAL_BGE_M3_V1.artifact_dir
    artifact.mkdir(parents=True)
    (artifact / "config.json").write_text("{}")
    (artifact / "model.safetensors").write_bytes(b"not the pinned weights")
    with pytest.raises(runtime.RetrievalIndexUnavailableError, match="weights do not match"):
        embedder._load()


@pytest.mark.asyncio
async def test_http_reports_an_unavailable_index_without_answering(monkeypatch):
    from fastapi import HTTPException

    from app.api.routes import rag as rag_routes
    from app.models.schemas import RagRequest

    class NoopLimiter:
        async def enforce(self, *_args):
            return None

        async def close(self):
            return None

    async def resolve_scope(_db, _user, _ids):
        return [4], (SimpleNamespace(id=4), SimpleNamespace(id=3, organization_id=2), SimpleNamespace(role="user"))

    async def preferences(*_args):
        return {"language": "tr", "tone": "professional", "response_length": "short"}

    async def unavailable(_question, **_kwargs):
        raise runtime.RetrievalIndexUnavailableError("generation is not ready")

    class NoModel:
        def __init__(self, *_args):
            raise AssertionError("the model must not be called")

    monkeypatch.setattr(rag_routes, "RedisRateLimiter", NoopLimiter)
    monkeypatch.setattr(rag_routes, "resolve_knowledge_base_scope", resolve_scope)
    monkeypatch.setattr(rag_routes, "get_effective_assistant_preferences", preferences)
    monkeypatch.setattr(rag_routes, "retrieve_rag_context", unavailable)
    monkeypatch.setattr(rag_routes, "OllamaProvider", NoModel)
    with pytest.raises(HTTPException) as raised:
        await rag_routes.query(RagRequest(question="soru", knowledge_base_ids=[4]), request=None, user={"sub": "7"}, db=SimpleNamespace())
    assert raised.value.status_code == 503
    assert raised.value.detail == runtime.retrieval_index_unavailable_detail()


@pytest.mark.asyncio
async def test_websocket_reports_an_unavailable_index_without_answering(monkeypatch):
    from test_voice_rag import FakeWebSocket, _wire

    stream_calls: list = []
    module = _wire(monkeypatch, retrieve_calls=[], stream_calls=stream_calls)

    async def unavailable(_question, **_kwargs):
        raise runtime.RetrievalIndexUnavailableError("generation is not ready")

    monkeypatch.setattr(module, "retrieve_rag_context", unavailable)
    ws = FakeWebSocket({"question": "soru", "knowledge_base_ids": [4]})
    await module.websocket_rag(ws)
    assert ws.messages == [{"type": "error", "data": runtime.retrieval_index_unavailable_detail()}]
    assert stream_calls == []


async def published(env, name, *, kb_id, version=1, revision=2, text="Yeni yan hak: yılda 3 gün gönüllülük izni."):
    """A source as the worker publishes it: document, ready version, the revision it commits."""
    doc = await env.db.get(Document, env.doc_ids[name]) if name in env.doc_ids else None
    if doc is None:
        user_id = (await env.db.scalar(select(User.id)))
        doc = Document(user_id=user_id, organization_id=env.org_id, workspace_id=env.ws_id, knowledge_base_id=kb_id,
                       filename=f"{name}.md", content="", active_version=version, source_revision=revision)
        env.db.add(doc)
        await env.db.flush()
        env.doc_ids[name] = doc.id
    row = DocumentVersion(document_id=doc.id, version=version, content_hash=f"{name}-{version}" * 4, file_size=10, status="ready",
                          stored_path=f"/data/modai/uploads/{name}-{version}.md")
    env.db.add(row)
    mirrored = await runtime.mirror_to_active_generation(env.db, document=doc, version=row, text=text, source_revision=revision)
    doc.active_version, doc.source_revision = version, revision
    await env.db.commit()
    return mirrored


@pytest.mark.asyncio
async def test_worker_mirroring_keeps_the_active_generation_current(env, monkeypatch):
    planned, _, _ = await built_and_validated(env)
    assert await published(env, "before-activation", kb_id=env.kb_id) is False  # legacy workspace: nothing to mirror
    # That upload arrived after validation: the candidate is incomplete and cannot be activated
    # until it is built again (resuming: only the new source is indexed) and validated.
    report = await tool.validate(env.db, planned["generation_id"], env.adapter)
    assert report["passed"] is False and report["state"] == "building"
    assert (await tool.build(env.db, planned["generation_id"], env.adapter))["indexed"] == 1
    assert (await tool.validate(env.db, planned["generation_id"], env.adapter))["passed"] is True
    await tool.activate(env.db, env.ws_id, planned["generation_id"], expected_epoch=0, confirm_workspace=env.ws_id)
    monkeypatch.setattr(pipeline, "get_settings", lambda: SimpleNamespace(rag_top_k=3))
    scope = {"organization_id": env.org_id, "workspace_id": env.ws_id, "knowledge_base_ids": [env.kb_id, env.kb2_id]}

    # A new upload is searchable in the active generation as soon as the worker publishes it.
    assert await published(env, "gonullu", kb_id=env.kb_id, text="Gönüllülük izni yılda 3 gündür.") is True
    context = await pipeline.retrieve_rag_context("Gönüllülük izni yılda kaç gündür?", db=env.db, **scope)
    assert context.sources[0].document == "gonullu.md"

    # A replacement: the new version is served and the old version's points are pruned.
    await published(env, "gonullu", kb_id=env.kb_id, version=2, revision=3, text="Gönüllülük izni artık yılda 5 gündür.")
    context = await pipeline.retrieve_rag_context("Gönüllülük izni yılda kaç gündür?", db=env.db, **scope)
    assert context.sources[0].document == "gonullu.md" and "5 gündür" in context.sources[0].text
    generation = await env.db.get(IndexGeneration, planned["generation_id"])
    records, _ = await env.adapter.scroll_generation(tool._write_index(generation, env.org_id))
    assert [(r.payload["document_version"], r.payload["source_revision"]) for r in records if r.payload["filename"] == "gonullu.md"] == [(2, 3)]

    # Nothing is behind: no missing source, no outdated item.
    status = await tool.status(env.db, env.ws_id)
    assert status["generations"][0]["lag"] == {"missing_or_outdated": [], "stale_points": []}


@pytest.mark.asyncio
async def test_mirroring_fails_closed_when_generations_are_disabled(env, monkeypatch):
    planned, _, _ = await built_and_validated(env)
    await tool.activate(env.db, env.ws_id, planned["generation_id"], expected_epoch=0, confirm_workspace=env.ws_id)
    monkeypatch.setattr(runtime, "get_settings", lambda: staging(enabled=False))
    with pytest.raises(runtime.RetrievalIndexUnavailableError):
        await published(env, "late", kb_id=env.kb_id)
