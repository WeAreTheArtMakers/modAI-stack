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


class RefreshSessionService:
    """Redis-backed, one-time refresh JWT sessions.

    Redis only stores a random JWT identifier and its subject, never a refresh
    token itself. ``GETDEL`` makes use of a refresh token a single atomic
    operation, so a successfully rotated credential cannot be replayed.
    """

    prefix = "modai:refresh-session:"

    def __init__(self, client: Redis | None = None):
        self.client = client or Redis.from_url(get_settings().redis_url, decode_responses=True)

    async def create(self, jti: str, user_id: int, ttl_seconds: int) -> bool:
        return bool(await self.client.set(self.prefix + jti, str(user_id), ex=ttl_seconds, nx=True))

    async def consume(self, jti: str, user_id: int) -> bool:
        value = await self.client.getdel(self.prefix + jti)
        return value == str(user_id)

    async def revoke(self, jti: str) -> None:
        await self.client.delete(self.prefix + jti)

    async def close(self) -> None:
        await self.client.aclose()


class RedisRateLimiter:
    prefix = "modai:rate-limit:"
    _increment_with_ttl = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return count
    """

    def __init__(self, client: Redis | None = None):
        self.client = client or Redis.from_url(get_settings().redis_url, decode_responses=True)

    async def enforce(self, bucket: str, key: str, limit: int, window_seconds: int) -> None:
        redis_key = f"{self.prefix}{bucket}:{key}"
        count = int(await self.client.eval(self._increment_with_ttl, 1, redis_key, window_seconds))
        if count > limit:
            raise HTTPException(429, "Too many requests. Please try again later.")

    async def close(self) -> None:
        await self.client.aclose()
