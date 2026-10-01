import asyncio
from pathlib import Path
from app.services.qdrant import QdrantService
from app.services.storage import FileStorage

def test_multi_knowledge_base_filter_uses_match_any():
    condition = QdrantService()._user_filter(1, organization_id=2, workspace_id=3, knowledge_base_ids=[4, 5]).must
    assert any(getattr(item.match, "any", None) == [4, 5] for item in condition)

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
