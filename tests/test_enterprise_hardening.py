import asyncio
import json
from pathlib import Path
import pytest
from app.services.qdrant import QdrantService
from app.services.storage import FileStorage
from app.services.jobs.redis_queue import RedisIndexQueue

def test_multi_knowledge_base_filter_uses_match_any():
    condition = QdrantService()._user_filter(1, organization_id=2, workspace_id=3, knowledge_base_ids=[4, 5]).must
    assert any(getattr(item.match, "any", None) == [4, 5] for item in condition)

def test_indexing_events_use_workspace_scoped_channels():
    assert RedisIndexQueue.events_channel(10) == "modai:indexing:events:10"
    assert RedisIndexQueue.events_channel(11) != RedisIndexQueue.events_channel(10)

@pytest.mark.asyncio
async def test_indexing_progress_is_published_only_to_requested_workspace():
    class FakeRedis:
        def __init__(self): self.calls = []
        async def publish(self, channel, payload): self.calls.append((channel, json.loads(payload)))

    redis = FakeRedis()
    queue = RedisIndexQueue(redis)
    event = {
        "organization_id": 1,
        "workspace_id": 10,
        "knowledge_base_id": 20,
        "document_id": 30,
        "job_id": "job-1",
        "status": "processing",
        "stage": "embedding",
    }
    await queue.publish_progress(event, workspace_id=10)
    assert redis.calls == [("modai:indexing:events:10", event)]

def test_storage_rejects_paths_outside_upload_root(tmp_path):
    storage = FileStorage(str(tmp_path))
    try: asyncio.run(storage.read(str(Path(tmp_path).parent / "secret.txt")))
    except ValueError: pass
    else: raise AssertionError("path traversal must be rejected")

def test_storage_round_trip_and_cleanup(tmp_path):
    storage = FileStorage(str(tmp_path))
    path = asyncio.run(storage.save(b"hello", ".txt"))
    assert asyncio.run(storage.read(path)) == b"hello"
    asyncio.run(storage.delete(path))
    assert not Path(path).exists()
