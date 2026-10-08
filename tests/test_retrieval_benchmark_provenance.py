import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.retrieval import provenance
from benchmarks.retrieval import run as benchmark_run
from benchmarks.retrieval.provenance import (
    discover_git_sha,
    normalize_runtime_build_sha,
    normalize_source_sha,
    resolve_source_sha,
)
from benchmarks.retrieval.reporting import render_markdown
from benchmarks.retrieval.runner import (
    DeterministicFixtureEmbedder,
    RunConfiguration,
    run_benchmark_sync,
)
from benchmarks.retrieval.schema import load_dataset


FIXTURE = Path("benchmarks/retrieval/datasets/v1/fixture.json")
SOURCE_SHA = "213cc6ec9e5076cf77a19779083fc1143afb1252"
OTHER_SHA = "fd62278921956bb74860279b6f17c5eaa5a9b085"


def _never_called():
    raise AssertionError("git discovery must not run when an explicit SHA is supplied")


def _dry_run_config(**provenance_fields) -> RunConfiguration:
    return RunConfiguration(
        dataset=load_dataset(FIXTURE),
        embedding_model="deterministic-hash-stub",
        embedding_revision="not-applicable",
        embedding_dimension=DeterministicFixtureEmbedder.dimension,
        query_prefix="",
        passage_prefix="",
        chunk_size=700,
        chunk_overlap=100,
        top_k=5,
        execution_mode="dry-run; synthetic hash vectors; not embedding-model quality",
        device="deterministic-stub",
        **provenance_fields,
    )


def _cli_dry_run(tmp_path, *extra: str) -> dict:
    exit_code = benchmark_run.main(
        [
            "--dry-run",
            "--dataset",
            str(FIXTURE),
            "--chunk-size",
            "700",
            "--chunk-overlap",
            "100",
            "--output",
            str(tmp_path),
            *extra,
        ]
    )
    assert exit_code == 0
    return json.loads((tmp_path / "retrieval-benchmark-v1.json").read_text(encoding="utf-8"))


def test_valid_explicit_source_sha_is_accepted():
    assert resolve_source_sha(SOURCE_SHA, _never_called) == (SOURCE_SHA, "explicit")


def test_uppercase_source_sha_is_normalized_to_lowercase():
    assert normalize_source_sha(SOURCE_SHA.upper()) == SOURCE_SHA
    assert resolve_source_sha(SOURCE_SHA.upper(), _never_called) == (SOURCE_SHA, "explicit")


@pytest.mark.parametrize("value", ["", SOURCE_SHA[:39], SOURCE_SHA + "0", SOURCE_SHA[:7]])
def test_source_sha_with_invalid_length_is_rejected(value):
    with pytest.raises(ValueError, match="40 hexadecimal"):
        resolve_source_sha(value, _never_called)


@pytest.mark.parametrize(
    "value",
    ["g" * 40, "0x" + SOURCE_SHA[:38], " " + SOURCE_SHA[:39], SOURCE_SHA[:39] + "\n", "main".ljust(40, "z")],
)
def test_source_sha_with_non_hex_characters_is_rejected(value):
    with pytest.raises(ValueError, match="40 hexadecimal"):
        resolve_source_sha(value, _never_called)


def test_explicit_source_sha_takes_precedence_over_git_discovery():
    calls = []

    def discover():
        calls.append(True)
        return OTHER_SHA

    assert resolve_source_sha(SOURCE_SHA, discover) == (SOURCE_SHA, "explicit")
    assert calls == []


def test_git_discovery_is_used_when_no_explicit_source_sha():
    assert resolve_source_sha(None, lambda: OTHER_SHA.upper()) == (OTHER_SHA, "git")


@pytest.mark.parametrize("discovered", [None, "", "not-a-sha", OTHER_SHA[:12]])
def test_source_sha_is_unavailable_without_valid_git_metadata(discovered):
    assert resolve_source_sha(None, lambda: discovered) == (None, "unavailable")


def test_git_discovery_returns_none_without_git_tooling(monkeypatch):
    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(provenance.subprocess, "run", missing_git)
    assert discover_git_sha() is None


def test_git_discovery_runs_in_benchmark_source_directory_and_validates_output(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["cwd"] = kwargs["cwd"]
        return SimpleNamespace(stdout="fatal: not a git repository\n")

    monkeypatch.setattr(provenance.subprocess, "run", fake_run)
    assert discover_git_sha() is None
    assert seen["command"] == ["git", "rev-parse", "HEAD"]
    assert seen["cwd"] == Path(provenance.__file__).resolve().parent

    monkeypatch.setattr(
        provenance.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(stdout=OTHER_SHA.upper() + "\n"),
    )
    assert discover_git_sha() == OTHER_SHA

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 3)

    monkeypatch.setattr(provenance.subprocess, "run", timeout)
    assert discover_git_sha() is None


def test_runtime_build_sha_accepts_only_full_shas():
    assert normalize_runtime_build_sha(OTHER_SHA.upper()) == OTHER_SHA
    assert normalize_runtime_build_sha("development") is None
    assert normalize_runtime_build_sha(None) is None


@pytest.mark.parametrize(
    ("source_sha", "origin"),
    [
        (None, "explicit"),
        (None, "git"),
        (SOURCE_SHA, "unavailable"),
        (SOURCE_SHA, "build"),
        (SOURCE_SHA.upper(), "explicit"),
        ("test-sha", "explicit"),
    ],
)
def test_run_configuration_rejects_inconsistent_source_provenance(source_sha, origin):
    with pytest.raises(ValueError):
        _dry_run_config(source_sha=source_sha, source_sha_origin=origin)


def test_report_metadata_separates_source_and_runtime_provenance():
    report = run_benchmark_sync(
        _dry_run_config(
            source_sha=SOURCE_SHA,
            source_sha_origin="explicit",
            runtime_build_sha=OTHER_SHA,
        ),
        DeterministicFixtureEmbedder(),
    )
    metadata = report["metadata"]
    assert report["schema_version"] == 2
    assert metadata["source_sha"] == SOURCE_SHA
    assert metadata["source_sha_origin"] == "explicit"
    assert metadata["runtime_build_sha"] == OTHER_SHA
    assert "git_sha" not in metadata
    markdown = render_markdown(report)
    assert f"Benchmark source SHA: `{SOURCE_SHA}` (explicit)" in markdown
    assert f"Runtime build SHA (dependency image, not the benchmark source): `{OTHER_SHA}`" in markdown


def test_report_metadata_marks_unavailable_source_provenance():
    report = run_benchmark_sync(
        _dry_run_config(source_sha=None, source_sha_origin="unavailable"),
        DeterministicFixtureEmbedder(),
    )
    assert report["metadata"]["source_sha"] is None
    assert report["metadata"]["source_sha_origin"] == "unavailable"
    assert report["metadata"]["runtime_build_sha"] is None
    markdown = render_markdown(report)
    assert "Benchmark source SHA: unavailable (unavailable)" in markdown
    assert "Runtime build SHA (dependency image, not the benchmark source): not recorded" in markdown


def test_cli_records_explicit_source_sha_without_git_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_run, "discover_git_sha", _never_called)
    metadata = _cli_dry_run(tmp_path, "--source-sha", SOURCE_SHA.upper())["metadata"]
    assert metadata["source_sha"] == SOURCE_SHA
    assert metadata["source_sha_origin"] == "explicit"


def test_cli_rejects_malformed_source_sha_before_writing_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_run, "discover_git_sha", _never_called)
    with pytest.raises(SystemExit):
        _cli_dry_run(tmp_path, "--source-sha", "not-a-sha")
    assert not (tmp_path / "retrieval-benchmark-v1.json").exists()


def test_cli_falls_back_to_git_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_run, "discover_git_sha", lambda: OTHER_SHA)
    metadata = _cli_dry_run(tmp_path)["metadata"]
    assert metadata["source_sha"] == OTHER_SHA
    assert metadata["source_sha_origin"] == "git"


def test_cli_never_uses_runtime_build_sha_as_source_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_run, "discover_git_sha", lambda: None)
    monkeypatch.setattr(
        benchmark_run,
        "get_settings",
        lambda: SimpleNamespace(chunk_size=700, chunk_overlap=100, build_sha=OTHER_SHA),
    )
    metadata = _cli_dry_run(tmp_path)["metadata"]
    assert metadata["source_sha"] is None
    assert metadata["source_sha_origin"] == "unavailable"
    assert metadata["runtime_build_sha"] == OTHER_SHA


def test_cli_source_provenance_does_not_mutate_production_configuration(tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(benchmark_run, "discover_git_sha", _never_called)
    settings_before = get_settings().model_dump()
    environment_before = dict(os.environ)
    _cli_dry_run(tmp_path, "--source-sha", SOURCE_SHA)
    assert get_settings().model_dump() == settings_before
    assert dict(os.environ) == environment_before
