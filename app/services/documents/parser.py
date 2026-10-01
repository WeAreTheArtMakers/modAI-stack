import io
from pathlib import Path
from pypdf import PdfReader
ALLOWED = {".txt", ".md", ".pdf"}
def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED: raise ValueError("unsupported document type")
    if suffix == ".pdf": return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    return data.decode("utf-8", errors="strict")

