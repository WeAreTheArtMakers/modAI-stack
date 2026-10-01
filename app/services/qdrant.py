from qdrant_client import AsyncQdrantClient
from app.core.config import get_settings
class QdrantService:
    def __init__(self): self.client = AsyncQdrantClient(url=get_settings().qdrant_url)
    async def health_check(self) -> bool:
        try: await self.client.get_collections(); return True
        except Exception: return False

