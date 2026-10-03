"""Protect the API/worker filesystem contract used by asynchronous indexing."""

from pathlib import Path
import re


COMPOSE_PATH = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def _service_block(service: str) -> str:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    match = re.search(
        rf"^  {re.escape(service)}:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)",
        compose,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"{service} service is missing from docker-compose.yml"
    return match.group(1)


def test_api_and_worker_share_persistent_document_storage_for_async_indexing():
    expected_data_dir = 'DATA_DIR: "/data/modai"'
    expected_volume = "- modaidata:/data/modai"

    for service in ("api", "worker"):
        block = _service_block(service)
        assert expected_data_dir in block
        assert expected_volume in block
