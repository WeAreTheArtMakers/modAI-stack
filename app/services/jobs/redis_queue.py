import json
from redis.asyncio import Redis
from app.core.config import get_settings
class RedisIndexQueue:
    key = "modai:indexing:queued"
    def __init__(self, client: Redis | None = None): self.client = client or Redis.from_url(get_settings().redis_url, decode_responses=True)
    async def enqueue(self, job_id: str): await self.client.rpush(self.key, json.dumps({"job_id": job_id}))
    async def dequeue(self, timeout: int = 5) -> str | None:
        item = await self.client.blpop(self.key, timeout=timeout)
        return json.loads(item[1])["job_id"] if item else None
    async def close(self): await self.client.aclose()
    async def publish_progress(self, event: dict): await self.client.publish("modai:indexing:events", json.dumps(event))
