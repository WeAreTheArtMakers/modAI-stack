"""Report whether Compose database variables are configured, never their values."""

import os
from pathlib import Path

from dotenv import dotenv_values

REQUIRED = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")


def check_compose_env(path: Path = Path(".env")) -> dict[str, bool]:
    values = dotenv_values(path) if path.is_file() else {}
    return {key: bool(os.environ.get(key) or values.get(key)) for key in REQUIRED}


def main() -> None:
    result = check_compose_env()
    for key, present in result.items():
        print(f"{key}: {'SET' if present else 'MISSING'}")
    if not all(result.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
