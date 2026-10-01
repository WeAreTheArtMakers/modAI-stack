import asyncio
import os
from pathlib import Path
from uuid import uuid4
from app.core.config import get_settings

class FileStorage:
    """Local storage with generated paths; user filenames never become paths."""
    def __init__(self, root: str | None = None):
        self.root = Path(root or get_settings().data_dir).resolve()
        self.uploads = self.root / "uploads"

    def _path(self, suffix: str) -> Path:
        self.uploads.mkdir(parents=True, exist_ok=True)
        return self.uploads / f"{uuid4().hex}{suffix.lower()}"

    async def save(self, data: bytes, suffix: str) -> str:
        path = self._path(suffix)
        temp = path.with_suffix(path.suffix + ".tmp")
        await asyncio.to_thread(temp.write_bytes, data)
        await asyncio.to_thread(os.replace, temp, path)
        return str(path)

    async def read(self, stored_path: str) -> bytes:
        path = Path(stored_path).resolve()
        if self.uploads not in path.parents:
            raise ValueError("invalid stored file path")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, stored_path: str | None) -> None:
        if not stored_path: return
        path = Path(stored_path).resolve()
        if self.uploads in path.parents and path.exists():
            await asyncio.to_thread(path.unlink)

storage = FileStorage()
