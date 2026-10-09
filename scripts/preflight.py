#!/usr/bin/env python3
"""Check a machine before installing or upgrading modAI-stack. Standard library only.

Reports PASS / WARN / FAIL for: Docker and its memory limit, host memory, free disk, the .env
file (required keys set, secrets changed from .env.example, registration closed), the pinned
model files, and the local Ollama generation model. Secret values are never printed.

Usage:
  python3 scripts/preflight.py                  # checks ./.env
  python3 scripts/preflight.py --env-file PATH
Exit status 1 when any check fails.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIB = 1024**3
REQUIRED_KEYS = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "JWT_SECRET", "OLLAMA_MODEL")
SECRET_KEYS = ("POSTGRES_PASSWORD", "JWT_SECRET")
KNOWN_PLACEHOLDERS = {"change-me-in-production", "replace-with-a-long-random-secret", "ci-only-secret", ""}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check_env(env: dict[str, str], example: dict[str, str]) -> list[tuple[str, str]]:
    """Findings for the .env file; never includes a secret value."""
    results = []
    missing = [key for key in REQUIRED_KEYS if not env.get(key)]
    results.append(("FAIL", f".env is missing {', '.join(missing)}") if missing else ("PASS", ".env has the required keys"))
    for key in SECRET_KEYS:
        value = env.get(key, "")
        if value and (value == example.get(key) or value.lower() in KNOWN_PLACEHOLDERS):
            results.append(("FAIL", f"{key} is still the example value; generate a new random secret"))
        elif key == "JWT_SECRET" and value and len(value) < 32:
            results.append(("WARN", "JWT_SECRET is shorter than 32 characters"))
    if env.get("ALLOW_REGISTRATION", "true").lower() == "true":
        results.append(("WARN", "ALLOW_REGISTRATION=true: anyone who reaches the console can create an account; set false after the first admin exists"))
    return results


def check_memory(host_bytes: int | None, docker_bytes: int | None) -> list[tuple[str, str]]:
    results = []
    if host_bytes is None:
        results.append(("WARN", "host memory could not be read"))
    elif host_bytes < 16 * GIB:
        results.append(("FAIL", f"host memory {host_bytes / GIB:.0f} GiB: at least 16 GiB is required"))
    elif host_bytes < 32 * GIB:
        results.append(("WARN", f"host memory {host_bytes / GIB:.0f} GiB: run only this stack (no second stack, few browser tabs); 32 GiB recommended"))
    else:
        results.append(("PASS", f"host memory {host_bytes / GIB:.0f} GiB"))
    if docker_bytes is not None:
        if docker_bytes < 8 * GIB:
            results.append(("WARN", f"Docker memory limit {docker_bytes / GIB:.1f} GiB: the multilingual (BGE-M3) profile needs about 2 GiB in each of api and worker; set at least 8 GiB"))
        else:
            results.append(("PASS", f"Docker memory limit {docker_bytes / GIB:.1f} GiB"))
    return results


def check_disk(free_bytes: int) -> tuple[str, str]:
    if free_bytes < 15 * GIB:
        return ("FAIL", f"free disk {free_bytes / GIB:.0f} GiB: at least 15 GiB needed for images, models and data")
    if free_bytes < 30 * GIB:
        return ("WARN", f"free disk {free_bytes / GIB:.0f} GiB: leave room for backups and growth (30 GiB+ recommended)")
    return ("PASS", f"free disk {free_bytes / GIB:.0f} GiB")


def _host_memory() -> int | None:
    try:
        if platform.system() == "Darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True).stdout)
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None
    return None


def _docker() -> tuple[list[tuple[str, str]], int | None]:
    if shutil.which("docker") is None:
        return [("FAIL", "docker is not installed")], None
    try:
        info = subprocess.run(["docker", "info", "--format", "{{json .MemTotal}}"], capture_output=True, text=True, timeout=30)
        compose = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return [("FAIL", "docker did not answer")], None
    results = []
    if info.returncode != 0:
        return [("FAIL", "docker is installed but not running")], None
    results.append(("PASS", "docker is running"))
    results.append(("PASS", f"docker compose {compose.stdout.strip()}") if compose.returncode == 0 else ("FAIL", "docker compose plugin is missing"))
    try:
        return results, int(json.loads(info.stdout))
    except ValueError:
        return results, None


def _script_check(script: str, *args: str) -> tuple[str, str]:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--check", *args], capture_output=True, text=True)
    name = script.removeprefix("fetch_").removesuffix(".py").replace("_", " ")
    if result.returncode == 0:
        return ("PASS", f"{name}: files present and verified")
    return ("FAIL", f"{name}: missing or changed files; run python3 scripts/{script} {' '.join(args)}".strip())


def _ollama(base_url: str, model: str) -> tuple[str, str]:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=10) as response:
            names = {item.get("name") for item in json.load(response).get("models", [])}
    except (OSError, ValueError):
        return ("FAIL", f"Ollama is not reachable at {base_url}")
    if model in names or f"{model}:latest" in names:
        return ("PASS", f"Ollama has {model}")
    return ("FAIL", f"Ollama does not have {model}; run: ollama pull {model}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    args = parser.parse_args(argv)

    results: list[tuple[str, str]] = []
    docker_results, docker_memory = _docker()
    results += docker_results
    results += check_memory(_host_memory(), docker_memory)
    results.append(check_disk(shutil.disk_usage(ROOT).free))
    env: dict[str, str] = {}
    if args.env_file.is_file():
        env = read_env(args.env_file)
        results += check_env(env, read_env(ROOT / ".env.example"))
    else:
        results.append(("FAIL", f"{args.env_file} not found; copy .env.example and set new secrets"))
    results.append(_script_check("fetch_voice_models.py"))
    results.append(_script_check("fetch_retrieval_models.py"))
    minilm = ROOT / env.get("MODEL_DIR", "./models") / "cache" / "models--sentence-transformers--all-MiniLM-L6-v2"
    results.append(("PASS", "MiniLM embedding model cached") if minilm.is_dir() else ("FAIL", "MiniLM embedding model missing; run python -m app.tools.prefetch_embedding_model with EMBEDDING_ALLOW_DOWNLOAD=true"))
    results.append(_ollama(os.environ.get("OLLAMA_URL", args.ollama_url), env.get("OLLAMA_MODEL") or "modAIJet:latest"))

    for status, message in results:
        print(f"{status:5s} {message}")
    failed = sum(status == "FAIL" for status, _ in results)
    print(f"\n{failed} failed, {sum(status == 'WARN' for status, _ in results)} warnings")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
