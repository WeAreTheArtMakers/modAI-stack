"""Release tooling: the pinned retrieval model lock and the installation preflight."""

import importlib.util
import json
import sys
from pathlib import Path

from app.services.rag.retrieval_contract_registry import BALANCED_MULTILINGUAL_BGE_M3_V1, BGE_M3_REVISION

ROOT = Path(__file__).resolve().parents[1]


def _script(name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_retrieval_model_lock_is_the_reviewed_bge_m3_artifact():
    lock = json.loads((ROOT / "retrieval-models.lock.json").read_text())
    (model,) = lock["models"]
    files = {entry["path"]: entry for entry in model["files"]}
    assert model["repository"] == BALANCED_MULTILINGUAL_BGE_M3_V1.space.model_id
    assert model["revision"] == BGE_M3_REVISION
    assert model["directory"] == BALANCED_MULTILINGUAL_BGE_M3_V1.artifact_dir
    assert model["profile"] == "balanced-multilingual@1" and model["license"] == "MIT"
    assert files["model.safetensors"]["size"] == BALANCED_MULTILINGUAL_BGE_M3_V1.weights_bytes
    assert all(len(entry["sha256"]) == 64 for entry in files.values())
    assert {"config.json", "modules.json", "tokenizer.json", "1_Pooling/config.json"} <= set(files)


def test_retrieval_model_check_fails_when_files_are_missing(tmp_path, capsys):
    fetch = _script("fetch_retrieval_models")
    assert fetch.main(["--check", "--dest", str(tmp_path)]) == 1
    assert "MISSING   model.safetensors" in capsys.readouterr().out


def test_preflight_rejects_example_secrets_without_printing_them():
    preflight = _script("preflight")
    example = {"POSTGRES_PASSWORD": "example-db-password", "JWT_SECRET": "example-jwt-secret-value"}
    env = {"POSTGRES_DB": "modai", "POSTGRES_USER": "modai", "OLLAMA_MODEL": "gemma3:4b", **example, "ALLOW_REGISTRATION": "true"}
    findings = preflight.check_env(env, example)
    text = " ".join(message for _, message in findings)
    assert [status for status, _ in findings].count("FAIL") == 2
    assert "example-db-password" not in text and "example-jwt-secret-value" not in text
    assert any("ALLOW_REGISTRATION" in message for _, message in findings)

    fresh = {**env, "POSTGRES_PASSWORD": "x" * 40, "JWT_SECRET": "y" * 64, "ALLOW_REGISTRATION": "false"}
    assert preflight.check_env(fresh, example) == [("PASS", ".env has the required keys")]
    assert preflight.check_env({}, example)[0][0] == "FAIL"


def test_preflight_memory_and_disk_thresholds():
    preflight = _script("preflight")
    gib = preflight.GIB
    assert preflight.check_memory(8 * gib, None)[0][0] == "FAIL"
    assert [status for status, _ in preflight.check_memory(16 * gib, 7 * gib)] == ["WARN", "WARN"]
    assert [status for status, _ in preflight.check_memory(32 * gib, 10 * gib)] == ["PASS", "PASS"]
    assert preflight.check_disk(10 * gib)[0] == "FAIL"
    assert preflight.check_disk(20 * gib)[0] == "WARN"
    assert preflight.check_disk(50 * gib)[0] == "PASS"
