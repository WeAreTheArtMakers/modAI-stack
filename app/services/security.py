"""Redis-backed, short-lived security primitives shared by HTTP and WebSocket flows."""
import json
import secrets

from fastapi import HTTPException
from redis.asyncio import Redis

from app.core.config import get_settings


class WebSocketTicketService:
    prefix = "modai:ws-ticket:"

    def __init__(self, client: Redis | None = None):
        self.client = client or Redis.from_url(get_settings().redis_url, decode_responses=True)

    async def issue(self, user: dict, scope: str, workspace_id: int | None = None) -> str:
        ticket = secrets.token_urlsafe(32)
        payload = json.dumps({"sub": str(user["sub"]), "role": user["role"], "scope": scope, "workspace_id": workspace_id})
        await self.client.set(self.prefix + ticket, payload, ex=get_settings().websocket_ticket_ttl_seconds, nx=True)
        return ticket

    async def consume(self, ticket: str, scope: str) -> dict:
        if not ticket or len(ticket) > 256:
            raise HTTPException(401, "Invalid WebSocket ticket")
        value = await self.client.getdel(self.prefix + ticket)
        if not value:
            raise HTTPException(401, "WebSocket ticket expired or already used")
        try:
            payload = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(401, "Invalid WebSocket ticket") from exc
        if payload.get("scope") != scope or not payload.get("sub"):
            raise HTTPException(403, "WebSocket ticket scope denied")
        return payload

    async def close(self) -> None:
        await self.client.aclose()


class RedisRateLimiter:
    prefix = "modai:rate-limit:"

    def __init__(self, client: Redis | None = None):
        self.client = client or Redis.from_url(get_settings().redis_url, decode_responses=True)

    async def enforce(self, bucket: str, key: str, limit: int, window_seconds: int) -> None:
        count = await self.client.incr(f"{self.prefix}{bucket}:{key}")
        if count == 1:
            await self.client.expire(f"{self.prefix}{bucket}:{key}", window_seconds)
        if count > limit:
            raise HTTPException(429, "Too many requests. Please try again later.")

    async def close(self) -> None:
        await self.client.aclose()
